---
name: pixivrank
description: 获取 Pixiv 每日排行榜图片，支持直接发送图片到聊天
allowed-tools:
  - "fetch_url"
  - "send_images"
  - "web_search"
user-invocable: true
disable-model-invocation: false
---

# Pixiv 日榜 SKILL

## 功能

帮助用户查看 Pixiv 每日排行榜：
- 获取普通日榜（day）
- 获取 R18 日榜（day_r18）
- **直接发送图片到聊天**（使用 `send_images` 工具）
- 根据用户偏好进行简单推荐

**✅ 本 SKILL 支持直接发送图片，无需用户点击链接查看！**

## API 接口（激活后立即阅读此部分）

### ⚠️⚠️⚠️ 关键提醒
**必须使用以下指定的 API 地址：**
- ✅ **正确**: `https://api.shewinder.win/pixiv/...`
- ❌ **错误**: `https://api.pixivic.com/...` (不要用！)
- ❌ **错误**: 其他任何 Pixiv API

### 1. 获取排行榜列表

**API URL 模板**：
```
https://api.shewinder.win/pixiv/rank?date={date}&mode={mode}&num=60
```

**实际调用示例**（替换为实际日期）：
```
https://api.shewinder.win/pixiv/rank?date=2024-01-15&mode=day&num=60
```

参数：
- `date`: 日期格式 `YYYY-MM-DD`，通常使用昨天日期
- `mode`: 排行榜类型
  - `day` - 普通日榜
  - `day_r18` - R18 日榜
- `num`: 获取数量，默认 60

返回：JSON 数组，每个元素包含：
- `id`: 作品 PID
- `title`: 标题
- `user.name`: 作者名
- `user.id`: 作者 ID
- `tags`: 标签数组
- `page_count`: 图片张数
- `urls`: 图片 URL 数组（替换域名使用）

### 2. 获取作品详情

**API URL 模板**：
```
https://api.shewinder.win/pixiv/illust_detail?illust_id={pid}
```

**实际调用示例**：
```
https://api.shewinder.win/pixiv/illust_detail?illust_id=12345678
```

返回单个作品的详细信息。

## 图片域名替换

API 返回的图片 URL 域名是 `i.pximg.net`，直接访问会被拒绝。
需要将域名替换为 `pixiv.shewinder.win` 才能正常访问：

```
原 URL: https://i.pximg.net/img-original/img/2024/01/01/00/00/00/12345678_p0.png
替换后: https://pixiv.shewinder.win/img-original/img/2024/01/01/00/00/00/12345678_p0.png
```

## 使用方法

### 场景 1：用户请求查看日榜（直接发送图片）

用户说："看看今天的 Pixiv 日榜"、"P 站今天有什么图"

执行步骤：
1. 计算昨天的日期（格式：YYYY-MM-DD）
2. **使用 `fetch_url` 调用 API（必须是 api.shewinder.win，建议 num=5-8 避免数据过大）：**
   ```
   fetch_url("https://api.shewinder.win/pixiv/rank?date=YYYY-MM-DD&mode=day&num=6")
   ```
3. 取前 6 个作品
4. **重要：将图片 URL 域名从 `i.pximg.net` 替换为 `pixiv.shewinder.win`**
5. **使用 `send_images` 工具下载并发送图片（关键步骤）：**
   ```python
   send_images(urls=[
       "https://pixiv.shewinder.win/xxx_p0.png",  # 第1张
       "https://pixiv.shewinder.win/xxx_p0.png",  # 第2张
       ...
   ])
   ```
6. 工具返回标识符（如 `<ai_image_1>`）
7. **在回复中包含标识符**，用户就能看到图片

示例输出格式：
```
📅 Pixiv 日榜（2024-01-15）- 前6名

1. 🎨 作品标题1
   👤 作者：作者名1 <ai_image_1>

2. 🎨 作品标题2
   👤 作者：作者名2 <ai_image_2>

...

💡 发送 "pr{数字}" 查看指定排名的详情
```

**✅ 关键：必须先调用 `send_images` 下载图片，然后在回复中包含返回的标识符！**

### 场景 2：用户请求查看指定排名的原图（直接发送图片）

