# SheBot (HoshinoBot) - AI Agent Guide

## Project Overview

**SheBot** (also known as `hinata`) is a QQ chat bot based on [NoneBot2](https://github.com/nonebot/nonebot2) framework. It's a modified version of [hoshino.nb2](https://github.com/AkiraXie/hoshino.nb2), designed for QQ group management and entertainment features.

The bot connects to QQ via OneBot protocol (through LLOneBot) and provides various services including image search, live streaming notifications, Bilibili video parsing, meme generation, and more.

### Key Features
- **Service Management**: Modular service system with per-group enable/disable control
- **Web Dashboard**: React-based management console for bot monitoring and configuration
- **Information Push**: Live streaming (Bilibili/Douyu) and video upload notifications
- **Entertainment**: Image search, meme generation, games (Wordle, Handle), and more
- **Group Management**: Anti-recall, anti-flash image, welcome messages, broadcast

## Technology Stack

### Backend
- **Python**: 3.11+ (required)
- **Framework**: NoneBot2 (async Python bot framework)
- **Protocol**: OneBot v11 (via `nonebot-adapter-onebot`)
- **Web Server**: FastAPI (embedded in NoneBot2)
- **Database**: SQLite (via Peewee ORM)
- **Image Processing**: Pillow (PIL), OpenCV
- **HTTP Client**: aiohttp, httpx

### Frontend (Web Dashboard)
- **Framework**: React 18 + Vite
- **UI Library**: Ant Design 5
- **Routing**: React Router v6
- **HTTP Client**: Axios

### Deployment
- **Container**: Docker + Docker Compose
- **Process Manager**: LLOneBot (QQ protocol implementation)
- **Package Manager**: uv (modern Python package manager)

## Project Structure

```
.
├── hoshino/                    # Main bot framework
│   ├── __init__.py            # Framework initialization, exports core classes
│   ├── config.py              # Plugin configuration system (Pydantic-based)
│   ├── service.py             # Core Service class for feature management
│   ├── matcher.py             # Event matcher wrappers
│   ├── event.py               # Event type definitions
│   ├── message.py             # Message utilities
│   ├── log.py                 # Logging configuration
│   ├── permission.py          # Permission definitions (ADMIN, SUPERUSER, etc.)
│   ├── res.py                 # Resource helper (R object for images/fonts)
│   ├── schedule.py            # Scheduled job utilities
│   ├── base/                  # Base plugins (always loaded)
│   │   ├── service_manage/    # Service enable/disable commands
│   │   ├── nlcmd/             # Natural language command processing
│   │   ├── black/             # Blacklist management
│   │   ├── help.py            # Help command
│   │   ├── zai.py             # "在？" response
│   │   └── ...
│   ├── modules/               # Feature modules (selectively loaded)
│   │   ├── setu/              # Image search features
│   │   ├── entertainment/     # Games and fun features
│   │   ├── infopush/          # Live stream & video notifications
│   │   ├── tools/             # Utility tools (translation, OCR, etc.)
│   │   ├── groupmanage/       # Group management features
│   │   ├── interactive/       # Interactive chat features
│   │   ├── pixiv/             # Pixiv integration
│   │   └── web/               # Web dashboard API
│   └── util/                  # Utility functions
├── web/                       # React web dashboard
│   ├── src/                   # React source code
│   ├── package.json           # NPM dependencies
│   └── vite.config.js         # Vite configuration
├── data/                      # Runtime data (SQLite DB, configs)
├── res/                       # Static resources (fonts, images)
├── static/                    # Built web dashboard files
├── logs/                      # Log files (rotated daily)
├── run.py                     # Application entry point
├── pyproject.toml             # Python dependencies and project metadata
├── Dockerfile                 # Docker build for production
└── docker-compose.yml.example # Docker Compose example
```

## Configuration

### Environment Variables (`.env`)
```ini
ENVIRONMENT=prod           # Environment: prod/dev
DRIVER=~fastapi           # NoneBot driver
PORT=9003                 # Web dashboard port (NoneBot runs on different port)
NICKNAME=["hinata"]       # Bot nickname
```

### Production Config (`.env.prod`)
```ini
host=0.0.0.0              # Bot listening IP
port=9000                 # Bot HTTP API port
debug=false               # Debug mode (DO NOT enable in production)
superusers=[123456]       # Superuser QQ numbers
nickname=["镜华"]         # Bot nickname in Chinese
command_start=["/", ""]   # Command prefixes
modules=["information", "entertainment", "setu", "groupmanage", "tools"]
data=data                 # Data directory
static=static             # Static resources directory
```

## Build and Run

### Local Development

1. **Install Dependencies (using uv)**
   ```bash
   uv sync
   ```

2. **Configure Environment**
   ```bash
   cp .env.prod.example .env.prod
   # Edit .env.prod with your settings
   ```

3. **Run the Bot**
   ```bash
   uv run python run.py
   ```

4. **Build Web Dashboard (optional)**
   ```bash
   cd web
   npm install
   npm run build
   cd ..
   # Or use the provided script
   ./build_web.sh
   ```

### Docker Deployment

1. **Build and Run with Docker Compose**
   ```bash
   # Copy and edit compose file
   cp docker-compose.yml.example docker-compose.yml
   # Edit docker-compose.yml with your settings
   docker-compose up -d
   ```

2. **Services in Compose**
   - `shebot`: The bot application (port 9000)
   - `llonebot`: LLOneBot for QQ protocol (ports 3000, 3001, 5600, 3080)

## Code Style and Conventions

### Python Code Style
- **Docstrings**: Use Chinese for comments and docstrings
- **File Header**: Each file should have author info header:
  ```python
  '''
  Author: AkiraXie
  Date: 2021-01-28 00:44:32
  Description: Brief description
  Github: http://github.com/AkiraXie/
  '''
  ```
- **Imports**: Group imports (stdlib, third-party, local)
- **Type Hints**: Use typing annotations where appropriate
- **Async**: Most bot handlers are async functions

### Service Pattern
Each feature is implemented as a `Service`:

```python
from hoshino import Service, Bot, Event

# Define service
sv = Service('服务名', help_='帮助文本', manage_perm=ADMIN)

# Define command handler
@sv.on_regex(r'正则表达式')
async def handler(bot: Bot, event: Event, state: T_State):
    await bot.send(event, '回复内容')
```

### Configuration Pattern
Use Pydantic-based config with decorator:

```python
from hoshino.config import BaseConfig, configuration

@configuration('plugin_name')
class Config(BaseConfig):
    daily_max_num: int = 10
    enable_r18: bool = False

# Access config
from hoshino.config import get_plugin_config_by_name
conf = get_plugin_config_by_name('plugin_name')
```

### Resource Access
Use the `R` object for accessing resources:

```python
from hoshino import R

# Access images
img_path = R.img('subdir', 'image.png')  # Returns path string
img_seg = R.img('subdir', 'image.png').open()  # Returns MessageSegment

# Access fonts
font_path = R.font('msyh.ttf')
```

## Testing

There is no formal test suite in this project. Testing is done manually:

1. Run the bot locally
2. Connect to a test QQ group
3. Send commands and verify responses

For web dashboard testing:
```bash
cd web
npm run dev  # Development server with hot reload
```

## Security Considerations

1. **Superuser Configuration**: Set `superusers` in `.env.prod` to your QQ number
2. **Access Token**: Configure `access_token` for go-cqhttp/LLOneBot connection
3. **Web Dashboard Auth**: Default login is QQ number as both username and password
   - JWT-based authentication (implementation in `hoshino/modules/web/`)
   - Token validation middleware can be enabled in `app.py`
4. **R18 Content**: Controlled by `check_r18()` function, disabled by default in groups
5. **Rate Limiting**: Services use `FreqLimiter` and `DailyNumberLimiter` for abuse prevention

## Module Loading

Modules are loaded based on `modules` config in `.env.prod`:

```python
# In run.py
moduledir = 'hoshino/modules/'
base = 'hoshino/base/'

# Base modules (always loaded)
nonebot.load_plugins(base)

# Configured modules
if modules := config.modules:
    for module in modules:
        module = os.path.join(moduledir, module)
        nonebot.load_plugins(module)
```

### Available Module Categories
- `information`: Info push (live streams, video uploads)
- `entertainment`: Games and fun features
- `setu`: Image search
- `groupmanage`: Group management
- `tools`: Utility tools

## Web Dashboard

The web dashboard provides:
- **Dashboard**: Bot status, group list, plugin info
- **Service Management**: Enable/disable services per group
- **Config Management**: Edit plugin configurations
- **Log Monitoring**: Real-time log viewing via WebSocket

### API Endpoints
- `/login` - Authentication
- `/api/bot/*` - Bot management APIs
- `/api/infopush/*` - Info push management
- `/ws` - WebSocket for real-time logs

### Development Mode
```bash
cd web
npm run dev
# Access http://localhost:3000
# API requests proxy to http://localhost:9002
```

## Troubleshooting

1. **Port Conflicts**: Ensure ports 9000 (bot), 9002/9003 (web), 3000 (dev) are available
2. **QQ Connection**: Verify LLOneBot is properly configured and connected
3. **Web UI Not Built**: Run `npm run build` in `web/` directory if `static/index.html` is missing
4. **Permission Denied**: Check file permissions for `data/` and `logs/` directories

## References

- [NoneBot2 Documentation](https://nonebot.dev/)
- [OneBot Protocol](https://github.com/botuniverse/onebot-11)
- [LLOneBot](https://github.com/LLOneBot/LLOneBot)
- [HoshinoBot (Original)](https://github.com/Ice-Cirno/HoshinoBot)
