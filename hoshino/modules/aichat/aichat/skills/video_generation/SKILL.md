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
| 角色参考 | `--task ref --images <标识符>` | 参考图作角色/场景参考（ref2va），**无锚定**，首帧自然，角色跟随参考图，约 1-2 分钟 |

**默认优先图生视频**（用户提供图片时）。用户明确"直接生成/从文字生成"时用 t2v。

## 视频工具（看视频/查规格/裁剪，禁止自写脚本）

需要**查看视频内容、查询规格、裁剪片段**时，调用 `scripts/video_tools.py`，**禁止自写 ffmpeg/ffprobe 脚本**：

```
# 查规格（时长/分辨率/帧率/大小）
execute_script(skill_name="video_generation", script_path="scripts/video_tools.py",
  args=["--probe", "--video", "<user_video_1>"], timeout=60)

# 抽帧（时间点秒 → <ai_image_N>，LLM 引用该图片即可"看"视频画面）
execute_script(skill_name="video_generation", script_path="scripts/video_tools.py",
  args=["--extract-frame", "--video", "<user_video_1>", "--at", "3.0"], timeout=60)

# 裁剪片段（起点+时长秒 → <ai_video_N>，保留原音轨）
execute_script(skill_name="video_generation", script_path="scripts/video_tools.py",
  args=["--cut", "--video", "<user_video_1>", "--start", "1.0", "--duration", "5"], timeout=60)
```

- `--video`：会话内视频标识符（`<user_video_N>` / `<ai_video_N>`），路径由 `SKILL_VIDEOS` 自动注入，无需手写路径
- 抽帧产物是 `<ai_image_N>`，在回复中引用即可让用户/模型看到该帧；需要判断视频内容时抽 2-4 个关键时间点的帧分别查看
- 裁剪结果 `<ai_video_N>` 可直接引用交付或作为链式任务的 `--source-video`

## 提示词规范（重要）

MiniMax H3 提示词是**自然语言格式**。**t2v/i2v 使用三段式，ref 使用官方六段式**，顺序固定：

```
integrated_multimodal_description: 正文（连续镜头自然语言描述，见下）
overall_soundscape: 全片环境音、动作音、非语言人声总结（全英文）
non_diegetic_music: 背景音乐描述（角色听不到、观众听到的，全英文）
```

**正文写法（核心纪律）**：
1. **不用 `[Shot N]` 分段**，用自然语言连续镜头描述整场内容；切镜用英文连接词推进：`the camera cuts to ...` / `the shot transitions to ...` / `the shot changes to ...` / `the camera dynamically follows ...`
2. **不写任何时间码**，全部靠自然语言连续镜头推进
3. 每个镜头只推进一个核心关系，下一镜从上一镜的末态直接接力（姿态/方向/位置/武器/对方状态/余波至少继承四项），不能切后重新起势或无因瞬移
4. **时长匹配**：镜头数按时长缩放——2 秒 ≈ 1-2 镜；5 秒 ≈ 3-4 镜；10 秒 ≈ 6-8 镜；15 秒 ≈ 10-14 镜（默认 12 镜），每镜 4-8 个原子事件
5. **声音拆两段**：环境音（overall_soundscape）+ 背景音乐（non_diegetic_music）分开写，**内容一律全英文**；`overall_soundscape:` 英文内容最后一个句点后**不换行**直接续写 `non_diegetic_music:`
6. **避免抽象词**：不用 "cinematic"/"beautiful"/"情绪很激动"，用具体细节（光线方向、颜色、材质、微表情、身体动作、具体声音）
7. **对话原语言**：对白/歌词保持原语言，一字不改；不新增台词或旁白
8. 声音字段名逐字使用 `overall_soundscape:` / `non_diegetic_music:`（英文小写半角冒号），不得翻译、删除或改写大小写

完整官方指南在技能目录 `references/h3-prompt-guide-base-en.txt`（T2V/I2V）与 `h3-prompt-guide-ref-en.txt`（角色参考模式），**写作前应参考**。

