from app.main import _infer_business_type


def test_infers_open_business_types() -> None:
    assert _infer_business_type("这里适合开一家文具店吗？请给出理由和下一步动作。") == "文具"
    assert _infer_business_type("这里适合开一家服装店吗？") == "服装"
    assert _infer_business_type("这里适合开一家餐厅吗？") == "中餐"
    assert _infer_business_type("我想开个奶茶店") == "茶饮"


def test_longest_alias_match_wins() -> None:
    assert _infer_business_type("我想开个日式拉面") == "日料"
    assert _infer_business_type("开一家兰州拉面") == "面食"


def test_ignores_question_words_and_modifiers() -> None:
    assert _infer_business_type("这里适合开什么店？") == ""
    assert _infer_business_type("在这里开一家稍微高端点的咖啡店怎么样") == "咖啡"


def test_window_takes_priority_over_full_text() -> None:
    assert _infer_business_type("健身房楼下开便利店") == "便利店"


def test_falls_back_to_full_question_without_verb() -> None:
    assert _infer_business_type("咖啡店在这个位置能活吗") == "咖啡"


def test_keeps_existing_scenario_when_question_has_no_business_type() -> None:
    assert _infer_business_type("请分析这个位置") == ""
