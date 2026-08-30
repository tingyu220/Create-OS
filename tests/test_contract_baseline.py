from dataclasses import replace

import pytest

from creative_os.domains.contract_baseline import BaselineEntry, BaselineManifest


def _entry(
    role: str = "profile",
    source_id: str = "profile-1",
    source_version: str = "3",
    content_hash: str = "a" * 64,
) -> BaselineEntry:
    return BaselineEntry(
        role=role,
        source_id=source_id,
        source_version=source_version,
        content_hash=content_hash,
    )


def test_build_sorts_canonical_entries_and_has_a_stable_literal_fingerprint():
    profile = _entry()
    fact = _entry("fact_snapshot", "fact-2", "7", "b" * 64)

    manifest = BaselineManifest.build((profile, fact))
    reordered = BaselineManifest.build((fact, profile))

    assert manifest.entries == (fact, profile)
    assert reordered == manifest
    assert manifest.fingerprint == "4fbe5de2e86c2d03ffd5680798f491bd298043c84b3f3e8fa8093ef636089fd4"


@pytest.mark.parametrize(
    "changed",
    [
        _entry("fact_snapshot", "fact-2", "8", "b" * 64),
        _entry("fact_snapshot", "fact-2", "7", "c" * 64),
        _entry("fact_snapshot", "fact-3", "7", "b" * 64),
    ],
    ids=["source-version", "source-hash", "source-id"],
)
def test_any_baseline_source_drift_changes_the_fingerprint(changed):
    profile = _entry()
    original = BaselineManifest.build((profile, _entry("fact_snapshot", "fact-2", "7", "b" * 64)))

    drifted = BaselineManifest.build((profile, changed))

    assert drifted.fingerprint != original.fingerprint


def test_duplicate_logical_source_is_rejected_even_if_its_version_or_hash_differs():
    duplicate = replace(_entry(), source_version="4", content_hash="d" * 64)

    with pytest.raises(ValueError, match="duplicate baseline source"):
        BaselineManifest.build((_entry(), duplicate))


@pytest.mark.parametrize(
    "entries",
    [
        (),
        (_entry("fact_snapshot", "fact-1", "1", "b" * 64),),
        (_entry(), object()),
        [_entry()],
    ],
    ids=["empty", "missing-profile", "invalid-entry", "mutable-container"],
)
def test_manifest_build_fails_closed_on_missing_or_invalid_entries(entries):
    with pytest.raises((TypeError, ValueError)):
        BaselineManifest.build(entries)


@pytest.mark.parametrize(
    "changes",
    [
        {"role": "unknown"},
        {"source_id": ""},
        {"source_version": ""},
        {"content_hash": "not-a-sha256"},
        {"source_version": 7},
    ],
    ids=["role", "source-id", "source-version", "content-hash", "field-type"],
)
def test_baseline_entry_rejects_unknown_empty_or_wrongly_typed_fields(changes):
    values = {
        "role": "profile",
        "source_id": "profile-1",
        "source_version": "3",
        "content_hash": "a" * 64,
    }
    values.update(changes)

    with pytest.raises((TypeError, ValueError)):
        BaselineEntry(**values)


def test_manifest_constructor_rejects_a_tampered_fingerprint():
    manifest = BaselineManifest.build((_entry(),))

    with pytest.raises(ValueError, match="fingerprint"):
        BaselineManifest(entries=manifest.entries, fingerprint="0" * 64)
