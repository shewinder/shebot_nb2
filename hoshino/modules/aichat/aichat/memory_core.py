"""记忆核心模块：AI 驱动的摘要生成与事实提取"""
import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import httpx
from loguru import logger

from .api import api_manager
from .config import Config
from .memory_store import SessionSummary, UserFact, load_facts, load_summaries, save_facts, save_summaries

conf = Config.get_instance('aichat')


# ========== Prompt 模板 ==========

SUMMARY_SYSTEM_PROMPT = """你是一个对话摘要助手。请用不超过50字的一句话总结以下对话的核心内容，重点关注：
- 用户提出的要求、指令或未完成事项
- 用户明确表达的不满或需要修正的行为
- 关键决策或约定
- 如有 Skill 激活或工具调用，请简要提及
不要记录角色扮演剧情、情感描写或无关细节。
只输出摘要内容，不要解释、不要加引号。"""

FACT_EXTRACTION_SYSTEM_PROMPT = """请从以下对话中提取关于用户的信息，并为每条事实标注分类。

返回严格合法的 JSON 数组，格式示例：
[{"key": "preferred_quality", "value": "4K REMUX", "confidence": 0.9, "category": "preference"}]
[{"key": "image_identifier_rule", "value": "不要在同一条回复中重复引用同一个图片标识符", "confidence": 0.95, "category": "rule"}]
[{"key": "user_name", "value": "小明", "confidence": 0.9, "category": "profile"}]

分类说明（category 字段必填）：
- "preference": 用户偏好、习惯（如喜欢详细回复、喜欢用表情）
- "rule": 用户对AI的行为约束、规则（如"不要重复引用图片"、"回复要简洁"）
- "profile": 用户个人资料（如姓名、职业、所在地）
- "context": 临时上下文约定（如"这次讨论用英文"、"今天聊电影"），仅适用于当前短期场景

规则：
- 首先判断上下文是否处于角色扮演过程，角色扮演的内容以及过程中产生的规则不提取
- key 使用英文 snake_case
- value 使用自然语言描述，清晰完整
- confidence 取值 0.0~1.0，表示确信程度
- category 必须从上述四类中选择
- 不要提取临时信息（如"现在几点"、"今天天气如何"）
- 用户明确提出的规则和要求必须提取，即使只出现一次
- 不要提取角色扮演、虚构剧情、场景对话中产生的规则或设定，只提取用户本人对 AI 助手明确表达的真实要求和偏好
- 如果规则是在角色扮演过程中由 AI 提出、用户只是配合回应的，不要提取为事实
- 如果没有任何可提取的信息，返回空数组 []"""


# ========== 消息格式化 ==========

def _format_message(msg: Dict[str, Any]) -> str:
    """将单条消息格式化为文本"""
    role = msg.get("role", "unknown")
    content = msg.get("content", "")
    
    if role == "system":
        return ""  # system 消息不纳入记忆分析
    
    # 处理多模态 content（列表格式）
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
        content = " ".join(texts)
    
    content = str(content) if content else ""
    
    # 限制单条消息长度，防止 prompt 过长
    if len(content) > 500:
        content = content[:500] + "..."
    
    if role == "assistant":
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            tool_names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]
            return f"[assistant]: [调用工具: {', '.join(tool_names)}]\n{content}"
        return f"[assistant]: {content}"
    
    if role == "tool":
        # tool 消息通常是 JSON，简化显示
        try:
            tool_data = json.loads(content)
            success = tool_data.get("success", "?")
            return f"[tool]: 执行结果(success={success})"
        except Exception:
            return f"[tool]: {content[:200]}"
    
    return f"[{role}]: {content}"


def _format_messages_for_analysis(messages: List[Dict[str, Any]]) -> str:
    """将消息列表格式化为可供 AI 分析的文本，只取最近 40 条非 system 消息"""
    non_system = [m for m in messages if m.get("role") != "system"]
    # 取最近 40 条，足够提取近期事实
    recent = non_system[-40:] if len(non_system) > 40 else non_system
    lines = []
    for msg in recent:
        line = _format_message(msg)
        if line:
            lines.append(line)
    return "\n".join(lines)


# ========== API 调用 ==========

