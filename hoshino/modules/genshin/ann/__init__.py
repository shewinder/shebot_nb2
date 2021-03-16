import requests
import nonebot
from bs4 import BeautifulSoup
from ..util import *
import os
import math
from urllib.request import urlopen
from  PIL  import   Image,ImageFont,ImageDraw
import io
import base64
api_url = 'https://hk4e-api-static.mihoyo.com/common/hk4e_cn/announcement/api/'
api_params = '?game=hk4e&game_biz=hk4e_cn&lang=zh-cn&bundle_id=hk4e_cn&platform=pc&region=cn_gf01&level=55&uid=105293904'
ann_content_url = '%sgetAnnContent%s' % (api_url, api_params)
ann_list_url = '%sgetAnnList%s' % (api_url, api_params)

FILE_PATH = os.path.dirname(__file__)
class ann:
    ann_list_data = []
    ann_content_data = []
    FONTS_PATH = os.path.join(FILE_PATH,'fonts')
    FONTS = os.path.join(FONTS_PATH,'msyh1.otf')
    font = ImageFont.truetype(FONTS, 14)
    def __init__(self):
        pass

    async def get_ann_content(self):
        res = dict_to_object(json.loads(requests.get(ann_content_url, timeout=10).text))
        if res.retcode == 0:
            self.ann_content_data = res.data.list
        return self.ann_content_data

    async def get_ann_list(self):
        res = dict_to_object(json.loads(requests.get(ann_list_url, timeout=10).text))
        if res.retcode == 0:
            self.ann_list_data = res.data.list
        return self.ann_list_data

    async def get_ann_ids(self):
        await self.get_ann_list()
        if not self.ann_list_data:
            return []
        ids = []
        for label in self.ann_list_data:
            ids += [x['ann_id'] for x in label['list']]
        return ids

    async def ann_list_msg(self):
        await self.get_ann_list()
        if not self.ann_list_data:
            return '获取游戏公告失败,请检查接口是否正常'
        msg = ''
        for data in self.ann_list_data:
            msg += '%s:\n' % data['type_label']
            data_list = [x for x in data['list'] if not x['ann_id'] in config.setting.ann_block]
            msg += '\n'.join(map(lambda x: '%s %s' % (x['ann_id'], x['title']), data_list))
            msg += '\n'
        msg += '\n请输入前面的数字ID进行查看,例: %s0000' % config.comm.ann_detail
        return msg
    
    def get_duanluo(self, text):
        txt = Image.new('RGBA', (600, 800), (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt)
        # 所有文字的段落
        duanluo = ""
        max_width = 600
        # 宽度总和
        sum_width = 0
        # 几行
        line_count = 1
        # 行高
        line_height = 0
        for char in text:
            width, height = draw.textsize(char, ann.font)
            sum_width += width
            if sum_width > max_width: # 超过预设宽度就修改段落 以及当前行数
                line_count += 1
                sum_width = 0
                duanluo += '\n'
            duanluo += char
            line_height = max(height, line_height)
        if not duanluo.endswith('\n'):
            duanluo += '\n'
        return duanluo, line_height, line_count
    
    def split_text(self, content):
        # 按规定宽度分组
        max_line_height, total_lines = 0, 0
        allText = []
        for text in content.split('\n'):
            duanluo, line_height, line_count = self.get_duanluo(text)
            max_line_height = max(line_height, max_line_height)
            total_lines += line_count
            allText.append((duanluo, line_count))
        line_height = max_line_height
        total_height = total_lines * line_height
        drow_height = total_lines * line_height
        return allText, total_height, line_height, drow_height
    
    async def ann_detail_msg(self, ann_id):
        await self.get_ann_content()
        if not self.ann_content_data:
            return '获取游戏公告失败,请检查接口是否正常'
        content = filter_list(self.ann_content_data, lambda x: x['ann_id'] == ann_id)
        if not content:
            return '没有找到对应的公告ID'
        soup = BeautifulSoup(content[0]['content'], 'lxml')
        banner = content[0]['banner']
        ann_img = banner if banner else ''
        for a in soup.find_all('a'):
            href = a.get('href')
            a.string += ' (%s)' % re.search(r'https?.+', re.sub(r'[;()\']', '', href)).group()

        for img in soup.find_all('img'):
            img.string = img.get('src')

        msg_list = [BeautifulSoup(x.get_text('\n').replace('<<', ''), 'lxml').get_text() for x in soup.find_all('p')]
        msg_list.append(ann_img)
        drow_height = 0
        #print('文字长度：' + str(drow_height))
        for msg in msg_list:
            #print('段落：' + str(msg))
            if 'jpg' in msg or 'png' in msg:
                image_bytes = urlopen(msg).read()
                # internal data file  
                data_stream = io.BytesIO(image_bytes)
                img = Image.open(data_stream)
                size = img.size
                #print('图片：长'+str(size[0])+'，宽'+str(size[1]))
                sf_height = math.ceil(size[1]/(size[0]/550))
                drow_height += sf_height+20
            else:
                x_drow_duanluo, x_drow_note_height, x_drow_line_height, x_drow_height = self.split_text(msg)
                drow_height += x_drow_height
        #print('画图长度：' + str(drow_height))
        
        im = Image.new("RGB", (600, drow_height), (255, 255, 255))
        draw = ImageDraw.Draw(im)
        # 左上角开始
        x, y = 0, 0
        for msg in msg_list:
            if 'jpg' in msg or 'png' in msg:
                image_bytes = urlopen(msg).read()
                # internal data file  
                data_stream = io.BytesIO(image_bytes)
                img = Image.open(data_stream)
                size = img.size
                sf_height = math.ceil(size[1]/(size[0]/550))
                box = (25, y+10)
                img = img.resize((550, sf_height))
                im.paste(img, box)
                y += sf_height+10
                #print('原图片：长'+str(size[0])+'，宽'+str(size[1]))
                #print('后图片：长575，宽'+str(sf_height))
            else:
                drow_duanluo, drow_note_height, drow_line_height, drow_height = self.split_text(msg)
                for duanluo, line_count in drow_duanluo:
                    draw.text((x, y), duanluo, fill=(0, 0, 0), font=ann.font)
                    y += drow_line_height * line_count
            
        bio  = io.BytesIO()
        im.save(bio, format='PNG')
        base64_str = 'base64://' + base64.b64encode(bio.getvalue()).decode()
        mes  = f"[CQ:image,file={base64_str}]"
        return mes


ann_db = init_db(config.cache_dir, 'ann.sqlite')


def sub_ann(group):
    sub_list = ann_db.get('sub', [])
    sub_list.append(group)
    ann_db['sub'] = list(set(sub_list))
    return '成功订阅原神公告'


def unsub_ann(group):
    sub_list = ann_db.get('sub', [])
    sub_list.remove(group)
    ann_db['sub'] = sub_list
    return '成功取消订阅原神公告'


async def check_ann_state():
    print('定时任务: 原神公告查询..')
    ids = ann_db.get('ids', [])
    sub_list = ann_db.get('sub', [])
    if not sub_list:
        print('没有群订阅, 取消获取数据')
        return
    if not ids:
        ids = await ann().get_ann_ids()
        if not ids:
            print('获取原神公告ID列表错误,请检查接口')
        ann_db['ids'] = ids
        print('初始成功, 将在下个轮询中更新.')
        return
    new_ids = await ann().get_ann_ids()

    new_ann = [i for i in new_ids if i not in ids]
    if not new_ann:
        print('没有最新公告')
        return

    detail_list = []
    for ann_id in new_ann:
        detail_list.append(await ann().ann_detail_msg(ann_id))
    
    tas_list = []
    for msg in detail_list: 
        data = {
            "type": "node",
            "data": {
                "name": "ご主人様",
                "uin": "1587640710",
                "content":msg
                    }
                }
        tas_list.append(data)
    
    for group in sub_list:
        await bot.send_group_forward_msg(group_id=group,messages=tas_list)
            #await bot.send_group_msg(group_id=group, message=msg)

    print('推送完毕, 更新数据库')
    ann_db['ids'] = new_ids


if config.setting.ann_cron_enable:
    @nonebot.scheduler.scheduled_job(
        'cron',
        minute=f"*/{config.setting.ann_cron_time}"
    )
    async def _():
        await check_ann_state()
