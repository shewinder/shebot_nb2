"""Skill 自更新工具组

提供给 AI 的 skill 创建/更新/删除/回滚/热重载能力。
权限默认 SUPERUSER（tools/permission.py），双层校验由 P3 框架自动执行。

推荐闭环（写入工具描述）：
update_skill → reload 自动完成 → activate_skill → execute_script 自测
→ 失败 rollback_skill。
"""
from typing import Annotated, Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger
from pydantic import Field

from ...skills import skill_manager, updater
from ..registry import tool_registry, ok, fail

if TYPE_CHECKING:
    from ...session import Session

_SCRIPTS_DESC = "脚本文件字典：{相对路径: 文件内容}，如 {\"scripts/fetch.py\": \"...\"}。路径禁止 .. 和绝对路径"


@tool_registry.register(
    description="""创建一个新的用户 SKILL 并立即热加载（无需重启）。

SKILL 是持久的技能包：SKILL.md 写清"何时用/怎么用"，可附带 scripts/ 脚本。
创建后其他会话也能在下一轮看到并激活它。

## 内容要求
- content 是指导正文（无需写 YAML frontmatter，系统自动生成）
- scripts 可选：{相对路径: 文件内容}，如 {"scripts/search.py": "..."}
- 写前会校验格式，写坏会自动撤销

## 注意
- 名称只允许小写字母/数字/下划线/连字符
- 与内置 SKILL 同名会覆盖内置（慎重）""",
)
async def create_skill(
    name: Annotated[str, Field(description="SKILL 名称（唯一标识）")],
    description: Annotated[str, Field(description="一句话描述用途（供 AI 选择激活）")],
    content: Annotated[str, Field(description="SKILL.md 指导正文")],
    scripts: Annotated[Optional[Dict[str, str]], Field(description=_SCRIPTS_DESC)] = None,
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    if not session:
        return fail("缺少会话上下文", error="Missing session")

    success, msg = updater.create_skill(
        name, description, content, scripts,
        user_id=session.user_id, group_id=session.group_id,
    )
    return ok(msg) if success else fail(msg)


@tool_registry.register(
    description="""更新已有 SKILL 的内容/描述/脚本并立即热加载。

写前自动备份（保留最近 5 版），更新后自动校验，格式损坏自动回滚。
内置 SKILL 只读：更新内置时会在用户路径生成覆盖副本，内置文件不受影响。

## 自测闭环（推荐）
1. update_skill 修改脚本/指导
2. activate_skill 激活
3. execute_script 跑一个测试用例验证
4. 结果不对 → rollback_skill 回滚""",
)
async def update_skill(
    name: Annotated[str, Field(description="SKILL 名称")],
    content: Annotated[Optional[str], Field(description="新的指导正文（省略=保持原样）")] = None,
    description: Annotated[Optional[str], Field(description="新的一句话描述（省略=保持原样）")] = None,
    scripts: Annotated[Optional[Dict[str, str]], Field(description=_SCRIPTS_DESC)] = None,
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    if not session:
        return fail("缺少会话上下文", error="Missing session")

    success, msg = updater.update_skill(
        name, content, description, scripts,
        user_id=session.user_id, group_id=session.group_id,
    )
    return ok(msg) if success else fail(msg)


@tool_registry.register(
    description="删除用户创建的 SKILL（内置 SKILL 只读，无法删除）",
)
async def delete_skill(
    name: Annotated[str, Field(description="SKILL 名称")],
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    if not session:
        return fail("缺少会话上下文", error="Missing session")

    success, msg = updater.delete_skill(name, user_id=session.user_id, group_id=session.group_id)
    return ok(msg) if success else fail(msg)


@tool_registry.register(
    description="回滚 SKILL 到最近一次备份版本；无备份时删除用户副本（回退到内置版本）",
)
async def rollback_skill(
    name: Annotated[str, Field(description="SKILL 名称")],
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    if not session:
        return fail("缺少会话上下文", error="Missing session")

    success, msg = updater.rollback_skill(name, user_id=session.user_id, group_id=session.group_id)
    return ok(msg) if success else fail(msg)


@tool_registry.register(
    description="手动热重载全部 SKILL。修改 SKILL 文件后调用，使变更立即对所有会话生效",
)
async def reload_skills(
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    try:
        names = updater.reload_skills()
        return ok(
            f"✅ 已热重载，当前共 {len(names)} 个 SKILL",
            metadata={"skill_names": names},
        )
    except Exception as e:
        logger.exception(f"reload_skills 执行失败: {e}")
        return fail(f"重载失败: {str(e)}", error=str(e))
