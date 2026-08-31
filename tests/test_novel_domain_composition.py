from __future__ import annotations

import importlib

import pytest

from creative_os import llm_writer
from creative_os.domains import novel_domain_composition
from creative_os.domains.novel_domain_composition import (
    build_env_novel_domain_service,
    build_llm_novel_domain_service,
    build_novel_domain_service,
)


class _Writer:
    def write(self, request, admission):
        raise AssertionError("装配测试不应执行正文生成")


class _Resolver:
    pass


class _Client:
    model = "test-model"

    def complete(self, messages, *, temperature, max_tokens):
        raise AssertionError("装配测试不应执行模型调用")


def test_build_llm_service_wraps_injected_client(tmp_path):
    service = build_llm_novel_domain_service(tmp_path, baseline_resolver=_Resolver(), client=_Client())

    assert service.capabilities().names[2] == "draft_writing"


def test_build_env_service_passes_env_file_and_reads_client_once(tmp_path, monkeypatch):
    calls = []
    client = _Client()

    def from_env(env_file):
        calls.append(env_file)
        return client

    monkeypatch.setattr(novel_domain_composition.OpenAICompatibleClient, "from_env", from_env)

    service = build_env_novel_domain_service(
        tmp_path,
        baseline_resolver=_Resolver(),
        env_file=tmp_path / "custom.env",
    )

    assert calls == [tmp_path / "custom.env"]
    assert service._writer._client is client


def test_importing_composition_does_not_read_environment(monkeypatch):
    monkeypatch.setattr(
        llm_writer.OpenAICompatibleClient,
        "from_env",
        lambda *_: (_ for _ in ()).throw(AssertionError()),
    )

    importlib.reload(novel_domain_composition)


def test_build_novel_domain_service_exposes_complete_capability_catalog(tmp_path) -> None:
    service = build_novel_domain_service(
        tmp_path,
        writer=_Writer(),
        baseline_resolver=_Resolver(),
    )

    assert service.capabilities().names == (
        "chapter_planning",
        "writer_admission",
        "draft_writing",
        "draft_review",
        "approved_compile",
        "lesson_candidate",
    )


@pytest.mark.parametrize("field", ("writer", "baseline_resolver"))
def test_build_novel_domain_service_rejects_missing_required_port(tmp_path, field) -> None:
    values = {"writer": _Writer(), "baseline_resolver": _Resolver()}
    values[field] = None

    with pytest.raises(ValueError, match=f"novel_domain_{field.replace('baseline_', 'baseline_')}_missing"):
        build_novel_domain_service(tmp_path, **values)
