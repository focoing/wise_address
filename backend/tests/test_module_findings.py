from app.models import (
    AnalysisModule,
    AnalysisRequest,
    Location,
    PointSample,
    PoiSummary,
    Scenario,
    StoreMetrics,
)
from app.services.analysis import build_analysis


def make_request(module: AnalysisModule, store_metrics: StoreMetrics | None = None) -> AnalysisRequest:
    return AnalysisRequest(
        module=module,
        location=Location(lng=114.29, lat=30.58, address="测试地址"),
        scenario=Scenario(businessType="咖啡", radius=1200),
        question="测试问题",
        storeMetrics=store_metrics,
    )


def make_poi_summary(**overrides) -> PoiSummary:
    params = dict(
        total=40,
        byCategory={"餐饮": 30, "汽车服务": 10},
        topPois=[],
        radius=1200,
        competitorCount=0,
    )
    params.update(overrides)
    return PoiSummary(**params)


def test_ecosystem_findings_gaps_and_saturation():
    request = make_request(AnalysisModule.ecosystem_planning)
    analysis = build_analysis(request, make_poi_summary())
    eco = analysis.moduleFindings["ecosystem"]
    assert eco["gaps"] == ["零售", "交通", "办公", "社区生活"]
    assert eco["saturated"] == [{"category": "餐饮", "count": 30, "share": 0.75}]
    assert eco["diversity"] == 2
    assert eco["categoryShare"]["餐饮"] == 0.75


def test_store_diagnosis_conversion_problem():
    metrics = StoreMetrics(monthlyRevenue=200000, monthlyRent=30000, dailyOrders=80, conversionRate=0.05)
    request = make_request(AnalysisModule.store_diagnosis, metrics)
    poi = make_poi_summary(byCategory={"办公": 10, "社区生活": 8, "零售": 6, "交通": 5})
    analysis = build_analysis(request, poi)
    diagnosis = analysis.moduleFindings["diagnosis"]
    assert any("到店转化问题" in problem for problem in diagnosis["problems"])
    assert diagnosis["rentRatio"] == 0.15
    assert diagnosis["signals"]


def test_store_diagnosis_rent_ratio_problem():
    metrics = StoreMetrics(monthlyRevenue=80000, monthlyRent=30000)
    request = make_request(AnalysisModule.store_diagnosis, metrics)
    poi = make_poi_summary(byCategory={"餐饮": 20, "办公": 10})
    analysis = build_analysis(request, poi)
    problems = analysis.moduleFindings["diagnosis"]["problems"]
    assert any("成本结构问题" in problem for problem in problems)


def test_store_diagnosis_without_metrics():
    request = make_request(AnalysisModule.store_diagnosis)
    analysis = build_analysis(request, make_poi_summary())
    assert analysis.moduleFindings["diagnosis"]["problems"] == ["经营数据不足"]


def test_region_findings_consistency():
    request = make_request(AnalysisModule.regional_potential)
    points = [
        PointSample(label=label, lng=114.29, lat=30.58, radius=1200, total=total, byCategory={"餐饮": 30, "办公": 20})
        for label, total in zip(["中心", "东侧", "南侧", "西侧", "北侧"], [50, 48, 52, 49, 51])
    ]
    analysis = build_analysis(request, make_poi_summary(samplePoints=points))
    region = analysis.moduleFindings["region"]
    assert "高" in region["consistency"]
    assert region["cv"] < 0.05
    assert region["samplePointCount"] == 5
    assert set(region["widespreadCategories"]) == {"餐饮", "办公"}
    assert region["localCategories"] == []
    assert [item["total"] for item in region["pointTotals"]] == [50, 48, 52, 49, 51]


def test_region_findings_insufficient_points():
    request = make_request(AnalysisModule.regional_potential)
    analysis = build_analysis(request, make_poi_summary())
    region = analysis.moduleFindings["region"]
    assert region["consistency"] == "数据不足"
    assert region["samplePointCount"] == 0


def test_regional_charts_use_sample_points():
    request = make_request(AnalysisModule.regional_potential)
    points = [
        PointSample(label=label, lng=114.29, lat=30.58, radius=1000, total=total, byCategory={"餐饮": 10})
        for label, total in zip(["A点", "B点", "C点"], [40, 50, 60])
    ]
    analysis = build_analysis(request, make_poi_summary(samplePoints=points))
    trend = analysis.charts["potentialTrend"]
    assert trend["labels"] == ["A点", "B点", "C点"]
    assert trend["values"] == [40, 50, 60]


def test_site_selection_has_no_module_findings():
    request = make_request(AnalysisModule.site_selection)
    analysis = build_analysis(request, make_poi_summary())
    assert analysis.moduleFindings is None
