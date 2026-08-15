from creative_os.llm_metrics import LLMUsage, parse_usage


def test_parse_usage_from_openai_compatible_response():
    usage = parse_usage(
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 300,
                "total_tokens": 400,
            }
        }
    )

    assert usage == LLMUsage(prompt_tokens=100, completion_tokens=300, total_tokens=400)


def test_parse_usage_returns_none_when_provider_omits_usage():
    assert parse_usage({"choices": []}) is None
