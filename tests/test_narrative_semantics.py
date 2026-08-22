from dataclasses import replace

from creative_os.domains.narrative_semantics import (
    FunctionSemanticNormalizer, SemanticRelation,
)
from tests.test_narrative_decision import _v2_decision


def test_different_words_with_same_structure_are_blocking_repetition():
    normalizer = FunctionSemanticNormalizer()
    previous = normalizer.normalize(
        "建立主角调查", before_state="未知", after_state="开始调查",
        arc_phase="setup", ending_shift="开始调查",
    )
    current = normalizer.normalize(
        "塑造主角追查", before_state="未知", after_state="开始调查",
        arc_phase="setup", ending_shift="开始调查",
    )
    comparison = normalizer.compare(current, previous)
    assert comparison.relation is SemanticRelation.REPEATED
    assert comparison.blocking is True
    assert comparison.asset_versions


def test_legal_upgrade_or_new_consequence_is_non_blocking():
    normalizer = FunctionSemanticNormalizer()
    previous = normalizer.normalize(
        "建立主角调查", before_state="怀疑", after_state="调查",
        arc_phase="setup", ending_shift="受到关注",
    )
    current = normalizer.normalize(
        "升级主角追查", before_state="调查", after_state="取得证据",
        arc_phase="escalation", ending_shift="进入审查",
    )
    comparison = normalizer.compare(current, previous)
    assert comparison.relation is SemanticRelation.PROGRESSION
    assert comparison.blocking is False


def test_unknown_vocabulary_is_blocking_and_negation_is_preserved():
    normalizer = FunctionSemanticNormalizer()
    uncertain = normalizer.normalize(
        "量子跃迁主角", before_state="A", after_state="B",
        arc_phase="turn", ending_shift="C",
    )
    assert normalizer.compare(uncertain, uncertain).relation is SemanticRelation.UNCERTAIN
    positive = normalizer.normalize("建立主角调查", before_state="A", after_state="B", arc_phase="setup", ending_shift="C")
    negative = normalizer.normalize("建立主角不调查", before_state="A", after_state="B", arc_phase="setup", ending_shift="C")
    assert positive.canonical_action != negative.canonical_action
    unrelated = normalizer.normalize("建立主角未雨绸缪后调查", before_state="A", after_state="B", arc_phase="setup", ending_shift="C")
    assert unrelated.uncertain is True


def test_only_explicitly_approved_entity_aliases_are_normalized():
    without = FunctionSemanticNormalizer().normalize(
        "建立林澈调查", before_state="A", after_state="B", arc_phase="setup", ending_shift="C",
    )
    with_alias = FunctionSemanticNormalizer(
        approved_entity_aliases={"林澈": "character:lin-che"},
    ).normalize(
        "建立林澈调查", before_state="A", after_state="B", arc_phase="setup", ending_shift="C",
    )
    assert without.uncertain is True
    assert with_alias.entity_or_hook_id == "character:lin-che"
    assert with_alias.uncertain is False
    false_boundary = FunctionSemanticNormalizer().normalize(
        "建立副主角调查", before_state="A", after_state="B", arc_phase="setup", ending_shift="C",
    )
    assert false_boundary.entity_or_hook_id == "unknown"


def test_raw_state_drift_and_phase_regression_cannot_launder_repetition():
    normalizer = FunctionSemanticNormalizer()
    previous = normalizer.normalize("建立主角调查", before_state="A", after_state="B", arc_phase="escalation", ending_shift="C")
    cosmetic = normalizer.normalize("塑造主角追查", before_state="A。", after_state="B", arc_phase="escalation", ending_shift="C")
    regression = normalizer.normalize("塑造主角追查", before_state="B", after_state="D", arc_phase="setup", ending_shift="E")
    assert normalizer.compare(cosmetic, previous).relation is SemanticRelation.UNCERTAIN
    assert normalizer.compare(regression, previous).relation is SemanticRelation.UNCERTAIN
    assert normalizer.compare(cosmetic, previous).blocking is True


def test_semantic_asset_version_is_explicit_and_stale_review_binding_changes():
    normalizer = FunctionSemanticNormalizer()
    assert normalizer.asset_versions == (("function_semantics", "v1"),)
