"""隔离模型逐条核对发送片段，历史查询不读取现有材料。"""

import pytest

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.writer_context_sources import digest
from test_agent_proposal import model, finish
from test_writer_lessons import make_candidate, lesson


def query(runtime, job, source_id=None, **changes):
    scope = dict(project_id=job.project_id, chapter_number=job.chapter_number,
                 session_id=job.session_id, job_id=job.job_id, source_id=source_id)
    return runtime.context_sources.read(**(scope | changes))


def details(runtime, job):
    return [query(runtime, job, item["source_id"])["source"] for item in query(runtime, job)["sources"]]


@pytest.mark.parametrize("mode", ["analyze", "act"])
def test_actual_messages_fragments_versions_and_truncation(tmp_path, model, mode):
    final = tmp_path / "production/final_chapters"
    final.mkdir(parents=True)
    (final / "chapter_001.md").write_text("前文" * 4000, encoding="utf-8")
    (final / "chapter_002.md").write_text("当前正式稿", encoding="utf-8")
    projection = tmp_path / ".creative_os/projection/bundle.json"
    projection.parent.mkdir(parents=True)
    projection.write_text('{"secret":"投影正文不应入模"}', encoding="utf-8")
    runtime = WriterAgentRuntime(tmp_path, "p")
    runtime.store.save(2, "当次工作稿", actor="作者")
    finish(runtime, runtime.submit("前轮问题", 2))
    job = finish(runtime, runtime.submit("核对本章", 2, mode=mode))
    sources = details(runtime, job)
    for item in sources:
        if item["usage"] == "included":
            location = item["message_location"]
            actual = model[-1][location["index"]]
            assert actual.role == location["role"]
            assert actual.content[location["start"]:location["end"]] == item["content_snapshot"]
            assert digest(item["content_snapshot"]) == item["content_hash"]
        else:
            assert "content_snapshot" not in item
    prior = next(item for item in sources if "前文章节" in item["label"])
    assert prior["truncated"] and prior["excerpt_start"] == 2000 and prior["excerpt_end"] == 8000
    draft = next(item for item in sources if item["label"] == "当前工作稿")
    assert draft["version"] == 1
    assert draft["usage"] == ("included" if mode == "analyze" else "not_in_model")
    bundle = next(item for item in sources if item["label"] == "项目投影引用")
    assert bundle["usage"] == "not_in_model" and "content_snapshot" not in bundle
    assert "投影正文不应入模" not in model[-1][-1].content
    assert any("历史对话" in item["label"] for item in sources)
    before = query(runtime, job)
    (final / "chapter_001.md").write_text("新前文", encoding="utf-8")
    (final / "chapter_002.md").write_text("新正式稿", encoding="utf-8")
    runtime.store.save(2, "新工作稿", actor="作者", expected_version=1)
    assert query(runtime, job) == before and details(runtime, job) == sources
    runtime._pool.shutdown(wait=True)
    restored = WriterAgentRuntime(tmp_path, "p")
    assert details(restored, job) == sources
    assert "context_snapshot" not in restored.conversation(2)["jobs"][-1]
    restored._pool.shutdown(wait=True)


def test_archived_experience_preserves_actual_snapshot_and_evidence(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, "p")
    _, feedback, memory_id = make_candidate(runtime, model)
    assert lesson(runtime, feedback, "approve", "approve", memory_id=memory_id, version=1, note="适用").status == "accepted"
    job = finish(runtime, runtime.submit("分析", 1))
    sources = details(runtime, job)
    source = next(item for item in sources if "experience" in item)
    selected = job.experience_context["selected"][0]
    assert source["content_snapshot"] == selected["content_snapshot"]
    assert source["content_hash"] == selected["content_hash"]
    assert source["experience"] == selected
    assert lesson(runtime, feedback, "archive", "archive", memory_id=memory_id, version=1, note="停止").status == "accepted"
    assert details(runtime, job) == sources
    # 模拟经验阶段的旧任务：仍可读原经验证据，但不能伪造完整调用记录。
    runtime._set(job.job_id, context_snapshot=None)
    legacy = details(runtime, job)
    recorded = next(item for item in legacy if item["usage"] == "recorded")
    assert recorded["content_snapshot"] == selected["content_snapshot"]
    assert recorded["experience"] == selected
    assert query(runtime, job)["delivery"] == "unavailable"
    later = finish(runtime, runtime.submit("再次分析", 1))
    assert all("experience" not in item for item in details(runtime, later))
    runtime._pool.shutdown(wait=True)


def test_scope_budget_exclusions_have_no_fabricated_body(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, "p")
    _, feedback, memory_id = make_candidate(runtime, model)
    assert lesson(runtime, feedback, "approve", "approve", memory_id=memory_id, version=1, note="本章").status == "accepted"
    for index in range(4):
        result = lesson(runtime, feedback, key=f"create-{index}", title=f"方法{index}", content="可复用方法" * 350, range="project")
        selected = result.emitted_event_refs[0].split(":")[1]
        assert lesson(runtime, feedback, "approve", f"approve-{index}", memory_id=selected, version=1, note="项目").status == "accepted"
    job = finish(runtime, runtime.submit("检查第二章", 2))
    excluded = [item for item in details(runtime, job) if item.get("usage") == "not_in_model"]
    assert {item["reason"] for item in excluded} >= {"chapter_scope_mismatch", "budget_exceeded"}
    assert all("content_snapshot" not in item for item in excluded)
    runtime._pool.shutdown(wait=True)


