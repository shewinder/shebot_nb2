# PT 下载助手 Skill

搜索 PT 站资源并控制 qBittorrent 下载的 AI Skill。

## 功能

- 🔍 多 PT 站资源搜索
- 📊 智能排序推荐（按做种数、大小等）
- ⬇️ 一键添加 qBittorrent 下载
- 📋 查看下载进度

## 安装

### 1. 安装依赖

```bash
uv pip install aiohttp beautifulsoup4
```

### 2. 配置

**首次运行会自动生成配置文件到 `data/config/ptdownload.json`**

只需编辑该文件，填写你的 **Cookie** 和 **qBittorrent 密码** 即可。

#### 默认生成的配置

```json
{
  "qbittorrent": {
    "enabled": false,
    "base_url": "http://localhost:8080",
    "username": "admin",
    "password": "",
    "verify_ssl": false
  },
  "pt_stations": [
    {
      "name": "北洋园",
      "enabled": true,
      "headers": {
        "Cookie": "在此填写你的北洋园 Cookie"
      }
    },
    {
      "name": "馒头",
      "enabled": false,
      "headers": {
        "Cookie": "在此填写你的馒头 Cookie"
      }
    }
  ]
}
```

#### 如何获取 Cookie

1. 登录 PT 站
2. F12 打开开发者工具 → Network 标签
3. 刷新页面，点击任意请求 → 复制 Cookie 值
4. 粘贴到配置文件的 `"Cookie": "..."` 处

### 3. 添加其他 PT 站

如需添加未内置的站点，在 `pt_stations` 数组中添加完整配置：

```json
{
  "name": "站点名称",
  "enabled": true,
  "search_url": "https://xxx.com/torrents.php?search={keyword}",
  "search_method": "get",
  "headers": {
    "Cookie": "your_cookie"
  },
  "result_selector": "table.torrents tr",
  "field_mapping": {
    "title": "a[href*='details.php']",
    "download": "a[href*='download.php']",
    "size": "td:nth-child(5)",
    "seeders": "td:nth-child(6)"
  }
}
```

## 使用

激活 Skill 后，AI 会自动处理：

```
你：#使用 pt-download
AI：✅ SKILL 'pt-download' 已激活

你：我想看肖申克的救赎
AI：🔍 搜索到 5 个资源：
    1. The.Shawshank.Redemption... (15.2GB) | 做种: 23 | 来源: 北洋园 ⭐
    2. ...
    
    回复序号下载

你：1
AI：✅ 已添加下载任务
    📁 资源: The.Shawshank.Redemption...
    📂 保存路径: /downloads/movies

你：查看下载进度
AI：📥 qBittorrent 任务列表...
```

## 手动测试脚本

```bash
# 搜索
python hoshino/modules/aichat/skills/ptdownload/scripts/pt_search.py "肖申克的救赎"

# 查看列表
python hoshino/modules/aichat/skills/ptdownload/scripts/qb_list.py
```

## ⚠️ 重要提示

**`data/config/ptdownload.json` 包含你的 Cookie 和密码，不要提交到 git！**

该文件已在 `.gitignore` 中排除。

## 故障排查

### 搜索不到结果

- 检查 Cookie 是否过期
- 检查站点是否启用（`enabled: true`）

### 添加下载失败

- 检查 qBittorrent Web UI 是否开启
- 检查用户名密码是否正确
- 设置 `"verify_ssl": false`（局域网推荐）
