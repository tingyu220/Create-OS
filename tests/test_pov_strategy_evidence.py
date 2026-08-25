import hashlib

import pytest

from creative_os.domains.pov_strategy_evidence import POVEvidenceError, verify_evidence_ref
from creative_os.domains.pov_strategy_model import EvidenceRef


def test_evidence_ref_requires_existing_unchanged_authoritative_source(tmp_path):
    path = tmp_path / "production" / "final_chapters" / "chapter_001.md"
    path.parent.mkdir(parents=True)
    original = "# 第1章\n正式正文"
    path.write_text(original, encoding="utf-8")
    ref = EvidenceRef(
        "production/final_chapters/chapter_001.md", "1",
        hashlib.sha256(original.encode("utf-8")).hexdigest(), "chapter:1", "正式章节",
    )
    verify_evidence_ref(tmp_path, ref)
    path.write_text("被篡改", encoding="utf-8")
    with pytest.raises(POVEvidenceError, match="unverifiable"):
        verify_evidence_ref(tmp_path, ref)


def test_evidence_locator_must_resolve_inside_source(tmp_path):
    path = tmp_path / ".creative_os" / "state" / "snapshots" / "event" / "launch.json"
    path.parent.mkdir(parents=True)
    text = '{"kind":"event","subject":"launch"}'
    path.write_text(text, encoding="utf-8")
    ref = EvidenceRef(
        ".creative_os/state/snapshots/event/launch.json", "1",
        hashlib.sha256(text.encode("utf-8")).hexdigest(), "snapshot:event:wrong", "状态",
    )
    with pytest.raises(POVEvidenceError, match="unverifiable"):
        verify_evidence_ref(tmp_path, ref)
