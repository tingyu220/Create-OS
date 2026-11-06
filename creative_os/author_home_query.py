"""作者首页只读摘要：真实稿件与待确认候选分计，不启动运行时或读取投影。"""

from datetime import datetime, timezone
import json
from pathlib import Path
import re

from creative_os.agent_conversation_store import AgentConversationStore
from creative_os.agent_proposal_store import AgentProposalStore
from creative_os.writer_draft_store import WriterDraftStore
from creative_os.workspace_command import CommandStoreError


def heading_title(text):
    first = text.partition("\n")[0][:256].strip()
    match = re.fullmatch(r"(?:#{1,6}\s*)?(第\s*[0-9一二三四五六七八九十百千万〇零]+\s*章.*)", first)
    return match[1].strip() if match else None


class AuthorHomeQuery:
    def __init__(self, project_root: str | Path, project_id: str):
        self.root = Path(project_root)
        self.project_id = project_id

    def read_json(self) -> bytes:
        return json.dumps(self.read(), ensure_ascii=False).encode("utf-8")

    def read(self) -> dict:
        chapters, attention, notices, issues = {}, [], [], []
        counts = {"formal": 0, "draft": 0, "candidate": 0}

        def chapter(number, path):
            updated = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            item = chapters.setdefault(number, {"chapter_number": number, "title": f"第 {number} 章",
                                               "has_formal": False, "has_draft": False,
                                               "pending_candidates": 0, "updated_at": updated})
            item["updated_at"] = max(item["updated_at"], updated)
            return item

        def collect(kind, label, action):
            try:
                action()
            except (OSError, ValueError, KeyError, TypeError, CommandStoreError):
                counts[kind] = None
                notices.append(f"部分{label}暂时无法读取，请查看运行诊断。")
                issues.append({"code": f"{kind}_unavailable", "message": notices[-1], "source": kind})

        title = self.project_id
        try:
            metadata_path = self.root / "project.json"
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata.get("id", self.project_id) != self.project_id:
                    raise ValueError("project_scope_mismatch")
                title = metadata.get("title") or metadata.get("name") or self.project_id
        except (OSError, ValueError, AttributeError):
            notices.append("书名暂时无法读取，已显示项目名称。")

        def formal():
            for path in sorted((self.root / "production" / "final_chapters").glob("chapter_*.md")):
                match = re.fullmatch(r"chapter_(\d+)", path.stem)
                if match and int(match[1]) > 0 and path.is_file():
                    item = chapter(int(match[1]), path)
                    item["has_formal"] = True
                    with path.open(encoding="utf-8") as stream:
                        item["title"] = heading_title(stream.readline(256)) or item["title"]
                    counts["formal"] += 1

        drafts = WriterDraftStore(self.root)

        def draft():
            for path in sorted(drafts.root.glob("chapter_*.jsonl")):
                match = re.fullmatch(r"chapter_(\d+)", path.stem)
                current = drafts.current(int(match[1])) if match and int(match[1]) > 0 else None
                if current is not None:
                    item = chapter(int(match[1]), path)
                    item["has_draft"] = True
                    item["title"] = heading_title(current[1]) or item["title"]
                    counts["draft"] += 1

        proposals = AgentProposalStore(self.root, self.project_id)

        def candidate():
            for path in sorted(proposals.root.glob("proposal-*.json")):
                value = proposals.public(proposals.read(path.stem))
                number = value["chapter_number"]
                if type(number) is not int or number <= 0:
                    raise ValueError("proposal_chapter_invalid")
                needs_recovery = value.get("review_recovery", {}).get("required", False)
                if (value["status"] in {"pending", "reviewing"} or needs_recovery) and value.get("result"):
                    chapter(number, path)["pending_candidates"] += 1
                    counts["candidate"] += 1
                    if value["status"] == "reviewing" or needs_recovery:
                        attention.append({"kind": "reviewing", "chapter_number": number,
                                          "message": "候选确认尚未完成，请打开章节核对处理结果。"})

        collect("formal", "正式稿", formal)
        collect("draft", "工作稿", draft)
        collect("candidate", "候选", candidate)
        sessions = AgentConversationStore(self.root, self.project_id)
        try:
            for path in sorted(sessions.root.glob("*.json")):
                match = re.fullmatch(r"chapter_(\d+)", path.stem)
                if path.stem != "story" and not match:
                    continue
                number = int(match[1]) if match else None
                stored_jobs = sessions.read(number)["jobs"]
                if not isinstance(stored_jobs, dict):
                    raise ValueError("session_jobs_invalid")
                jobs = list(stored_jobs.values())
                if any(not isinstance(job, dict) or not isinstance(job.get("status"), str) or not job["status"]
                       or not isinstance(job.get("updated_at", ""), str) for job in jobs):
                    raise ValueError("session_job_invalid")
                if not jobs:
                    continue
                latest = max(jobs, key=lambda item: item.get("updated_at", ""))
                if latest["status"] != "completed":
                    failed = latest["status"] == "failed"
                    attention.append({"kind": "failed" if failed else "running", "chapter_number": number,
                                      "message": "上次创作未完成，请打开查看原因并重试。" if failed else "创作任务正在处理中，可打开查看进展。"})
        except (OSError, ValueError, KeyError, TypeError):
            notices.append("部分创作任务状态暂时无法读取，请查看运行诊断。")
            issues.append({"code": "session_unavailable", "message": notices[-1], "source": "session"})

        ordered = sorted(chapters.values(), key=lambda item: (item["updated_at"], item["chapter_number"]), reverse=True)
        # 有待确认候选时先处理候选，其次继续已有工作稿，再打开正式章节。
        resume = next((item for item in ordered if item["pending_candidates"]), None)
        resume = resume or next((item for item in ordered if item["has_draft"]), None)
        resume = resume or (ordered[0] if ordered else None)
        return {"project_id": self.project_id, "title": title, "status": "partial" if notices else "fresh", "issues": issues,
                "counts": counts, "chapters": ordered, "attention": attention, "notices": notices,
                "resume": None if resume is None else {"chapter_number": resume["chapter_number"],
                    "source": "candidate" if resume["pending_candidates"] else "draft" if resume["has_draft"] else "formal"}}
