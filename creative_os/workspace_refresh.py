from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable
from creative_os.runtime.events import EventType, ExecutionEvent
from uuid import uuid4
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from creative_os.workspace_dto import ProjectionSection

class RefreshStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"

@dataclass(frozen=True, slots=True)
class RefreshDiagnostic:
    code: str
    message: str

@dataclass(frozen=True, slots=True)
class RefreshResult:
    refresh_id: str
    status: RefreshStatus
    attempts: int
    diagnostic: RefreshDiagnostic | None = None
    trace_id: str | None = None
    receipt: RefreshReceipt | None = None
    requested_at: str | None = None
    completed_at: str | None = None

@dataclass(frozen=True, slots=True)
class RefreshReceipt:
    refresh_id: str
    project_id: str
    sections: tuple[str, ...]
    snapshot_id: str
    trace_id: str

class ProjectionRefreshStoreError(ValueError):
    pass

class FileRefreshStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path); self.states = self._load_states()
    def _load_states(self):
        if not self.path.is_file(): return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict): raise ValueError
            for key, value in raw.items():
                if set(value) != {"project_id", "sections", "status", "attempts", "diagnostic", "trace_id", "terminal", "receipt", "requested_at", "completed_at"}: raise ValueError
                if not isinstance(value["project_id"], str) or not value["project_id"] or not isinstance(value["sections"], list) or not value["sections"] or any(x not in {s.value for s in ProjectionSection} for x in value["sections"]): raise ValueError
                if value["status"] not in {s.value for s in RefreshStatus} | {"requested"} or type(value["attempts"]) is not int or value["attempts"] < 0: raise ValueError
                if value["terminal"] and (value["status"] != RefreshStatus.SUCCEEDED.value or value["receipt"] is None or value["completed_at"] is None): raise ValueError
                if not isinstance(value["trace_id"], str) or not value["trace_id"] or not isinstance(value["requested_at"], str) or not value["requested_at"] or (value["completed_at"] is not None and (not isinstance(value["completed_at"], str) or not value["completed_at"])): raise ValueError
                diagnostic = value["diagnostic"]
                if diagnostic is not None and (set(diagnostic) != {"code", "message"} or not isinstance(diagnostic["code"], str) or not diagnostic["code"] or not isinstance(diagnostic["message"], str) or not diagnostic["message"]): raise ValueError
                receipt = value["receipt"]
                if receipt is not None:
                    if set(receipt) != {"refresh_id", "project_id", "sections", "snapshot_id", "trace_id"} or receipt["refresh_id"] != key or receipt["project_id"] != value["project_id"] or receipt["sections"] != value["sections"] or receipt["trace_id"] != value["trace_id"]: raise ValueError
                    if any(not isinstance(receipt[x], str) or not receipt[x] for x in ("refresh_id", "project_id", "snapshot_id", "trace_id")) or not isinstance(receipt["sections"], list) or not receipt["sections"] or any(not isinstance(section, str) or not section or section not in {item.value for item in ProjectionSection} for section in receipt["sections"]): raise ValueError
                if not value["terminal"] and receipt is not None: raise ValueError
            return raw
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise ProjectionRefreshStoreError("projection_refresh_store_corrupt") from error
    def save(self, key: str, value: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True); lock = self.path.with_suffix(".lock")
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            latest = self._load_states()
            if key in latest and latest[key].get("terminal") and latest[key] != value: raise ProjectionRefreshStoreError("projection_refresh_terminal_conflict")
            latest[key] = value; self.states = latest; temp = self.path.with_suffix(".tmp")
            with temp.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(self.states, stream, ensure_ascii=False, sort_keys=True); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, self.path)
        except FileExistsError as error:
            raise ProjectionRefreshStoreError("projection_refresh_store_busy") from error
        finally:
            if "handle" in locals(): os.close(handle)
            try: os.remove(lock)
            except FileNotFoundError: pass

