from __future__ import annotations

from app.models import AlternativeRecommendation, AnalysisModule, AnalysisRequest, AnalysisResponse, PoiSummary


MODULE_NAMES = {
    AnalysisModule.site_selection: "品牌新店精准选址",
    AnalysisModule.store_diagnosis: "存量门店优化诊断",
    AnalysisModule.ecosystem_planning: "商业生态规划",
    AnalysisModule.regional_potential: "区域商业潜力评估",
}


def build_analysis(request: AnalysisRequest, poi_summary: PoiSummary) -> AnalysisResponse:
    dimensions = _score_dimensions(request, poi_summary)
    score = round(sum(dimensions.values()) / len(dimensions))
    actions = _actions(request.module, score)
    risks = _risks(request, dimensions)
    evidence = _evidence(request, poi_summary, dimensions)
    charts = _charts(dimensions, poi_summary)
    recommendation = _recommendation(request, score, dimensions)
    alternatives = _alternatives(request, score, dimensions)
    return AnalysisResponse(
        module=request.module,
        score=max(0, min(100, score)),
        dimensions=dimensions,
        poiSummary=poi_summary,
        charts=charts,
        recommendation=recommendation,
        actions=actions,
        risks=risks,
        evidence=evidence,
        estimatedFields=["客流强度", "租金压力", "消费潜力", "竞品压力"],
        alternatives=alternatives,
    )


