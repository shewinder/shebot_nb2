---
name: pt-download
description: 搜索 PT 站资源并添加到 qBittorrent 下载。当用户搜索电影/电视剧、或说"想看 xxx"、"下载 xxx"时使用。
allowed-tools:
  - "execute_script"
user-invocable: true
---

# PT 下载

搜索 PT 站影视资源并添加到 qBittorrent。

## 工作流程

1. **搜索**: 用户说想看某部电影/电视剧时，执行搜索脚本
2. **选择**: 向用户展示搜索结果（序号、标题、大小、做种数、来源）
3. **下载**: 用户说"下载第N个"时，从搜索结果提取对应链接，执行下载脚本

## 脚本调用

### 搜索资源

```python
execute_script(skill_name="pt-download", script_path="scripts/pt_search.py", args=["关键词"])
```

**输出格式**:
```
🔍 搜索到 N 个资源：

1. 资源标题 ⭐
   大小: X GB | 做种: N | 来源: 站点名
   下载链接: https://xxx/download.php?id=123

2. ...
```

### 添加下载

用户选择序号后，从搜索结果中提取对应下载链接：

```python
execute_script(skill_name="pt-download", script_path="scripts/qb_add.py", args=["--url", "下载链接"])
```

### 查看下载进度

```python
execute_script(skill_name="pt-download", script_path="scripts/qb_list.py")
```

## 交互示例

```
用户：我想看奥本海默
AI：[执行 pt_search.py "奥本海默"]
    🔍 找到3个结果：
    1. Oppenheimer.2023.1080p... (18GB) | 做种: 45 | 来源: 馒头 ⭐
    2. Oppenheimer.2023.2160p... (52GB) | 做种: 23 | 来源: 天雪
    3. ...
    回复"下载第N个"选择

用户：下载第1个
AI：[提取第1条的下载链接 https://...]
    [执行 qb_add.py --url https://...]
    ✅ 已添加下载
```

## 注意事项

- 搜索结果每行末尾包含"下载链接: xxx"，用于提取
- 推荐标记 ⭐ 表示资源质量较好（做种多、大小适中）
- 如脚本返回"qBittorrent 未启用"，告知用户检查 `data/config/ptdownload.json`
- 如脚本返回"Cookie 失效"，告知用户 PT 站 Cookie 需要更新
