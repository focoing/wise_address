from __future__ import annotations

import asyncio
import json

import httpx

from app.config import Settings
from app.models import AnalysisRequest, AnalysisResponse
from app.services.analysis import MODULE_NAMES


PROMPTS = {
    "site_selection": "你是品牌新店精准选址智能体，专注点位评估、竞品判断、客流估算和开店行动建议。",
    "store_diagnosis": "你是存量门店优化诊断智能体，专注经营问题定位、门店提升策略和短期行动排期。",
    "ecosystem_planning": "你是商业生态规划智能体，专注区域业态结构、招商组合和商业生态补位。",
    "regional_potential": "你是区域商业潜力评估智能体，专注区域发展潜力、品牌适配度和阶段性进入策略。",
}

MAX_ATTEMPTS = 3


def llm_context(request: AnalysisRequest, analysis: AnalysisResponse) -> dict:
    payload = {
        "question": request.question,
        "location": {
            "address": request.location.address,
            "lng": request.location.lng,
            "lat": request.location.lat,
        },
        "scenario": {
            "businessType": request.scenario.businessType,
            "targetCustomers": request.scenario.targetCustomers,
            "radius": request.scenario.radius,
        },
        "analysis": {
            "score": analysis.score,
            "dimensions": analysis.dimensions,
            "poiSummary": {
                "total": analysis.poiSummary.total,
                "byCategory": analysis.poiSummary.byCategory,
                "radius": analysis.poiSummary.radius,
                "estimated": analysis.poiSummary.estimated,
                "competitorCount": analysis.poiSummary.competitorCount,
            },
            "recommendation": analysis.recommendation,
            "risks": analysis.risks[:3],
            "actions": analysis.actions[:4],
            "alternatives": [
                {"title": alt.title, "reason": alt.reason} for alt in analysis.alternatives[:2]
            ],
        },
    }
    if request.storeMetrics:
        payload["storeMetrics"] = request.storeMetrics.model_dump()
    if analysis.moduleFindings:
        payload["moduleFindings"] = analysis.moduleFindings
    return payload


async def chat_completion(
    settings: Settings,
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.3,
) -> dict | None:
    """底层非流式对话调用，多智能体共用。

    成功返回 message 字典（含 content / tool_calls），失败返回 None，
    由调用方决定降级路径。自带 3 次重试 + 指数退避（应对免费档随机限流）。
    """
    if not settings.llm_api_key:
        return None
    body = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "thinking": {"type": "disabled"},
    }
    if tools:
        body["tools"] = tools
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    for attempt in range(MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(url, headers=headers, json=body)
                if response.status_code == 429:
                    raise RuntimeError("429 限流（免费档并发/频率限制）")
                response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            if isinstance(message, dict):
                return message
        except Exception:
            pass
        if attempt < MAX_ATTEMPTS - 1:
            await asyncio.sleep(2 * (attempt + 1))
    return None


def fallback_answer(request: AnalysisRequest, analysis: AnalysisResponse, reason: str) -> str:
    module_name = MODULE_NAMES[request.module]
    alternatives = ""
    if analysis.alternatives:
        alternatives = "\n替代推荐方案：" + "；".join(
            f"{item.title}，{item.expectedImpact}" for item in analysis.alternatives[:3]
        )
    return (
        f"{module_name}智能体暂用本地模型建议。{reason}\n\n"
        f"结论：当前点位综合得分 {analysis.score}，{analysis.recommendation}\n"
        f"关键依据：{'；'.join(analysis.evidence)}\n"
        f"风险点：{'；'.join(analysis.risks)}\n"
        f"实施步骤：{'；'.join(analysis.actions[:4])}"
        f"{alternatives}"
    )
