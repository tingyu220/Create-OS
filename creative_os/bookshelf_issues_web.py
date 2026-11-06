"""异常处理的全局HTTP边界及数据入口门禁；拒绝时不装配Runtime。"""

import json
import re
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import UUID

from creative_os.bookshelf_web import send
from creative_os.project_issues import ProjectIssuesQuery
from creative_os.project_write_gate import operation_migration_lease
from creative_os.web_command_dto import decode_web_command, encode_command_result, WebCommandValidationError

ROUTES = {"/api/commands/" + name.replace("_", "-"): name for name in
          ("migrate_project_directory", "reconcile_project_directory", "continue_project_directory")}


def error(handler, status, code, message, **details):
    send(handler, status, {"error": {"code": code, "message": message, **details}})


def _query(raw, allowed):
    data = parse_qs(raw, keep_blank_values=True)
    if data.keys() - allowed or any(len(values) != 1 for values in data.values()):
        raise ValueError("parameters_invalid")
    return {key: values[0] for key, values in data.items()}


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("operation_id_invalid")
    return value


def handle_issues_get(handler):
    request = urlsplit(handler.path)
    match = re.fullmatch(r"/api/projects/migrations/([^/]+)", request.path)
    if request.path not in {"/api/projects/issues", "/api/projects/migration-preview"} and not match:
        return False
    try:
        service = handler.migration_service
        if service is None or handler.project_registry is None:
            raise OSError
        if request.path == "/api/projects/issues":
            query = _query(request.query, {"offset", "limit"})
            value = ProjectIssuesQuery(handler.project_registry.root).read(int(query.get("offset", "0")), int(query.get("limit", "20")))
        elif match:
            if request.query:
                raise ValueError
            value = service.status(_uuid(unquote(match[1])))
            if value is None:
                error(handler, 404, "migration_operation_not_found", "尚未找到该操作，请保留编号并重新读取状态。")
                return True
        else:
            query = _query(request.query, {"project_id"})
            if set(query) != {"project_id"}:
                raise ValueError
            value = service.preview(query["project_id"])
        send(handler, 200, value)
    except ValueError:
        error(handler, 400, "migration_query_invalid", "查询参数或作品状态无效，请重新检查。")
    except (OSError, RuntimeError, TypeError, KeyError):
        error(handler, 503, "migration_evidence_unavailable", "处理记录暂不可读，请保留现有详情，稍后重新检查。")
    return True


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_json_field")
        value[key] = item
    return value


def _non_json_constant(_value):
    raise ValueError("invalid_json_constant")


def result_status(result):
    if result.status.value == "accepted":
        return 202
    code = result.error.code
    if code in {"migration_evidence_unavailable", "migration_legacy_evidence_required"}:
        return 503
    if code in {"preview_stale", "preview_token_invalid", "project_migration_busy", "project_migration_active",
                "project_migration_state_unknown", "command_outcome_unknown", "continuation_no_invalid",
                "migration_idempotency_conflict", "migration_confirmation_required", "migration_needs_reconciliation"}:
        return 409
    return 422


def _handle_stale_preview(handler, command):
    """首次预检仅是提示；拒绝证明必须与首次迁移持相同外置互斥。"""
    service = handler.migration_service
    try:
        with operation_migration_lease(service.projects_root, command.target["project_id"]):
            if service.operations.read_operation(command.payload["operation_id"]) is not None:
                # 已有意图由原边界核对身份并重放，不再以旧预览推断未执行。
                result = service.commands.execute(command)
                send(handler, result_status(result), encode_command_result(result))
                return True
            try:
                service.previews.validate(command.payload["preview_token"], command.payload["operation_id"], command.payload["plan_fingerprint"])
            except ValueError:
                error(handler, 409, "preview_stale", "预览已过期或作品内容已变化，请重新检查。",
                      operation_id=command.payload["operation_id"], project_id=command.target["project_id"], operation_created=False)
                return True
    except ValueError as exc:
        if str(exc) != "project_migration_busy":
            raise
        error(handler, 409, "project_migration_busy", "目录状态正在处理，尚不能确认结果，请读取原操作状态。")
        return True
    # 锁内复查发现预览已恢复有效，交原边界重新取得所有权并执行检查。
    result = service.commands.execute(command)
    send(handler, result_status(result), encode_command_result(result))
    return True


