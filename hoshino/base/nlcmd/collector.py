"""
Matcher信息收集器
从nonebot内部matchers中提取所有命令信息
"""

from typing import List

from pydantic import BaseModel
from nonebot.rule import CommandRule, ShellCommandRule
import nonebot

try:
    from arclet.alconna import command_manager
    ALC = True
except ImportError:
    ALC = False


class CommandInfo(BaseModel):
    plugin: str
    cmds: List[str]
    shell_command_help: str


def collect_all_commands() -> List[CommandInfo]:
    """
    
    返回所有可用的命令信息列表
    """
    all_commands: List[CommandInfo] = []
    
    # 遍历所有可用的命令
    for plugin in nonebot.get_loaded_plugins():
        for m in plugin.matcher:
            rule = m.rule
            for checker in rule.checkers:
                ca = checker.call
                if isinstance(ca, CommandRule):
                    cmds = [".".join(cmd) for cmd in ca.cmds]
                    all_commands.append(CommandInfo(
                        plugin=plugin.name,
                        cmds=cmds,
                        shell_command_help="",
                    ))
                elif isinstance(ca, ShellCommandRule):
                    cmds = [" ".join(cmd) for cmd in ca.cmds]
                    help = ca.parser.format_help()
                    all_commands.append(CommandInfo(
                        plugin=plugin.name,
                        cmds=cmds,
                        shell_command_help=help,
                    ))
                else:
                    continue # TODO 后续支持AlconnaRule
    if ALC:
        for cmd in command_manager.get_commands():
            ns = cmd.namespace
            _cmds = [cmd.name]
            _cmds.extend(command_manager.get_shortcut(cmd).keys())
            all_commands.append(CommandInfo(
                plugin=ns,
                cmds=_cmds,
                shell_command_help="",
            ))

    return all_commands

                