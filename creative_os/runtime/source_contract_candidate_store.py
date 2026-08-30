from pathlib import Path
import json
from creative_os.domains.source_contract_candidate import encode_candidate
class ContractCandidateStore:
 def __init__(self,root): self.path=Path(root)/'.creative_os/publication_migration/contract_candidates.jsonl'; self.path.parent.mkdir(parents=True,exist_ok=True)
 def append(self,v):
  for x in self.path.read_text(encoding='utf-8').splitlines() if self.path.exists() else []:
   if json.loads(x).get('candidate_hash')==v.candidate_hash:return v.candidate_hash
  self.path.open('a',encoding='utf-8').write(encode_candidate(v)+'\n'); return v.candidate_hash
