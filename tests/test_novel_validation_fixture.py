import hashlib
import json
from pathlib import Path
import shutil

import pytest

from creative_os.domains.narrative_decision import NarrativeValidationError
from creative_os.domains.novel_validation_fixture import load_independent_validation_case


PROJECT = Path(__file__).resolve().parents[1] / "projects" / "novel_domain_validation"
FIXTURE = PROJECT / "validation" / "independent_short_story.json"


def _write_fixture_project(tmp_path: Path, payload: dict) -> Path:
    project = tmp_path / "novel_domain_validation"
    validation = project / "validation"
    validation.mkdir(parents=True)
    shutil.copy2(PROJECT / "brief.json", project / "brief.json")
    path = validation / "independent_short_story.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_independent_fixture_has_complete_novel_scene_contract():
    case = load_independent_validation_case(FIXTURE)

    case.chapter_contract.scene_plan.validate(required=True, novel_required=True)
    assert case.fake_draft.content_hash == hashlib.sha256(case.fake_draft.content.encode("utf-8")).hexdigest()
    for essential in case.chapter_contract.scene_plan.scenes[0].essential_information:
        assert essential in case.fake_draft.content
    payload = FIXTURE.read_text(encoding="utf-8")
    for forbidden in ("文明升阶", "林子轩", "陈景行"):
        assert forbidden not in payload


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda payload: payload.update(unexpected=True), "unknown root field"),
        (lambda payload: payload["planning"].pop("chapter_contract"), "chapter identity"),
        (lambda payload: payload["planning"]["chapter_contract"]["scene_plan"].update(scenes=[]), "empty scene"),
        (
            lambda payload: payload["planning"]["chapter_contract"]["scene_plan"]["scenes"][0]["closure"].update(choice_made=False),
            "scene closure",
        ),
        (lambda payload: payload["fake_draft"].update(content_hash="0" * 64), "content hash"),
        (lambda payload: payload["boundary"].update(estimated_chinese_chars=1), "boundary minimum"),
    ],
)
def test_loader_rejects_invalid_fixture_contract(tmp_path, mutate, match):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    mutate(payload)
    path = _write_fixture_project(tmp_path, payload)

    with pytest.raises(NarrativeValidationError, match=match):
        load_independent_validation_case(path)


def test_loader_rejects_baseline_evidence_hash_that_does_not_match_source(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["baseline_evidence"][0]["source_hash"] = "0" * 64

    with pytest.raises(NarrativeValidationError, match="baseline evidence source hash mismatch"):
        load_independent_validation_case(_write_fixture_project(tmp_path, payload))


def test_loader_rejects_tampered_baseline_evidence_source(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture = _write_fixture_project(tmp_path, payload)
    brief = fixture.parents[1] / "brief.json"
    brief.write_bytes(brief.read_bytes() + b"\n")

    with pytest.raises(NarrativeValidationError, match="baseline evidence source hash mismatch"):
        load_independent_validation_case(fixture)


def test_loader_rejects_baseline_evidence_source_outside_project(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["baseline_evidence"][0]["source_id"] = "../brief.json"

    with pytest.raises(NarrativeValidationError, match="baseline evidence source path outside project"):
        load_independent_validation_case(_write_fixture_project(tmp_path, payload))
