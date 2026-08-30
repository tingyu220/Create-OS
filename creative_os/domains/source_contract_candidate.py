from dataclasses import dataclass, asdict
import hashlib, json
@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    source_edition: str; chapter: int; paragraph: int; offset: int; excerpt_hash: str; target_field: str
@dataclass(frozen=True, slots=True)
class ContractCandidate:
    contract_id: str; version: int; intent: dict; bindings: tuple[EvidenceBinding,...]; blocking: tuple[str,...]
    @property
    def candidate_hash(self): return hashlib.sha256(json.dumps(asdict(self),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def encode_candidate(v): return json.dumps({'schema_version':1,**asdict(v),'candidate_hash':v.candidate_hash},ensure_ascii=False,sort_keys=True)
