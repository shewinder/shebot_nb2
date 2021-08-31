
#源码来源于https://github.com/Womsxd/YuanShen_User_Info

import os
import hashlib
import math
import json
import time
import random
import re
import string

import aiohttp
from pathlib import Path
from PIL import Image
from PIL import ImageFont, ImageDraw

from hoshino.util.sutil import download_async
from hoshino.sres import Res as R

mhyVersion = "2.9.0"
salt = "w5k9n3aqhoaovgw25l373ee18nsazydo" # Github-@Azure99
client_type = "5"
cache_Cookie = "_MHYUUID=56fc6352-7705-4e19-830f-5cbfc4c5c4f4; UM_distinctid=17af55bf80b447-0e219834d7a735-2343360-144000-17af55bf80c59d; _ga=GA1.2.970723111.1627901029; _gid=GA1.2.1807082744.1627901029; aliyungf_tc=35e0735253ebeecb62e2f480ddedf63792961a81403af39aab767ca8236f8a98; ltoken=ZkCVrBFNsegXg5qfeYWIdfW7EPQQWEeSV0yCCJ5d; ltuid=185852111; cookie_token=8VTZx1edbZR8s71AEpDxYW5Tap0sxVZA3u6FCWd1; account_id=185852111"

RES_PATH = Path(__file__).parent.parent.joinpath('_res')
FONTS_PATH = RES_PATH.joinpath('fonts')
FONTS = FONTS_PATH.joinpath('sakura.ttf')
IMG_PATH = RES_PATH.joinpath('imgs')
ICON_PATH = RES_PATH.joinpath('icon')
font = ImageFont.truetype(str(FONTS), 16)

def get_duanluo(text):
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
        width, height = draw.textsize(char, font)
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

def split_text(content):
    # 按规定宽度分组
    max_line_height, total_lines = 0, 0
    allText = []
    for text in content.split('\n'):
        duanluo, line_height, line_count = get_duanluo(text)
        max_line_height = max(line_height, max_line_height)
        total_lines += line_count
        allText.append((duanluo, line_count))
    line_height = max_line_height
    total_height = total_lines * line_height
    drow_height = total_lines * line_height
    return allText, total_height, line_height, drow_height

def md5(text):
    md5 = hashlib.md5()
    md5.update(text.encode())
    return md5.hexdigest()


def DSGet():
    n = salt
    i = str(int(time.time()))
    r = ''.join(random.sample(string.ascii_lowercase + string.digits, 6))
    c = md5("salt=" + n + "&t=" + i + "&r=" + r)
    return i + "," + r + "," + c



async def GetInfo(Uid, ServerID):
    async with aiohttp.ClientSession() as session:
        async with session.get(
                url="https://api-takumi.mihoyo.com/game_record/genshin/api/index?server=" + ServerID + "&role_id=" + Uid,
                headers={
                    'Accept': 'application/json, text/plain, */*',
                    'DS': DSGet(),
                    'Origin': 'https://webstatic.mihoyo.com',
                    'x-rpc-app_version': mhyVersion,
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 9; Unspecified Device) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/39.0.0.0 Mobile Safari/537.36 miHoYoBBS/2.2.0',
                    'x-rpc-client_type': client_type,
                    'Referer': 'https://webstatic.mihoyo.com/app/community-game-records/index.html?v=6',
                    'Accept-Encoding': 'gzip, deflate',
                    'Accept-Language': 'zh-CN,en-US;q=0.8',
                    'X-Requested-With': 'com.mihoyo.hyperion',
                    "Cookie": cache_Cookie
                    }) as req:
            return await req.text()

async def GetCharacter(Uid, ServerID, Character_ids):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url = "https://api-takumi.mihoyo.com/game_record/genshin/api/character",
                headers = {
                    'Accept': 'application/json, text/plain, */*',
                    'DS': DSGet(),
                    'Origin': 'https://webstatic.mihoyo.com',
                    "Cookie": cache_Cookie,#自己获取
                    'x-rpc-app_version': mhyVersion,
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 9; Unspecified Device) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/39.0.0.0 Mobile Safari/537.36 miHoYoBBS/2.2.0',
                    'x-rpc-client_type': client_type,
                    'Referer': 'https://webstatic.mihoyo.com/app/community-game-records/index.html?v=6',
                    'Accept-Encoding': 'gzip, deflate',
                    'Accept-Language': 'zh-CN,en-US;q=0.8',
                    'X-Requested-With': 'com.mihoyo.hyperion'
                },
                json = {"character_ids": Character_ids ,"role_id": Uid ,"server": ServerID }) as req:
                    return await req.text()
    except:
        print ("访问失败，请重试！")
        return

