"""持久化发布浏览器工作台（仅供隔离 Fake 浏览器验证）。

该模块只保存浏览器会话引用和发布上下文，不保存密码、Cookie 或页面凭据。
真实平台接入仍由平台适配器负责；工作台负责生命周期、暂停和重连核对。
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


class BrowserWorkbenchError(RuntimeError):
    """工作台状态或浏览器连接不满足操作前置条件。"""


class ReconnectionMismatch(BrowserWorkbenchError):
    """重连时页面身份、目标或正文哈希不一致。"""


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class BrowserSessionState:
    platform: str
    session_id: str
    page_id: str
    page_url: str | None = None
    work_id: str | None = None
    work_title: str | None = None
    chapter_number: int | None = None
    platform_work_title: str | None = None
    platform_chapter_number: int | None = None
    current_step: str | None = None
    operation_id: str | None = None
    content_sha256: str | None = None
    status: str = "connected"
    pause_mode: str | None = None
    pause_reason: str | None = None
    login_state: str = "unknown"
    connected: bool = True
    reconnect_verified: bool = False
    resume_required: bool = False
    panel_side: str = "right"
    browser_window: str = "persistent"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """稳定序列化；显式过滤任何可能误传的凭据字段。"""
        raw = asdict(self)
        raw.pop("metadata", None)
        # 只输出约定字段，避免把浏览器对象、Cookie 或密码写入检查点。
        return raw

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BrowserSessionState":
        allowed = {name for name in cls.__dataclass_fields__}
        values = {key: value for key, value in data.items() if key in allowed}
        values.setdefault("platform", "tomato")
        values.setdefault("session_id", "")
        values.setdefault("page_id", "")
        return cls(**values)


class FakePage:
    """不联网的持久化页对象，模拟用户已打开的平台作品。"""

    def __init__(self, browser: "FakeBrowser", *, work_id: str, title: str, chapter_number: int = 1) -> None:
        self.browser = browser
        self.page_id = f"page-{uuid.uuid4().hex}"
        self.work_id = work_id
        self.title = title
        self.chapter_number = chapter_number
        self.chapter_title = f"第{chapter_number}章"
        self.content = ""
        self.content_sha256 = _sha256("")
        self.logged_in = True
        self.captcha_required = False
        self.closed = False
        self.input_preserved = True

    @property
    def connected(self) -> bool:
        return bool(self.browser.connected and not self.closed)

    def fill(self, content: str) -> str:
        if not self.connected:
            raise BrowserWorkbenchError("browser_session_interrupted")
        self.content = content
        self.content_sha256 = _sha256(content)
        return self.content_sha256

    def snapshot(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "work_id": self.work_id,
            "title": self.title,
            "chapter_number": self.chapter_number,
            "chapter_title": self.chapter_title,
            "content_sha256": self.content_sha256,
            "logged_in": self.logged_in,
            "captcha_required": self.captcha_required,
            "closed": self.closed,
        }

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    """Fake 浏览器拥有 session_id、随机本地端口和多个独立标签页。"""

    def __init__(self, *, platform: str = "tomato", port: int = 0, session_id: str | None = None) -> None:
        self.platform = platform
        self.session_id = session_id or f"session-{uuid.uuid4().hex}"
        self.port = port or self._random_port()
        self.connected = True
        self.pages: dict[str, FakePage] = {}

    @staticmethod
    def _random_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def new_page(self, *, work_id: str, title: str, chapter_number: int = 1) -> FakePage:
        if not self.connected:
            raise BrowserWorkbenchError("browser_session_interrupted")
        page = FakePage(self, work_id=work_id, title=title, chapter_number=chapter_number)
        self.pages[page.page_id] = page
        return page

    def get_page(self, page_id: str) -> FakePage:
        page = self.pages.get(page_id)
        if page is None:
            # Fake 重新连接时测试夹具可能只恢复 page_id；按页对象再查一次。
            page = next((item for item in self.pages.values() if item.page_id == page_id), None)
        if page is None:
            raise BrowserWorkbenchError("page_not_found")
        return page

    def crash(self) -> None:
        self.connected = False
        for page in self.pages.values():
            page.closed = True

    def close(self) -> None:
        self.crash()


class PersistentBrowserWorkbenchController:
    """管理固定右侧平台窗口和可恢复的发布上下文。"""

    def __init__(self, storage_path: str | os.PathLike[str], *, platform: str = "tomato", browser: FakeBrowser | None = None) -> None:
        self.storage_path = Path(storage_path)
        self.browser: FakeBrowser | None = browser
        self.page: FakePage | None = None
        self.state = self._load() or BrowserSessionState(platform=platform, session_id="", page_id="", connected=False)
        if browser and browser.connected and not self.state.session_id:
            self.state.session_id = browser.session_id
            self.state.platform = browser.platform
        if browser and browser.connected and self.state.page_id:
            try:
                self.page = browser.get_page(self.state.page_id)
            except BrowserWorkbenchError:
                self.page = None

    def _load(self) -> BrowserSessionState | None:
        try:
            return BrowserSessionState.from_dict(json.loads(self.storage_path.read_text(encoding="utf-8")))
        except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def persist(self) -> dict[str, Any]:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.state.to_dict()
        fd, temp_name = tempfile.mkstemp(prefix="publication-session-", suffix=".tmp", dir=self.storage_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.storage_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return payload

    def connect(self, browser: FakeBrowser, page: FakePage | None = None) -> dict[str, Any]:
        if not browser.connected:
            self.mark_interrupted("browser_session_interrupted")
            raise BrowserWorkbenchError("browser_session_interrupted")
        # 已有检查点时先核对持久化引用，禁止用新 session/page 覆盖旧上下文。
        if self.state.session_id or self.state.page_id:
            if browser.session_id != self.state.session_id:
                raise ReconnectionMismatch("session_mismatch")
            candidate = page
            if candidate is None:
                try:
                    candidate = browser.get_page(self.state.page_id)
                except BrowserWorkbenchError as exc:
                    raise ReconnectionMismatch("page_closed") from exc
            if candidate.page_id != self.state.page_id:
                raise ReconnectionMismatch("page_mismatch")
            return self.reconcile_page(candidate)
        self.browser = browser
        self.page = page or (browser.get_page(self.state.page_id) if self.state.page_id else None)
        if self.page is None:
            raise BrowserWorkbenchError("page_required")
        self.state.session_id = browser.session_id
        self.state.page_id = self.page.page_id
        self.state.platform = browser.platform
        self.state.connected = True
        self.state.login_state = "logged_in" if self.page.logged_in else "expired"
        self.state.reconnect_verified = not bool(self.state.resume_required)
        self.persist()
        return self.view()

    def handoff(self, *, platform: str, session_id: str, page_id: str, page_url: str | None = None,
                work_id: str | None = None, work_title: str | None = None,
                chapter_number: int | None = None, content_sha256: str | None = None,
                platform_work_title: str | None = None, platform_chapter_number: int | None = None,
                login_state: str = "unknown", reconnect: bool = False) -> dict[str, Any]:
        """记录真实浏览器待核对的接管引用；绝不把“打开页面”伪造为已连接。"""
        refs = (platform.strip(), session_id.strip(), page_id.strip())
        if not all(refs):
            raise ValueError("browser_handoff_reference_required")
        if chapter_number is not None and (type(chapter_number) is not int or chapter_number <= 0):
            raise ValueError("chapter_number_invalid")
        if reconnect and (self.state.session_id, self.state.page_id) != (session_id, page_id):
            raise ReconnectionMismatch("handoff_reference_mismatch")
        if not reconnect and (self.state.session_id or self.state.page_id) and (self.state.session_id, self.state.page_id) != (session_id, page_id):
            raise ReconnectionMismatch("handoff_reference_mismatch")
        self.state.platform = platform
        self.state.session_id, self.state.page_id = session_id, page_id
        self.state.page_url = page_url
        self.state.work_id, self.state.work_title = work_id, work_title
        self.state.chapter_number = chapter_number
        if platform_work_title is not None:
            self.state.platform_work_title = platform_work_title
        if platform_chapter_number is not None:
            self.state.platform_chapter_number = platform_chapter_number
        self.state.content_sha256 = content_sha256
        self.state.login_state = login_state if login_state in {"unknown", "logged_in", "expired"} else "unknown"
        self.state.connected = False
        self.state.reconnect_verified = False
        self.state.resume_required = True
        self.state.status = "awaiting_reconcile"
        self.persist()
        return self.view()

    def open(self, page: FakePage) -> dict[str, Any]:
        if not page.connected:
            raise BrowserWorkbenchError("browser_session_interrupted")
        self.browser, self.page = page.browser, page
        self.state.session_id = page.browser.session_id
        self.state.page_id = page.page_id
        self.state.platform = page.browser.platform
        self.state.work_id, self.state.work_title = page.work_id, page.title
        self.state.chapter_number = page.chapter_number
        self.state.connected = True
        self.state.login_state = "logged_in" if page.logged_in else "expired"
        self.state.reconnect_verified = True
        self.state.resume_required = False
        self.persist()
        return self.view()

    def bind_target(self, *, work_id: str, work_title: str, chapter_number: int, current_step: str | None = None) -> dict[str, Any]:
        if not self.page or not self.page.connected:
            self.mark_interrupted("browser_session_interrupted")
            raise BrowserWorkbenchError("browser_session_interrupted")
        if (self.page.work_id, self.page.title, self.page.chapter_number) != (work_id, work_title, chapter_number):
            raise ReconnectionMismatch("target_mismatch")
        self.state.work_id, self.state.work_title = work_id, work_title
        self.state.chapter_number, self.state.current_step = chapter_number, current_step
        self.persist()
        return self.view()

    def set_operation(self, *, operation_id: str, content: str, step: str) -> dict[str, Any]:
        self.state.operation_id = operation_id
        self.state.content_sha256 = _sha256(content)
        self.state.current_step = step
        self.persist()
        return self.view()

    def set_step(self, step: str) -> dict[str, Any]:
        self.state.current_step = step
        self.persist()
        return self.view()

    def fill(self, content: str) -> dict[str, Any]:
        if not self.page or not self.page.connected:
            self.mark_interrupted("browser_session_interrupted")
            raise BrowserWorkbenchError("browser_session_interrupted")
        if self.state.content_sha256 and self.state.content_sha256 != _sha256(content):
            raise ReconnectionMismatch("content_sha256_mismatch")
        self.page.fill(content)
        self.state.content_sha256 = self.page.content_sha256
        self.persist()
        return self.view()

    def pause(self, mode: str, reason: str = "user_pause") -> dict[str, Any]:
        if mode not in {"safe", "immediate"}:
            raise ValueError("pause_mode_invalid")
        self.state.pause_mode, self.state.pause_reason = mode, reason
        self.state.status = "paused"
        self.state.resume_required = True
        self.state.reconnect_verified = bool(self.page and self.page.connected)
        self.persist()
        return self.view()

    def mark_interrupted(self, reason: str = "browser_session_interrupted") -> dict[str, Any]:
        self.state.status = "browser_session_interrupted"
        self.state.pause_reason = reason
        self.state.connected = False
        self.state.resume_required = True
        self.state.reconnect_verified = False
        self.persist()
        return self.view()

    def poll(self) -> dict[str, Any]:
        if not self.browser or not self.page or not self.browser.connected or self.page.closed:
            return self.mark_interrupted("browser_session_interrupted")
        if self.page.captcha_required:
            self.state.status, self.state.pause_reason = "paused", "captcha_required"
        elif not self.page.logged_in:
            self.state.status, self.state.pause_reason = "paused", "login_expired"
        self.state.connected = True
        self.persist()
        return self.view()

    def reconcile_page(self, page: FakePage | None = None) -> dict[str, Any]:
        page = page or self.page
        if page is None or not page.connected:
            raise ReconnectionMismatch("page_unavailable")
        expected = self.state
        checks = {
            "session_id": page.browser.session_id == expected.session_id,
            "page_id": page.page_id == expected.page_id,
            "work_id": page.work_id == expected.work_id,
            "chapter_number": page.chapter_number == expected.chapter_number,
            "content_sha256": not expected.content_sha256 or page.content_sha256 == expected.content_sha256,
        }
        if not all(checks.values()):
            raise ReconnectionMismatch("reconnect_mismatch:" + ",".join(key for key, ok in checks.items() if not ok))
        self.browser, self.page = page.browser, page
        self.state.connected = True
        self.state.reconnect_verified = True
        self.state.status = "paused" if self.state.resume_required else self.state.status
        self.state.login_state = "logged_in" if page.logged_in else "expired"
        self.persist()
        return {"ok": True, "checks": checks, **self.view()}

    def reconnect(self, browser: FakeBrowser) -> dict[str, Any]:
        if not self.state.session_id or not self.state.page_id:
            raise BrowserWorkbenchError("session_checkpoint_missing")
        if not browser.connected or browser.session_id != self.state.session_id:
            self.mark_interrupted("browser_session_interrupted")
            raise ReconnectionMismatch("session_mismatch")
        try:
            page = browser.get_page(self.state.page_id)
        except BrowserWorkbenchError as exc:
            self.mark_interrupted("page_closed")
            raise ReconnectionMismatch("page_closed") from exc
        self.browser, self.page = browser, page
        return self.reconcile_page(page)

    def resume(self) -> dict[str, Any]:
        if not self.state.connected or not self.state.reconnect_verified:
            raise BrowserWorkbenchError("reconcile_required")
        if self.state.status not in {"paused", "browser_session_interrupted"}:
            return self.view()
        if not self.page or not self.page.connected:
            raise BrowserWorkbenchError("browser_session_interrupted")
        if self.page.captcha_required:
            raise BrowserWorkbenchError("captcha_required")
        if not self.page.logged_in:
            raise BrowserWorkbenchError("login_expired")
        self.state.status = "connected"
        self.state.pause_mode = None
        self.state.pause_reason = None
        self.state.resume_required = False
        self.persist()
        return self.view()

    def view(self) -> dict[str, Any]:
        payload = self.state.to_dict()
        payload["endpoint"] = self.browser.endpoint if self.browser else None
        payload["page"] = self.page.snapshot() if self.page else None
        payload["password_saved"] = False
        payload["fixed_side"] = self.state.panel_side
        return payload

    def render_panel_html(self) -> str:
        view = self.view()
        text = json.dumps(view, ensure_ascii=False, sort_keys=True)
        return (
            '<aside id="publication-browser-workbench" class="publication-browser-workbench" '
            'aria-label="持久化平台浏览器工作台" data-fixed-side="right">'
            '<header><strong>平台浏览器</strong><span data-session-status>' + str(view["status"]) + '</span></header>'
            '<pre data-session-state>' + text.replace("<", "&lt;") + '</pre>'
            '</aside>'
        )


# 兼容不同调用方的语义化别名。
PersistentBrowserSessionController = PersistentBrowserWorkbenchController
PublicationBrowserWorkbench = PersistentBrowserWorkbenchController

__all__ = [
    "BrowserSessionState", "BrowserWorkbenchError", "FakeBrowser", "FakePage",
    "PersistentBrowserWorkbenchController", "PersistentBrowserSessionController",
    "PublicationBrowserWorkbench", "ReconnectionMismatch",
]
