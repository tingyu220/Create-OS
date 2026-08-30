from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from creative_os.runtime.publication_migration_store import PublicationMigrationStore, ActiveEditionPointer

@dataclass(frozen=True, slots=True)
class ActivePublicationEdition:
    edition_id: str
    manifest_hash: str
    migration_id: str

    @classmethod
    def load(cls, project_root: str | Path) -> "ActivePublicationEdition":
        pointer = PublicationMigrationStore(Path(project_root)).load_active_edition()
        if pointer is None:
            return cls("legacy-default", "0" * 64, "legacy")
        return cls(pointer.target_edition_id, pointer.manifest_hash, pointer.migration_id)

    def require(self, edition_id: str) -> None:
        if edition_id != self.edition_id:
            raise ValueError("stale_publication_edition")

def bind_edition(payload: dict, project_root: str | Path) -> dict:
    active = ActivePublicationEdition.load(project_root)
    bound = dict(payload)
    bound["edition_id"] = active.edition_id
    bound["edition_manifest_hash"] = active.manifest_hash
    return bound
