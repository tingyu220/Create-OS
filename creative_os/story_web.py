"""故事 HTTP 契约；Query 不落盘，显式编辑与确认经过 CommandBoundary。"""

from dataclasses import asdict
import json
from urllib.parse import parse_qs, urlsplit

from creative_os.story_architecture_store import StoryArchitectureStore
from creative_os.agent_conversation_store import AgentConversationStore
from creative_os.project_directory import read_project_metadata, validated_project


def send(handler, status, value):
    handler._send_json(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), close=True)


def read_body(handler, *, max_bytes=100000):
    length = int(handler.headers.get("Content-Length", "-1"))
    if handler.headers.get_content_type() != "application/json" or not 0 < length <= max_bytes:
        raise ValueError("story_request_invalid")
    value = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("story_request_invalid")
    return value


def handle_story_get(handler):
    request = urlsplit(handler.path)
    if request.path not in {"/api/story", "/api/story/session", "/api/story/sources"}:
        return False
    try:
        runtime = handler.agent_runtime
        query = parse_qs(request.query, keep_blank_values=True)
        if request.path == "/api/story/sources":
            fields = {"project_id", "scope", "session_id", "job_id", "step"}
            if runtime is None or set(query) != fields or any(len(values) != 1 for values in query.values()):
                raise ValueError("story_scope_mismatch")
            if {key: query[key][0] for key in ("project_id", "scope", "session_id")} != {"project_id": runtime.project_id, "scope": "story", "session_id": runtime.story.session_id}:
                raise ValueError("story_scope_mismatch")
            job = runtime.get(query["job_id"][0])
            if job is None or job.scope != "story" or job.session_id != query["session_id"][0]:
                raise ValueError("story_scope_mismatch")
            step = query["step"][0]
            snapshot = next((item for item in job.step_snapshots if str(item["step"]) == step), None)
            if snapshot is None:
                raise ValueError("story_step_not_found")
            send(handler, 200, snapshot)
            return True
        if request.path == "/api/story/session":
            if runtime is None or query != {"project_id": [runtime.project_id], "scope": ["story"]}:
                raise ValueError("story_scope_mismatch")
            metadata = runtime.root / "project.json"
            data = json.loads(metadata.read_text(encoding="utf-8")) if metadata.exists() else {}
            send(handler, 200, {"project_id": runtime.project_id, "scope": "story", "session_id": runtime.story.session_id,
                                "idea": data.get("idea", ""), "title": data.get("title") or data.get("name") or runtime.project_id})
            return True
        if runtime is None or set(query) != {"project_id", "scope", "session_id"} or any(len(values) != 1 for values in query.values()):
            raise ValueError("story_scope_mismatch")
        view = runtime.story.view()
        if {key: values[0] for key, values in query.items()} != {key: view[key] for key in ("project_id", "scope", "session_id")}:
            raise ValueError("story_scope_mismatch")
        session = runtime.conversation(None)
        # 完整 step 快照不在轮询中返回；按指定 job 读取，避免正文反复传输。
        for job in session["jobs"]:
            job.pop("context_snapshot", None)
            job.pop("step_snapshots", None)
        send(handler, 200, {**session, **view})
    except (ValueError, OSError, TypeError) as error:
        handler._agent_error(error)
    return True


def handle_story_post(handler):
    route = urlsplit(handler.path).path
    if route == "/api/projects/create":
        try:
            if handler.project_registry is None:
                raise ValueError("project_creation_unavailable")
            raw = read_body(handler)
            if set(raw) != {"title", "idea", "operation_id"} or not isinstance(raw["operation_id"], str) or not raw["operation_id"].strip():
                raise ValueError("project_creation_invalid")
            root = handler.project_registry.creator.create(raw["title"], raw["idea"], operation_id=raw["operation_id"])
            project_id = read_project_metadata(handler.project_registry.root, root)["id"]
            if validated_project(handler.project_registry.root, project_id)[0] != root:
                raise ValueError("project_scope_mismatch")
            view = StoryArchitectureStore(root, project_id).view()
            send(handler, 201, {"project_id": project_id, "scope": "story", "session_id": view["session_id"]})
        except (ValueError, OSError, TypeError, KeyError) as error:
            handler._agent_error(ValueError(str(error)))
        return True
    if route not in {"/api/story/intents", "/api/story/retry", "/api/story/start-first-chapter"}:
        return False
    try:
        raw = read_body(handler)
        runtime = handler.agent_runtime
        fields = {"project_id", "scope", "session_id"}
        extras = {"instruction"} if route.endswith("intents") else {"job_id"} if route.endswith("retry") else {"confirmed_version", "confirmed_hash", "target_words", "tolerance_words"}
        allowed_fields = [fields | extras]
        if route.endswith("intents"):
            allowed_fields.append(fields | extras | {"requested_expert"})
        if runtime is None or set(raw) not in allowed_fields:
            raise ValueError("story_request_invalid")
        if {key: raw[key] for key in fields} != {"project_id": runtime.project_id, "scope": "story", "session_id": runtime.story.session_id}:
            raise ValueError("story_scope_mismatch")
        if route.endswith("intents"):
            runtime.validate_submit(raw["instruction"], None, session_id=raw["session_id"], requested_expert=raw.get("requested_expert"))
            job = handler._activate_project().submit(raw["instruction"], None, session_id=raw["session_id"], requested_expert=raw.get("requested_expert"))
        elif route.endswith("retry"):
            runtime.validate_retry(raw["job_id"], chapter_number=None, session_id=raw["session_id"])
            job = handler._activate_project().retry(raw["job_id"], chapter_number=None, session_id=raw["session_id"])
        else:
            confirmed = runtime.story.view()["confirmed"]
            if confirmed is None:
                raise ValueError("story_confirmation_required")
            if type(raw["confirmed_version"]) is not int or (confirmed["version"], confirmed["hash"]) != (raw["confirmed_version"], raw["confirmed_hash"]):
                raise ValueError("confirmed_conflict")
            instruction = "依据作者已确认的故事设定创作第一章，建立人物、开篇场景与核心矛盾。"
            runtime.validate_submit(instruction, 1, mode="act", target_words=raw["target_words"], tolerance_words=raw["tolerance_words"])
            runtime = handler._activate_project()
            from creative_os.domains.project_authority import project_authority_lock
            with project_authority_lock(runtime.root):
                confirmed = runtime.story.view()["confirmed"]
                if confirmed is None:
                    raise ValueError("story_confirmation_required")
                if type(raw["confirmed_version"]) is not int or (confirmed["version"], confirmed["hash"]) != (raw["confirmed_version"], raw["confirmed_hash"]):
                    raise ValueError("confirmed_conflict")
                job = runtime.submit(instruction, 1, mode="act", target_words=raw["target_words"], tolerance_words=raw["tolerance_words"])
        public = asdict(job)
        for key in ("context_snapshot", "step_snapshots"):
            public.pop(key, None)
        send(handler, 202, public)
    except (ValueError, OSError, TypeError, KeyError) as error:
        handler._agent_error(error)
    return True
