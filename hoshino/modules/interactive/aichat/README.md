# AI Chat 插件

支持以 `#` 开头的消息触发AI对话，支持session管理。

## 功能特性

- ✅ 以 `#` 开头的消息自动触发AI对话
- ✅ Session管理：每个用户/群组独立的对话历史
- ✅ 支持持久化存储，重启后对话历史不丢失
- ✅ 支持Session超时自动清理
- ✅ 支持手动清除对话历史

## 配置说明

配置文件位置：`data/config/aichat.json`

```json
{
  "api_base": "https://api.openai.com/v1",
  "api_key": "your-api-key-here",
  "model": "gpt-3.5-turbo",
  "max_history": 10,
  "session_timeout": 3600,
  "max_tokens": 1000,
  "temperature": 0.7
}
```

### 配置项说明

- `api_base`: AI API的基础URL，支持OpenAI兼容的API
- `api_key`: API密钥
- `model`: 使用的模型名称
- `max_history`: 每个session保存的最大历史消息数（对话轮数）
- `session_timeout`: Session超时时间（秒），0表示永不过期
- `max_tokens`: 最大生成token数
- `temperature`: 温度参数，控制回复的随机性（0-1）

## 使用方法

### 基本使用

在群聊或私聊中发送以 `#` 开头的消息即可触发AI对话：

```
# 你好，介绍一下你自己
```

### 清除对话历史

使用以下命令清除当前对话历史：

```
清除对话
清空对话
重置对话
```

## Session管理

- **群聊Session**: 每个用户在每个群组有独立的对话历史
- **私聊Session**: 每个用户有独立的私聊对话历史
- **自动清理**: 超过 `session_timeout` 时间的Session会自动清理
- **持久化**: Session数据保存在 `data/aichat_sessions.json`

## 支持的API

本插件支持所有OpenAI兼容的API，包括但不限于：

- OpenAI官方API
- Azure OpenAI
- 其他OpenAI兼容的API服务

只需修改配置文件中的 `api_base` 和 `api_key` 即可。

## 注意事项

1. 首次使用前需要在配置文件中设置 `api_key`
2. Session数据会持久化保存，重启后不会丢失
3. 建议根据API服务的限制合理设置 `max_tokens` 和 `max_history`
