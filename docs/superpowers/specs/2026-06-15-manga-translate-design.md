# 漫画翻译重嵌 — 设计规格

## 概述

日文漫画自动翻译重嵌，核心管道：CRAFT 文字检测 → LaMa 擦除 → 多模态 LLM 识别+翻译 → Pillow 渲染嵌字。

## 架构

```
┌─────────────────────────────────┐
│  mgpu 服务（独立项目）             │
│  POST /detect_and_inpaint        │
│  输入：漫画图片                    │
│  输出：擦除后图片 + bbox 列表      │
│  · CRAFT 文字检测                 │
│  · LaMa 图像擦除                  │
└────────────┬────────────────────┘
             │ HTTP
             ▼
┌─────────────────────────────────┐
│  SheBot aichat Skill             │
│  · SKILL.md 编排流程              │
│  · AI 对每个 bbox 做 OCR + 翻译   │
│  · render.py Pillow 渲染译文      │
└─────────────────────────────────┘
```

## mgpu 服务

- **部署位置**：`/root/bot/mgpu/`
- **框架**：FastAPI + PyTorch
- **GPU**：RTX 5080, CUDA 13.1
- **端点**：`POST /detect_and_inpaint`
  - 请求：multipart 图片上传
  - 响应：`{ "inpainted_image": "<base64>", "bboxes": [{"id": 0, "x": 100, "y": 200, "w": 300, "h": 50}, ...] }`

## aichat Skill

- **位置**：`hoshino/modules/aichat/aichat/skills/manga_translate/`
- **SKILL.md**：告知 AI 如何编排漫画翻译流程
- **render.py**：Pillow 渲染脚本，输入擦除后图片 + 翻译 JSON，输出嵌字后图片

## 管道流程

1. 用户发送漫画图片
2. AI 激活 manga_translate skill
3. AI 调用 mgpu 服务 `/detect_and_inpaint`
4. AI 对每个 bbox 区域做 OCR 识别原文并翻译
5. AI 调用 render.py 将译文渲染回图片
6. 返回结果给用户

## 依赖

### mgpu 服务
- torch + torchvision (CUDA)
- craft-text-detector 或 CRAFT-pytorch
- lama-cleaner 或直接集成 LaMa
- fastapi + uvicorn

### SheBot
- Pillow（已有）
- httpx（已有）

## 待定

- mgpu 项目具体结构待实现时确定
- render.py 字体选择策略
- 多页漫画处理方式
