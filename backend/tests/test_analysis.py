from app.models import AnalysisModule, AnalysisRequest, Location, PoiItem, PoiSummary, Scenario
from app.services.analysis import build_analysis


def test_analysis_returns_structured_result() -> None:
    request = AnalysisRequest(
        module=AnalysisModule.site_selection,
        location=Location(lng=121.4737, lat=31.2304, address="上海市人民广场"),
        scenario=Scenario(businessType="精品咖啡", radius=1200),
        question="这里适合开店吗？",
    )
    poi_summary = PoiSummary(
        total=3,
        byCategory={"办公": 1, "交通": 1, "餐饮": 1},
        topPois=[PoiItem(name="示例POI", type="商务住宅", distance=120)],
        radius=1200,
    )

    result = build_analysis(request, poi_summary)

    assert 0 <= result.score <= 100
    assert result.dimensions
    assert result.actions
    assert "客流" in result.estimatedFields[0]


def test_low_score_analysis_returns_alternatives() -> None:
    request = AnalysisRequest(
        module=AnalysisModule.site_selection,
        location=Location(lng=121.4737, lat=31.2304, address="测试点位"),
        scenario=Scenario(businessType="文具店", radius=300, rentSensitivity=100, competitorTolerance=0),
        question="这里适合开一家文具店吗？",
    )
    poi_summary = PoiSummary(total=30, byCategory={"餐饮": 20}, topPois=[], radius=300)

    result = build_analysis(request, poi_summary)

    assert result.score < 62
    assert result.alternatives
    assert any(item.type in {"business_type", "operation", "location_condition"} for item in result.alternatives)


def test_high_score_analysis_has_no_alternatives() -> None:
    request = AnalysisRequest(
        module=AnalysisModule.site_selection,
        location=Location(lng=121.4737, lat=31.2304, address="测试点位"),
        scenario=Scenario(businessType="餐厅", radius=1200, rentSensitivity=0, competitorTolerance=100),
        question="这里适合开一家餐厅吗？",
    )
    poi_summary = PoiSummary(
        total=8,
        byCategory={"办公": 3, "交通": 2, "社区生活": 2, "零售": 1},
        topPois=[],
        radius=1200,
    )

    result = build_analysis(request, poi_summary)

    assert result.score >= 62
    assert result.alternatives == []
