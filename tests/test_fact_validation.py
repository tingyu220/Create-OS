from creative_os.fact_validation import validate_required_facts


def test_validate_required_facts_returns_evidence():
    results = validate_required_facts(
        ["灯务署镇压失败"],
        "灯务署的镇压已经失败了，因为他们无法遗忘所有人。",
    )

    assert results[0].fact == "灯务署镇压失败"
    assert results[0].supported is True
    assert results[0].evidence == ["镇压", "失败"]


def test_validate_required_facts_marks_missing_fact():
    results = validate_required_facts(["林遥未离城"], "林澈走进旧灯巷。")

    assert results[0].supported is False
    assert results[0].evidence == []