class ProjectionRefreshCoordinator:
    def __init__(self, builder: Callable[[str, frozenset[ProjectionSection], str], object], journal_path: str | Path | None = None, clock: Callable[[], str] | None = None) -> None:
        self._builder = builder
        self._requests: dict[str, tuple[str, frozenset[ProjectionSection], int, str]] = {}
        self._journal_path = Path(journal_path) if journal_path else None
        self._clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self._store = FileRefreshStateStore(self._journal_path) if self._journal_path else None
        if self._journal_path and self._journal_path.is_file():
            for key, row in self._store.states.items(): self._requests[key] = (row["project_id"], frozenset(ProjectionSection(x) for x in row["sections"]), row["attempts"], row["trace_id"])

    def refresh(self, project_id: str, sections: set[ProjectionSection], trace_id: str | None = None) -> RefreshResult:
        refresh_id = f"refresh-{uuid4().hex}"
        effective_trace_id = f"trace-{refresh_id}" if trace_id is None else trace_id
        if not isinstance(effective_trace_id, str) or not effective_trace_id.strip():
            raise ValueError("refresh_trace_id_invalid")
        self._requests[refresh_id] = (project_id, frozenset(sections), 0, effective_trace_id)
        self._record(refresh_id, "requested", None)
        return self.retry(refresh_id)

    def handle_event(self, project_id: str, event: ExecutionEvent) -> RefreshResult:
        return self.refresh(project_id, set(sections_for_event(event.event_type.value)))

    def retry(self, refresh_id: str) -> RefreshResult:
        if refresh_id not in self._requests:
            raise KeyError("refresh_id_not_found")
        project_id, sections, attempts, trace_id = self._requests[refresh_id]
        if self._store and self._store.states.get(refresh_id, {}).get("terminal"):
            state = self._store.states[refresh_id]
            receipt = None if state.get("receipt") is None else RefreshReceipt(refresh_id, state["project_id"], tuple(state["sections"]), state["receipt"]["snapshot_id"], state["receipt"]["trace_id"])
            return RefreshResult(refresh_id, RefreshStatus.SUCCEEDED, attempts, None, state.get("trace_id"), receipt, state.get("requested_at"), state.get("completed_at"))
        attempts += 1
        self._requests[refresh_id] = (project_id, sections, attempts, trace_id)
        try:
            value = self._builder(project_id, sections, refresh_id)
            snapshot_id = getattr(value, "snapshot_id", None)
            if not snapshot_id:
                raise RuntimeError("projection_refresh_receipt_missing")
        except Exception as error:
            requested = self._store.states[refresh_id].get("requested_at") if self._store else None
            result = RefreshResult(refresh_id, RefreshStatus.FAILED, attempts, RefreshDiagnostic("projection_refresh_failed", str(error)), self._trace(refresh_id), None, requested, self._clock())
            self._record(refresh_id, result.status.value, result.diagnostic, result); return result
        requested = self._store.states[refresh_id].get("requested_at") if self._store else None
        receipt = RefreshReceipt(refresh_id, project_id, tuple(sorted(item.value for item in sections)), snapshot_id, self._trace(refresh_id))
        result = RefreshResult(refresh_id, RefreshStatus.SUCCEEDED, attempts, None, self._trace(refresh_id), receipt, requested, self._clock()); self._record(refresh_id, result.status.value, None, result); return result

    def _trace(self, refresh_id: str) -> str:
        if self._store:
            stored_trace_id = self._store.states.get(refresh_id, {}).get("trace_id")
            if stored_trace_id:
                return stored_trace_id
        return self._requests[refresh_id][3]

    def _record(self, refresh_id: str, status: str, diagnostic: RefreshDiagnostic | None, result: RefreshResult | None = None) -> None:
        if not self._journal_path: return
        project_id, sections, attempts, _trace_id = self._requests[refresh_id]; self._journal_path.parent.mkdir(parents=True, exist_ok=True)
        receipt = None if result is None or result.receipt is None else {"refresh_id": result.receipt.refresh_id, "project_id": result.receipt.project_id, "sections": result.receipt.sections, "snapshot_id": result.receipt.snapshot_id, "trace_id": result.receipt.trace_id}
        requested_at = self._store.states.get(refresh_id, {}).get("requested_at") or self._clock()
        self._store.save(refresh_id, {"project_id": project_id, "sections": sorted(item.value for item in sections), "status": status, "attempts": attempts, "diagnostic": None if diagnostic is None else {"code": diagnostic.code, "message": diagnostic.message}, "trace_id": self._trace(refresh_id), "terminal": status == "succeeded", "receipt": receipt, "requested_at": requested_at, "completed_at": None if result is None else result.completed_at})

def sections_for_event(event_type: str) -> frozenset[ProjectionSection]:
    known_event_types = {item.value for item in EventType}
    return frozenset(ProjectionSection) if event_type in known_event_types else frozenset()
