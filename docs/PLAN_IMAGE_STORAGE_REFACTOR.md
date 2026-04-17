# Session 图像存储改造计划

## 目标

将 Session 中的图像从**纯内存 base64/URL 字符串**改造为**文件系统持久化 + 元数据索引**，使：
1. Skill 脚本（`execute_script`）可直接读写图像文件
2. AI 能获取图像元数据（尺寸、格式）做智能决策
3. 图像不因 Session 过期/重启而丢失
4. 对外标识符机制 (`<user_image_1>`, `<ai_image_1>`) 完全兼容

---

## 现状分析

当前 Session 图像存储（`session.py`）：
```python
self._user_images: Dict[str, str] = {}  # {"<user_image_1>": "data:image/png;base64,..."}
self._ai_images: Dict[str, str] = {}    # {"<ai_image_1>": "https://..."}
```

**问题**：
- 纯内存，Session 清理即丢失
- value 是 base64 字符串，大图像会膨胀内存和 Token
- `execute_script` 子进程完全无法访问
- 无元数据（尺寸、格式、创建时间）

---

## 新架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      Session (session.py)                     │
│  ┌─────────────┐    ┌─────────────────────────────────────┐ │
│  │ _user_images│    │         ImageStore                  │ │
│  │ _ai_images  │───→│  ┌─────────┐  ┌─────────────────┐  │ │
│  │ (元数据索引)│    │  │ImageEntry│  │ 文件系统持久化   │  │ │
│  └─────────────┘    │  │identifier│  │ data/aichat/... │  │ │
│                     │  │file_path │  │   .meta.json    │  │ │
│                     │  │width     │  │   .png/.jpg     │  │ │
│                     │  │height    │  └─────────────────┘  │ │
│                     │  └─────────┘                         │ │
│                     └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              execute_script (工具层增强)                      │
│  注入 env["SKILL_IMAGES"] = {                                │
│      "<user_image_1>": "/bot/data/aichat/images/.../u_1.png"│
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
```

### 存储目录结构

```
data/aichat/images/
└── {session_id}/              # 原始 session_id 作为目录名
    ├── .meta.json             # 元数据索引文件
    ├── user_image_1.png
    ├── user_image_2.jpg
    ├── ai_image_1.png
    └── ai_image_2.png
```

`.meta.json` 示例：
```json
{
  "user_image_1": {
    "source": "user",
    "identifier": "<user_image_1>",
    "filename": "user_image_1.png",
    "format": "png",
    "width": 1024,
    "height": 1024,
    "size_bytes": 1250000,
    "created_at": 1713345678.0
  },
  "ai_image_1": {
    "source": "ai",
    "identifier": "<ai_image_1>",
    "filename": "ai_image_1.jpg",
    "format": "jpg",
    "width": 1536,
    "height": 1536,
    "size_bytes": 890000,
    "created_at": 1713345680.0
  }
}
```

---

## 分阶段实施计划

### 阶段 1：ImageStore 数据层（新增文件，零风险）

**新建文件**：`hoshino/modules/aichat/image_store.py`

**核心类**：
```python
@dataclass
class ImageEntry:
    identifier: str          # "<user_image_1>"
    source: str              # "user" | "ai"
    session_id: str
    filename: str
    format: str              # "png" | "jpg" | "webp"
    width: Optional[int]
    height: Optional[int]
    size_bytes: int
    created_at: float
    file_path: Path          # 绝对路径

class ImageStore:
    BASE_DIR: Path = Path("data/aichat/images")
    
    def __init__(self, session_id: str)
    async def store(self, image_data: str, source: str) -> ImageEntry
    def get(self, identifier: str) -> Optional[ImageEntry]
    def list_all(self) -> List[ImageEntry]
    def list_by_source(self, source: str) -> List[ImageEntry]
    def get_data_url(self, identifier: str) -> Optional[str]
    def get_file_path(self, identifier: str) -> Optional[Path]
    def build_image_list_text(self) -> str
    def cleanup(self, max_images: int = 20)
```

**关键设计决策**：
- `store()` 接受 base64 data URL / http URL / bytes，统一转为本地文件
- `get_data_url()` 按需从文件读取并转回 base64（保持对现有调用方的兼容）
- 用 PIL 提取 width/height，失败也不阻塞
- `.meta.json` 用 JSON 存储，简单可手动修复
- 目录名直接使用 `session_id`（如 `group_123_user_456`），便于人工排查

**验证**：运行独立单元测试，验证 store/get/data_url 流转正确。

---

### 阶段 2：Session 层适配（改造 session.py）

**保持对外接口 100% 兼容**，内部实现替换为 ImageStore。

**改动点**：

| 方法 | 当前实现 | 新实现 |
|---|---|---|
| `__init__` | `self._user_images = {}`<br>`self._ai_images = {}` | `self._image_store = ImageStore(session_id)` |
| `store_user_image(data)` | 写入 `_user_images[id] = data` | `await self._image_store.store(data, "user")` |
| `store_ai_image(data)` | 写入 `_ai_images[id] = data` | `await self._image_store.store(data, "ai")` |
| `resolve_image_identifier(id)` | 查两个 dict | `entry = store.get(id)`<br>`return store.get_data_url(id)` |
| `get_image_segment(id)` | 查 dict 后处理 | `entry = store.get(id)`<br>`从文件读取并生成 MessageSegment` |
| `build_image_list_prompt()` | 打印 dict keys | 用 `store.list_all()` 输出元数据列表 |

**兼容性注意**：
- `resolve_image_identifier` 仍返回 `str`（base64 data URL 或 URL），调用方无需修改
- `get_image_segment` 从文件读取后生成 `MessageSegment.image()`，行为不变
- `_user_images` / `_ai_images` 可保留为 `@property` 返回兼容字典，防止外部直接访问

**验证**：启动 bot，发送带图片的消息，验证 `#画一只猫` 等基础功能正常。

---

### 阶段 3：工具层适配（改造 3 个文件）

**文件 1：`chat.py`**
- `download_image_to_base64()` — **无需改动**，返回 base64 data URL
- `handle_ai_chat()` 中 `session.store_user_image(base64_image)` — **无需改动**（Session 接口不变）

**文件 2：`tools/builtin/send_images.py`**
- `_download_image_to_base64()` — **无需改动**
- `send_images()` 中 `session.store_ai_image(image_data)` — **无需改动**

**文件 3：`tools/builtin/generate_image.py`**
- 编辑分支：`session.resolve_image_identifier(identifier)` — **无需改动**（返回 data URL）
- 生成分支：`session.store_ai_image(url)` — **无需改动**

> 由于 Session 对外接口保持兼容，工具层理论上零改动。但实际测试中发现性能问题（反复从文件读 base64）再考虑优化。

**验证**：
- 测试 `generate_image` 的纯生成模式
- 测试 `generate_image` 的编辑模式（传入 `image_identifiers`）
- 测试 `send_images` 下载外部图片

---

### 阶段 4：execute_script 增强（改造 1 个文件）

**文件**：`tools/builtin/execute_script.py`

**新增逻辑**（在构建子进程环境变量之前）：
```python
# 注入当前会话的图片路径映射
if session:
    image_map = {}
    for entry in session.list_images():  # 新增 Session 方法
        image_map[entry.identifier] = str(entry.file_path)
    if image_map:
        env["SKILL_IMAGES"] = json.dumps(image_map)
```

**新增 Session 方法**（`session.py`）：
```python
def list_images(self) -> List[ImageEntry]:
    """列出当前会话所有图片（供 Skill 脚本使用）"""
    return self._image_store.list_all()
```

**验证**：
编写测试 Skill 脚本：
```python
import os, json, sys
images = json.loads(os.environ.get("SKILL_IMAGES", "{}"))
for id, path in images.items():
    print(f"{id} -> {path} exists={os.path.exists(path)}")
```
AI 调用 `execute_script` 执行后，确认输出包含正确的文件路径。

---

### 阶段 5：image_generation Skill（新增目录）

**新建目录**：`hoshino/modules/aichat/skills/image_generation/`

**文件清单**：
```
image_generation/
├── SKILL.md          # 提示词指导 + 模型选择策略
├── _meta.json        # allowed_tools: ["generate_image"]
└── scripts/          # （预留，阶段 5 暂空或只放 prompt_enhance.py）
```

**SKILL.md 核心内容**：
- 何时激活：用户要求画图、生图、编辑图片、改图
- 提示词工程指导：风格词、构图词、负面词模板
- 模型选择策略：快速→Gemini，高质量→OpenAI/DALL-E 3，特定风格→ComfyUI
- 尺寸/比例建议：人物 3:4、风景 16:9、头像 1:1
- 图像编辑指导：如何引用 `<user_image_N>` 和 `<ai_image_N>`

**_meta.json**：
```json
{
  "name": "image_generation",
  "description": "AI 图像生成与编辑，支持文生图、图生图、风格转换",
  "allowed_tools": ["generate_image"],
  "user_invocable": true,
  "disable_model_invocation": false
}
```

> **注意**：`generate_image` 仍作为全局工具保留。Skill 激活后，AI 获得更详细的指导内容，但工具调用路径不变。

**验证**：
- 用户发送"#画一只猫"，观察 AI 是否自动激活 `image_generation` Skill
- 检查系统消息中是否注入了 Skill 指导内容

---

### 阶段 6：验证与清理

**端到端验证清单**：

| 场景 | 操作 | 预期结果 |
|---|---|---|
| 基础生图 | `#画一只猫` | 正常生成图片，标识符 `<ai_image_1>` 正确 |
| 图像编辑 | `#把这张图变成赛博朋克风格`（带图） | 读取 `<user_image_1>`，编辑后返回 `<ai_image_2>` |
| 多模态识别 | `#描述这张图`（带图，多模态模型） | 图片正常存入文件，多模态消息正常构建 |
| send_images | `#发几张猫图`（setu skill 等） | 外部图片下载后存入文件，正常发送 |
| Skill 脚本访问 | `#使用 image_generation` + 脚本调用 | 脚本 env 中 `SKILL_IMAGES` 包含正确路径 |
| Session 过期重建 | 重启 bot，相同用户继续对话 | 历史图片丢失（预期），但当前会话图片持久 |
| 并发 | 多个用户同时发图 | 各 session 目录隔离，无冲突 |

**清理项**：
- 删除 Session 中 `_user_images` / `_ai_images` 的冗余兼容代码（确认无外部引用后）
- 添加 `.gitignore` 排除 `data/aichat/images/`

---

## 改动文件汇总

| 文件 | 操作 | 阶段 | 风险 |
|---|---|---|---|
| `image_store.py` | 新增 | 1 | 零风险 |
| `session.py` | 改造 | 2 | **中**（核心模块，影响所有功能） |
| `execute_script.py` | 增强 | 4 | 低 |
| `skills/image_generation/` | 新增 | 5 | 零风险 |
| `chat.py` | 适配验证 | 3 | 理论零改动 |
| `tools/builtin/generate_image.py` | 适配验证 | 3 | 理论零改动 |
| `tools/builtin/send_images.py` | 适配验证 | 3 | 理论零改动 |

**总计**：新增 2 个文件，改造 2 个文件，验证 3 个文件，新增 1 个 Skill 目录。

---

## 风险与回滚策略

| 风险 | 等级 | 回滚方案 |
|---|---|---|
| ImageStore 文件写入失败（权限/磁盘满） | 中 | `store()` 捕获异常，降级为内存存储 + 告警日志 |
| Session 改造后 resolve_image_identifier 返回 None | 高 | 立即回滚 `session.py`，恢复旧的双 dict 实现 |
| PIL 提取元数据失败（损坏图片） | 低 | `store()` 中 width/height 设为 None，不影响主流程 |
| 目录名含特殊字符导致文件系统错误 | 低 | `session_id` 格式是固定的 `group_N_user_M` / `private_N`，无特殊字符 |
| 图片文件累积占满磁盘 | 低 | `.meta.json` 配合 `cleanup()` 方法，后续可加定时清理任务 |

---

## 性能考量

| 场景 | 改造前 | 改造后 | 影响 |
|---|---|---|---|
| 存储图片 | 内存 dict 插入 O(1) | 文件写入 + PIL 解析 | 增加 ~50-200ms，可接受 |
| resolve_image_identifier | 内存 dict 查询 O(1) | 查 `.meta.json` + 文件读取转 base64 | 增加 ~5-20ms，可接受 |
| build_image_list_prompt | 拼接字符串 | 读 JSON + 拼接 | 几乎无影响 |
| 消息历史中的 base64 | 完整 base64 在 messages 中传输 | **不变**，messages 仍存 base64 | 无变化 |

> 消息历史中的 base64 不会因本次改造而减少，因为 `add_message` 时已经把 base64 放进去了。后续可考虑在消息历史中只存标识符，但那是另一个更大的改造。

---

## 下一步

确认计划后，按阶段 1 → 6 顺序执行。每阶段完成后做验证，通过后再进入下一阶段。