**ref 模式的特殊结构（官方六段式）**：`--task ref` 必须使用官方六段式（参考图用 `<Picture 1>`/`<Picture 2>` 标签引用），顺序固定：

```
subject_definitions: <Subject 1> 是 <Picture 1> 中的……（逐张定义角色）
summary: [reference generation] 目标视频整体内容概述……
retention_analysis: <Subject 1>（出现在 [Shot 1]）：fully_preserved - 关键外貌特征……
detailed_description: [Shot 1] 画面/动作/镜头/对白/环境音描述……
overall_soundscape: 全片环境音总结……
non_diegetic_music: 背景音乐描述……
```

六段缺一不可，三段式提示词在 ref 模式下相似度会明显下降。资产角色区的识别与正文调用规则见"角色参考模式"章节。

## 调用方式

执行脚本 `scripts/comfyui_video.py`：

```
--task t2v|i2v|ref       # 任务类型（默认 t2v）
--prompt "提示词"         # 必填（t2v/i2v 三段式；ref 官方六段式）
--duration 1-15        # 时长（秒，任意值，默认 2）
--resolution 480p|768p  # 分辨率档位（默认 480p；768p 高清约 3-5 倍耗时，适合最终成片）
--images <标识符>        # i2v/ref 必填：图片标识符（如 <user_image_1>），多张逗号分隔
--guides "0,2.5,5"     # i2v 多图锚定时间点（秒，与图片数一致；缺省自动均分）
--anchor first|last    # i2v 单图锚定位置（默认 first；last=图片作为视频尾帧）
--aspect-ratio W:H     # ref 指定画幅（如 16:9、3:4；拼接参考图必填，见"拼接参考图"章节）
--steps N              # 采样步数（默认按任务与加速 LoRA 匹配：ref=4、t2v/i2v=8；一般不用改）
--lora-strength 0-1    # MysticXXX LoRA 强度（仅 t2v/i2v 生效；0=关闭该 LoRA，默认 0.5）
```

## 超时与续查机制（重要）

生成耗时 1-2 分钟，脚本单次等待最长 240 秒：

1. **首次调用**：提交并等待。完成返回 `identifier`（如 `<ai_video_1>`），在回复中引用即可。
2. **返回 `视频仍在生成中，请使用 --prompt-id xxx 继续查询`**：再次调用仅带 `--prompt-id xxx` 续查（幂等，可多次）。
3. 收到 `<ai_video_N>` 后，在回复文本中引用（如"视频来了 <ai_video_1>"），系统自动发送。

## 使用示例

