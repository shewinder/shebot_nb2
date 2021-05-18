import asyncio
import os
import json

from peewee import *
from PIL import Image, ImageFile
from random import randint

from .getsetu import get_final_setu
from queue import Queue

from hoshino import MessageSegment

from .config import plugin_config as pc

ImageFile.LOAD_TRUNCATED_IMAGES = True

class SetuWarehouse:
    def __init__(self,store_path,r18=0):
        self.warehouse = Queue(5)
        self.r18 = r18
        if os.path.exists(store_path):
            self.store_path = store_path
        else:
            try:
                os.mkdir(store_path)
                self.store_path = store_path
            except Exception as ex:
                print(ex)

    def count(self):
            return self.warehouse.qsize()

    def keep_supply(self):
        while True:
            print('正在补充色图')
            setus = get_final_setu(num=8, save_dir=self.store_path, r18=self.r18)
            for setu in setus:
                self.warehouse.put(setu)
                print(f'补充一张色图，库存{self.count()}张\n')

    def fetch(self,num=1): 
        send_pics=[]
        for i in range(0,num):
            try:
                send_pics.append(self.warehouse.get())
            except:
                print('色图不足，等待补充,本次取出取消')
            print(f'库存{self.count()}张\n')

        return send_pics

path = os.path.join(os.path.dirname(__file__),'setu_config.json')
def save_config(config:dict):
    try:
        with open(path,'w',encoding='utf8') as f:
            json.dump(config,f,ensure_ascii=False,indent=2)
        return True
    except Exception as ex:
        print(ex)
        return False

def load_config():
    try:
        with open(path,'r',encoding='utf8') as f:
            config = json.load(f)
            return config
    except:
        return {}

from hoshino.sres import Res as R
async def send_setus(bot,ctx,folder,setus,with_url=False,is_to_delete=False):
    reply = MessageSegment.text('')
    for setu in setus:
        pic = R.image(f'{folder}/{setu.url.split("/")[-1]}')
        reply += MessageSegment.text(f'{setu.title}\n画师：{setu.author}\npid:{setu.pid}')
        reply += pic
    ret = await bot.send(ctx, reply ,at_sender=False)
    if with_url:
        urls = ''
        for setu in setus:
            urls = urls+setu.url+'\n\n'
        await bot.send(ctx,urls.strip(),at_sender=False)
    if is_to_delete:
        msg_id = ret['message_id']
        self_id = ctx.self_id
        await asyncio.sleep(pc.config.delete_after)
        await bot.delete_msg(self_id=self_id, message_id=msg_id)


