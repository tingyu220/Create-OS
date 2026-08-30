from pathlib import Path
from creative_os.domains.web_novel_quality_store import WebNovelQualityStore

def test_quality_store_exact_restart_and_idempotency(tmp_path: Path):
    store=WebNovelQualityStore(tmp_path)
    payload={"review_id":"q1","artifact_hash":"a"*64,"hard_status":"passed","issues":[]}
    first=store.append(payload)
    assert WebNovelQualityStore(tmp_path).load_exact("q1",first["content_hash"]) == payload
    assert store.append(payload)==first
