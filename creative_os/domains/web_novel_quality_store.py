from pathlib import Path
import hashlib,json,os
from creative_os.domains.project_authority import project_authority_lock

class WebNovelQualityStore:
    def __init__(self, project_root:str|Path): self.project_root=Path(project_root); self.root=self.project_root/'.creative_os'/'quality'; self.path=self.root/'records.jsonl'
    @staticmethod
    def _canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    def append(self,payload):
        if set(payload)!={"review_id","artifact_hash","hard_status","issues"}: raise ValueError('quality_schema')
        rec={"review_id":payload['review_id'],"payload":payload,"content_hash":hashlib.sha256(self._canon(payload).encode()).hexdigest()}
        with project_authority_lock(self.project_root):
            existing=self._read()
            for r in existing:
                if r['review_id']==rec['review_id']:
                    if r['payload']==payload:return r
                    raise ValueError('quality_conflict')
            self.root.mkdir(parents=True,exist_ok=True)
            with self.path.open('a',encoding='utf-8',newline='\n') as f:f.write(self._canon(rec)+'\n');f.flush();os.fsync(f.fileno())
            return rec
    def _read(self):
        if not self.path.exists(): return []
        return [json.loads(x) for x in self.path.read_text(encoding='utf-8').splitlines()]
    def load_exact(self,review_id,content_hash):
        with project_authority_lock(self.project_root):
            for r in self._read():
                if r['review_id']==review_id:
                    if r['content_hash']!=content_hash: raise ValueError('content_hash_mismatch')
                    return r['payload']
        raise KeyError(review_id)
