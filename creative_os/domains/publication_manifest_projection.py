from dataclasses import dataclass, asdict
import hashlib, json
@dataclass(frozen=True, slots=True)
class ApprovedSourceTargetProjection:
    grouping_candidate_hash: str
    archive_hash: str
    edition_id: str
    approval_hash: str
    groups: tuple[dict, ...]
    @property
    def projection_hash(self): return hashlib.sha256(json.dumps(asdict(self),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def encode_projection(value): return json.dumps({'schema_version':1,**asdict(value),'projection_hash':value.projection_hash},ensure_ascii=False,sort_keys=True)
