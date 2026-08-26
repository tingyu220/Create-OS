from creative_os.pov_strategy_shadow import run_pov_strategy_shadow
from creative_os.domains.pov_strategy_model import ChapterNeeds


def test_shadow_missing_input_blocks_without_contract_or_chapter(tmp_path):
    before = set(tmp_path.rglob("*"))
    result = run_pov_strategy_shadow(tmp_path, 2, ChapterNeeds(("推进",), "问题", (), "", ()), write_audit=False)
    assert result.status == "blocked"
    after = set(tmp_path.rglob("*"))
    assert before == after
