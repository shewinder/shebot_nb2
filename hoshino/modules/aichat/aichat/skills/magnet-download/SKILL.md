---
name: magnet-download
description: 下载磁力链接到 NAS 的 qBittorrent。用户发送 magnet 链接、"下载这个磁力"、"帮我下载" 附带磁力链接时激活
allowed-tools:
  - "execute_script"
user-invocable: true
---

# 磁力链接下载

将磁力链接添加到 NAS 上运行的 qBittorrent 下载任务。

## 工作流程

1. 用户发送 magnet 链接或要求下载磁力
2. 调用 `magnet_add.py` 将磁力链接添加到 qBittorrent
3. 返回添加结果

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
AI：  🔗 正在添加磁力链接到 NAS...
      ✅ 已添加下载任务
      📁 保存路径: /downloads
      💡 发送「查看下载」可查看进度

用户：查看下载
AI：  📊 下载列表
      1. Ubuntu 22.04 ISO | 45.2% | 3.2 MB/s | 剩余 8分钟
      2. Debian 12 ISO   | 100%  | 已完成
```

## 注意事项

- 磁力链接以 `magnet:?xt=` 开头，长度可能超过 2000 字符，需要完整传递
- 如果脚本返回 "qBittorrent 未启用"，告知用户检查 `data/config/ptdownload.json`
- 下载路径默认为 qBittorrent 配置中的默认路径，可通过 `--save-path` 覆盖
- 首次使用前需要在 NAS 上安装并配置 qBittorrent
