---
name: pt-download
description: 搜索 PT 站资源并添加到 qBittorrent 下载，或查看下载进度。当用户想看/下载影视、动漫等资源（如"我想看xxx电影"、"帮我下载xxx"），或查询下载进度（如"查看下载"、"下载进度"、"qb状态"）时使用
allowed-tools:
  - "execute_script"
user-invocable: true
---

# PT 下载

搜索 PT 站影视资源并添加到 qBittorrent，支持按类型保存到不同目录。

## 工作流程

1. **搜索**: 用户说想看某资源时，执行搜索脚本
2. **选择**: 向用户展示搜索结果
3. **下载**: 用户选择序号后，判断资源类型，调用下载脚本时传入 `--category` 参数

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
AI：[执行搜索]
    🔍 找到3个结果：
    1. [北洋园] Oppenheimer.2023.1080p... (18GB) | 做种: 45
    2. [audiences] Oppenheimer.2023.2160p... (45GB) | 做种: 12
    3. [北洋园] Oppenheimer.2023.1080p... (15GB) | 做种: 8
    回复序号下载

用户：下载第1个
AI：[执行 qb_add.py --category movie]
    ✅ 已添加下载任务
    🏷️ 分类: 电影
    📌 来源: 北洋园
```

## 注意事项

- **必须向用户展示资源来源站点**（格式: `[站点名]`），让用户知道资源来自哪个 PT 站
- 搜索结果每行末尾包含"下载链接: xxx"，用于提取
- 推荐标记 ⭐ 表示资源质量较好（做种多、大小适中）
- 如脚本返回"qBittorrent 未启用"，告知用户检查 `data/config/ptdownload.json`
- 如脚本返回"Cookie 失效"，告知用户 PT 站 Cookie 需要更新
