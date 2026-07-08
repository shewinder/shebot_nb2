---
name: qbittorrent
description: 管理已有 qBittorrent 下载任务。用于查看任务进度、查询分类、暂停、恢复、删除、重校验和修改分类
---

# qBittorrent 管理

管理 NAS 上运行的 qBittorrent 下载任务，重点用于查看、暂停、恢复、删除、重校验和修改分类。

本 Skill 当前不替代 `magnet-download` 和 `pt-download` 的添加流程；磁力下载和 PT 下载仍按各自原有 Skill 执行。

## 配置

通过环境变量读取 qBittorrent Web UI 配置：

- `PT_QB_URL`：qBittorrent Web UI 地址，例如 `http://127.0.0.1:8080`
- `PT_QB_USERNAME`：用户名，默认 `admin`
- `PT_QB_PASSWORD`：密码
- `PT_QB_SAVE_PATH`：默认保存路径，默认 `/downloads`
- `PT_QB_VERIFY_SSL`：是否校验 SSL，默认 `false`

## 常用流程

1. 用户询问下载进度或任务状态时，调用 `list` 或 `status`。
2. 用户要按名称找任务时，只能用 `list --search 关键词` 筛选。
3. 用户要删除、暂停、恢复、重校验、改分类时，先通过 `list` 或 `status` 确认目标任务 hash。
4. 删除任务前必须让用户明确确认；未确认时不要调用 `delete`。
5. 删除本地文件风险更高，只有用户明确要求删除文件时才传 `--delete-files`。

## 脚本调用

### 获取分类

```python
execute_script(skill_name="qbittorrent", script_path="scripts/qb.py", args=["categories"])
```

### 查看任务

```python
execute_script(skill_name="qbittorrent", script_path="scripts/qb.py", args=["list"])
execute_script(skill_name="qbittorrent", script_path="scripts/qb.py", args=["list", "--filter", "downloading"])
execute_script(skill_name="qbittorrent", script_path="scripts/qb.py", args=["list", "--search", "关键词"])
execute_script(skill_name="qbittorrent", script_path="scripts/qb.py", args=["status", "--hash", "任务hash"])
```

### 管理任务

```python
execute_script(skill_name="qbittorrent", script_path="scripts/qb.py", args=["pause", "--hash", "任务hash"])
execute_script(skill_name="qbittorrent", script_path="scripts/qb.py", args=["resume", "--hash", "任务hash"])
execute_script(skill_name="qbittorrent", script_path="scripts/qb.py", args=["recheck", "--hash", "任务hash"])
execute_script(skill_name="qbittorrent", script_path="scripts/qb.py", args=["set-category", "--hash", "任务hash", "--category", "电影"])
```

删除任务必须加 `--confirm`，且必须先得到用户明确确认：

```python
execute_script(skill_name="qbittorrent", script_path="scripts/qb.py",
               args=["delete", "--hash", "任务hash", "--confirm"])
```

删除本地文件需要额外传 `--delete-files`：

```python
execute_script(skill_name="qbittorrent", script_path="scripts/qb.py",
               args=["delete", "--hash", "任务hash", "--delete-files", "--confirm"])
```

## 注意事项

- 当前不要用本 Skill 接管磁力或 PT 的添加流程。
- 脚本只输出紧凑文本，不提供 JSON 输出，避免下载列表过大时被工具截断。
- `--search` 只用于 `list`，不要用于 `delete`、`pause`、`resume`、`recheck`、`set-category`。
- 列表每行会显示短 hash，管理命令可直接使用该短 hash；脚本会先解析为完整 hash，匹配不到或匹配多个时不会执行操作。
- `--hash` 支持一次传多个，也可重复传；例如 `--hash a b c`、`--hash a --hash b`、`--hash "a,b,c"`。
- 删除任务是破坏性操作，必须先让用户明确确认。
- 如果脚本返回 qBittorrent 未配置，提示用户检查 `PT_QB_URL`、`PT_QB_USERNAME`、`PT_QB_PASSWORD`。
