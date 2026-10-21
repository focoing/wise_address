import asyncio
import json

import pytest

from app.models import (
    AgentTrace,
    AnalysisModule,
    AnalysisRequest,
    Location,
    PoiSummary,
    Scenario,
)
from app.services import agents
from app.services.agents import (
    collect_pois_hardcoded,
    run_answer_pipeline,
    run_data_agent,
)
from app.services.analysis import build_analysis


def make_request(module: AnalysisModule = AnalysisModule.site_selection) -> AnalysisRequest:
    return AnalysisRequest(
        module=module,
        location=Location(lng=114.29, lat=30.58, address="测试地址"),
        scenario=Scenario(businessType="咖啡", radius=1200),
        question="这里适合开咖啡店吗",
    )


def make_analysis(request: AnalysisRequest):
    return build_analysis(
        request,
        PoiSummary(
            total=30,
            byCategory={"餐饮": 12, "办公": 10},
            topPois=[],
            radius=1200,
            competitorCount=5,
        ),
    )


class FakeSettings:
    llm_api_key = "test-key"
    llm_model = "test-model"
    llm_base_url = "https://example.com"


class FakeAmapClient:
    def __init__(self, *, structure_total=40, competitor_total=7, fail_keywords=False):
        self.structure_total = structure_total
        self.competitor_total = competitor_total
        self.fail_keywords = fail_keywords
        self.calls = []

    async def nearby_pois(self, lng, lat, radius, keywords=None, types=None, pages=1):
        self.calls.append({"lng": lng, "lat": lat, "radius": radius, "keywords": keywords, "pages": pages})
        if keywords and self.fail_keywords:
            raise RuntimeError("amap down")
        if keywords:
            return PoiSummary(
                total=self.competitor_total,
                byCategory={"餐饮": self.competitor_total},
                topPois=[],
                radius=radius,
            )
        return PoiSummary(
            total=self.structure_total,
            byCategory={"餐饮": 20, "办公": 12},
            topPois=[],
            radius=radius,
        )


