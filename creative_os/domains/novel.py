from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from creative_os.domains.base import DomainPackage
from creative_os.domains.novel_capabilities import NOVEL_CAPABILITY_NAMES


class NovelSchemaKind(StrEnum):
    CHARACTER = "character"
    WORLD = "world"
    LOCATION = "location"
    EVENT = "event"
    CHAPTER = "chapter"
    SCENE = "scene"
    TIMELINE = "timeline"
    RELATIONSHIP = "relationship"
    FORESHADOW = "foreshadow"
    CONFLICT = "conflict"
    STYLE = "style"
    NARRATIVE_DECISION = "narrative_decision"


@dataclass(frozen=True, slots=True)
class NovelSchemaDefinition:
    name: str
    required_fields: list[str]
    optional_fields: list[str] = field(default_factory=list)


class NovelDomainPackage(DomainPackage):
    def __init__(self) -> None:
        self._schema_definitions = {
            NovelSchemaKind.CHARACTER: NovelSchemaDefinition(
                name="Character",
                required_fields=["name", "role", "goal", "state"],
                optional_fields=["conflict", "relations", "hooks"],
            ),
            NovelSchemaKind.WORLD: NovelSchemaDefinition(
                name="World",
                required_fields=["rule", "scope", "limit", "evidence"],
                optional_fields=["source", "risk"],
            ),
            NovelSchemaKind.LOCATION: NovelSchemaDefinition(
                name="Location",
                required_fields=["name", "role", "state"],
                optional_fields=["anchors", "access_constraints", "evidence"],
            ),
            NovelSchemaKind.EVENT: NovelSchemaDefinition(
                name="Event",
                required_fields=["event", "participants", "outcome", "evidence"],
                optional_fields=["chapter", "impact"],
            ),
            NovelSchemaKind.CHAPTER: NovelSchemaDefinition(
                name="Chapter",
                required_fields=["chapter", "goal", "scenes", "knowledge_updates"],
                optional_fields=["hooks", "summary"],
            ),
            NovelSchemaKind.SCENE: NovelSchemaDefinition(
                name="Scene",
                required_fields=["scene", "goal", "characters", "conflict", "outcome"],
                optional_fields=["setting", "foreshadow"],
            ),
            NovelSchemaKind.TIMELINE: NovelSchemaDefinition(
                name="Timeline",
                required_fields=["time", "event", "impact"],
                optional_fields=["chapter", "scene"],
            ),
            NovelSchemaKind.RELATIONSHIP: NovelSchemaDefinition(
                name="Relationship",
                required_fields=["source", "target", "relation"],
                optional_fields=["status", "evidence"],
            ),
            NovelSchemaKind.FORESHADOW: NovelSchemaDefinition(
                name="Foreshadow",
                required_fields=["hook", "source", "status"],
                optional_fields=["resolution", "risk"],
            ),
            NovelSchemaKind.CONFLICT: NovelSchemaDefinition(
                name="Conflict",
                required_fields=["subject", "opponent", "stakes"],
                optional_fields=["resolution", "chapter"],
            ),
            NovelSchemaKind.STYLE: NovelSchemaDefinition(
                name="Style",
                required_fields=["tone", "pace", "constraints"],
                optional_fields=["examples"],
            ),
            NovelSchemaKind.NARRATIVE_DECISION: NovelSchemaDefinition(
                name="NarrativeDecision",
                required_fields=["chapter", "arc", "chapter_contract", "target_chinese_chars"],
                optional_fields=["reader_change", "pressure_curve", "foreshadow_actions"],
            ),
        }
        self._rules_by_area = {
            "review": [
                "character_consistency",
                "world_rule_consistency",
                "timeline_consistency",
                "foreshadow_tracking",
                "relationship_consistency",
                "narrative_contract_required",
                "reader_state_tracking",
                "foreshadow_lifecycle",
                "outline_change_requires_approval",
            ],
            "workflow": [
                "proposal_before_world",
                "character_before_chapter",
                "chapter_goal_required",
                "scene_before_draft",
            ],
            "writing": [
                "scene_conflict_required",
                "character_state_required",
                "world_rule_must_be_respected",
                "protagonist_choice_required",
                "information_boundary_required",
            ],
        }
        templates = {
            "character": "Name:\nRole:\nGoal:\nConflict:\nState:\nRelations:\nHooks:",
            "world": "Rule:\nScope:\nLimit:\nEvidence:\nRisk:",
            "chapter": "Chapter:\nGoal:\nScenes:\nKey Events:\nKnowledge Updates:\nHooks:",
            "scene": "Scene:\nGoal:\nCharacters:\nConflict:\nOutcome:\nForeshadow:",
            "timeline": "Time:\nEvent:\nImpact:\nChapter:\nScene:",
            "relationship": "Source:\nTarget:\nRelation:\nStatus:\nEvidence:",
            "foreshadow": "Hook:\nSource:\nStatus:\nResolution:\nRisk:",
            "review": "Issue:\nEvidence:\nSeverity:\nFix Task:",
        }
        super().__init__(
            name="novel",
            schema=[definition.name for definition in self._schema_definitions.values()],
            rules=sorted({rule for rules in self._rules_by_area.values() for rule in rules}),
            workflow=[
                "Idea",
                "Proposal",
                "World",
                "Character",
                "Outline",
                "Chapter",
                "Scene",
                "Draft",
                "Review",
                "Knowledge Update",
            ],
            templates=templates,
        )
        self._skills = [
            "story-design",
            "character-design",
            "world-building",
            "plot-design",
            "chapter-planning",
            "scene-planning",
            "scene-writing",
            "dialogue-writing",
            "revision",
        ]
        self._production_workflow = [
            "Idea",
            "Proposal",
            "Story Bible",
            "Outline",
            "Chapter Plan",
            "Scene Plan",
            "Draft",
            "Review",
            "Compile",
            "Final",
        ]

    def schema_definition(self, kind: NovelSchemaKind | str) -> NovelSchemaDefinition:
        schema_kind = NovelSchemaKind(kind)
        return self._schema_definitions[schema_kind]

    def rules_for(self, area: str) -> list[str]:
        return list(self._rules_by_area.get(area, []))

    def template(self, name: str) -> str:
        if name not in self.templates:
            raise KeyError(name)
        return self.templates[name]

    @property
    def skills(self) -> list[str]:
        return list(self._skills)

    @property
    def production_workflow(self) -> list[str]:
        return list(self._production_workflow)

    @property
    def capability_names(self) -> tuple[str, ...]:
        """返回领域可执行能力；具体实现由 NovelDomainService 组合。"""
        return NOVEL_CAPABILITY_NAMES
