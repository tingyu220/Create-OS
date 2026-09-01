from __future__ import annotations

from creative_os.projection.quality import GateResultSnapshot, QualityIssueSnapshot, QualitySnapshot
from creative_os.projection.source import ProjectFacts, ProjectionChangeSet


def project_quality(
    facts: ProjectFacts,
    previous: QualitySnapshot | None = None,
    changes: ProjectionChangeSet | None = None,
) -> QualitySnapshot:
    del previous, changes
    issues = tuple(
        QualityIssueSnapshot(
            issue_id=item.issue_id,
            code=item.code,
            severity=item.severity,
            blocking=item.blocking,
            scope=item.scope,
            source_refs=(item.source_ref,),
        )
        for item in sorted(facts.quality_issues, key=lambda value: value.issue_id)
    )
    gates = tuple(
        GateResultSnapshot(
            gate_id=item.gate_id,
            status=item.status,
            source_refs=(item.source_ref,),
        )
        for item in sorted(facts.gate_results, key=lambda value: (value.gate_id, value.source_ref.source_id))
    )
    references = tuple(dict.fromkeys(
        [*(item.source_refs[0] for item in issues), *(item.source_refs[0] for item in gates)]
    ))
    return QualitySnapshot(issues=issues, gate_results=gates, source_refs=references)
