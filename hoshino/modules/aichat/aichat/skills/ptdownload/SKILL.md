---
name: pt-download
description: 搜索 PT 站资源并添加到 qBittorrent 下载，或查看下载进度。当用户想看/下载影视、动漫等资源（如"我想看xxx电影"、"帮我下载xxx"），或查询下载进度（如"查看下载"、"下载进度"、"qb状态"）时使用
---

# PT 下载

搜索 PT 站影视资源并添加到 qBittorrent。

## 可用站点

| 站点 | 脚本 | 方式 |
|------|------|------|
| M-Team | `search_mteam.py` | API（搜索 + 下载） |
| 北洋园 | `search_tjupt.py` | 网页抓取 |
| audiences | `search_audiences.py` | 网页抓取 |

## 工作流程

1. **获取分类**：先调用 `qb_add.py --list-categories` 获取 qb 可用分类
2. **搜索**：对每个站点执行搜索脚本
3. **选择**：汇总结果展示给用户（标注站点来源）
4. **添加**：用户选择后，调用站点脚本的 `--add` 模式（一步完成下载种子 + 提交 qb），分类由 Agent 从搜索结果的资源类型判断
5. **监控**：添加成功后，使用 `run_background_task` 提交后台监控

## 脚本调用

### 获取 qb 分类

```python
execute_script(skill_name="pt-download", script_path="scripts/qb_add.py", args=["--list-categories"])
```

### 搜索资源

```python
# M-Team（默认搜全部内容，可带 --free 仅免费种）
execute_script(skill_name="pt-download", script_path="scripts/search_mteam.py", args=["关键词"])
execute_script(skill_name="pt-download", script_path="scripts/search_mteam.py", args=["--free", "关键词"])

# 北洋园
execute_script(skill_name="pt-download", script_path="scripts/search_tjupt.py", args=["关键词"])

# audiences
execute_script(skill_name="pt-download", script_path="scripts/search_audiences.py", args=["关键词"])
```

### 添加下载

```python
# 站点脚本一步完成（下载种子 + 提交 qb，支持批量）
execute_script(skill_name="pt-download", script_path="scripts/search_mteam.py", args=["--add", "123", "456", "--category", "电影"])
execute_script(skill_name="pt-download", script_path="scripts/search_tjupt.py", args=["--add", "下载链接", "--category", "电影"])

# 已有本地种子文件
execute_script(skill_name="pt-download", script_path="scripts/qb_add.py", args=["--file", "路径", "--category", "电影"])
```

### 查看下载进度

```python
# 查看全部
execute_script(skill_name="pt-download", script_path="scripts/qb_list.py")

# 按名称搜索
execute_script(skill_name="pt-download", script_path="scripts/qb_list.py", args=["--search", "关键词"])
```

## 注意事项

- 必须向用户展示资源来源站点（如 `[北洋园]`、`[M-Team]`）
- M-Team 支持 `--free` 仅搜索免费种，也支持按种子 ID 下载
- 下载前应先调用 `--list-categories` 获取 qb 当前分类列表
