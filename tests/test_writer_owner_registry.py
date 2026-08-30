from pathlib import Path
from creative_os.domains.chapter_production_owner_registry import production_owner_registry, production_exit_manifest

def test_writer_registry_declares_all_production_exits():
    registry=production_owner_registry()
    assert {"writer_execution_authority","writer_reconciliation","staged_artifact","final_artifact","promotion_receipt"} <= set(registry)
    manifest=production_exit_manifest()
    assert "novel_continuation_runner.promote_passing_draft" in manifest["promotion"]
    assert "novel_continuation_runner.continue_one_chapter" in manifest["writer"]

def test_writer_exit_scan_finds_only_guarded_final_writes():
    manifest=production_exit_manifest()
    assert all(item["guarded"] is True for item in manifest["final_writes"])
