# SheBot - AI 智能体指南

## 项目运行方式

### 本地开发

```bash
# 1. 安装依赖（使用 uv）
uv sync

# 2. 配置环境
cp .env.prod.example .env.prod
# 编辑 .env.prod 设置 superusers, web_password 等

# 3. 运行机器人
uv run python run.py

# 4. 构建 Web 仪表板（可选）
cd web && npm install && npm run build
```

### Docker 部署

```bash
cp docker-compose.yml.example docker-compose.yml
# 编辑 docker-compose.yml
docker-compose up -d
```

### 配置说明

```ini
# .env.prod 关键配置
superusers=[123456]           # 超级用户 QQ 号
nickname=["镜华"]             # 机器人昵称
modules=["infopush", "entertainment", "setu", ...]  # 加载的模块
web_password=shebot           # Web 管理面板密码
```

---

## 项目规范

### 核心原则：先查现有代码

**在编写任何新代码前，必须先研究项目中已有的代码实践。**

```bash
# 查看命令定义方式
grep -r "sv.on_" hoshino/modules/ | head -20

# 查看 logger 用法
grep -r "sv.logger" hoshino/modules/ | head -10

# 查看 Service 定义
grep -r "Service(" hoshino/modules/ | head -10
```

**常见陷阱：**
- ❌ `from nonebot import on_prefix` - 本项目可能无此接口
- ❌ `log.new_logger()` - 本项目使用 `sv.logger`
- ❌ 臆造参数如 `manage_perm=0` - 应使用 `permission.py` 常量
- ❌ 假设通用 NoneBot2 文档完全适用 - 本项目有额外封装

### 服务模式标准写法

```python
from hoshino import Service, Bot, Event

sv = Service('服务名', help_='帮助文本')

cmd = sv.on_command('命令名', aliases={'别名'}, only_group=False)

@cmd.handle()
async def handler(bot: Bot, event: Event):
    sv.logger.info('日志信息')  # 正确：用 sv.logger
    await bot.send(event, '回复内容')
```

**可用方法：**
- `sv.on_command(name, aliases=set(), only_group=True)`
- `sv.on_startswith(msg)` / `sv.on_endswith(msg)`
- `sv.on_regex(pattern)` / `sv.on_keyword(keywords)`
- `sv.on_message()` / `sv.on_notice()` / `sv.on_request()`

### 配置模式

```python
from hoshino.config import BaseConfig, configuration

@configuration('plugin_name')
class Config(BaseConfig):
    daily_max_num: int = 10

# 读取配置
from hoshino.config import get_plugin_config_by_name
conf = get_plugin_config_by_name('plugin_name')
```

### 资源访问

```python
from hoshino import R

img_path = R.img('subdir', 'image.png')       # 路径字符串
font_path = R.font('msyh.ttf')                # 字体路径
```

### 代码风格

- **文档字符串**：使用中文
- **文件头**：包含作者信息
  ```python
  '''
  Author: YourName
  Date: 2024-01-01
  Description: 简要描述
  Github: http://github.com/yourname/
  '''
  ```
- **导入顺序**：标准库 → 第三方 → 本地
- **异步**：处理器必须是 async 函数

### 权限常量

```python
from hoshino.permission import ADMIN, NORMAL, SUPERUSER

# ADMIN = SUPERUSER | GROUP_ADMIN | GROUP_OWNER
# 服务管理至少需要 ADMIN 权限
```

---

## 项目经验

### 模块开发经验

**加载机制：**
- `hoshino/base/` - 基础模块，始终加载
- `hoshino/modules/` - 功能模块，按 `.env.prod` 中 `modules` 配置加载

**配置热更新：**
```python
from hoshino.config import save_plugin_config
save_plugin_config("aichat", conf)  # 保存后立即生效
```

### Playwright 浏览器自动化

```python
from hoshino.util.playwright_util import screenshot, get_page

# 基础截图
img_bytes = await screenshot("https://example.com", full_page=True)

# 高级操作
async with get_page() as page:
    await page.goto("https://example.com")
    await page.click("#btn")
    img_bytes = await page.screenshot()
```

**部署注意：**
- 浏览器镜像约 2GB，首次拉取较慢
- 建议分配至少 1GB 内存
- 调试界面：`http://localhost:3003`

### Web 仪表板开发

```bash
# 构建方式
cd web
npm run build
```