def _score_dimensions(request: AnalysisRequest, poi_summary: PoiSummary) -> dict[str, int]:
    categories = poi_summary.byCategory
    total = poi_summary.total
    food = categories.get("餐饮", 0)
    retail = categories.get("零售", 0)
    transit = categories.get("交通", 0)
    office = categories.get("办公", 0)
    living = categories.get("社区生活", 0)
    diversity = len([count for count in categories.values() if count > 0])

    traffic = _clamp(42 + transit * 7 + min(total, 25))
    flow = _clamp(38 + office * 6 + living * 4 + retail * 3 + transit * 4)
    competitor_signal = poi_summary.competitorCount or food
    competitors = _clamp(78 - competitor_signal * 4 + request.scenario.competitorTolerance // 4)
    ecosystem = _clamp(36 + diversity * 8 + retail * 3 + food * 2)
    rent = _clamp(82 - min(total, 25) * 2 - request.scenario.rentSensitivity // 3)
    consumption = _clamp(40 + office * 5 + retail * 4 + living * 3)
    match = _business_match(request.scenario.businessType, categories, flow, ecosystem)

    if request.module == AnalysisModule.store_diagnosis and request.storeMetrics:
        metrics = request.storeMetrics
        if metrics.monthlyRevenue and metrics.monthlyRent:
            rent_ratio = metrics.monthlyRent / max(metrics.monthlyRevenue, 1)
            rent = _clamp(92 - int(rent_ratio * 180))
        if metrics.conversionRate is not None:
            match = _clamp(match + int((metrics.conversionRate - 0.12) * 120))

    return {
        "客流强度": flow,
        "交通便利": traffic,
        "竞品压力": competitors,
        "租金健康": rent,
        "消费潜力": consumption,
        "业态匹配": match,
        "生态完整": ecosystem,
    }


def _business_match(business_type: str, categories: dict[str, int], flow: int, ecosystem: int) -> int:
    text = business_type.lower()
    if "咖啡" in text or "茶" in text:
        base = 42 + categories.get("办公", 0) * 7 + categories.get("交通", 0) * 5
    elif "餐" in text or "饭" in text:
        base = 44 + categories.get("办公", 0) * 5 + categories.get("社区生活", 0) * 5
    elif "零售" in text or "便利" in text:
        base = 45 + categories.get("零售", 0) * 4 + categories.get("社区生活", 0) * 5
    else:
        base = 38 + flow // 4 + ecosystem // 4
    return _clamp(base)


def _charts(dimensions: dict[str, int], poi_summary: PoiSummary) -> dict[str, object]:
    category_names = list(poi_summary.byCategory.keys())
    category_values = list(poi_summary.byCategory.values())
    return {
        "radar": [{"name": key, "value": value} for key, value in dimensions.items()],
        "poiBars": {"labels": category_names, "values": category_values},
        "potentialTrend": {
            "labels": ["当前", "3个月", "6个月", "12个月"],
            "values": [
                dimensions["消费潜力"],
                _clamp(dimensions["消费潜力"] + 4),
                _clamp(dimensions["消费潜力"] + 8),
                _clamp(dimensions["消费潜力"] + 12),
            ],
        },
        "ecosystem": {"labels": category_names, "values": category_values},
    }


def _recommendation(request: AnalysisRequest, score: int, dimensions: dict[str, int]) -> str:
    module_name = MODULE_NAMES[request.module]
    address = request.location.address or f"{request.location.lng},{request.location.lat}"
    strongest = max(dimensions, key=dimensions.get)
    weakest = min(dimensions, key=dimensions.get)
    if score >= 78:
        verdict = "建议优先进入尽调与租约谈判阶段"
    elif score >= 62:
        verdict = "具备试点价值，但需要通过业态和租金条件控制风险"
    else:
        verdict = "不建议直接落位，应先寻找替代点位或调整经营模型"
    return f"{module_name}结果：{address} 综合得分 {score}。{verdict}。主要优势是{strongest}，主要短板是{weakest}。"


def _actions(module: AnalysisModule, score: int) -> list[str]:
    common = [
        "复核 500-1500 米范围内竞品、交通入口和主力客群动线。",
        "用不同时段进行现场客流抽样，校准模型估算指标。",
        "将租金、装修、获客成本纳入 12 个月现金流测算。",
    ]
    module_actions = {
        AnalysisModule.site_selection: ["筛选 2-3 个替代点位进行横向打分。", "与业主谈判设置试营业或阶梯租金条款。"],
        AnalysisModule.store_diagnosis: ["拆分到店、外卖、复购三类经营指标定位短板。", "围绕低分维度进行门头、品类、价格带或营销优化。"],
        AnalysisModule.ecosystem_planning: ["补齐区域缺失业态，避免同质化招商。", "按工作日、周末和夜间消费场景规划组合。"],
        AnalysisModule.regional_potential: ["建立候选品牌清单，按客群匹配度排序。", "分阶段验证交通改善、人口导入和竞品变化。"],
    }
    return module_actions[module] + common + (["得分偏低时先降低固定成本承诺。"] if score < 62 else [])


def _risks(request: AnalysisRequest, dimensions: dict[str, int]) -> list[str]:
    risks = []
    if dimensions["竞品压力"] < 55:
        risks.append("周边同类业态密度偏高，需避免价格战和产品同质化。")
    if dimensions["租金健康"] < 55:
        risks.append("租金压力偏高，建议设置租金红线和退出条件。")
    if dimensions["交通便利"] < 55:
        risks.append("交通触达不足，需依赖社区复购或线上获客补足。")
    if request.scenario.radius > 2500:
        risks.append("分析半径较大，可能稀释真实步行可达商圈特征。")
    return risks or ["未发现单一高危维度，但仍需通过线下尽调验证客流与租约条件。"]


def _evidence(request: AnalysisRequest, poi_summary: PoiSummary, dimensions: dict[str, int]) -> list[str]:
    evidence = [
        f"分析半径 {poi_summary.radius} 米，获取周边 POI {poi_summary.total} 个。",
        f"目标业态为 {request.scenario.businessType}，目标客群为 {request.scenario.targetCustomers}。",
        f"模型最高维度为 {max(dimensions, key=dimensions.get)}，最低维度为 {min(dimensions, key=dimensions.get)}。",
        "客流、租金、消费潜力为基于 POI 与场景参数的估算指标。",
    ]
    if poi_summary.competitorCount:
        evidence.insert(1, f"周边同业态（{request.scenario.businessType}）竞品约 {poi_summary.competitorCount} 家。")
    return evidence


def _alternatives(request: AnalysisRequest, score: int, dimensions: dict[str, int]) -> list[AlternativeRecommendation]:
    if score >= 62:
        return []

    weakest = min(dimensions, key=dimensions.get)
    business_type = request.scenario.businessType
    alternatives: list[AlternativeRecommendation] = []

    if weakest == "竞品压力":
        alternatives.append(
            AlternativeRecommendation(
                title="改为差异化或复合业态",
                type="business_type",
                reason=f"当前 {business_type} 周边同类压力偏高，直接进入容易被价格战和同质化分流。",
                steps=[
                    "保留目标客群，但减少与周边同类门店的核心品类重叠。",
                    "增加服务、体验、会员或复合零售属性，形成非价格竞争点。",
                    "重新抽样 500-1000 米范围内竞品菜单、价格带和客群评价。",
                ],
                expectedImpact="降低直接竞品冲突，提高业态识别度和复购空间。",
            )
        )
    elif weakest == "租金健康":
        alternatives.append(
            AlternativeRecommendation(
                title="采用轻资产或小面积试点",
                type="operation",
                reason="租金健康分偏低，固定成本会显著放大试错风险。",
                steps=[
                    "优先谈判快闪、联营、阶梯租金或短租试营业条款。",
                    "压缩首店面积和装修投入，把预算转向获客与复购验证。",
                    "设置 3 个月现金流止损线，未达标时及时退出或转型。",
                ],
                expectedImpact="降低固定成本承诺，保留验证市场的灵活性。",
            )
        )
    elif weakest == "交通便利":
        alternatives.append(
            AlternativeRecommendation(
                title="换到更强到达性的微点位",
                type="location_condition",
                reason="交通便利度不足会影响自然进店和偶发消费。",
                steps=[
                    "优先寻找地铁口、公交站、社区主入口或办公楼大堂动线附近点位。",
                    "现场记录早晚高峰、午间和周末三类时段的可见客流。",
                    "把门头可见性和步行绕行距离纳入二次筛选。",
                ],
                expectedImpact="提升自然曝光和到店效率，减少对线上投放的依赖。",
            )
        )
    elif weakest in {"客流强度", "消费潜力"}:
        alternatives.append(
            AlternativeRecommendation(
                title="寻找更高密度客群区域",
                type="location_condition",
                reason=f"{weakest}偏低，当前区域对 {business_type} 的需求承载可能不足。",
                steps=[
                    "优先比较办公、社区、学校或交通节点更密集的候选区域。",
                    "缩小分析半径到真实步行可达范围，重新评估有效客流。",
                    "若坚持当前区域，改为预约制、社群制或低客流依赖模型。",
                ],
                expectedImpact="提高目标客群触达率，减少低客流导致的坪效压力。",
            )
        )
    elif weakest == "业态匹配":
        alternatives.append(
            AlternativeRecommendation(
                title="调整为更匹配周边生态的品类",
                type="business_type",
                reason=f"当前周边 POI 结构与 {business_type} 的匹配度不足。",
                steps=[
                    "根据周边主力 POI 重新定义目标客群和消费场景。",
                    "选择更贴近日常高频、办公配套或社区刚需的品类方向。",
                    "用同一套场景参数对替代品类重新打分，再决定是否进入尽调。",
                ],
                expectedImpact="提高业态与区域需求的贴合度，降低开业后教育市场成本。",
            )
        )

    alternatives.append(
        AlternativeRecommendation(
            title="保留观察，先做低成本验证",
            type="operation",
            reason="综合评分低于建议落位阈值，直接签约存在较高不确定性。",
            steps=[
                "用 1-2 周进行现场客流、竞品和消费访谈验证。",
                "制作最低可行经营模型，测算保本点和最差情形现金流。",
                "同时寻找至少 2 个替代点位进行横向评分。",
            ],
            expectedImpact="避免过早锁定低质量点位，提高最终选址成功率。",
        )
    )
    return alternatives


def _clamp(value: int | float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))
