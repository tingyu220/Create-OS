import ast
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from creative_os.domains.writer_admission import AdmittedContractProjection, WriterAdmissionError, WriterAdmissionToken
from creative_os.llm_writer import promote_llm_writer_pilot_to_final, run_llm_writer_pilot
from creative_os.novel_continuation_runner import PreparedWriterRun, continue_one_chapter, promote_passing_draft
from creative_os.domains.novel_continuation import ContinuationTask
from writer_architecture_checks import module_name, qualified_definitions, signature, validate_transparent_delegate


MANIFEST = Path("tests/assets/writer_production_exits_v4.json")
PUBLIC = {
    "creative_os.novel_continuation_runner.continue_one_chapter",
    "creative_os.novel_continuation_runner.promote_passing_draft",
    "creative_os.llm_writer.run_llm_writer_pilot",
    "creative_os.llm_writer.promote_llm_writer_pilot_to_final",
}


def _definitions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return tree, {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def test_versioned_manifest_has_exact_ast_signatures_and_all_scanned_sinks():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(manifest) == 14
    assert {item["symbol"] for item in manifest if item["kind"].startswith("public_")} == PUBLIC
    for item in manifest:
        tree, _ = _definitions(Path(item["file"]))
        qualified_name = item["symbol"].removeprefix(module_name(item["file"]) + ".")
        node = qualified_definitions(tree)[qualified_name]
        assert signature(qualified_name, node) == item["signature"]
        body = ast.unparse(node)
        if item["kind"] == "model_client_sink":
            assert any(isinstance(call.func, ast.Attribute) and call.func.attr == "complete"
                       for call in ast.walk(node) if isinstance(call, ast.Call))
        if item["kind"] == "final_chapter_write_sink":
            assert "final_chapters" in body and ("write_text" in body or "_write_text" in body)
        if item["kind"] == "human_approved_import_sink":
            assert "approval.json" in body and "shutil.copy2" in body
        if item["kind"] == "transparent_delegate":
            assert item["business_entry"] == "creative_os.runtime.runner.RuntimeRunner.execute"
            assert item["allowed_constructors"] == ["creative_os.agent_runtime.WriterAgentRuntime._run", "creative_os.agent_runtime.WriterAgentRuntime._execute_story_step"]
        if item["kind"] == "controlled_model_step":
            assert item["scopes"] == ["story", "chapter", "combat"]
            assert item["max_steps"] == {"story": 6, "chapter": 6, "combat": 4}
            assert not any(isinstance(node, (ast.For, ast.While, ast.AsyncFor)) for node in ast.walk(node))
        if item["kind"] == "bounded_tool_loop":
            assert item["model_entry"] == "creative_os.agent_runtime.WriterAgentRuntime._execute_story_step"
            assert item["max_steps"] == (4 if item["symbol"].endswith("run_combat_expert") else 6)
    assert [item["symbol"] for item in manifest if item["kind"] == "model_client_sink"] == ["creative_os.runtime.runner.RuntimeRunner.execute"]

    model_sinks = []
    production_sources = {}
    for path in Path("creative_os").rglob("*.py"):
        tree, _ = _definitions(path)
        production_sources[path.as_posix()] = path.read_text(encoding="utf-8")
        qualified_names = {id(node): name for name, node in qualified_definitions(tree).items()}
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            if (isinstance(call.func, ast.Attribute) and call.func.attr == "complete"
                    and any(name in ast.unparse(call.func.value).lower() for name in ("client", "adapter"))):
                owner = parents.get(call)
                while owner is not None and not isinstance(owner, ast.FunctionDef):
                    owner = parents.get(owner)
                model_sinks.append((path.as_posix(), qualified_names[id(owner)]))
    declared = [(item["file"], item["symbol"].removeprefix(module_name(item["file"]) + "."))
                for item in manifest if item["kind"] in {"model_client_sink", "transparent_delegate"}]
    assert sorted(model_sinks) == sorted(declared)
    validate_transparent_delegate(production_sources)
    import writer_architecture_checks
    checker = getattr(writer_architecture_checks, "validate_combat_loops", None)
    assert checker is not None, "有限专家循环架构契约尚未实现"
    checker(production_sources)

    promotion_defs = set()
    promotion_calls = set()
    for path in Path("creative_os").rglob("*.py"):
        tree, functions = _definitions(path)
        for name in functions:
            if name.startswith(("promote_", "publish_")):
                promotion_defs.add(f"{path.with_suffix('').as_posix().replace('/', '.')}.{name}")
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            called = ast.unparse(call.func).rsplit(".", 1)[-1]
            if called.startswith(("promote_", "publish_")):
                promotion_calls.add(called)
    assert promotion_defs == {
        "creative_os.novel_continuation_runner.promote_passing_draft",
        "creative_os.llm_writer.promote_llm_writer_pilot_to_final",
    }
    assert promotion_calls <= {symbol.rsplit(".", 1)[-1] for symbol in promotion_defs}

    final_sinks = set()
    guarded_names = {"_continue_one_chapter_impl", "_promote_passing_draft_impl",
                     "_run_llm_writer_pilot_impl", "_promote_llm_writer_pilot_to_final_impl"}
    guard_violations = []
    for path in Path("creative_os").rglob("*.py"):
        tree, functions = _definitions(path)
        for name, node in functions.items():
            final_vars = set()
            for assign in ast.walk(node):
                if isinstance(assign, ast.Assign):
                    targets, value = assign.targets, assign.value
                elif isinstance(assign, ast.AnnAssign):
                    targets, value = [assign.target], assign.value
                else:
                    continue
                if value is not None and "production" in ast.unparse(value) and "final_chapters" in ast.unparse(value):
                    final_vars.update(ast.unparse(target) for target in targets)
            writes_final = any(
                isinstance(call, ast.Call)
                and any(word in ast.unparse(call.func) for word in ("write_text", "shutil.copy2", "replace", "open"))
                and (any(var in ast.unparse(call) for var in final_vars)
                     or ("production" in ast.unparse(call) and "final_chapters" in ast.unparse(call)))
                for call in ast.walk(node)
            )
            if writes_final:
                final_sinks.add(f"{path.with_suffix('').as_posix().replace('/', '.')}.{name}")
        if path.name not in {"novel_continuation_runner.py", "llm_writer.py"}:
            source = ast.unparse(tree)
            if any(name in source for name in guarded_names) or "_EXIT_GUARD" in source:
                guard_violations.append(path.as_posix())
    assert final_sinks == {
        "creative_os.importing.materializer.materialize_project",
        "creative_os.novel_continuation_runner._continue_one_chapter_impl",
        "creative_os.novel_continuation_runner._promote_passing_draft_impl",
        "creative_os.writer_draft_store.promote",
    }
    assert guard_violations == []

    allowed_internal_callers = {
        "_continue_one_chapter_impl": "continue_one_chapter",
        "_promote_passing_draft_impl": "promote_passing_draft",
        "_run_llm_writer_pilot_impl": "run_llm_writer_pilot",
        "_promote_llm_writer_pilot_to_final_impl": "promote_llm_writer_pilot_to_final",
    }
    for file_name in ("creative_os/novel_continuation_runner.py", "creative_os/llm_writer.py"):
        tree, _ = _definitions(Path(file_name))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            called = ast.unparse(call.func).rsplit(".", 1)[-1]
            if called not in allowed_internal_callers:
                continue
            owner = parents.get(call)
            while owner is not None and not isinstance(owner, ast.FunctionDef):
                owner = parents.get(owner)
            assert owner.name == allowed_internal_callers[called]


@pytest.mark.parametrize("path,change", [
    ("creative_os/combat_agent.py", "while True:\n pass"),
    ("creative_os/chapter_agent_tools.py", "client.complete(messages)"),
    ("creative_os/combat_agent.py", "RuntimeRunner().execute(request, client)"),
    ("creative_os/combat_agent.py", "from creative_os.writer_context_sources import CapturingModelAdapter as Proxy\nProxy(client, callback).complete(messages)"),
])
def test_expert_boundaries_reject_unbounded_loops_and_new_model_exits(path, change):
    import writer_architecture_checks
    checker = getattr(writer_architecture_checks, "validate_combat_loops", None)
    assert checker is not None, "有限专家循环架构契约尚未实现"
    sources = {file.as_posix(): file.read_text(encoding="utf-8") for file in Path("creative_os").rglob("*.py")}
    sources[path] += "\ndef bypass():\n" + "\n".join(" " + line for line in change.splitlines())
    with pytest.raises(AssertionError):
        checker(sources)


def test_public_exits_require_prepared_and_runner_has_no_active_loader_or_final_token():
    runner, runner_functions = _definitions(Path("creative_os/novel_continuation_runner.py"))
    _, writer_functions = _definitions(Path("creative_os/llm_writer.py"))
    functions = {**runner_functions, **writer_functions}
    for name in ("continue_one_chapter", "promote_passing_draft", "run_llm_writer_pilot", "promote_llm_writer_pilot_to_final"):
        assert functions[name].args.args[0].arg == "prepared"
    source = ast.unparse(runner)
    assert "load_active_narrative_decision" not in source
    assert "load_active_narrative_decision" not in Path(
        "creative_os/production_validation.py"
    ).read_text(encoding="utf-8")
    for name in ("continue_one_chapter", "promote_passing_draft"):
        body = ast.unparse(functions[name])
        assert "finalize_admission" not in body
        assert "WriterAdmissionToken" not in body
    prepared_fields = set(PreparedWriterRun.__dataclass_fields__)
    assert "grant" not in prepared_fields
    assert {"projection", "token", "context", "run_id"} <= prepared_fields


class _BlockedAdmission:
    def __init__(self, project_root):
        self.project_root = project_root

    def validate_token(self, *_args, **_kwargs):
        raise WriterAdmissionError("invalid_token")


class _NoCallClient:
    calls = 0

    def complete(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("model must not be called")


@pytest.mark.parametrize("exit_name", sorted(PUBLIC))
@pytest.mark.parametrize("invalid_kind", ["no_token", "grant_as_token", "old_token", "wrong_contract_hash", "wrong_context", "wrong_run", "tampered_task"])
def test_every_public_exit_rejects_invalid_admission_before_side_effects(tmp_path, exit_name, invalid_kind):
    service = _BlockedAdmission(tmp_path)
    projection = AdmittedContractProjection("contract-1", 1, "a" * 64, "{}")
    task = ContinuationTask(2, 1, "goal", [], [], [], "ending", [], 7000, 5250, projection)
    task_body = hashlib.sha256(json.dumps(asdict(task), ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest()
    context = type("Context", (), {"fingerprint": "d" * 64,
                                    "task": SimpleNamespace(id="chapter-002", goal="goal"),
                                    "knowledge": [SimpleNamespace(id="writer-task:chapter:002", body=task_body)]})()
    projection_hash = hashlib.sha256(json.dumps(asdict(projection), sort_keys=True,
                                                separators=(",", ":")).encode()).hexdigest()
    token = WriterAdmissionToken(
        "writer_admission_token", "grant-1", tmp_path.name, "chapter_002", "contract-1", 1,
        "a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64, "f" * 64,
        "rules-v1", (), "1" * 64, projection_hash, "2" * 64, "d" * 64, "run-1",
        "2026-08-22T00:00:00+00:00", "2026-08-23T00:00:00+00:00", "signature",
    )
    if invalid_kind == "no_token":
        token = None
    elif invalid_kind == "grant_as_token":
        token = object()
    elif invalid_kind == "wrong_contract_hash":
        token = replace(token, contract_content_hash="0" * 64)
    elif invalid_kind == "wrong_context":
        context.fingerprint = "e" * 64
    elif invalid_kind == "wrong_run":
        token = replace(token, run_id="another-run")
    elif invalid_kind == "old_token":
        token = replace(token, expires_at="2020-01-01T00:00:00+00:00")
    elif invalid_kind == "tampered_task":
        task = replace(task, forbidden_contradictions=["tampered"])
    prepared = PreparedWriterRun(tmp_path, "run-1", task, context, projection, token, service)
    client = _NoCallClient()
    before = tuple(tmp_path.rglob("*"))
    with pytest.raises((TypeError, ValueError, WriterAdmissionError)):
        if exit_name.endswith("continue_one_chapter"):
            continue_one_chapter(prepared, client=client)
        elif exit_name.endswith("promote_passing_draft"):
            promote_passing_draft(prepared)
        elif exit_name.endswith("run_llm_writer_pilot"):
            run_llm_writer_pilot(prepared, client)
        else:
            promote_llm_writer_pilot_to_final(prepared)
    assert client.calls == 0
    assert tuple(tmp_path.rglob("*")) == before
