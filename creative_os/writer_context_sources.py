"""当次模型输入的只读快照；引用只作说明，绝不转换成文件读取路径。"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import re


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ContextCapture:
    """在组装消息时登记同一字符串，在适配器调用前核对实际消息位置。"""

    def __init__(self):
        self.entries = []

    def add(self, label, ref, content=None, *, version=None, reason=None, original=None, start=0, message_start=None, **metadata):
        entry = {"label": label, "source_ref": ref, "version": version,
                 "usage": "included" if content is not None else "not_in_model", "reason": reason, **metadata}
        if content is not None:
            original = content if original is None else original
            entry.update(content_snapshot=content, content_hash=digest(content),
                         original_hash=digest(original), original_chars=len(original),
                         excerpt_start=start, excerpt_end=start + len(content),
                         _message_start=message_start,
                         truncated=start != 0 or len(content) != len(original))
        self.entries.append(entry)

    def snapshot(self, job, messages, *, content_offset=0):
        entries = deepcopy(self.entries)
        for entry in entries:
            if entry["usage"] == "included":
                text = entry["content_snapshot"]
                # 只核对拼接时登记的段边界；相同文本可能属于不同来源，禁止搜索定位。
                index = len(messages) - 1
                relative_start = entry.pop("_message_start")
                if type(relative_start) is not int or relative_start < 0:
                    raise ValueError("context_snapshot_location_missing")
                start = content_offset + relative_start
                if messages[index].content[start:start + len(text)] != text:
                    raise ValueError("context_snapshot_message_mismatch")
                entry["message_location"] = {"index": index, "role": messages[index].role,
                                             "start": start, "end": start + len(text)}
        # 完整消息也供核对系统提示、历史对话与请求包装，没有隐含摘要替代原文。
        for index, message in enumerate(messages):
            entries.append({"label": "系统提示" if index == 0 else ("本次完整请求" if index == len(messages) - 1 else f"历史对话消息 {index}"),
                            "source_ref": f"message:{index}", "version": "request-v1", "usage": "included",
                            "content_snapshot": message.content, "content_hash": digest(message.content),
                            "truncated": False, "original_chars": len(message.content),
                            "excerpt_start": 0, "excerpt_end": len(message.content),
                            "message_location": {"index": index, "role": message.role, "start": 0, "end": len(message.content)}})
        for index, entry in enumerate(entries):
            entry["source_id"] = f"source-{job.job_id[6:]}-{index + 1:04d}"
        return {"schema_version": 1, "project_id": job.project_id, "chapter_number": job.chapter_number, "scope": job.scope,
                "session_id": job.session_id, "job_id": job.job_id,
                "captured_at": datetime.now(timezone.utc).isoformat(), "delivery": "adapter_call_started",
                "sources": entries}


class CapturingModelAdapter:
    """只观察既有调用，不改消息或模型参数；异常不推断远端是否收到。"""

    def __init__(self, client, capture):
        self.client, self.capture = client, capture

    def complete(self, messages, **kwargs):
        self.capture(messages)
        return self.client.complete(messages, **kwargs)


class WriterContextSourceQuery:
    def __init__(self, runtime):
        self.runtime = runtime

    def read(self, *, project_id, chapter_number, session_id, job_id, source_id=None):
        if (project_id != self.runtime.project_id or type(chapter_number) is not int or chapter_number <= 0
                or not isinstance(job_id, str) or not re.fullmatch(r"agent-[a-f0-9]{32}", job_id)):
            raise ValueError("context_scope_mismatch")
        job = self.runtime.get(job_id)
        if job is None or (job.project_id, job.chapter_number, job.session_id) != (project_id, chapter_number, session_id):
            raise ValueError("context_scope_mismatch")
        snapshot = deepcopy(job.context_snapshot)
        scope = {"project_id": project_id, "chapter_number": chapter_number, "session_id": session_id, "job_id": job_id}
        if snapshot is None:
            snapshot = {**scope, "schema_version": 1, "delivery": "unavailable", "sources": self._legacy(job)}
        if any(snapshot.get(key) != value for key, value in scope.items()):
            raise ValueError("context_scope_mismatch")
        if source_id is not None:
            if not isinstance(source_id, str) or not re.fullmatch(r"source-[a-f0-9]{32}-\d{4,}", source_id):
                raise ValueError("context_source_invalid")
            source = next((item for item in snapshot["sources"] if item["source_id"] == source_id), None)
            if source is None:
                raise ValueError("context_source_not_found")
            return {**scope, "delivery": snapshot["delivery"], "captured_at": snapshot.get("captured_at"), "source": source}
        return {**scope, "schema_version": 1, "delivery": snapshot["delivery"], "captured_at": snapshot.get("captured_at"),
                "sources": [{key: item[key] for key in ("source_id", "label", "usage", "reason", "version", "truncated") if key in item}
                            for item in snapshot["sources"]]}

    @staticmethod
    def _legacy(job):
        entries = [{"label": "章节与请求内容", "usage": "unavailable", "reason": "legacy_snapshot_missing"}]
        # 旧经验已经有真实片段快照，复用证据；失败任务不据此声称已送达模型。
        trace = job.experience_context or {}
        for selected in trace.get("selected", []):
            entries.append({**deepcopy(selected), "label": "作者经验（旧任务记录）", "usage": "recorded",
                            "reason": "legacy_selection_only", "experience": deepcopy(selected)})
        for excluded in trace.get("excluded", []):
            entries.append({**deepcopy(excluded), "label": "作者经验（未入模）", "usage": "not_in_model"})
        for index, entry in enumerate(entries):
            entry["source_id"] = f"source-{job.job_id[6:]}-{index + 1:04d}"
        return entries
