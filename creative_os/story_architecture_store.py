"""故事设定领域权威；原子聚合提交候选、确认历史与唯一 current 指针。"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from creative_os.domains.project_authority import project_authority_lock


def content_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        stream.flush()
        import os
        os.fsync(stream.fileno())
    temporary.replace(path)


def validate_content(blocks, questions, combat_plans=None):
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 40 or not isinstance(questions, list) or len(questions) > 50:
        raise ValueError("story_content_invalid")
    keys = set()
    for block in blocks:
        if not isinstance(block, dict) or set(block) != {"key", "title", "text"}:
            raise ValueError("story_block_invalid")
        if any(not isinstance(block[key], str) or not block[key].strip() for key in block):
            raise ValueError("story_block_invalid")
        if block["key"] in keys or len(block["key"]) > 80 or len(block["title"]) > 200:
            raise ValueError("story_block_invalid")
        keys.add(block["key"])
    if any(not isinstance(question, str) or not question.strip() for question in questions):
        raise ValueError("story_questions_invalid")
    from creative_os.combat_story_candidate import validate_combat_plans
    value = {"blocks": deepcopy(blocks), "open_questions": list(questions)}
    if combat_plans is not None:
        value["combat_plans"] = validate_combat_plans(combat_plans, blocks)
    if len(json.dumps(value, ensure_ascii=False)) > 48000:
        raise ValueError("story_content_budget_exceeded")
    return value


def render_story(value):
    plans = {plan["block_key"]: plan for plan in value.get("combat_plans", [])}
    sections = []
    for block in value["blocks"]:
        note = ""
        if plan := plans.get(block["key"]):
            note = "未来创作计划，不是已发生事实。\n"
            if content_hash(block) != plan["original_block_hash"]:
                note += ("作者修订" if plan["author_revised"] else "修订建议") + "：来源仅关联原专家建议，不为修订文字提供证据背书。\n"
        sections.append(f"## {block['title']}\n{note}{block['text']}")
    if value["open_questions"]:
        sections.append("## 未定问题（不得自行当成事实）\n" + "\n".join(f"- {question}" for question in value["open_questions"]))
    return "\n\n".join(sections)


class StoryArchitectureStore:
    def __init__(self, project_root, project_id):
        self.root, self.project_id = Path(project_root), project_id
        self.path = self.root / ".creative_os" / "story" / "architecture.json"
        # 无文件时也有稳定会话标识，使 Query 真正只读。
        self.session_id = "story-" + content_hash({"project_id": project_id})[:32]

    def _read(self):
        if not self.path.exists():
            return {"schema_version": 1, "project_id": self.project_id, "scope": "story", "session_id": self.session_id,
                    "revisions": [], "confirmed_versions": [], "current": 0, "operations": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data["project_id"] != self.project_id or data["session_id"] != self.session_id:
            raise ValueError("story_scope_mismatch")
        for item in data["revisions"] + data["confirmed_versions"]:
            from creative_os.combat_story_candidate import validate_combat_plans
            validate_combat_plans(item["content"].get("combat_plans", []), item["content"]["blocks"], self.project_id)
            if item["hash"] != content_hash(item["content"]) or item["text"] != render_story(item["content"]):
                raise ValueError("story_integrity_error")
        if data["current"] != len(data["confirmed_versions"]):
            raise ValueError("story_integrity_error")
        return data

    def view(self):
        data = self._read()
        return {key: deepcopy(data[key]) for key in ("project_id", "scope", "session_id")} | {
            "candidate": deepcopy(data["revisions"][-1]) if data["revisions"] else None,
            "confirmed": deepcopy(data["confirmed_versions"][-1]) if data["current"] else None}

    def _operation(self, data, session_id, operation_id, identity):
        if session_id != self.session_id:
            raise ValueError("session_scope_mismatch")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("operation_id_required")
        fingerprint = content_hash(identity)
        previous = data["operations"].get(operation_id)
        if previous and previous["fingerprint"] != fingerprint:
            raise ValueError("idempotency_conflict")
        return fingerprint, deepcopy(previous["result"]) if previous else None

    def propose(self, session_id, blocks, open_questions, *, expected_revision, actor, operation_id):
        content = validate_content(blocks, open_questions)
        if type(expected_revision) is not int or expected_revision < 0 or not isinstance(actor, str) or not actor.strip():
            raise ValueError("story_revision_invalid")
        with project_authority_lock(self.root):
            data = self._read()
            from creative_os.combat_story_candidate import reconcile_combat_plans
            base = data["revisions"][-1] if data["revisions"] else data["confirmed_versions"][-1] if data["current"] else None
            # 幂等指纹只绑定输入；来源关联由锁内当前版本保留，重试不受后续编辑干扰。
            fingerprint, previous = self._operation(data, session_id, operation_id, {"action": "propose", "content": content, "expected_revision": expected_revision, "actor": actor})
            if previous is not None:
                return previous
            plans = reconcile_combat_plans(base["content"], blocks, actor) if base and "combat_plans" in base["content"] else None
            content = validate_content(blocks, open_questions, plans)
            return self._append_candidate(data, content, expected_revision, actor, operation_id, fingerprint)

    def _append_candidate(self, data, content, expected_revision, actor, operation_id, fingerprint):
        """调用方持有项目锁，候选、机器关联与幂等回执同一次原子提交。"""
        if expected_revision != len(data["revisions"]):
            raise ValueError("candidate_conflict")
        result = {"revision": expected_revision + 1, "hash": content_hash(content), "content": content,
                  "text": render_story(content), "actor": actor, "created_at": datetime.now(timezone.utc).isoformat()}
        data["revisions"].append(result)
        data["operations"][operation_id] = {"fingerprint": fingerprint, "result": result}
        atomic_json(self.path, data)
        return deepcopy(result)

    def confirm(self, session_id, revision, candidate_hash, *, expected_confirmed_version, actor, operation_id):
        if actor != "作者":
            raise ValueError("story_author_required")
        if type(revision) is not int or revision <= 0 or type(expected_confirmed_version) is not int or expected_confirmed_version < 0 or not isinstance(actor, str) or not actor.strip():
            raise ValueError("story_confirmation_invalid")
        with project_authority_lock(self.root):
            data = self._read()
            fingerprint, previous = self._operation(data, session_id, operation_id, {"action": "confirm", "revision": revision, "hash": candidate_hash, "expected_confirmed_version": expected_confirmed_version, "actor": actor})
            if previous is not None:
                return previous
            candidate = data["revisions"][-1] if data["revisions"] else None
            if candidate is None or (candidate["revision"], candidate["hash"]) != (revision, candidate_hash):
                raise ValueError("candidate_conflict")
            if data["current"] != expected_confirmed_version:
                raise ValueError("confirmed_conflict")
            result = {**deepcopy(candidate), "version": data["current"] + 1, "confirmed_by": actor,
                      "confirmed_at": datetime.now(timezone.utc).isoformat(), "operation_id": operation_id,
                      "project_id": self.project_id, "session_id": session_id}
            data["confirmed_versions"].append(result)
            data["current"] = result["version"]
            data["operations"][operation_id] = {"fingerprint": fingerprint, "result": result}
            atomic_json(self.path, data)
            return deepcopy(result)
