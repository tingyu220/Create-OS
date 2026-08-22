import hashlib
import json

import pytest

from creative_os.domains.narrative_migration import NarrativeMigrationService
from creative_os.memory.model import MemoryStatus
from creative_os.memory.store import JsonMemoryStore
from tests.test_narrative_codec import _legacy_v1_payload


def _source():
    raw = json.dumps(_legacy_v1_payload(), ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def test_migration_is_idempotent_candidate_only_and_never_moves_pointer(tmp_path):
    raw, digest = _source()
    service = NarrativeMigrationService(tmp_path)
    first = service.migrate("legacy-7", 3, digest, raw, actor="editor")
    second = NarrativeMigrationService(tmp_path).migrate(
        "legacy-7", 3, digest, raw, actor="editor",
    )
    assert first == second
    item = JsonMemoryStore(tmp_path / ".creative_os" / "memory").get_strict(first.candidate_item_id)
    assert item.status is MemoryStatus.CANDIDATE
    assert item.approved_by is None
    assert not (tmp_path / ".creative_os" / "narrative_contracts" / "current").exists()


@pytest.mark.parametrize("fault", ["after_prepare", "after_candidate"])
def test_migration_recovers_partial_failure_using_exact_candidate(tmp_path, fault):
    raw, digest = _source()
    service = NarrativeMigrationService(tmp_path)
    with pytest.raises(RuntimeError, match="fault"):
        service.migrate("legacy-7", 3, digest, raw, actor="editor", fault=fault)
    recovered = NarrativeMigrationService(tmp_path).recover()
    assert len(recovered) == 1
    assert recovered[0].candidate_item_id


def test_completed_chapter_is_replay_only_and_writes_no_candidate(tmp_path):
    raw, digest = _source()
    result = NarrativeMigrationService(tmp_path).migrate(
        "legacy-7", 3, digest, raw, actor="editor", completed=True,
    )
    assert result.report.replay_only is True
    assert result.candidate_item_id is None
    assert JsonMemoryStore(tmp_path / ".creative_os" / "memory").list() == []


def test_migration_keeps_legacy_active_record_and_rejects_journal_tamper(tmp_path):
    raw, digest = _source()
    store = JsonMemoryStore(tmp_path / ".creative_os" / "memory")
    from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
    legacy = MemoryItem.new_candidate(
        id="legacy-7", kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
        scope_id=tmp_path.name, title="旧合同", content=raw,
        evidence=(MemoryEvidence("legacy", "legacy-7", "旧记录"),),
    ).activate(actor="editor")
    store.add_immutable(legacy)
    result = NarrativeMigrationService(tmp_path).migrate(
        "legacy-7", 3, digest, raw, actor="editor",
    )
    assert store.get_strict("legacy-7") == legacy
    journal = next((tmp_path / ".creative_os" / "narrative_migrations").glob("*.json"))
    journal.write_bytes(journal.read_bytes().replace(b'"committed"', b'"prepared"'))
    with pytest.raises(ValueError, match="journal"):
        NarrativeMigrationService(tmp_path).recover()
    assert store.get_strict(result.candidate_item_id).status is MemoryStatus.CANDIDATE


def test_different_legacy_triple_cannot_reuse_candidate_provenance(tmp_path):
    raw, digest = _source()
    NarrativeMigrationService(tmp_path).migrate(
        "legacy-7", 3, digest, raw, actor="editor",
    )
    alternate = raw + "\n"
    alternate_hash = hashlib.sha256(alternate.encode()).hexdigest()
    with pytest.raises(ValueError, match="candidate conflict"):
        NarrativeMigrationService(tmp_path).migrate(
            "legacy-7-copy", 4, alternate_hash, alternate, actor="editor",
        )
