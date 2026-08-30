from __future__ import annotations

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import creative_os.runtime.publication_length_disposition_store as store_module

from creative_os.domains.publication_migration_model import (
    LengthIntervalKind,
    PublicationLengthPolicy,
    length_policy_hash,
)
from creative_os.runtime.publication_length_disposition_store import (
    PublicationLengthDispositionConflict,
    PublicationLengthDispositionIntegrityError,
    PublicationLengthDispositionStore,
)


H = "a" * 64


def _long_text():
    return "文" * 5001 + "。"


def _short_text():
    return "文" * 2000 + "。"


def test_store_generates_exact_long_decision_and_reopens(tmp_path):
    policy = PublicationLengthPolicy()
    store = PublicationLengthDispositionStore(tmp_path)
    decision = store.append_decision(
        "migration-1", 5, _long_text(), policy,
        "editor", "高潮节点不可拆", decided_at="2026-08-28T10:00:00+08:00",
    )
    assert decision.policy_hash == length_policy_hash(policy)
    assert decision.record_sequence == 1
    assert PublicationLengthDispositionStore(tmp_path).require_exact(decision) == decision


def test_store_is_idempotent_but_rejects_same_binding_conflict(tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    args = ("migration-1", 5, _long_text(), PublicationLengthPolicy(),
            "editor", "高潮节点不可拆")
    first = store.append_decision(*args, decided_at="2026-08-28T10:00:00+08:00")
    assert store.append_decision(*args, decided_at="2026-08-28T10:00:00+08:00") == first
    with pytest.raises(PublicationLengthDispositionConflict, match="decision_conflict"):
        store.append_decision(*args[:-1], "另一理由", decided_at="2026-08-28T10:00:01+08:00")


def test_store_rejects_forged_reference_and_tampered_chain(tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    decision = store.append_decision(
        "migration-1", 5, _short_text(), PublicationLengthPolicy(),
        "editor", "独立强钩子", decided_at="2026-08-28T10:00:00+08:00",
    )
    with pytest.raises(PublicationLengthDispositionIntegrityError, match="decision_exact_not_found"):
        store.require_exact(replace(decision, body_hash="b" * 64))
    path = tmp_path / ".creative_os/publication_migration/length_dispositions/records.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["payload"]["reason"] = "篡改"
    path.write_text(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(PublicationLengthDispositionIntegrityError, match="record_chain_tampered"):
        PublicationLengthDispositionStore(tmp_path).recover()


def test_store_recovers_after_records_publish_before_head(monkeypatch, tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    original = store._write_head
    monkeypatch.setattr(store, "_write_head", lambda _rows: (_ for _ in ()).throw(RuntimeError("crash")))
    with pytest.raises(RuntimeError, match="crash"):
        store.append_decision(
            "migration-1", 5, _long_text(), PublicationLengthPolicy(),
            "editor", "完整高潮", decided_at="2026-08-28T10:00:00+08:00",
        )
    monkeypatch.setattr(store, "_write_head", original)
    recovered = PublicationLengthDispositionStore(tmp_path).recover()
    assert len(recovered) == 1
    assert recovered[0].reason == "完整高潮"


def test_store_recovers_prepared_journal_before_records_publish(monkeypatch, tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    monkeypatch.setattr(store, "_publish_envelope", lambda _row: (_ for _ in ()).throw(RuntimeError("crash")))
    with pytest.raises(RuntimeError, match="crash"):
        store.append_decision("migration-1", 5, _long_text(), PublicationLengthPolicy(),
                              "editor", "完整高潮", decided_at="2026-08-28T10:00:00+08:00")
    recovered = PublicationLengthDispositionStore(tmp_path).recover()
    assert len(recovered) == 1


def test_store_recovers_head_written_before_journal_clear(monkeypatch, tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    original = store._filesystem.atomic_write_bytes
    def crash_on_clear(path, payload, *, expected):
        if path == store.journal_path and payload == b"":
            raise RuntimeError("crash")
        return original(path, payload, expected=expected)
    monkeypatch.setattr(store._filesystem, "atomic_write_bytes", crash_on_clear)
    with pytest.raises(RuntimeError, match="crash"):
        store.append_decision("migration-1", 5, _long_text(), PublicationLengthPolicy(),
                              "editor", "完整高潮", decided_at="2026-08-28T10:00:00+08:00")
    assert len(PublicationLengthDispositionStore(tmp_path).recover()) == 1


@pytest.mark.parametrize("text", ["文" * 2500 + "。", "文" * 5000 + "。", "文" * 5501 + "。"],
                         ids=["short-boundary", "warning-upper", "hard-limit"])
def test_store_cannot_mint_decision_outside_eligible_intervals(tmp_path, text):
    with pytest.raises(ValueError, match="length_interval_not_approvable"):
        PublicationLengthDispositionStore(tmp_path).append_decision(
            "migration-1", 5, text, PublicationLengthPolicy(), "editor", "无效例外",
            decided_at="2026-08-28T10:00:00+08:00",
        )


def test_store_payload_hash_binds_actual_character_count_and_ruleset(tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    decision = store.append_decision(
        "migration-1", 5, _long_text(), PublicationLengthPolicy(), "editor", "完整高潮",
        decided_at="2026-08-28T10:00:00+08:00",
    )
    path = tmp_path / ".creative_os/publication_migration/length_dispositions/records.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["payload"]["chinese_character_count"] == 5001
    assert row["payload"]["ruleset_version"] == "publication-length-policy-v1"
    assert row["payload"]["policy_thresholds"]["hard_max"] == 5500
    assert store.require_exact(decision, _long_text(), PublicationLengthPolicy()) == decision


def test_domain_hash_rejects_payload_tampering_even_when_envelope_is_rewrapped(tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    store.append_decision("migration-1", 5, _long_text(), PublicationLengthPolicy(), "editor", "完整高潮",
                          decided_at="2026-08-28T10:00:00+08:00")
    path = tmp_path / ".creative_os/publication_migration/length_dispositions/records.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["payload"]["reason"] = "重包篡改"
    canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    row["payload_hash"] = hashlib.sha256(canonical(row["payload"])).hexdigest()
    row["envelope_hash"] = hashlib.sha256(canonical({k: v for k, v in row.items() if k != "envelope_hash"})).hexdigest()
    path.write_bytes(canonical(row) + b"\n")
    head = tmp_path / ".creative_os/publication_migration/length_dispositions/head.json"
    head.write_bytes(canonical({"count": 1, "head_hash": row["envelope_hash"]}))
    with pytest.raises(PublicationLengthDispositionIntegrityError, match="decision_domain_hash_invalid"):
        PublicationLengthDispositionStore(tmp_path).recover()


def test_store_rejects_tampered_head_and_truncated_journal(tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    store.append_decision("migration-1", 5, _long_text(), PublicationLengthPolicy(), "editor", "完整高潮",
                          decided_at="2026-08-28T10:00:00+08:00")
    head = tmp_path / ".creative_os/publication_migration/length_dispositions/head.json"
    head.write_text("{}", encoding="utf-8")
    with pytest.raises(PublicationLengthDispositionIntegrityError, match="head_tampered"):
        PublicationLengthDispositionStore(tmp_path).recover()

    other = tmp_path / "other"
    other.mkdir()
    second = PublicationLengthDispositionStore(other)
    second.append_decision("migration-1", 5, _long_text(), PublicationLengthPolicy(), "editor", "完整高潮",
                           decided_at="2026-08-28T10:00:00+08:00")
    journal = other / ".creative_os/publication_migration/length_dispositions/journal.json"
    journal.write_bytes(b'{"state":')
    with pytest.raises((PublicationLengthDispositionIntegrityError, json.JSONDecodeError)):
        PublicationLengthDispositionStore(other).recover()


def test_two_store_instances_serialize_same_and_conflicting_decisions(tmp_path):
    def append(reason):
        return PublicationLengthDispositionStore(tmp_path).append_decision(
            "migration-1", 5, _long_text(), PublicationLengthPolicy(), "editor", reason,
            decided_at="2026-08-28T10:00:00+08:00",
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        same = tuple(pool.map(append, ("完整高潮", "完整高潮")))
    assert same[0] == same[1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(append, reason) for reason in ("完整高潮", "冲突理由")]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result())
        except PublicationLengthDispositionConflict:
            outcomes.append("conflict")
    assert "conflict" in outcomes


def _process_command(root: Path, reason: str) -> list[str]:
    script = (
        "from pathlib import Path; "
        "from creative_os.runtime.publication_length_disposition_store import PublicationLengthDispositionStore; "
        "from creative_os.domains.publication_migration_model import PublicationLengthPolicy; "
        f"PublicationLengthDispositionStore(Path({str(root)!r})).append_decision("
        f"'migration-1',5,'文'*5001+'。',PublicationLengthPolicy(),'editor',{reason!r},"
        "decided_at='2026-08-28T10:00:00+08:00')"
    )
    return [sys.executable, "-c", script]


def test_cross_process_same_decision_is_idempotent_and_conflict_has_one_winner(tmp_path):
    same = [subprocess.Popen(_process_command(tmp_path, "完整高潮")) for _ in range(2)]
    assert [item.wait(timeout=30) for item in same] == [0, 0]
    other = tmp_path / "conflict"
    other.mkdir()
    conflict = [subprocess.Popen(_process_command(other, reason)) for reason in ("理由甲", "理由乙")]
    codes = sorted(item.wait(timeout=30) for item in conflict)
    assert codes[0] == 0 and codes[1] != 0


@pytest.mark.parametrize("filename", ["records.jsonl", "head.json"])
def test_live_authority_file_replacement_fails_closed(monkeypatch, tmp_path, filename):
    store = PublicationLengthDispositionStore(tmp_path)
    decision = store.append_decision("migration-1", 5, _long_text(), PublicationLengthPolicy(),
                                     "editor", "完整高潮", decided_at="2026-08-28T10:00:00+08:00")
    attacked = False
    def hook(event, path):
        nonlocal attacked
        if not attacked and event == "before_file_open" and path.name == filename:
            attacked = True
            path.replace(path.with_suffix(path.suffix + ".backup"))
            path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(store_module, "_IO_HOOK", hook)
    with pytest.raises((PublicationLengthDispositionIntegrityError, json.JSONDecodeError)):
        store.require_exact(decision, _long_text(), PublicationLengthPolicy())


def test_live_project_root_and_lock_replacement_fail_closed(monkeypatch, tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    attacked = False
    def hook(event, path):
        nonlocal attacked
        if not attacked and event == "before_lock_open":
            attacked = True
            backup = tmp_path.with_name(tmp_path.name + "-backup")
            tmp_path.replace(backup)
            tmp_path.mkdir()
    monkeypatch.setattr(store_module, "_IO_HOOK", hook)
    with pytest.raises((PublicationLengthDispositionIntegrityError, OSError)):
        store.recover()


def test_extra_layout_and_live_journal_replacement_fail_closed(monkeypatch, tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    store.append_decision("migration-1", 5, _long_text(), PublicationLengthPolicy(), "editor", "完整高潮",
                          decided_at="2026-08-28T10:00:00+08:00")
    (store.root / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(PublicationLengthDispositionIntegrityError, match="authority_layout_tampered"):
        store.recover()

    other = tmp_path / "journal-live"
    other.mkdir()
    live = PublicationLengthDispositionStore(other)
    live.append_decision("migration-1", 5, _long_text(), PublicationLengthPolicy(), "editor", "完整高潮",
                         decided_at="2026-08-28T10:00:00+08:00")
    live.journal_path.write_text("{}", encoding="utf-8")
    attacked = False
    def hook(event, path):
        nonlocal attacked
        if not attacked and event == "before_file_open" and path == live.journal_path:
            attacked = True
            path.replace(path.with_suffix(".json.backup"))
            path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(store_module, "_IO_HOOK", hook)
    with pytest.raises(PublicationLengthDispositionIntegrityError):
        live.recover()


def test_lock_path_reparse_or_directory_substitution_is_rejected(monkeypatch, tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    def hook(event, path):
        if event == "before_lock_open" and not path.exists():
            path.mkdir()
    monkeypatch.setattr(store_module, "_IO_HOOK", hook)
    with pytest.raises((PublicationLengthDispositionIntegrityError, OSError)):
        store.recover()


def test_live_store_root_replacement_is_rejected_without_skip(monkeypatch, tmp_path):
    store = PublicationLengthDispositionStore(tmp_path)
    attacked = False
    def hook(event, _path):
        nonlocal attacked
        if not attacked and event == "before_lock_open":
            attacked = True
            backup = store.root.with_name(store.root.name + "-backup")
            store.root.replace(backup)
            store.root.mkdir()
    monkeypatch.setattr(store_module, "_IO_HOOK", hook)
    with pytest.raises((PublicationLengthDispositionIntegrityError, OSError)):
        store.recover()


def test_store_root_symlink_or_reparse_probe_is_rejected(tmp_path):
    authority_parent = tmp_path / ".creative_os/publication_migration"
    authority_parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = authority_parent / "length_dispositions"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError as cause:
        pytest.skip(f"platform cannot create symlink probe: {cause}")
    with pytest.raises(PublicationLengthDispositionIntegrityError):
        PublicationLengthDispositionStore(tmp_path)
