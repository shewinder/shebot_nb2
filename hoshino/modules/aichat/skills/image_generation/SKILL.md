---
name: image_generation
description: 当用户要求画图、生图、编辑图片、改图、风格转换时激活
allowed-tools:
  - "execute_script"
user-invocable: true
disable-model_invocation: false
---

# 图像生成与编辑 SKILL

## 核心原则

**Prompt 调优由模型决定，不是由服务商/协议脚本决定。**

同一个模型无论通过哪个服务商调用，调优策略相同。协议脚本（gemini.py / openai.py / comfyui.py / atlascloud.py）只做 HTTP 协议转换，不修改 prompt。


## 模型选择策略

**用户明确指定优先。** 如果用户明确指定了供应商（如"用 Gemini 画"）、模型（如"用 seedream"）或提示词内容，以用户要求为准，不再覆盖或修改。

**默认优先使用本地 ComfyUI，不消耗 API 费用。** 仅在以下情况才使用付费模型：
- ComfyUI 暂不支持（如图像编辑）
- ComfyUI 不可用或报错

## 可用模型

| 模型 | 协议脚本 | Prompt 语言 | 特点 | 能力 | 内容审查 |
|------|---------|------------|------|------|----------|
| z_image_turbo | comfyui.py | **中文** | qwen CLIP 中文极强，8步采样快 | generate | 完全无审核 |
| bytedance/seedream-v4/edit | atlascloud.py | 中文 | 字节跳动 Seedream，质量高，提示词遵循好 | generate, edit | 几乎无审核 |
| gemini-3.1-flash-image-preview | gemini.py | **英文** | Google Gemini，速度快，理解力强 | generate, edit | 审核严格 |

## 工作流程

1. **判断场景**：是否涉及图像编辑？→ 选择合适的模型
2. **Prompt 调优**：按照所选模型的调优策略处理 prompt（语言、质量词、风格词等）
3. **调用脚本**：将调优后的 prompt 原样传入对应脚本

---

## 模型级调优策略

### gemini-3.1-flash-image-preview

**Prompt 语言**：英文

**调优方法**：
1. 将中文核心概念翻译为高质量英文
2. 附加英文质量词：`masterpiece, best quality, highly detailed`
3. 根据内容附加风格词（anime style / photorealistic / cyberpunk 等）
4. 重组为自然语言描述，而非标签列表

**调优示例**：
```
用户: "画一只可爱的橘猫在樱花树下"
AI 调优后: "A cute orange tabby cat sleeping under a cherry blossom tree,
            soft pink petals falling, warm sunlight filtering through branches,
            masterpiece, best quality, highly detailed, anime style"
```

---

### bytedance/seedream-v4/edit

**Prompt 语言**：**保留中文**

**调优方法**：
1. 保留用户原始中文描述（Seedream 中文理解优秀）
2. 补充中文质量词：`高清细节，精美画质，极致细腻`
3. 根据内容补充中文风格词：`电影级光影`，`治愈系画风`，`赛博朋克风格` 等
4. **不要翻译为英文**

**调优示例**：
```
用户: "一只可爱的橘猫在樱花树下睡觉"
AI 调优后: "高清细节，精美画质，一只可爱的橘猫在樱花树下睡觉，
            粉色花瓣飘落，温暖阳光透过树枝，治愈系画风"
```

---

### z_image_turbo

**Prompt 语言**：**保留中文**

**调优方法**：
1. 保留用户原始中文描述（qwen_3_4b CLIP 中文理解极强）
2. 补充中文质量词：`高清细节，精美画质`
3. 根据内容补充中文风格词：`治愈系画风`，`赛博朋克风格`，`油画质感` 等
4. **不要翻译为英文**

**调优示例**：
```
用户: "一只可爱的橘猫在樱花树下睡觉"
AI 调优后: "高清细节，精美画质，一只可爱的橘猫在樱花树下睡觉，
            粉色花瓣飘落，温暖阳光透过树枝，治愈系画风"
```

---

## 风格词速查表

调优时根据用户需求附加相应风格词（根据模型语言选择中英文）：

| 用户需求 | 英文风格词 | 中文风格词 |
|---------|-----------|-----------|
| 二次元/动漫 | `anime style, vibrant colors, cel shading` | `二次元画风，鲜艳色彩` |
| 写实/照片 | `photorealistic, 8k uhd, dslr` | `写实照片，超高清` |
| 赛博朋克 | `cyberpunk, neon lights, futuristic city` | `赛博朋克风格，霓虹灯光` |
| 油画 | `oil painting, brush strokes, classical art` | `油画质感，笔触纹理` |
| 像素风 | `pixel art, retro game style` | `像素风格，复古游戏` |
| 水彩 | `watercolor painting, soft edges` | `水彩画风，柔和边缘` |
| 素描 | `pencil sketch, monochrome` | `铅笔素描，黑白线条` |
| 治愈系 | `healing, warm atmosphere, soft lighting` | `治愈系画风，温暖氛围` |

---

## 图像编辑

当用户上传图片并要求修改时：

1. 从对话上下文中找到图片标识符（如 `<user_image_1>`，系统会在消息末尾附加可用图片列表）
2. 选择支持编辑的模型（gemini-3.1-flash-image-preview 或 bytedance/seedream-v4/edit）
3. 按模型调优策略处理编辑指令
4. 调用对应协议脚本：

```python
execute_script(
    skill_name="image_generation",
    script_path="scripts/gemini.py",  # 或 scripts/atlascloud.py
    args=["--prompt", "<调优后的prompt>", "--images", "<user_image_1>"]
)
```

### 当前可用图片查询

系统会在每条用户消息末尾附加【当前可用图片】列表：
```
<user_image_1> (user, png, 1024x1024)
<ai_image_1> (ai, jpg, 512x512)
```

---

## 协议脚本参数说明

所有协议脚本参数统一，prompt 必须是 AI 已经调优完成的：

- `--prompt` (必填): AI 调优后的 prompt，脚本原样透传给 API
- `--images` (可选): 待编辑图片标识符，逗号分隔
- `--aspect-ratio` (可选): `1:1`, `4:3`, `3:4`, `16:9`, `9:16`, `2:3`, `3:2`
- `--size` (可选): `512`, `1K`, `2K`, `4K`
- `--model` (必填): 模型名称（如 `gemini-3.1-flash-image-preview`、`z_image_turbo`、`bytedance/seedream-v4/edit`），脚本用此名称调用 API 和选择工作流

**通用调用示例**：
```python
execute_script(
    skill_name="image_generation",
    script_path="scripts/comfyui.py",  # 根据模型替换为 gemini.py / atlascloud.py / openai.py
    args=["--prompt", "<AI调优后的prompt>",
          "--aspect-ratio", "1:1",
          "--model", "z_image_turbo"]
)
```

### 尺寸与比例建议

| 内容类型 | 推荐比例 | 推荐尺寸 |
|---------|---------|---------|
| 人物肖像/立绘 | 3:4 或 2:3 | 1K ~ 2K |
| 风景/场景 | 16:9 或 4:3 | 2K ~ 4K |
| 头像/图标 | 1:1 | 512 ~ 1K |
| 手机壁纸 | 9:16 | 2K |

---

## 回复风格

- 引用生成的图片标识符：`已生成 <ai_image_1>`
- 简要说明使用的模型和风格特点
- 不要详细解释每一步做了什么
