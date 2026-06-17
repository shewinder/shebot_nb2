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

返回 `{"success": true, "results": [...], "data_id": "abc123"}`。**记住 data_id，Step 4 要用。**

## Step 2：交叉验证

**⚠️ 纯文本模型（如 DeepSeek）不具备多模态能力，禁止假装看图。**

优先级：

1. **有多模态能力** → 直接观察原图，交叉验证
2. **纯文本模型 → delegate_task type="vision"** → 把原图和 bbox 列表发给 vision subagent，让它做画面描述 + 原文复核 + 样式记录
3. **vision subagent 不可用 → 跳过交叉验证** → 直接用本地OCR结果

**无论哪种方式，多模态模型必须同时完成两件事：**

1. **描述画面** — 场景、角色表情、动作、情绪氛围、对话气泡的形态。这是翻译时判断语气的关键语境
2. **复核原文** — 逐框对比本地OCR结果，纠正可能的错误
3. **记录样式** — 每框文字的颜色（hex）、是否有描边、字体粗细。这是 Step 3 渲染参数的依据

交叉验证规则：
- **一致** → 高置信，直接采用
- **差异小**（假名/汉字替换）→ 结合上下文选更合理者
- **差异大** → 再细看一次，综合决定

## Step 3：分析 + 翻译

交叉验证后的精确原文 + 坐标 → 逐框决策：

### 3.1 过滤
以下情况**跳过**（不翻译、不擦除）：
- 原文为空或纯标点/符号（如装饰心形♥）
- 框内是logo、花纹、网点，不是文字

### 3.2 合并碎片
**竖排相邻的框如果 OCR 文本能连成一句话，必须合并成一个 translation**，否则单独渲染每框字太小。用 `bbox_ids` 合并：
```json
{"bbox_id": 2, "bbox_ids": [2, 3, 4, 5], "text": "Ruby在演艺圈迅速走红", ...}
```
横排框如果重叠也合并。单字/拟声词不需要合并。

### 3.3 翻译
- 基于交叉验证后的精确原文
- **结合 Step 2 的画面描述：** 场景情绪、角色表情、动作氛围决定每句台词的语气和措辞
- 对话口语化、符合角色性格（傲娇、吐槽、慌张、冷漠等），旁白/说明文保持正式
- 拟声词用合适的中文拟声
- 日文汉字适当转中文习惯用字
- **禁止使用 emoji/特殊符号（❤️♡♪☆等）**——嵌字字体渲染效果差，用中文拟声词或标点代替

**标点与符号保留规则：**
- 全角数字（１０：２３）→ 保留不译，或转半角数字（10:23）
- 省略号（．．．）→ 保留为 …
- 纯标点/数字/时间的文字区域 → 跳过，不擦除也不嵌入

### 3.4 渲染参数

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `font` | 字体 | `sans`(黑体，对话默认) `heiti`(粗黑/微软雅黑，拟声词) `serif`(宋体，旁白/说明) |
| `color` | 文字色 | **以原图文字颜色为准**，不要随意改色。对话框通常是黑色，拟声词/效果音常有特殊颜色 |
| `direction` | 方向 | `auto`(自动) `horizontal`(横) `vertical`(竖) |
| `outline` | 描边 | 原文有白色描边就是`true` |
| `outline_color` | 描边色 | `#ffffff` |

**方向判断：** bbox 高 > 宽×1.5 → `vertical`，否则默认 `horizontal`

## Step 4：擦除 + 嵌字

```python
execute_script(skill_name="manga_translate",
  script_path="scripts/manga_service.py",
  args=["inpaint_render", "--image", "<user_image_1>",
        "--data-id", "<Step 1 的 data_id>",
        "--translations", '<翻译JSON字符串>'])
```

**translations.json 格式：**
```json
[
  {
    "bbox_id": 0,
    "text": "翻译后的中文文本",
    "font": "sans",
    "color": "#000000",
    "direction": "horizontal",
    "outline": true,
    "outline_color": "#ffffff"
  },
  {
    "bbox_id": 2,
    "bbox_ids": [2, 3],
    "text": "合并多个碎片的译文",
    "font": "heiti",
    "color": "#ff5588",
    "direction": "vertical",
    "outline": false,
    "outline_color": "#ffffff"
  }
]
```

## 回复用户

发送结果图片，简述处理情况。多页漫画逐页处理。