def GetSpiralAbys(Uid, ServerID, Schedule_type):
    try:
        req = requests.get(
            url = "https://api-takumi.mihoyo.com/game_record/genshin/api/spiralAbyss?schedule_type=" + Schedule_type + "&server="+ ServerID +"&role_id=" + Uid,
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'DS': DSGet(),
                'Origin': 'https://webstatic.mihoyo.com',
                "Cookie": cache_Cookie,#自己获取
                'x-rpc-app_version': mhyVersion,
                'User-Agent': 'Mozilla/5.0 (Linux; Android 9; Unspecified Device) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/39.0.0.0 Mobile Safari/537.36 miHoYoBBS/2.2.0',
                'x-rpc-client_type': client_type,
                'Referer': 'https://webstatic.mihoyo.com/app/community-game-records/index.html?v=6',
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Language': 'zh-CN,en-US;q=0.8',
                'X-Requested-With': 'com.mihoyo.hyperion'
            }
        )
        return (req.text)
    except:
        print ("访问失败，请重试！")
        #sys.exit (1)
        return    

def calcStringLength(text):
    # 令len(str(string).encode()) = m, len(str(string)) = n
    # 字符串所占位置长度 = (m + n) / 2
    # 但由于'·'属于一个符号而非中文字符所以需要把长度 - 1
    if re.search('·', text) is not None:
        stringlength = int(((str(text).encode()) + len(str(text)) - 1) / 2)
    elif re.search(r'[“”]', text) is not None:
        stringlength = int((len(str(text).encode()) + len(str(text))) / 2) - 2
    else:
        stringlength = int((len(str(text).encode()) + len(text)) / 2)

    return stringlength


def spaceWrap(text, flex=10):
    stringlength = calcStringLength(text)

    return '%s' % (str(text)) + '%s' % (' ' * int((int(flex) - stringlength)))


def elementDict(text, isOculus=False):
    elementProperty = str(re.sub(r'culus_number$', '', text)).lower()
    elementMastery = {
        "anemo": "风",
        "pyro": "火",
        "geo": "岩",
        "electro": "雷",
        "cryo": "冰",
        "hydro": "水",
        "dendro": "草",  # https://genshin-impact.fandom.com/wiki/Dendro
        "none": "无",
    }
    try:
        elementProperty = str(elementMastery[elementProperty])
    except KeyError:
        elementProperty = "草"
    if isOculus:
        return elementProperty + "神瞳"
    elif not isOculus:
        return elementProperty + "属性"

