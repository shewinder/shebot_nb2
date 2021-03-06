from io import BytesIO
from os import path
import os
from typing import Union

from filetype.filetype import guess_mime
from PIL import Image

from hoshino import MessageSegment


from hoshino.util.sutil import get_random_file, get_md5, download_async

# Res资源封装类
# img 和 image 代表的分别为ResImg和 MessageSegment 对象

class ResImg:
    def __init__(self, abs_path):
        self._path = abs_path

    @property
    def path(self):
        """资源文件的路径，供bot内部使用"""
        return self._path

    @property
    def exist(self):
        return os.path.exists(self.path)

    @property
    def cqcode(self) -> MessageSegment:
        if self.exist:
            return MessageSegment.image(f'file:///{os.path.abspath(self.path)}')
        else:
            return MessageSegment.text('【图片丢了】')

    def open(self) -> Image:
        try:
            return Image.open(self.path)
        except FileNotFoundError:
            print(f'缺少图片资源：{self.path}')
            raise

class Res:
    base_dir = path.abspath(path.join('data', 'static'))
    image_dir = path.join(base_dir, 'image')
    record_dir = path.join(base_dir, 'record')
    img_cache_dir = path.join(image_dir, 'cache')

    if not path.exists(image_dir):
        os.makedirs(image_dir)

    if not path.exists(record_dir):
        os.makedirs(record_dir)

    if not path.exists(img_cache_dir):
        os.makedirs(img_cache_dir)
    
    
    def check_exist(res_path: str) -> bool:
        return path.exists(res_path)

    @classmethod
    def img(cls, pic_path: str) -> ResImg:
        if cls.check_exist(pic_path):
            return ResImg(pic_path)
        elif cls.check_exist(path.join(cls.image_dir, pic_path)):
            return ResImg(path.join(cls.image_dir, pic_path))
        else:
            return ResImg()

    @classmethod
    def image(cls, pic_path: str) -> MessageSegment:
        if cls.check_exist(pic_path):
            return ResImg(pic_path).cqcode
        elif cls.check_exist(path.join(cls.image_dir, pic_path)):
            return ResImg(path.join(cls.image_dir, pic_path)).cqcode
        else:
            return ResImg().cqcode

    @classmethod
    def record(cls, rec_path) -> MessageSegment:
        if cls.check_exist(rec_path):
            return MessageSegment.record(f'file:///{rec_path}')
        elif cls.check_exist(path.join(cls.record_dir, rec_path)):
            return MessageSegment.record(f'file:///{path.join(cls.record_dir, rec_path)}')
        else:
            return '【图片丢了】'

    @classmethod
    def get_random_img(cls, folder=None) -> ResImg:
        if not folder:
            image_path = cls.image_dir
        else:
            image_path = path.join(cls.image_dir, folder)
        image_name = get_random_file(image_path)
        return cls.img(path.join(image_path, image_name))

    @classmethod
    def get_random_record(cls, folder=None) -> MessageSegment:
        if not folder:
            record_path = cls.record_dir
        else:
            record_path = path.join(cls.record_dir, folder)
        rec_name = get_random_file(record_path)
        return cls.record(path.join(record_path, rec_name))

    @classmethod
    async def img_from_url(cls, url: str, cache=True) -> ResImg:
        fname = get_md5(url)
        image = path.join(cls.img_cache_dir, f'{fname}.jpg')
        if not path.exists(image) or not cache:
            image = await download_async(url, cls.img_cache_dir, f'{fname}.jpg')
        return cls.img(image) 

    @classmethod
    def image_from_memory(cls, data: Union[bytes, Image.Image]) -> MessageSegment:
        if isinstance(data, Image.Image):
            out = BytesIO()
            data.save(out, format='png')
            data = out.getvalue()
        if not isinstance(data, bytes):
            raise ValueError('不支持的参数类型')
        ftype = guess_mime(data)
        if not ftype or not ftype.startswith('image'):
            raise ValueError('不是有效的图片类型')
        fn = get_md5(data)
        save_path = path.join(cls.img_cache_dir, fn)
        with open(save_path, 'wb') as f:
            f.write(data)
        return cls.image(path.join(cls.img_cache_dir, fn))

