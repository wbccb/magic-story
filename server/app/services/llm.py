import json
from typing import Any, Dict

from openai import OpenAI

from app.settings import get_settings


SYSTEM_PROMPT = """
你是儿童故事渲染助手。请根据用户的录音转写文本，输出一个 JSON 对象，不要输出任何额外说明。
JSON 结构必须为:
{
  "corrected_narration": "适合儿童旁白的润色文本",
  "complexity_score": 1到10之间的整数,
  "render_route": "i2v_api 或 parallax_2d"
}

规则:
1. corrected_narration 使用简洁自然的中文。
2. complexity_score 越高表示动作越复杂、场景变化越多。
3. complexity_score 大于 5 时 render_route 返回 i2v_api，否则返回 parallax_2d。
""".strip()


def _fallback_plan(text: str) -> Dict[str, Any]:
    """
    生成兜底方案
    用途: 当本地模型返回格式不稳定时，仍然保证任务链能继续往下执行
    """
    normalized = text.strip() or "这是一段充满想象力的儿童故事。"
    score = 7 if any(keyword in normalized for keyword in ["飞", "跑", "追", "冒险", "战斗", "变身"]) else 4
    return {
        "corrected_narration": f"魔法修正后的旁白：{normalized}",
        "complexity_score": score,
        "render_route": "i2v_api" if score > 5 else "parallax_2d",
    }


def _normalize_plan(payload: Dict[str, Any], source_text: str) -> Dict[str, Any]:
    """
    规范化模型输出
    用途: 兜底处理本地模型字段缺失或类型异常，避免污染主任务状态
    """
    fallback = _fallback_plan(source_text)
    corrected_narration = str(payload.get("corrected_narration") or fallback["corrected_narration"]).strip()
    try:
        complexity_score = int(payload.get("complexity_score", fallback["complexity_score"]))
    except (TypeError, ValueError):
        complexity_score = fallback["complexity_score"]
    complexity_score = max(1, min(10, complexity_score))

    render_route = str(payload.get("render_route") or "").strip()
    if render_route not in {"i2v_api", "parallax_2d"}:
        render_route = "i2v_api" if complexity_score > 5 else "parallax_2d"

    return {
        "corrected_narration": corrected_narration,
        "complexity_score": complexity_score,
        "render_route": render_route,
    }


def analyze_story_text(transcribed_text: str) -> Dict[str, Any]:
    """
    解析故事文本
    用途: 按配置选择 Mock、本地 Ollama 或 OpenAI 兼容接口，对旁白进行润色并决定渲染路线
    """
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider == "mock":
        return _fallback_plan(transcribed_text)

    client = OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
    )
    completion = client.chat.completions.create(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcribed_text},
        ],
    )
    content = completion.choices[0].message.content or "{}"
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = _fallback_plan(transcribed_text)

    if provider not in {"ollama", "openai_compatible"}:
        raise RuntimeError(f"暂不支持的 LLM Provider: {settings.llm_provider}")
    return _normalize_plan(payload, transcribed_text)
