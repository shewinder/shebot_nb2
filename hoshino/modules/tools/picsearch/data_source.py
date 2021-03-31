import requests
import re

class Paint:
    def __init__(self):
        self.similarity = None
        self.thumbnail = None
        self.title = None
        self.pid = None
        self.author = None
        self.url = None
class Anime():
    def __init__(self):
        self.similarity = None
        self.anime = None
        self.season = None
        self.episode = None
        self.at = None
        self.is_adult =None

def saucenao_api(pic_url):
    url = 'https://saucenao.com/search.php'
    params = {
        'db' : 5,
        'output_type' : 2,
        'testmode' : 1,
        'numres' : 1,
        'url' : pic_url,
        'api_key' : '0a9d3bd4068fe8be95ae1ce20320b01c3a69440b'
    }
    try:
        with requests.get(url,params) as resp:
            res_list = []
            results = resp.json()['results']
            for result in results:
                header = result['header']
                data = result['data']
                res = Paint()
                res.similarity = float(header['similarity'])
                res.thumbnail = header['thumbnail']
                res.pid = data['pixiv_id']
                res.author = data['member_name']
                res.title = data['title']
                #以下处理图片代理站链接
                index_name = header['index_name']
                try:
                    num = int(re.search('\d{4,10}_p(\d{1,3}).',index_name).group(1))+1
                except:
                    num = 1
                if num > 1:
                    res.url = f'https://pixiv.cat/{res.pid}-{num}.jpg'
                else:
                    res.url = f'https://pixiv.cat/{res.pid}.jpg或者https://pixiv.cat/{res.pid}-{num}.jpg'
                res_list.append(res)
            return res_list
    except:
        return None

def tracemoe_api(pic_url):
    url = 'https://trace.moe/api/search'
    params = {
        'url' : pic_url
    }
    try:
        with requests.get(url,params) as resp:
            result = resp.json()['docs'][0]
            ani = Anime()
            ani.similarity = float(result['similarity'])
            ani.anime = result['title_chinese']
            ani.season = result['season']
            ani.episode = result['episode']
            ani.at = result['at']
            ani.is_adult = result['is_adult']
            return ani
    except:
        return None
