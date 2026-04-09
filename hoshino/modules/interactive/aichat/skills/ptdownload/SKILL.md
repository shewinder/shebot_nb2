---
name: pt-download
description: 搜索 PT 站资源并添加到 qBittorrent 下载。当用户表达想看/下载影视、动漫、纪录片、音乐等资源意图时使用，例如"我想看xxx电影"、"帮我下载xxx剧"、"搜索xxx纪录片"等。AI 需要根据用户请求判断资源类型并传入对应分类数。
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

1. 资源标题 ⭐
   大小: X GB | 做种: N | 来源: 站点名
   下载链接: https://xxx/download.php?id=123

2. ...
```

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
    1. Oppenheimer.2023.1080p... (18GB) | 做种: 45
    2. ...
    回复序号下载

用户：下载第1个
AI：[执行 qb_add.py --category movie]
    ✅ 已添加下载任务
    🏷️ 分类: 电影
```

## 注意事项

- 搜索结果每行末尾包含"下载链接: xxx"，用于提取
- 推荐标记 ⭐ 表示资源质量较好（做种多、大小适中）
- 如脚本返回"qBittorrent 未启用"，告知用户检查 `data/config/ptdownload.json`
- 如脚本返回"Cookie 失效"，告知用户 PT 站 Cookie 需要更新