用户说："pr3"、"第3张"、"看下第5名"

执行步骤：
1. 提取数字 N
2. 如果之前已经获取过日榜数据，从缓存中取第 N 个作品的 PID
3. 如果没有缓存，重新获取日榜
4. **使用 `fetch_url` 调用 API：**
   ```
   fetch_url("https://api.shewinder.win/pixiv/illust_detail?illust_id=12345678")
   ```
5. **重要：将图片 URL 域名从 `i.pximg.net` 替换为 `pixiv.shewinder.win`**
6. **使用 `send_images` 下载图片：**
   ```python
   send_images(urls=["https://pixiv.shewinder.win/xxx_p0.png"])
   ```
7. 工具返回 `<ai_image_1>`
8. 回复作品信息 + 标识符，如："🎨 作品标题 <ai_image_1>"

### 场景 3：用户请求 R18 日榜

用户说："R18 榜"、"成人榜"

执行步骤：
1. 获取 `mode=day_r18` 的数据
2. 其他步骤同普通日榜
3. ⚠️ 注意：R18 内容需要确保在适当的群组/私聊环境下展示

### 场景 4：用户根据标签/作者搜索偏好

用户说："推荐点二次元图"、"有初音未来的图吗"

执行步骤：
1. 获取日榜数据
2. 根据用户关键词匹配标签
3. 筛选匹配的作品优先展示
4. 如果没有完全匹配的，展示热门作品并说明

## 交互示例（含图片发送）

**示例 1：获取普通日榜（直接发图片）**
```
用户：看看今天的 P 站日榜

AI 执行：
1. fetch_url 获取数据
2. send_images(urls=[6个图片URL]) → 返回 <ai_image_1> 到 <ai_image_6>

AI 回复：
📅 Pixiv 日榜（2024-01-15）- 前6名

1. 🎨 じいさんばあさん若返る <ai_image_1>
   👤 作者：新挑限

2. 🎨 作品标题2 <ai_image_2>
   👤 作者：作者名2

3. 🎨 作品标题3 <ai_image_3>
   👤 作者：作者名3

...

💡 发送 "pr数字" 查看详情
```

**结果：用户直接看到 6 张图片**

---

**示例 2：获取指定作品**
```
用户：pr3

AI 执行：
1. fetch_url 获取作品详情
2. send_images(urls=["https://pixiv.shewinder.win/xxx_p0.png"])
   → 返回 <ai_image_1>

AI 回复：
🎨 作品标题 <ai_image_1>
👤 作者：作者名
🏷️ 标签：tag1, tag2
📄 页数：3 张
```

**结果：用户直接看到作品图片**

## 注意事项（必读）

1. **🚨 API 地址（关键）：**
   - **正确**: `https://api.shewinder.win/pixiv/rank?date=...`
   - **错误**: `https://api.pixivic.com/...` ❌ 已确认无法访问！
   - **每次调用 fetch_url 前，务必检查 URL 是否以 `api.shewinder.win` 开头**

2. **🖼️ 发送图片的正确流程（重要）：**
   - 第1步：获取图片 URL（替换域名后）
   - 第2步：**调用 `send_images(urls=[...])` 下载图片**
   - 第3步：**工具返回标识符（如 `<ai_image_1>`）**
   - 第4步：**在你的回复中包含这些标识符**，用户才能看到图片
   - ❌ 错误：直接发送 URL 链接
   - ✅ 正确：使用 `send_images` 工具

3. **域名替换**：API 返回的图片 URL 域名是 `i.pximg.net`，**必须替换为 `pixiv.shewinder.win`**

4. **数量限制**：`send_images` 一次最多 10 张图片，建议日榜展示 5-8 张

5. **多图作品**：`page_count > 1` 时，`urls` 数组包含多张图片

6. **R18 内容**：获取 R18 榜前请确认当前环境适合展示

7. **缓存复用**：同一会话内获取日榜后可以缓存结果，方便后续 pr 查询

## 日期计算参考

Python 代码参考：
```python
from datetime import datetime, timedelta
yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
```

AI 可以使用当前时间工具获取昨天日期。
