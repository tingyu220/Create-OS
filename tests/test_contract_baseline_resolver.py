from dataclasses import dataclass

import pytest

from creative_os.domains.contract_baseline import BaselineEntry
from creative_os.domains.contract_baseline_resolver import (
    AuthorityRead,
    AuthorityFactSnapshot,
    BaselineSourceResolver,
    ResolverError,
    UnsupportedAuthorityAdapter,
    default_authority_adapters,
)


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
