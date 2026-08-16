"""对话模式与历史管理命令（进入/退出模式、清除、回溯、token 查询）"""
from hoshino import Bot, Event

from ..infra.metrics import metrics
from ..persona import persona_manager
from ..service import sv
from ..session import session_manager

enter_chat_mode_cmd = sv.on_command('进入对话模式', aliases=('连续对话', '免井号对话', '聊天模式', '进入聊天'), only_group=False, block=True)


@enter_chat_mode_cmd.handle()
async def enter_chat_mode(bot: Bot, event: Event):
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    persona = persona_manager.get_persona(user_id, group_id)
    session = session_manager.get_or_create_session(user_id, group_id, persona)
    session.continuous_mode = True

    msg = "已进入连续对话模式！\n现在可以直接发送消息，无需 # 前缀即可与AI对话。\n"
    msg += f"当前人格：{persona[:30]}..." if persona else "当前人格：默认"
    msg += "\n\n提示：\n- 发送「退出对话模式」退出此模式\n- 发送「清除对话」清空当前对话历史\n- session过期后将自动退出此模式"

    await enter_chat_mode_cmd.finish(msg)


exit_chat_mode_cmd = sv.on_command('退出对话模式', aliases=('退出聊天', '结束对话模式'), only_group=False)


@exit_chat_mode_cmd.handle()
async def exit_chat_mode(bot: Bot, event: Event):
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    session = session_manager.get_session(user_id, group_id)
    was_in_mode = session.continuous_mode if session else False

    if not was_in_mode:
        await exit_chat_mode_cmd.finish("你当前不在连续对话模式中，发送「进入对话模式」来开启")
        return

    # 退出连续对话模式
    if session:
        session.continuous_mode = False
    await exit_chat_mode_cmd.finish("已退出连续对话模式。\n现在需要使用 # 前缀来触发AI对话。")


check_chat_mode_cmd = sv.on_command('查看对话模式', aliases=('对话模式状态',), only_group=False)


@check_chat_mode_cmd.handle()
async def check_chat_mode(bot: Bot, event: Event):
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    session = session_manager.get_session(user_id, group_id)
    in_mode = session.continuous_mode if session else False

    if in_mode:
        await check_chat_mode_cmd.finish("当前处于「连续对话模式」，直接发送消息即可与AI对话\n发送「退出对话模式」退出此模式")
    else:
        await check_chat_mode_cmd.finish("当前处于「普通模式」，需要使用 # 前缀触发AI对话\n发送「进入对话模式」开启免#触发")


clear_cmd = sv.on_command('清除对话', aliases=('清空对话', '重置对话', '清除上下文', '清空上下文'), only_group=False)


@clear_cmd.handle()
async def clear_session(bot: Bot, event: Event):
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    if session_manager.clear_session(user_id, group_id):
        await bot.send(event, "对话历史已清除")
    else:
        await bot.send(event, "没有找到对话历史")


rollback_cmd = sv.on_command('回溯', aliases=('回退', '删除对话', '返回'), only_group=False, block=True)


@rollback_cmd.handle()
async def rollback_session(bot: Bot, event: Event):
    args = str(event.message).strip().split()

    count = 1  # 默认回溯1条
    if len(args) >= 2:
        try:
            count = int(args[1].strip())
            if count < 1:
                await rollback_cmd.finish("回溯条数必须大于0，例如：回溯 3")
                return
            if count > 50:
                await rollback_cmd.finish("一次最多回溯50条对话")
                return
        except ValueError:
            await rollback_cmd.finish("请输入有效的数字，例如：回溯 3")
            return

    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    session = session_manager.get_session(user_id, group_id)
    if not session:
        await rollback_cmd.finish("没有可回溯的对话记录")
        return

    deleted, actual_rounds = session.rollback_messages(count)

    if deleted == 0:
        await rollback_cmd.finish("没有可回溯的对话记录")
    elif actual_rounds < count:
        await rollback_cmd.finish(f"已回溯 {actual_rounds} 条对话（共删除 {deleted} 条消息，历史记录不足）")
    else:
        await rollback_cmd.finish(f"已回溯 {actual_rounds} 条对话（共删除 {deleted} 条消息）")


query_token_cmd = sv.on_command('查询token', aliases=('token查询', 'token统计', 'token使用'), only_group=False)


@query_token_cmd.handle()
async def query_token(bot: Bot, event: Event):
    """查询当前 session 的 token 使用情况与全局统计"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    session = session_manager.get_session(user_id, group_id)

    if not session or session.total_tokens == 0:
        await query_token_cmd.finish("📊 当前会话暂无 token 使用记录\n\n提示：\n- 请先与 AI 进行对话\n- Token 统计在 session 过期后重置")
        return

    lines = [
        "📊 当前会话 Token 使用情况：\n",
        f"💬 输入 Token：{session.total_prompt_tokens:,}",
        f"🤖 输出 Token：{session.total_completion_tokens:,}",
        f"📈 总计 Token：{session.total_tokens:,}",
        "\n注：Token 统计在 session 过期后重置",
    ]

    # 全局统计（自进程启动以来）
    snap = metrics.snapshot()
    if snap["llm_calls"] > 0:
        lines.append(
            f"\n🌐 全局统计（进程启动以来）：\n"
            f"  LLM 调用：{snap['llm_calls']} 次，"
            f"平均延迟 {snap['llm_avg_latency_ms']:.0f}ms，"
            f"最长 {snap['llm_max_latency_ms']:.0f}ms\n"
            f"  全局 Token：输入 {snap['llm_prompt_tokens']:,} / 输出 {snap['llm_completion_tokens']:,}\n"
            f"  工具执行：{snap['tool_calls']} 次，超时 {snap['tool_timeouts']} 次"
        )
        if snap["llm_error_codes"]:
            errs = "、".join(f"{code}×{count}" for code, count in snap["llm_error_codes"].items())
            lines.append(f"  LLM 错误：{errs}")

    await query_token_cmd.finish("\n".join(lines))
