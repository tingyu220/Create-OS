import hashlib
import json
from pathlib import Path

import pytest

from creative_os.domains.narrative_decision import NarrativeValidationError
from creative_os.domains.novel_validation_fixture import load_independent_validation_case


PROJECT = Path(__file__).resolve().parents[1] / "projects" / "novel_domain_validation"
FIXTURE = PROJECT / "validation" / "independent_short_story.json"


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
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(NarrativeValidationError, match=match):
        load_independent_validation_case(path)
