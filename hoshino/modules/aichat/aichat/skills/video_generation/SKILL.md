---
name: video_generation
description: 当用户要求生成视频、做视频、让图片动起来、文生视频、图生视频时激活
disable-model_invocation: false
---

# 视频生成 SKILL

基于本地 ComfyUI Wan2.2 模型的视频生成能力。支持文生视频（T2V）与图生视频（I2V）。

## 能力边界

- 时长：**2 秒**（默认）或 **5 秒**
- 输出：24fps MP4
- **分辨率自适应**：图生视频按输入图宽高比自动计算目标分辨率（16 对齐，像素量上限约 40 万，等同 832×480）；文生视频固定 832×480（16:9）
- 风格：写实/电影感最佳；可描述任意场景（人物、动物、风景、科幻等）

## 模型选择

| 任务 | 脚本参数 | 特点 |
|------|---------|------|
| 文生视频（默认）| `--task t2v` | 快速版（Q8+LightX2V 4步），约 **3 分钟** |
| 文生视频（高质量）| `--task t2v_quality` | 精细细节更强，约 10 分钟，仅在用户要求高质量/复杂场景时用 |
| 图生视频 | `--task i2v --images <标识符>` | 让静态图片动起来，约 3-5 分钟 |

**默认优先使用图生视频能力**（如果用户提供了图片或想让现有图片动起来）。
用户明确要求"直接生成视频/从文字生成"时使用文生视频（默认快速版）。

## 调用方式

执行脚本 `scripts/comfyui_video.py`，参数：

```
--task t2v|t2v_quality|i2v  # 任务类型（默认 t2v 快速版）
--prompt "视频描述"      # 必填，描述画面与运动
--duration 2|5          # 时长（秒，默认 2）
--images <标识符>        # i2v 必填：图片标识符（如 <user_image_1>），逗号分隔多张
```

## 超时与续查机制（重要）

视频生成耗时 3-10 分钟，单次脚本调用最多等待约 280 秒：

1. **首次调用**：提交任务并等待。若完成，返回 `identifier`（如 `<ai_video_1>`），在回复中引用即可。
2. **若返回 `视频仍在生成中，请使用 --prompt-id xxx 继续查询`**：再次调用脚本，仅带 `--prompt-id xxx`（可加 `--task`）继续等待，直到返回视频标识符。**该操作幂等，可多次调用。**
3. 收到 `<ai_video_N>` 标识符后，在回复文本中引用（如"视频来了 <ai_video_1>"），系统会自动发送。

## 提示词技巧（视频特有）

- **运动必须显式描述**：`walks forward` / `turns around` / `hair blowing in wind` / `camera slowly tracking`
- **镜头语言**：`camera slowly pushing in` / `camera orbits around` / `aerial shot` / `handheld shot`
- **光线**：`golden hour lighting` / `neon glow` / `soft diffused light`（无光线描述画面易灰平）
- **结构**：主体 + 动作 + 环境 + 光线 + 镜头 + 质感（`photorealistic, film still, professional color grading`）
- **I2V 提示词**：描述"从首帧延续"的运动，如 `the woman continues standing, her hair gently moving in the wind`；大动作要加身份保持词 `same woman, same outfit`
- **负面词不要用否定句式**（如 no blur），用正向描述替代
- **建议全英文提示词**（模型对英文理解最佳）

## 使用示例

```
# 文生视频（2 秒）
execute_script(
    skill_name="video_generation",
    script_path="scripts/comfyui_video.py",
    args=["--task", "t2v", "--prompt", "a red panda walking through snowy bamboo forest, camera slowly tracking, golden hour lighting, photorealistic"],
    timeout=300
)

# 图生视频（5 秒，让用户图片动起来）
execute_script(
    skill_name="video_generation",
    script_path="scripts/comfyui_video.py",
    args=["--task", "i2v", "--images", "<user_image_1>", "--duration", "5",
          "--prompt", "the woman turns around slowly, hair whipping in wind, camera orbits, photorealistic"],
    timeout=300
)

# 续查未完成的任务
execute_script(
    skill_name="video_generation",
    script_path="scripts/comfyui_video.py",
    args=["--prompt-id", "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"],
    timeout=300
)
```

## 注意事项

- 生成中请告知用户"正在生成视频，大约需要 X 分钟"，避免用户等待焦虑
- 若返回错误（ComfyUI 未启动、显存不足等），如实告知用户，可建议稍后重试
- 视频体积约 1-3MB，QQ 可直接发送
