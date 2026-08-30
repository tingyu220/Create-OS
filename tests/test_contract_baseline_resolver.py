from dataclasses import dataclass

import pytest

from creative_os.domains.contract_baseline import BaselineEntry
from creative_os.domains.contract_baseline_resolver import (
    AuthorityRead,
    AuthorityFactSnapshot,
    BaselineSourceResolver,
    ResolverError,
    UnsupportedAuthorityAdapter,
    ImmutableMemoryAuthorityAdapter,
    default_authority_adapters,
)
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.store import JsonMemoryStore
import hashlib


@dataclass(frozen=True)
class Value:
    name: str


def entry(role="profile", source_id="profile-main", version="r1", digest="a" * 64):
    return BaselineEntry(role, source_id, version, digest)


def test_exact_resolve_uses_explicit_adapter_and_returns_immutable_read(tmp_path):
    class Adapter:
        role = "profile"

        def read_exact(self, root, requested):
            assert root == tmp_path
            return AuthorityRead("profile", "profile-main", "r1", "a" * 64, "profile-v1", Value("ok"))

    result = BaselineSourceResolver({"profile": Adapter()}).resolve(tmp_path, entry())
    assert result.value == Value("ok")
    with pytest.raises(AttributeError):
        result.value = Value("changed")


@pytest.mark.parametrize("bad", [entry(source_id="wrong"), entry(version="r2"), entry(digest="b" * 64)])
def test_mismatch_is_blocking_resolver_error(tmp_path, bad):
    class Adapter:
        role = "profile"
        def read_exact(self, root, requested):
            return AuthorityRead("profile", "profile-main", "r1", "a" * 64, "profile-v1", Value("ok"))

    with pytest.raises(ResolverError) as caught:
        BaselineSourceResolver({"profile": Adapter()}).resolve(tmp_path, bad)
    assert caught.value.issue.blocking is True


def test_missing_exact_capability_fails_closed(tmp_path):
    with pytest.raises(ResolverError) as caught:
        BaselineSourceResolver({}).resolve(tmp_path, entry())
    assert caught.value.issue.code == "source_not_versioned"


def test_duplicate_roles_are_rejected_before_reads(tmp_path):
    resolver = BaselineSourceResolver({})
    with pytest.raises(ResolverError) as caught:
        resolver.resolve_manifest(tmp_path, (entry(), entry(source_id="profile-2")))
    assert caught.value.issue.code == "duplicate_role"


def test_default_unversioned_roles_fail_closed(tmp_path):
    resolver = BaselineSourceResolver(default_authority_adapters())
    with pytest.raises(ResolverError) as caught:
        resolver.resolve(tmp_path, entry("previous_chapter", "chapter:1"))
    assert caught.value.issue.code == "source_not_versioned"


def test_immutable_memory_authority_adapter_reads_exact_active_envelope(tmp_path):
    content = '{"name":"profile"}'
    item = MemoryItem.new_candidate(
        id="baseline-profile-chapter-027-v0001",
        kind=MemoryKind.PROJECT_DECISION,
        scope=MemoryScope.PROJECT,
        scope_id=tmp_path.name,
        title="冻结 Baseline Profile",
        content=content,
        evidence=(MemoryEvidence("controller_approval", "chapter-027"),),
        applicability=("planning", "writing", "review"),
        tags={"baseline_authority"},
    ).activate(actor="tingyu")
    JsonMemoryStore(tmp_path / ".creative_os/memory").add_immutable(item)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

    read = ImmutableMemoryAuthorityAdapter("profile", lambda value: value).read_exact(
        tmp_path,
        entry("profile", item.id, "v0001", digest),
    )

    assert read.value == content
    assert read.source_id == item.id


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "", "subject": "hero", "canonical_payload": ()},
        {"kind": "character", "subject": "", "canonical_payload": ()},
        {"kind": "character", "subject": "hero", "canonical_payload": (("b", 1), ("a", 2))},
        {"kind": "character", "subject": "hero", "canonical_payload": (("a", []),)},
    ],
)
def test_fact_snapshot_requires_deeply_immutable_canonical_payload(kwargs):
    with pytest.raises((TypeError, ValueError)):
        AuthorityFactSnapshot(**kwargs)
