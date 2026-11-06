"""书架与最近位置的 HTTP 边界，与创作 Runtime 装配保持分离。"""

import json
import re
from urllib.parse import parse_qs, urlsplit, unquote

from creative_os.project_catalog import ProjectCatalog
from creative_os.project_registry import validated_project
from creative_os.workspace_recent_store import WorkspaceRecentStore, location_url


def send(handler, status, value):
    handler._send_json(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), close=True)


def handle_bookshelf_get(handler):
    request = urlsplit(handler.path)
    entry = re.fullmatch(r"/p/([^/]+)/?", request.path)
    if entry and handler.project_registry is not None:
        try:
            project_id = unquote(entry[1])
            project = ProjectCatalog(handler.project_registry.root).project(project_id)
            location = project["default_location"]
            query = parse_qs(request.query, keep_blank_values=True)
            if query:
                if query.keys() - {"chapter", "source"} or "chapter" not in query or any(len(values) != 1 for values in query.values()):
                    raise ValueError("project_entry_invalid")
                location = {"page": "writer", "chapter_number": int(query["chapter"][0]), "source": query.get("source", ["auto"])[0]}
            else:
                try:
                    recent = next((row for row in WorkspaceRecentStore(handler.project_registry.root).read() if row["project_id"] == project_id), None)
                    location = recent or location
                except ValueError:
                    pass  # UI 位置损坏不阻断作品；书内 POST 会显示非阻塞的记录错误。
            destination = location_url(project_id, location)
            handler.send_response(302); handler.send_header("Location", destination)
            handler.send_header("Content-Length", "0"); handler.end_headers()
        except (OSError, ValueError, TypeError):
            send(handler, 404, {"error": {"code": "project_entry_unavailable", "message": "作品入口暂不可用，请返回书架重新选择。"}})
        return True
    if request.path not in {"/api/projects", "/api/projects/recent"}:
        return False
    try:
        if handler.project_registry is None:
            raise OSError("project_catalog_unavailable")
        if request.path == "/api/projects/recent":
            if request.query:
                raise ValueError("workspace_recent_parameters_invalid")
            items, warnings = [], []
            records = WorkspaceRecentStore(handler.project_registry.root).read()
            for row in records[:20]:
                try:
                    _, metadata = validated_project(handler.project_registry.root, row["project_id"])
                    title = metadata.get("title") or metadata.get("name") or row["project_id"]
                    items.append({**row, "title": title, "url": location_url(row["project_id"], row)})
                except (OSError, ValueError):
                    warnings.append({"project_id": row["project_id"], "message": "最近记录中的作品暂不可用。"})
            send(handler, 200, {"items": items, "positions": {row["project_id"]: row for row in records}, "warnings": warnings})
            return True
        query = parse_qs(request.query, keep_blank_values=True)
        if query.keys() - {"query", "offset", "limit"} or any(len(values) != 1 for values in query.values()):
            raise ValueError("project_catalog_parameters_invalid")
        result = ProjectCatalog(handler.project_registry.root).list_projects(query.get("query", [""])[0],
                    offset=int(query.get("offset", ["0"])[0]), limit=int(query.get("limit", ["20"])[0]))
        send(handler, 200, result)
    except ValueError as error:
        code = "workspace_recent_corrupt" if str(error) == "workspace_recent_corrupt" else "project_catalog_parameters_invalid"
        send(handler, 503 if code == "workspace_recent_corrupt" else 400, {"error": {"code": code, "message": "最近记录损坏，请检查工作区记录；现有作品仍可打开。" if code == "workspace_recent_corrupt" else "作品目录查询参数无效。"}})
    except OSError:
        send(handler, 503, {"error": {"code": "project_catalog_unavailable", "message": "作品目录暂时无法读取，请稍后重试。"}})
    return True


def handle_bookshelf_post(handler):
    if urlsplit(handler.path).path != "/api/projects/recent":
        return False
    try:
        if handler.project_registry is None:
            raise OSError("project_catalog_unavailable")
        length = int(handler.headers.get("Content-Length", "-1"))
        if handler.headers.get_content_type() != "application/json" or not 0 < length <= 4096:
            raise ValueError("workspace_recent_request_invalid")
        raw = json.loads(handler.rfile.read(length).decode("utf-8"))
        if not isinstance(raw, dict) or not {"project_id", "page", "chapter_number"} <= raw.keys() or raw.keys() - {"project_id", "page", "chapter_number", "source"}:
            raise ValueError("workspace_recent_request_invalid")
        record = WorkspaceRecentStore(handler.project_registry.root).record(**raw)
        send(handler, 200, {"record": record})
    except (ValueError, TypeError) as error:
        corrupt = str(error) == "workspace_recent_corrupt"
        send(handler, 503 if corrupt else 400, {"error": {"code": "workspace_recent_corrupt" if corrupt else "workspace_recent_request_invalid", "message": "最近位置未记录，当前创作仍可继续。"}})
    except OSError:
        send(handler, 503, {"error": {"code": "workspace_recent_unavailable", "message": "最近位置暂不可写，当前创作仍可继续。"}})
    return True
