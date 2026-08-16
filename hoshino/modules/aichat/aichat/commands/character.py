"""角色卡导入命令（PNG 角色卡 → 个人/全局预设人格）"""
from typing import Tuple
from loguru import logger

import httpx

from hoshino import Bot, Event
from hoshino.permission import SUPERUSER
from hoshino.util import get_event_imageurl
from hoshino.util.message_util import extract_images_from_reply

from ..character_import import parse_character_png
from ..persona import persona_manager
from ..service import sv


async def _process_character_images(event: Event, bot: Bot, save_as_global: bool = False) -> Tuple[int, int, int, list, list]:
    image_urls = get_event_imageurl(event)

    try:
        image_urls.extend(await extract_images_from_reply(event, bot))
    except Exception as e:
        logger.debug(f"提取引用消息图片失败: {e}")

    if not image_urls:
        return 0, 0, 0, [], ["未找到图片"]

    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    success_count = 0
    fail_count = 0
    skip_count = 0
    imported_names = []
    fail_reasons = []

    for i, image_url in enumerate(image_urls, 1):
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
                resp = await client.get(image_url)
            if resp.status_code != 200:
                fail_count += 1
                fail_reasons.append(f"第{i}张：下载失败 HTTP {resp.status_code}")
                continue

            image_data = resp.content
            if not image_data:
                fail_count += 1
                fail_reasons.append(f"第{i}张：图片数据为空")
                continue

            success, char_card, msg = parse_character_png(image_data)

            if not success or not char_card:
                skip_count += 1
                logger.debug(f"第{i}张图片不是有效的角色卡：{msg}")
                continue

            persona_name = char_card.name
            persona_text = char_card.to_persona_text()

            if save_as_global:
                success_save, msg_save = persona_manager.add_global_preset(persona_name, persona_text)
            else:
                success_save, msg_save = persona_manager.save_persona(user_id, group_id, persona_name, persona_text)

            if success_save:
                success_count += 1
                imported_names.append(persona_name)
            else:
                fail_count += 1
                fail_reasons.append(f"{persona_name}：{msg_save}")

        except Exception as e:
            logger.exception(f"处理第{i}张图片失败: {e}")
            fail_count += 1
            fail_reasons.append(f"第{i}张：处理异常 {e}")

    return success_count, fail_count, skip_count, imported_names, fail_reasons


def _build_import_result_message(
    success_count: int,
    fail_count: int,
    skip_count: int,
    imported_names: list,
    fail_reasons: list,
    total_images: int,
    is_global: bool = False
) -> str:
    if success_count == 0 and fail_count == 0 and skip_count > 0:
        return f"未找到有效的角色卡图片。\n共检测 {total_images} 张图片，都不是有效的 TavernAI / SillyTavern PNG 角色卡。"

    if success_count == 0:
        msg_lines = [f"❌ 导入失败，共 {fail_count} 个错误："]
        msg_lines.extend(fail_reasons[:5])
        if len(fail_reasons) > 5:
            msg_lines.append(f"...还有 {len(fail_reasons) - 5} 个错误")
        return "\n".join(msg_lines)

    # 有成功导入的
    scope = "全局预设" if is_global else "个人"
    msg_lines = [f"✅ 成功导入 {success_count} 个{scope}角色卡"]

    if len(imported_names) <= 5:
        msg_lines.append("导入的角色：" + ", ".join(f"「{n}」" for n in imported_names))
    else:
        msg_lines.append(f"导入的角色：{', '.join(f'「{n}」' for n in imported_names[:5])} 等共 {len(imported_names)} 个")

    if fail_count > 0:
        msg_lines.append(f"\n⚠️ {fail_count} 个导入失败")

    if skip_count > 0:
        msg_lines.append(f"\nℹ️ {skip_count} 张图片不是角色卡，已跳过")

    if is_global:
        msg_lines.append(f"\n使用「预设人格列表」查看全局预设")
        msg_lines.append(f"使用「使用人格 <角色名>」来应用角色")
    else:
        msg_lines.append(f"\n使用「列出人格」查看已保存的角色")
        msg_lines.append(f"使用「使用人格 <角色名>」来应用角色")

    return "\n".join(msg_lines)


import_persona_cmd = sv.on_command('导入角色卡', aliases=('导入人格', '加载角色卡'), only_group=False)


@import_persona_cmd.handle()
async def import_persona(bot: Bot, event: Event):
    success_count, fail_count, skip_count, imported_names, fail_reasons = await _process_character_images(
        event, bot, save_as_global=False
    )

    if fail_reasons and fail_reasons[0] == "未找到图片":
        await import_persona_cmd.finish("请发送 PNG 格式的角色卡图片\n\n支持方式：\n1. 直接发送「导入角色卡」并附带 PNG 图片\n2. 回复包含 PNG 图片的消息并发送「导入角色卡」\n3. 引用消息中的 PNG 图片并发送「导入角色卡」\n\n支持格式：TavernAI / SillyTavern PNG 角色卡")
        return

    total_images = success_count + fail_count + skip_count

    msg = _build_import_result_message(
        success_count, fail_count, skip_count, imported_names, fail_reasons, total_images, is_global=False
    )
    await import_persona_cmd.finish(msg)


import_global_persona_cmd = sv.on_command('导入全局角色卡', aliases=('导入全局人格', '加载全局角色卡'), permission=SUPERUSER, only_group=False)


@import_global_persona_cmd.handle()
async def import_global_persona(bot: Bot, event: Event):
    success_count, fail_count, skip_count, imported_names, fail_reasons = await _process_character_images(
        event, bot, save_as_global=True
    )

    if fail_reasons and fail_reasons[0] == "未找到图片":
        await import_global_persona_cmd.finish("请发送 PNG 格式的角色卡图片\n\n支持方式：\n1. 直接发送「导入全局角色卡」并附带 PNG 图片\n2. 回复包含 PNG 图片的消息并发送「导入全局角色卡」\n3. 引用消息中的 PNG 图片并发送「导入全局角色卡」\n\n支持格式：TavernAI / SillyTavern PNG 角色卡")
        return

    total_images = success_count + fail_count + skip_count

    msg = _build_import_result_message(
        success_count, fail_count, skip_count, imported_names, fail_reasons, total_images, is_global=True
    )
    await import_global_persona_cmd.finish(msg)
