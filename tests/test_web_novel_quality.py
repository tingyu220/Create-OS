import pytest
from creative_os.domains.web_novel_quality import WebNovelQualityGate

def test_quality_gate_hard_rules_block_missing_structure():
    result=WebNovelQualityGate.evaluate({"artifact_hash":"a"*64,"chapter":1,"choice":False,"progress":False,"conflict":False,"hook":False})
    assert result.status == "blocked"
    assert {"choice_missing","progress_missing"} <= set(result.issues)

def test_quality_gate_keeps_human_soft_score_separate():
    result=WebNovelQualityGate.evaluate({"artifact_hash":"a"*64,"chapter":1,"choice":True,"progress":True,"conflict":True,"hook":True})
    assert result.status == "passed"
    assert result.soft_review_required is True
