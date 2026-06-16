---
name: manga_translate
description: 当用户要求翻译漫画、汉化漫画、嵌字时激活
---

# 漫画翻译重嵌

## 流程总览

```
/ocr → 每个文字区域的位置和原文
交叉验证 → 大模型看图复核原文
翻译 + 渲染参数 → 基于交叉验证后的原文
/inpaint_and_render → 成品
```

**核心原则：翻译基于本地OCR的精确原文。图像大模型辅助视觉判断（过滤误检、字体、颜色、方向）和交叉验证原文。**


## Step 1：检测并识别文字

```python
execute_script(skill_name="manga_translate",
  script_path="scripts/manga_service.py",
  args=["ocr", "--image", "<user_image_1>"])
```

返回每个文字区域的位置和原文：`{"success": true, "results": [{bbox_id, text, x, y, w, h, polygon}, ...]}`。

把返回的 results 保存为 bbox 文件，后续渲染要用：

```python
write_file(path="data/aichat/images/<session_id>/bboxes.json",
           content='<results JSON>')
```

## Step 2：大模型交叉验证

用多模态能力观察原图中每个 bbox 区域，也读一遍原文。结合本地OCR结果交叉验证：

- **一致** → 高置信，直接采用
- **差异小**（假名/汉字替换）→ 结合上下文选更合理者
- **差异大** → 大模型再细看一次，综合决定
- **本地空/大的有** → 互补采用

**最终得到经交叉验证的精确原文，用于翻译。**

## Step 3：分析 + 翻译

交叉验证后的精确原文 + 坐标 → 逐框决策：

### 3.1 过滤
以下情况**跳过**（不翻译、不擦除）：
- 原文为空或纯标点/符号（如装饰心形♥）
- 框内是logo、花纹、网点，不是文字

### 3.2 合并碎片
手写体/拟声词被切成多个框，用 `bbox_ids` 合并：
```json
{"bbox_id": 2, "bbox_ids": [2, 3, 4], "text": "合并译文", ...}
```

### 3.3 翻译
- 基于交叉验证后的精确原文
- **结合原图语境：** 观察画面场景、角色表情、对话气泡的形态，判断说话人的情绪和语气
- 对话翻译要口语化、符合角色性格（傲娇、吐槽、解释等），旁白/说明文保持正式
- 拟声词用合适的中文拟声
- 日文汉字适当转中文习惯用字

### 3.4 渲染参数

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `font` | 字体 | `sans`(黑体，对话默认) `heiti`(粗黑/微软雅黑，拟声词) `serif`(宋体，旁白/说明) |
| `color` | 文字色 | hex色值，对话框`#000000`，拟声词`#ff5588`等 |
| `direction` | 方向 | `auto`(自动) `horizontal`(横) `vertical`(竖) |
| `outline` | 描边 | 原文有白色描边就是`true` |
| `outline_color` | 描边色 | `#ffffff` |

**方向判断：** bbox 高 > 宽×1.5 → `vertical`，否则默认 `horizontal`

## Step 4：擦除 + 嵌字

把翻译结果和bbox都写入文件，调用渲染：

```python
write_file(path="data/aichat/images/<session_id>/translations.json",
           content='<翻译JSON>')

execute_script(skill_name="manga_translate",
  script_path="scripts/manga_service.py",
  args=["inpaint_render", "--image", "<user_image_1>",
        "--translations-file", "data/aichat/images/<session_id>/translations.json",
        "--bboxes-file", "data/aichat/images/<session_id>/bboxes.json"])
```

**translations.json 格式：**
```json
[
  {
    "bbox_id": 0,
    "text": "6月9日是69之日！（色情之日）",
    "font": "heiti",
    "color": "#000000",
    "direction": "horizontal",
    "outline": true,
    "outline_color": "#ffffff"
  },
  {
    "bbox_id": 2,
    "bbox_ids": [2, 3, 4],
    "text": "为了教大家69是啥需要实际演示一下",
    "font": "sans",
    "color": "#000000",
    "direction": "vertical",
    "outline": true,
    "outline_color": "#ffffff"
  }
]
```

**必须传入 bbox 数据（--bboxes-file），否则服务端重复检测可能不一致。**

## 回复用户

发送结果图片，简述处理情况。多页漫画逐页处理。
