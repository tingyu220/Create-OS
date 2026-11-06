import pytest

from creative_os.web_command_dto import WebCommandValidationError, decode_web_command


def command(command_id, payload, *, target=None):
    return {
        "command_id": command_id,
        "request_id": "req-1",
        "actor": "作者",
        "target": target or {"project_id": "book", "scope": "story", "session_id": "story-session"},
        "payload": payload,
        "expected_version": None,
        "idempotency_key": "idem-1",
    }


def test_adopt_combat_candidate_requires_result_id_and_revision_identity():
    request = decode_web_command(command("adopt_combat_candidate", {"result_id": "combat-result-1", "expected_revision": 3}))
    assert request.command_id == "adopt_combat_candidate"
    assert request.payload == {"result_id": "combat-result-1", "expected_revision": 3}


def test_adopt_combat_candidate_rejects_chapter_target():
    with pytest.raises(WebCommandValidationError):
        decode_web_command(command("adopt_combat_candidate", {"result_id": "combat-result-1", "expected_revision": 3}, target={"project_id": "book", "chapter_number": 1}))

