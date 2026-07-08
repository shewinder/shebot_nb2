'''
Author: SheBot
Date: 2026-07-08
Description: Pixivrank 用户画像提取工具
'''
from typing import List


def _extract_markdown_section(text: str, title_keywords: List[str]) -> str:
    lines = text.splitlines()
    collecting = False
    result: List[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and any(keyword in stripped for keyword in title_keywords):
            collecting = True
            continue
        if collecting and stripped.startswith("## "):
            break
        if collecting:
            result.append(line)

    return "\n".join(result).strip()


def extract_profile_for_filter(pref: str, max_chars: int = 1200, fallback_chars: int = 800) -> str:
    sections = [
        _extract_markdown_section(pref, ["推荐摘要", "核心偏好摘要"]),
        _extract_markdown_section(pref, ["核心审美画像"]),
    ]
    content = "\n\n".join(section for section in sections if section)
    if not content:
        return pref[:fallback_chars].strip()
    return content[:max_chars].strip()


def extract_profile_summary(pref: str, max_chars: int = 120) -> str:
    profile = extract_profile_for_filter(pref, max_chars=max_chars, fallback_chars=max_chars)
    return " ".join(profile.split())[:max_chars]
