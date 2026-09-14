from __future__ import annotations

import json

from creative_os.projection.quality import GateResultSnapshot, QualityIssueSnapshot, QualitySnapshot
from creative_os.projection.source import ProjectFacts, ProjectionChangeSet


def project_quality(
    facts: ProjectFacts,
    previous: QualitySnapshot | None = None,
    changes: ProjectionChangeSet | None = None,
) -> QualitySnapshot:
    del previous, changes
    dispositions = {}
    for event in facts.execution_events:
        if event.event_type != "ReviewIssueAccepted":
            continue
        try:
            payload = json.loads(event.payload_json)
            issue_id = payload.get("issue_id")
            if isinstance(issue_id, str) and issue_id:
                dispositions[issue_id] = event.source_ref
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    issues = tuple(
        QualityIssueSnapshot(
            issue_id=item.issue_id,
            code=item.code,
            severity=item.severity,
            blocking=item.blocking,
            scope=item.scope,
            source_refs=(item.source_ref,) if item.issue_id not in dispositions else (item.source_ref, dispositions[item.issue_id]),
            disposition_status="accepted" if item.issue_id in dispositions else None,
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
        [*(ref for item in issues for ref in item.source_refs), *(ref for item in gates for ref in item.source_refs)]
    ))
    return QualitySnapshot(issues=issues, gate_results=gates, source_refs=references)
