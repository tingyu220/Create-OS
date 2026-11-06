"""独立候选及冻结快照；不执行模型、不写正式稿。"""

from copy import deepcopy
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

from creative_os.domains.project_authority import project_authority_lock
from creative_os.writer_draft_store import WriterDraftStore
from creative_os.workspace_command import FileCommandResultStore, CommandRecordState
from creative_os.project_write_gate import project_write_method


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def review_identity(review):
    """仅绑定原审阅的不可变身份，不把可续写的回执检查点混入指纹。"""
    identity = {key: review[key] for key in ("identity", "actor", "feedback", "job_id")}
    return {"feedback_id": review["feedback"]["id"],
            "review_hash": content_hash(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")))}


def find_review(proposal, payload):
    reviews = ([proposal["review"]] if proposal.get("review") else []) + list(reversed(proposal.get("review_attempts", [])))
    return next((review for review in reviews if review_identity(review) == payload), None)


class AgentProposalStore:
    def __init__(self, project_root: Path, project_id: str) -> None:
        self.project_root = project_root
        self.project_id = project_id
        self.root = project_root / ".creative_os" / "agent" / "proposals"
        self.drafts = WriterDraftStore(project_root)

    def baseline(self, chapter: int) -> dict:
        """调用方持有项目锁，版本和正文一次冻结。"""
        current = self.drafts.current(chapter)
        if current:
            version, content = current
            return {"source": "draft", "version": version.version, "hash": content_hash(content),
                    "ref": f"writer-draft:{chapter}:{version.version}", "content": content}
        formal = self.project_root / "production" / "final_chapters" / f"chapter_{chapter:03d}.md"
        content = formal.read_text(encoding="utf-8") if formal.exists() else ""
        return {"source": "formal" if formal.exists() else "empty", "version": None,
                "hash": content_hash(content), "ref": f"canonical:chapter-{chapter:03d}" if formal.exists() else f"empty:chapter-{chapter:03d}",
                "content": content}

    def create(self, job, message_id: str) -> dict:
        with project_authority_lock(self.project_root):
            parent = self.read(job.parent_proposal_id) if job.parent_proposal_id else None
            base = deepcopy(parent["base"]) if parent else self.baseline(job.chapter_number)
            selected = parent["result"] if parent and job.proposal_source == "candidate" else base
            proposal_id = f"proposal-{uuid4().hex}"
            proposal = {"schema_version": 1, "proposal_id": proposal_id,
                        "project_id": self.project_id, "chapter_number": job.chapter_number,
                        "session_id": job.session_id, "task_id": job.job_id, "message_id": message_id,
                        "decision_id": job.decision_id, "parent_proposal_id": job.parent_proposal_id,
                        "created_at": datetime.now(timezone.utc).isoformat(), "status": "generating",
                        "base": base, "input": deepcopy(selected), "result": None, "review": None}
            # 引用标识持久快照，不再指向会变化的当前稿件。
            proposal["base"]["source_ref"] = base["ref"]
            proposal["base"]["ref"] = f"{proposal_id}#base"
            self.write(proposal)
            return proposal

    def complete(self, proposal_id: str, content: str, *, word_assessment: dict | None = None) -> dict:
        if not content.strip():
            raise ValueError("proposal_content_empty")
        with project_authority_lock(self.project_root):
            proposal = self.read(proposal_id)
            proposal["result"] = {"ref": f"{proposal_id}#result", "hash": content_hash(content), "content": content}
            proposal["status"] = "pending"
            if word_assessment is not None:
                proposal["word_assessment"] = deepcopy(word_assessment)
            self.write(proposal)
            return proposal

    def fail_unfinished(self, proposal_id: str, error: str) -> None:
        with project_authority_lock(self.project_root):
            proposal = self.read(proposal_id)
            if proposal["result"] is None:
                proposal["status"] = "failed"
                proposal["error"] = error
                self.write(proposal)

    def read(self, proposal_id: str) -> dict:
        if not isinstance(proposal_id, str) or not re.fullmatch(r"proposal-[a-f0-9]{32}", proposal_id):
            raise ValueError("proposal_id_invalid")
        proposal = json.loads((self.root / f"{proposal_id}.json").read_text(encoding="utf-8"))
        if proposal["project_id"] != self.project_id:
            raise ValueError("proposal_scope_mismatch")
        return proposal

    @project_write_method("project_root")
    def write(self, proposal: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{proposal['proposal_id']}.json"
        temporary = path.with_suffix(f".{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def view(self, proposal_id: str) -> dict:
        # 提案文件原子替换，正文及冻结基线同文件；Query 不创建项目锁文件。
        proposal = self.public(self.read(proposal_id))
        before = proposal["base"]["content"]
        after = (proposal["result"] or {}).get("content", "")
        proposal["diff"] = "\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                                      fromfile="冻结原稿", tofile="候选提案", lineterm=""))
        return proposal

    def public(self, proposal):
        result = deepcopy(proposal)
        commands = FileCommandResultStore(self.project_root)
        reviews = ([proposal["review"]] if proposal.get("review") else []) + list(reversed(proposal.get("review_attempts", [])))
        for review in reviews:
            pending = any((record := commands.read(command["key"])) is not None and record.state is CommandRecordState.RESERVED
                          for command in review["commands"])
            if (review is proposal.get("review") and proposal["status"] == "reviewing") or pending:
                result["review_recovery"] = {"required": True, "actor": review["actor"], "payload": review_identity(review),
                                             "action": review["identity"]["action"], "reason": review["identity"]["reason"]}
                break
        return result
