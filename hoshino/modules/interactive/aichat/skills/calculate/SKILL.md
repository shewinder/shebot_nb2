---
name: calculate
description: 执行安全数学计算的 SKILL，支持基础运算和复杂表达式
allowed-tools:
  - "Bash(python scripts/*)"
  - "Read"
user-invocable: true
disable-model-invocation: false
---

# Calculate SKILL

## 功能

执行安全的数学计算，支持：
- 基础运算：加减乘除、幂运算
- 复杂表达式：支持括号优先级
- 数学函数：abs, round, max, min 等

## 使用方法

当用户需要计算时，使用 Bash 工具调用 calculate.py 脚本：

```bash
python scripts/calculate.py "表达式"
```

## 示例

```bash
python scripts/calculate.py "15 * 23"
python scripts/calculate.py "(100 + 200) / 3"
python scripts/calculate.py "2 ** 10"
```

## 输出格式

脚本返回 JSON 格式：
```json
{
  "success": true,
  "result": 345,
  "expression": "15 * 23"
}
```

## 注意事项

1. 表达式中不要包含等号
2. 脚本会自动处理除零等错误
3. 不支持赋值操作（如 x = 5）
