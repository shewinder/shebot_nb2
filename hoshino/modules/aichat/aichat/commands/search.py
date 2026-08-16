"""搜索 Provider 切换命令（超管）"""
from hoshino import Bot, Event
from hoshino.permission import SUPERUSER

from ..config import Config
from ..service import sv
from ..tools.builtin.search_providers import get_provider, list_providers, switch_provider

conf = Config.get_instance('aichat')

switch_search_cmd = sv.on_command('切换搜索', aliases=('切换搜索后端', '切换搜索引擎'), permission=SUPERUSER, only_group=False)


@switch_search_cmd.handle()
async def switch_search_handle(bot: Bot, event: Event):
    args = str(event.message).strip().split(maxsplit=1)

    if len(args) < 2:
        current = conf.search_provider
        lines = ["可用搜索后端："]
        for name in list_providers():
            p = get_provider(name)
            mark = " (当前)" if name == current else ""
            lines.append(f"  {name}{mark} — {p['label']}")
        lines.append(f"\n当前: {get_provider(current)['label']}")
        lines.append("使用「切换搜索 <name>」切换")
        await switch_search_cmd.finish("\n".join(lines))
        return

    target = args[1].strip().lower()
    if target not in list_providers():
        await switch_search_cmd.finish(f"未知搜索后端「{target}」，可用: {', '.join(list_providers())}")
        return

    if target == conf.search_provider:
        await switch_search_cmd.finish(f"搜索后端已经是 {get_provider(target)['label']}，无需切换")
        return

    success = await switch_provider(target)
    if success:
        await switch_search_cmd.finish(f"已切换搜索后端为: {get_provider(target)['label']}")
    else:
        await switch_search_cmd.finish("切换失败，请查看日志")
