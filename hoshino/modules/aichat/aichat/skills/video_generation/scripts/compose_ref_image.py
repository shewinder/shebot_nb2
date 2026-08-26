#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-08-26
Description: 多图拼接为单张参考图，供 video_generation SKILL 单图参考（ref2va）使用

用途不限多人物：多角色同框、单人多视角（正/侧/背）、角色+场景、双图对比等，
凡是"多张参考图 → 一张图按单图 ref 跑"的场景都适用。

用法：
    compose_ref_image.py --images <id1>,<id2>[,<id3>...] [--layout h|v] [--gap 8] [--bg white]

- 解析多个图片标识符（复用 image_generation/_common.resolve_image_file）
- 统一高度（横向）或统一宽度（纵向）缩放后拼接成一张图
- 存入当前会话 ImageStore，返回 <ai_image_N> 供后续 --task ref 单图参考引用
"""
import argparse
import io
import sys
from pathlib import Path
from typing import List

from PIL import Image

# 复用 image_generation 技能的通用工具（HTTP / 图片解析 / 输出协议）
_IG_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "image_generation" / "scripts"
sys.path.insert(0, str(_IG_SCRIPTS))

from _common import (
    resolve_image_file, store_image,
    output_result, output_error,
)


def compose_images(paths: List[str], layout: str, gap: int, bg: str) -> Image.Image:
    """拼接多张图片为一张

    - 横向（h）：统一高度（取最高），从左到右排列
    - 纵向（v）：统一宽度（取最宽），从上到下排列
    """
    imgs = []
    for p in paths:
        with Image.open(p) as im:
            im = im.convert("RGB")
            imgs.append(im.copy())

    if not imgs:
        raise RuntimeError("没有可拼接的图片")

    if layout == "h":
        target_h = max(im.height for im in imgs)
        resized = []
        for im in imgs:
            w = max(1, round(im.width * target_h / im.height))
            resized.append(im.resize((w, target_h), Image.LANCZOS))
        width = sum(im.width for im in resized) + gap * (len(resized) - 1)
        canvas = Image.new("RGB", (width, target_h), bg)
        x = 0
        for im in resized:
            canvas.paste(im, (x, 0))
            x += im.width + gap
        return canvas
    else:  # v
        target_w = max(im.width for im in imgs)
        resized = []
        for im in imgs:
            h = max(1, round(im.height * target_w / im.width))
            resized.append(im.resize((target_w, h), Image.LANCZOS))
        height = sum(im.height for im in resized) + gap * (len(resized) - 1)
        canvas = Image.new("RGB", (target_w, height), bg)
        y = 0
        for im in resized:
            canvas.paste(im, (0, y))
            y += im.height + gap
        return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description="多图拼接为单张参考图")
    parser.add_argument("--images", required=True, help="图片标识符，逗号分隔")
    parser.add_argument("--layout", choices=["h", "v"], default="h", help="拼接方向：h=横向（默认），v=纵向")
    parser.add_argument("--gap", type=int, default=8, help="图间间隙像素（默认 8）")
    parser.add_argument("--bg", default="white", help="背景色（PIL 颜色名或十六进制，默认 white）")
    args = parser.parse_args()

    # 解析标识符
    paths: List[str] = []
    for ident in args.images.split(","):
        ident = ident.strip()
        if not ident:
            continue
        path = resolve_image_file(ident)
        if path:
            paths.append(path)
        else:
            output_error(f"未找到图片标识符: {ident}")
            return
    if not paths:
        output_error("拼接至少需要一张图片")
        return
    if len(paths) < 2:
        output_error("拼接至少需要两张图片")
        return

    # 拼接
    try:
        canvas = compose_images(paths, args.layout, max(0, args.gap), args.bg)
    except Exception as e:
        output_error(f"拼接失败: {e}")
        return

    # 存入 ImageStore（source="ai" → <ai_image_N>），供后续 ref 单图参考引用
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    stored = store_image(buf.getvalue(), "ai", "png")
    output_result(True, identifier=stored["identifier"], path=stored["path"],
                  model="compose_ref")


if __name__ == "__main__":
    main()
