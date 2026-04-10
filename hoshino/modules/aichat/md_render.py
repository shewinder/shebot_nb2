"""Markdown 渲染为图片模块"""
import os
import re
from io import BytesIO
from typing import List, Optional

from loguru import logger

try:
    from hoshino.util.playwright_util import get_page, check_browser_health
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright 未安装，Markdown 渲染功能不可用")

try:
    import markdown
    from markdown.extensions import fenced_code, tables, nl2br
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False
    logger.warning("Markdown 库未安装")


MD_PATTERNS = [
    r'#{1,6}\s+',  # 标题
    r'\*\*.*?\*\*',  # 粗体
    r'\*.*?\*',  # 斜体
    r'`[^`]+`',  # 行内代码
    r'```[\s\S]*?```',  # 代码块
    r'\[.*?\]\(.*?\)',  # 链接
    r'!\[.*?\]\(.*?\)',  # 图片
    r'^\s*[-*+]\s+',  # 列表项
    r'^\s*\d+\.\s+',  # 有序列表
    r'^\s*>\s+',  # 引用
    r'\|.*?\|.*?\|',  # 表格
    r'^\s*---\s*$',  # 分隔线
]


def is_markdown(text: str, min_features: int = 2) -> bool:
    if not text or len(text) < 50:
        return False
    
    feature_count = 0
    for pattern in MD_PATTERNS:
        if re.search(pattern, text, re.MULTILINE):
            feature_count += 1
            if feature_count >= min_features:
                return True
    
    return False


MD_IMAGE_PATTERN = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
PLAIN_IMAGE_URL_PATTERN = re.compile(r'https?://[^\s<>"\']+\.(?:png|jpg|jpeg|gif|webp)(?:\?[^\s<>"\']*)?', re.IGNORECASE)


def extract_image_urls(text: str) -> List[str]:
    urls = []
    if not text:
        return urls
    
    for match in MD_IMAGE_PATTERN.finditer(text):
        url = match.group(2).strip()
        if url:
            urls.append(url)
    
    for match in PLAIN_IMAGE_URL_PATTERN.finditer(text):
        url = match.group(0)
        if url and url not in urls:  # 去重
            urls.append(url)
    
    return urls


def strip_thinking_tags(text: str) -> str:
    text = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<thinking>[\s\S]*?</thinking>', '', text, flags=re.IGNORECASE)
    return text.strip()


def markdown_to_html(md_text: str) -> str:
    text = strip_thinking_tags(md_text)
    
    if not MARKDOWN_AVAILABLE:
        # 降级：简单处理
        return f"<p>{text.replace(chr(10), '<br>')}</p>"
    
    md = markdown.Markdown(extensions=[
        'fenced_code',      # 代码块 ```
        'tables',           # 表格
        'nl2br',           # 换行转 <br>
        'toc',             # 标题锚点（可选）
    ])
    
    html = md.convert(text)
    return html


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            font-size: 15px;
            line-height: 1.7;
            color: #24292f;
            background: #ffffff;
            padding: 24px 32px;
        }
        
        .content {
            max-width: 720px;
            margin: 0 auto;
        }
        
        h1, h2, h3, h4, h5, h6 {
            margin-top: 24px;
            margin-bottom: 16px;
            font-weight: 600;
            line-height: 1.25;
            color: #1f2328;
        }
        
        h1 { font-size: 26px; padding-bottom: 8px; border-bottom: 1px solid #d0d7de; }
        h2 { font-size: 22px; padding-bottom: 6px; border-bottom: 1px solid #d0d7de; }
        h3 { font-size: 18px; }
        h4 { font-size: 16px; }
        h5 { font-size: 15px; }
        h6 { font-size: 14px; color: #656d76; }
        
        p {
            margin-bottom: 12px;
        }
        
        code {
            font-family: 'JetBrains Mono', 'Fira Code', Consolas, Monaco, monospace;
            background: rgba(175, 184, 193, 0.2);
            padding: 2px 6px;
            border-radius: 6px;
            font-size: 0.875em;
            color: #24292f;
        }
        
        pre {
            background: #f6f8fa;
            border-radius: 8px;
            padding: 16px;
            overflow-x: auto;
            margin-bottom: 16px;
            border: 1px solid #d0d7de;
        }
        
        pre code {
            background: transparent;
            padding: 0;
            border-radius: 0;
            font-size: 13px;
            line-height: 1.6;
        }
        
        blockquote {
            border-left: 4px solid #d0d7de;
            padding: 0 16px;
            margin-bottom: 16px;
            color: #656d76;
        }
        
        ul, ol {
            margin-bottom: 16px;
            padding-left: 24px;
        }
        
        li {
            margin-bottom: 4px;
        }
        
        li + li {
            margin-top: 4px;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 16px;
            border-spacing: 0;
        }
        
        th, td {
            padding: 8px 12px;
            text-align: left;
            border: 1px solid #d0d7de;
        }
        
        th {
            background: #f6f8fa;
            font-weight: 600;
        }
        
        tr:nth-child(2n) {
            background: #f6f8fa;
        }
        
        hr {
            border: none;
            height: 1px;
            background: #d0d7de;
            margin: 24px 0;
        }
        
        strong {
            font-weight: 600;
        }
        
        a {
            color: #0969da;
            text-decoration: none;
        }
        
        a:hover {
            text-decoration: underline;
        }
        
        .footer {
            margin-top: 32px;
            padding-top: 16px;
            border-top: 1px solid #d0d7de;
            text-align: center;
            font-size: 12px;
            color: #8c959f;
        }
    </style>
</head>
<body>
    <div class="content">
        {{content}}
        <div class="footer">AI 生成内容 · 仅供参考</div>
    </div>
</body>
</html>
"""


async def render_markdown_to_image(md_text: str, ws_url: Optional[str] = None) -> Optional[bytes]:
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright 不可用，无法渲染 Markdown")
        return None
    
    try:
        if ws_url and not await check_browser_health(ws_url):
            logger.warning("浏览器服务不可用")
            return None
        
        html_content = markdown_to_html(md_text)
        full_html = HTML_TEMPLATE.replace('{{content}}', html_content)
        
        browser_url = ws_url or os.getenv(
            "BROWSER_WS_URL", 
            "ws://browser:3000/chromium?launch={\"headless\":false}"
        )
        
        async with get_page(browser_url, viewport={"width": 800, "height": 600}) as page:
            await page.set_content(full_html, wait_until="networkidle")
            await page.wait_for_timeout(300)
            body_height = await page.evaluate('document.body.scrollHeight')
            await page.set_viewport_size({"width": 800, "height": body_height + 50})
            await page.wait_for_timeout(100)
            img_bytes = await page.screenshot(full_page=False, type="png")
            return img_bytes
            
    except Exception as e:
        logger.exception(f"渲染 Markdown 失败: {e}")
        return None


async def render_text_if_markdown(
    text: str,
    min_length: int = 100,
    ws_url: Optional[str] = None
) -> Optional[bytes]:
    if not text or len(text) < min_length:
        return None
    
    if not is_markdown(text):
        return None
    
    return await render_markdown_to_image(text, ws_url)
