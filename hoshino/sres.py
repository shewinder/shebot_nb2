from io import BytesIO
from typing import Optional, Union
from pathlib import Path

from PIL import Image

from hoshino import MessageSegment


from hoshino import res_dir
from hoshino.util.sutil import get_random_file


class ResImg:
    def __init__(self, abs_path: Union[str, Path]):
        if isinstance(abs_path, str):
            abs_path = Path(abs_path)
        #if not abs_path.is_relative_to(res_dir):
            #raise ValueError('Cannot access outside RESOUCE_DIR')
        self._path = abs_path

    @property
    def path(self):
        """资源文件的路径，供bot内部使用"""
        return self._path

    @property
    def cqcode(self) -> MessageSegment:
        with open(self.path, 'rb') as f:
            b = f.read()
        return MessageSegment.image(file=b)
        #return MessageSegment.image(f'file:///{os.path.abspath(self.path)}')

    @property
    def url(self) -> str:
        return self.path.as_uri()

    def open(self) -> Image.Image:
        try:
            return Image.open(self.path)
        except FileNotFoundError:
            print(f'缺少图片资源：{self.path}')
            raise

class ResRec:
    def __init__(self, abs_path: Union[str, Path]):
        if isinstance(abs_path, str):
            abs_path = Path(abs_path)
        #if not abs_path.is_relative_to(res_dir):
            #raise ValueError('Cannot access outside RESOUCE_DIR')
        self._path = abs_path

    @property
    def path(self):
        """资源文件的路径，供bot内部使用"""
        return self._path

    @property
    def cqcode(self) -> MessageSegment:
        with open(self.path, 'rb') as f:
            b = f.read()
        return MessageSegment.record(file=b)

    @property
    def url(self) -> str:
        return self.path.as_uri()

class Res:
    """
    Res资源封装类
    img 和 image 代表的分别为ResImg和 MessageSegment 对象
    img用于图像操作， image用于发送
    """
    base_dir = Path(res_dir)
    image_dir = base_dir.joinpath('image')
    record_dir = base_dir.joinpath('record')

    if not image_dir.exists():
        image_dir.mkdir()

    if not record_dir.exists():
        record_dir.mkdir()

    @classmethod
    def img(cls, p: Union[str, Path]) -> ResImg:
        if isinstance(p, str):
            p = Path(p)
        if p.exists():
            return ResImg(p)
        elif cls.image_dir.joinpath(p).exists():
            return ResImg(cls.image_dir.joinpath(p))
        else:
            raise ValueError('file not found')

    @classmethod
    def image(cls, p: str) -> MessageSegment:
        return cls.img(p).cqcode


    @classmethod
    def record(cls, p: Union[str, Path]) -> MessageSegment:
        if isinstance(p, str):
            p = Path(p)
        if p.exists():
            return ResRec(p).cqcode
        elif cls.record_dir.joinpath(p).exists():
            return ResRec(cls.record_dir.joinpath(p)).cqcode
        else:
            raise ValueError('file not found')

    @classmethod
    def get_random_img(cls, folder: Union[str, Path]) -> ResImg:
        """
        随机获取一个给定路径下的img， 以res_dir为基准目录
        """
        image_path = cls.base_dir.joinpath(folder)
        image_name = get_random_file(image_path)
        return cls.img(image_path.joinpath(image_name))

    @classmethod
    def get_random_record(cls, folder=None) -> MessageSegment:
        """
        随机获取一个给定路径下的record， 以res_dir为基准目录
        """
        record_path = cls.base_dir.joinpath(folder)
        rec_name = get_random_file(record_path)
        return cls.record(record_path.joinpath(rec_name))

    @classmethod
    def image_from_memory(cls, data: Union[bytes, Image.Image]) -> MessageSegment:
        if isinstance(data, Image.Image):
            out = BytesIO()  
            data.save(out, format='png')
            data = out.getvalue()
        if not isinstance(data, bytes):
            raise ValueError('不支持的参数类型')
        return MessageSegment.image(file=data)
