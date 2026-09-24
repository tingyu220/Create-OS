from creative_os.agent_intent import AgentIntentRequest, accept_agent_intent


def test_agent_accepts_natural_language_self_check_without_fixed_checklist():
    receipt = accept_agent_intent(AgentIntentRequest("p", 79, "这一章目前写得不对，你自己检查一下。", "作者"))
    assert receipt.status == "accepted"
    assert "自行选择必要上下文" in receipt.message

