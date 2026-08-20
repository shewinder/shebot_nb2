---
name: video_generation
description: 当用户要求生成视频、做视频、让图片动起来、文生视频、图生视频时激活
disable-model_invocation: false
---

# 视频生成 SKILL

基于 **MiniMax H3**（本地 ComfyUI）的视频生成能力。支持文生视频（T2V）与图生视频（I2V），**原生生成同步音轨**（对白/环境音/音乐）。

## 能力边界

- 时长：**1-15 秒任意**（默认 2 秒，`--duration 10` 即 10 秒，帧数自动对齐模型网格）
- 分辨率：**480p 快速档**（864×480，默认）/ **768p 高清档**（1344×768，约 3-5 倍耗时）；i2v 按输入图比例自适应，24fps MP4（含 AAC 音轨）
- 出片：约 **1-2 分钟/条**（比传统模型快 3-5 倍）
- 语义：自然语言提示词（**中文/英文均可**）

## 模型选择

| 任务 | 脚本参数 | 特点 |
|------|---------|------|
| 文生视频 | `--task t2v` | 文本直接生成音视频，约 1-2 分钟 |
| 图生视频 | `--task i2v --images <标识符>` | 首帧锚定图片，约 1-2 分钟 |

**默认优先图生视频**（用户提供图片时）。用户明确"直接生成/从文字生成"时用 t2v。

## 提示词规范（重要：官方格式）

MiniMax H3 提示词是**自然语言三段式**，顺序固定：

```
integrated_multimodal_description: [Shot 1] 画面/动作/镜头/对白/环境音描述 ...
[Shot 2] ...

overall_soundscape: 全片环境音、动作音、非语言人声总结 ...

non_diegetic_music: 背景音乐描述（角色听不到、观众听到的）...
```

**核心规则**：
1. **分镜结构**：`[Shot N]` 开头，按时间顺序描述每个镜头（构图/主体/环境/动作/镜头运动/声音）
2. **声音拆两段**：环境音（overall_soundscape）+ 背景音乐（non_diegetic_music）分开写
3. **时长匹配**：描述内容的总时长 ≈ 目标视频时长（2 秒 ≈ 1 个短镜头；5 秒 ≈ 2-3 个镜头）
4. **避免抽象词**：不用 "cinematic"/"beautiful"，用具体细节（光线方向、颜色、材质、具体声音）
5. **对话原语言**：对白/歌词保持原语言
6. 引用标签全篇一致（`<Picture 1>` / `<Video 1>` / `<Audio 1>`）

完整官方指南在技能目录 `references/h3-prompt-guide-base-en.txt`（T2V/I2V）与 `h3-prompt-guide-ref-en.txt`（参考视频模式），**写作前应参考**。

## 调用方式

执行脚本 `scripts/comfyui_video.py`：

```
--task t2v|i2v          # 任务类型（默认 t2v）
--prompt "三段式提示词"  # 必填
--duration 1-15        # 时长（秒，任意值，默认 2）
--resolution 480p|768p  # 分辨率档位（默认 480p；768p 高清约 3-5 倍耗时，适合最终成片）
--images <标识符>        # i2v 必填：图片标识符（如 <user_image_1>）
```

## 超时与续查机制（重要）

生成耗时 1-2 分钟，脚本单次等待约 280 秒：

1. **首次调用**：提交并等待。完成返回 `identifier`（如 `<ai_video_1>`），在回复中引用即可。
2. **返回 `视频仍在生成中，请使用 --prompt-id xxx 继续查询`**：再次调用仅带 `--prompt-id xxx` 续查（幂等，可多次）。
3. 收到 `<ai_video_N>` 后，在回复文本中引用（如"视频来了 <ai_video_1>"），系统自动发送。

## 使用示例

```
# 文生视频（5 秒，官方三段式）
execute_script(
    skill_name="video_generation",
    script_path="scripts/comfyui_video.py",
    args=["--task", "t2v", "--duration", "5",
          "--prompt", "integrated_multimodal_description: [Shot 1] A red panda walks through a snowy bamboo forest at dawn, soft golden light through mist, camera slowly tracking forward. Gentle snow falling, panda's fur rippling. Audio: soft footsteps on snow.\n\noverall_soundscape: gentle wind, snow crunching, distant birdsong\n\nnon_diegetic_music: soft ambient piano, warm and calm"],
    timeout=300
)

# 图生视频
execute_script(
    skill_name="video_generation",
    script_path="scripts/comfyui_video.py",
    args=["--task", "i2v", "--images", "<user_image_1>", "--duration", "5",
          "--prompt", "integrated_multimodal_description: [Shot 1] The woman from the image continues standing on the rooftop, turns her head slowly and smiles, hair moving in wind, camera slowly pushing in. Audio: wind, distant city.\n\noverall_soundscape: gentle wind, distant city ambience\n\nnon_diegetic_music: soft cinematic strings"],
    timeout=300
)

# 续查
execute_script(
    skill_name="video_generation",
    script_path="scripts/comfyui_video.py",
    args=["--prompt-id", "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"],
    timeout=300
)
```

## 注意事项

- 生成中告知用户"正在生成视频，约 1-2 分钟"
- 若返回错误（ComfyUI 未启动等），如实告知可稍后重试
- 视频约 1-2MB（含音轨），QQ 可直接发送
- 音频是模型原生生成的：提示词里写什么声音，视频里就有对应音轨
