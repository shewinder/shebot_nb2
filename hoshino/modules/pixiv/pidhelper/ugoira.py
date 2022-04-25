from io import BytesIO
import os
import tempfile
import zipfile
from typing import List

import aiohttp
from PIL import Image


async def get_ugoira_gif(pid: str) -> bytes:
    """
    transform pixiv ugoira(its animated image format) to gif bytes
    """
    apiurl = "https://api.shewinder.win/pixiv/ugoira/"
    param = {"illust_id": pid}
    async with aiohttp.ClientSession() as session:
        async with session.get(apiurl, params=param) as resp:
            if resp.status == 200:
                ugoira_json = await resp.json()

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_url: str = ugoira_json["ugoira_metadata"]["zip_urls"]['medium']
        zip_url = zip_url.replace('600x600', '1920x1080')
        print(f'download form {zip_url}')
        zip_file = await download(
            zip_url.replace("i.pximg.net", "pixiv.shewinder.win"),
            os.path.join(tmpdir, "ugoira.zip"),
        )
        frame_dir = extract(zip_file, os.path.join(tmpdir, "imgs"))
        frames = list(
            map(
                lambda x: Image.open(os.path.join(frame_dir, x["file"])),
                ugoira_json["ugoira_metadata"]["frames"],
            )
        )
        delays = list(map(lambda x: x["delay"], ugoira_json["ugoira_metadata"]["frames"]))
        return generate_gif(frames, delays)


async def download(url, path):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                with open(path, "wb") as f:
                    f.write(await resp.read())
    return path


def extract(zip_file, dst_dir):
    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        zip_ref.extractall(dst_dir)
    return dst_dir


def generate_gif(frames: List[Image.Image], delays: List[int]) -> bytes:
    first = frames[0]
    frames.pop(0)
    out = BytesIO()
    first.save(
        fp=out,
        save_all=True,
        append_images=frames,
        format="gif",
        duration=delays,
        loop=0,
        quality=95,
    )
    return out.getvalue()
