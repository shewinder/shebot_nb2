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

### 工作准则

**⚠️ 重要：未经明确指令，不要执行 `git commit`**

- 只有用户明确说 "commit" 或 "提交" 时才执行代码提交
- 完成代码修改后，等待用户确认再提交
- 不要在用户未要求的情况下主动提交代码

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
- ❌ `for x: Type in iterable:` - Python 不支持在 for 语句中给循环变量加类型注解，会导致 `SyntaxError`

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

**类型注解（Typing）：**
- 函数参数和返回值必须添加类型注解
- 变量推导类型不清晰时添加注解（如 `state.get()` 返回值）
- 容器类型使用泛型：`List[str]`, `Dict[str, int]`, `Optional[Model]`
- ❌ 禁止 `for x: Type in iterable:` 语法错误

```python
from typing import List, Optional, Dict, Tuple

def get_models(api: str) -> List[str]:
    models: List[str] = state.get('models', [])
    target: Optional[str] = None
    return models
```

**交互式命令（多步对话）：**
使用 `got` 方法实现等待用户输入：

```python
from hoshino.typing import T_State

cmd = sv.on_command('选择')

@cmd.handle()
async def handle(bot: Bot, event: Event, state: T_State):
    await cmd.send("请发送选项序号")
    # 可选：预存数据到 state
    state['options'] = ['a', 'b', 'c']

@cmd.got('choice', prompt='请发送序号')  # 参数名 + 提示语
async def got_choice(bot: Bot, event: Event, state: T_State):
    choice = str(state['choice']).strip()
    if choice == '取消':
        await cmd.finish("已取消")
    options: List[str] = state.get('options', [])
    # 处理选择...
```

**NoneBot 异常处理：**
- `FinishedException` - 调用 `matcher.finish()` 后抛出，用于结束命令流程，**不是错误**
- 不要在 `except Exception` 中记录 `FinishedException` 为错误

```python
from nonebot.exception import FinishedException

try:
    await matcher.finish("消息")  # 会抛出 FinishedException
except FinishedException:
    raise  # 重新抛出，正常流程
except Exception as e:
    logger.error(f"真正错误: {e}")
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
