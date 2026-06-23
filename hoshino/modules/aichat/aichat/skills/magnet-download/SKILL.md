---
name: magnet-download
description: 下载磁力链接到 NAS 的 qBittorrent。用户发送 magnet 链接、"下载这个磁力"、"帮我下载" 附带磁力链接时激活
---

# 磁力链接下载

将磁力链接添加到 NAS 上运行的 qBittorrent 下载任务。

## 工作流程

1. 用户发送 magnet 链接/hash 或要求下载磁力
2. **先调用 `analyze.py` 验车**，脚本会自动下载截图并存入 ImageStore，返回 `<ai_image_N>` 标识符
3. 向用户展示验车结果（文字信息 + 截图标识符），等用户确认是否下载
4. 用户确认后，**调用 `magnet_add.py` 添加下载任务**
5. 添加成功后，提交后台监控任务（通过 `run_background_task`）
6. 告知用户"已添加下载任务，完成后通知你"

## 脚本调用

### 验车（必须先执行）

```python
execute_script(skill_name="magnet-download", script_path="scripts/analyze.py",
               args=["magnet:?xt=urn:btih:xxx"])
```

返回种子名称、大小、文件数、类型，以及 `screenshots` 数组（含 `<ai_image_N>` 标识符，图片已自动存储好，可直接引用）。

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
AI：[调用 analyze.py 验车]

    🔍 验车结果
    种子名称: Some.Movie.2024.1080p.BluRay
    文件类型: video-mkv
    总大小: 8.50 GB
    文件数: 3
    Hash: abc123...
    📸 截图: <ai_image_1> <ai_image_2> <ai_image_3>

    要下载吗？

用户：下载
AI：[调用 magnet_add.py 添加任务]
    ✅ 已添加下载任务，完成后通知你
```

## 注意事项

- **必须先验车再下载**，让用户看到种子内容后确认
- 磁力链接以 `magnet:?xt=` 开头，长度可能超过 2000 字符，需要完整传递
- 如果脚本返回 "qBittorrent 未配置"，告知用户检查 PT_QB_URL 等环境变量
- 下载路径默认为 qBittorrent 配置中的默认路径，可通过 `--save-path` 覆盖
