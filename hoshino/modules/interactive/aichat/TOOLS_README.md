# AI Chat Tool/Function Calling 功能说明

## 概述

aichat 模块现已支持标准的 OpenAI Tool/Function Calling 功能，让 AI 模型可以主动调用外部工具（如生成图片、搜索网页等）来完成用户请求。

## 配置方法

### 1. 启用 Tool Calling

在 `data/config/aichat.json` 中，为支持 Tool Calling 的模型添加 `supports_tools: true`：

```json
{
  "apis": [
    {
      "id": "grok",
      "name": "Grok-4.1",
      "api_base": "https://api.example.com/v1",
      "api_key": "your-api-key",
      "model": "grok-4.1",
      "supports_multimodal": true,
      "supports_tools": true
    }
  ]
}
```

### 2. 支持的模型

- **Grok-4.1** (通过 Sorux API 或其他兼容 OpenAI API 的提供商)
- **GPT-4/GPT-4o** (OpenAI)
- **Claude 3** (Anthropic)
- 其他支持 OpenAI 格式 Tools API 的模型

## 使用方法

### 方式一：自然语言触发（需要模型支持 Tool Calling）

当模型配置 `supports_tools: true` 时，AI 会自动识别需要工具的场景：

```
用户: #帮我画一只在月球上跳舞的兔子
AI: 🎨 正在为您生成图片...
[图片]
这是一只在月球表面欢快跳舞的兔子，背景是星空和地球。
```

### 方式二：直接命令（无需模型支持 Tool Calling）

使用 `生图` 命令直接调用图片生成：

```
生图 一只可爱的猫咪在草地上打滚
生图 赛博朋克风格的城市夜景 1024x1792
```

## 可用工具

### 1. generate_image - 图片生成

根据文本描述生成图片。

**参数：**
- `prompt` (必填): 图片描述
- `size`: 图片尺寸，可选 `1024x1024` (方形), `1024x1792` (竖屏), `1792x1024` (横屏)
- `quality`: 质量，可选 `standard` (标准) 或 `hd` (高清)
- `n`: 生成数量，1-4

**示例：**
```
#画一只在海边看日出的金毛犬
#生成一张科幻风格的城市图片，尺寸1024x1792
```

### 2. web_search - 网页搜索（预留）

搜索网页获取实时信息（暂未实现）。

## 技术细节

### 工具调用流程

1. 用户发送消息
2. 系统检测模型是否支持 Tool Calling
3. 如支持，在 API 调用时传入 `tools` 参数
4. 模型决定是否需要调用工具
5. 如需调用，系统执行工具函数并返回结果
6. 模型根据工具结果生成最终回复
7. 支持多轮工具调用（最多 5 轮）

### 图片生成服务

默认使用 **Pollinations.ai** 免费服务：
- 无需 API Key
- 无调用次数限制
- 支持自定义尺寸和种子

URL 格式：`https://image.pollinations.ai/prompt/{prompt}?width={w}&height={h}&seed={n}&nologo=true`

## 故障排除

### 模型不调用工具

1. 检查 `supports_tools` 是否设置为 `true`
2. 使用更明确的提示词，如"请使用生图工具..."
3. 部分模型可能需要在 system prompt 中启用工具

### 图片生成失败

1. 检查网络连接
2. Pollinations.ai 可能偶尔超时，可重试
3. 查看日志中的错误信息

### 工具调用循环

系统已设置最大工具调用轮数（5轮），防止无限循环。

## 扩展开发

### 添加新工具

在 `tools.py` 中添加：

```python
# 1. 在 TOOLS_SCHEMA 中添加工具定义
{
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "工具描述",
        "parameters": {...}
    }
}

# 2. 实现工具函数
async def my_tool(param: str) -> Dict[str, Any]:
    return {"success": True, "result": "..."}

# 3. 注册工具
TOOL_FUNCTIONS["my_tool"] = my_tool
```
