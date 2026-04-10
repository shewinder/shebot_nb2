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

**配置文件位置：`data/config/ptdownload.json`**

首次使用时会自动生成默认配置，或手动创建：

```bash
cp hoshino/modules/interactive/aichat/skills/ptdownload/config.json.example \
   data/config/ptdownload.json
```

然后编辑 `data/config/ptdownload.json`：

#### qBittorrent 配置

```json
"qbittorrent": {
  "enabled": true,
  "base_url": "http://你的qb地址:8080",
  "username": "admin",
  "password": "你的密码",
  "default_save_path": "/downloads/movies",
  "verify_ssl": false
}
```

#### PT 站配置

```json
{
  "name": "站点名称",
  "enabled": true,
  "search_url": "https://xxx.com/torrents.php?search={keyword}",
  "search_method": "get",
  "headers": {
    "Cookie": "your_cookie_here"
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

### 如何获取 Cookie

1. 登录 PT 站
2. F12 打开开发者工具
3. 刷新页面，任意请求 → 请求头 → 复制 Cookie

### 如何选择器调试

1. 打开 PT 站搜索页面
2. F12 → Elements 标签
3. 右键搜索结果行 → Copy → Copy selector
4. 调整字段映射选择器

## 使用

激活 Skill 后，AI 会自动处理：

```
你：#使用 pt-download
AI：✅ SKILL 'pt-download' 已激活

你：我想看肖申克的救赎
AI：🔍 搜索到 5 个资源：
    1. The.Shawshank.Redemption... (15.2GB) | 做种: 23 | 来源: 馒头 ⭐
    2. ...
    
    回复序号下载

你：1
AI：✅ 已添加下载任务
    📁 The.Shawshank.Redemption...
    📂 保存路径: /downloads/movies

你：查看下载进度
AI：📥 qBittorrent 任务列表...
```

## 手动测试脚本

```bash
cd hoshino/modules/interactive/aichat/skills/ptdownload

# 搜索
python scripts/pt_search.py "肖申克的救赎"

# 添加下载（根据序号）
python scripts/qb_add.py --index 1

# 添加下载（直接链接）
python scripts/qb_add.py --url "magnet:?xt=urn:btih:..."

# 查看列表
python scripts/qb_list.py
```

## 文件说明

```
ptdownload/                         # 内置 Skill 目录
├── SKILL.md                        # AI 指导文档（git 跟踪）
├── README.md                       # 本文件（git 跟踪）
├── config.json.example             # 配置示例（git 跟踪）
├── config.py                       # 配置读取模块（git 跟踪）
├── _meta.json                      # Skill 元数据（git 跟踪）
├── .last_search.json               # 上次搜索结果缓存（自动生成）
└── scripts/                        # 执行脚本（git 跟踪）
    ├── pt_search.py
    ├── qb_add.py
    └── qb_list.py

data/config/ptdownload.json         # 用户配置（不在 git 中）
```

## ⚠️ 重要提示

**`data/config/ptdownload.json` 包含你的 Cookie 和密码，不要提交到 git！**

该文件已在 `.gitignore` 中排除（如果没有请添加）：

```gitignore
# PT Download Skill 用户配置
data/config/ptdownload.json
```

## 故障排查

### 搜索不到结果

- 检查 Cookie 是否过期
- 检查 `result_selector` 是否正确
- 检查 `field_mapping` 字段映射

### 添加下载失败

- 检查 qBittorrent Web UI 是否开启
- 检查用户名密码是否正确
- 检查 `base_url` 是否可以访问
- 检查防火墙是否阻止端口

### SSL 证书错误

设置 `"verify_ssl": false`（局域网推荐）