```
# 文生视频（5 秒，三段式，自然语言连续镜头）
execute_script(
    skill_name="video_generation",
    script_path="scripts/comfyui_video.py",
    args=["--task", "t2v", "--duration", "5",
          "--prompt", "integrated_multimodal_description: A red panda walks through a snowy bamboo forest at dawn, soft golden light through mist, camera slowly tracking forward. Gentle snow falling, panda's fur rippling. the camera cuts to a closer shot of its paws leaving soft prints, breath visible in cold air. Audio: soft footsteps on snow.\n\noverall_soundscape: gentle wind, snow crunching, distant birdsong\n\nnon_diegetic_music: soft ambient piano, warm and calm"],
    timeout=600
)

# 图生视频
execute_script(
    skill_name="video_generation",
    script_path="scripts/comfyui_video.py",
    args=["--task", "i2v", "--images", "<user_image_1>", "--duration", "5",
          "--prompt", "integrated_multimodal_description: The woman from the image continues standing on the rooftop, turns her head slowly and smiles, hair moving in wind, camera slowly pushing in. the camera cuts to a wide shot showing the city below. Audio: wind, distant city.\n\noverall_soundscape: gentle wind, distant city ambience\n\nnon_diegetic_music: soft cinematic strings"],
    timeout=600
)

# 续查
execute_script(
    skill_name="video_generation",
    script_path="scripts/comfyui_video.py",
    args=["--prompt-id", "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"],
    timeout=600
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

参考图不锚定到具体帧，而是作为 `<Picture N>` 角色/场景参考被模型跟随，**首帧自然、角色还原度高**。适合：角色卡驱动角色出演、保持多镜头人物一致。**多张参考图一律先拼接成单图再走本模式**（见"拼接参考图"章节）。

```
# 智乃+心爱 角色卡出演（提示词用官方六段式，<Picture 1>/<Picture 2> 引用）
--task ref --images <user_image_1>,<user_image_2> --duration 5
```

规则：
- **提示词必须用官方六段式**（subject_definitions/summary/retention_analysis/detailed_description/overall_soundscape/non_diegetic_music），见上文"提示词规范"；三段式在 ref 模式下相似度会明显下降
- 每张参考图在提示词中用 `<Picture N>` 标签引用（第 N 张图），先 `subject_definitions` 定义角色（绑定 `<Subject N>` + 中文身份描述）；**正文用中文身份称呼，不用 `<Subject N>`/图片标签**（见下文"资产角色绑定"）
- 参考图不限于 AI 生成：**用户上传的 `<user_image_N>`、AI 生成的 `<ai_image_N>` 均可**，任何会话内图片标识符都能解析
- 与多图锚定的区别：锚定锁定的是"这一帧长什么样"；ref 是"角色长什么样"，画面构图完全交给提示词
- 典型用途：角色卡出演、多镜头角色一致性（比锚定模式首帧更自然，无卡片感）

### 资产角色绑定（写 ref 提示词前必做）

**核心规则（两条都要做到）**：
1. `subject_definitions` 必须给出**清晰、完整的标签定义**（每个 `<Subject N>` 绑定 `<Picture N>` 中的具体角色，附中文身份描述）
2. `detailed_description` 正文必须使用**中文身份称呼**，**禁止出现任何图片标签**（`<Picture N>`/`<Subject N>` 都不出现，只用"穿风衣的男人""红裙女人"这类称呼）

**先识别，后写作**：用户提供图片时，必须先完整识别图片内容——图中有几个人物、各自的性别/年龄段/外貌特征、服装与配饰、手持道具、所处场景、光线方向与构图，将识别结果写入资产角色区（`subject_definitions`），**不得跳过识别直接生成正文**。

**资产角色区写法**（每个资产一段简洁但足以锁定身份的中文描述）：
- 人物身份、性别与年龄段
- 体型、脸部特征、发型、眼神气质
- 服装、配饰、手持道具及其主色
- 关键材质与结构（如丝绸的垂坠感、金属眼镜的冷光、戒指的细节）
- 在视频中的角色（主角、对话对手、旁观者、场景或道具参考）
- **不写**对话时间线、镜头安排、气氛宣传语或尚未发生的情绪变化

**正文调用规则**：
- `detailed_description` 正文**不出现图片标签**，直接用识别出的中文身份称呼推动动作/对白（如"穿风衣的男人""红裙女人""主角"）
- 图片外自然生成的对话对手、环境延伸或道具，直接用稳定中文名称描述
- 正文用自然语言连续镜头（见"提示词规范"正文写法），不用 `[Shot N]`、不写逐镜时间码

## 拼接参考图（多图 → 单图 ref）

多张参考图**拼成一张图**后，按单图参考跑。典型用途：多角色同框对话、单人多视角（正/侧/背）、角色+场景、双图对比、**角色 + 局部细节（身体部位/特写画法）**等。**所有"多张参考图"场景一律先拼接再走单图 ref**。

### 第一步：拼接参考图（`scripts/compose_ref_image.py`）

```
execute_script(skill_name="video_generation",
  script_path="scripts/compose_ref_image.py",
  args=["--images", "<user_image_1>,<user_image_2>", "--layout", "h", "--gap", "8"],
  timeout=60)
