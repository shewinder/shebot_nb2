# SheBot (HoshinoBot) - AI 智能体指南

## 项目概述

**SheBot**（也称为 `hinata`）是一个基于 [NoneBot2](https://github.com/nonebot/nonebot2) 框架的 QQ 聊天机器人。它是 [hoshino.nb2](https://github.com/AkiraXie/hoshino.nb2) 的修改版本，专为 QQ 群管理和娱乐功能而设计。

该机器人通过 OneBot 协议（通过 LLOneBot）连接 QQ，提供各种服务，包括图片搜索、直播通知、Bilibili 视频解析、表情包生成、游戏（Wordle、Handle）等。

### 主要特性
- **服务管理**：模块化服务系统，支持按群组启用/禁用控制
- **Web 仪表板**：基于 React 的管理控制台，用于机器人监控和配置
- **信息推送**：直播（Bilibili/斗鱼）和视频上传通知
- **娱乐功能**：图片搜索、表情包生成、游戏等
- **群管理**：防撤回、防闪照、欢迎消息、广播

## 技术栈

### 后端
- **Python**: 3.11+（必需）
- **框架**: NoneBot2（异步 Python 机器人框架）
- **协议**: OneBot v11（通过 `nonebot-adapter-onebot`）
- **Web 服务器**: FastAPI（内置于 NoneBot2）
- **数据库**: SQLite（通过 Peewee ORM）
- **图像处理**: Pillow (PIL)、OpenCV
- **HTTP 客户端**: aiohttp、httpx、curl_cffi
- **任务调度**: APScheduler（通过 `nonebot-plugin-apscheduler`）
- **认证**: PyJWT

### 前端（Web 仪表板）
- **框架**: React 18 + Vite
- **UI 库**: Ant Design 5
- **路由**: React Router v6
- **HTTP 客户端**: Axios

### 部署
- **容器**: Docker + Docker Compose
- **进程管理器**: LLOneBot（QQ 协议实现）
- **包管理器**: uv（现代 Python 包管理器）

## 项目结构

```
.
├── hoshino/                    # 机器人主框架
│   ├── __init__.py            # 框架初始化，导出核心类
│   ├── config.py              # 插件配置系统（基于 Pydantic）
│   ├── service.py             # 用于功能管理的核心 Service 类
│   ├── matcher.py             # 事件匹配器包装器
│   ├── event.py               # 事件类型定义
│   ├── message.py             # 消息工具
│   ├── log.py                 # 日志配置
│   ├── permission.py          # 权限定义（ADMIN、SUPERUSER 等）
│   ├── res.py                 # 资源助手（用于图片/字体的 R 对象）
│   ├── schedule.py            # 定时任务工具
│   ├── base/                  # 基础插件（始终加载）
│   │   ├── service_manage/    # 服务启用/禁用命令
│   │   ├── nlcmd/             # 自然语言命令处理
│   │   ├── black/             # 黑名单管理
│   │   ├── help.py            # 帮助命令
│   │   ├── zai.py             # "在？" 响应
│   │   └── ...
│   ├── modules/               # 功能模块（选择性加载）
│   │   ├── setu/              # 图片搜索功能
│   │   ├── entertainment/     # 游戏和娱乐功能
│   │   ├── infopush/          # 直播和视频通知
│   │   ├── tools/             # 实用工具（翻译、OCR 等）
│   │   ├── groupmanage/       # 群管理功能
│   │   ├── interactive/       # 交互式聊天功能
│   │   ├── pixiv/             # Pixiv 集成
│   │   └── webui/             # Web 仪表板 API
│   └── util/                  # 工具函数
├── web/                       # React Web 仪表板
│   ├── src/                   # React 源代码
│   ├── package.json           # NPM 依赖
│   └── vite.config.js         # Vite 配置
├── data/                      # 运行时数据（SQLite 数据库、配置）
│   ├── db/                    # 数据库文件
│   ├── service/               # 服务启用/禁用状态
│   └── config/                # 插件配置（JSON）
├── res/                       # 静态资源（字体、图片）
│   └── fonts/                 # 字体文件
├── static/                    # 构建后的 Web 仪表板文件
├── logs/                      # 日志文件（按天轮替）
├── run.py                     # 应用程序入口
├── pyproject.toml             # Python 依赖和项目元数据
├── Dockerfile                 # Docker 生产构建
└── docker-compose.yml.example # Docker Compose 示例
```

## 配置

### 环境变量（`.env`）
```ini
ENVIRONMENT=prod           # 环境：prod/dev
DRIVER=~fastapi           # NoneBot 驱动
PORT=9003                 # Web 仪表板端口（NoneBot 运行在不同端口）
NICKNAME=["hinata"]       # 机器人昵称
```

### 生产配置（`.env.prod`）
```ini
host=0.0.0.0              # 机器人监听 IP
port=9000                 # 机器人 HTTP API 端口
debug=false               # 调试模式（生产环境请勿启用）
superusers=[123456]       # 超级用户 QQ 号
nickname=["镜华"]         # 机器人中文昵称
command_start=["/", ""]   # 命令前缀
modules=["infopush", "entertainment", "setu", "groupmanage", "tools", "interactive", "pixiv", "webui"]
data=data                 # 数据目录
static=static             # 静态资源目录
web_password=shebot       # Web 仪表板密码
```

## 构建和运行

### 本地开发

1. **安装依赖（使用 uv）**
   ```bash
   uv sync
   ```

2. **配置环境**
   ```bash
   cp .env.prod.example .env.prod
   # 使用您的设置编辑 .env.prod
   ```

3. **运行机器人**
   ```bash
   uv run python run.py
   ```

4. **构建 Web 仪表板（可选）**
   ```bash
   cd web
   npm install
   npm run build
   cd ..
   # 或使用提供的脚本
   ./build_web.sh
   ```

### Docker 部署

1. **使用 Docker Compose 构建和运行**
   ```bash
   # 复制并编辑 compose 文件
   cp docker-compose.yml.example docker-compose.yml
   # 使用您的设置编辑 docker-compose.yml
   docker-compose up -d
   ```

2. **Compose 中的服务**
   - `shebot`：机器人应用程序（端口 9000）
   - `llonebot`：用于 QQ 协议的 LLOneBot（端口 3000、3001、5600、3080）

## 代码风格和约定

### Python 代码风格
- **文档字符串**：注释和文档字符串使用中文
- **文件头**：每个文件应包含作者信息头：
  ```python
  '''
  Author: AkiraXie
  Date: 2021-01-28 00:44:32
  Description: 简要描述
  Github: http://github.com/AkiraXie/
  '''
  ```
- **导入**：分组导入（标准库、第三方、本地）
- **类型提示**：在适当的地方使用类型注解
- **异步**：大多数机器人处理器是异步函数

### 服务模式
每个功能都实现为一个 `Service`：

```python
from hoshino import Service, Bot, Event
from hoshino.typing import T_State

# 定义服务
sv = Service('服务名', help_='帮助文本', manage_perm=ADMIN)

# 定义命令处理器
@sv.on_regex(r'正则表达式')
async def handler(bot: Bot, event: Event, state: T_State):
    await bot.send(event, '回复内容')
```

### 配置模式
使用基于 Pydantic 的配置和装饰器：

```python
from hoshino.config import BaseConfig, configuration

@configuration('plugin_name')
class Config(BaseConfig):
    daily_max_num: int = 10
    enable_r18: bool = False

# 访问配置
from hoshino.config import get_plugin_config_by_name
conf = get_plugin_config_by_name('plugin_name')
```

### 资源访问
使用 `R` 对象访问资源：

```python
from hoshino import R

# 访问图片
img_path = R.img('subdir', 'image.png')  # 返回路径字符串
img_seg = R.img('subdir', 'image.png').open()  # 返回 PIL Image

# 访问字体
font_path = R.font('msyh.ttf')
```

## 模块加载

模块根据 `.env.prod` 中的 `modules` 配置加载：

```python
# 在 run.py 中
moduledir = 'hoshino/modules/'
base = 'hoshino/base/'

# 基础模块（始终加载）
nonebot.load_plugins(base)

# 配置的模块
if modules := config.modules:
    for module in modules:
        module = os.path.join(moduledir, module)
        nonebot.load_plugins(module)
```

### 可用模块类别
- `infopush`：信息推送（直播、视频上传）
- `entertainment`：游戏和娱乐功能
- `setu`：图片搜索
- `groupmanage`：群管理
- `tools`：实用工具
- `interactive`：交互式聊天
- `pixiv`：Pixiv 集成
- `webui`：Web 仪表板 API

## Web 仪表板

Web 仪表板提供：
- **仪表板**：机器人状态、群组列表、插件信息
- **服务管理**：按群组启用/禁用服务
- **配置管理**：编辑插件配置
- **日志监控**：通过 WebSocket 实时查看日志

### API 端点
- `/api/login` - 认证
- `/api/bot/*` - 机器人管理 API
- `/api/infopush/*` - 信息推送管理
- `/ws` - 用于实时日志的 WebSocket

### 开发模式
```bash
cd web
npm run dev
# 访问 http://localhost:3000
# API 请求代理到 http://localhost:9002
```

## 测试

本项目没有正式的测试套件。测试是手动完成的：

1. 在本地运行机器人
2. 连接到测试 QQ 群
3. 发送命令并验证响应

对于 Web 仪表板测试：
```bash
cd web
npm run dev  # 带热重载的开发服务器
```

## 安全注意事项

1. **超级用户配置**：在 `.env.prod` 中将 `superusers` 设置为您的 QQ 号
2. **访问令牌**：配置 `access_token` 用于 go-cqhttp/LLOneBot 连接
3. **Web 仪表板认证**：默认登录密码通过 `.env.prod` 中的 `web_password` 配置
   - 基于 JWT 的认证（实现在 `hoshino/modules/webui/` 中）
   - `app.py` 中的令牌验证中间件
4. **R18 内容**：由 `check_r18()` 函数控制，默认在群组中禁用
5. **速率限制**：服务使用 `FreqLimiter` 和 `DailyNumberLimiter` 防止滥用

## 权限系统

权限在 `hoshino/permission.py` 中定义：

- `SUPERUSER`：机器人超级用户（来自配置）
- `ADMIN`：SUPERUSER | GROUP_ADMIN | GROUP_OWNER
- `OWNER`：SUPERUSER | GROUP_OWNER
- `NORMAL`：SUPERUSER | GROUP | PRIVATE

服务管理至少需要 `ADMIN` 权限。

## 日志

日志通过 `loguru` 管理，具有以下功能：
- 带颜色的控制台输出（开发环境 DEBUG 级别，生产环境 INFO 级别）
- `logs/` 目录中按天轮替的日志文件
- 单独的日志文件
- 通过 `wrap_logger` 实现服务特定的日志记录器

## 故障排除

1. **端口冲突**：确保端口 9000（机器人）、9002/9003（Web）、3000（开发）可用
2. **QQ 连接**：验证 LLOneBot 是否正确配置和连接
3. **Web UI 未构建**：如果缺少 `static/index.html`，请在 `web/` 目录中运行 `npm run build`
4. **权限被拒绝**：检查 `data/` 和 `logs/` 目录的文件权限

## 参考资料

- [NoneBot2 文档](https://nonebot.dev/)
- [OneBot 协议](https://github.com/botuniverse/onebot-11)
- [LLOneBot](https://github.com/LLOneBot/LLOneBot)
- [HoshinoBot (原版)](https://github.com/Ice-Cirno/HoshinoBot)
