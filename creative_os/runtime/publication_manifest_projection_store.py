from pathlib import Path
import json, hashlib
from creative_os.domains.publication_manifest_projection import ApprovedSourceTargetProjection, encode_projection
class ProjectionStore:
    def __init__(self, root):
        self.root=Path(root)/'.creative_os/publication_migration/projections'; self.root.mkdir(parents=True,exist_ok=True); self.path=self.root/'records.jsonl'; self.head=self.root/'head.json'
    def append(self,v):
        raw=encode_projection(v); rows=self.path.read_text(encoding='utf-8').splitlines() if self.path.exists() else []
        for line in rows:
            x=json.loads(line)
            if x.get('projection_hash')==v.projection_hash:return v.projection_hash
        line=json.dumps(json.loads(raw),ensure_ascii=False,sort_keys=True,separators=(',',':')); self.path.open('a',encoding='utf-8').write(line+'\n'); h=hashlib.sha256(line.encode()).hexdigest(); self.head.write_text(h,encoding='utf-8'); return v.projection_hash
    def load_exact(self,digest):
        for line in self.path.read_text(encoding='utf-8').splitlines():
            x=json.loads(line)
            if x.get('projection_hash')==digest:return x
        raise ValueError('projection_not_found')
