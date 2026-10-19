import json
import re
from pathlib import Path

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.models import AgentResponse, AnalysisModule, AnalysisRequest, AnalysisResponse, HistorySessionDetail, HistorySessionSummary
from app.services.amap import AmapClient
from app.services.analysis import build_analysis
from app.services.llm import ask_llm, stream_llm
from app.services.history import delete_session, get_session_detail, init_history_db, list_sessions, save_agent_history


app = FastAPI(title="商枢智能体 API", version="0.1.0")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    init_history_db()


def amap_client(settings: Settings = Depends(get_settings)) -> AmapClient:
    return AmapClient(settings)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "商枢智能体"}


@app.get("/api/config/public")
async def public_config(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {"mapProvider": "my_map", "amapKey": settings.amap_key, "defaultCity": "上海"}


@app.get("/api/geo/reverse")
async def reverse_geo(
    lng: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    client: AmapClient = Depends(amap_client),
) -> dict[str, object]:
    return await client.reverse_geocode(lng, lat)


@app.get("/api/poi/nearby")
async def nearby_poi(
    lng: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    radius: int = Query(1200, ge=300, le=5000),
    keywords: str | None = None,
    types: str | None = None,
    client: AmapClient = Depends(amap_client),
) -> dict[str, object]:
    return (await client.nearby_pois(lng, lat, radius, keywords, types)).model_dump()


@app.post("/api/analysis/site-selection", response_model=AnalysisResponse)
async def site_selection(request: AnalysisRequest, client: AmapClient = Depends(amap_client)) -> AnalysisResponse:
    request.module = AnalysisModule.site_selection
    return await _run_analysis(request, client)


@app.post("/api/analysis/store-diagnosis", response_model=AnalysisResponse)
async def store_diagnosis(request: AnalysisRequest, client: AmapClient = Depends(amap_client)) -> AnalysisResponse:
    request.module = AnalysisModule.store_diagnosis
    return await _run_analysis(request, client)


@app.post("/api/analysis/ecosystem-planning", response_model=AnalysisResponse)
async def ecosystem_planning(request: AnalysisRequest, client: AmapClient = Depends(amap_client)) -> AnalysisResponse:
    request.module = AnalysisModule.ecosystem_planning
    return await _run_analysis(request, client)


@app.post("/api/analysis/regional-potential", response_model=AnalysisResponse)
async def regional_potential(request: AnalysisRequest, client: AmapClient = Depends(amap_client)) -> AnalysisResponse:
    request.module = AnalysisModule.regional_potential
    return await _run_analysis(request, client)


@app.post("/api/agent/chat", response_model=AgentResponse)
async def agent_chat(
    request: AnalysisRequest,
    client: AmapClient = Depends(amap_client),
    settings: Settings = Depends(get_settings),
) -> AgentResponse:
    analysis = await _run_analysis(request, client)
    answer, fallback = await ask_llm(settings, request, analysis)
    response = AgentResponse(answer=answer, analysis=analysis, usedModel=settings.llm_model, fallback=fallback)
    session_id, turn_id = save_agent_history(request, analysis, response)
    response.sessionId = session_id
    response.turnId = turn_id
    return response


@app.post("/api/agent/chat/stream")
async def agent_chat_stream(
    request: AnalysisRequest,
    client: AmapClient = Depends(amap_client),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    async def event_stream():
        analysis = await _run_analysis(request, client)
        yield _sse("analysis", {"analysis": analysis.model_dump(mode="json"), "usedModel": settings.llm_model})

        answer_parts: list[str] = []
        fallback = False
        async for chunk, chunk_fallback in stream_llm(settings, request, analysis):
            fallback = fallback or chunk_fallback
            answer_parts.append(chunk)
            yield _sse("delta", {"text": chunk})

        answer = "".join(answer_parts)
        response = AgentResponse(answer=answer, analysis=analysis, usedModel=settings.llm_model, fallback=fallback)
        session_id, turn_id = save_agent_history(request, analysis, response)
        yield _sse(
            "done",
            {
                "answer": answer,
                "fallback": fallback,
                "usedModel": settings.llm_model,
                "sessionId": session_id,
                "turnId": turn_id,
            },
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/history/sessions", response_model=list[HistorySessionSummary])
async def history_sessions() -> list[HistorySessionSummary]:
    return list_sessions()


@app.get("/api/history/sessions/{session_id}", response_model=HistorySessionDetail)
async def history_session_detail(session_id: str) -> HistorySessionDetail:
    return get_session_detail(session_id)


@app.delete("/api/history/sessions/{session_id}")
async def history_session_delete(session_id: str) -> dict[str, str]:
    return delete_session(session_id)


async def _run_analysis(request: AnalysisRequest, client: AmapClient) -> AnalysisResponse:
    request.scenario.businessType = request.scenario.businessType.strip()
    if not request.scenario.businessType:
        request.scenario.businessType = _infer_business_type(request.question)

    if not request.location.address:
        geo = await client.reverse_geocode(request.location.lng, request.location.lat)
        request.location.address = str(geo.get("address") or "")
        request.location.district = str(geo.get("district") or "")

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
    return build_analysis(request, poi_summary)


BUSINESS_LEXICON: dict[str, tuple[str, ...]] = {
    "咖啡": ("咖啡", "咖啡馆", "咖啡厅"),
    "茶饮": ("茶饮", "奶茶", "柠檬茶", "果茶", "茶室", "饮品店"),
    "中餐": ("中餐", "中餐厅", "饭店", "餐厅", "家常菜", "私房菜"),
    "火锅": ("火锅", "串串", "串串香", "麻辣烫", "冒菜"),
    "烧烤": ("烧烤", "烤肉", "撸串", "炸串"),
    "面食": ("面馆", "面店", "米粉", "米线", "螺蛳粉", "牛肉面", "兰州拉面"),
    "快餐": ("快餐", "中式快餐", "简餐", "食堂"),
    "西餐": ("西餐", "西餐厅", "牛排", "意面", "披萨", "汉堡"),
    "日料": ("日料", "日本料理", "寿司", "居酒屋", "日式拉面"),
    "烘焙": ("烘焙", "面包店", "蛋糕店", "甜品店", "点心", "包子铺"),
    "小吃": ("小吃", "炸鸡", "卤味", "鸭脖", "麻辣拌"),
    "便利店": ("便利店", "小卖部", "夫妻店"),
    "超市": ("超市", "生鲜超市", "水果店", "菜店"),
    "文具": ("文具", "文具店", "文具铺"),
    "美发": ("美发", "理发", "理发店", "发廊", "剪发"),
    "美甲": ("美甲", "美睫"),
    "美容": ("美容", "美容院", "皮肤管理", "SPA", "spa"),
    "健身": ("健身", "健身房", "撸铁"),
    "瑜伽": ("瑜伽", "瑜伽馆", "普拉提"),
    "宠物": ("宠物", "宠物店", "宠物医院", "宠物美容", "猫咖", "狗咖"),
    "花店": ("花店", "鲜花", "花艺"),
    "书店": ("书店", "书咖", "绘本馆"),
    "服装": ("服装", "服装店", "买手店", "潮牌", "童装"),
    "酒店": ("酒店", "民宿", "客栈", "旅馆", "宾馆"),
    "药店": ("药店", "药房"),
    "洗车": ("洗车", "汽修", "汽车美容", "汽车保养"),
    "洗衣": ("洗衣", "洗衣店", "干洗"),
    "教培": ("培训", "托管", "早教", "琴行", "画画班"),
    "网吧": ("网吧", "网咖", "电竞馆"),
    "台球": ("台球", "台球厅"),
    "酒吧": ("酒吧", "清吧", "精酿"),
    "足疗": ("足疗", "按摩", "采耳"),
}


def _infer_business_type(question: str) -> str:
    normalized = re.sub(r"\s+", "", question)
    for candidate in _business_type_windows(normalized) + [normalized]:
        matched = _match_business_lexicon(candidate)
        if matched:
            return matched
    return ""


def _business_type_windows(text: str) -> list[str]:
    patterns = [
        r"开(?:一家|一个|一间|个|间)?([^，。！？?,\s]{1,24}?)(?:吗|么|呢|[，。！？?,]|$)",
        r"经营(?:一家|一个|一间|个|间)?([^，。！？?,\s]{1,24}?)(?:吗|么|呢|[，。！？?,]|$)",
        r"做(?:一家|一个|一间|个|间)?([^，。！？?,\s]{1,24}?)(?:吗|么|呢|[，。！？?,]|$)",
        r"适合(?:开)?(?:一家|一个|一间|个|间)?([^，。！？?,\s]{1,24}?)(?:吗|么|呢|[，。！？?,]|$)",
    ]
    windows: list[str] = []
    for pattern in patterns:
        windows.extend(match.group(1) for match in re.finditer(pattern, text))
    return windows


def _match_business_lexicon(text: str) -> str:
    best_alias = ""
    best_canonical = ""
    for canonical, aliases in BUSINESS_LEXICON.items():
        for alias in aliases:
            if alias in text and len(alias) > len(best_alias):
                best_alias = alias
                best_canonical = canonical
    return best_canonical


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
