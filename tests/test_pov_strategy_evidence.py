import hashlib

import pytest

from creative_os.domains.pov_strategy_evidence import POVEvidenceError, verify_evidence_ref
from creative_os.domains.pov_strategy_model import EvidenceRef
from creative_os.domains.narrative_evidence import EvidenceLocator


def test_evidence_ref_requires_existing_unchanged_authoritative_source(tmp_path):
    path = tmp_path / "production" / "final_chapters" / "chapter_001.md"
    path.parent.mkdir(parents=True)
    original = "# 第1章\n正式正文"
    path.write_text(original, encoding="utf-8")
    ref = EvidenceRef(
        source_id="production/final_chapters/chapter_001.md", source_version="1",
        source_content_hash=hashlib.sha256(original.encode("utf-8")).hexdigest(),
        locator=EvidenceLocator("text_anchor", "chapter:1"), assertion="正式章节",
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
        source_id=".creative_os/state/snapshots/event/launch.json", source_version="1",
        source_content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        locator=EvidenceLocator("text_anchor", "snapshot:event:wrong"), assertion="状态",
    )
    with pytest.raises(POVEvidenceError, match="unverifiable"):
        verify_evidence_ref(tmp_path, ref)
