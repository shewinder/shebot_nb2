'''
Author: Kimi
Date: 2026-03-22
Description: Playwright 功能演示模块
    展示如何使用远程浏览器进行网页截图、内容获取等操作
'''

import os
import re
from io import BytesIO

from nonebot.adapters.onebot.v11 import MessageSegment

from hoshino import Service, Bot, Event, CommandArg, Message
from hoshino.util.playwright_util import (
    screenshot,
    fetch_page_content,
    get_page,
    check_browser_health
)


# 获取浏览器服务地址（从环境变量或使用默认值）
BROWSER_WS_URL = os.getenv(
    "BROWSER_WS_URL", 
    "ws://browser:3000/chromium?launch={\"headless\":false}"
)

sv = Service(
    'playwright_demo',
    help_='''
Playwright 浏览器功能演示
- 网页截图 [url] - 对指定网页进行截图
- 网页内容 [url] - 获取网页文本内容
- 浏览器状态 - 检查浏览器服务是否可用
- 网页元素 [选择器] [url] - 截取特定元素
- 执行脚本 [url] [JS代码] - 在页面执行 JavaScript
- 滚动截图 [url] - 滚动页面后截图（适用于懒加载页面）
''',
    enable_on_default=False  # 默认关闭，需管理员手动开启
)


# ============ 基础命令 ============

screenshot_cmd = sv.on_command('网页截图', only_group=False)

@screenshot_cmd.handle()
async def web_screenshot(bot: Bot, event: Event, arg: Message = CommandArg()):
    """网页截图命令
    用法：
      网页截图 https://example.com - 默认 1920x1080 视口
      网页截图 --width 1280 https://example.com - 指定宽度
      网页截图 --mobile https://example.com - 移动端视口
    """
    text = str(arg).strip()
    
    if not text:
        await screenshot_cmd.finish('请提供网址，例如：网页截图 https://example.com')
        return
    
    # 解析参数
    args = text.split()
    url = None
    width = 1920
    height = 1080
    is_mobile = False
    
    i = 0
    while i < len(args):
        if args[i] == '--width' and i + 1 < len(args):
            width = int(args[i + 1])
            i += 2
        elif args[i] == '--height' and i + 1 < len(args):
            height = int(args[i + 1])
            i += 2
        elif args[i] == '--mobile':
            is_mobile = True
            width = 375
            height = 812
            i += 1
        elif not url and not args[i].startswith('--'):
            url = args[i]
            i += 1
        else:
            i += 1
    
    if not url:
        await screenshot_cmd.finish('请提供网址')
        return
        
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await bot.send(event, f'正在截图 ({width}x{height})...')
    
    try:
        # 截取网页全屏
        viewport = {"width": width, "height": height}
        img_bytes = await screenshot(
            url=url,
            full_page=True,
            ws_url=BROWSER_WS_URL,
            viewport=viewport
        )
        
        # 发送图片
        await bot.send(event, MessageSegment.image(BytesIO(img_bytes)))
        
    except Exception as e:
        sv.logger.error(f"截图失败: {e}")
        await bot.send(event, f'截图失败: {str(e)}')


content_cmd = sv.on_command('网页内容', only_group=False)

@content_cmd.handle()
async def web_content(bot: Bot, event: Event, arg: Message = CommandArg()):
    """获取网页内容命令"""
    url = str(arg).strip()
    
    if not url:
        await content_cmd.finish('请提供网址，例如：网页内容 https://example.com')
        return
        
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await bot.send(event, '正在获取内容...')
    
    try:
        # 获取渲染后的页面内容
        content = await fetch_page_content(
            url=url,
            ws_url=BROWSER_WS_URL
        )
        
        # 提取正文（简化处理）
        # 移除 script 和 style 标签内容
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
        # 移除 HTML 标签
        text = re.sub(r'<[^>]+>', '', content)
        # 合并空白
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 限制长度
        if len(text) > 500:
            text = text[:500] + '...'
            
        await bot.send(event, f'网页内容：\n{text}')
        
    except Exception as e:
        sv.logger.error(f"获取内容失败: {e}")
        await bot.send(event, f'获取内容失败: {str(e)}')


