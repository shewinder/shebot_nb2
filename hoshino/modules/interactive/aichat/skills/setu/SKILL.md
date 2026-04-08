---
name: setu
description: 当用户请求色图/插画时激活，调用API获取并发送图片
allowed-tools:
  - "fetch_url"
  - "send_images"
  - "read_file"
user-invocable: true
disable-model_invocation: false
---

# 色图/插画 SKILL

## 功能

获取高质量二次元插画，支持关键词搜索和随机推荐

## API 接口

### 1. Lolicon API（随机/关键词）

**接口**: `https://api.lolicon.app/setu`

参数：
- `r18`: 0(全年龄) / 1(R18) / 2(混合)
- `keyword`: 搜索关键词（可选）
- `num`: 数量（1-10，建议3-5）
- `size1200`: true（使用中等尺寸）

**响应字段**：
- `data[].title`: 作品标题
- `data[].author`: 作者名
- `data[].pid`: Pixiv ID
- `data[].tags`: 标签数组
- `data[].urls.original`: 原图URL
- `data[].r18`: 是否R18

**图片代理**: 将 `i.pixiv.re` 替换为 `pixiv.shewinder.win`

### 2. Yande.re API（高质量图库）

**接口**: `https://yande.shewinder.win/post.json`

参数：
- `tags`: 标签（空格分隔，用 `+` 编码）
- `limit`: 返回数量（默认20，最大100）
- `order:score`: 按质量分数排序

**响应字段**：
- `id`: 作品ID
- `tags`: 空格分隔的标签字符串
- `author`: 上传者
- `file_url`: 图片URL
- `rating`: s/q/e (safe/questionable/explicit)
- `score`: 质量分数

**特点**：
- 图片质量普遍较高
- 支持复杂标签组合搜索
- 标签需使用英文

**标签翻译**：Yande 标签需为英文，AI 自行将中文关键词翻译为英文标签

**图片代理**：Yande 返回的图片 URL 域名需替换为 `files.shewinder.win`，例如：
- 原始：`https://files.yande.re/image/xxx/yyy.jpg`
- 替换后：`https://files.shewinder.win/image/xxx/yyy.jpg`

---

## 场景 1: 随机色图

**用户**: "来点色图"、"来张图"

**AI 执行**:
1. `fetch_url` 调用 API 获取随机图（**r18=2**, num=5）
2. `send_images` 下载并准备图片（自动反和谐）
3. 回复带图片和作品信息

**回复示例**：
```
找到几张好看的图喵～

1. 🎨 作品标题 <ai_image_1>
   👤 作者：作者名
   🏷️ 标签：少女、兽耳、治愈

2. 🎨 作品标题 <ai_image_2>
   👤 作者：作者名
   🏷️ 标签：泳装、夏日
```

---

## 场景 2: 关键词搜索

**用户**: "来份猫耳色图"、"想要少女壁纸"

**AI 执行**:
1. 提取关键词（如"猫耳"、"少女"）
2. **选择API**：
   - 普通搜索 → Lolicon API（keyword=猫耳, **r18=2**, num=5）
   - 追求高质量/多标签 → Yande API（AI翻译为 cat_ears+order:score）
3. `fetch_url` 调用 API
4. `send_images` 发送结果
5. 如无结果，提示换关键词或尝试 Yande

**回复示例**：
```
在找「猫耳」主题的图呢，找到这些喵～

1. 🎨 猫耳少女 <ai_image_1>
   👤 作者：作者名
   🏷️ 猫耳、女仆装、蓝发
```

**提示**：如果 Lolicon 结果不满意，可以尝试说"yande 猫耳"获取更高质量的图（Yande 标签需用英文，如 "yande cat_ears"）

---

## 场景 3: 结合用户画像推荐

**用户**: "推荐点我喜欢的"

**AI 执行**:
1. `read_file` 读取用户画像（`aichat/preferences/{user_id}.md`）
2. 从画像提取高频标签（如"兽耳"、"蓝发"）
3. **选择API**：
   - 简单标签/随机推荐 → Lolicon API
   - 多标签组合/追求高质量 → Yande API