```

- `--images`：多张参考图标识符，逗号分隔（至少 2 张）
- `--layout`：`h` 横向并排（默认，推荐，对应"左=角色A、右=角色B"）；`v` 纵向堆叠
- `--gap`：图间间隙像素（默认 8）；`--bg`：背景色（PIL 颜色名，默认 white）
- 返回 `{"success": true, "identifier": "<ai_image_N>", "path": ...}` —— 保存该标识符，第二步引用它

### 第二步：单图参考生成（`comfyui_video.py --task ref`）

```
execute_script(skill_name="video_generation",
  script_path="scripts/comfyui_video.py",
  args=["--task", "ref", "--images", "<ai_image_N>", "--duration", "5",
        "--resolution", "480p",
        "--aspect-ratio", "16:9",
        "--prompt", "<六段式：单图拆多 Subject，见下>"],
  timeout=600)
```

- **拼接图会带偏画幅，必须显式指定 `--aspect-ratio`**：先读取原始参考图（拼接前的第一张图）的宽高比，据此传参（如原图 3:4 竖图 → `--aspect-ratio 3:4`；横图 → `16:9` 等）。未指定时视频宽高会跟随拼接图，画幅错误
- 可选值：`16:9` / `9:16` / `3:4` / `4:3` / `1:1` 等任意 `W:H` 格式，按档位像素量（480p/768p）计算

### 提示词模板（拼接图 + 资产角色绑定，官方六段式）

拼接图整体是 `<Picture 1>`。**先完整识别图中每个角色/场景**（身份/年龄/外貌/服装/道具/场景/光线），把识别结果写入资产角色区；再按资产角色绑定规范写正文。每个角色拆成独立 `<Subject N>` 并给出**锁定身份的中文描述**（含服装配饰及主色）；场景类拼接图（如角色+场景）可给场景单独一个 `<Subject N>`：

```
subject_definitions: <Subject 1> 是 <Picture 1> 左侧的"<中文身份称呼>"（身份/性别/年龄段；体型/脸/发型/眼神；服装配饰道具及主色；材质结构；视频中的角色）。<Subject 2> 是 <Picture 1> 右侧的"<中文身份称呼>"（同上）。
summary: [reference generation] 穿风衣的男人与红裙女人……（用中文称呼概述整体内容）
retention_analysis: <Subject 1>（出现在 [Shot 1]）：fully_preserved - <关键身份特征>；<Subject 2>（出现在 [Shot 1]）：fully_preserved - <关键身份特征>
detailed_description: 一个中全景定场镜头框住"穿风衣的男人"与"红裙女人"隔桌对坐……（正文：自然语言连续镜头，无 [Shot N] 无时间码，中文身份称呼，不出现图片标签；多角色保持区分，不合并身体、不互换服装）…… the camera cuts to ……（继续连续镜头）
overall_soundscape: <全英文环境音/动作音/对白语气总结，最后一个句点后不换行>
non_diegetic_music: <全英文配乐描述>
```

要点：
- **先识别后写作**：`subject_definitions` 前必须先完成图片识别（人物/性别/年龄/外貌/服装配饰/道具/场景/光线/构图），不得跳过识别直接生成正文
- 资产角色区只写锁定身份的描述（含服装配饰、材质结构、视频角色定位），**不写**对话时间线、镜头安排、气氛宣传语或尚未发生的情绪变化
- **正文用中文身份称呼**（"穿风衣的男人""红裙女人""主角"），不出现图片标签；图片外自然生成的对话对手/环境/道具直接用稳定中文名称描述
- 拼接图各部分方位务必与正文一致（"左侧的 X 对右侧的 Y 说话"），多角色时显式写"保持角色区分，不合并身体、不互换服装"
- **局部细节参考（身体部位/特写画法等）一律拼接进角色图，禁止作为独立参考图**
- 若需对比拼接与多图的效果差异，用同一提示词分别跑两遍（仅排查用，正式生成一律拼接）
- **正文用自然语言连续镜头，不用 `[Shot N]` 分段**，切镜用 `the camera cuts to` / `the shot transitions to` / `the shot changes to` / `the camera dynamically follows` 等英文连接词；每镜 4-8 个原子事件，按时长缩放镜头数（见"提示词规范"）
- **声音字段全英文**：`overall_soundscape:` 内容全英文，最后一个句点后不换行直接续写 `non_diegetic_music:`，配乐内容也全英文
- 480p 快速测试参数效果；确认后再用 768p 出成片

## 链式长视频（角色替换 + 长片续写）

把一段**源视频的角色替换成指定角色**（或纯续写生成），支持超过单段上限的长视频（源视频按 124 帧窗口切段，段间 22 帧 Motion Context 衔接）。**执行脚本是 `scripts/comfyui_video_chain.py`（独立脚本，不是 comfyui_video.py 的任务）：**

```
# 角色替换：源视频动作/场景/字幕 1:1 保留，人物换成参考图角色
execute_script(skill_name="video_generation", script_path="scripts/comfyui_video_chain.py",
  args=["--images", "<user_image_1>,<user_image_2>,<user_image_3>",
        "--source-video", "<user_video_1>",
        "--prompt", "<video editing 六段式，见下>",
        "--segments", "6", "--resolution", "768p", "--keep-audio"],
  timeout=600)
