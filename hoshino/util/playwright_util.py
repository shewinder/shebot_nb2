'''
Author: Kimi
Date: 2026-03-22
Description: Playwright 远程浏览器连接工具
    通过 WebSocket 连接 Docker 中独立运行的浏览器服务
    无需在本地安装浏览器
'''

import asyncio
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator
from urllib.parse import urljoin

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
except ImportError:
    raise ImportError(
        "请先安装 playwright Python 库: uv add playwright\n"
        "注意：不需要运行 playwright install 安装浏览器"
    )

from hoshino.log import logger


# 默认浏览器服务配置
DEFAULT_BROWSER_WS_URL = "ws://browser:3000/chromium?launch={\"headless\":false}"
DEFAULT_TIMEOUT = 30000  # 30秒


class PlaywrightClient:
    """
    Playwright 远程浏览器客户端
    
    通过 WebSocket 连接到 Docker 中运行的 browserless/chrome 服务
    支持复用浏览器会话和上下文
    
    使用示例:
        client = PlaywrightClient()
        page = await client.new_page()
        await page.goto("https://example.com")
        await client.close()
    """
    
    def __init__(
        self,
        ws_url: str = DEFAULT_BROWSER_WS_URL,
        timeout: int = DEFAULT_TIMEOUT,
        viewport: Optional[dict] = None
    ):
        """
        初始化 Playwright 客户端
        
        Args:
            ws_url: 浏览器服务的 WebSocket URL
            timeout: 默认超时时间（毫秒）
            viewport: 视口设置，默认 1920x1080
        """
        self.ws_url = ws_url
        self.timeout = timeout
        self.viewport = viewport or {"width": 1920, "height": 1080}
        
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        
    async def connect(self) -> Browser:
        """
        连接到远程浏览器
        
        Returns:
            Browser 实例
        """
        if self._browser:
            return self._browser
            
        self._playwright = await async_playwright().start()
        
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.ws_url.replace("ws://", "http://").replace("/chromium", "/")
            )
            logger.info(f"已连接到远程浏览器: {self.ws_url}")
        except Exception as e:
            # 如果 CDP 连接失败，尝试普通 WebSocket 连接
            try:
                self._browser = await self._playwright.chromium.connect(self.ws_url)
                logger.info(f"已通过 WebSocket 连接到远程浏览器: {self.ws_url}")
            except Exception as e2:
                logger.error(f"连接浏览器失败: {e}, {e2}")
                raise
                
        return self._browser
    
    async def new_context(self, **kwargs) -> BrowserContext:
        """
        创建新的浏览器上下文
        
        Returns:
            BrowserContext 实例
        """
        if not self._browser:
            await self.connect()
            
        context_options = {
            "viewport": self.viewport,
            **kwargs
        }
        
        self._context = await self._browser.new_context(**context_options)
        
        # 设置默认超时（在 context 创建后设置）
        self._context.set_default_timeout(self.timeout)
        self._context.set_default_navigation_timeout(self.timeout)
        
        return self._context
    
    async def new_page(self, **kwargs) -> Page:
        """
        创建新页面
        
        Returns:
            Page 实例
        """
        if not self._context:
            await self.new_context()
            
        page = await self._context.new_page()
        
        # 注入反检测脚本
        await self._inject_stealth_script(page)
        
        return page
    
    async def _inject_stealth_script(self, page: Page):
        """注入反检测脚本，绕过一些网站的基本检测"""
        stealth_script = """
        () => {
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            window.chrome = { runtime: {} };
        }
        """
        await page.add_init_script(stealth_script)
    
    async def close(self):
        """关闭浏览器连接"""
        try:
            if self._context:
                await self._context.close()
                self._context = None
                
            if self._browser:
                await self._browser.close()
                self._browser = None
                
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
                
            logger.info("浏览器连接已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器连接时出错: {e}")
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


@asynccontextmanager
async def get_page(
    ws_url: str = DEFAULT_BROWSER_WS_URL,
    timeout: int = DEFAULT_TIMEOUT,
    viewport: Optional[dict] = None
) -> AsyncGenerator[Page, None]:
    """
    上下文管理器，自动管理页面生命周期
    
    使用示例:
        async with get_page() as page:
            await page.goto("https://example.com")
            content = await page.content()
    """
    client = PlaywrightClient(ws_url, timeout, viewport)
    try:
        page = await client.new_page()
        yield page
    finally:
        await client.close()


async def screenshot(
    url: str,
    selector: Optional[str] = None,
    full_page: bool = False,
    ws_url: str = DEFAULT_BROWSER_WS_URL,
    wait_for: Optional[str] = None,
    wait_timeout: int = 5000,
    viewport: Optional[dict] = None
) -> bytes:
    """
    网页截图便捷函数
    
    Args:
        url: 目标网页 URL
        selector: 如果指定，只截取该元素
        full_page: 是否截取整个页面
        ws_url: 浏览器服务地址
        wait_for: 等待某个选择器出现
        wait_timeout: 等待超时时间
        viewport: 自定义视口大小，默认 1920x1080
        
    Returns:
        PNG 图片字节数据
        
    使用示例:
        img_bytes = await screenshot("https://example.com", full_page=True)
    """
    # 使用更大的视口确保桌面端渲染
    custom_viewport = viewport or {"width": 1920, "height": 1080}
    
    async with get_page(ws_url, viewport=custom_viewport) as page:
        # 设置更真实的 User-Agent
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
        })
        
        # 导航并等待网络空闲
        await page.goto(url, wait_until="networkidle")
        
        # 额外等待确保字体和布局稳定
        await page.wait_for_timeout(500)
        
        # 等待特定选择器（如果指定）
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=wait_timeout)
        
        # 截图前滚动到顶部确保一致性
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(200)
        
        if selector:
            element = await page.query_selector(selector)
            if element:
                return await element.screenshot(type="png")
            else:
                raise ValueError(f"未找到元素: {selector}")
        else:
            return await page.screenshot(full_page=full_page, type="png")


async def fetch_page_content(
    url: str,
    wait_for: Optional[str] = None,
    evaluate: Optional[str] = None,
    ws_url: str = DEFAULT_BROWSER_WS_URL
) -> str:
    """
    获取网页内容便捷函数
    
    Args:
        url: 目标网页 URL
        wait_for: 等待某个选择器出现后再获取内容
        evaluate: 执行自定义 JavaScript 并返回结果
        ws_url: 浏览器服务地址
        
    Returns:
        网页 HTML 内容或 JavaScript 执行结果
        
    使用示例:
        # 获取渲染后的 HTML
        html = await fetch_page_content("https://spa-example.com")
        
        # 获取特定元素内容
        text = await fetch_page_content(
            "https://example.com",
            evaluate="document.querySelector('.content').innerText"
        )
    """
    async with get_page(ws_url) as page:
        await page.goto(url, wait_until="networkidle")
        
        if wait_for:
            await page.wait_for_selector(wait_for)
        
        if evaluate:
            return await page.evaluate(evaluate)
        
        return await page.content()


# 便捷函数：检查浏览器服务是否可用
async def check_browser_health(ws_url: str = DEFAULT_BROWSER_WS_URL) -> bool:
    """
    检查浏览器服务是否可用
    
    Returns:
        True 如果服务可用，否则 False
    """
    try:
        health_url = ws_url.replace("ws://", "http://").replace("/chromium", "/health")
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(health_url, timeout=5) as resp:
                return resp.status == 200
    except Exception as e:
        logger.warning(f"浏览器健康检查失败: {e}")
        return False