def tool_call(name: str, args: dict) -> dict:
    return {
        "id": f"call_{name}_{len(json.dumps(args))}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


class LLMScript:
    """按顺序返回预置 message；条目为 None 表示该次调用失败。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, settings, messages, tools=None, temperature=0.3):
        self.calls.append({"messages": messages, "tools": tools})
        if not self.responses:
            return {"role": "assistant", "content": "{}"}
        return self.responses.pop(0)


def test_data_agent_happy_path(monkeypatch):
    script = LLMScript([
        {"role": "assistant", "content": "", "tool_calls": [tool_call("search_pois", {"radius": 800, "pages": 2})]},
        {"role": "assistant", "content": "", "tool_calls": [tool_call("search_pois", {"radius": 800, "keywords": "咖啡"})]},
        {"role": "assistant", "content": json.dumps({"radius": 800, "notes": "先结构采样再竞品搜索"}, ensure_ascii=False)},
    ])
    monkeypatch.setattr(agents, "chat_completion", script)
    client = FakeAmapClient()

    summary, notes, ok = asyncio.run(run_data_agent(FakeSettings(), client, make_request()))

    assert ok is True
    assert summary.total == 40
    assert summary.competitorCount == 7
    assert summary.radius == 800
    assert "结构采样" in notes
    assert client.calls[0]["keywords"] is None
    assert client.calls[1]["keywords"] == "咖啡"


def test_data_agent_llm_failure_returns_none(monkeypatch):
    async def fail(*args, **kwargs):
        return None

    monkeypatch.setattr(agents, "chat_completion", fail)
    summary, notes, ok = asyncio.run(run_data_agent(FakeSettings(), FakeAmapClient(), make_request()))
    assert ok is False
    assert summary is None


def test_data_agent_clamps_tool_params(monkeypatch):
    script = LLMScript([
        {"role": "assistant", "content": "", "tool_calls": [tool_call("search_pois", {"radius": 99999, "pages": 99})]},
        {"role": "assistant", "content": json.dumps({"notes": "完成"})},
    ])
    monkeypatch.setattr(agents, "chat_completion", script)
    client = FakeAmapClient()

    summary, notes, ok = asyncio.run(run_data_agent(FakeSettings(), client, make_request()))

    assert ok is True
    assert client.calls[0]["radius"] == 3000
    assert client.calls[0]["pages"] == 3


def test_data_agent_tolerates_tool_error(monkeypatch):
    script = LLMScript([
        {"role": "assistant", "content": "", "tool_calls": [tool_call("search_pois", {"keywords": "咖啡"})]},
        {"role": "assistant", "content": "", "tool_calls": [tool_call("search_pois", {"pages": 2})]},
        {"role": "assistant", "content": json.dumps({"notes": "竞品检索失败后补做结构采样"}, ensure_ascii=False)},
    ])
    monkeypatch.setattr(agents, "chat_completion", script)
    client = FakeAmapClient(fail_keywords=True)

    summary, notes, ok = asyncio.run(run_data_agent(FakeSettings(), client, make_request()))

    assert ok is True
    assert summary.total == 40
    assert summary.competitorCount == 0


def test_data_agent_requires_structure_sample(monkeypatch):
    script = LLMScript([
        {"role": "assistant", "content": json.dumps({"notes": "我直接回答"})},
    ])
    monkeypatch.setattr(agents, "chat_completion", script)
    summary, notes, ok = asyncio.run(run_data_agent(FakeSettings(), FakeAmapClient(), make_request()))
    assert ok is False
    assert summary is None


def test_collect_pois_hardcoded():
    request = make_request()
    client = FakeAmapClient()
    summary = asyncio.run(collect_pois_hardcoded(request, client))
    assert summary.total == 40
    assert summary.competitorCount == 7
    assert client.calls[0]["pages"] == 2

    client2 = FakeAmapClient(fail_keywords=True)
    summary2 = asyncio.run(collect_pois_hardcoded(request, client2))
    assert summary2.competitorCount == 0


def test_pipeline_analyst_failure_uses_template(monkeypatch):
    async def fail(*args, **kwargs):
        return None

    monkeypatch.setattr(agents, "chat_completion", fail)
    request = make_request()
    analysis = make_analysis(request)
    trace = AgentTrace()

    answer, fallback = asyncio.run(run_answer_pipeline(FakeSettings(), request, analysis, trace))

    assert fallback is True
    assert "本地模型" in answer
    assert trace.analyst == "fallback"


def test_pipeline_reviewer_pass(monkeypatch):
    script = LLMScript([
        {"role": "assistant", "content": "报告草稿"},
        {"role": "assistant", "content": json.dumps({"verdict": "pass", "issues": []})},
    ])
    monkeypatch.setattr(agents, "chat_completion", script)
    request = make_request()
    analysis = make_analysis(request)
    trace = AgentTrace()

    answer, fallback = asyncio.run(run_answer_pipeline(FakeSettings(), request, analysis, trace))

    assert fallback is False
    assert answer == "报告草稿"
    assert trace.analyst == "ok"
    assert trace.reviewer == "ok"


def test_pipeline_reviewer_revise_triggers_revision(monkeypatch):
    revised = "修订后的报告"
    script = LLMScript([
        {"role": "assistant", "content": "综合得分 999，明显错误。"},
        {"role": "assistant", "content": json.dumps({"verdict": "revise", "issues": ["得分数字错误"]}, ensure_ascii=False)},
        {"role": "assistant", "content": revised},
    ])
    monkeypatch.setattr(agents, "chat_completion", script)
    request = make_request()
    analysis = make_analysis(request)
    trace = AgentTrace()

    answer, fallback = asyncio.run(run_answer_pipeline(FakeSettings(), request, analysis, trace))

    assert fallback is False
    assert answer == revised
    assert trace.analyst == "ok"
    assert trace.reviewer == "revise"
    assert "得分数字错误" in trace.reviewerNotes


def test_pipeline_reviewer_failure_returns_draft(monkeypatch):
    script = LLMScript([
        {"role": "assistant", "content": "报告草稿"},
        None,
    ])
    monkeypatch.setattr(agents, "chat_completion", script)
    request = make_request()
    analysis = make_analysis(request)
    trace = AgentTrace()

    answer, fallback = asyncio.run(run_answer_pipeline(FakeSettings(), request, analysis, trace))

    assert fallback is False
    assert answer == "报告草稿"
    assert trace.reviewer == "skipped"


def test_pipeline_revision_failure_returns_draft(monkeypatch):
    script = LLMScript([
        {"role": "assistant", "content": "报告草稿"},
        {"role": "assistant", "content": json.dumps({"verdict": "revise", "issues": ["数字错误"]}, ensure_ascii=False)},
        None,
    ])
    monkeypatch.setattr(agents, "chat_completion", script)
    request = make_request()
    analysis = make_analysis(request)
    trace = AgentTrace()

    answer, fallback = asyncio.run(run_answer_pipeline(FakeSettings(), request, analysis, trace))

    assert fallback is False
    assert answer == "报告草稿"
    assert trace.reviewer == "revise"


def test_data_agent_regional_records_point_samples(monkeypatch):
    script = LLMScript([
        {"role": "assistant", "content": "", "tool_calls": [tool_call("search_pois", {"pages": 2})]},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                tool_call("search_pois", {"lng": 114.30, "lat": 30.58, "radius": 900}),
                tool_call("search_pois", {"lng": 114.28, "lat": 30.58, "radius": 900}),
            ],
        },
        {"role": "assistant", "content": json.dumps({"notes": "区域多点采样完成"}, ensure_ascii=False)},
    ])
    monkeypatch.setattr(agents, "chat_completion", script)
    client = FakeAmapClient()
    request = make_request(module=AnalysisModule.regional_potential)

    summary, notes, ok = asyncio.run(run_data_agent(FakeSettings(), client, request))

    assert ok is True
    assert summary.total == 40
    assert summary.radius == 1200  # base 保留中心点采样（默认半径）
    assert [point.label for point in summary.samplePoints] == ["中心", "东侧", "西侧"]
    assert len(client.calls) == 3
    assert client.calls[1]["lng"] == pytest.approx(114.30)
    assert client.calls[2]["lng"] == pytest.approx(114.28)


def test_data_agent_clamps_sub_point_offset(monkeypatch):
    script = LLMScript([
        {"role": "assistant", "content": "", "tool_calls": [tool_call("search_pois", {"pages": 2})]},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [tool_call("search_pois", {"lng": 119.29, "lat": 35.58, "radius": 900})],
        },
        {"role": "assistant", "content": json.dumps({"notes": "完成"}, ensure_ascii=False)},
    ])
    monkeypatch.setattr(agents, "chat_completion", script)
    client = FakeAmapClient()
    request = make_request(module=AnalysisModule.regional_potential)

    summary, notes, ok = asyncio.run(run_data_agent(FakeSettings(), client, request))

    assert ok is True
    # 偏离量被夹紧到中心点 ±0.025 度（约 2.5 公里）
    assert client.calls[1]["lng"] == pytest.approx(114.29 + 0.025)
    assert client.calls[1]["lat"] == pytest.approx(30.58 + 0.025)
    assert summary.samplePoints[1].label == "东北侧"
