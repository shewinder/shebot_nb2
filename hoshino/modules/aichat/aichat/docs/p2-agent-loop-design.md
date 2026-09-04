# P2 设计：AgentLoop 统一 与 Reply 管道

> 状态：已评审通过并实施（2026-08）。第 11 节 4 个决策点全部按"确认"执行：
> 删除 max_history、AgentResult 保留子会话、auto-attach 对 bg/scheduled 生效、
> `subagent_profiles[0]` 回落怪癖保持不变。实施完成后 git 提交待用户指令。
> 关联：`../README_ARCH.md`（P0/P1 已落地的规范）

## 1. 背景与目标

### 现状问题

- 三条"隔离会话执行"路径（delegate_task / 后台任务 / 定时任务）各自拼装 `run_agent`
  参数，`blocked_tools` 等语义复制粘贴 3 份，新需求要改 3 处。
- 两个已确诊 bug：
  - **令牌泄露**：后台/定时任务 `_send_result` 传 `session=None`，结果里的
    `<ai_image_N>` 以字面量发给用户（`_send_util.py` 无 session 时跳过解析）。
  - **跨会话错位**：子 Agent 的图片编号独立于父会话，其返回文本被主模型
    原样引用后，父会话解析出**同号不同图**。
- 图片发送是裸正则替换：写错格式的令牌静默消失、图片位置保真度为零、
  去重只在单条消息内。
- `max_history` 配置从未生效（用户决策：**不保留，直接删除**）。

### 目标

1. 单一执行循环：`AgentTask`（规格）+ `run_agent_loop`（实现）取代 `run_agent`。
2. 修掉上述两个 bug。
3. 图片发送升级为 Reply 管道（显式发送/保序/容错/会话级去重）。
4. Session 生命周期内聚（`Session.dispose()` 统一清理）。

### 非目标（明确不做）

- 不改主对话链路（`chat.py` 继续用 `ChatExecutor`，仅发送侧经 Reply 管道）。
- 不做工具权限接线、成本上限（P3）；命令层拆分、可观测性（P4）。
- 不引入新依赖。

## 2. 现状路径梳理

### 2.1 三个调用方差异矩阵（改造前实测基线）

| 参数 | delegate_task | background_task | scheduled_task |
|---|---|---|---|
| system_prompt | 类型定义（search/vision） | `_BG_SYSTEM_PROMPT` | 固定一句 |
| session_prefix | `subagent_{parent.session_id}` | `bg_task_{task.id}` | `agent_task_{task.id}_{uuid6}` |
| max_rounds | profile 覆盖，否则 `subagent_max_rounds` | `subagent_max_rounds` | `subagent_max_rounds` |
| blocked_tools | `{run_background_task, delegate_task, schedule_task}` | 同左 | 同左 |
| locked_tools | True（每轮不重取工具） | False | False |
| preactivate_skills | 有（AI 传入） | 有 | 有 |
| profile | `agent_type` | 无 | 无 |
| image_identifiers | 有 | 无 | 无 |
| parent_session | 有 | 无 | 无 |
| 结果去向 | `ok(content)` 回主循环 | `_send_result` 发用户 | `_send_result` 发用户 |

### 2.2 关键耦合点（设计必须兼容）

- `tools/__init__.py:72`：`wait_and_resume` 仅对 `session_id.startswith("bg_task_")`
  的会话可见 → **新 session_id 必须保留前缀语义**。
- `_resolve_api_config` 的既有怪癖：无 profile 时若有 `subagent_profiles`，
  会回落到 `subagent_profiles[0]`（即 bg/scheduled 现在可能正在用 profiles[0] 的 API）。
  → **保持行为对齐**，文档标注为已知怪癖，不在本轮改变（改 API 归属影响成本）。
- `ChatExecutor.chat` 已含工具循环与 usage 记账，AgentLoop 不重写循环，
  只做"会话创建/提示注入/资源传递/清理"的编排。

## 3. AgentTask 规格（pydantic）

```python
class AgentTask(BaseModel):
    task: str                              # user 消息内容
    system_prompt: str                     # 子 Agent 系统提示
    user_id: int
    group_id: Optional[int] = None
    tools: Optional[List[Dict[str, Any]]] = None  # None=自动全量；[]=无工具；否则白名单
    max_rounds: int = 10
    profile: Optional[str] = None          # 子 Agent 模型配置名
    persona: Optional[str] = None
    image_identifiers: List[str] = []
    parent_session: Optional[Session] = None
    preactivate_skills: List[str] = []
    blocked_tools: frozenset = frozenset()
    locked_tools: bool = False             # True=首轮后不重取工具
    session_prefix: str = "agent"          # 仅语义前缀；真实 id 会追加 uuid
    label: str = "sub"                     # 日志标识
    api_config: Optional[Dict[str, Any]] = None  # 显式指定时跳过 profile 解析
```

