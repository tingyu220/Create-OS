from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MemoryUsageRecord:
    run_id: str
    task_id: str
    context_fingerprint: str
    memory_ids: tuple[str, ...]
    issues_before: tuple[str, ...]
    issues_after: tuple[str, ...]
    human_rating: int | None = None
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True, slots=True)
class MemoryEffect:
    uses: int
    issue_delta: int
    average_human_rating: float | None


def record_usage(path: str | Path, record: MemoryUsageRecord) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")


def summarize_effects(path: str | Path) -> dict[str, MemoryEffect]:
    target = Path(path)
    if not target.exists():
        return {}
    aggregates: dict[str, dict[str, object]] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        delta = len(payload["issues_after"]) - len(payload["issues_before"])
        for memory_id in payload["memory_ids"]:
            current = aggregates.setdefault(memory_id, {"uses": 0, "delta": 0, "ratings": []})
            current["uses"] = int(current["uses"]) + 1
            current["delta"] = int(current["delta"]) + delta
            if payload.get("human_rating") is not None:
                ratings = current["ratings"]
                assert isinstance(ratings, list)
                ratings.append(int(payload["human_rating"]))

    effects: dict[str, MemoryEffect] = {}
    for memory_id, values in aggregates.items():
        ratings = values["ratings"]
        assert isinstance(ratings, list)
        effects[memory_id] = MemoryEffect(
            uses=int(values["uses"]),
            issue_delta=int(values["delta"]),
            average_human_rating=(sum(ratings) / len(ratings)) if ratings else None,
        )
    return effects
