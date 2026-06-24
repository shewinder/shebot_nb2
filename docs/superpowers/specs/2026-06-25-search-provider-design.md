# Web Search Provider 插件化设计

## 概述

将 `web_search` 工具从硬编码的单一搜索后端改为插件化的 Provider 架构，支持通过配置热切换搜索提供商，切换时 AI 看到精准匹配当前 Provider 的参数 schema。

## 核心设计

### Provider 协议

每个搜索后端封装为 `search_providers/` 下的一个模块，暴露统一的接口：

```python
# search_providers/<name>.py

PROVIDER = {
    "name": "youcom",              # 唯一标识
    "label": "You.com",            # 人类可读名称
    "description": "...",          # AI tool description
    "parameters": {...},           # JSON Schema，仅声明本 provider 支持的参数
}

async def tool_fn(query, **params) -> ToolResult:
    """完整的 tool 实现：读 env → 调 API → 格式化 → 返回 ok/fail"""
    ...
```

### 热切换

```
/set search_provider <name>
        │
        ▼
switch_provider(name)
        ├─ config.search_provider = name
        ├─ save_plugin_config("aichat", config)         ← 持久化到文件
        └─ tool_registry.register("web_search", ...)(provider.tool_fn)  ← 覆盖注册
        │
        ▼
下一轮 AI 请求 → get_schemas() → 新 provider 的 schema
```

切换时把 provider 的 `tool_fn` 直接注册到 `web_search` 名下。AI 调 `web_search` 就是调 `youcom.tool_fn` 或 `iqs.tool_fn`，零中间层。

### 配置持久化

复用现有 `@configuration('aichat')` 体系，在 `Config` 中新增字段：

```python
class Config(BaseConfig):
    search_provider: str = "youcom"
```

配置存储在 `config/aichat.json`，通过 `save_plugin_config()` 持久化，跨重启保留。

## 文件结构

```
aichat/tools/builtin/
├── web_search.py              # 启动注册入口（~15行）
└── search_providers/
    ├── __init__.py             # _PROVIDERS 注册表 + switch_provider()
    ├── youcom.py               # You.com Search API 实现
    └── iqs.py                  # 阿里云百炼 IQS 实现
```

## 各模块职责

### registry.py (新增 1 个方法)

ToolRegistry 已支持同名覆盖注册，无需新增方法。Hot-switch 时直接 `register("web_search", ...)` 即可，行为等价于覆盖。

### config.py (新增 1 个字段)

```python
search_provider: str = "youcom"
```

### search_providers/__init__.py

```python
from . import youcom, iqs

_PROVIDERS = {"youcom": youcom.PROVIDER, "iqs": iqs.PROVIDER}

def get_provider(name: str) -> dict | None
def list_providers() -> list[str]

async def switch_provider(name: str) -> bool:
    # 1. 拿到 provider
    # 2. 持久化 config.search_provider
    # 3. tool_registry.register("web_search", ...)(provider.tool_fn)
```

### web_search.py

启动时读取 `config.search_provider`，用对应 provider 注册 `web_search` 工具。仅此而已，不参与运行时分发。

## 扩展新 Provider

只需两步：

1. 新建 `search_providers/brave.py`，实现 `PROVIDER` + `tool_fn`
2. 在 `__init__.py` 的 `_PROVIDERS` 中加一行

## 变更清单

| 文件 | 操作 |
|------|------|
| `registry.py` | 无需改动（覆盖注册已是现有行为） |
| `config.py` | `Config` + `search_provider: str = "youcom"` |
| `search_providers/__init__.py` | 新建，注册表 + switch_provider |
| `search_providers/youcom.py` | 新建，从 web_search.py 拆出 You.com 逻辑 |
| `search_providers/iqs.py` | 新建，从 web_search.py 拆出 IQS 逻辑 |
| `web_search.py` | 简化为启动注册入口（~15行） |
