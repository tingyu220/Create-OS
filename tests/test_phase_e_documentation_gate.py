from pathlib import Path

def test_phase_e_operations_document_covers_offline_gate_evidence():
    text=Path('docs/phase-e-offline-operations.md').read_text(encoding='utf-8')
    for term in ('brief/schema/readiness','Engagement projection','Ledger/Curve/Foreshadow','Orchestrator 状态','Store 备份与恢复','Writer 出口','真实校准'):
        assert term in text

def test_roadmap_records_offline_completion_and_calibration_boundary():
    text=Path('docs/novel-production-roadmap.md').read_text(encoding='utf-8')
    assert '已完成并通过离线 Gate' in text and '未启动' in text
