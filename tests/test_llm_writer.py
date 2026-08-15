import pytest

from creative_os.llm_writer import (
    ChapterRewriteInput,
    ModelMessage,
    OpenAICompatibleClient,
    build_chapter_rewrite_input,
    build_writer_messages,
    promote_llm_writer_pilot_to_final,
    revalidate_llm_writer_pilot,
    run_llm_writer_pilot,
    validate_llm_rewrite,
)
from creative_os.validation_runtime import write_v11_acceptance_artifacts


def test_openai_compatible_client_reads_env(monkeypatch):
    monkeypatch.setenv("CREATIVE_OS_LLM_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("CREATIVE_OS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("CREATIVE_OS_LLM_MODEL", "writer-model")

    client = OpenAICompatibleClient.from_env()

    assert client.base_url == "https://api.example.test/v1"
    assert client.api_key == "sk-test"
    assert client.model == "writer-model"


def test_openai_compatible_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("CREATIVE_OS_LLM_API_KEY", raising=False)
    monkeypatch.setenv("CREATIVE_OS_LLM_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("CREATIVE_OS_LLM_MODEL", "writer-model")

    with pytest.raises(ValueError, match="CREATIVE_OS_LLM_API_KEY"):
        OpenAICompatibleClient.from_env(None)


def test_openai_compatible_client_reads_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CREATIVE_OS_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("CREATIVE_OS_LLM_API_KEY", raising=False)
    monkeypatch.delenv("CREATIVE_OS_LLM_MODEL", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "CREATIVE_OS_LLM_BASE_URL=https://api.dotenv.test/v1\n"
        "CREATIVE_OS_LLM_API_KEY=sk-dotenv\n"
        "CREATIVE_OS_LLM_MODEL=dotenv-model\n",
        encoding="utf-8",
    )

    client = OpenAICompatibleClient.from_env(env_path)

    assert client.base_url == "https://api.dotenv.test/v1"
    assert client.api_key == "sk-dotenv"
    assert client.model == "dotenv-model"


def test_openai_compatible_client_prefers_process_env_over_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_OS_LLM_API_KEY", "sk-process")
    monkeypatch.setenv("CREATIVE_OS_LLM_MODEL", "process-model")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "CREATIVE_OS_LLM_API_KEY=sk-dotenv\n"
        "CREATIVE_OS_LLM_MODEL=dotenv-model\n",
        encoding="utf-8",
    )

    client = OpenAICompatibleClient.from_env(env_path)

    assert client.api_key == "sk-process"
    assert client.model == "process-model"


def test_build_chapter_rewrite_input_for_chapter_four(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)

    payload = build_chapter_rewrite_input(tmp_path, 4)

    assert payload.chapter_number == 4
    assert payload.title == "废档案"
    assert "废弃档案库" in payload.source_text
    assert "进入废弃档案库并建立档案被清理过的异常" in payload.scene_goals
    assert "档案库与灯务署系统仍连接" in payload.required_facts
    assert "Context" in payload.banned_terms
    assert payload.min_chinese_chars >= 1000


def test_build_chapter_rewrite_input_deduplicates_required_facts(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)

    payload = build_chapter_rewrite_input(tmp_path, 12)

    assert len(payload.required_facts) == len(set(payload.required_facts))


def test_writer_prompt_contains_continuity_and_anti_ai_constraints(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)
    payload = build_chapter_rewrite_input(tmp_path, 4)

    messages = build_writer_messages(payload)
    joined = "\n".join(message.content for message in messages)

    assert "不要把三个场景机械拼接" in joined
    assert "转场必须服务情绪、动作或信息推进" in joined
    assert "不要使用统一时间词开头" in joined
    assert "档案库与灯务署系统仍连接" in joined


def test_validate_llm_rewrite_rejects_time_opener_and_shrinkage(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)
    payload = build_chapter_rewrite_input(tmp_path, 4)

    issues = validate_llm_rewrite(payload, "# 第 4 章：废档案\n\n凌晨，林澈站在门外。")

    assert "time_word_opener" in issues
    assert "below_minimum_chinese_chars" in issues


def test_validate_llm_rewrite_accepts_supported_paraphrased_facts(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)
    payload = build_chapter_rewrite_input(tmp_path, 4)
    text = (
        "# 第 4 章：废档案\n\n"
        "钥匙插进去的时候，林澈感觉到锁芯在吃他的指纹。"
        "档案库没有彻底废弃。维护员林澈，权限等级未变更，系统仍识别他为维护员。"
        "档案库与灯务署系统仍然连接。林遥的公开档案下层浮出被覆盖后的底稿。"
        "自愿离城名单的原始底稿里，林澈看见了岚舟。编号相同，两个人，同一个回声室。"
        "许砚看见了屏幕上的回声室编号，但她没有上报。林澈拉着阿岚退入侧门继续逃。"
    )
    text += "雾压着门缝。林澈把每一个名字都记进心里。" * 120

    issues = validate_llm_rewrite(payload, text)

    assert not [issue for issue in issues if issue.startswith("missing_fact:")]


def test_validate_llm_rewrite_accepts_generic_supported_facts(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)
    payload = build_chapter_rewrite_input(tmp_path, 7)
    text = (
        "# 第 7 章：维护员\n\n"
        "白塔旧址的门比记忆中矮了一截。墙上一整面线路图曾经完整，"
        "但关键节点被金属刮刀毁掉，刀痕精准地切进模块编号。"
        "林澈看出旧检修网的回路，冷光塔的供能线路从这里分出去，"
        "向下延伸的接口指向回声室。封条背面写着维护员林澈签署过协议，"
        "时间正是三年前冷光塔升级期间。LC-0427 工具箱被系统封存，"
        "锁扣验证后，系统仍承认林澈的维护权限，冷光塔也开始响应旧编号，"
        "塔底巡灯员注意到异常，正朝这边移动。"
    )
    text += "旧塔里的冷光一截一截爬上墙面。" * 120

    issues = validate_llm_rewrite(payload, text)

    assert not [issue for issue in issues if issue.startswith("missing_fact:")]


def test_validate_llm_rewrite_accepts_final_record_and_crackdown_paraphrases():
    payload = ChapterRewriteInput(
        chapter_number=32,
        title="反证",
        source_text="",
        previous_summary="",
        scene_goals=[],
        required_facts=["岚舟最后记录出现", "灯务署镇压失败"],
        banned_terms=[],
        min_chinese_chars=1,
    )
    text = (
        "# 第 32 章：反证\n\n"
        "最后一条解锁的记录的日期是今天。姓名：岚舟。"
        "灯务署的镇压已经失败了，不是因为他们人手不够，是因为他们无法遗忘所有人。"
    )

    issues = validate_llm_rewrite(payload, text)

    assert not [issue for issue in issues if issue.startswith("missing_fact:")]


def test_validate_llm_rewrite_accepts_ending_closure_without_meta_terms():
    payload = ChapterRewriteInput(
        chapter_number=36,
        title="第一盏灯",
        source_text="",
        previous_summary="",
        scene_goals=[],
        required_facts=["主线闭合", "雾城出现第一盏自愿点亮的灯"],
        banned_terms=[],
        min_chinese_chars=1,
    )
    text = (
        "# 第 36 章：第一盏灯\n\n"
        "林遥选择留下来，林澈把复印件收进怀里，阿岚和许砚跟上。"
        "雾城南街那截冷光管还在砖沿上亮着，不属于任何一份照明档案。"
        "那是一个人自愿点亮的灯。第一盏。"
    )

    issues = validate_llm_rewrite(payload, text)

    assert not [issue for issue in issues if issue.startswith("missing_fact:")]


class FakeWriterClient:
    def __init__(self):
        self.calls = 0

    def complete(self, messages: list[ModelMessage], *, temperature: float, max_tokens: int) -> str:
        self.calls += 1
        prompt = next(message.content for message in messages if "请重写《雾城回声》第" in message.content)
        if "第 4 章" in prompt:
            return _fake_chapter(4, "废档案", "林澈把手套压在废弃档案库门缝上。")
        if "第 5 章" in prompt:
            return _fake_chapter(5, "审查室", "许砚没有先看口供，她先看林澈的手。")
        return _fake_chapter(6, "白塔旧址", "白塔旧址的墙面先认出了林澈。")


def test_run_llm_writer_pilot_writes_chapters_four_to_six(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)

    record = run_llm_writer_pilot(tmp_path, FakeWriterClient())

    assert record["result"] == "pass"
    assert record["chapters"] == [4, 5, 6]
    assert (tmp_path / "llm_writer_pilot" / "chapters" / "chapter_004.md").exists()
    assert (tmp_path / "llm_writer_pilot" / "inputs" / "chapter_004_input.json").exists()
    assert (tmp_path / "llm_writer_pilot" / "reviews" / "chapter_004_review.json").exists()
    chapter_004 = (tmp_path / "llm_writer_pilot" / "chapters" / "chapter_004.md").read_text(encoding="utf-8")
    assert not chapter_004.splitlines()[2].startswith(("凌晨", "清晨", "上午", "中午", "下午", "傍晚", "夜", "深夜"))


class RetryAwareFakeWriterClient:
    def __init__(self):
        self.prompts: list[str] = []

    def complete(self, messages: list[ModelMessage], *, temperature: float, max_tokens: int) -> str:
        prompt = "\n".join(message.content for message in messages)
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            return "# 第 4 章：废档案\n\n凌晨，林澈站在门外。"
        return _fake_chapter(4, "废档案", "林澈把手套压在废弃档案库门缝上。")


def test_run_llm_writer_pilot_sends_review_feedback_on_retry(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)
    client = RetryAwareFakeWriterClient()

    record = run_llm_writer_pilot(tmp_path, client, chapters=[4], max_attempts=2)

    assert record["result"] == "pass"
    assert len(client.prompts) == 2
    assert "上一版未通过质量门禁" in client.prompts[1]
    assert "time_word_opener" in client.prompts[1]
    assert "below_minimum_chinese_chars" in client.prompts[1]
    assert record["attempts"]["chapter_004"] == 2


def test_revalidate_llm_writer_pilot_updates_existing_reviews(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)
    run_llm_writer_pilot(tmp_path, FakeWriterClient(), chapters=[4])

    record = revalidate_llm_writer_pilot(tmp_path, chapters=[4])

    assert record["result"] == "pass"
    assert record["mode"] == "revalidate"
    review = (tmp_path / "llm_writer_pilot" / "reviews" / "chapter_004_review.json").read_text(encoding="utf-8")
    assert '"mode": "revalidate"' in review


def test_promote_llm_writer_pilot_to_final_replaces_canonical_chapter_and_rebuilds_drafts(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)
    run_llm_writer_pilot(tmp_path, FakeWriterClient(), chapters=[4])
    old_chapter = (tmp_path / "final_chapters" / "chapter_004.md").read_text(encoding="utf-8")
    assert "查清档案库被清理过的痕迹" in old_chapter

    record = promote_llm_writer_pilot_to_final(tmp_path, chapters=[4])

    assert record["result"] == "pass"
    promoted = (tmp_path / "final_chapters" / "chapter_004.md").read_text(encoding="utf-8")
    polished = (tmp_path / "drafts" / "final_draft_polished.md").read_text(encoding="utf-8")
    assert "林澈把手套压在废弃档案库门缝上" in promoted
    assert "查清档案库被清理过的痕迹" not in promoted
    assert "林澈把手套压在废弃档案库门缝上" in polished
    assert "查清档案库被清理过的痕迹" not in polished
    assert (tmp_path / "backups" / "canonical_before_llm_writer_pilot_promotion" / "final_chapters" / "chapter_004.md").exists()


def _fake_chapter(number: int, title: str, first_sentence: str) -> str:
    required = {
        4: [
            "废弃档案库未彻底废弃",
            "林澈旧维护权限可进入档案库",
            "档案库与灯务署系统仍连接",
            "林遥档案被覆盖",
            "岚舟档案与林遥同属回声室编号",
            "自愿离城名单存在原始底稿",
            "许砚知道回声室编号",
            "许砚没有立即上报全部证据",
            "林澈和阿岚继续逃亡",
        ],
        5: [
            "林澈熟悉审查室结构",
            "许砚怀疑林澈旧身份",
            "林澈刻意隐藏冷光管核心信息",
            "许砚看见林遥残影",
            "低亮冷光可在审查室环境显影",
            "林澈愿意冒险证明林遥未离城",
            "审查记录存在缺页",
            "缺页与回声室编号相关",
            "许砚开始保护证据链",
        ],
        6: [
            "白塔旧址保存旧事故档案",
            "白姨知道回声室相关旧事",
            "十年前事故与禁灯令升级有关",
            "林澈有旧维护员编号",
            "白姨认识年少林澈",
            "周闻白与白塔事故存在隐秘关联",
            "林澈曾安装回声室相关模块",
            "冷光塔前身与白塔有关",
            "林澈记忆被剪除不是偶然",
        ],
    }[number]
    paragraphs = [
        first_sentence + f" 第{index}次核对时，" + "。".join(required) + "。"
        for index in range(1, 81)
    ]
    body = "\n\n".join(paragraphs)
    return f"# 第 {number} 章：{title}\n\n{body}\n"
