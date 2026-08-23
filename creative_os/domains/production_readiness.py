from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path

from creative_os.domains.reader_engagement_gate import evaluate_reader_engagement_exit_gate
from creative_os.domains.production_readiness_store import ProductionReadinessStore


class ReadinessBlockedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProductionReadinessResult:
    status: str
    issues: tuple[str, ...]
    engagement_gate_passed: bool


class ProductionReadinessAudit:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)

    def audit(self) -> ProductionReadinessResult:
        try:
            brief = json.loads((self.project_root / "brief.json").read_text(encoding="utf-8"))
        except Exception:
            raise ReadinessBlockedError("brief_missing")
        issues: list[str] = []
        if not isinstance(brief.get("genre"), str) or not brief["genre"].strip():
            issues.append("genre_missing")
        if not isinstance(brief.get("logline"), str) or not brief["logline"].strip():
            issues.append("logline_missing")
        gate = evaluate_reader_engagement_exit_gate(self.project_root)
        if not gate.passed:
            issues.append("active_engagement_missing")
        if issues:
            return ProductionReadinessResult("blocked", tuple(issues), gate.passed)
        return ProductionReadinessResult("ready", (), True)

    def audit_project(self, project_root: str | Path) -> ProductionReadinessResult:
        self.project_root = Path(project_root)
        return self.audit()

    def audit_with_source(self, authority_root: str | Path, source_root: str | Path) -> ProductionReadinessResult:
        self.project_root = Path(authority_root)
        self.source_root = Path(source_root)
        try:
            brief = json.loads((self.source_root / "Novel_README.md").read_text(encoding="utf-8")) if False else None
            readme = (self.source_root / "Novel_README.md").read_text(encoding="utf-8")
        except Exception:
            return ProductionReadinessResult("blocked", ("source_read_error",), False)
        issues: list[str] = []
        if "**类型**： 科幻/类三体" not in readme or "一句话简介" not in readme:
            issues.append("source_positioning_missing")
        if not (self.source_root / "00_Worldview" / "Main_Worldview.md").is_file():
            issues.append("worldview_missing")
        if not (self.source_root / "02_Plot" / "Plot_Outline.md").is_file():
            issues.append("plot_missing")
        gate = evaluate_reader_engagement_exit_gate(self.project_root)
        if not gate.passed:
            issues.append("active_engagement_missing")
        return ProductionReadinessResult("blocked" if issues else "ready", tuple(issues), gate.passed)

    def build_source_approval(self, authority_root: str | Path, source_root: str | Path) -> dict[str, object]:
        authority_root, source_root = Path(authority_root), Path(source_root)
        result = self.audit_with_source(authority_root, source_root)
        if result.status != "ready":
            raise ReadinessBlockedError(",".join(result.issues))
        files = [source_root / "Novel_README.md", source_root / "00_Worldview" / "Main_Worldview.md", source_root / "核心框架.md", source_root / "02_Plot" / "Plot_Outline.md", source_root / "03_Hooks" / "Hooks_Tracker.md"]
        sources = tuple({"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files)
        body = {"status": "approved", "sources": sources, "ruleset": "phase-e-readiness-v1"}
        body["approval_hash"] = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return body

    def build_readiness_approval(self, project_root: str | Path) -> dict[str, str | tuple[str, ...]]:
        result = self.audit_project(project_root)
        if result.status != "ready":
            raise ReadinessBlockedError(",".join(result.issues))
        brief = json.loads((Path(project_root) / "brief.json").read_text(encoding="utf-8"))
        approval = {
            "project_root": str(Path(project_root)),
            "status": result.status,
            "issues": result.issues,
            "approval_hash": hashlib.sha256(json.dumps({"project_root": str(Path(project_root)), "status": result.status, "issues": result.issues}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "brief_genre": brief.get("genre", ""),
            "brief_logline": brief.get("logline", ""),
        }
        return approval

    def require_ready(self) -> ProductionReadinessResult:
        result = self.audit()
        if result.status != "ready":
            raise ReadinessBlockedError(",".join(result.issues))
        return result

    def persist_audit(self) -> dict:
        result=self.audit(); payload={"audit_hash": hashlib.sha256(json.dumps({"status":result.status,"issues":result.issues},sort_keys=True,default=str).encode()).hexdigest(),"status":result.status,"ruleset_hash":hashlib.sha256(b"phase-e-readiness-v1").hexdigest()}
        return ProductionReadinessStore(self.project_root).append_audit(payload)

    def approve(self, audit_record_id: str, audit_hash: str, actor: str, reason: str) -> dict:
        return ProductionReadinessStore(self.project_root).append_approval({"audit_record_id":audit_record_id,"audit_hash":audit_hash,"actor":actor,"reason":reason,"decision":"approved"})
