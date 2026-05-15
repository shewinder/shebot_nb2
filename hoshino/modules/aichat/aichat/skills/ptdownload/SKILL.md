---
name: pt-download
description: 搜索 PT 站资源并添加到 qBittorrent 下载，或查看下载进度。当用户想看/下载影视、动漫等资源（如"我想看xxx电影"、"帮我下载xxx"），或查询下载进度（如"查看下载"、"下载进度"、"qb状态"）时使用
allowed-tools:
  - "execute_script"
  - "run_background_task"
  - "schedule_continuation"
user-invocable: true
---

# PT 下载

搜索 PT 站影视资源并添加到 qBittorrent，支持按类型保存到不同目录。

## 工作流程

1. **搜索**: 用户说想看某资源时，执行搜索脚本（快速操作，直接在当前对话完成）
2. **选择**: 向用户展示搜索结果
3. **添加**: 用户选择序号后，**在当前对话中直接调用 `qb_add.py` 添加下载**（秒级完成，不需要后台）
4. **监控**: 添加成功后，**使用 `run_background_task`（action=start）提交后台监控任务**
   - task_description 示例："监控 qBittorrent 中「Oppenheimer.2023.1080p...」的下载进度，每3分钟检查一次，完成后汇报文件信息（文件名、大小、路径）"
5. 告知用户"已添加下载任务，完成后通知你"
6. 后台任务中通过 `schedule_continuation` 定时查进度 → 完成后汇报

## category 参数

下载脚本支持以下分类：

- `movie` - 电影
- `tv` - 电视剧
- `anime` - 动漫
- `r18` - 成人向

## 脚本调用

### 搜索资源

```python
execute_script(skill_name="pt-download", script_path="scripts/pt_search.py", args=["关键词"])
```

**输出格式**:
```
🔍 搜索到 N 个资源：

1. [站点名] 资源标题 ⭐
   大小: X GB | 做种: N
   下载链接: https://xxx/download.php?id=123

2. ...
```

**重要**: 向用户展示搜索结果时，**必须显示资源来源站点**（如 `[北洋园]`、`[audiences]`），方便用户知道资源来自哪个 PT 站。

### 添加下载

用户选择序号后，从搜索结果中提取对应下载链接：

```python
execute_script(skill_name="pt-download", script_path="scripts/qb_add.py", 
               args=["--url", "下载链接", "--title", "资源标题", "--category", "movie"])
```

### 查看下载进度

```python
execute_script(skill_name="pt-download", script_path="scripts/qb_list.py")
```

## 交互示例

```
用户：我想看奥本海默
AI：[执行搜索 - 当前对话完成]
    🔍 找到3个结果：
    1. [北洋园] Oppenheimer.2023.1080p... (18GB) | 做种: 45
    2. [audiences] Oppenheimer.2023.2160p... (45GB) | 做种: 12
    3. [北洋园] Oppenheimer.2023.1080p... (15GB) | 做种: 8
    回复序号下载

用户：下载第1个
AI：[执行 qb_add.py - 当前对话完成]
    ✅ 已添加下载任务
    🏷️ 分类: 电影
    📌 来源: 北洋园
    然后调用 run_background_task 提交后台监控
    🔍 将在后台监控下载进度，完成后通知你

[几分钟后，下载完成，自动推送通知]

AI：  📋 后台任务执行完成
     任务: 监控 qBittorrent 中「Oppenheimer.2023.1080p...」的下载进度
     ✅ 下载完成
     📁 文件名: Oppenheimer.2023.1080p.BluRay.x264
     📦 大小: 18 GB
     📂 路径: /downloads/movie/Oppenheimer.2023.1080p.BluRay.x264
```

## 注意事项

- **必须向用户展示资源来源站点**（格式: `[站点名]`），让用户知道资源来自哪个 PT 站
- 搜索结果每行末尾包含"下载链接: xxx"，用于提取
- 推荐标记 ⭐ 表示资源质量较好（做种多、大小适中）
- 如脚本返回"qBittorrent 未启用"，告知用户检查 `data/config/ptdownload.json`
- 如脚本返回"Cookie 失效"，告知用户 PT 站 Cookie 需要更新
