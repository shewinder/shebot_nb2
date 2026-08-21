---
name: video_generation
description: 当用户要求生成视频、做视频、让图片动起来、文生视频、图生视频时激活
disable-model_invocation: false
---

# 视频生成 SKILL

基于 **MiniMax H3**（本地 ComfyUI）的视频生成能力。支持文生视频（T2V）、图生视频（I2V）与角色参考（ref2va），**原生生成同步音轨**（对白/环境音/音乐）。

## 能力边界

- 时长：**1-15 秒任意**（默认 2 秒，`--duration 10` 即 10 秒，帧数自动对齐模型网格）
- 分辨率：**480p 快速档**（864×480，默认）/ **768p 高清档**（1344×768，约 3-5 倍耗时）；i2v 按输入图比例自适应，24fps MP4（含 AAC 音轨）
- 出片：约 **1-2 分钟/条**（比传统模型快 3-5 倍）
- 语义：自然语言提示词（**中文/英文均可**）

## 模型选择

| 任务 | 脚本参数 | 特点 |
|------|---------|------|
| 文生视频 | `--task t2v` | 文本直接生成音视频，约 1-2 分钟 |
| 图生视频 | `--task i2v --images <标识符>` | 单图=首/尾帧锚定（`--anchor`）；双图=首尾帧；多图=多帧剧情锚定（`--guides`），约 1-2 分钟 |
| 角色参考 | `--task ref --images <标识符>` | 参考图作 `<Picture N>` 角色/场景参考（ref2va），**无锚定**，首帧自然，角色跟随参考图，约 1-2 分钟 |

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

完整官方指南在技能目录 `references/h3-prompt-guide-base-en.txt`（T2V/I2V）与 `h3-prompt-guide-ref-en.txt`（角色参考模式），**写作前应参考**。

**角色参考模式（`--task ref`）必须使用官方六段式格式**（参考图用 `<Picture 1>`/`<Picture 2>` 标签引用），顺序固定：

```
subject_definitions: <Subject 1> 是 <Picture 1> 中的……（逐张定义角色）
summary: [reference generation] 目标视频整体内容概述……
retention_analysis: <Subject 1>（出现在 [Shot 1]）：fully_preserved - 关键外貌特征……
detailed_description: [Shot 1] 画面/动作/镜头/对白/环境音描述……
overall_soundscape: 全片环境音总结……
non_diegetic_music: 背景音乐描述……
```

六段缺一不可，三段式提示词在 ref 模式下相似度会明显下降。

## 调用方式

执行脚本 `scripts/comfyui_video.py`：

```
--task t2v|i2v|ref       # 任务类型（默认 t2v）
--prompt "提示词"         # 必填（ref 模式用官方六段式）
--duration 1-15        # 时长（秒，任意值，默认 2）
--resolution 480p|768p  # 分辨率档位（默认 480p；768p 高清约 3-5 倍耗时，适合最终成片）
--images <标识符>        # i2v/ref 必填：图片标识符（如 <user_image_1>），多张逗号分隔
--guides "0,2.5,5"     # i2v 多图锚定时间点（秒，与图片数一致；缺省自动均分）
--anchor first|last    # i2v 单图锚定位置（默认 first；last=图片作为视频尾帧）
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

## 多图锚定（剧情分镜）

多张图片按时间点锚定到视频的指定帧，实现"分镜控制"：

```
# 图A 是开场画面(0s)，图B 是 2.5s 转折点，图C 是结局(5s)
--task i2v --images <imgA>,<imgB>,<imgC> --guides "0,2.5,5" --duration 5
```

规则：
- 图片数 = guides 数量（缺省 guides 时自动均分到时间轴）
- 提示词描述完整剧情（各镜头的画面、动作、声音）
- 典型用途：变身/转场/剧情转折的关键帧锁定
- 首图决定分辨率比例（多图建议同比例）

## 角色参考模式（ref2va）

参考图不锚定到具体帧，而是作为 `<Picture N>` 角色/场景参考被模型跟随，**首帧自然、角色还原度高**。适合：角色卡驱动角色出演、保持多镜头人物一致。

```
# 智乃+心爱 角色卡出演（提示词用官方六段式，<Picture 1>/<Picture 2> 引用）
--task ref --images <user_image_1>,<user_image_2> --duration 5
```

规则：
- **提示词必须用官方六段式**（subject_definitions/summary/retention_analysis/detailed_description/overall_soundscape/non_diegetic_music），见上文"提示词规范"；三段式会显著降低相似度
- 每张参考图在提示词中用 `<Picture N>` 标签引用（第 N 张图），先 `subject_definitions` 定义角色再在分镜中用 `<Subject N>` 称呼
- 参考图不限于 AI 生成：**用户上传的 `<user_image_N>`、AI 生成的 `<ai_image_N>` 均可**，任何会话内图片标识符都能解析
- 参考图数量不限（工作流按图数动态扩展），首图决定分辨率比例
- 与多图锚定的区别：锚定锁定的是"这一帧长什么样"；ref 是"角色长什么样"，画面构图完全交给提示词
- 典型用途：角色卡出演、多镜头角色一致性（比锚定模式首帧更自然，无卡片感）

## 注意事项

- 生成中告知用户"正在生成视频，约 1-2 分钟"
- 若返回错误（ComfyUI 未启动等），如实告知可稍后重试
- 视频约 1-2MB（含音轨），QQ 可直接发送
- 音频是模型原生生成的：提示词里写什么声音，视频里就有对应音轨