校验规则：
- `max_rounds` 夹取到 `[1, conf.max_tool_rounds]`；
- `blocked_tools` 必须是工具名的 frozenset；
- `task` 非空（strip 后）。

## 4. AgentLoop 设计

```python
@dataclass
class AgentResult:
    result: ChatResult        # 与现 ChatResult 完全一致（行为对齐）
    session: Session          # 已解除注册，但对象保留供图片解析/发送/清理
```

```python
async def run_agent_loop(task: AgentTask) -> AgentResult:
    # 1. 解析 api_config：显式参数 > profile > subagent_profiles[0] > 主 API
    #    （复用现 _resolve_api_config 语义）
    # 2. session_id = f"{task.session_prefix}_{uuid4().hex[:8]}"   ← 根治竞态
    #    确保前缀语义保留（bg_task_ / agent_task_ / subagent_）
    # 3. Session(register=True)；设置 agent_label / _blocked_tools /
    #    _subagent_locked_tools
    # 4. 预激活 skills（失败仅告警，不中断）
    # 5. 图片传递：task.parent_session 存在时执行 _copy_images，
    #    并记录映射 {child_identifier: parent_identifier}（供 rehome 使用）
    # 6. 构建 user 消息：多模态（api 支持时嵌 data_url）或纯文本+标识符
    # 7. ChatExecutor(session).chat(api_config, tools, max_rounds)
    # 8. finally：仅当 registry 中仍是我们自己的实例时才 pop
    #    （if session_manager.sessions.get(sid) is session: pop）
    # 9. 返回 AgentResult（session 未 dispose，由调用方决定何时清理）
```

### 4.1 并发正确性

- uuid 后缀保证同前缀并行任务互不覆盖（修 bug：同轮并行 delegate 互踩）。
- finally 的 `is` 校验保证不会误删后续同名任务（其实 uuid 后不可能同名，双保险）。
- 子会话不注册进 `SessionManager._sweep` 的清理范围（`group_`/`private_` 之外的
  会话本就不被 GC 扫，保持不变）。

### 4.2 错误语义（行为对齐）

- API 未配置 → `AgentResult(result=ChatResult(error="API 未配置"))`，不抛异常。
- 执行异常 → 捕获后包装进 `ChatResult.error`，保证 bg/scheduler 的
  `task.status="failed"` 流程照旧。

## 5. 图片重定位 `rehome_images`

### 5.1 问题

子会话标识符是子会话本地命名空间；文本回传主模型后被父会话解析，错位。

### 5.2 算法

```python
async def rehome_images(
    agent_result: AgentResult, parent: Session,
) -> str:
    content = agent_result.result.content or ""
    # 1. 提取 content 中的裸句柄和显式发送标记（与 Reply 管道共用规则）
    # 2. 对每个裸句柄：
    #    a. 在 image_map（复制溯源映射）中 → 直接替换为父标识符，零拷贝
    #    b. 否则从子会话取 data_url → parent.store_ai_image(url=原url)
    #       → 替换为新的父标识符
    #    c. 拷贝/解析失败 → 降级为字面文本 "[图片]"（不再静默消失）
    # 3. 对显式发送标记执行同样重定位，并保留 [[send_*:...]] 语义
    # 4. 不自动追加未被引用的媒体；返回重写后的 content
```

### 5.3 生命周期约定

- delegate：`rehome_images` 后调用 `agent_result.session.dispose()`（子会话磁盘
  图片目录清空，修复孤儿目录累积）。
- bg/scheduled：发送结果后 `dispose()`；发送期间 session 仍存活
  （修令牌泄露：`_send_result(task, content, session=agent_result.session)`）。

## 6. Reply 管道

### 6.1 模型

```python
@dataclass
class ReplyPart:
    kind: Literal["text", "image", "video", "at"]
    text: str = ""                 # kind=text
    identifier: str = ""           # kind=image/video（规范化后的标识符）
    qq_id: int = 0                 # kind=at
```

### 6.2 build_reply 算法

