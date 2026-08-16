# 设计：Skill 自更新系统（Bot 自主创建/更新/回滚 Skill）

> 状态：设计稿（待评审，评审通过后才动代码）
> 决策点（已拍板）：A1 管理工具默认 SUPERUSER；B1 内置 skill 只读，
> 更新内置 = 用户路径生成覆盖副本；C2 删除帮助文本中不存在的停用命令。
> 关联：`../README_ARCH.md`（P0-P4 已落地的基础设施）

## 1. 目标

让 AI 在会话中自主完成"创建新 skill / 改进已有 skill / 失败回滚"的闭环，
且满足：内置 skill 文件不被修改、变更全局共享资源需 SUPERUSER、可审计可回滚。

## 2. 现状底座（P0-P4 已就绪，本设计直接复用）

- SKILL 格式：`SKILL.md`（YAML frontmatter: name/description）+ `_meta.json` + `scripts/`
- 双路径：内置（git 跟踪，只读）+ 用户路径 `data/skills`（gitignore，同名覆盖内置）
- `skill_manager.reload()` 已实现（整表原子替换；会话激活只存名字，reload 后新内容自动生效）
- 权限双层接线（P3）：schema 层过滤 + 执行层校验，`Config.tool_permissions` 可覆盖
- 工具执行兜底超时（P3 `conf.tool_timeout`）、`execute_script` 仅限已激活 skill 目录

## 3. 存储约定

```
data/skills/
├── <name>/SKILL.md              # 用户 skill（同名覆盖内置）
├── .backup/<name>/<ts>/         # 每次写前的完整目录备份（保留最近 5 份）
└── .changes.jsonl               # 审计日志（action/时间/触发者/大小/来源/backup_id）
```

discovery 只认含 `SKILL.md` 的目录，`.backup`/`.changes.jsonl` 天然不被扫描。

## 4. 组件设计

### 4.1 能力层 `skills/updater.py`（同步、不 import hoshino 之外的重依赖）

| 函数 | 职责 |
|---|---|
| `validate_skill_name(name)` | 严格字符集 `[a-z0-9_-]{1,50}`，拒绝 `..`/`/`/空格/中文 |
| `parse_frontmatter(content)` | 从 `discovery.py` 提升为公开函数，discovery 与 updater 共用（写前校验与读时解析一致） |
| `create_skill(name, description, content, scripts)` | 校验→写 `data/skills/<name>/`→审计→reload |
| `update_skill(name, content?, description?, scripts?)` | 写前备份；**内置 skill** → 先整目录复制到用户路径再改副本（B1） |
| `delete_skill(name)` | 仅用户路径 skill；内置拒绝 |
| `rollback_skill(name)` | 恢复最新备份；无备份时删除用户副本（回退到内置） |
| `reload_skills()` | 调 `skill_manager.reload()`，返回新名称列表 |
| `_backup(name)` / `_list_backups(name)` | 目录拷贝备份 + 保留最近 5 份轮换 |

**限制**：SKILL.md ≤ 50KB；scripts ≤ 10 个、单个 ≤ 100KB；用户 skill 总数 ≤ 50。
**并发**：模块级 `threading.Lock` 串行化全部写操作（低频操作，全局锁足够）。
**写后自检**：update/create 后立即 reload 并确认 `get_skill(name)` 存在且解析成功；
解析失败 → 自动恢复备份并返回错误（AI 改坏 skill 不会造成静默消失）。

### 4.2 工具层 `tools/builtin/skill_admin.py`

| 工具 | 权限（DEFAULT_TOOL_PERMISSIONS） | 说明 |
|---|---|---|
| `create_skill(name, description, content, scripts?)` | SUPERUSER | scripts: `{相对路径: 文件内容}` |
| `update_skill(name, content?, description?, scripts?)` | SUPERUSER | 部分更新；内置→用户副本 |
| `delete_skill(name)` | SUPERUSER | 仅用户路径 |
| `rollback_skill(name)` | SUPERUSER | 恢复上一版 |
| `reload_skills()` | SUPERUSER | 手动热重载（含"改完不生效"修复） |

工具描述中写明验证闭环流程：改 → `reload_skills` → `activate_skill` →
`execute_script` 自测 → 失败 `rollback_skill`。

### 4.3 审计

`.changes.jsonl` 每条：`{ts, action, skill, user_id, group_id, from(内置|用户|新建), size, backup_id}`。
操作日志经 `infra.logging.sanitize` 后打印（内容本身持久化到审计文件，不进日志）。

### 4.4 帮助文本修正（C2）

`service.py` help 删除「#停用技能 <skill名称>」「#停用所有技能」两行（命令不存在）。

## 5. 风险与对策

| 风险 | 对策 |
|---|---|
| AI 写坏 SKILL.md（格式错→静默消失） | 写前 frontmatter 校验 + 写后 reload 自检 + 自动回滚备份 |
| AI 写的脚本直接上生产执行 | 执行仍受 execute_script 三重限制（激活+目录+超时）；创建面限 SUPERUSER |
| 并发写同名 skill | updater 全局锁串行化 |
| 备份膨胀 | 每 skill 保留最近 5 份轮换 |
| 路径遍历/覆盖任意文件 | 名称严格字符集 + 目标目录强制在用户 skill 路径下 |
| 覆盖内置后想回退 | 删除用户副本即回退到内置（rollback 语义覆盖） |

## 6. 测试设计（`test/aichat/test_skill_updater.py`）

- updater 单测（隔离临时 skill 路径）：create/update/delete/rollback、备份轮换、
  审计写入、非法名称拒绝、内置只读、内置更新生成用户副本、写坏自动回滚
- 工具层：普通用户 schema 不可见（SUPERUSER 过滤）+ 执行被拒；超管放行
- 集成：create → reload → `skill_manager.list_skills()` 出现新 skill

## 7. 文件清单（约 6 个）

| 类型 | 文件 |
|---|---|
| 新增 | `skills/updater.py`、`tools/builtin/skill_admin.py`、`test/aichat/test_skill_updater.py` |
| 修改 | `skills/discovery.py`（提公开 parse_frontmatter）、`tools/permission.py`（5 个 SUPERUSER 条目）、`service.py`（help 删 2 行） |

## 8. 实施顺序（评审通过后）

1. `discovery.py` 提公共解析函数（无行为变化）
2. `updater.py` + 单测（核心：校验/备份/回滚/审计/自检回滚）
3. `skill_admin.py` 工具注册 + 权限条目 + service.py help 修正
4. 工具层/集成测试 + 全量验证 + diff

## 9. 待评审决策点（补充）

1. 备份保留份数：5 份（默认）？可配？
2. 是否需要 `test_skill` 便捷工具（reload+activate+execute 一步封装），还是只靠工具描述指导？
3. 用户 skill 总数上限 50：作为 Config 项（`skill_max_user_skills`）还是常量？
