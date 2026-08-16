---
name: pixiv_data
description: 当用户请求访问 Pixiv 数据、Pixiv 作品详情、PID 信息、Pixiv 日榜、R18日榜或排行榜原始数据时激活。使用项目内 shewinder Pixiv API 获取并整理数据。
---

# Pixiv 数据访问 SKILL

## 数据源

使用 `curl` 工具访问已知 API（url 参数直接带查询串，或按需使用 headers/data）。

| 场景 | URL |
|------|-----|
| 日榜 | `https://api.shewinder.win/pixiv/rank?date=YYYY-MM-DD&mode=day&num=60` |
| R18 日榜 | `https://api.shewinder.win/pixiv/rank?date=YYYY-MM-DD&mode=day_r18&num=60` |
| 作品详情 | `https://api.shewinder.win/pixiv/illust_detail?illust_id=PID` |

日榜数据默认查昨天日期。`pixivrank` 的定时更新在当天 18:30 后运行，是为了确保昨天榜单已稳定发布。

## 字段规范

Pixiv API 返回的是 Pixiv illust 结构。整理结果时按项目 `pixivrank` 的 `RankPic` 口径归一化：

| 输出字段 | 来源 |
|----------|------|
| `pid` | `id` |
| `title` | `title` |
| `author` | `user.name` |
| `author_id` | `user.id` |
| `page_count` | `page_count` |
| `tags` | `tags[].name` 与 `tags[].translated_name` 合并，过滤空值 |
| `urls` | 单页用 `meta_single_page.original_image_url`，多页用 `meta_pages[].image_urls.original` |
| `url` | `urls[0]` |

排行榜返回数组时只处理 `type == "illust"` 的项目；跳过漫画、动图或缺少原图 URL 的异常项。

## 图片 URL

API 返回的原图 URL 通常在 `i.pximg.net` 域名下。需要直接访问图片文件时，将域名替换为项目代理：

- `i.pximg.net` -> `pixiv.shewinder.win`
- 如果出现 `i.pixiv.re`，也替换为 `pixiv.shewinder.win`

## 调用示例

### 查询 PID 作品

1. 准备参数：`PID`。
2. 调用 `curl(url="https://api.shewinder.win/pixiv/illust_detail?illust_id=PID")`
3. 按字段规范整理标题、作者、标签、页数、收藏/浏览、图片 URL 等信息。

### 查询日榜

1. 准备参数：`date=YYYY-MM-DD`；默认使用昨天日期，当天榜单可能未稳定。
2. 准备模式：普通日榜用 `mode=day`，R18 用 `mode=day_r18`。
3. 调用 `curl` 获取 60 条。
4. 只保留 `type == "illust"`，按榜单顺序选前 N 张。
5. 按字段规范整理每个作品的数据。

## 数据约束

- 不要编造 API 没返回的标题、作者、标签、收藏数或浏览数。
- API 失败、返回空或字段缺失时，保留空值。
- R18 榜单仅使用 `mode=day_r18`，普通日榜仅使用 `mode=day`。
