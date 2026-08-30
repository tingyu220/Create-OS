from __future__ import annotations

from collections import Counter
from pathlib import Path
import hashlib
import json
import os
import tempfile
import shutil

from creative_os.domains.publication_source_snapshot import VerifiedSourceParagraph
from creative_os.domains.publication_source_snapshot import load_verified_archive
from creative_os.domains.target_chapter_grouping import TargetChapterGroupingCandidate
from creative_os.runtime.publication_split_approval_store import SplitPlanApprovalStore
from creative_os.runtime.target_chapter_grouping_store import TargetGroupingStore


class MaterializationError(ValueError):
    """目标版正文无法安全物化。"""


def validate_exact_coverage(
    groups: tuple[TargetChapterGroupingCandidate, ...],
    available_mappings: tuple[tuple[int, int], ...],
) -> None:
    mapped = tuple(mapping for group in groups for mapping in group.source_mappings)
    if Counter(mapped) != Counter(available_mappings) or len(mapped) != len(set(mapped)):
        raise MaterializationError("source_mapping_not_exact")


def render_target_chapter(
    target_chapter_id: int,
    title: str,
    paragraphs: tuple[VerifiedSourceParagraph, ...],
) -> str:
    if target_chapter_id <= 0 or not title.strip() or not paragraphs:
        raise MaterializationError("target_chapter_invalid")
    body = [
        paragraph.text.rstrip()
        for paragraph in paragraphs
        if not paragraph.text.lstrip().startswith("#")
    ]
    body = [paragraph for paragraph in body if paragraph.strip()]
    return f"# 第 {target_chapter_id} 章：{title.strip()}\n\n" + "\n\n".join(body) + "\n"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def materialize_approved_target(
    project_root: str | Path,
    migration_id: str,
    *,
    target_edition_id: str = "civilization-publication-v2",
) -> dict[str, object]:
    root = Path(project_root).absolute()
    approval_store = SplitPlanApprovalStore(root)
    try:
        candidate, receipt, review = approval_store.load_current_bundle(migration_id)
        decision = approval_store.require_current_approval(candidate, receipt, review)
    finally:
        approval_store.close()
    if candidate.target_edition_id != target_edition_id:
        raise MaterializationError("target_edition_mismatch")

    groups = TargetGroupingStore(root).list_current(migration_id)
    if not groups:
        raise MaterializationError("grouping_missing")
    target_ids = tuple(group.target_chapter_id for group in groups)
    if target_ids != tuple(range(target_ids[0], target_ids[-1] + 1)):
        raise MaterializationError("target_chapter_not_contiguous")

    archive = load_verified_archive(receipt, root)
    titles, title_registry_hash = _load_titles(root, target_edition_id, target_ids)
    expansions, expansion_registry_hash = _load_expansions(root, target_edition_id)
    available = tuple((item.chapter_number, item.paragraph_ordinal) for item in archive.iter_paragraphs())
    validate_exact_coverage(groups, available)
    paragraphs = {
        (item.chapter_number, item.paragraph_ordinal): item
        for item in archive.iter_paragraphs()
    }
    chapters: list[dict[str, object]] = []
    documents: dict[str, str] = {}
    for group in groups:
        selected = tuple(paragraphs[mapping] for mapping in group.source_mappings)
        content = render_target_chapter(group.target_chapter_id, titles[group.target_chapter_id], selected)
        if group.target_chapter_id in expansions:
            content = apply_published_expansion(content, expansions[group.target_chapter_id])
        filename = f"chapter_{group.target_chapter_id:03d}.md"
        documents[filename] = content
        chapters.append({
            "target_chapter_id": group.target_chapter_id,
            "file": filename,
            "content_hash": content_hash(content),
            "candidate_hash": group.candidate_hash,
            "title": titles[group.target_chapter_id],
            "source_mappings": [list(mapping) for mapping in group.source_mappings],
            "estimated_chinese_chars": group.estimated_chinese_chars,
            "short_chapter_disposition": group.short_chapter_disposition,
        })
    manifest: dict[str, object] = {
        "schema_version": 1,
        "migration_id": migration_id,
        "target_edition_id": target_edition_id,
        "source_edition_id": archive.source_edition_id,
        "source_snapshot_hash": archive.snapshot_hash,
        "source_archive_hash": archive.archive_hash,
        "split_candidate_hash": candidate.candidate_hash,
        "approval_decision_hash": decision.decision_hash,
        "title_registry_hash": title_registry_hash,
        "published_expansion_registry_hash": expansion_registry_hash,
        "activation_status": "withheld",
        "chapters": chapters,
    }
    manifest["manifest_hash"] = hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
    _publish_target(root, target_edition_id, documents, manifest)
    return manifest


