"""书架异常的结构化只读查询。"""

import json
from pathlib import Path

from creative_os.author_home_query import AuthorHomeQuery
from creative_os.novel_project import sanitize_project_folder_name
from creative_os.project_directory import scan_project_directories
from creative_os.project_directory_inventory import inventory_hash


class ProjectIssuesQuery:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def read(self, offset=0, limit=20):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("project_issues_parameters_invalid")
        projects, warnings = scan_project_directories(self.root)
        issues = []
        entries = [(root.name, project_id, root, metadata, None) for project_id, (root, metadata) in projects.items()]
        entries.extend((row["directory"], row["project_id"], None, None, row) for row in warnings)
        entries.sort(key=lambda row: (row[0].casefold(), row[1].casefold()))
        page = entries[offset:offset + limit]
        for directory, project_id, root, metadata, warning in page:
            if warning is not None:
                issues.append(self._issue(project_id, directory, warning["code"], warning["message"], None, ["recheck"]))
                continue
            title = metadata.get("title") or metadata.get("name") or project_id
            summary = None
            try:
                summary = AuthorHomeQuery(root, project_id).read()
            except Exception:
                issues.append(self._issue(project_id, root.name, "summary_unavailable", "作品摘要暂不可读，数量未知，可打开作品核对。", title, ["recheck", "open"]))
            if summary and summary.get("issues"):
                for diagnostic in summary["issues"]:
                    issues.append(self._issue(project_id, root.name, diagnostic["code"], diagnostic["message"], title, ["recheck", "open"], summary.get("counts")))
            try:
                target = sanitize_project_folder_name(metadata.get("title") or metadata.get("name") or project_id)
                if target != root.name and root.name.isascii() and any("\u4e00" <= char <= "\u9fff" for char in target) and not any(child.name.casefold() == target.casefold() for child in self.root.iterdir()):
                    issues.append(self._issue(project_id, root.name, "directory_name_mismatch", "目录名与作品名不一致，可预览迁移。", title, ["preview_migration"], summary.get("counts") if summary else None))
            except (ValueError, TypeError):
                issues.append(self._issue(project_id, root.name, "project_title_invalid", "作品名称不能安全映射为目录名。", title, ["open_project"], summary.get("counts") if summary else None))
        issues.sort(key=lambda item: (item["directory"].casefold(), item["project_id"].casefold(), item["code"]))
        revision = inventory_hash({"projects": [(key, value[0].name, value[1].get("name"), value[1].get("title")) for key, value in sorted(projects.items())], "warnings": warnings})
        return {"issues": issues, "items": issues, "total": len(entries), "total_projects": len(entries), "offset": offset, "limit": limit,
                "next_offset": min(offset + limit, len(entries)), "checked_projects": len(page), "catalog_revision": revision}

    @staticmethod
    def _issue(project_id, directory, code, message, title, actions, counts=None):
        return {"issue_id": inventory_hash([directory, project_id, code]), "project_id": project_id, "directory": directory, "title": title or project_id,
                "code": code, "message": message, "impact": "可能影响打开或继续写作。", "actions": actions,
                "known_counts": counts or {"formal": None, "draft": None, "candidate": None}}
