from .model import ArtifactSet, Chara
from hoshino.util.sutil import load_config
from pathlib import Path
from typing import List
import requests
import json
import base64

from .config import USER_CHARA_DIR, USER_ART_DIR, USER_DIR


def get_token():
    grant_type = 'client_credentials'
    client_id = '9CO1vOQibtsB5e5CkjPOhgQk'
    client_secret = 'LwRFPZOxXGGSQDbVNxe1BhjpLAlKct2F'
    url = 'https://aip.baidubce.com/oauth/2.0/token'
    params = {'grant_type':grant_type,'client_id':client_id,'client_secret':client_secret}
    with requests.get(url,params) as resp:
        data = resp.json()
        token = data['access_token']
        #print(token)
        return token

"""def ocr(pic_url) -> List:#参数图片url
    token = get_token()
    print(token)
    url = "https://aip.baidubce.com/rest/2.0/ocr/v1/formula?access_token="+token
    params = {'url':pic_url}
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    with requests.post(url,data=params,headers=headers) as resp:
        data = resp.json()
        print(data)
        words_result = data['words_result']
        return words_result"""
    
def ocr(img_bytes: bytes):
    token = get_token()
    url = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token="+token
    img = base64.b64encode(img_bytes)
    params ={"image":img}
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    with requests.post(url,data=params,headers=headers) as resp:
        data = resp.json()
        words_result = data['words_result']
        return words_result

def to_number(s: str):
    if ',' in s:
        s = s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        pass
    if '%' in s:
        s = s.replace('%', '')
    try:
        return float(s)/100
    except ValueError:
        pass 
 
    try:
        import unicodedata
        unicodedata.numeric(s)
        return True
    except (TypeError, ValueError):
        pass
    return False

def linear_interpolation(x1, y1, x2, y2, x):
    return y1 + x * (y2-y1)/(x2-x1)

def get_user_chara(uid: int, name: str):
    p = USER_CHARA_DIR.joinpath(f'{uid}.json')
    d = load_config(p).get(name)
    if d:
        return Chara(**d)
    else:
        return None

def get_user_artset(uid: int, name: str):
    p = USER_ART_DIR.joinpath(f'{uid}.json')
    d = load_config(p).get(name)
    if d:
        return ArtifactSet(**d)
    else:
        return None

def get_user_ysid(uid: int):
    p = USER_DIR.joinpath('binds.json')
    return load_config(p).get(str(uid))