status_cmd = sv.on_command('浏览器状态', aliases={'browser_status'}, only_group=False)

@status_cmd.handle()
async def browser_status(bot: Bot, event: Event):
    """检查浏览器服务状态"""
    is_healthy = await check_browser_health(BROWSER_WS_URL)
    
    if is_healthy:
        await status_cmd.finish('✅ 浏览器服务运行正常')
    else:
        await status_cmd.finish('❌ 浏览器服务不可用')


# ============ 高级用法示例 ============

element_cmd = sv.on_command('网页元素', only_group=False)

@element_cmd.handle()
async def web_element(bot: Bot, event: Event, arg: Message = CommandArg()):
    """
    截取特定元素示例
    使用方式: 网页元素 [选择器] [url]
    例如: 网页元素 #content https://example.com
    """
    text = str(arg).strip()
    args = text.split(maxsplit=1)
    
    if len(args) < 2:
        await element_cmd.finish('用法：网页元素 [CSS选择器] [URL]\n例如：网页元素 #content https://example.com')
        return
    
    selector = args[0]
    url = args[1]
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await bot.send(event, f'正在截取元素 {selector}...')
    
    try:
        img_bytes = await screenshot(
            url=url,
            selector=selector,
            ws_url=BROWSER_WS_URL
        )
        await bot.send(event, MessageSegment.image(BytesIO(img_bytes)))
        
    except Exception as e:
        sv.logger.error(f"截图失败: {e}")
        await bot.send(event, f'截图失败: {str(e)}')


script_cmd = sv.on_command('执行脚本', only_group=False)

@script_cmd.handle()
async def execute_script(bot: Bot, event: Event, arg: Message = CommandArg()):
    """
    在页面执行 JavaScript 并返回结果
    使用方式: 执行脚本 [URL] [JS代码]
    """
    text = str(arg).strip()
    
    # 简单解析：第一个词是 URL，后面是 JS
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await script_cmd.finish('用法：执行脚本 [URL] [JavaScript代码]')
        return
    
    url, script = parts
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await bot.send(event, '正在执行脚本...')
    
    try:
        async with get_page(BROWSER_WS_URL) as page:
            await page.goto(url, wait_until="networkidle")
            result = await page.evaluate(script)
            
            # 格式化结果
            result_str = str(result)
            if len(result_str) > 1000:
                result_str = result_str[:1000] + '...'
                
            await bot.send(event, f'执行结果：\n{result_str}')
            
    except Exception as e:
        sv.logger.error(f"执行脚本失败: {e}")
        await bot.send(event, f'执行失败: {str(e)}')


# ============ 复杂场景示例：滚动截图 ============

async def screenshot_with_scroll(url: str, scroll_times: int = 3) -> bytes:
    """
    滚动页面并截图的示例
    适用于懒加载内容的页面
    """
    async with get_page(BROWSER_WS_URL) as page:
        await page.goto(url, wait_until="networkidle")
        
        # 滚动页面多次，触发懒加载
        for i in range(scroll_times):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(500)  # 等待 500ms
        
        # 回到顶部
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(200)
        
        return await page.screenshot(full_page=True, type="png")


scroll_cmd = sv.on_command('滚动截图', only_group=False)

@scroll_cmd.handle()
async def scroll_screenshot(bot: Bot, event: Event, arg: Message = CommandArg()):
    """滚动页面后截图（适用于懒加载页面）"""
    url = str(arg).strip()
    
    if not url:
        await scroll_cmd.finish('请提供网址')
        return
        
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await bot.send(event, '正在滚动截图...')
    
    try:
        img_bytes = await screenshot_with_scroll(url, scroll_times=5)
        await bot.send(event, MessageSegment.image(BytesIO(img_bytes)))
        
    except Exception as e:
        sv.logger.error(f"滚动截图失败: {e}")
        await bot.send(event, f'截图失败: {str(e)}')
