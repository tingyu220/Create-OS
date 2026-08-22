from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class SemanticRelation(StrEnum):
    REPEATED = "repeated"
    PROGRESSION = "progression"
    DISTINCT = "distinct"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class FunctionSemanticKey:
    function_type: str
    canonical_action: str
    entity_or_hook_id: str
    before_state: str
    after_state: str
    arc_phase: str
    ending_shift: str
    uncertain: bool = False


@dataclass(frozen=True, slots=True)
class SemanticComparison:
    relation: SemanticRelation
    blocking: bool
    evidence: tuple[str, ...]
    asset_versions: tuple[tuple[str, str], ...]


class FunctionSemanticNormalizer:
    """Deterministic local normalizer backed only by versioned repository assets."""

    def __init__(self, *, approved_entity_aliases: dict[str, str] | None = None,
                 asset_root: str | Path | None = None) -> None:
        root = Path(asset_root) if asset_root else Path(__file__).parents[1] / "assets" / "function_semantics" / "v1"
        self._actions = _load(root / "action_lexicon.json", {"schema_version", "version", "actions", "negations"})
        self._stops = _load(root / "stop_phrases.json", {"schema_version", "version", "phrases"})
        self._types = _load(root / "function_types.json", {"schema_version", "version", "types", "allowed_transitions"})
        self._entities = _load(root / "entity_slots.json", {"schema_version", "version", "builtins", "policy"})
        self._cases = _load(root / "cases.json", {"schema_version", "version", "cases"})
        if {asset["version"] for asset in (self._actions, self._stops, self._types, self._entities, self._cases)} != {"v1"}:
            raise ValueError("semantic asset versions must match")
        _string_mapping(self._actions["actions"], "action lexicon")
        _string_list(self._actions["negations"], "negations", allow_empty=False)
        _string_list(self._stops["phrases"], "stop phrases", allow_empty=True)
        if set(self._actions["negations"]) & set(self._stops["phrases"]):
            raise ValueError("negations cannot be stop phrases")
        function_types = _string_mapping(self._types["types"], "function types")
        if set(function_types) != {"establish", "upgrade", "turn", "reveal", "fulfill", "close"}:
            raise ValueError("function type asset must define the six approved types")
        transitions = self._types["allowed_transitions"]
        if (not isinstance(transitions, list) or any(
            not isinstance(item, list) or len(item) != 2
            or any(value not in function_types for value in item)
            for item in transitions
        )):
            raise ValueError("invalid function type transitions")
        aliases = self._entities["builtins"]
        if not isinstance(aliases, dict):
            raise ValueError("entity builtins must be an object")
        if self._entities["policy"] != "approved_aliases_only":
            raise ValueError("entity alias policy must be approved_aliases_only")
        cases = self._cases["cases"]
        if (not isinstance(cases, list) or any(
            not isinstance(item, dict) or set(item) != {"left", "right", "relation"}
            or not all(isinstance(item[name], str) and item[name].strip()
                       for name in ("left", "right"))
            or item["relation"] not in {relation.value for relation in SemanticRelation}
            for item in cases
        )):
            raise ValueError("invalid semantic cases")
        self._aliases = {**aliases, **(approved_entity_aliases or {})}
        if any(not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip()
               for key, value in self._aliases.items()):
            raise ValueError("entity aliases must be explicit string mappings")
        self.asset_versions = (("function_semantics", "v1"),)
        self._validate_cases()

    def normalize(self, text: str, *, before_state: str, after_state: str,
                  arc_phase: str, ending_shift: str) -> FunctionSemanticKey:
        values = (text, before_state, after_state, arc_phase, ending_shift)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("semantic normalization requires non-empty strings")
        normalized = text.strip()
        for phrase in self._stops["phrases"]:
            if normalized.startswith(phrase):
                normalized = normalized[len(phrase):]
        function_type, type_alias = _match_with_alias(normalized, self._types["types"])
        body = normalized[len(type_alias):] if type_alias and normalized.startswith(type_alias) else normalized
        action, action_alias = _match_with_alias(body, self._actions["actions"])
        negated = bool(action_alias) and any(marker + action_alias in body
                                             for marker in self._actions["negations"])
        ambiguous_negation = any(marker in body for marker in self._actions["negations"]) and not negated
        canonical_action = ("not:" if negated else "") + (action or "unknown")
        entity = next((entity_id for alias, entity_id in sorted(
            self._aliases.items(), key=lambda item: (-len(item[0]), item[0])
        ) if body.startswith(alias)), "unknown")
        uncertain = function_type is None or action is None or entity == "unknown" or ambiguous_negation
        return FunctionSemanticKey(
            function_type or "unknown", canonical_action, entity,
            before_state.strip(), after_state.strip(), arc_phase.strip(), ending_shift.strip(),
            uncertain,
        )

    def compare(self, current: FunctionSemanticKey,
                previous: FunctionSemanticKey) -> SemanticComparison:
        if type(current) is not FunctionSemanticKey or type(previous) is not FunctionSemanticKey:
            raise TypeError("semantic comparison requires normalized keys")
        evidence = (f"previous={_key_text(previous)}", f"current={_key_text(current)}")
        if current.uncertain or previous.uncertain:
            return SemanticComparison(SemanticRelation.UNCERTAIN, True, evidence, self.asset_versions)
        same_core = (current.canonical_action, current.entity_or_hook_id) == (
            previous.canonical_action, previous.entity_or_hook_id,
        )
        same_state = (current.before_state, current.after_state, current.arc_phase,
                      current.ending_shift) == (
            previous.before_state, previous.after_state, previous.arc_phase,
            previous.ending_shift,
        )
        phases = {"setup": 0, "escalation": 1, "turn": 2, "aftermath": 3, "closure": 4}
        non_regressing = (current.arc_phase in phases and previous.arc_phase in phases
                          and phases[current.arc_phase] >= phases[previous.arc_phase])
        allowed_transition = [previous.function_type, current.function_type] in self._types["allowed_transitions"]
        continuous_new_consequence = (
            current.before_state == previous.after_state
            and (current.after_state != previous.after_state
                 or current.ending_shift != previous.ending_shift)
        )
        if same_core and current.function_type == previous.function_type and same_state:
            relation = SemanticRelation.REPEATED
        elif same_core and non_regressing and (allowed_transition or continuous_new_consequence):
            relation = SemanticRelation.PROGRESSION
        elif same_core:
            relation = SemanticRelation.UNCERTAIN
        else:
            relation = SemanticRelation.DISTINCT
        return SemanticComparison(relation, relation in {SemanticRelation.REPEATED, SemanticRelation.UNCERTAIN},
                                  evidence, self.asset_versions)

    def _validate_cases(self) -> None:
        for case in self._cases["cases"]:
            left = self.normalize(case["left"], before_state="S0", after_state="S1",
                                  arc_phase="setup", ending_shift="E")
            right_phase = "escalation" if case["relation"] == "progression" else "setup"
            right = self.normalize(case["right"], before_state="S0", after_state="S1",
                                   arc_phase=right_phase, ending_shift="E")
            if self.compare(right, left).relation.value != case["relation"]:
                raise ValueError("semantic case does not match normalizer behavior")


