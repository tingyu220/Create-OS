from __future__ import annotations

import pytest

from creative_os.domains.novel_domain_composition import build_novel_domain_service


class _Writer:
    def write(self, request, admission):
        raise AssertionError("装配测试不应执行正文生成")


class _Resolver:
    pass


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
