"""Workspace 与 Writer 共用的中文展示映射。"""

from __future__ import annotations


_STATUS_LABELS = {
    "fresh": "最新",
    "stale": "待刷新",
    "partial": "部分可用",
    "unavailable": "暂不可用",
    "running": "运行中",
    "passed": "已通过",
    "failed": "失败",
    "blocked": "已阻塞",
    "not_started": "未开始",
    "accepted": "已受理",
    "rejected": "已拒绝",
    "succeeded": "已完成",
    "retrying": "重试中",
}

_EVENT_LABELS = {
    "UserRevised": "作者修改了章节",
    "TaskCreated": "创建了任务",
    "TaskStarted": "开始执行任务",
    "TaskFailed": "本次运行失败",
    "ReviewFailed": "审阅未通过",
    "ResultGenerated": "生成了结果",
    "CapabilityCalled": "调用了创作能力",
}

_COMMAND_LABELS = {
    "start_chapter_run": "开始生成本章",
    "refresh_workspace_projection": "刷新工作台数据",
    "accept_review_issue": "确认审阅问题",
    "save_writer_draft": "保存工作稿",
    "restore_writer_version": "恢复历史版本",
    "open_writer_chapter": "打开章节",
}


def status_label(value: str | None) -> str:
    if not value:
        return "未知状态"
    return _STATUS_LABELS.get(value, value)


def event_label(value: str | None) -> str:
    if not value:
        return "未知活动"
    return _EVENT_LABELS.get(value, "系统活动")


def command_label(value: str | None) -> str:
    if not value:
        return "未知操作"
    return _COMMAND_LABELS.get(value, "工作台操作")


def diagnostic_label(code: str | None, message: str | None = None) -> str:
    labels = {
        "operations_usage_unavailable": "暂时没有用量统计",
        "operations_recovery_unavailable": "暂时没有恢复状态",
        "operations_retry_unavailable": "暂时没有重试状态",
        "workspace_projection_unavailable": "工作台数据暂时不可用",
    }
    return labels.get(code or "", message or "需要查看数据状态")


def is_internal_identifier(value: str | None) -> bool:
    """判断值是否应隐藏在普通产品界面。"""
    if not value:
        return False
    return value.startswith(("trace-", "refresh-", "event-", "projection-")) or ".creative_os/" in value
