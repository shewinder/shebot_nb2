# Playwright 浏览器自动化

本模块为 SheBot 提供浏览器自动化功能，通过 Docker 独立运行浏览器服务，无需在应用容器中安装浏览器。

## 架构说明

```
┌─────────────┐      WebSocket       ┌──────────────┐
│   shebot    │ ◄──────────────────► │  browserless │
│  (Playwright)│                     │    /chrome   │
│             │                      │   (Docker)   │
└─────────────┘                      └──────────────┘
```

- **shebot**：Playwright Python 客户端，通过 WebSocket 连接远程浏览器
- **browserless/chrome**：独立的 Chrome 浏览器服务，通过 Docker 运行

## 快速开始

### 1. 启动服务

```bash
# 复制并编辑配置
cp docker-compose.yml.example docker-compose.yml

# 启动所有服务
docker-compose up -d
```

### 2. 验证浏览器服务

```bash
# 检查浏览器健康状态
curl http://localhost:3003/health

# 预期返回: {"status":"healthy","chrome":true,"playwright":true}
```

### 3. 在代码中使用

```python
from hoshino.util.playwright_util import screenshot

# 截取网页
img_bytes = await screenshot("https://example.com", full_page=True)
```

## API 参考

### 便捷函数

#### `screenshot(url, selector=None, full_page=False, ws_url=DEFAULT_BROWSER_WS_URL, wait_for=None)`

截取网页或指定元素。

```python
from hoshino.util.playwright_util import screenshot

# 截取整个页面
img_bytes = await screenshot("https://example.com", full_page=True)

# 截取特定元素
img_bytes = await screenshot(
    "https://example.com",
    selector="#content",
    wait_for=".loaded"  # 等待元素出现
)
```

#### `fetch_page_content(url, wait_for=None, evaluate=None, ws_url=DEFAULT_BROWSER_WS_URL)`

获取网页内容或执行 JavaScript。

```python
from hoshino.util.playwright_util import fetch_page_content

# 获取渲染后的 HTML
html = await fetch_page_content("https://spa-example.com")

# 执行 JavaScript 获取特定内容
text = await fetch_page_content(
    "https://example.com",
    evaluate="document.querySelector('.content').innerText"
)
```

### 上下文管理器

#### `get_page(ws_url=DEFAULT_BROWSER_WS_URL, timeout=DEFAULT_TIMEOUT, viewport=None)`

自动管理页面生命周期的上下文管理器。

```python
from hoshino.util.playwright_util import get_page

async with get_page() as page:
    await page.goto("https://example.com")
    
    # 点击元素
    await page.click("#button")
    
    # 填写表单
    await page.fill("#input", "value")
    
    # 截图
    img_bytes = await page.screenshot()
```

### PlaywrightClient 类

更灵活的控制方式，支持复用浏览器会话。

```python
from hoshino.util.playwright_util import PlaywrightClient

client = PlaywrightClient()

# 连接浏览器
await client.connect()

# 创建页面
page = await client.new_page()

# 使用页面
await page.goto("https://example.com")
img_bytes = await page.screenshot()

# 关闭连接
await client.close()
```

或使用 async with：

```python
async with PlaywrightClient() as client:
    page = await client.new_page()
    await page.goto("https://example.com")
```

## 配置选项

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `BROWSER_WS_URL` | `ws://browser:3000/chromium?launch={"headless":false}` | 浏览器 WebSocket 地址 |

### Docker Compose 配置

```yaml
browser:
  image: browserless/chrome:latest
  environment:
    - MAX_CONCURRENT_SESSIONS=5      # 最大并发会话数
    - CONNECTION_TIMEOUT=300000      # 连接超时（毫秒）
    - MAX_IDLE_TIME=60000            # 空闲超时（毫秒）
    - DEFAULT_HEADLESS=false         # 默认无头模式
    - ENABLE_DEBUG_VIEWER=true       # 启用调试界面
```

## 使用场景示例

### 场景 1：网页截图

```python
from io import BytesIO
from nonebot.adapters.onebot.v11 import MessageSegment
from hoshino.util.playwright_util import screenshot

@sv.on_prefix('截图')
async def capture(bot, event):
    url = event.get_plaintext().replace('截图', '').strip()
    img_bytes = await screenshot(url, full_page=True)
    await bot.send(event, MessageSegment.image(BytesIO(img_bytes)))
```

### 场景 2：抓取动态内容

```python
from hoshino.util.playwright_util import get_page

async def fetch_dynamic_content(url):
    async with get_page() as page:
        await page.goto(url)
        
        # 等待 AJAX 加载完成
        await page.wait_for_selector(".content-loaded")
        
        # 提取内容
        content = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('.item'))
                .map(el => el.textContent);
        }''')
        
        return content
```

### 场景 3：表单自动填写

```python
from hoshino.util.playwright_util import get_page

async def auto_login(url, username, password):
    async with get_page() as page:
        await page.goto(url)
        
        # 填写表单
        await page.fill('input[name="username"]', username)
        await page.fill('input[name="password"]', password)
        
        # 点击登录
        await page.click('button[type="submit"]')
        
        # 等待登录成功
        await page.wait_for_url("**/dashboard**")
        
        # 获取登录后的 Cookie
        cookies = await page.context.cookies()
        return cookies
```

## 调试

### 访问调试界面

浏览器服务提供 Playwright 调试界面：

```
http://localhost:3003
```

### 查看浏览器日志

```bash
# 查看浏览器容器日志
docker-compose logs -f browser
```

### 本地开发时连接远程浏览器

如果你本地开发时需要连接 Docker 中的浏览器：

```python
import os

# 覆盖默认地址
os.environ['BROWSER_WS_URL'] = 'ws://localhost:3003/chromium?launch={"headless":false}'

from hoshino.util.playwright_util import screenshot

img_bytes = await screenshot("https://example.com")
```

## 故障排除

### 连接超时

检查浏览器服务是否正常运行：

```bash
docker-compose ps browser
curl http://localhost:3003/health
```

### 内存不足

增加 browser 服务的内存限制：

```yaml
browser:
  deploy:
    resources:
      limits:
        memory: 2G
      reservations:
        memory: 512M
```

### 页面加载失败

可能是网站反爬虫机制，尝试：

```python
async with get_page() as page:
    # 设置更真实的 User-Agent
    await page.set_extra_http_headers({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...'
    })
    await page.goto(url)
```

## 参考资料

- [Playwright 文档](https://playwright.dev/python/)
- [Browserless 文档](https://docs.browserless.io/)
- [Playwright 最佳实践](https://playwright.dev/python/docs/best-practices)
