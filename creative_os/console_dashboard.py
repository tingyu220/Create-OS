from __future__ import annotations

from creative_os.projection.chapters import ChapterStatus
from creative_os.projection.model import ProjectSnapshot


def render_console_dashboard(snapshot: ProjectSnapshot) -> str:
    """把统一只读快照格式化为文本，不读取或修改任何项目来源。"""
    lines = [
        f"项目：{snapshot.project_id}",
        f"当前阶段：{snapshot.overview.current_stage}",
        f"运行状态：{snapshot.overview.run_status.value}",
        "",
        "章节矩阵",
    ]
    if not snapshot.chapters:
        lines.append("暂无章节投影")
    else:
        passed = sum(1 for item in snapshot.chapters if item.status is ChapterStatus.PASSED)
        blocked = sum(1 for item in snapshot.chapters if item.status is ChapterStatus.BLOCKED)
        failed = sum(1 for item in snapshot.chapters if item.status is ChapterStatus.FAILED)
        lines.extend([f"通过：{passed}", f"阻塞：{blocked}", f"失败：{failed}"])
        for chapter in snapshot.chapters:
            lines.append(
                f"{chapter.chapter_id} {chapter.status.value} "
                f"attempts={chapter.attempts} elapsed={chapter.elapsed_seconds:.1f}s"
            )

    lines.extend(["", "质量"])
    if not snapshot.quality.issues:
        lines.append("暂无质量问题")
    else:
        lines.extend(
            f"{item.code} severity={item.severity} blocking={str(item.blocking).lower()} scope={item.scope}"
            for item in snapshot.quality.issues
        )

    lines.extend(["", "运行轨迹"])
    if not snapshot.trace.entries:
        lines.append("暂无运行轨迹")
    else:
        lines.extend(item.summary for item in snapshot.trace.entries)
    return "\n".join(lines)
