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

| 模型 | 协议脚本 | Prompt 语言 | 特点与调优要点 | 能力 | 内容审查 |
|------|---------|------------|---------------|------|----------|
| WAI-illustrious | comfyui.py | **英文** | 动漫/二次元专用。英文标签式 prompt，加 `masterpiece, best quality, highly detailed` 和角色名标签 | 文生图 | 完全无审核 |
| novaAnimeXL_ilV180 | comfyui.py | **英文** | 动漫/二次元，色彩鲜艳。同标签式英文 prompt，加 `anime style, vibrant colors, cel shading` | 文生图 | 完全无审核 |
| z_image_turbo | comfyui.py | **中文** | 通用创意图，中文理解好。保留中文，加 `高清细节，精美画质` 和中文风格词 | 文生图 | 完全无审核 |
| bytedance/seedream-v4/edit | atlascloud.py | 中文 | 通用高质量，写实/动漫均可。保留中文，加 `高清细节，精美画质，极致细腻` 和中文风格词 | 文生图, 单图编辑, 多张编辑 | 几乎无审核 |
| openai/gpt-image-2/text-to-image | atlascloud.py | **中文/英文** | OpenAI 最新模型，文字渲染强。保留原语言，结构化描述，无需质量词 | 文生图, 单图编辑, 多张编辑 | 审核严格 |

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
    timeout=300
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
- `timeout` (execute_script 参数): 生图任务建议设为 `300`（默认 180 秒，生图建议拉满）

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