async def JsonAnalysis(JsonText,Uid, ServerID):
    data = json.loads(JsonText)
    if data["retcode"] != 0:
        if data["retcode"] == 10001:
            os.remove("cookie.txt")
            return "Cookie错误/过期，请重置Cookie"
        return (
                "Api报错，返回内容为：\r\n"
                + JsonText + "\r\n出现这种情况可能是UID输入错误 or 不存在"
        )
    else:
        pass
    msg_list = []
    Character_Info = f'UID{Uid} 的信息为：\n'
    Character_Info += "人物：\n"
    msg_list.append(Character_Info)
    name_length = []
    Character_List = data["data"]["avatars"]
    Character_ids = []
    for i in Character_List:
        Character_ids +=  [i["id"]]
        name_length.append(calcStringLength(i["name"]))
    dataC = json.loads(await GetCharacter(Uid, ServerID, Character_ids)) 
    Character_datas = dataC["data"]["avatars"]
    namelength_max = int(max(name_length))
    for i in Character_datas:
        weapon = i["weapon"]
        Character_Type = elementDict(i["element"], isOculus=False)
        if i["name"] == "旅行者":
            if i["image"].find("UI_AvatarIcon_PlayerGirl") != -1:
                msg_list.append(i['icon'])
                msg_list.append(weapon['icon'])
                TempText = (
                        spaceWrap(str("荧"), namelength_max) +
                        "（" + spaceWrap(str(i["level"]), 2) + "级）"
                        + "武器 ：" + str(weapon["name"]) + " " + str(weapon["level"]) + "级 " + " 精炼" + str(weapon["affix_level"])
                )
                msg_list.append(TempText)
            elif i["image"].find("UI_AvatarIcon_PlayerBoy") != -1:
                msg_list.append(i['icon'])
                msg_list.append(weapon['icon'])
                TempText = (
                        spaceWrap(str("空"), namelength_max) +
                        "（" + spaceWrap(str(i["level"]), 2) + "级）"
                        + "武器 ：" + str(weapon["name"]) + " " + str(weapon["level"]) + "级 " + " 精炼" + str(weapon["affix_level"])
                )
                msg_list.append(TempText)

            else:
                msg_list.append(i['icon'])
                msg_list.append(weapon['icon'])
                TempText = (
                        i["name"] + "[?]" +
                        "（" + spaceWrap(str(i["level"]), 2) + "级）"
                        + "武器 ：" + str(weapon["name"]) + " " + str(weapon["level"]) + "级 " + " 精炼" + str(weapon["affix_level"])
                )
                msg_list.append(TempText)

        else:
            msg_list.append(i['icon'])
            msg_list.append(weapon['icon'])
            TempText = (
                    spaceWrap(str(i["name"]), namelength_max) +
                    "（" + spaceWrap(str(i["level"]), 2) + "级，"
                    + str(i["actived_constellation_num"]) + "命）"
                     + "武器 ：" + str(weapon["name"]) + " " + str(weapon["level"]) + "级 " + " 精炼" + str(weapon["affix_level"])
            )
            msg_list.append(TempText)
        Character_Info = Character_Info + TempText
    Account_Info = "\n账号信息：\n"
    Account_Info += "活跃天数：　　" + str(data["data"]["stats"]["active_day_number"]) + "\n"
    Account_Info += "达成成就数量：" + str(data["data"]["stats"]["achievement_number"]) + "个\n"
    for key in data["data"]["stats"]:
        if re.search(r'culus_number$', key) is not None:
            Account_Info = "{}{}已收集：{}个\n".format(
                Account_Info,
                elementDict(str(key), isOculus=True),  # 判断神瞳属性
                str(data["data"]["stats"][key])
            )
        else:
            pass
    Account_Info += "获得角色数量：" + str(data["data"]["stats"]["avatar_number"]) + "个\n"
    Account_Info += "传送点已解锁：" + str(data["data"]["stats"]["way_point_number"]) + "个\n"
    Account_Info += "秘境解锁数量：" + str(data["data"]["stats"]["domain_number"]) + "个\n"
    Account_Info += "深渊当期进度："
    if data["data"]["stats"]["spiral_abyss"] != "-":
        Account_Info += data["data"]["stats"]["spiral_abyss"] + "\n"
    else:
        Account_Info += "没打\n"
    Account_Info = Account_Info + (
            "\n开启宝箱计数：\n" +
            "普通宝箱：" + str(data["data"]["stats"]["common_chest_number"]) + "个\n" +
            "精致宝箱：" + str(data["data"]["stats"]["exquisite_chest_number"]) + "个\n" +
            "珍贵宝箱：" + str(data["data"]["stats"]["precious_chest_number"]) + "个\n" +
            "华丽宝箱：" + str(data["data"]["stats"]["luxurious_chest_number"]) + "个\n"
    )
    msg_list.append(Account_Info)
    Area_list = data["data"]["world_explorations"]
    Prestige_Info = "区域信息：\n"
    ExtraArea_Info = "供奉信息：\n"

    # 排版开始
    prestige_info_length = []
    extra_area_info_length = []
    for i in Area_list:
        prestige_info_length.append(calcStringLength(i["name"] + " "))
        if len(i["offerings"]) != 0:
            extra_area_info_length.append(calcStringLength(str(i["offerings"][0]["name"]) + " "))

    prestige_info_length_max = max(prestige_info_length)
    extra_area_info_length_max = max(extra_area_info_length)
    # 排版结束

    for i in Area_list:
        if (i["type"] == "Reputation"):
            Prestige_Info = "{}\t{}探索进度：{}%，声望等级：{}级\n".format(
                Prestige_Info,
                spaceWrap(i["name"] + " ", prestige_info_length_max),  # 以最长的地名为准，自动补足空格
                spaceWrap(str(i["exploration_percentage"] / 10).replace("100.0", "100"), 4),  # 以xx.x%长度为准，自动补足空格
                spaceWrap(str(i["level"]), 2)
            )
        else:
            Prestige_Info = "{}\t{}探索进度：{}%\n".format(
                Prestige_Info,
                spaceWrap(i["name"] + " ", prestige_info_length_max),  # 以最长的地名为准，自动补足空格
                spaceWrap(str(i["exploration_percentage"] / 10).replace("100.0", "100"), 4)  # 以xx.x%长度为准，自动补足空格
            )
        if len(i["offerings"]) != 0:
            ExtraArea_Info = "{}\t{}供奉等级：{}级，位置：{}\n".format(
                ExtraArea_Info,
                spaceWrap(str(i["offerings"][0]["name"] + " "), extra_area_info_length_max),
                spaceWrap(str(i["offerings"][0]["level"]), 2),
                str(i["name"])
            )
    Home_Info = "家园信息：\n" + spaceWrap("已开启区域：", 16)
    Home_List = data["data"]["homes"]
    homeworld_list = []
    for i in Home_List:
        homeworld_list.append(i["name"])
    Home_Info += '、'.join(homeworld_list) + "\n"
    Home_Info += spaceWrap("最高洞天仙力：", 16) + str(Home_List[0]["comfort_num"]) + '（' + Home_List[0][
        "comfort_level_name"] + '）\n'
    Home_Info += "已获得摆件数量：" + str(Home_List[0]["item_num"]) + "\n"
    Home_Info += spaceWrap("最大信任等级：", 16) + str(Home_List[0]["level"]) + '级' + "\n"
    Home_Info += "最高历史访客数：" + str(Home_List[0]["visit_num"])
    msg_list.append(Prestige_Info)
    msg_list.append(ExtraArea_Info)
    msg_list.append(Home_Info)
    drow_height = 0
    shul = 1
    for msg in msg_list:
        #print('段落：' + str(msg))
        if 'jpg' in msg or 'png' in msg:
            if shul%2 == 0:
                drow_height += 80
            shul += 1
        else:
            x_drow_duanluo, x_drow_note_height, x_drow_line_height, x_drow_height = split_text(msg)
            drow_height += x_drow_height
    
    base_img1 = os.path.join(IMG_PATH, "dt1.jpg")
    dtimg1 = Image.open(base_img1)
    
    base_img2 = os.path.join(IMG_PATH, "dt2.jpg")
    dtimg2 = Image.open(base_img2)
    
    base_img = os.path.join(IMG_PATH, "dt.jpg")
    dtimg = Image.open(base_img)
    
    need_height = drow_height-477
    needdt = math.ceil(need_height/477)
    drow_height = 1300+needdt*477
    
    im = Image.new("RGB", (600, drow_height), (255, 255, 255))
    
    for num in range(needdt):
        dtheight = 608 + int(num) * 477
        dtbox = (0, dtheight)
        im.paste(dtimg, dtbox)
    
    dtbox1 = (0, 0)
    im.paste(dtimg1, dtbox1)
    
    dtbox2 = (0, drow_height-692)
    im.paste(dtimg2, dtbox2)
    
    
    
    draw = ImageDraw.Draw(im)
    # 左上角开始
    x, y = 25, 608
    shulx = 1
    for msg in msg_list:
        if 'jpg' in msg or 'png' in msg:
            filename = msg.split('/')[-1]
            if not ICON_PATH.joinpath(filename).exists():
                avt = await download_async(msg, ICON_PATH, save_name=filename)

            #读取网络图片信息
            img = Image.open(ICON_PATH.joinpath(filename))
            #image_bytes = urlopen(msg).read()
            # internal data file  
            #格式化网络图片链接
            #data_stream = io.BytesIO(image_bytes)
            #打开网络图片
            #img = Image.open(data_stream).convert('RGBA')
            #获取图片像素
            size = img.size
            #等比缩放
            #定义图片插入的位置
            if shulx%2 == 0:
                box = (110, y-60)
                #等比缩放要放入的图片
                img = img.resize((40, 40))
                #图片插入
                im.paste(img, box, mask=img.split()[3])
            else:
                box = (30, y+10)
                #等比缩放要放入的图片
                img = img.resize((60, 60))
                #图片插入
                im.paste(img, box, mask=img.split()[3])
                y += 80
                #print('原图片：长'+str(size[0])+'，宽'+str(size[1]))
                #print('后图片：长575，宽'+str(sf_height))
            shulx += 1
        else:
            drow_duanluo, drow_note_height, drow_line_height, drow_height = split_text(msg)
            for duanluo, line_count in drow_duanluo:
                draw.text((x, y), duanluo, fill=(0, 0, 0), font=font)
                y += drow_line_height * line_count
        
    return R.image_from_memory(im)