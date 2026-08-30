from __future__ import annotations

from pathlib import Path
import hashlib
import json

from creative_os.runtime.publication_migration_store import PublicationMigrationStore
from creative_os.domains.publication_migration_model import MigrationCheckpoint, CheckpointPhase
from creative_os.domains.publication_migration_codec import manifest_hash


class PublicationMigrationService:
    def __init__(self, project_root: str | Path, *, target_edition_id: str = "civilization-publication-v2"):
        self.project_root = Path(project_root).absolute()
        self.target_edition_id = target_edition_id
        self.target_root = self.project_root / ".creative_os" / "publication_migration" / "target_editions" / target_edition_id
        self.store = PublicationMigrationStore(self.project_root)

    def snapshot(self, migration_id: str, manifest_digest: str):
        return self.store.load_exact(migration_id, manifest_digest)

    def approve_plan(self, migration_id: str, manifest_digest: str):
        manifest = self.snapshot(migration_id, manifest_digest)
        if manifest.target_edition_id != self.target_edition_id:
            raise ValueError("edition_mismatch")
        return manifest

    def rebuild_content_batch(self, migration_id: str, batch_id: str, source_start: int, source_end: int, *, source_edition_id: str):
        if source_edition_id == self.target_edition_id:
            raise ValueError("edition_mismatch")
        self.target_root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(f"{migration_id}:{batch_id}:{source_start}:{source_end}".encode()).hexdigest()
        (self.target_root / f"batch-{batch_id}.json").write_text(json.dumps({"batch_id": batch_id, "source_start": source_start, "source_end": source_end, "fingerprint": digest}, sort_keys=True) + "\n", encoding="utf-8")
        return digest

    def rebuild_authority_batch(self, migration_id: str, batch_id: str, manifest_digest: str):
        manifest = self.snapshot(migration_id, manifest_digest)
        if manifest.target_edition_id != self.target_edition_id:
            raise ValueError("edition_mismatch")
        return manifest

    def verify_batch(self, migration_id: str, batch_id: str, manifest_digest: str):
        manifest = self.snapshot(migration_id, manifest_digest)
        if manifest.target_edition_id != self.target_edition_id:
            raise ValueError("edition_mismatch")
        return True

    def activate(self, migration_id: str, manifest_digest: str):
        with self.store._transaction.acquire() as lock:
            manifest = self.snapshot(migration_id, manifest_digest)
            if manifest.target_edition_id != self.target_edition_id:
                raise ValueError("edition_mismatch")
            return self.store.activate_verified_manifest(manifest_digest, lock)
