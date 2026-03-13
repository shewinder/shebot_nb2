#!/bin/bash

# SheBot Web 控制台构建脚本

echo "=========================================="
echo "SheBot Web 控制台构建脚本"
echo "=========================================="

# 检查 Node.js
echo "检查 Node.js 环境..."
if ! command -v node &> /dev/null; then
    echo "错误: 未找到 Node.js，请先安装 Node.js 16+"
    echo "安装指南: https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 16 ]; then
    echo "错误: Node.js 版本过低，需要 16+，当前版本: $(node -v)"
    exit 1
fi

echo "Node.js 版本: $(node -v)"
echo ""

# 进入 web 目录
cd web || exit 1

# 安装依赖
echo "安装 npm 依赖..."
npm install
if [ $? -ne 0 ]; then
    echo "错误: 依赖安装失败"
    exit 1
fi
echo ""

# 构建
echo "构建生产版本..."
npm run build
if [ $? -ne 0 ]; then
    echo "错误: 构建失败"
    exit 1
fi
echo ""

# 检查构建结果
cd ..
if [ -f "static/index.html" ]; then
    echo "=========================================="
    echo "构建成功！"
    echo "静态文件已生成到 static/ 目录"
    echo ""
    echo "使用方法:"
    echo "  1. 启动 Bot: python run.py"
    echo "  2. 访问 http://localhost:9002"
    echo "=========================================="
else
    echo "错误: 构建后未找到 static/index.html"
    exit 1
fi