```

**前台无本地状态续跑机制（重要）**：链式任务由当前 LLM 会话持续执行，脚本每次只处理一个 ComfyUI prompt，LLM 必须保存并原样传回返回值中的 `state`：
开始前请将 aichat 的 `max_tool_rounds` 配置调到足以覆盖全部分段调用和必要重试的值。
1. 首次调用提交第 1 段，返回 `{"status": "partial", "state": {...}}`；保存完整 `state`。
2. 立即继续调用 `execute_script`，使用 `args=["--state", "<上次返回的完整 state JSON>", "--wait", "240"]`、`timeout=600`。脚本会在内部等待，不要调用 `run_background_task`、`wait_and_resume` 或 shell sleep。
3. 若仍返回 `partial`，保存最新 `state` 并立即重复 `--state` 调用；不要再次传首轮参数。
4. 若返回带 `state` 的可重试错误，原样保留该 `state` 并重试一次；任务明确丢失或连续重试仍失败时才告知用户失败。
5. 段完成时脚本会存储该段、提交下一段并返回更新后的 `state`。不得把中间 `<ai_video_N>` 当成品发送。
6. 直到返回 `{"success": true, "identifier": "<ai_video_N>"}` 才结束工具调用；最终回复只输出该视频标识符，不附带其他文字，让当前会话把交付结果作为一条视频消息发送。
7. 脚本不写 `chain_state`、锁文件或 `state.json`，也不使用 `--resume`；`state` 只保存在当前 LLM 工具上下文中，不能手工修改任何字段。

**禁止偷懒（硬性规则，违反即任务失败）**：
- **禁止使用后台 sub agent 执行链式任务**（`run_background_task`、`delegate_task`、`wait_and_resume` 均不可用）；链式任务必须由当前会话前台逐轮 `--state` 续跑，直到拿到最终 `<ai_video_N>`
- **禁止编写辅助脚本来循环提交/续跑链式任务**（如写一个 for 循环脚本依次调用 `--state` 或 `--prompt-id`）；必须由 LLM 自己逐轮调用 `execute_script` 传递 `state`
- 禁止把链式任务"外包"给任何子代理、后台任务或脚本；`state` 只能在当前 LLM 工具调用上下文中传递
- 若当前轮工具调用超时或中断，下一轮用**同一份** `state` 继续，不得重新发起首轮参数

规则：
- **提示词用 video editing 六段式**（链式替换专用，与 ref 的 `<Picture N>` 六段式、t2v/i2v 三段式均不同），顺序固定：

```
subject_definitions: <Subject 1> 是 <Picture N> 中的<中文身份称呼>（身份/性别/年龄/发型/眼眸/服装配饰/主色/体型）；attribute_transfer - 仅替换源视频人物的身份与服装，其余一切跟随源视频
summary: [video editing] 将源视频中的<原人物>替换为 <Subject 1>，源视频的场景/镜头/动作时序全部 1:1 保留
retention_analysis: <Video 1>（全程）：partially_preserved - 保留场景构图、镜头运动、动作时序、人物走位与字幕，仅替换人物身份和服装；<Subject 1>（全程）：attribute_transfer - <关键外观锚点>
detailed_description: 保持源视频的动作、场景构图、镜头角度与节奏 1:1 复刻，只将人物外观替换为<中文身份称呼>；**不描述源视频之外的新动作、新镜头、新场景元素**（自然语言连续镜头，无 [Shot N] 无时间码）
overall_soundscape: <全英文，源音轨保留>
non_diegetic_music: <全英文>
```

- **`<Video 1>` 引用必须存在**：链式替换靠 `<Video 1>` 标签绑定源视频，`retention_analysis` 里标 `partially_preserved`（保留场景/动作/时序，只换身份服装），否则模型不保留源视频内容
- **`<Subject 1>` 标 `attribute_transfer`**：目标角色只转移外观锚点（发型/发色/眼睛/服装），动作全部来自源视频
- **`detailed_description` 禁止自由创作（硬性规则）**：正文只写"保持源视频 1:1，只替换人物外观为 X"，**禁止描述源视频之外的新动作、新姿态、新镜头、新场景元素、新光线**（如"仰卧/转身/丝织物缠绕/烛光映照"这类自创画面一律不写）——写越具体，模型越倾向重新生成而非跟随源视频，导致与源视频不一致
- **先抽帧观察，再写正文**：写 `detailed_description` 前必须用 `video_tools.py --extract-frame` 抽 2-4 个关键时间点帧观察源视频实际内容；正文中如需提及动作/场景，只能描述抽帧观察到的真实内容，不得脑补
- **采样配置固定 euler + simple**（res_multistep/beta 会导致替换不稳定/失败/圣光/丢字幕，已实测定位）
- 身份图 3 张左右（正面全身/侧面/脸部特写）
- 源视频自动转 24fps 并按窗口切片（每段用对应时间片）；30fps 源无需预处理
- 每段 124 帧窗口（5.17s）→ 交付 102 帧，段间自动衔接；`--segments` 控制段数（源 25s ≈ 6 段）；每段正文按"提示词规范"时长匹配（≈5 秒/段 → 3-4 镜）
- `--keep-audio`：成片保留源视频原音轨（BGM/对白，时间轴 1:1 对齐；注意对白是原角色的声音）；声音字段仅作画面声效参考
- 各段无 H3 生成音轨；时长：段数 × 2-7 分钟（720×960 4 步）

## 超分（可选，默认不执行）

**默认不超分**：生成的视频直接交付。**仅当用户明确要求"超分/高清/放大/更清晰"时才调用** `scripts/upscale_video.py` 对已生成的视频做 2x 超分（RealESRGAN anime_6B，固定 24 帧/块分块处理防爆显存，保留原音轨）：

```
execute_script(skill_name="video_generation",
  script_path="scripts/upscale_video.py",
  args=["--video", "<ai_video_N>", "--scale", "2"],
  timeout=600)
