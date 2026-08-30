from __future__ import annotations
from pathlib import Path
import hashlib, json, os, uuid
from .chapter_run_checkpoint import ChapterRunCheckpoint, ChapterRunState
from creative_os.domains.project_authority import project_authority_lock

class ChapterRunCheckpointStore:
    def __init__(self, project_root: str | Path):
        self.root=Path(project_root)/".creative_os"/"production-runs"; self.records_path=self.root/"checkpoints.jsonl"; self.head_path=self.root/"head.json"
    def append(self, item: ChapterRunCheckpoint) -> ChapterRunCheckpoint:
        with project_authority_lock(self.root.parent.parent):
            records=self.recover(); existing=next((x for x in records if x.idempotency_key==item.idempotency_key),None)
            if existing:
                if existing==item:return existing
                raise ValueError("conflict")
            scoped=[x for x in records if x.project_id==item.project_id and x.chapter_number==item.chapter_number]
            if scoped and (item.sequence != scoped[-1].sequence+1 or item.previous_hash != scoped[-1].checkpoint_hash): raise ValueError("conflict")
            self.root.mkdir(parents=True,exist_ok=True)
            prev = "0" * 64
            if self.records_path.exists():
                prev = json.loads(self.records_path.read_text(encoding="utf-8").splitlines()[-1])["entry_hash"]
            env={"schema_version":1,"sequence":len(records)+1,"previous_hash":prev,"record":self._encode(item)}; env["entry_hash"]=hashlib.sha256(self._canon(env).encode()).hexdigest()
            with self.records_path.open("a",encoding="utf-8",newline="\n") as f:f.write(self._canon(env)+"\n");f.flush();os.fsync(f.fileno())
            self.head_path.write_text(self._canon({"count":len(records)+1,"head_hash":env["entry_hash"]})+"\n",encoding="utf-8")
            return item
    def current(self, project_id:str, chapter_number:int):
        matches=[x for x in self.recover() if x.project_id==project_id and x.chapter_number==chapter_number]
        if not matches: raise KeyError((project_id,chapter_number))
        return matches[-1]
    def recover(self):
        if not self.records_path.exists(): return ()
        out=[]; prev="0"*64
        try:
            for line in self.records_path.read_text(encoding="utf-8").splitlines():
                env=json.loads(line); expected=hashlib.sha256(self._canon({k:v for k,v in env.items() if k!="entry_hash"}).encode()).hexdigest()
                if env.get("sequence")!=len(out)+1 or env.get("previous_hash")!=prev or env.get("entry_hash")!=expected: raise ValueError
                out.append(self._decode(env["record"])); prev=env["entry_hash"]
            return tuple(out)
        except Exception as e: raise ValueError("tampered") from e
    @staticmethod
    def _encode(x): return {"project_id":x.project_id,"chapter_number":x.chapter_number,"state":x.state.value,"sequence":x.sequence,"previous_hash":x.previous_hash,"checkpoint_hash":x.checkpoint_hash,"idempotency_key":x.idempotency_key,"refs":list(x.refs)}
    @staticmethod
    def _decode(x): return ChapterRunCheckpoint(x["project_id"],x["chapter_number"],ChapterRunState(x["state"]),x["sequence"],x["previous_hash"],x["checkpoint_hash"],x["idempotency_key"],tuple(x["refs"]))
    @staticmethod
    def _canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",", ":"))
