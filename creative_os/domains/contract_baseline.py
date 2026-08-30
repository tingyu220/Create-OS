from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


BASELINE_ROLES = frozenset(
    {
        "profile",
        "fact_snapshot",
        "previous_chapter",
        "outline_change",
    }
)


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _require_sha256(value: object, name: str) -> str:
    text = _require_text(value, name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{name} must be a lowercase sha256")
    return text


@dataclass(frozen=True, slots=True)
class BaselineEntry:
    """One immutable source version used when a contract was approved."""

    role: str
    source_id: str
    source_version: str
    content_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, str):
            raise TypeError("baseline role must be text")
        if self.role not in BASELINE_ROLES:
            raise ValueError(f"unsupported baseline role: {self.role}")
        _require_text(self.source_id, "baseline source_id")
        _require_text(self.source_version, "baseline source_version")
        _require_sha256(self.content_hash, "baseline content_hash")


@dataclass(frozen=True, slots=True)
class BaselineManifest:
    """Canonical set of approval inputs bound by a deterministic fingerprint."""

    entries: tuple[BaselineEntry, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        canonical = _canonical_entries(self.entries)
        if canonical != self.entries:
            raise ValueError("baseline entries must be in canonical order")
        _require_sha256(self.fingerprint, "baseline fingerprint")
        if self.fingerprint != _fingerprint(canonical):
            raise ValueError("baseline fingerprint does not match canonical entries")

    @classmethod
    def build(cls, entries: tuple[BaselineEntry, ...]) -> BaselineManifest:
        canonical = _canonical_entries(entries)
        return cls(entries=canonical, fingerprint=_fingerprint(canonical))


def _canonical_entries(entries: object) -> tuple[BaselineEntry, ...]:
    if not isinstance(entries, tuple):
        raise TypeError("baseline entries must be a tuple")
    if not entries:
        raise ValueError("baseline entries are required")
    if not all(isinstance(entry, BaselineEntry) for entry in entries):
        raise TypeError("baseline entries must contain BaselineEntry values")

    seen: set[tuple[str, str]] = set()
    profile_count = 0
    for entry in entries:
        key = (entry.role, entry.source_id)
        if key in seen:
            raise ValueError(f"duplicate baseline source: {entry.role}/{entry.source_id}")
        seen.add(key)
        profile_count += entry.role == "profile"
    if profile_count != 1:
        raise ValueError("baseline manifest requires exactly one profile source")

    return tuple(
        sorted(
            entries,
            key=lambda entry: (entry.role, entry.source_id, entry.source_version, entry.content_hash),
        )
    )


def _fingerprint(entries: tuple[BaselineEntry, ...]) -> str:
    canonical_json = json.dumps(
        [asdict(entry) for entry in entries],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