4. `fetch_url` 调用搜索（**r18=2**）
5. 匹配度高的优先展示

**回复示例**：
```
根据主人喜欢的「兽耳+少女」组合，找到这些喵～

1. 🎨 作品标题 <ai_image_1>
   👤 作者：作者名
   💕 匹配偏好：兽耳、少女、治愈
```

**API 选择建议**：
| 情况 | 推荐API | 原因 |
|------|--------|------|
| 单标签/随机 | Lolicon | 简单易用，结果多样 |
| 多标签组合 | Yande | 支持复杂标签查询 |
| 追求高分辨率 | Yande | 图片质量普遍更高 |
| 需要R18混合 | Lolicon | r18=2参数支持更好 |

---

## 场景 4: Yande 高质量搜索

**用户**: "yande 少女"、"yande 猫耳+泳装"

**AI 执行**：
1. 解析标签（如 `["少女", "泳装"]`）
2. **AI 翻译**：将中文标签翻译为英文（如 少女→girl, 猫耳→cat_ears）
3. `fetch_url` 调用 Yande API（`tags=girl+swimsuit+order:score`, limit=20）
4. 按 `score` 排序，选择高分作品
5. `send_images` 发送（最多2张，避免刷屏）

**常见标签对照**：
| 中文 | 英文标签 |
|------|---------|
| 少女 | girl / teenage |
| 猫耳 | cat_ears |
| 兽耳 | animal_ears |
| 泳装 | swimsuit |
| 女仆装 | maid |
| 蓝发 | blue_hair |
| 双马尾 | twintails |

**回复示例**：
```
从 Yande 高质量图库找到这些喵～（搜索标签：girl, swimsuit）

1. 🎨 Yande 精选 <ai_image_1>
   👤 上传者：用户名
   ⭐ 质量分：95
   🏷️ 标签：catgirl, swimsuit, summer
```

**特点**：
- 图片分辨率普遍更高
- 适合找特定组合标签（如"cat_ears+swimsuit"）
- 默认按质量排序

---

## 场景 5: R18 内容

**用户**: "来点涩的"、"r18"

**AI 执行**:
1. ⚠️ 确认环境（群聊需检查配置，私聊默认可行）
2. `fetch_url` 调用 API（r18=1, num=3）
3. `send_images` 发送

**注意**：群聊中R18需确认群配置，建议私聊使用

---

## 通用规则

### R18 参数设置

**默认策略**：如果用户未明确说明是否需要 R18，**r18 参数设置为 2（混合）**

| 用户输入 | r18 参数 | 说明 |
|---------|---------|------|
| 未提及 R18 | `2` | 混合模式（默认） |
| "来点涩的"/"r18" | `1` | 仅 R18 |
| "正常图"/"不要涩" | `0` | 仅全年龄 |

### 图片处理
- **Lolicon**: `i.pixiv.re` → `pixiv.shewinder.win`
- **Yande**: `files.yande.re` → `files.shewinder.win`
- 使用 `send_images` 下载，自动反和谐
- 引用返回的 `<ai_image_N>` 标识符

### 失败处理
- API 无结果："没有找到呢，换个关键词试试？"
- 下载失败：跳过该图，继续发送其他

### API 选择指南

| 场景 | 推荐 API | 原因 |
|------|---------|------|
| 随机/单关键词 | Lolicon | 简单快速，支持中文标签 |
| 多标签组合 | Yande | 支持 `tag1+tag2+tag3` 复杂查询 |
| 追求高分辨率 | Yande | 图片质量普遍更高，文件更大 |
| 需要R18混合 | Lolicon | `r18=2` 参数更灵活 |
| 大量结果 | Yande | limit 最大支持 100 |

### 回复风格
- 包含作品标题、作者、标签
- 关键词搜索时说明匹配理由
- Yande 结果标注来源（"Yande 精选"）
