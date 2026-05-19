# PixivRank Vision 筛选设计

## 背景

当前 AI 筛选（`ai_filter.py`）只传文本元数据（PID、标题、作者、标签）给 AI，AI 看不到图片本身。用户画像中包含视觉偏好（如"冷色调构图"），但 AI 无从判断哪些图片匹配。图片下载、base64 转换、多模态 API 调用等基础设施已存在于 `__init__.py`（隐式偏好更新），但未接入筛选环节。

## 目标

用 vision 模型替代纯文本筛选，让 AI 直接看图做审美判断，提升日榜推送质量。

## 方案：合并多用户 + 分批

每个群一次筛选流程：

```
60 张图 → 按 vision_batch_size 分片（默认 10×6）→ 每批并行 {
  下载该批图片 → base64
  构造 multimodal prompt：所有用户画像 + 图片
  调用 vision API → 每个用户选出 vision_select_per_user 张
} → 汇总投票排序 → 取前 15 张 → 不足则随机补齐
```

核心优势：
- 每批一次调用内完成所有用户的筛选，不随用户数增长
- 批次并行执行，总耗时 = 单次调用 + 下载
- 降级链路完整：vision 失败 → 文本筛选 → 随机

## 配置新增（config.py）

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `vision_filter_enabled` | `true` | 视觉筛选总开关，关闭走纯文本 |
| `vision_api_base` | `https://api.gemini.com` | Vision API 地址 |
| `vision_api_key` | `""` | Vision API Key |
| `vision_model` | `gemini-2.5-flash` | 模型名 |
| `vision_batch_size` | `10` | 每批图片数 |
| `vision_select_per_user` | `4` | 每批每用户最多选几张 |

## 新文件：vision_filter.py

位置：`hoshino/modules/pixiv/pixivrank/vision_filter.py`

三个函数：
- `_download_image(url) -> Optional[str]` — 下载图片转 base64 data URL，复用现有逻辑
- `call_vision_batch(images_b64, user_prefs, config) -> Optional[dict]` — 单批调用，构造 multimodal prompt，解析 JSON 返回 `{user_idx: [pid, ...]}`
- `vision_filter_images(images, user_prefs, config) -> (selected_pids, vote_details)` — 编排入口，分批、并行下载、并行调用、汇总排序

API 调用格式：直接 httpx POST，content 为 `[text, image_url, image_url, ...]` 数组，不依赖 aichat 链路。

## 修改：data_source.py

`filter_rank_ai()` 中，在基础过滤和读取画像之后，插入：

```python
if conf.vision_filter_enabled and conf.vision_api_key and user_prefs:
    selected_pids, vote_details = await vision_filter_images(...)
elif conf.ai_filter_enabled and conf.ai_api_key and user_prefs:
    selected_pids, vote_details, _ = await ai_filter_images_multi_user(...)
else:
    selected_pids = None
```

后续投票排序、随机补齐逻辑不变。

## 不改的文件

- `ai_filter.py` — 保留作为 fallback
- `__init__.py` — 不变

## 降级链路

```
vision_filter_enabled && vision_api_key 已配
  → 调用 vision_filter_images()
    → 某批下载失败：该图不参与此批，后续可被随机补齐
    → 某批 API 失败：此批结果为空，其他批继续
    → 全部批失败：降级到 ai_filter_images_multi_user()
      → 文本筛选也失败：随机补齐
  → 无画像用户：跳过，直接随机补齐
```

## 候选图不足时

- 候选图 < target_count(15)：全部保留，不补齐
- 候选图 < vision_batch_size(10)：只发 1 批，包含所有候选图
- 画像用户 > 8：按 max_users=8 截取（复用现有逻辑）

## API 成本估算

以默认配置（每批 10 张，6 批并行，gemini-2.5-flash）：
- 单次调用：~15K token（10 张图 + 画像文本）
- 6 批总计：~90K token
- 用户数不影响调用次数
