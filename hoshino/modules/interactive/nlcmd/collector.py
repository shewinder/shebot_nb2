"""
Matcher信息收集器
从nonebot内部matchers中提取所有命令信息
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from nonebot.internal.matcher import matchers
from nonebot.matcher import Matcher

def _safe_repr(obj: Any, max_len: int = 240) -> str:
    try:
        s = repr(obj)
    except Exception:
        s = f"<unreprable:{type(obj).__name__}>"
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def _call_kind(call: Any) -> str:
    if call is None:
        return "None"
    try:
        return call.__class__.__name__
    except Exception:
        return type(call).__name__


def _iter_checkers(rule_or_perm: Any) -> Iterable[Any]:
    checkers = getattr(rule_or_perm, "checkers", None)
    if checkers is None:
        return []
    # Rule/Permission.checkers 一般是 tuple[Dependent, ...]
    try:
        return list(checkers)
    except Exception:
        return []


def _extract_cmds(call: Any) -> List[str]:
    """
    从 Command/ShellCommand call 中抽取 cmds: tuple[tuple[str,...], ...] → List[str]
    """
    cmds = getattr(call, "cmds", None)
    if not cmds:
        return []
    out: List[str] = []
    # cmds 形态： (('开启解析',), ('别名',), ...)
    if isinstance(cmds, tuple):
        for item in cmds:
            if isinstance(item, tuple):
                out.extend([c for c in item if isinstance(c, str) and c])
            elif isinstance(item, str):
                out.append(item)
    elif isinstance(cmds, str):
        out.append(cmds)
    # 去重但保持顺序
    seen = set()
    uniq: List[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _is_to_me_call(call: Any) -> bool:
    # 不强依赖具体类导入，仅用类名判定
    try:
        name = call.__class__.__name__
    except Exception:
        name = type(call).__name__
    return name == "ToMe"


def _dep_to_schema(dep: Any) -> Dict[str, Any]:
    call = getattr(dep, "call", None)
    data: Dict[str, Any] = {}
    cmds = _extract_cmds(call)
    if cmds:
        data["cmds"] = cmds
    return {
        "kind": _call_kind(call),
        "repr": _safe_repr(call),
        "data": data,
    }


def _handler_to_schema(handler_dep: Any) -> Dict[str, Any]:
    call = getattr(handler_dep, "call", None)
    module = getattr(call, "__module__", None)
    qualname = getattr(call, "__qualname__", None)
    return {
        "module": module if isinstance(module, str) else None,
        "qualname": qualname if isinstance(qualname, str) else None,
        "repr": _safe_repr(call),
    }


def extract_matcher_info(matcher: Matcher, priority: int) -> Dict[str, Any]:
    """
    仅基于未封装 matcher 信息，输出归一化 schema（不导出 __dict__）。
    """
    src = getattr(matcher, "_source", None)
    source = {
        "plugin_id": getattr(src, "plugin_id", None),
        "module_name": getattr(src, "module_name", None),
        "lineno": getattr(src, "lineno", None),
    }

    rule = getattr(matcher, "rule", None)
    perm = getattr(matcher, "permission", None)

    rule_deps_raw = list(_iter_checkers(rule))
    perm_deps_raw = list(_iter_checkers(perm))

    rule_deps = [_dep_to_schema(d) for d in rule_deps_raw]
    permission_deps = [_dep_to_schema(d) for d in perm_deps_raw]

    # triggers 派生
    to_me = False
    commands: List[str] = []
    shell_commands: List[str] = []
    for d in rule_deps_raw:
        call = getattr(d, "call", None)
        if _is_to_me_call(call):
            to_me = True
        cmds = _extract_cmds(call)
        if cmds:
            # Command vs ShellCommand 用 kind 区分
            kind = _call_kind(call)
            if kind == "ShellCommand":
                shell_commands.extend(cmds)
            else:
                commands.extend(cmds)

    # 去重并保持顺序
    def _uniq(seq: Sequence[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for x in seq:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    triggers = {
        "to_me": to_me,
        "commands": _uniq(commands),
        "shell_commands": _uniq(shell_commands),
    }

    handlers_raw = getattr(matcher, "handlers", None) or []
    handlers = []
    try:
        for h in list(handlers_raw):
            handlers.append(_handler_to_schema(h))
    except Exception:
        handlers = []

    default_state = getattr(matcher, "_default_state", None) or {}
    default_state_keys: List[str] = []
    if isinstance(default_state, dict):
        default_state_keys = [k for k in default_state.keys() if isinstance(k, str)]

    expire_time = getattr(matcher, "expire_time", None)

    return {
        "priority": int(priority),
        "type": getattr(matcher, "type", None),
        "block": bool(getattr(matcher, "block", False)),
        "temp": bool(getattr(matcher, "temp", False)),
        "expire_time": str(expire_time) if expire_time is not None else None,
        "source": {
            "plugin_id": source["plugin_id"] if isinstance(source["plugin_id"], str) else None,
            "module_name": source["module_name"] if isinstance(source["module_name"], str) else None,
            "lineno": int(source["lineno"]) if isinstance(source["lineno"], int) else None,
        },
        "rule_deps": rule_deps,
        "permission_deps": permission_deps,
        "handlers": handlers,
        "default_state_keys": default_state_keys,
        "triggers": triggers,
    }


def collect_all_matchers() -> List[Dict[str, Any]]:
    """
    收集所有matcher信息
    
    返回所有可用的命令信息列表
    """
    all_matchers: List[Dict[str, Any]] = []
    
    # 遍历所有优先级的matchers
    for priority, matcher_set in matchers.items():
        for matcher in matcher_set:
            all_matchers.append(extract_matcher_info(matcher, int(priority)))
    
    return all_matchers


def format_matchers_for_llm(matcher_infos: List[Dict[str, Any]], max_items: int = 120) -> str:
    """
    将 matcher 列表格式化为LLM可理解的文本（用于 debug 或 prompt 拼装）。
    """
    lines: List[str] = []
    for i, m in enumerate(matcher_infos[:max_items]):
        src = m.get("source", {}) or {}
        trig = m.get("triggers", {}) or {}
        cmds = ", ".join(trig.get("commands", []) or [])
        scmds = ", ".join(trig.get("shell_commands", []) or [])
        to_me = "to_me" if trig.get("to_me") else ""
        line = (
            f"{i+1}. type={m.get('type')}, priority={m.get('priority')}, block={m.get('block')}, "
            f"plugin={src.get('plugin_id')}, module={src.get('module_name')}, line={src.get('lineno')}, "
            f"commands=[{cmds}], shell_commands=[{scmds}] {to_me}".strip()
        )
        lines.append(line)
    return "\n".join(lines)
