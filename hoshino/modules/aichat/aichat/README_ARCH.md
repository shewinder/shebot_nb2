# aichat 架构规范与重构路线

> 本文件是 aichat 插件的**工程规范基准**。新增/修改代码前先读这里；
> 与规范冲突的写法不再新增，存量代码按重构路线逐步收敛。

## 一、冻结的规范（P0）

### 1. HTTP 客户端

- 所有 HTTP 请求必须走 `httpx`；LLM API 调用必须经 `infra.llm_gateway.LLMGateway`
  （统一连接池、超时、重试、错误分类、日志脱敏）。
- **禁止**新增 `aiohttp` / `aiohttpx` / `requests` 调用。
- 存量旧客户端（`aiohttpx` 等）在修改到对应文件时顺手替换为 httpx。

### 2. 错误模型

- 新增代码的失败必须用 `infra.errors.AppError` 子类（带 `code` / `retryable`）或
  `infra.errors.Result[T]` 表达，**禁止**返回裸字符串错误、解析 `str(e)` 判断类型。
- 需要区分处理时用 `isinstance(err, LLMRateLimitedError)` 等类型判断，不用字符串匹配。

### 3. 日志

- 进入日志的**任何** LLM 请求/响应、工具结果，必须先经 `infra.logging.sanitize()`
  脱敏（base64 图片数据 → 占位符、超长截断）。
- 禁止把 `api_key`、完整 base64 图片、超大 JSON 直接打进日志。
- 长耗时/多并发流程建议用 `infra.logging.log_context()` + `log_tag()` 携带
  session/task 标识（P2 起逐步接入）。

### 4. 配置

- 读取配置做快照：`Config.snapshot()`（`model_dump()`），避免长流程中配置被并发修改。
- 修改配置的写入路径必须持有 `config.config_write_guard()` 锁（threading.RLock，
  兼容同步/异步调用方）。

### 5. 基础设施层边界

- `aichat/infra/` 下所有模块**禁止 import hoshino**，配置一律参数注入，
  保证可用 `httpx.MockTransport` 等标准库手段独立单测。
- 测试放 `test/aichat/`，使用 unittest（与项目现有测试风格一致），
  测试通过 `sys.path` 直接引入 `aichat/infra` 包，不初始化 NoneBot。

### 6. 其它既有约定（重申）

- 禁止函数内 import；类型注解齐全；注释解释"为什么"。
- 工具返回统一用 `tools.registry.ok() / fail()`（chat_executor 执行层统一整形）。
- 出站消息统一经 Reply 管道（`reply.build_reply` / `reply.send_reply`），
  图片标识符解析失败降级为字面文本，禁止静默丢弃。
- 未经明确指令不得 git commit。

## 二、目录结构

```
aichat/
├── infra/                  # 底座层（本文件规范的主体，禁止 import hoshino）
│   ├── errors.py           #   AppError 层级 + Result
│   ├── logging.py          #   log_context/log_tag + sanitize
│   └── llm_gateway.py      #   LLMGateway（httpx/超时/重试/脱敏）
├── agent_loop.py           # AgentTask/AgentResult/run_agent_loop（隔离执行统一编排）
├── reply.py                # Reply 管道（build_reply/send_reply）
├── subagent_types.py       # 子 Agent 类型定义（SUBAGENT_TYPES）
├── chat.py                 # 入口处理（会话锁 + _run_chat）
├── chat_executor.py        # 编排（已接入 gateway）
├── session.py              # Session/SessionManager（锁 + GC + dispose）
├── config.py               # 配置（snapshot + 写锁）
├── tools/ mcp/ skills/ memory/ persona/ ...  # 能力层（P3 起接口化）
└── README_ARCH.md          # 本文件
```

## 三、重构路线与状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 统一错误/日志规范、测试锚点、规范文档 | ✅ 已落地 |
| P1 | LLMGateway、config 访问、SessionStore（锁+GC）+ 最小接入 | ✅ 已落地 |
| P2 | AgentLoop/AgentTask 统一执行路径、Reply 管道（图片 bug 修复+兜底）、Session 生命周期内聚 | ✅ 已落地 |
| P3 | 工具权限双层接线、chat_executor 接口定型、gateway 参数接配置、schema 缓存、后台任务上限/表清理、定时任务执行锁、MCP 真并行 | ✅ 已落地 |
| P4 | `__init__.py` 命令层拆分、死代码清理、可观测性（成本/延迟/错误率） | ⬜ 待做 |

## 四、已知债务与决策记录

- 文件 IO 异步化已明确**暂不实施**（用户决策）：async 函数中的同步小文件读写维持现状，
  若未来记忆/图片文件变大成为实测瓶颈再评估 `asyncio.to_thread` 方案。
- `max_history` 配置字段已**删除**（用户决策：从未生效，不保留）。
- `agent_loop._resolve_api_config` 保留"无 profile 时回落 `subagent_profiles[0]`"的
  既有怪癖（影响 bg/scheduled 的 API 归属），未改变，详见 docs/p2-agent-loop-design.md。
- 工具权限默认全 `USER`（用户决策 A1）：机制已接通，管理员经
  `Config.tool_permissions` 收紧（如 `{"execute_script": "SUPERUSER"}`）。
