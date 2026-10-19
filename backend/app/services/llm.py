from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

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


def _llm_context(request: AnalysisRequest, analysis: AnalysisResponse) -> dict:
    return {
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


async def ask_llm(settings: Settings, request: AnalysisRequest, analysis: AnalysisResponse) -> tuple[str, bool]:
    if not settings.llm_api_key:
        return _fallback_answer(request, analysis, "智谱 API key 未配置。"), True

    system_prompt = _system_prompt(request)
    user_payload = _llm_context(request, analysis)
    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": 0.3,
        "thinking": {"type": "disabled"},
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(url, headers=headers, json=body)
                if response.status_code == 429:
                    last_error = RuntimeError("429 限流（免费档并发/频率限制）")
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                response.raise_for_status()
            data = response.json()
            answer = data["choices"][0]["message"]["content"]
            return answer, False
        except Exception as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(2 * (attempt + 1))
                continue
    return _fallback_answer(request, analysis, f"智谱 GLM 调用失败（已重试 {MAX_ATTEMPTS} 次）：{last_error!r}"), True


async def stream_llm(
    settings: Settings,
    request: AnalysisRequest,
    analysis: AnalysisResponse,
) -> AsyncIterator[tuple[str, bool]]:
    if not settings.llm_api_key:
        yield _fallback_answer(request, analysis, "智谱 API key 未配置。"), True
        return

    system_prompt = _system_prompt(request)
    user_payload = _llm_context(request, analysis)
    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": 0.3,
        "thinking": {"type": "disabled"},
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        yielded = False
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    if response.status_code == 429:
                        last_error = RuntimeError("429 限流（免费档并发/频率限制）")
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line.removeprefix("data:").strip()
                        if payload == "[DONE]":
                            break
                        if not payload:
                            continue
                        data = json.loads(payload)
                        delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            yielded = True
                            yield delta, False
            return
        except Exception as exc:
            last_error = exc
            if not yielded and attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(2 * (attempt + 1))
                continue
            yield _fallback_answer(request, analysis, f"智谱 GLM 调用失败：{exc!r}"), True
            return
    yield _fallback_answer(request, analysis, f"智谱 GLM 调用失败（已重试 {MAX_ATTEMPTS} 次）：{last_error!r}"), True


def _system_prompt(request: AnalysisRequest) -> str:
    module_prompt = PROMPTS[request.module.value]
    return (
        f"{module_prompt}\n"
        "请基于用户选择的地图位置、周边 POI、评分维度和模拟参数回答。"
        "输出必须包含：结论、关键依据、风险点、实施步骤。"
        "如果结构化分析中 alternatives 不为空，必须增加“替代推荐方案”并说明替代路径。"
        "不要编造高德数据中不存在的精确客流或租金数字；如使用估算，请明确说明。"
        "回答使用中文，语气专业、直接、可执行。"
    )


def _fallback_answer(request: AnalysisRequest, analysis: AnalysisResponse, reason: str) -> str:
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