def _load(path: Path, fields: set[str]) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"invalid semantic asset: {path.name}") from error
    if (not isinstance(value, dict) or set(value) != fields
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not isinstance(value["version"], str) or not value["version"].strip()):
        raise ValueError(f"invalid semantic asset schema: {path.name}")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate semantic asset key")
        result[key] = value
    return result


def _match(text: str, mapping: object) -> str | None:
    if not isinstance(mapping, dict):
        raise ValueError("semantic lexicon must be an object")
    matches = [canonical for canonical, aliases in mapping.items()
               if isinstance(aliases, list) and any(alias in text for alias in aliases)]
    return sorted(matches)[0] if len(matches) == 1 else None


def _match_with_alias(text: str, mapping: object) -> tuple[str | None, str | None]:
    if not isinstance(mapping, dict):
        raise ValueError("semantic lexicon must be an object")
    matches = [(canonical, alias) for canonical, aliases in mapping.items()
               if isinstance(aliases, list) for alias in aliases if alias in text]
    canonicals = {canonical for canonical, _ in matches}
    if len(canonicals) != 1:
        return None, None
    canonical = next(iter(canonicals))
    alias = sorted((alias for item, alias in matches if item == canonical),
                   key=lambda value: (-len(value), value))[0]
    return canonical, alias


def _string_mapping(value: object, name: str) -> dict[str, list[str]]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{name} must be an object")
    for key, aliases in value.items():
        if (not isinstance(key, str) or not key.strip()
                or not isinstance(aliases, list) or not aliases):
            raise ValueError(f"invalid {name}")
        _string_list(aliases, name, allow_empty=False)
    return value


def _string_list(value: object, name: str, *, allow_empty: bool) -> list[str]:
    if (not isinstance(value, list) or (not allow_empty and not value)
            or any(not isinstance(item, str) or not item.strip() for item in value)
            or len(set(value)) != len(value)):
        raise ValueError(f"invalid {name}")
    return value


def _key_text(value: FunctionSemanticKey) -> str:
    return "|".join((value.function_type, value.canonical_action, value.entity_or_hook_id,
                     value.before_state, value.after_state, value.arc_phase, value.ending_shift))
