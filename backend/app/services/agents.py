"""多智能体流水线：数据智能体 → 规则引擎 → 分析师智能体 → 审稿智能体。

架构约束（不可动摇）：
- 规则引擎（analysis.py）永远是唯一事实锚点，LLM 环节全部可降级；
  最坏情况退化为固定检索策略 + 本地模板，可靠性不劣于单 LLM 模式。
- GLM-4.7-Flash 免费档存在随机并发限流，所有 LLM 调用串行执行。
- 业态识别保持确定性词表方案（main.py），数据智能体只决定检索策略。
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Awaitable, Callable

from app.config import Settings
from app.models import AgentTrace, AnalysisRequest, AnalysisResponse, PointSample, PoiSummary
from app.services.amap import AmapClient
from app.services.llm import PROMPTS, chat_completion, fallback_answer, llm_context


StageCallback = Callable[[str, str], Awaitable[None]]

MAX_LLM_ROUNDS = 8
RADIUS_BOUNDS = (300, 3000)
PAGES_BOUNDS = (1, 3)

SEARCH_POIS_TOOL = {
    "type": "function",
    "function": {
        "name": "search_pois",
        "description": "搜索坐标周边的 POI。不带 keywords 时用于商圈结构采样（了解整体业态分布）；带 keywords 时用于竞品搜索。",
        "parameters": {
            "type": "object",
            "properties": {
                "radius": {
                    "type": "integer",
                    "description": "搜索半径（米），300-3000，默认使用默认半径",
                },
                "keywords": {
                    "type": "string",
                    "description": "搜索关键词，仅竞品搜索时填写（通常为目标业态名）；结构采样必须留空",
                },
                "pages": {
                    "type": "integer",
                    "description": "抓取页数（1-3，每页最多 25 条），默认 1，结构采样建议 2",
                },
                "lng": {
                    "type": "number",
                    "description": "采样点经度，仅区域多点采样时使用，偏离中心不超过约 2.5 公里",
                },
                "lat": {
                    "type": "number",
                    "description": "采样点纬度，仅区域多点采样时使用，偏离中心不超过约 2.5 公里",
                },
            },
            "required": [],
        },
    },
}

STANDARD_DATA_SYSTEM = (
    "你是商业选址数据智能体，负责为一次选址评估制定并执行周边 POI 检索策略。\n"
    "工作流程：\n"
    "1. 先调用一次 search_pois（不带 keywords，pages=2）做商圈结构采样。\n"
    "2. 如果给定业态，再调用一次 search_pois（keywords=业态名）统计竞品数量。\n"
    "3. 仅当结构采样 total 明显偏低（如少于 15）时，才扩大半径或增加页数重查一次。\n"
    "通常 2 次调用即可完成，工具调用总数不得超过 4 次。\n"
    "完成后不要再调用工具，直接输出一行 JSON："
    '{"radius": <最终采用的结构采样半径>, "notes": "<一句话检索策略说明>"}。\n'
    "只基于工具返回的数据决策，不要编造。"
)

ECOSYSTEM_DATA_SYSTEM = (
    "你是商业生态规划数据智能体，为一次区域业态结构分析执行 POI 检索。\n"
    "工作流程：\n"
    "1. 调用一次 search_pois（不带 keywords，radius 用 2000-3000，pages=2 或 3）做大范围结构采样，尽量覆盖更多业态类别。\n"
    "2. 仅当采样 total 少于 20 时，才扩大半径或增加页数重查一次。\n"
    "3. 不需要竞品关键词搜索。\n"
    "通常 1-2 次调用即可完成，工具调用总数不超过 3 次。\n"
    "完成后不要再调用工具，直接输出一行 JSON：{\"notes\": \"<一句话采样说明>\"}。\n"
    "只基于工具返回的数据决策，不要编造。"
)

REGIONAL_DATA_SYSTEM = (
    "你是区域商业潜力评估数据智能体，需要通过多点采样评估区域一致性。\n"
    "工作流程：\n"
    "1. 先对中心点调用一次 search_pois（不带 keywords，pages=2，radius 用默认值）。\n"
    "2. 再分别在中心点的东、南、西、北四个方向各偏离约 1 公里处（通过 lng/lat 参数指定采样点）"
    "各调用一次 search_pois（不带 keywords，radius 用 800-1000，pages=1）。可以在一条消息里同时发起多个调用。\n"
    "3. 工具调用总数不超过 6 次。\n"
    "完成后不要再调用工具，直接输出一行 JSON：{\"notes\": \"<一句话区域采样说明>\"}。\n"
    "只基于工具返回的数据决策，不要编造。"
)

DATA_STRATEGIES: dict[str, tuple[str, int]] = {
    "site_selection": (STANDARD_DATA_SYSTEM, 4),
    "store_diagnosis": (STANDARD_DATA_SYSTEM, 4),
    "ecosystem_planning": (ECOSYSTEM_DATA_SYSTEM, 3),
    "regional_potential": (REGIONAL_DATA_SYSTEM, 6),
}

REVIEWER_SYSTEM = (
    "你是多智能体流水线中的审稿智能体，只做数字核对，不评价写作。\n"
    "给你一份分析师报告草稿和结构化分析 JSON（唯一事实锚点）。只检查一件事：\n"
    "- 草稿中的数字（评分、维度分、POI 总数、竞品数量、半径）是否与 JSON 中的数字不一致；\n"
    "- 草稿是否编造了 JSON 中不存在的精确数字（如具体客流量、租金金额）。\n"
    "硬性规则：每条 issue 必须写成“草稿中数字 A，JSON 中为 B”的格式，"
    "无法同时引用两个具体数字的，一律不得列入 issues。\n"
    "以下情况一律不算问题：\n"
    "- 分数含义解读（如竞品压力 0 分表示竞争压力大，属正常表述）；\n"
    "- 行动建议中的泛化范围（如“复核 500-1500 米范围”）；\n"
    "- 语言风格、观点深浅、措辞模糊。\n"
    "如果草稿所有数字都与 JSON 一致，verdict 必须是 pass。\n"
    '输出严格 JSON（不要输出其他内容）：{"verdict": "pass 或 revise", "issues": ["草稿中数字A，JSON中为B", ...]}，'
    "issues 最多 5 条。"
)


# ---------------------------------------------------------------------------
# 数据智能体（一期：tool-calling 检索策略）
# ---------------------------------------------------------------------------


async def run_data_agent(
    settings: Settings,
    client: AmapClient,
    request: AnalysisRequest,
) -> tuple[PoiSummary | None, str, bool]:
    """数据智能体：LLM 通过工具调用自主决定检索策略。

    返回 (poi_summary, notes, ok)。失败时返回 (None, "", False)，
    调用方走 collect_pois_hardcoded 降级路径。
    """
    if not settings.llm_api_key:
        return None, "", False

    system_prompt, tool_budget = DATA_STRATEGIES.get(request.module.value, DATA_STRATEGIES["site_selection"])

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "location": {
                        "lng": request.location.lng,
                        "lat": request.location.lat,
                        "address": request.location.address,
                    },
                    "businessType": request.scenario.businessType,
                    "defaultRadius": request.scenario.radius,
                },
                ensure_ascii=False,
            ),
        },
    ]

    base: PoiSummary | None = None
    competitor_count = 0
    samples: list[PointSample] = []

    for _ in range(MAX_LLM_ROUNDS):
        message = await chat_completion(settings, messages, tools=[SEARCH_POIS_TOOL], temperature=0.2)
        if message is None:
            return None, "", False

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            notes = _parse_notes(message.get("content") or "")
            if base is None:
                # 没有执行过结构采样，视为失败，走降级
                return None, notes, False
            base.competitorCount = competitor_count
            base.samplePoints = samples
            return base, notes, True

        messages.append(
            {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        for call in tool_calls:
            if tool_budget <= 0:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(call.get("id", "")),
                        "content": json.dumps(
                            {"error": "工具调用预算已用完，请直接输出最终 JSON"}, ensure_ascii=False
                        ),
                    }
                )
                continue
            tool_budget -= 1
            result, is_structure, summary, sample_lng, sample_lat = await _execute_search_pois(client, request, call)
            if summary is not None:
                if is_structure:
                    samples.append(
                        PointSample(
                            label=_direction_label(request, sample_lng, sample_lat),
                            lng=sample_lng,
                            lat=sample_lat,
                            radius=summary.radius,
                            total=summary.total,
                            byCategory=summary.byCategory,
                        )
                    )
                    is_center = (
                        abs(sample_lng - request.location.lng) < 0.001
                        and abs(sample_lat - request.location.lat) < 0.001
                    )
                    if is_center:
                        base = summary
                else:
                    competitor_count = summary.total
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(call.get("id", "")),
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    # LLM 轮次用尽：只要有结构采样结果就可用了
    if base is not None:
        base.competitorCount = competitor_count
        base.samplePoints = samples
        return base, "数据智能体达到轮次上限，使用已采集数据。", True
    return None, "", False


async def _execute_search_pois(
    client: AmapClient,
    request: AnalysisRequest,
    call: dict,
) -> tuple[dict, bool, PoiSummary | None, float, float]:
    """执行一次 search_pois 工具调用。

    返回 (给LLM的结果, 是否结构采样, PoiSummary, 采样点经度, 采样点纬度)。
    采样点坐标被夹紧在中心点 ±0.025 度（约 2.5 公里）范围内。
    """
    try:
        args = json.loads(call.get("function", {}).get("arguments") or "{}")
        if not isinstance(args, dict):
            args = {}
    except ValueError:
        args = {}
    radius = _clamp_int(args.get("radius", request.scenario.radius), *RADIUS_BOUNDS)
    pages = _clamp_int(args.get("pages", 1), *PAGES_BOUNDS)
    keywords = str(args.get("keywords") or "").strip()
    lng = _clamp_float(args.get("lng"), request.location.lng - 0.025, request.location.lng + 0.025, request.location.lng)
    lat = _clamp_float(args.get("lat"), request.location.lat - 0.025, request.location.lat + 0.025, request.location.lat)
    try:
        summary = await client.nearby_pois(
            lng,
            lat,
            radius,
            keywords=keywords or None,
            pages=pages,
        )
    except Exception as exc:
        return {"error": f"检索失败：{exc!r}"}, False, None, request.location.lng, request.location.lat
    result: dict = {
        "lng": round(lng, 6),
        "lat": round(lat, 6),
        "radius": radius,
        "pages": pages,
        "total": summary.total,
        "byCategory": summary.byCategory,
    }
    if keywords:
        result["keywords"] = keywords
        return result, False, summary, lng, lat
    return result, True, summary, lng, lat


async def collect_pois_hardcoded(request: AnalysisRequest, client: AmapClient) -> PoiSummary:
    """固定检索策略：结构采样 2 页 + 业态竞品搜索。数据智能体的降级路径。"""
    poi_summary = await client.nearby_pois(
        request.location.lng,
        request.location.lat,
        request.scenario.radius,
        pages=2,
    )
    if request.scenario.businessType:
        try:
            competitors = await client.nearby_pois(
                request.location.lng,
                request.location.lat,
                request.scenario.radius,
                keywords=request.scenario.businessType,
            )
            poi_summary.competitorCount = competitors.total
        except Exception:
            poi_summary.competitorCount = 0
    return poi_summary


# ---------------------------------------------------------------------------
# 分析师 / 审稿智能体（二期：定性洞察 + 事实校验 + 打回修订）
# ---------------------------------------------------------------------------


async def run_analyst(
    settings: Settings,
    request: AnalysisRequest,
    analysis: AnalysisResponse,
    retrieval_notes: str,
) -> str | None:
    """分析师智能体：基于事实锚点撰写报告草稿（含跨维度定性洞察）。失败返回 None。"""
    system = _analyst_system_prompt(request)
    user = json.dumps(
        {**llm_context(request, analysis), "检索说明": retrieval_notes},
        ensure_ascii=False,
    )
    message = await chat_completion(
        settings,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    content = (message or {}).get("content") or ""
    content = content.strip()
    return content or None


async def run_reviewer(
    settings: Settings,
    request: AnalysisRequest,
    analysis: AnalysisResponse,
    draft: str,
) -> tuple[str, list[str]] | None:
    """审稿智能体：校验草稿数字与事实锚点的一致性。

    返回 (verdict, issues)；verdict 为 "pass" 或 "revise"。失败返回 None。
    """
    user = json.dumps(
        {"事实锚点": llm_context(request, analysis), "报告草稿": draft},
        ensure_ascii=False,
    )
    message = await chat_completion(
        settings,
        [
            {"role": "system", "content": REVIEWER_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
    )
    return _parse_review((message or {}).get("content") or "")


async def run_revision(
    settings: Settings,
    request: AnalysisRequest,
    analysis: AnalysisResponse,
    draft: str,
    issues: list[str],
) -> str | None:
    """修订：审稿打回后，分析师按审稿意见修订一次。失败返回 None。"""
    system = _analyst_system_prompt(request) + (
        "\n这是修订任务：审稿智能体发现以下事实性问题，"
        "请修正后重新输出完整报告，其余内容保持不变。"
    )
    user = json.dumps(
        {
            "事实锚点": llm_context(request, analysis),
            "报告草稿": draft,
            "审稿意见": issues,
        },
        ensure_ascii=False,
    )
    message = await chat_completion(
        settings,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    content = (message or {}).get("content") or ""
    content = content.strip()
    return content or None


async def run_answer_pipeline(
    settings: Settings,
    request: AnalysisRequest,
    analysis: AnalysisResponse,
    trace: AgentTrace,
    on_stage: StageCallback | None = None,
) -> tuple[str, bool]:
    """答案流水线：分析师 → 审稿 →（打回则修订一次）。

    降级链：分析师失败 → 本地模板；审稿失败 → 直接用草稿；修订失败 → 用草稿。
    """

    async def stage(key: str, label: str) -> None:
        if on_stage:
            await on_stage(key, label)

    await stage("analyst", "分析师智能体撰写报告")
    draft = await run_analyst(settings, request, analysis, trace.retrievalNotes)
    if draft is None:
        trace.analyst = "fallback"
        return (
            fallback_answer(request, analysis, "分析师智能体不可用（LLM 未配置或调用失败），已降级为本地模板建议。"),
            True,
        )
    trace.analyst = "ok"

    await stage("reviewer", "审稿智能体校验事实一致性")
    review = await run_reviewer(settings, request, analysis, draft)
    if review is None:
        trace.reviewer = "skipped"
        return draft, False
    verdict, issues = review
    if verdict != "revise" or not issues:
        trace.reviewer = "ok"
        return draft, False

    trace.reviewer = "revise"
    trace.reviewerNotes = "；".join(issues[:3])
    await stage("revision", "审稿打回，分析师修订报告")
    revised = await run_revision(settings, request, analysis, draft, issues)
    if revised:
        return revised, False
    return draft, False


REPORT_SKELETONS = {
    "site_selection": (
        "输出必须包含：结论、关键依据、风险点、实施步骤。"
        "如果结构化分析中 alternatives 不为空，必须增加“替代推荐方案”并说明替代路径。\n"
        "在关键依据之后增加“分析师洞察”小节：结合多个维度的组合关系"
        "（如竞品密度×客流结构×业态匹配）给出规则分数之外的商业判断，"
        "说明这种组合对目标业态为什么有利或不利。"
    ),
    "store_diagnosis": (
        "输出必须包含：问题定位（说明属于哪类核心问题，依据 moduleFindings.diagnosis 中的 problems）、"
        "经营信号解读（结合 storeMetrics 与 signals 说明当前经营状态）、"
        "提升策略（按短期 1-2 周、中期 1-2 月给出排期）、风险点。"
    ),
    "ecosystem_planning": (
        "输出必须包含：区域业态结构总览（结合 categoryShare 与 diversity）、"
        "缺口与饱和分析（依据 gaps 与 saturated，说明哪些业态缺失、哪些过密）、"
        "招商补位建议（按优先级排序）、落地节奏。"
    ),
    "regional_potential": (
        "输出必须包含：区域一致性判断（依据 cv 与 consistency，结合 pointTotals 说明点位间差异）、"
        "潜力维度评估（基于评分维度）、"
        "分阶段进入策略（按试点、验证、扩张三阶段展开，每阶段给出进入与退出条件）、风险点。"
    ),
}


def _analyst_system_prompt(request: AnalysisRequest) -> str:
    module_prompt = PROMPTS[request.module.value]
    skeleton = REPORT_SKELETONS.get(request.module.value, REPORT_SKELETONS["site_selection"])
    return (
        f"{module_prompt}\n"
        "你是多智能体流水线中的分析师智能体：上游数据智能体已完成周边 POI 检索，"
        "本地规则引擎已完成结构化打分，用户消息中的 JSON 是唯一事实锚点。\n"
        "请基于用户位置、周边 POI、评分维度、检索说明和模拟参数回答。"
        f"{skeleton}\n"
        "所有数字（评分、维度分、POI 数量、竞品数、半径、占比）必须与 JSON 完全一致；"
        "不要编造高德数据中不存在的精确客流或租金数字；如使用估算，请明确说明。\n"
        "回答使用中文，语气专业、直接、可执行。"
    )


def _parse_notes(content: str) -> str:
    match = re.search(r"\{.*\}", content, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                notes = str(data.get("notes") or "").strip()
                if notes:
                    return notes[:160]
        except ValueError:
            pass
    return content.strip()[:160] or "数据智能体完成检索。"


def _parse_review(content: str) -> tuple[str, list[str]] | None:
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in ("pass", "revise"):
        return None
    issues = [str(item).strip() for item in (data.get("issues") or []) if str(item).strip()]
    issues = issues[:5]
    if verdict == "revise" and not issues:
        verdict = "pass"
    return verdict, issues


def _clamp_int(value, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def _clamp_float(value, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _direction_label(request: AnalysisRequest, lng: float, lat: float) -> str:
    dx = lng - request.location.lng
    dy = lat - request.location.lat
    if abs(dx) < 0.001 and abs(dy) < 0.001:
        return "中心"
    angle = math.degrees(math.atan2(dy, dx)) % 360
    names = ["东", "东北", "北", "西北", "西", "西南", "南", "东南"]
    return names[int((angle + 22.5) // 45) % 8] + "侧"
