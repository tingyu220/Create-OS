from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from creative_os.domains.novel_baseline import BaselineArtifact, CanonChapter, NovelBaselineDraft, build_novel_baseline
from creative_os.domains.novel_conflicts import ImportConflict, detect_import_conflicts
from creative_os.domains.novel_importer import classify_novel_documents
from creative_os.importing.model import ImportDocument, ImportManifest
from creative_os.importing.scanner import scan_source
from creative_os.novel_project import create_novel_project


class ImportApprovalError(ValueError):
    pass


def scan_into_project(source_root: str | Path, projects_root: str | Path, title: str) -> Path:
    project_root = Path(projects_root) / title
    if not project_root.exists():
        create_novel_project(projects_root, title)
    manifest = scan_source(source_root)
    import_root = _import_root(project_root)
    _write_json(import_root / "manifest.json", _manifest_dict(manifest))
    return project_root


def report_project(project_root: str | Path) -> tuple[NovelBaselineDraft, list[ImportConflict]]:
    root = Path(project_root)
    manifest = _load_manifest(_import_root(root) / "manifest.json")
    baseline = build_novel_baseline(classify_novel_documents(manifest))
    conflicts = detect_import_conflicts(baseline)
    import_root = _import_root(root)
    _write_json(import_root / "baseline.json", _baseline_dict(baseline))
    _write_json(import_root / "conflicts.json", [asdict(conflict) for conflict in conflicts])
    report_path = root / "production" / "reports" / "import_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_report_markdown(baseline, conflicts), encoding="utf-8")
    return baseline, conflicts


def approve_import(project_root: str | Path, *, actor: str, decisions_path: str | Path) -> None:
    root = Path(project_root)
    normalized_actor = actor.strip()
    if not normalized_actor or normalized_actor.casefold() == "system":
        raise ImportApprovalError("import approval requires a human actor")
    baseline, conflicts = report_project(root)
    decisions = _read_json(Path(decisions_path))
    accepted = list(decisions.get("accepted_canon_paths", []))
    known_paths = {chapter.source_path for chapter in baseline.canon_chapters}
    if not accepted or not set(accepted) <= known_paths:
        raise ImportApprovalError("accepted_canon_paths must select canonical chapter paths")
    known_knowledge_paths = {item.source_path for item in baseline.knowledge_candidates}
    accepted_knowledge = list(decisions.get("accepted_knowledge_paths", sorted(known_knowledge_paths)))
    if not set(accepted_knowledge) <= known_knowledge_paths:
        raise ImportApprovalError("accepted_knowledge_paths contains unknown documents")
    resolutions = decisions.get("resolutions", {})
    high_codes = {conflict.code for conflict in conflicts if conflict.severity == "high"}
    if not high_codes <= set(resolutions):
        raise ImportApprovalError("all high-severity conflicts require explicit resolutions")
    _write_json(
        _import_root(root) / "approval.json",
        {
            "actor": normalized_actor,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "accepted_canon_paths": accepted,
            "accepted_knowledge_paths": accepted_knowledge,
            "resolutions": resolutions,
        },
    )


def materialize_project(project_root: str | Path) -> list[Path]:
    root = Path(project_root)
    baseline, conflicts = report_project(root)
    approval_path = _import_root(root) / "approval.json"
    if not approval_path.exists():
        raise ImportApprovalError("import requires an approval record")
    approval = _read_json(approval_path)
    high_codes = {conflict.code for conflict in conflicts if conflict.severity == "high"}
    if not high_codes <= set(approval.get("resolutions", {})):
        raise ImportApprovalError("unresolved high-severity import conflicts")
    accepted = set(approval.get("accepted_canon_paths", []))
    if not accepted:
        raise ImportApprovalError("approval has no canonical chapters")
    accepted_knowledge = set(approval.get("accepted_knowledge_paths", []))
    manifest = _load_manifest(_import_root(root) / "manifest.json")
    _verify_source_unchanged(manifest)

    copied: list[Path] = []
    source_root = Path(manifest.source_root)
    for chapter in baseline.canon_chapters:
        if chapter.source_path not in accepted:
            continue
        destination = root / "production" / "final_chapters" / f"chapter_{chapter.number:03d}.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / chapter.source_path, destination)
        copied.append(destination)
    active_knowledge = [
        {
            "title": item.title,
            "content": item.content,
            "source_path": item.source_path,
            "source_hash": item.source_hash,
            "heading": item.heading,
            "status": "active",
            "approved_by": approval["actor"],
        }
        for item in baseline.knowledge_candidates
        if item.source_path in accepted_knowledge
    ]
    knowledge_path = root / ".creative_os" / "knowledge" / "imported_active.json"
    _write_json(knowledge_path, active_knowledge)
    active_baseline = _baseline_dict(baseline)
    active_baseline["canon_chapters"] = [
        chapter for chapter in active_baseline["canon_chapters"] if chapter["source_path"] in accepted
    ]
    for key in ("world_rules", "characters", "plot_milestones", "hooks", "style_constraints", "knowledge_candidates"):
        active_baseline[key] = [item for item in active_baseline[key] if item["source_path"] in accepted_knowledge]
    _write_json(_import_root(root) / "active_baseline.json", active_baseline)
    return copied


def _import_root(project_root: Path) -> Path:
    root = project_root / ".creative_os" / "import"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _verify_source_unchanged(manifest: ImportManifest) -> None:
    current = scan_source(manifest.source_root)
    expected = {document.relative_path: document.sha256 for document in manifest.documents}
    actual = {document.relative_path: document.sha256 for document in current.documents}
    if actual != expected:
        raise ImportApprovalError("source changed after scan; scan and review again")


def _manifest_dict(manifest: ImportManifest) -> dict[str, Any]:
    return {"source_root": manifest.source_root, "documents": [asdict(document) for document in manifest.documents]}


def _load_manifest(path: Path) -> ImportManifest:
    payload = _read_json(path)
    return ImportManifest(
        source_root=str(payload["source_root"]),
        documents=[ImportDocument(**document) for document in payload["documents"]],
    )


def _baseline_dict(baseline: NovelBaselineDraft) -> dict[str, Any]:
    return {
        "canon_chapters": [asdict(chapter) for chapter in baseline.canon_chapters],
        "world_rules": [asdict(item) for item in baseline.world_rules],
        "characters": [asdict(item) for item in baseline.characters],
        "plot_milestones": [asdict(item) for item in baseline.plot_milestones],
        "hooks": [asdict(item) for item in baseline.hooks],
        "style_constraints": [asdict(item) for item in baseline.style_constraints],
        "knowledge_candidates": [asdict(item) for item in baseline.knowledge_candidates],
    }


def _report_markdown(baseline: NovelBaselineDraft, conflicts: list[ImportConflict]) -> str:
    lines = ["# 导入报告", "", f"- 正式章节候选：{len(baseline.canon_chapters)}", f"- 项目知识候选：{len(baseline.knowledge_candidates)}", "", "## 冲突"]
    if not conflicts:
        lines.append("\n无高风险冲突。")
    for conflict in conflicts:
        lines.extend(["", f"- [{conflict.severity}] {conflict.code}: {', '.join(conflict.values)}", f"  来源：{', '.join(conflict.sources)}"])
    return "\n".join(lines) + "\n"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