def handle_issues_post(handler):
    request = urlsplit(handler.path)
    scoped = re.fullmatch(r"/p/[^/]+(/api/commands/[^/]+)", request.path)
    if scoped and scoped[1] in ROUTES:
        error(handler, 422, "migration_global_route_required", "目录处理只能从全局书架入口执行。")
        return True
    if request.path not in ROUTES:
        return False
    if handler.migration_service is None:
        error(handler, 503, "migration_service_unavailable", "目录处理暂不可用，作品仍保留在原位置。")
        return True
    if handler.headers.get_content_type() != "application/json":
        error(handler, 415, "unsupported_media_type", "只接受 application/json。")
        return True
    try:
        length = int(handler.headers.get("Content-Length", "-1"))
        if handler.headers.get("Transfer-Encoding") or request.query or not 0 < length <= 16384:
            raise ValueError
        raw = json.loads(handler.rfile.read(length).decode("utf-8"), object_pairs_hook=_object, parse_constant=_non_json_constant)
    except (ValueError, UnicodeError, RecursionError):
        error(handler, 400, "invalid_json", "请求体或长度无效，请重新打开预览。")
        return True
    try:
        command = decode_web_command(raw)
        if command.command_id != ROUTES[request.path]:
            error(handler, 422, "migration_command_route_mismatch", "命令与处理入口不匹配。")
            return True
        if command.command_id == "migrate_project_directory":
            service = handler.migration_service
            if service.operations.read_operation(command.payload["operation_id"]) is None:
                try:
                    plan = service.previews.validate(command.payload["preview_token"], command.payload["operation_id"], command.payload["plan_fingerprint"])
                except ValueError:
                    return _handle_stale_preview(handler, command)
                if plan["project_id"] != command.target["project_id"]:
                    error(handler, 422, "project_scope_mismatch", "预览与作品身份不匹配。")
                    return True
        result = handler.migration_service.commands.execute(command)
        send(handler, result_status(result), encode_command_result(result))
    except WebCommandValidationError:
        error(handler, 422, "validation_failed", "处理命令必须绑定原作品、完整预览和明确确认。")
    except (OSError, RuntimeError, ValueError, TypeError, KeyError):
        error(handler, 503, "migration_evidence_unavailable", "操作结果尚未确认，请保留操作编号并读取状态。")
    return True


def guard_data_request(handler, *, writable=False):
    """在select_project、旧默认适配器及任何可写接管之前执行。"""
    path = urlsplit(handler.path).path
    scoped = re.match(r"^/p/([^/]+)/(.*)$", path)
    if scoped:
        project_id, root = unquote(scoped[1]), None
    elif handler.routed_project_id and path.startswith("/api/"):
        # 路由后核对本请求已绑定的根；迁移后新请求会重新解析到新根。
        project_id = handler.routed_project_id
        root = getattr(getattr(handler, "writer_adapter", None), "project_root", None)
        if root is None:
            root = getattr(getattr(handler, "agent_runtime", None), "root", None)
    elif path.startswith("/api/") and not path.startswith("/api/projects"):
        project_id, root = handler.default_project_id, handler.default_project_root
    else:
        return False
    if project_id is None:
        return False
    try:
        if handler.migration_service is None:
            if not handler.migration_unavailable:
                return False
            raise RuntimeError
        state = handler.migration_service.availability(project_id, root, writable=writable)
        if state["available"]:
            return False
        error(handler, state["http_status"], state["reason_code"],
              "作品目录已整理，请从书架重新打开；旧默认入口需要重载服务。" if state["reload_required"] else "该作品正在目录处理或等待核对，暂时不能读取或写入。")
    except (RuntimeError, ValueError, OSError, TypeError):
        error(handler, 409 if writable else 503, "migration_evidence_unavailable", "作品目录状态暂不可确认，请返回书架重新检查。")
    return True
