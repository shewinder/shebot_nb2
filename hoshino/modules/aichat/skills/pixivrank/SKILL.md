---
name: pixivrank
description: 获取 Pixiv 日榜图片并发送给用户
allowed-tools:
  - "fetch_url"
  - "send_images"
  - "read_file"
user-invocable: true
disable-model_invocation: false
---

# Pixiv 日榜 SKILL

## 功能

- 获取 Pixiv 日榜（普通/R18）
- 自动优化推荐（根据用户画像默默筛选，不在回复中提及）
- 直接发送图片到聊天

## API

**日榜接口**：`https://api.shewinder.win/pixiv/rank?date=YYYY-MM-DD&mode=day&num=N`

参数：
- `date`: 昨天日期（YYYY-MM-DD）
- `mode`: `day` 或 `day_r18`
- `num`: 获取数量（推荐 30，用于过滤）

**图片域名替换**：`i.pximg.net` → `pixiv.shewinder.win`

## 工作流程

1. `read_file` 读取用户画像（路径：`aichat/preferences/{user_id}.md`）
2. `fetch_url` 获取日榜（num=30）
3. 根据画像筛选作品（不在回复中说明筛选过程）
4. 选择 5-6 张发送

**匹配逻辑**：
- 作品的 `tags` 数组与用户的偏好标签匹配越多，优先级越高
- 包含用户回避标签的作品直接排除
- 可参考 `total_bookmarks`（收藏数）作为质量参考

**如果用户画像不存在或为空**：
- 直接发送热门作品（前 6 张）

## 场景 1：普通日榜

用户说："看看日榜"、"P站排行"

执行：获取日榜并优化推荐，直接展示作品

回复示例：
```
📅 2026-04-06 Pixiv 日榜

1. 🎨 作品标题1 <ai_image_1>
   👤 作者：作者名1

2. 🎨 作品标题2 <ai_image_2>
   👤 作者：作者名2

...
```

## 场景 2：R18 日榜

用户说："R18 榜"

执行：
1. `fetch_url` 获取 `mode=day_r18` 数据
2. 应用用户画像过滤（不提及）

## 注意事项

- 图片 URL 必须替换为 `pixiv.shewinder.win`
- `send_images` 返回 `<ai_image_N>`，在回复中引用
- **回复中不要提及"根据喜好筛选"、"个性化推荐"等字样**，默默进行即可
- 无画像时发送默认热门作品
