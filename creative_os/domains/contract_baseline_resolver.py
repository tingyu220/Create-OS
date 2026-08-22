from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from creative_os.domains.contract_baseline import BASELINE_ROLES, BaselineEntry
from creative_os.domains.contract_issue import ContractIssue
from creative_os.domains.narrative_decision import NarrativeChangeRequest, NarrativeDecision, NarrativeProjectProfile
from creative_os.domains.narrative_evidence import ResolvedEvidenceSource
from creative_os.memory.store import JsonMemoryStore
import hashlib


@dataclass(frozen=True, slots=True)
class AuthorityRead:
    role: str
    source_id: str
    source_version: str
    content_hash: str
    schema_version: str
    value: Any
    evidence_sources: tuple[ResolvedEvidenceSource, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthorityFactSnapshot:
    kind: str
    subject: str
    canonical_payload: tuple[tuple[str, Any], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("fact snapshot kind is required")
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise ValueError("fact snapshot subject is required")
        if not isinstance(self.canonical_payload, tuple):
            raise TypeError("fact snapshot payload must be a tuple")
        keys = []
        for item in self.canonical_payload:
            if not isinstance(item, tuple) or len(item) != 2:
                raise TypeError("fact snapshot payload entries must be pairs")
            key, value = item
            if not isinstance(key, str) or not key.strip():
                raise ValueError("fact snapshot payload key is required")
            _require_deeply_immutable(value)
            keys.append(key)
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("fact snapshot payload keys must be unique and canonical")


@dataclass(frozen=True, slots=True)
class AuthoritativeBaselineSnapshot:
    profile: NarrativeProjectProfile
    fact_snapshots: tuple[AuthorityFactSnapshot, ...]
    previous_chapter: NarrativeDecision | None
    change_requests: tuple[NarrativeChangeRequest, ...]
    reads: tuple[AuthorityRead, ...]
    evidence_sources: tuple[ResolvedEvidenceSource, ...]

    def evidence_resolver(self, source_id: str) -> ResolvedEvidenceSource | None:
        matches = tuple(source for source in self.evidence_sources if source.source_id == source_id)
        return matches[0] if len(matches) == 1 else None


class AuthorityRoleAdapter(Protocol):
    role: str

    def read_exact(self, project_root: Path, entry: BaselineEntry) -> AuthorityRead: ...


class ResolverError(ValueError):
    def __init__(self, issue: ContractIssue):
        super().__init__(issue.code)
        self.issue = issue


class BaselineSourceResolver:
    """Read-only exact resolver; adapters are the only authority access path."""

    def __init__(self, adapters: dict[str, AuthorityRoleAdapter]):
        if set(adapters) - BASELINE_ROLES or len(set(adapters)) != len(adapters):
            raise ValueError("invalid adapter registry")
        for role, adapter in adapters.items():
            if getattr(adapter, "role", None) != role:
                raise ValueError("adapter role mismatch")
        self._adapters = dict(adapters)

    def resolve(self, project_root: str | Path, entry: BaselineEntry) -> AuthorityRead:
        adapter = self._adapters.get(entry.role)
        if adapter is None:
            raise self._error("source_not_versioned", entry.role)
        try:
            result = adapter.read_exact(Path(project_root), entry)
        except ResolverError:
            raise
        except Exception as error:
            raise self._error("authority_read_error", entry.role) from error
        if not isinstance(result, AuthorityRead):
            raise self._error("record_corrupt", entry.role)
        if (result.role, result.source_id, result.source_version, result.content_hash) != (
            entry.role, entry.source_id, entry.source_version, entry.content_hash
        ):
            raise self._error("source_drift", entry.role)
        if not result.schema_version.strip():
            raise self._error("unsupported_schema", entry.role)
        return result

    def resolve_manifest(self, project_root: str | Path, entries: tuple[BaselineEntry, ...]) -> AuthoritativeBaselineSnapshot:
        roles = [entry.role for entry in entries]
        if len(set(roles)) != len(roles):
            duplicate = next(role for role in roles if roles.count(role) > 1)
            raise self._error("duplicate_role", duplicate)
        seen: set[str] = set()
        reads = []
        for entry in entries:
            if entry.role in seen:
                raise self._error("duplicate_role", entry.role)
            seen.add(entry.role)
            reads.append(self.resolve(project_root, entry))
        by_role = {read.role: read for read in reads}
        profile = getattr(by_role.get("profile"), "value", None)
        if not isinstance(profile, NarrativeProjectProfile):
            raise self._error("record_corrupt", "profile")
        previous = getattr(by_role.get("previous_chapter"), "value", None)
        if previous is not None and not isinstance(previous, NarrativeDecision):
            raise self._error("record_corrupt", "previous_chapter")
        change = getattr(by_role.get("outline_change"), "value", ())
        if not isinstance(change, tuple) or not all(isinstance(item, NarrativeChangeRequest) for item in change):
            raise self._error("record_corrupt", "outline_change")
        facts = getattr(by_role.get("fact_snapshot"), "value", ())
        if not isinstance(facts, tuple) or not all(isinstance(item, AuthorityFactSnapshot) for item in facts):
            raise self._error("record_corrupt", "fact_snapshot")
        evidence_sources = tuple(source for read in reads for source in read.evidence_sources)
        if len({source.source_id for source in evidence_sources}) != len(evidence_sources):
            raise self._error("record_corrupt", "evidence_sources")
        return AuthoritativeBaselineSnapshot(
            profile, facts, previous, change, tuple(reads), evidence_sources
        )

    @staticmethod
    def _error(code: str, field_path: str) -> ResolverError:
        return ResolverError(ContractIssue(code, "error", True, field_path, (), "修复并重新生成权威版本绑定"))


class VersionedMemoryAdapter:
    """Exact read adapter for immutable existing Memory revisions."""

    def __init__(self, role: str, item_id: str, decoder):
        self.role = role
        self.item_id = item_id
        self._decoder = decoder

    def read_exact(self, project_root: Path, entry: BaselineEntry) -> AuthorityRead:
        item_id = self.item_id
        if self.role == "outline_change":
            if not entry.source_id.startswith("narrative-change:"):
                raise ResolverError(BaselineSourceResolver._error("source_id_mismatch", self.role).issue)
            item_id = "narrative-change-" + entry.source_id.removeprefix("narrative-change:")
        store = JsonMemoryStore(project_root / ".creative_os" / "memory")
        try:
            revisions = store.revisions(item_id)
        except Exception as error:
            raise ResolverError(BaselineSourceResolver._error("io_error", self.role).issue) from error
        for item in revisions:
            versions = {str(item.version), f"v{item.version:04d}"}
            if entry.source_version not in versions:
                continue
            digest = hashlib.sha256(item.content.encode("utf-8")).hexdigest()
            if digest != entry.content_hash:
                raise ResolverError(BaselineSourceResolver._error("hash_mismatch", self.role).issue)
            try:
                value = self._decoder(item.content)
            except Exception as error:
                raise ResolverError(BaselineSourceResolver._error("decode_error", self.role).issue) from error
            return AuthorityRead(self.role, entry.source_id, entry.source_version, digest, "memory-v1", value)
        raise ResolverError(BaselineSourceResolver._error("source_not_versioned", self.role).issue)


class UnsupportedAuthorityAdapter:
    def __init__(self, role: str):
        self.role = role

    def read_exact(self, project_root: Path, entry: BaselineEntry) -> AuthorityRead:
        raise ResolverError(BaselineSourceResolver._error("source_not_versioned", self.role).issue)


def default_authority_adapters() -> dict[str, AuthorityRoleAdapter]:
    return {
        "profile": VersionedMemoryAdapter("profile", "narrative-project-profile", NarrativeProjectProfile.from_json),
        "outline_change": VersionedMemoryAdapter(
            "outline_change", "narrative-change", lambda content: (NarrativeChangeRequest.from_json(content),)
        ),
        "fact_snapshot": UnsupportedAuthorityAdapter("fact_snapshot"),
        "previous_chapter": UnsupportedAuthorityAdapter("previous_chapter"),
    }


def _require_deeply_immutable(value: object) -> None:
    if value is None or type(value) in {str, int, float, bool}:
        return
    if isinstance(value, tuple):
        for item in value:
            _require_deeply_immutable(item)
        return
    raise TypeError("fact snapshot payload values must be deeply immutable")