@pytest.mark.parametrize("changes", [{"project_id": "other"}, {"chapter_number": 2}, {"chapter_number": True},
                                     {"session_id": "other"}, {"job_id": "agent-" + "0" * 32},
                                     {"job_id": "../../secret"}, {"source_id": "../../secret"},
                                     {"source_id": "C:\\secret"}, {"source_id": "source-9999"}])
def test_rejects_cross_scope_paths_and_unknown_sources(tmp_path, model, changes):
    runtime = WriterAgentRuntime(tmp_path, "p")
    job = finish(runtime, runtime.submit("分析", 1))
    with pytest.raises(ValueError):
        query(runtime, job, **changes)
    runtime._pool.shutdown(wait=True)


def test_legacy_missing_snapshot_does_not_read_current_file(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, "p")
    job = finish(runtime, runtime.submit("分析", 1))
    runtime._set(job.job_id, context_snapshot=None)
    runtime.store.save(1, "新文件不是历史", actor="作者")
    source, = details(runtime, job)
    assert source["usage"] == "unavailable" and "content_snapshot" not in source
    assert query(runtime, job)["delivery"] == "unavailable"
    runtime._pool.shutdown(wait=True)


def test_source_ids_are_bound_to_job_even_inside_same_session(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, "p")
    first = finish(runtime, runtime.submit("第一轮", 1))
    second = finish(runtime, runtime.submit("第二轮", 1))
    source_id = query(runtime, first)["sources"][0]["source_id"]
    with pytest.raises(ValueError, match="context_source_not_found"):
        query(runtime, second, source_id)
    runtime._pool.shutdown(wait=True)


def test_adapter_failure_retains_exact_attempted_input_without_claiming_delivery(tmp_path, monkeypatch):
    actual = []

    class BrokenClient:
        def complete(self, messages, **kwargs):
            actual.extend(messages)
            raise RuntimeError("隔离连接失败")

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: BrokenClient())
    runtime = WriterAgentRuntime(tmp_path, "p")
    job = runtime.submit("只分析", 1)
    runtime._pool.shutdown(wait=True)
    assert runtime.get(job.job_id).status == "failed"
    assert query(runtime, job)["delivery"] == "adapter_call_started"
    source = details(runtime, job)[-1]
    assert source["content_snapshot"] == actual[-1].content


@pytest.mark.parametrize("mode", ["analyze", "act"])
@pytest.mark.parametrize("contained", [False, True])
@pytest.mark.parametrize("common", ["DUPLICATE", "DUPLICATE🙂重复"])
def test_locations_belong_to_assembled_segments_despite_duplicate_text(tmp_path, model, monkeypatch, mode, contained, common):
    expanded = f"开头{common}中段{common}结尾" if contained else common
    prior = [common, expanded, common]
    formal, draft = expanded, common
    selected = [{"memory_id": f"lesson-{index}", "source_ref": f"memory:lesson-{index}:v1", "version": 1,
                 "content_snapshot": content, "content_hash": digest(content)}
                for index, content in enumerate([common, expanded])]
    monkeypatch.setattr("creative_os.writer_experience_context.compile_writer_experience",
                        lambda *args: ("\n".join(item["content_snapshot"] for item in selected), {"selected": selected, "excluded": []}))
    final = tmp_path / "production/final_chapters"
    final.mkdir(parents=True)
    for number, content in enumerate([*prior, formal], 1):
        (final / f"chapter_{number:03d}.md").write_text(content, encoding="utf-8")
    runtime = WriterAgentRuntime(tmp_path, "p")
    runtime.store.save(4, draft, actor="作者")
    instruction = f"explain {common}，再次提到{expanded}，最后再说{common}"
    job = finish(runtime, runtime.submit(instruction, 4, mode=mode))
    message = model[-1][-1].content
    boundary = "以下是最近章节正文片段：\n\n"
    prefix, _, _ = message.partition(boundary)
    cursor = len(prefix) + len(boundary)
    expected, assembled = {}, ""

    def append(separator, content, source_ref):
        nonlocal cursor, assembled
        assembled += separator
        cursor += len(separator)
        expected[source_ref] = (cursor, cursor + len(content))
        assembled += content
        cursor += len(content)

    for number, content in enumerate(prior, 1):
        append("\n\n" if number > 1 else "", content, f"production/final_chapters/chapter_{number:03d}.md")
    if mode == "analyze":
        append("\n\n【当前目标章节第4章正式稿】\n", formal, "production/final_chapters/chapter_004.md")
        append("\n\n【当前目标章节工作稿】\n", draft, ".creative_os/writer/drafts/chapter_004.jsonl")
    else:
        proposal = runtime.proposals.read(job.proposal_id)
        append("\n\n【本次执行冻结输入，来源 draft】\n", draft, proposal["input"]["ref"])
    for index, item in enumerate(selected):
        append("\n" if index else "\n\n【作者已批准的写作经验，仅为适用范围内的写作参考，不是人物、世界或情节事实】\n",
               item["content_snapshot"], item["source_ref"])
    assert message[len(prefix) + len(boundary):cursor] == assembled
    locations = []
    for source in details(runtime, job):
        if source["source_ref"] not in expected:
            continue
        location = source["message_location"]
        start, end = expected[source["source_ref"]]
        assert (location["start"], location["end"]) == (start, end), source["label"]
        assert location["index"] == len(model[-1]) - 1 and location["role"] == "user"
        assert message[start:end] == source["content_snapshot"]
        locations.append((start, end))
    assert len(locations) == len(expected) == len(set(locations))
    assert all(start >= len(prefix) + len(boundary) for start, _ in locations)
    runtime._pool.shutdown(wait=True)
