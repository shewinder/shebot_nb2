from nonebot import *
import random,os,json,re, time
import hashlib
import os
from urllib.parse import urlencode
from functools import partial

import requests

cookie = '_MHYUUID=56fc6352-7705-4e19-830f-5cbfc4c5c4f4; UM_distinctid=17af55bf80b447-0e219834d7a735-2343360-144000-17af55bf80c59d; _ga=GA1.2.970723111.1627901029; _gid=GA1.2.1807082744.1627901029; aliyungf_tc=35e0735253ebeecb62e2f480ddedf63792961a81403af39aab767ca8236f8a98; ltoken=ZkCVrBFNsegXg5qfeYWIdfW7EPQQWEeSV0yCCJ5d; ltuid=185852111; cookie_token=8VTZx1edbZR8s71AEpDxYW5Tap0sxVZA3u6FCWd1; account_id=185852111'

def __md5__(text):
    _md5 = hashlib.md5()
    _md5.update(text.encode())
    return _md5.hexdigest()

def __get_ds__(query, body=None):
    if body:
        body = json.dumps(body)
    n = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs" # Github-@lulu666lulu
    i = str(int(time.time()))
    r = str(random.randint(100000, 200000))
    q = '&'.join([f'{k}={v}' for k, v in query.items()])
    c = __md5__("salt=" + n + "&t=" + i + "&r=" + r + '&b=' + (body or '') + '&q=' + q)
    return i + "," + r + "," + c

def request_data(uid=0, api='index', character_ids=None, cookie=''):
    server = 'cn_gf01'
    if uid[0] == "5":
        server = 'cn_qd01'
    headers = {
        'Accept': 'application/json, text/plain, */*',
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) miHoYoBBS/2.11.1",
        "Referer": "https://webstatic.mihoyo.com/",
        "x-rpc-app_version": "2.11.1",
        "x-rpc-client_type": '5',
        "DS": "",
        'Cookie': cookie
    }

    params = {"role_id": uid, "server": server}

    json_data = None
    fn = requests.get
    base_url = 'https://api-takumi.mihoyo.com/game_record/app/genshin/api/%s'
    url = base_url % api + '?'
    if api == 'index':
        url += urlencode(params)
    elif api == 'spiralAbyss':
        params['schedule_type'] = '1'
        url += urlencode(params)
    elif api == 'character':
        fn = requests.post
        json_data = {"character_ids": character_ids,"role_id": uid, "server": server}
        params = {}

    headers['DS'] = __get_ds__(params, json_data)
    req =  fn(url=url, headers=headers, json=json_data)
    if req:
        return  req.json()
    else:
        return

get_ysinfo = partial(request_data, cookie=cookie)

def get_chara_from_miyoushe(uid: str, name: str):
    res = request_data(uid=uid, cookie=cookie)
    Character_List = res["data"]["avatars"]
    Character_ids = []
    for i in Character_List:
        Character_ids +=  [i["id"]]
    res = request_data(uid=uid, cookie=cookie, api='character', character_ids=Character_ids)
    avatars = res['data']['avatars']
    for avatar in avatars:
        if avatar['name'] == name:
            break
    chara = {}
    chara['c_level'] = avatar['level']
    chara['rank'] = avatar['actived_constellation_num']
    chara['w_name'] = avatar['weapon']['name']
    chara['w_level'] = avatar['weapon']['level']
    chara['refine'] = avatar['weapon']['affix_level']
    return chara