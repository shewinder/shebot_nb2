from . import util
from .ann import *
from .material import *
from hoshino import Service  # 如果使用hoshino的分群管理取消注释这行
from hoshino.typing import MessageSegment, NoticeSession, CQEvent
import os
from  PIL  import   Image,ImageFont,ImageDraw
from io import BytesIO
import base64
#
sv = Service('egenshin')  # 如果使用hoshino的分群管理取消注释这行
# 初始化配置文件
config = util.get_config()

# 初始化nonebot
_bot = get_bot()
FILE_PATH = os.path.dirname(__file__)

class ImgText:
    FONTS_PATH = os.path.join(FILE_PATH,'fonts')
    FONTS = os.path.join(FONTS_PATH,'msyh1.otf')
    font = ImageFont.truetype(FONTS, 14)
    def __init__(self, text):
        # 预设宽度 可以修改成你需要的图片宽度
        self.width = 600
        # 文本
        self.text = text
        # 段落 , 行数, 行高
        self.duanluo, self.note_height, self.line_height, self.drow_height = self.split_text()
    def get_duanluo(self, text):
        txt = Image.new('RGBA', (600, 800), (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt)
        # 所有文字的段落
        duanluo = ""
        # 宽度总和
        sum_width = 0
        # 几行
        line_count = 1
        # 行高
        line_height = 0
        for char in text:
            width, height = draw.textsize(char, ImgText.font)
            sum_width += width
            if sum_width > self.width: # 超过预设宽度就修改段落 以及当前行数
                line_count += 1
                sum_width = 0
                duanluo += '\n'
            duanluo += char
            line_height = max(height, line_height)
        if not duanluo.endswith('\n'):
            duanluo += '\n'
        return duanluo, line_height, line_count
    def split_text(self):
        # 按规定宽度分组
        max_line_height, total_lines = 0, 0
        allText = []
        for text in self.text.split('\n'):
            duanluo, line_height, line_count = self.get_duanluo(text)
            max_line_height = max(line_height, max_line_height)
            total_lines += line_count
            allText.append((duanluo, line_count))
        line_height = max_line_height
        total_height = total_lines * line_height
        drow_height = total_lines * line_height
        return allText, total_height, line_height, drow_height
    def draw_text(self):
        """
        绘图以及文字
        :return:
        """
        im = Image.new("RGB", (600, self.drow_height), (255, 255, 255))
        draw = ImageDraw.Draw(im)
        # 左上角开始
        x, y = 0, 0
        for duanluo, line_count in self.duanluo:
            draw.text((x, y), duanluo, fill=(0, 0, 0), font=ImgText.font)
            y += self.line_height * line_count
        bio  = BytesIO()
        im.save(bio, format='PNG')
        base64_str = 'base64://' + base64.b64encode(bio.getvalue()).decode()
        mes  = f"[CQ:image,file={base64_str}]"
        return mes


@sv.on_message('group')  # 如果使用hoshino的分群管理取消注释这行 并注释下一行的 @_bot.on_message("group")
# @_bot.on_message  # nonebot使用这
async def main(*params):
    bot, ctx = (_bot, params[0]) if len(params) == 1 else params
    msg = str(ctx['message']).strip()
    is_super_admin = ctx.user_id in _bot.config.SUPERUSERS
    is_admin = util.is_group_admin(ctx) or is_super_admin

    # ---------------- 原神公告 ----------------

    # 原神公告
    keyword = util.get_msg_keyword(config.comm.ann_list, msg, True)
    if isinstance(keyword, str) and keyword == '':        
        tas_list = []
        tat = await ann().ann_list_msg()
        msg = str(tat)
        n = ImgText(msg)
        mes = n.draw_text()
        data = {
            "type": "node",
            "data": {
                "name": "ご主人様",
                "uin": "1587640710",
                "content":mes
                    }
                }
        tas_list.append(data)
        await _bot.send_group_forward_msg(group_id=ctx['group_id'],messages=tas_list)
    # 原神公告详情
    keyword = util.get_msg_keyword(config.comm.ann_detail, msg, True)
    if keyword and keyword.isdigit():
        tas_list = []
        tat = await ann().ann_detail_msg(int(keyword))
        data = {
            "type": "node",
            "data": {
                "name": "ご主人様",
                "uin": "1587640710",
                "content":tat
                    }
                }
        tas_list.append(data)
        await _bot.send_group_forward_msg(group_id=ctx['group_id'],messages=tas_list)

    # 订阅原神公告
    keyword = util.get_msg_keyword(config.comm.sub_ann, msg, True)
    if isinstance(keyword, str) and config.setting.ann_cron_enable:
        if not config.setting.ann_enable_only_admin:
            await _bot.send(ctx, sub_ann(ctx.group_id))
        elif is_admin:
            await _bot.send(ctx, sub_ann(ctx.group_id))
        else:
            await _bot.send(ctx, '你没有权限开启原神公告推送')

    # 取消订阅原神公告
    keyword = util.get_msg_keyword(config.comm.unsub_ann, msg, True)
    if isinstance(keyword, str):
        if not config.setting.ann_enable_only_admin:
            await _bot.send(ctx, unsub_ann(ctx.group_id))
        elif is_admin:
            await _bot.send(ctx, unsub_ann(ctx.group_id))
        else:
            await _bot.send(ctx, '你没有权限取消原神公告推送')

    # ---------------- 素材定时提醒 ----------------
    mat = material(ctx.group_id, ctx.user_id)
    # 收集素材
    keyword = util.get_msg_keyword(config.comm.material, msg, True)
    if keyword:
        await _bot.send(ctx, await mat.mark(keyword))
    if keyword == '':
        await _bot.send(ctx, await mat.status())

    # 查看材料
    keyword = util.get_msg_keyword(config.comm.show_material, msg, True)
    if keyword:
        await _bot.send(ctx, await mat.show(keyword))
