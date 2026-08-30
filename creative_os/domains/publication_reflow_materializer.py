from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import shutil
import tempfile


class PublicationReflowError(ValueError):
    """发布版重排无法安全执行。"""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_verified_edition(root: Path, edition_id: str) -> tuple[Path, dict[str, object]]:
    edition_root = root / ".creative_os" / "publication_migration" / "target_editions" / edition_id
    manifest_path = edition_root / "manifest.json"
    if not manifest_path.is_file():
        raise PublicationReflowError("source_manifest_missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored_hash = manifest.pop("manifest_hash", None)
    if stored_hash != hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest():
        raise PublicationReflowError("source_manifest_hash_mismatch")
    manifest["manifest_hash"] = stored_hash
    for item in manifest["chapters"]:
        content = (edition_root / item["file"]).read_text(encoding="utf-8")
        if _content_hash(content) != item["content_hash"]:
            raise PublicationReflowError("source_content_hash_mismatch")
    return edition_root, manifest


def _chapter_body(raw: str) -> list[str]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", raw) if item.strip()]
    return [item for item in paragraphs if not item.startswith("#")]


def _chapter_title(raw: str) -> str:
    first = raw.splitlines()[0].strip()
    match = re.match(r"#\s*第\s*\d+\s*章[：:]\s*(.+)", first)
    if not match:
        raise PublicationReflowError("source_title_invalid")
    return match.group(1).strip()


def _render(number: int, title: str, paragraphs: list[str]) -> str:
    if not title or not paragraphs:
        raise PublicationReflowError("target_chapter_invalid")
    return f"# 第 {number} 章：{title}\n\n" + "\n\n".join(paragraphs) + "\n"


def materialize_publication_reflow(
    project_root: str | Path,
    *,
    spec_path: str | Path,
) -> dict[str, object]:
    root = Path(project_root).absolute()
    spec_file = Path(spec_path).absolute()
    spec_raw = spec_file.read_bytes()
    spec = json.loads(spec_raw.decode("utf-8"))
    if spec.get("schema_version") != 1:
        raise PublicationReflowError("reflow_spec_invalid")
    source_root, source_manifest = _load_verified_edition(root, spec["source_edition_id"])
    if source_manifest["manifest_hash"] != spec["source_manifest_hash"]:
        raise PublicationReflowError("reflow_source_drift")

    source_items = {int(item["target_chapter_id"]): item for item in source_manifest["chapters"]}
    source_documents = {
        number: (source_root / item["file"]).read_text(encoding="utf-8")
        for number, item in source_items.items()
    }
    expansion_map = {int(item["source_chapter_id"]): item for item in spec.get("expansions", [])}
    trim_map = {int(item["source_chapter_id"]): item for item in spec.get("trims", [])}
    entries = spec.get("chapters") or _expand_merge_plan(sorted(source_documents), spec)
    used: list[int] = []
    documents: dict[str, str] = {}
    chapters: list[dict[str, object]] = []
    for entry in entries:
        target_number = int(entry["target_chapter_id"])
        source_numbers = [int(item) for item in entry["source_chapter_ids"]]
        if not source_numbers or any(number not in source_documents for number in source_numbers):
            raise PublicationReflowError("reflow_source_chapter_invalid")
        paragraphs: list[str] = []
        for source_number in source_numbers:
            source_paragraphs = _chapter_body(source_documents[source_number])
            trim = trim_map.get(source_number)
            if trim is not None:
                keep = int(trim["keep_through_paragraph"])
                if keep < 1 or keep > len(source_paragraphs):
                    raise PublicationReflowError("reflow_trim_invalid")
                source_paragraphs = source_paragraphs[:keep]
            expansion = expansion_map.get(source_number)
            if expansion is not None:
                ordinal = int(expansion["after_paragraph"])
                additions = [str(item).strip() for item in expansion["paragraphs"]]
                if ordinal < 1 or ordinal > len(source_paragraphs) or any(not item for item in additions):
                    raise PublicationReflowError("reflow_expansion_invalid")
                source_paragraphs[ordinal:ordinal] = additions
            paragraphs.extend(source_paragraphs)
        title = entry.get("title") or _chapter_title(source_documents[source_numbers[0]])
        content = _render(target_number, title, paragraphs)
        filename = f"chapter_{target_number:03d}.md"
        used.extend(source_numbers)
        documents[filename] = content
        chapters.append({
            "target_chapter_id": target_number,
            "file": filename,
            "title": title,
            "source_chapter_ids": source_numbers,
            "source_content_hashes": [source_items[number]["content_hash"] for number in source_numbers],
            "content_hash": _content_hash(content),
        })

    expected = sorted(source_documents)
    if sorted(used) != expected or len(used) != len(set(used)):
        raise PublicationReflowError("reflow_source_coverage_not_exact")
    target_ids = [item["target_chapter_id"] for item in chapters]
    if target_ids != list(range(target_ids[0], target_ids[-1] + 1)):
        raise PublicationReflowError("reflow_target_not_contiguous")

    manifest: dict[str, object] = {
        "schema_version": 1,
        "source_edition_id": spec["source_edition_id"],
        "source_manifest_hash": source_manifest["manifest_hash"],
        "target_edition_id": spec["target_edition_id"],
        "reflow_spec_hash": hashlib.sha256(spec_raw).hexdigest(),
        "activation_status": "withheld",
        "chapters": chapters,
    }
    manifest["manifest_hash"] = hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()
    _publish(root, spec["target_edition_id"], documents, manifest)
    return manifest


def _expand_merge_plan(source_ids: list[int], spec: dict[str, object]) -> list[dict[str, object]]:
    """把少量合章声明展开为连续目标章，避免维护大而易错的逐章配置。"""
    merges = {
        int(item["source_chapter_ids"][0]): item
        for item in spec.get("merges", [])
    }
    entries: list[dict[str, object]] = []
    cursor = 0
    target_number = source_ids[0]
    while cursor < len(source_ids):
        source_number = source_ids[cursor]
        merge = merges.get(source_number)
        selected = [source_number] if merge is None else [int(item) for item in merge["source_chapter_ids"]]
        if source_ids[cursor:cursor + len(selected)] != selected:
            raise PublicationReflowError("reflow_merge_not_contiguous")
        entry: dict[str, object] = {
            "target_chapter_id": target_number,
            "source_chapter_ids": selected,
        }
        if merge is not None:
            entry["title"] = merge["title"]
        entries.append(entry)
        cursor += len(selected)
        target_number += 1
    return entries


def _publish(root: Path, edition_id: str, documents: dict[str, str], manifest: dict[str, object]) -> None:
    editions = root / ".creative_os" / "publication_migration" / "target_editions"
    editions.mkdir(parents=True, exist_ok=True)
    target = editions / edition_id
    temporary = Path(tempfile.mkdtemp(prefix=f".{edition_id}-", dir=editions))
    try:
        for filename, content in documents.items():
            (temporary / filename).write_text(content, encoding="utf-8", newline="\n")
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        backup = editions / f".{edition_id}-superseded"
        if backup.exists():
            raise PublicationReflowError("reflow_backup_conflict")
        if target.exists():
            target.rename(backup)
        try:
            temporary.rename(target)
        except Exception:
            if backup.exists():
                backup.rename(target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
