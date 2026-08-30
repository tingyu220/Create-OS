from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib,json
from creative_os.domains.chapter_production_owner_registry import production_owner_registry

@dataclass(frozen=True, slots=True)
class FakeChapterArtifact:
    metadata: dict
    structured_evidence: tuple[dict, ...]
    artifact_hash: str

class FakeChapterWriter:
    def __init__(self, project_root: str|Path):
        self.project_root=Path(project_root); self.calls=0; self.prepared_runs=[]; self._cache={}; self.reopen_counts={name:0 for name in production_owner_registry()}
    def prepare(self, chapter:int):
        if chapter in self._cache:return self._cache[chapter]
        self.calls+=1
        metadata={"chapter":chapter,"choice":f"choice-{chapter}","cost":f"cost-{chapter}","arc":f"arc-{chapter}","conflict":f"conflict-{chapter}","expectation":f"expectation-{chapter}","state":f"state-{chapter}","hook":f"hook-{chapter}"}
        digest=hashlib.sha256(json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        artifact=FakeChapterArtifact(metadata,(dict(metadata),),digest); self._cache[chapter]=artifact; return artifact
    def resume(self,chapter): return self.prepare(chapter)
    def verify_artifact(self,metadata):
        if len(metadata.get('artifact_hash',''))!=64: raise ValueError('artifact_hash')
        return True
    def close_reopen_all(self):
        for name in self.reopen_counts:self.reopen_counts[name]+=1
