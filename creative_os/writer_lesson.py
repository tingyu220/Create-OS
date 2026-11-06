"""Writer 经验候选：只消费可核对的作者反馈，不把审阅结果推断成规则。"""

from dataclasses import asdict, replace
import hashlib
import json

from creative_os.memory.feedback import FeedbackStore
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.store import JsonMemoryStore
from creative_os.workspace_command import CommandRejectedError


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class WriterLessonService:
    def __init__(self, runtime):
        self.runtime = runtime
        self.root = runtime.root

    @property
    def store(self):
        return JsonMemoryStore(self.root / ".creative_os" / "memory")

    def feedback(self, target):
        if (set(target) != {"project_id", "chapter_number", "session_id", "feedback_id"}
                or target["project_id"] != self.runtime.project_id
                or type(target["chapter_number"]) is not int or target["chapter_number"] < 1
                or any(not isinstance(target[key], str) or not target[key].strip() for key in ("session_id", "feedback_id"))):
            raise CommandRejectedError("lesson_scope_mismatch", "经验目标的项目、章节或会话不匹配。")
        records = [item for item in FeedbackStore(self.root, initialize=False).list() if item.id == target["feedback_id"]]
        if len(records) != 1:
            raise CommandRejectedError("feedback_not_found", "找不到唯一的持久作者反馈。")
        feedback = records[0]
        if any(getattr(feedback, key) != target[key] for key in ("project_id", "chapter_number", "session_id")) or not feedback.proposal_id:
            raise CommandRejectedError("lesson_scope_mismatch", "反馈归属不匹配。")
        try:
            proposal = self.runtime.proposals.read(feedback.proposal_id)
            expected = proposal["review"]["feedback"]
            if (feedback.to_dict() != expected or proposal["status"] not in {"accepted", "rejected", "cancelled", "revised"}
                    or not proposal["review"]["actor"].strip() or proposal["review"]["actor"].strip().casefold() == "system"
                    or any(proposal[key] != target[key] for key in ("project_id", "chapter_number", "session_id"))
                    or proposal["task_id"] != feedback.task_id or proposal["message_id"] != feedback.message_id
                    or proposal["base"]["hash"] != digest(proposal["base"]["content"])
                    or proposal["result"]["hash"] != digest(proposal["result"]["content"])):
                raise ValueError("feedback_evidence_mismatch")
        except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
            raise CommandRejectedError("feedback_evidence_mismatch", "反馈与提案证据不一致，不能提炼经验。") from error
        return feedback, proposal

    def candidate(self, target, payload):
        feedback, proposal = self.feedback(target)
        content = payload["content"].strip()
        scope = payload["range"]
        body = {"schema_version": 1, "kind": "writer_lesson", "content": content,
                "range": scope, "chapter_number": feedback.chapter_number,
                "feedback": feedback.to_dict(), "feedback_actor": proposal["review"]["actor"], "proposal_id": proposal["proposal_id"],
                "base": {key: proposal["base"][key] for key in ("source", "version", "ref", "hash")},
                "result": {key: proposal["result"][key] for key in ("ref", "hash")}}
        item_id = "writer-lesson-" + digest(canonical({"target": target, "title": payload["title"].strip(), "body": body}))[:24]
        item = MemoryItem.new_candidate(
            id=item_id, kind=MemoryKind.EXPERIENCE, scope=MemoryScope.PROJECT,
            scope_id=self.runtime.project_id, title=payload["title"].strip(), content=canonical(body),
            evidence=(MemoryEvidence("feedback", feedback.id, feedback.reason),
                      MemoryEvidence("writer_proposal", proposal["proposal_id"], proposal["result"]["hash"]),
                      MemoryEvidence("writer_base", proposal["base"]["ref"], proposal["base"]["hash"])),
            applicability=("writing",), tags={"writer_lesson", "lesson", "novel"}, confidence=0.7)
        # 相同反馈、经验和范围产生完全一致的候选，允许中断后的原请求续办。
        return replace(item, created_at=feedback.created_at, updated_at=feedback.created_at)

    def scoped_item(self, target, item_id):
        try:
            item = self.store.get_strict(item_id)
            body = json.loads(item.content)
            if (item.kind != MemoryKind.EXPERIENCE or item.scope != MemoryScope.PROJECT
                    or item.scope_id != self.runtime.project_id or "writer_lesson" not in item.tags
                    or body["feedback"]["id"] != target["feedback_id"]
                    or any(body["feedback"][key] != target[key] for key in ("project_id", "chapter_number", "session_id"))):
                raise ValueError("lesson_scope_mismatch")
            return item
        except (KeyError, TypeError, ValueError) as error:
            raise CommandRejectedError("lesson_scope_mismatch", "经验不存在或来源归属不匹配。") from error

    def query(self, chapter):
        feedback = [item.to_dict() for item in FeedbackStore(self.root, initialize=False).list()
                    if item.project_id == self.runtime.project_id and item.chapter_number == chapter and item.proposal_id]
        lessons = []
        if (self.root / ".creative_os/memory/items").exists():
            for item in JsonMemoryStore(self.root / ".creative_os" / "memory", initialize=False).list():
                if (item.scope != MemoryScope.PROJECT or item.kind != MemoryKind.EXPERIENCE
                        or item.scope_id != self.runtime.project_id or "writer_lesson" not in item.tags):
                    continue
                body = json.loads(item.content)
                if body["chapter_number"] != chapter and body["range"] != "project":
                    continue
                lessons.append({**asdict(item), "tags": sorted(item.tags), "detail": body})
        return {"project_id": self.runtime.project_id, "chapter_number": chapter,
                "feedback": feedback, "lessons": lessons}
