"""作品书架的纯文件目录；只对当前页读取已有作者摘要。"""

from pathlib import Path
from urllib.parse import quote

from creative_os.author_home_query import AuthorHomeQuery
from creative_os.project_directory import validated_project, scan_project_directories
from creative_os.story_architecture_store import StoryArchitectureStore
from creative_os.workspace_command import CommandStoreError


class ProjectCatalog:
    def __init__(self, projects_root):
        self.root = Path(projects_root).resolve()

    def list_projects(self, query="", offset=0, limit=20):
        if not isinstance(query, str) or len(query) > 200 or type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("project_catalog_parameters_invalid")
        if not self.root.is_dir():
            raise OSError("projects_root_unavailable")
        projects, warnings = scan_project_directories(self.root)
        entries = []
        for project_id, (root, metadata) in projects.items():
            try:
                title = metadata.get("title") or metadata.get("name") or project_id
                if not isinstance(title, str) or not title.strip():
                    raise ValueError("project_title_invalid")
                if query.casefold() not in title.casefold() and query.casefold() not in project_id.casefold():
                    continue
                entries.append((title, project_id, root, metadata))
            except (OSError, ValueError, TypeError):
                warnings.append({"project_id": project_id, "directory": root.name, "code": "project_unavailable", "message": "这部作品的目录或元数据暂不可用。"})
        entries.sort(key=lambda entry: (entry[0].casefold(), entry[1].casefold()))
        items = [self._safe_item(*entry) for entry in entries[offset:offset + limit]]
        warnings.extend({"project_id": item["project_id"], "code": "project_summary_partial", "message": "部分作品摘要暂不可用，可打开作品核对。"}
                        for item in items if item["status"] == "partial")
        return {"items": items, "total": len(entries), "offset": offset, "limit": limit, "warnings": warnings}

    def project(self, project_id):
        root, metadata = validated_project(self.root, project_id)
        title = metadata.get("title") or metadata.get("name") or project_id
        if not isinstance(title, str) or not title.strip():
            raise ValueError("project_title_invalid")
        return self._safe_item(title, project_id, root, metadata)

    @staticmethod
    def _safe_item(title, project_id, root, metadata):
        try:
            return ProjectCatalog._item(title, project_id, root, metadata)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, CommandStoreError):
            # 单书摘要异常保留真实身份和可用入口；未知数量绝不冒充零。
            prefix = "/p/" + quote(project_id, safe="")
            location = {"page": "story", "chapter_number": None, "source": "auto"} if metadata.get("story_mode", False) else {"page": "writer", "chapter_number": 1, "source": "auto"}
            return {"project_id": project_id, "title": title, "entry_url": prefix + "/", "writer_url": prefix + "/writer",
                    "story_url": prefix + "/story", "counts": {"formal": None, "draft": None, "candidate": None},
                    "status": "partial", "notices": ["作品摘要暂不可用，稿件数量未知；可打开作品核对。"], "default_location": location}

    @staticmethod
    def _item(title, project_id, root, metadata):
        summary = AuthorHomeQuery(root, project_id).read()
        prefix = "/p/" + quote(project_id, safe="")
        resume = summary["resume"]
        if resume:
            source = resume["source"] if resume["source"] in {"draft", "formal"} else "auto"
            if source == "auto":
                chapter = next((item for item in summary["chapters"] if item["chapter_number"] == resume["chapter_number"]), {})
                source = "draft" if chapter.get("has_draft") else "formal" if chapter.get("has_formal") else "auto"
            location = {"page": "writer", "chapter_number": resume["chapter_number"], "source": source}
        else:
            needs_story = bool(metadata.get("story_mode", False))
            if needs_story:
                try:
                    needs_story = StoryArchitectureStore(root, project_id).view()["confirmed"] is None
                except (OSError, ValueError, KeyError, TypeError):
                    summary["notices"].append("故事设定暂时无法读取，可打开构思页面核对。")
                    summary["status"] = "partial"
            location = {"page": "story", "chapter_number": None, "source": "auto"} if needs_story else {"page": "writer", "chapter_number": 1, "source": "auto"}
        return {"project_id": project_id, "title": title, "entry_url": prefix + "/", "writer_url": prefix + "/writer",
                "story_url": prefix + "/story", "counts": summary["counts"], "status": summary["status"],
                "notices": summary["notices"], "default_location": location}
