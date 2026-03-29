# Playwright MCP 使用说明

Playwright MCP 是一个基于 MCP (Model Context Protocol) 的浏览器自动化服务器，让 AI 能够控制浏览器进行网页操作。

## 部署方式

### Docker Compose（唯一支持方式）

项目已在 `docker-compose.yml` 中配置好 Playwright MCP 服务：

```yaml
playwright-mcp:
  image: mcr.microsoft.com/playwright/mcp:latest
  container_name: playwright-mcp
  restart: always
  ports:
    - "8931:8931"
  command: ["node", "cli.js", "--headless", "--browser", "chromium", "--no-sandbox", "--port", "8931"]
  networks:
    - bot-network
```

启动服务：
```bash
docker-compose up -d playwright-mcp
```

### 配置

在 `data/config/aichat.json` 中添加 MCP 配置：

```json
{
  "enable_mcp": true,
  "mcp_servers": [
    {
      "id": "playwright",
      "name": "浏览器自动化",
      "transport": "sse",
      "url": "http://playwright-mcp:8931/sse",
      "enabled": true
    }
  ]
}
```

**注意**：当前仅支持 `sse` 传输方式，用于连接 Docker 部署的 MCP 服务。

## 可用工具

连接成功后，AI 可以使用以下浏览器工具：

| 工具名 | 功能 |
|--------|------|
| `browser_navigate` | 导航到指定 URL |
| `browser_click` | 点击页面元素 |
| `browser_fill` | 填写表单输入 |
| `browser_type` | 在元素中输入文本 |
| `browser_select` | 选择下拉框选项 |
| `browser_hover` | 鼠标悬停 |
| `browser_screenshot` | 截图 |
| `browser_get_text` | 获取页面文本 |
| `browser_evaluate` | 执行 JavaScript |

## 使用示例

部署完成后，用户可以直接对 AI 说：

```
#帮我打开 https://example.com 并截图
```

```
#搜索 "Python教程"，打开第一个结果
```

```
#访问这个链接，提取其中的主要内容
```

## 管理命令

超级用户可以使用以下命令管理 MCP：

- `MCP列表` - 查看所有 MCP server 状态
- `MCP工具` - 列出所有可用工具
- `MCP重启 playwright` - 重启 Playwright MCP 服务

## 注意事项

1. **无头模式**：Docker 版本的 Playwright MCP 仅支持无头模式（headless），无法显示浏览器界面
2. **资源占用**：浏览器自动化需要较多内存，建议至少分配 1GB
3. **网络访问**：确保容器可以访问目标网站
4. **并发限制**：单个 Playwright MCP 实例同时只能处理一个会话

## 故障排查

### 连接失败

检查服务是否运行：
```bash
docker-compose ps playwright-mcp
docker-compose logs playwright-mcp
```

### 工具调用失败

使用 `MCP重启 playwright` 命令重启服务。

### 网页访问失败

检查网络连接：
```bash
docker exec playwright-mcp curl -I https://example.com
```