async def _call_memory_api(system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> str:
    """调用 AI API 获取记忆相关输出"""
    api_config = api_manager.get_api_config()
    if not api_config or not api_config.get("api_key"):
        logger.warning("记忆系统无法调用 API：配置缺失")
        return ""
    
    url = f"{api_config['api_base'].rstrip('/')}/chat/completions"
    model = api_config.get("model", "unknown")
    headers = {
        "Authorization": f"Bearer {api_config['api_key']}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    
    logger.debug(f"[_call_memory_api] 请求 model={model}, max_tokens={max_tokens}, user_prompt_len={len(user_prompt)}")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            finish_reason = data.get("choices", [{}])[0].get("finish_reason", "")
            usage = data.get("usage", {})
            logger.debug(f"[_call_memory_api] 响应 finish_reason={finish_reason}, usage={usage}, content_len={len(content) if content else 0}, content_preview={content[:100] if content else '(empty)'}")
            return content.strip()
    except Exception as e:
        logger.warning(f"[_call_memory_api] 记忆系统 API 调用失败: {e}")
        return ""


def _clean_json_response(text: str) -> str:
    """清洗 AI 返回的 JSON，去除 markdown code block"""
    # 匹配 ```json ... ``` 或 ``` ... ```
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


# ========== 核心功能 ==========

async def generate_summary(
    session_id: str,
    messages: List[Dict[str, Any]],
    active_skills: Set[str],
    message_count: int
) -> Optional[SessionSummary]:
    """生成会话摘要"""
    context = _format_messages_for_analysis(messages)
    if not context:
        return None
    
    user_prompt = f"请总结以下对话：\n\n{context}"
    summary_text = await _call_memory_api(SUMMARY_SYSTEM_PROMPT, user_prompt)
    
    if not summary_text:
        return None
    
    # 截断到合理长度
    summary_text = summary_text[:200]
    
    # 判断是否有未完成事项（启发式：是否有 downloading / 监控 / 等待 等关键词）
    pending_keywords = ["下载", "监控", "等待", "进行中", "未完成", "稍后", "待处理"]
    has_pending = any(kw in summary_text for kw in pending_keywords)
    
    return SessionSummary(
        session_id=session_id,
        summary=summary_text,
        active_skills=list(active_skills),
        has_pending_tasks=has_pending,
        timestamp=datetime.now(),
        message_count=message_count
    )


async def extract_facts(
    session_id: str,
    messages: List[Dict[str, Any]],
    existing_facts: List[UserFact]
) -> List[UserFact]:
    """从对话中提取用户事实，并与已有事实合并"""
    context = _format_messages_for_analysis(messages)
    if not context:
        return existing_facts
    
    user_prompt = f"请从以下对话中提取用户事实：\n\n{context}"
    raw_response = await _call_memory_api(FACT_EXTRACTION_SYSTEM_PROMPT, user_prompt)
    
    if not raw_response:
        return existing_facts
    
    # 解析 JSON
    try:
        cleaned = _clean_json_response(raw_response)
        extracted = json.loads(cleaned)
        if not isinstance(extracted, list):
            logger.warning(f"事实提取返回非数组: {raw_response[:200]}")
            return existing_facts
    except Exception as e:
        logger.warning(f"事实提取 JSON 解析失败: {e}, 原始内容: {raw_response[:200]}")
        return existing_facts
    
    # 合并到已有事实：按 key 覆盖，保留 confidence 更高的
    fact_map: Dict[str, UserFact] = {f.key: f for f in existing_facts}
    
    for item in extracted:
        if not isinstance(item, dict):
            continue
        key = item.get("key", "").strip()
        value = str(item.get("value", "")).strip()
        confidence = float(item.get("confidence", 0.5))
        category = str(item.get("category", "preference")).strip().lower()
        
        if not key or not value:
            continue
        
        # 过滤低置信度
        if confidence < 0.6:
            continue
        
        # 标准化分类
        valid_categories = {"preference", "rule", "profile", "context"}
        if category not in valid_categories:
            category = "preference"
        
        # context 类事实自动设置 1 小时过期时间
        expires_at = None
        if category == "context":
            expires_at = datetime.now() + timedelta(hours=1)
        
        # 如果已有同 key，保留 confidence 更高的
        if key in fact_map and fact_map[key].confidence >= confidence:
            continue
        
        fact_map[key] = UserFact(
            key=key,
            value=value,
            confidence=confidence,
            updated_at=datetime.now(),
            source=session_id,
            category=category,
            expires_at=expires_at
        )
    
    return list(fact_map.values())


def format_memory_for_prompt(user_id: int, max_summaries: int = 3, max_facts: int = 20) -> str:
    """读取用户记忆并格式化为可注入 system prompt 的文本"""
    summaries = load_summaries(user_id)
    facts = load_facts(user_id)
    
    # 过滤已过期的事实
    now = datetime.now()
    valid_facts = [f for f in facts if f.expires_at is None or f.expires_at > now]
    expired_count = len(facts) - len(valid_facts)
    if expired_count > 0:
        logger.debug(f"[Memory] 过滤了 {expired_count} 条已过期事实")
    
    if not summaries and not valid_facts:
        return ""
    
    lines = ["<user_memory>"]
    
    # 近期摘要
    if summaries:
        recent = sorted(summaries, key=lambda s: s.timestamp, reverse=True)[:max_summaries]
        lines.append("<recent_sessions>")
        for s in recent:
            time_str = s.timestamp.strftime("%m-%d %H:%M")
            session_type = "群" if s.session_id.startswith("group_") else "私聊"
            lines.append(f"- {session_type} ({time_str}): {s.summary}")
        lines.append("</recent_sessions>")
    
    # 已知事实，按分类分组
    if valid_facts:
        # 按 updated_at 排序，取最近 max_facts 条
        recent_facts = sorted(valid_facts, key=lambda f: f.updated_at, reverse=True)[:max_facts]
        
        category_names = {
            "rule": "行为规则",
            "preference": "用户偏好",
            "profile": "个人资料",
            "context": "当前上下文"
        }
        
        # 按分类分组
        by_category: Dict[str, List[UserFact]] = {}
        for f in recent_facts:
            by_category.setdefault(f.category, []).append(f)
        
        lines.append("<known_facts>")
        for cat in ["rule", "preference", "profile", "context"]:
            if cat not in by_category:
                continue
            cat_name = category_names.get(cat, cat)
            lines.append(f"  [{cat_name}]")
            for f in by_category[cat]:
                lines.append(f"  - {f.value}")
        lines.append("</known_facts>")
    
    lines.append("</user_memory>")
    return "\n".join(lines)


# ========== 高层封装：Session 记忆提取 ==========

async def extract_and_save_memory(
    user_id: int,
    session_id: str,
    messages: List[Dict[str, Any]],
    active_skills: Set[str]
) -> None:
    """从 Session 中提取摘要和事实并保存"""
    logger.debug(f"[extract_and_save_memory] 开始执行 user_id={user_id}, session_id={session_id}, messages_count={len(messages)}")
    message_count = len([m for m in messages if m.get("role") in ("user", "assistant")])
    if message_count < 2:
        logger.debug(f"[extract_and_save_memory] Session {session_id} 消息太少({message_count}条)，跳过记忆提取")
        return
    
    try:
        # 生成摘要
        logger.debug(f"[extract_and_save_memory] 开始生成摘要 user_id={user_id}")
        summary = await generate_summary(session_id, messages, active_skills, message_count)
        if summary:
            summaries = load_summaries(user_id)
            summaries.append(summary)
            # 按时间排序，保留最近的 N 条
            summaries.sort(key=lambda s: s.timestamp)
            max_sum = getattr(conf, 'memory_max_summaries', 5)
            if len(summaries) > max_sum:
                summaries = summaries[-max_sum:]
            save_summaries(user_id, summaries)
            logger.info(f"[extract_and_save_memory] 已保存用户 {user_id} 的会话摘要: {summary.summary[:50]}")
        else:
            logger.debug(f"[extract_and_save_memory] 摘要生成返回为空，未保存")
    except Exception as e:
        logger.exception(f"[extract_and_save_memory] 生成摘要失败: {e}")
    
    try:
        # 提取事实
        logger.debug(f"[extract_and_save_memory] 开始提取事实 user_id={user_id}")
        existing_facts = load_facts(user_id)
        facts = await extract_facts(session_id, messages, existing_facts)
        if facts:
            # 按 updated_at 排序，保留最近的 N 条
            max_fac = getattr(conf, 'memory_max_facts', 30)
            facts.sort(key=lambda f: f.updated_at)
            if len(facts) > max_fac:
                facts = facts[-max_fac:]
            save_facts(user_id, facts)
            logger.info(f"[extract_and_save_memory] 已保存用户 {user_id} 的事实: {len(facts)} 条")
        else:
            logger.debug(f"[extract_and_save_memory] 事实提取返回为空，未保存")
    except Exception as e:
        logger.exception(f"[extract_and_save_memory] 提取事实失败: {e}")
    logger.debug(f"[extract_and_save_memory] 执行完毕 user_id={user_id}, session_id={session_id}")
