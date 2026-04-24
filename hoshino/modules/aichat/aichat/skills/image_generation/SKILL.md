---
name: image_generation
description: 当用户要求画图、生图、编辑图片、改图、风格转换时激活
allowed-tools:
  - "execute_script"
user-invocable: true
disable-model_invocation: false
---

# 图像生成与编辑 SKILL


## 模型选择策略

**用户明确指定优先。** 如果用户明确指定了供应商（如"用 Gemini 画"）、模型（如"用 seedream"）或提示词内容，以用户要求为准，不再覆盖或修改。

**默认优先使用本地 ComfyUI。** 仅在以下情况才使用其他模型：
- ComfyUI 暂不支持（如图像编辑）
- ComfyUI 不可用或报错

**二次元/动漫场景优先使用 WAI-illustrious 或 novaAnimeXL_ilV180。** 两者均为 SDXL 动漫专用，角色还原度和二次元质量显著优于通用模型。但 **不支持写实/真人场景**，当用户要求写实照片、真人肖像等时，不用这两个模型。

**Cosplay 场景**：cosplay 指"真人 coser 扮演动漫角色"，属于**写实照片风格**，不是二次元动漫风格。应使用支持写实的模型，**不要**使用 WAI-illustrious。

## 可用模型

| 模型 | 协议脚本 | Prompt 语言 | 特点 | 能力 | 内容审查 |
|------|---------|------------|------|------|----------|
| WAI-illustrious | comfyui.py | **英文** | 动漫/二次元专用，角色还原度高 | 文生图 | 完全无审核 |
| novaAnimeXL_ilV180 | comfyui.py | **英文** | 动漫/二次元风格，色彩鲜艳，细节丰富 | 文生图 | 完全无审核 |
| z_image_turbo | comfyui.py | **中文** | 通用创意图，中文理解好，速度快，适合插画/概念设计 | 文生图 | 完全无审核 |
| bytedance/seedream-v4/edit | atlascloud.py | 中文 | 通用高质量生图，提示词遵循好，写实和动漫均可 | 文生图, 单图编辑, 多张编辑 | 几乎无审核 |
| google/nano-banana/edit | atlascloud.py | **英文** | Nano Banana 格式，Google 图像编辑，提示词遵循好 | 单图编辑, 多张编辑 | 几乎无审核 |
| gemini-3.1-flash-image-preview | gemini.py | **英文** | 通用生图，理解力强，支持复杂构图描述 | 文生图, 单图编辑, 多张编辑 | 审核严格 |

## 工作流程

1. **判断场景**：
   - **纯文生图**（用户只说"画一张 xxx"）→ 走 comfyui 或其他模型的文生图
   - **图像编辑**（用户明确要求"修改这张图""改图""换风格"等）→ 根据输入图片数量选择对应能力的模型：
     - **1 张图** → 选择支持**单图编辑**的模型（`bytedance/seedream-v4/edit` / `gemini-3.1-flash-image-preview`）
     - **2 张及以上** → 选择支持**多张编辑**的模型（`bytedance/seedream-v4/edit` / `gemini-3.1-flash-image-preview`）
     - **默认优先本地 ComfyUI**；不可用时 fallback 到云端模型
2. **Prompt 调优**：按照所选模型的调优策略处理 prompt（语言、质量词、风格词等）
3. **调用脚本**：将调优后的 prompt 原样传入对应脚本

> ⚠️ **参考图 vs 编辑图 区分原则**
>
> **纯风格参考**（用户说"参考这张图新画一张""按照这个风格画""模仿这张图"）：
> - 利用多模态能力分析参考图的风格/内容特征，融入 prompt
> - 走纯文生图，**不要**传 `--images`
>
> **基于原图构图的编辑**（用户说"保持这个姿势改成 xxx""把这张图改成写实风格""基于这张图生成 cosplay"）：
> - 需要保留原图的构图、姿势或主体内容，仅改变风格/细节
> - 走编辑流程，**必须**传 `--images`

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

### WAI-illustrious

**Prompt 语言**：**英文**

### novaAnimeXL_ilV180

**Prompt 语言**：**英文**
- 动漫/二次元风格模型，适合角色插画、场景渲染
- 色彩鲜艳，线条清晰，对人物面部和服装细节表现较好
- 与 WAI-illustrious 相比，风格更偏向传统日式动画，可根据用户喜好选择

**调优方法**：
1. 将用户描述翻译/转换为英文标签式 prompt（SDXL CLIP 对英文标签理解最佳）
2. 补充英文质量词：`masterpiece, best quality, highly detailed`
3. 根据内容补充风格词：`anime style, vibrant colors, cel shading`
4. 角色图追加角色名标签（如 `hatsune miku, vocaloid`）以提升还原度
5. **不要保留中文**

**调优示例**：
```
用户: "画一个穿水手服的蓝发女孩在樱花树下"
AI 调优后: "1girl, solo, blue hair, blue eyes, school uniform, cherry blossoms,
            smile, looking at viewer, soft lighting, anime style, vibrant colors,
            masterpiece, best quality, highly detailed"
```

**注意事项**：
- 该模型为**动漫/二次元专用**，写实/真人/照片类 prompt 效果差，应切换至其他模型
- 原生分辨率 1024x1024，二次元角色推荐 2:3 或 1:1 比例

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



## 图像编辑

**图像编辑**指在**已有图片基础上做修改**（如：换背景、改表情、换装、风格转换、去水印等）。

**以下情况不走编辑，走文生图**：
- 用户说"参考这张图新画一张""按照这个风格画""模仿这张图"——当前系统不支持垫图/参考图生成，忽略图片，按纯文生图处理
- 用户只是上传了图但没有任何修改指令

**走编辑流程的条件**（满足任意一条即可）：
- 用户明确表达"修改""编辑""改图""把这张图改成 xxx"等
- 用户要求"保持原图构图/姿势/内容"并改变风格或细节（如"保持这个姿势换成真人风格""基于这张图改成 cosplay"）
- 用户要求基于已有图片做重绘/风格迁移/角色替换等

当确认需要编辑时：

1. 从对话上下文中找到图片标识符（如 `<user_image_1>`，系统会在消息末尾附加可用图片列表）
2. 选择支持编辑的模型（gemini-3.1-flash-image-preview 或 bytedance/seedream-v4/edit）
3. 按模型调优策略处理编辑指令
4. 调用对应协议脚本：

```python
execute_script(
    skill_name="image_generation",
    script_path="scripts/comfyui.py",  # 或 scripts/gemini.py / scripts/atlascloud.py
    args=["--prompt", "<调优后的prompt>", "--images", "<user_image_1>,<user_image_2>"],
    timeout=180
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
- `--images` (可选): 待编辑图片标识符，逗号分隔。**只有图像编辑时才需要传，纯文生图不要传**
- `--aspect-ratio` (可选): `1:1`, `4:3`, `3:4`, `16:9`, `9:16`, `2:3`, `3:2`
- `--size` (可选): `512`, `1K`, `2K`, `4K`
- `--model` (必填): 模型名称（如 `z_image_turbo`、`qwen_image_edit`），脚本用此名称加载 `reference/{model}.json` 工作流
- `timeout` (execute_script 参数): 生图任务建议设为 `180`（默认 30 秒对本地 ComfyUI 通常不够）

**通用调用示例**：
```python
execute_script(
    skill_name="image_generation",
    script_path="scripts/comfyui.py",
    args=["--prompt", "<AI调优后的prompt>",
          "--aspect-ratio", "1:1",
          "--model", "z_image_turbo"],
    timeout=180
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