def verify_materialized_target(
    project_root: str | Path,
    *,
    target_edition_id: str = "civilization-publication-v2",
) -> dict[str, object]:
    target_root = Path(project_root).absolute() / ".creative_os" / "publication_migration" / "target_editions" / target_edition_id
    manifest_path = target_root / "manifest.json"
    if not manifest_path.is_file():
        raise MaterializationError("target_manifest_missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored_hash = manifest.pop("manifest_hash", None)
    if stored_hash != hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest():
        raise MaterializationError("target_manifest_hash_mismatch")
    manifest["manifest_hash"] = stored_hash
    expected_names = {"manifest.json", *(item["file"] for item in manifest["chapters"])}
    actual_names = {path.name for path in target_root.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise MaterializationError("target_file_set_mismatch")
    for item in manifest["chapters"]:
        raw = (target_root / item["file"]).read_text(encoding="utf-8")
        if content_hash(raw) != item["content_hash"]:
            raise MaterializationError("target_content_hash_mismatch")
    return manifest


def _publish_target(
    project_root: Path,
    target_edition_id: str,
    documents: dict[str, str],
    manifest: dict[str, object],
) -> None:
    editions_root = project_root / ".creative_os" / "publication_migration" / "target_editions"
    editions_root.mkdir(parents=True, exist_ok=True)
    target_root = editions_root / target_edition_id
    if target_root.exists():
        existing = verify_materialized_target(project_root, target_edition_id=target_edition_id)
        if existing == manifest:
            return
    temporary = Path(tempfile.mkdtemp(prefix=f".{target_edition_id}-", dir=editions_root))
    try:
        for filename, content in documents.items():
            (temporary / filename).write_text(content, encoding="utf-8", newline="\n")
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if target_root.exists():
            backup = editions_root / f".{target_edition_id}-superseded"
            if backup.exists():
                raise MaterializationError("target_backup_conflict")
            os.rename(target_root, backup)
            try:
                os.rename(temporary, target_root)
                verify_materialized_target(project_root, target_edition_id=target_edition_id)
            except Exception:
                if target_root.exists():
                    shutil.rmtree(target_root)
                os.rename(backup, target_root)
                raise
            shutil.rmtree(backup)
        else:
            os.rename(temporary, target_root)
    except Exception:
        if temporary.exists():
            for path in temporary.iterdir():
                path.unlink()
            temporary.rmdir()
        raise


def _load_titles(
    project_root: Path,
    target_edition_id: str,
    target_ids: tuple[int, ...],
) -> tuple[dict[int, str], str]:
    path = project_root / ".creative_os" / "publication_migration" / "chapter_titles" / f"{target_edition_id}.json"
    if not path.is_file():
        raise MaterializationError("title_registry_missing")
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if value.get("schema_version") != 1 or value.get("target_edition_id") != target_edition_id:
        raise MaterializationError("title_registry_invalid")
    titles = {int(key): item.strip() for key, item in value.get("titles", {}).items()}
    if tuple(sorted(titles)) != target_ids or any(not title or len(title) > 16 for title in titles.values()):
        raise MaterializationError("title_registry_not_exact")
    if len(set(titles.values())) != len(titles):
        raise MaterializationError("title_registry_duplicate")
    return titles, hashlib.sha256(raw).hexdigest()


def apply_published_expansion(content: str, spec: dict[str, object]) -> str:
    if content_hash(content) != spec.get("base_content_hash"):
        raise MaterializationError("published_revision_base_mismatch")
    paragraphs = content.rstrip("\n").split("\n\n")
    for insertion in spec.get("insertions", []):
        anchor = insertion.get("after_paragraph_hash")
        matches = [index for index, paragraph in enumerate(paragraphs) if content_hash(paragraph) == anchor]
        additions = insertion.get("paragraphs")
        if len(matches) != 1 or not isinstance(additions, list) or not additions:
            raise MaterializationError("published_revision_anchor_invalid")
        index = matches[0] + 1
        paragraphs[index:index] = [str(paragraph).strip() for paragraph in additions]
    return "\n\n".join(paragraphs) + "\n"


def _load_expansions(
    project_root: Path,
    target_edition_id: str,
) -> tuple[dict[int, dict[str, object]], str]:
    path = project_root / ".creative_os" / "publication_migration" / "published_expansions" / f"{target_edition_id}.json"
    if not path.is_file():
        return {}, hashlib.sha256(b"").hexdigest()
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if value.get("schema_version") != 1 or value.get("target_edition_id") != target_edition_id:
        raise MaterializationError("published_revision_registry_invalid")
    expansions = {int(key): item for key, item in value.get("chapters", {}).items()}
    return expansions, hashlib.sha256(raw).hexdigest()
