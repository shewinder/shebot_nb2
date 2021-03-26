import re
import requests

from hoshino import Service, Bot, Event
from hoshino.typing import T_State
from hoshino.util.sutil import get_md5
from .config import plugin_config, Config

conf: Config = plugin_config.config

sv = Service('翻译')

languages = {
    "中文" : "zh",
    "英语" : "en",
    "粤语" : "yue",
    "文言文" : "wyw",
    "日语" : "jp", 
    "法语" : "fra",
    "俄语" : "ru",
    "德语" : "de",
}

sv = Service('translate')
trans = sv.on_command('translate', aliases = {'翻译'}, only_group=False)

@trans.handle()
async def translate(bot: Bot, event: Event, state: T_State):
    query = str(event.get_message()).strip()
    match = re.match('([\s\S]{1,500})为(.{0,10})?',query) or re.match('([\s\S]{1,500})',query)
    if match:
        query = match.group(1)
        try:
            to = languages.get(match.group(2)) if languages.get(match.group(2)) else 'zh'
        except:
            to = 'zh'
        appid = conf.appid
        key = conf.key
        salt = 'asufghsfhs' #随便
        sign = get_md5(appid+query+salt+key)
        url = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
        params = {
            'q' : query,
            'from' : 'auto',
            'to' : to,
            'appid' : appid,
            'salt' : salt,
            'sign' : sign
        }
        with requests.get(url,params) as resp:
            if resp.json().get('error_code'):
                await bot.send(event,'返回结果错误',at_sender=False)
                return
            result = resp.json()['trans_result'][0]['dst']
            await bot.send(event,result,at_sender=False)