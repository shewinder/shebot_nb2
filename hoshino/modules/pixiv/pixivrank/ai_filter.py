'''
Author: SheBot
Date: 2026-04-08
Description: AI 图片筛选 - 极简独立实现
'''
import json
from typing import List, Dict, Optional
import httpx
from hoshino import userdata_dir
from hoshino.log import logger


def read_user_preference(user_id: str) -> str:
    """读取用户画像文件"""
    path = userdata_dir.joinpath(f"aichat/preferences/{user_id}.md")
    if path.exists():
        content = path.read_text(encoding='utf-8')
        logger.debug(f"读取画像文件成功: {path}，长度 {len(content)}")
        return content
    logger.debug(f"画像文件不存在: {path}")
    return ""


async def ai_filter_images(
    user_id: str,
    images: List[Dict],
    api_base: str,
    api_key: str,
    model: str,
    select_count: int = 6
) -> Optional[List[int]]:
    """
    调用 AI 根据用户喜好筛选图片
    
    Args:
        user_id: 用户/群ID
        images: 图片列表，每项包含 {"pid": int, "title": str, "author": str, "tags": List[str]}
        api_base: AI API 地址
        api_key: AI API 密钥
        model: 模型名称
        select_count: 需要选择的数量
    
    Returns:
        选中的 PID 列表（保持优先级顺序），失败时返回 None
    """
    logger.info(f"开始 AI 筛选: user_id={user_id}, 候选图片={len(images)}张, 目标={select_count}张")
    
    # 读取用户喜好
    preference = read_user_preference(user_id)
    
    # 无画像时直接返回 None，让调用方降级
    if not preference:
        logger.info(f"用户 {user_id} 无画像文件，跳过 AI 筛选")
        return None
    
    if not api_key:
        logger.warning("AI API 密钥未配置，跳过 AI 筛选")
        return None
    
    logger.info(f"画像长度: {len(preference)} 字符，准备调用 AI")
    
    # 构建图片描述
    img_descriptions = []
    for i, img in enumerate(images, 1):
        tags_str = ", ".join(img.get("tags", [])[:10])  # 限制标签数量
        img_descriptions.append(
            f"[{i}] PID:{img['pid']} | {img['title']} | 作者:{img['author']} | 标签:{tags_str}"
        )
    
    # 构建 prompt
    system_prompt = """你是一个图片推荐助手。根据用户的画像喜好，从候选图片中选择最符合的图片。
注意：必须返回图片的 PID（数字ID），不要返回序号。
只返回 JSON 格式，不要任何解释：
{
  "selected": [pid1, pid2, pid3, ...],
  "reason": "简要说明选择理由"
}"""

    user_prompt = f"""【用户画像】
{preference[:3000]}

【候选图片】（共{len(images)}张）
{chr(10).join(img_descriptions)}

请从中选择最符合用户喜好的 {select_count} 张图片。
重要：返回每个图片的 PID 数字（如 143198268），不是方括号里的序号！"""

    # 调用 AI
    try:
        logger.info(f"调用 AI API: model={model}, base={api_base}")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.3,  # 低温度，确定性输出
                    "max_tokens": 500
                }
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            
            logger.debug(f"AI 原始返回: {content[:500]}...")
            
            # 解析 JSON
            json_str = content.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            
            result = json.loads(json_str.strip())
            selected_pids_raw = result.get("selected", [])
            reason = result.get("reason", "无说明")
            
            # 类型转换：确保 PID 是整数
            selected_pids = []
            for pid in selected_pids_raw:
                try:
                    selected_pids.append(int(pid))
                except (ValueError, TypeError):
                    logger.warning(f"AI 返回的 PID 无法转换为整数: {pid}")
            
            logger.info(f"AI 返回: selected={selected_pids}, reason={reason}")
            
            # 验证 PID 有效性
            valid_pids = {img["pid"] for img in images}
            logger.debug(f"有效 PID 集合: {list(valid_pids)[:10]}...")
            
            filtered = []
            invalid_pids = []
            for pid in selected_pids:
                if pid in valid_pids:
                    filtered.append(pid)
                else:
                    invalid_pids.append(pid)
            
            if invalid_pids:
                logger.warning(f"AI 返回了无效 PID: {invalid_pids}")
            
            logger.info(f"AI 筛选完成: 从 {len(images)} 张选中 {len(filtered)} 张（原始返回 {len(selected_pids)} 张）")
            return filtered[:select_count]
            
    except httpx.HTTPStatusError as e:
        logger.error(f"AI API HTTP 错误: {e.response.status_code} - {e.response.text[:200]}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"AI 返回 JSON 解析失败: {e}")
        logger.error(f"原始内容: {content[:500]}")
        return None
    except Exception as e:
        logger.exception(f"AI 筛选失败: {e}")
        return None
