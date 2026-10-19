from pathlib import Path

from app.models import AgentResponse, AnalysisModule, AnalysisRequest, Location, PoiSummary, Scenario
from app.services.analysis import build_analysis
from app.services import history


def test_history_session_lifecycle(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "history.db"
    monkeypatch.setattr(history, "DATA_DIR", tmp_path)
    monkeypatch.setattr(history, "DB_PATH", db_path)

    request = AnalysisRequest(
        module=AnalysisModule.site_selection,
        location=Location(lng=121.4737, lat=31.2304, address="上海市人民广场", district="黄浦区"),
        scenario=Scenario(businessType="精品咖啡", radius=1200),
        question="这里适合开店吗？",
    )
    analysis = build_analysis(
        request,
        PoiSummary(total=1, byCategory={"交通": 1}, topPois=[], radius=1200),
    )
    response = AgentResponse(answer="适合谨慎评估。", analysis=analysis, usedModel="test", fallback=False)

    session_id, turn_id = history.save_agent_history(request, analysis, response)
    second_session_id, _ = history.save_agent_history(request, analysis, response)

    assert session_id == second_session_id
    assert turn_id
    sessions = history.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].turnCount == 2

    detail = history.get_session_detail(session_id)
    assert len(detail.turns) == 2
    assert detail.turns[0].analysis.score == analysis.score

    deleted = history.delete_session(session_id)
    assert deleted["status"] == "deleted"
    assert history.list_sessions() == []
