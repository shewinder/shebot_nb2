"""
Author: SheBot
Date: 2026-04-02
Description: 通用脚本执行工具
"""
import asyncio
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from ..registry import tool_registry, ok, fail

if TYPE_CHECKING:
    from hoshino import Bot, Event
    from ...session import Session


def _resolve_script_path(script_path: str, working_dir: Optional[Path] = None) -> Path:
    """解析脚本路径为绝对路径"""
    path = Path(script_path)
    if not path.is_absolute() and working_dir:
        path = working_dir / path
    return path.resolve()


def _is_path_safe(target: Path, allowed_base: Path) -> bool:
    """检查目标路径是否在允许的基目录内（防止目录遍历）"""
    try:
        target.relative_to(allowed_base)
        return True
    except ValueError:
        return False


@tool_registry.register(
    name="execute_script",
    description="""执行指定 SKILL 目录下的脚本文件（Python、Shell 等）

用于执行已激活 SKILL 目录下的脚本，完成特定任务。

## 参数说明
- skill_name: SKILL 名称（必须从当前激活的 SKILL 中选择）
- script_path: 脚本文件路径（相对于 SKILL 目录，如 'scripts/calc.py'）
- args: 传递给脚本的参数列表（字符串数组）
- timeout: 超时时间（秒，默认30，最大300）

## 使用示例
```python
# 执行 math SKILL 的 calculate.py 脚本
execute_script(
    skill_name="math",
    script_path="scripts/calculate.py",
    args=["15 * 23"]
)
```

## 重要提示
- skill_name 必须是当前已激活的 SKILL 之一
- 只能执行该 SKILL 目录下的脚本（安全限制）
- 如果需要执行多个 SKILL 的脚本，请分别调用

## 返回值
- stdout: 脚本的标准输出
- stderr: 脚本的标准错误
- return_code: 脚本退出码
""",
    parameters={
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "SKILL 名称（必须从当前激活的 SKILL 中选择）"
            },
            "script_path": {
                "type": "string",
                "description": "脚本文件路径（相对于 SKILL 目录，如 'scripts/calc.py'）"
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "传递给脚本的参数列表",
                "default": []
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒，默认30，最大300）",
                "default": 30,
                "minimum": 1,
                "maximum": 300
            }
        },
        "required": ["skill_name", "script_path"]
    }
)
async def execute_script(
    skill_name: str,
    script_path: str,
    args: Optional[List[str]] = None,
    timeout: int = 30,
    session: Optional["Session"] = None,
    bot: Optional["Bot"] = None,
    event: Optional["Event"] = None,
) -> Dict[str, Any]:
    """执行指定脚本
    
    Args:
        skill_name: SKILL 名称（必须从当前激活的 SKILL 中选择）
        script_path: 脚本路径（相对于 SKILL 目录）
        args: 脚本参数
        timeout: 超时时间
        session: 当前会话
        bot: Bot 实例
        event: Event 实例
        
    Returns:
        执行结果
    """
    if args is None:
        args = []
    
    # 限制超时时间
    timeout = min(max(timeout, 1), 300)
    
    # 验证 skill_name 是否已激活
    if not session or skill_name not in session.active_skills:
        return fail(f"SKILL '{skill_name}' 未激活，请先激活该 SKILL")
    
    # 获取 SKILL 目录
    from ...skills import skill_manager
    skill = skill_manager.get_skill(skill_name)
    if not skill:
        return fail(f"SKILL '{skill_name}' 不存在")
    
    # 权限检查
    script_path_obj = Path(script_path)
    can_execute, reason = await _check_execute_permission(
        script_name=script_path_obj.name,
        skill=skill,
        session=session,
        bot=bot,
        event=event
    )
    if not can_execute:
        return fail(f"权限检查失败: {reason}")
    
    # 解析为绝对路径（基于 SKILL 目录）
    script_abs = _resolve_script_path(script_path, skill.directory)
    
    # 检查文件是否存在
    if not script_abs.exists():
        return fail(f"脚本不存在: {script_path}")
    
    if not script_abs.is_file():
        return fail(f"路径不是文件: {script_path}")
    
    # 确定解释器
    interpreter = _get_interpreter(script_abs)
    if not interpreter:
        return fail(f"不支持的脚本类型: {script_abs.suffix}")
    
    # 构建命令
    cmd = [interpreter, str(script_abs)] + args
    
    # 执行脚本
    try:
        logger.info(f"执行脚本: {' '.join(cmd)}, timeout={timeout}")
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(script_abs.parent)
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return fail(f"脚本执行超时（{timeout}秒）")
        
        stdout_str = stdout.decode('utf-8', errors='replace').strip()
        stderr_str = stderr.decode('utf-8', errors='replace').strip()
        
        # 限制输出长度（防止 Token 爆炸）
        max_output = 10000
        if len(stdout_str) > max_output:
            stdout_str = stdout_str[:max_output] + "\n... (输出已截断)"
        if len(stderr_str) > max_output:
            stderr_str = stderr_str[:max_output] + "\n... (错误输出已截断)"
        
        result = {
            "stdout": stdout_str,
            "stderr": stderr_str,
            "return_code": proc.returncode
        }
        
        if proc.returncode == 0:
            return ok("脚本执行成功", metadata=result)
        else:
            return fail(
                f"脚本执行失败（退出码: {proc.returncode}）",
                error=stderr_str or "未知错误",
                metadata=result
            )
            
    except Exception as e:
        logger.exception(f"执行脚本失败: {e}")
        return fail(f"执行脚本失败: {str(e)}")


def _get_interpreter(script_path: Path) -> Optional[str]:
    """根据文件后缀获取解释器"""
    suffix = script_path.suffix.lower()
    interpreters = {
        '.py': 'python',
        '.sh': 'bash',
        '.bash': 'bash',
    }
    return interpreters.get(suffix)


async def _check_execute_permission(
    script_name: str,
    skill: Any,
    session: Optional["Session"],
    bot: Optional["Bot"],
    event: Optional["Event"]
) -> tuple:
    """检查执行权限
    
    Args:
        script_name: 脚本文件名
        skill: SKILL 对象
        session: 当前会话
        bot: Bot 实例
        event: Event 实例
        
    Returns:
        (bool, str) - (是否允许, 原因)
    """
    from hoshino.permission import SUPERUSER
    
    # 检查 skill 是否有 execute_script 权限
    if not skill.metadata.has_tool_permission("execute_script"):
        return False, f"SKILL '{skill.metadata.name}' 无权使用 execute_script 工具"
    
    # 检查脚本路径是否在 skill 目录内
    script_path = Path(script_name)
    if script_path.is_absolute():
        return False, "脚本路径必须是相对路径"
    
    script_abs = (skill.directory / script_path).resolve()
    if not _is_path_safe(script_abs, skill.directory):
        return False, f"脚本路径超出 SKILL '{skill.metadata.name}' 目录范围"
    
    return True, ""
