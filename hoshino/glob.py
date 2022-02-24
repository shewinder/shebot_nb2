from queue import Queue
from typing import Optional
from playwright.async_api import async_playwright, Browser

NR18 = Queue(10) # 非r18色图
R18 = Queue(10) # r18色图.

_browser: Optional[Browser] = None


async def get_browser() -> Browser:
    global _browser
    if not _browser or not _browser.is_connected():
        ap = await async_playwright().start()
        _browser = await ap.chromium.launch()
    return _browser