```

- `--video`：会话内视频标识符（`<ai_video_N>`）
- `--scale`：放大倍数，`2`（默认）或 `4`
- 首次调用会返回 `status=partial`、`progress` 和 `state`，不会等待整片完成；必须把完整 `state` 原样保存在当前对话上下文中
- 后续调用使用 `args=["--state", "<上次返回的 state JSON>"]`，每次最多等待一个 24 帧块；`pending` 或 `partial` 都继续原样传回最新 `state`
- 只有返回 `success=true` 且包含新标识符 `<ai_video_N>` 时才算完成，回复中引用该超分版交付
- 中间帧和块视频保存在当前会话 `tmp/upscale_<run_id>/`，不会占用 VideoStore 条目；会话失效时随 session 目录清理
- 每次调用建议 `timeout=600`、`--wait 240`，避免单次工具调用超过执行上限；ComfyUI 任务丢失或失败时会返回 `status=error`，需要根据错误重新提交
- 生成流程中不要主动建议超分；用户提出"不够清晰/放大"等要求时才使用

## 注意事项

- 生成中告知用户"正在生成视频，约 1-2 分钟"
- 若返回错误（ComfyUI 未启动等），如实告知可稍后重试
- 视频约 1-2MB（含音轨），QQ 可直接发送
- 音频是模型原生生成的：提示词里写什么声音，视频里就有对应音轨