```python
async def build_reply(
    content: str,
    session: Optional[Session],
    *,
) -> List[ReplyPart]:
    # 1. 仅解析 [[send_image:...]] / [[send_video:...]] 与 @ 标记；裸媒体句柄不发送
    # 2. session 为 None → 显式发送命令降级为文本；
    #    解析失败（编号不存在/文件丢失）→ 降级字面文本 + warning 日志
    # 3. 会话级去重：session._turn_sent_images（每轮 user 消息时重置）
    # 4. 不自动补发未被显式引用的媒体
    # 5. 返回有序 parts
```

### 6.3 send_reply 与兼容层

- `send_reply(parts, group_id, user_id, at_user_id)`：沿用现有
  plain/markdown/转发合并逻辑（`_send_util.py` 已有实现搬入）。
- `send_ai_response(content, session, ...)` 保留签名，改为
  `build_reply` + `send_reply` 的薄包装 → **所有现有调用方零改动**。

### 6.4 Session 新增字段

- `_turn_sent_images: Set[str]`（Reply 管道去重状态）

## 7. Session 生命周期内聚

```python
def dispose(self) -> None:
    """统一清理会话资源：图片目录 + MCP 状态 + 会话锁"""
    self._image_store.clear()
    mcp_sm.clear_session(self.session_id)   # 原散落在 SessionManager
    _session_locks.pop(self.session_id, None)

# SessionManager._remove_session 改为：
#   del sessions[sid] → sessions[sid].dispose()
```

清理逻辑从"删 session 时手动记得清 MCP"收敛为 Session 自身职责。

## 8. 实施顺序（评审通过后按此执行）

| 步 | 内容 | 验证预期 |
|---|---|---|
| 1 | `agent_loop.py`：AgentTask/AgentResult/run_agent_loop（含 uuid、`is` 校验） | 单测：并发两 loop 互不覆盖 |
| 2 | `rehome_images` + `_copy_images` 溯源映射 | 单测：映射命中零拷贝、未命中拷贝、失败降级 |
| 3 | `reply.py`：build_reply/send_reply + `_send_util` 薄包装 | 单测：保序/容错/去重/auto-attach |
| 4 | 三调用方接入 AgentLoop + 修令牌泄露；删除 `_agent_runner.py` | 集成冒烟：三条路径行为对齐（日志基线对比） |
| 5 | `Session.dispose()` 内聚 + 调用方 dispose 时机 | 冒烟：孤儿目录不再累积 |
| 6 | `config.py` 删 `max_history`；README_ARCH 记录 | 配置加载正常 |
| 7 | 全量验证 + diff 展示 | 新旧测试全绿 |

## 9. 测试设计

- `test/aichat/test_agent_loop.py`
  - gateway 注入 MockTransport（复用 P1 手法）；
  - 断言：session_id 含随机后缀；blocked_tools 从工具列表中被过滤；
    `locked_tools` 时工具不重取；profile 解析优先级；执行后 registry 已清。
  - rehome：映射命中/未命中/降级三路径（用内存假 ImageStore）。
- `test/aichat/test_reply.py`
  - 假 ImageStore（dict 实现 get/get_data_url/list_all），不落盘；
  - 用例：裸 `<ai_image_1>` 不发送；`[[send_image:ai_image_1]]` 保序并发送；
    缺失句柄降级字面文本；重复标识符去重；默认不自动补发；
    `session=None` 时显式命令转字面文本。
- 改造前先跑一遍三条路径的日志基线（本地 MockTransport），改造后 diff 对比。

## 10. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 行为漂移（四条路径任一表现变化） | 步骤 4 前录制日志基线；每步独立可回滚 |
| Reply 管道影响所有出站消息 | `send_ai_response` 签名不变，改动集中在新文件 + 薄包装 |
| 子会话 dispose 过早导致发图失败 | dispose 时机明确写入调用方（发送后）；集成冒烟覆盖 |
| `subagent_profiles[0]` 怪癖被无意改变 | 设计明确"保持对齐"，不触碰 API 归属逻辑 |

## 11. 待评审的决策点（请重点看）

1. `max_history` 直接删除配置字段（Pydantic 模型里移除），不做任何兼容——
   与项目"不保留旧配置"原则一致，确认？
2. `AgentResult.session` 保留子会话对象直到调用方 dispose——接受？
3. 未被显式发送标记引用的媒体不会自动发送，背景/定时任务同样遵循此规则
   （其 user 消息即任务文本）——接受？
4. `_resolve_api_config` 的 `subagent_profiles[0]` 回落怪癖本轮保持不变——接受？
