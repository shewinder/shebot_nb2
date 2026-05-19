---
name: magnet-download
description: 下载磁力链接到 NAS 的 qBittorrent。用户发送 magnet 链接、"下载这个磁力"、"帮我下载" 附带磁力链接时激活
---

# 磁力链接下载

将磁力链接添加到 NAS 上运行的 qBittorrent 下载任务。

## 工作流程

1. 用户发送 magnet 链接或要求下载磁力
2. **在当前对话中直接调用 `magnet_add.py` 添加下载任务**（秒级完成，不需要后台）
3. 添加成功后，**使用 `run_background_task`（action=start）提交后台监控任务**
   - task_description 示例："监控 qBittorrent 中磁力链接 magnet:?xt=urn:btih:xxx 的下载进度，每2分钟检查一次，完成后汇报文件信息（文件名、大小、路径）"
4. 告知用户"已添加下载任务，完成后通知你"
5. 后台任务中通过 `schedule_continuation` 定时查进度 → 完成后汇报

## 脚本调用

### 添加磁力下载

```python
execute_script(skill_name="magnet-download", script_path="scripts/magnet_add.py",
               args=["--url", "magnet:?xt=urn:btih:xxx"])
```

可选指定保存路径和分类：

```python
execute_script(skill_name="magnet-download", script_path="scripts/magnet_add.py",
               args=["--url", "magnet:?xt=urn:btih:xxx", "--save-path", "/downloads/movie", "--category", "movie"])
```

### 查看下载进度

```python
execute_script(skill_name="magnet-download", script_path="scripts/magnet_add.py",
               args=["--list"])
```

## 交互示例

```
用户：magnet:?xt=urn:btih:abc123...
AI：[执行 magnet_add.py - 当前对话完成]
    ✅ 已添加下载任务
    📁 保存路径: /downloads
    然后调用 run_background_task 提交后台监控
    🔍 将在后台监控下载进度，完成后通知你

[几分钟后，下载完成，自动推送通知]

AI：  📋 后台任务执行完成
     任务: 监控 qBittorrent 中...的下载进度
     ✅ 下载完成
     📁 文件名: Ubuntu 22.04 ISO
     📦 大小: 4.7 GB
     📂 路径: /downloads/Ubuntu 22.04 ISO
```

## 注意事项

- **必须通过 `run_background_task` 提交下载**，下载是耗时操作，不应阻塞当前对话
- 磁力链接以 `magnet:?xt=` 开头，长度可能超过 2000 字符，需要完整传递
- 如果脚本返回 "qBittorrent 未启用"，告知用户检查 `data/config/ptdownload.json`
- 下载路径默认为 qBittorrent 配置中的默认路径，可通过 `--save-path` 覆盖
- 首次使用前需要在 NAS 上安装并配置 qBittorrent
