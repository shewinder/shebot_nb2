#!/usr/bin/env python3
"""
计算器工具脚本
执行基础数学运算 - 使用 AST 安全计算
"""
import ast
import json
import sys
import argparse
from typing import Any


class SafeEvaluator(ast.NodeVisitor):
    """安全的 AST 表达式求值器"""
    
    ALLOWED_OPS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b if b != 0 else float('inf'),
        ast.Pow: lambda a, b: a ** b,
        ast.Mod: lambda a, b: a % b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.USub: lambda a: -a,
        ast.UAdd: lambda a: +a,
    }
    
    ALLOWED_CALLS = {
        'abs', 'round', 'max', 'min', 'sum', 'len',
        'int', 'float', 'str',
    }
    
    def __init__(self):
        self.result = None
    
    def visit_BinOp(self, node: ast.BinOp) -> Any:
        """处理二元操作符"""
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_type = type(node.op)
        
        if op_type not in self.ALLOWED_OPS:
            raise ValueError(f"不支持的操作符: {op_type.__name__}")
        
        return self.ALLOWED_OPS[op_type](left, right)
    
    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        """处理一元操作符"""
        operand = self.visit(node.operand)
        op_type = type(node.op)
        
        if op_type not in self.ALLOWED_OPS:
            raise ValueError(f"不支持的一元操作符: {op_type.__name__}")
        
        return self.ALLOWED_OPS[op_type](operand)
    
    def visit_Num(self, node: ast.Num) -> Any:
        """处理数字（Python 3.7 及以下）"""
        return node.n
    
    def visit_Constant(self, node: ast.Constant) -> Any:
        """处理常量（Python 3.8+）"""
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"不支持的常量类型: {type(node.value)}")
    
    def visit_Expression(self, node: ast.Expression) -> Any:
        """处理表达式节点"""
        return self.visit(node.body)
    
    def visit_Call(self, node: ast.Call) -> Any:
        """处理函数调用"""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name not in self.ALLOWED_CALLS:
                raise ValueError(f"不支持的函数: {func_name}")
            
            args = [self.visit(arg) for arg in node.args]
            import builtins
            return getattr(builtins, func_name)(*args)
        
        raise ValueError("只支持简单的内置函数调用")
    
    def generic_visit(self, node: ast.AST) -> Any:
        """默认访问方法"""
        raise ValueError(f"不支持的语法: {type(node).__name__}")


def safe_eval(expression: str) -> float:
    """
    安全地计算数学表达式
    仅支持数字和基本数学运算符
    """
    expression = expression.strip()
    if not expression:
        raise ValueError("表达式不能为空")
    
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as e:
        raise ValueError(f"语法错误: {e}")
    
    # 检查是否有不允许的节点类型
    allowed_nodes = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv,
        ast.USub, ast.UAdd, ast.Call, ast.Name, ast.Load, ast.Tuple,
    )
    
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"表达式包含不允许的内容: {type(node).__name__}")
    
    evaluator = SafeEvaluator()
    return evaluator.visit(tree)


def main():
    parser = argparse.ArgumentParser(description='计算器工具')
    parser.add_argument('expression', nargs='?', help='要计算的表达式')
    parser.add_argument('--args-file', help='参数文件路径（JSON格式）')
    
    args = parser.parse_args()
    
    # 支持通过文件传递参数（用于复杂场景）
    if args.args_file:
        try:
            with open(args.args_file, 'r', encoding='utf-8') as f:
                params = json.load(f)
            expression = params.get('expression', '')
        except Exception as e:
            print(json.dumps({
                "success": False,
                "error": f"读取参数失败: {e}"
            }, ensure_ascii=False))
            return
    else:
        expression = args.expression
    
    if not expression:
        print(json.dumps({
            "success": False,
            "error": "请提供要计算的表达式"
        }, ensure_ascii=False))
        return
    
    try:
        result = safe_eval(expression)
        result_str = str(int(result)) if result == int(result) else str(result)
        print(json.dumps({
            "success": True,
            "result": result,
            "result_str": result_str,
            "expression": expression
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({
            "success": False,
            "error": str(e),
            "expression": expression
        }, ensure_ascii=False))


if __name__ == '__main__':
    main()
