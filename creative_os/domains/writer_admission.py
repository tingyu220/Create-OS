from __future__ import annotations
import hashlib,hmac,json,secrets,uuid,threading
from dataclasses import asdict,dataclass,replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Callable,TypeVar
from creative_os.domains.contract_approval import ApprovalStatus
from creative_os.domains.contract_baseline_resolver import BaselineSourceResolver,ResolverError
from creative_os.domains.contract_lifecycle import ContractLifecycleCoordinator,ContractPointer
from creative_os.domains.contract_preflight import ContractPreflightValidator
from creative_os.domains.contract_record_store import ContractRecordStore,authoritative_record_hash
from creative_os.domains.contract_review import validate_reviewer_gate
from creative_os.domains.narrative_causality import CausalDependencyAnalyzer
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.project_authority import project_authority_lock
from creative_os.memory.model import MemoryStatus
from creative_os.domains.contract_revision import WriterRunContinuationAuthorization

class WriterAdmissionError(ValueError):pass
@dataclass(frozen=True,slots=True)
class AdmittedContractProjection: contract_id:str;contract_version:int;contract_content_hash:str;canonical_json:str
@dataclass(frozen=True,slots=True)
class ContextExclusion: contract_id:str;contract_version:int
@dataclass(frozen=True,slots=True)
class PreAdmissionRequest: contract_id:str
@dataclass(frozen=True,slots=True)
class AdmissionGrant:
 token_type:str;grant_id:str;project_id:str;chapter_id:str;contract_id:str;contract_version:int;contract_content_hash:str;baseline_fingerprint:str;activation_binding_hash:str;authority_state_hash:str;approval_record_hash:str;reviewer_result_hash:str;ruleset_version:str;semantic_asset_versions:tuple[tuple[str,str],...];disposition_set_hash:str;projection:AdmittedContractProjection;projection_hash:str;exclusions:tuple[ContextExclusion,...];exclusions_hash:str;issued_at:str;expires_at:str;signature:str
@dataclass(frozen=True,slots=True)
class WriterAdmissionToken:
 token_type:str;grant_id:str;project_id:str;chapter_id:str;contract_id:str;contract_version:int;contract_content_hash:str;baseline_fingerprint:str;activation_binding_hash:str;authority_state_hash:str;approval_record_hash:str;reviewer_result_hash:str;ruleset_version:str;semantic_asset_versions:tuple[tuple[str,str],...];disposition_set_hash:str;projection_hash:str;exclusions_hash:str;context_fingerprint:str;run_id:str;issued_at:str;expires_at:str;signature:str
@dataclass(frozen=True,slots=True)
class RestrictedWriterAdmissionToken:
 token_type:str;authorization_id:str;restricted_old_run:bool;project_id:str;chapter_id:str;contract_id:str;contract_version:int;contract_content_hash:str;projection_hash:str;context_fingerprint:str;run_id:str;issued_at:str;expires_at:str;signature:str
@dataclass(frozen=True,slots=True)
class AdmissionAuthorityState:
 pointer:ContractPointer;decision:object;authority_state_hash:str;projection:AdmittedContractProjection;projection_hash:str;exclusions:tuple[ContextExclusion,...];exclusions_hash:str

class _PrivateMac:
 def __init__(self,key):self.__key=key
 def sign(self,d,v):return hmac.new(self.__key,d+b'\0'+_canonical(v),hashlib.sha256).hexdigest()
 def verify(self,d,v,s):return hmac.compare_digest(s,self.sign(d,v))
T=TypeVar('T')
_KEYS:dict[str,bytes]={};_KEY_GUARD=threading.Lock()
def _project_key(root:Path)->bytes:
 key=str(root.absolute())
 with _KEY_GUARD:return _KEYS.setdefault(key,secrets.token_bytes(32))

class WriterAdmissionService:
 _GRANT_DOMAIN=b'creative-os/grant/v1';_TOKEN_DOMAIN=b'creative-os/token/v1';_RESTRICTED_DOMAIN=b'creative-os/restricted-old-run/v1'
 def __init__(self,project_root:str|Path,resolver:BaselineSourceResolver):self.project_root=Path(project_root);self._resolver=resolver;self.__mac=_PrivateMac(_project_key(self.project_root))
 def pre_admit(self,request:PreAdmissionRequest)->AdmissionGrant:
  if not isinstance(request,PreAdmissionRequest):raise TypeError('pre_admit requires PreAdmissionRequest')
  with project_authority_lock(self.project_root):
   s=self._evaluate_authority_locked(request.contract_id);n=datetime.now(timezone.utc);p=s.pointer
   g=AdmissionGrant('admission_grant',str(uuid.uuid4()),self.project_root.name,s.decision.chapter_contract.chapter_id,request.contract_id,p.contract_version,p.content_hash,p.baseline_fingerprint,p.activation_binding_hash,s.authority_state_hash,p.approval_record_hash,p.reviewer_result_hash,p.ruleset_version,p.semantic_asset_versions,p.disposition_set_hash,s.projection,s.projection_hash,s.exclusions,s.exclusions_hash,n.isoformat(),(n+timedelta(minutes=5)).isoformat(),'')
   return replace(g,signature=self.__mac.sign(self._GRANT_DOMAIN,_unsigned(g)))
 def finalize_admission(self,g:AdmissionGrant,context_fingerprint:str,run_id:str)->WriterAdmissionToken:
  _sha(context_fingerprint);_text(run_id)
  with project_authority_lock(self.project_root):
   self._grant(g);s=self._evaluate_authority_locked(g.contract_id)
   if s.authority_state_hash!=g.authority_state_hash:raise WriterAdmissionError('authority_state_drift')
   n=datetime.now(timezone.utc);t=WriterAdmissionToken('writer_admission_token',g.grant_id,g.project_id,g.chapter_id,g.contract_id,g.contract_version,g.contract_content_hash,g.baseline_fingerprint,g.activation_binding_hash,g.authority_state_hash,g.approval_record_hash,g.reviewer_result_hash,g.ruleset_version,g.semantic_asset_versions,g.disposition_set_hash,g.projection_hash,g.exclusions_hash,context_fingerprint,run_id,n.isoformat(),(n+timedelta(minutes=5)).isoformat(),'')
   return replace(t,signature=self.__mac.sign(self._TOKEN_DOMAIN,_unsigned(t)))
 def validate_grant_for_context(self,g:AdmissionGrant)->AdmissionGrant:
  with project_authority_lock(self.project_root):
   self._grant(g);s=self._evaluate_authority_locked(g.contract_id)
   if s.authority_state_hash!=g.authority_state_hash:raise WriterAdmissionError('authority_state_drift')
   return g
 def validate_token(self,t:WriterAdmissionToken,expected_run_id:str,actual_context_fingerprint:str,*,handoff:Callable[[],T]|None=None)->WriterAdmissionToken|T:
  with project_authority_lock(self.project_root):
   if isinstance(t,RestrictedWriterAdmissionToken):
    self._restricted(t,expected_run_id,actual_context_fingerprint)
    found=ContractRecordStore(self.project_root).find_exact_continuation_authorization(authorization_id=t.authorization_id,run_id=t.run_id,contract_id=t.contract_id,contract_version=t.contract_version,contract_hash=t.contract_content_hash)
    if found is None:raise WriterAdmissionError('continuation_authorization_not_active')
    _expiry(found[1].expires_at)
    current=ContractLifecycleCoordinator(self.project_root).read_pointer(t.contract_id)
    if current is None or (current.contract_version,current.content_hash)==(t.contract_version,t.contract_content_hash):raise WriterAdmissionError('restricted_token_requires_replaced_contract')
    return t if handoff is None else handoff()
   self._token(t,expected_run_id,actual_context_fingerprint);s=self._evaluate_authority_locked(t.contract_id)
   if s.authority_state_hash!=t.authority_state_hash:raise WriterAdmissionError('authority_state_drift')
   return t if handoff is None else handoff()
 def issue_restricted_continuation_token(self,old_token:WriterAdmissionToken,authorization_id:str)->RestrictedWriterAdmissionToken:
  with project_authority_lock(self.project_root):
   self._token(old_token,old_token.run_id,old_token.context_fingerprint)
   found=ContractRecordStore(self.project_root).find_exact_continuation_authorization(authorization_id=authorization_id,run_id=old_token.run_id,contract_id=old_token.contract_id,contract_version=old_token.contract_version,contract_hash=old_token.contract_content_hash)
   if found is None:raise WriterAdmissionError('continuation_authorization_not_active')
   authorization=found[1];_expiry(authorization.expires_at)
   current=ContractLifecycleCoordinator(self.project_root).read_pointer(old_token.contract_id)
   if current is None or (current.contract_version,current.content_hash)==(old_token.contract_version,old_token.contract_content_hash):raise WriterAdmissionError('contract_not_replaced')
   n=datetime.now(timezone.utc);expires=min(datetime.fromisoformat(old_token.expires_at),datetime.fromisoformat(authorization.expires_at))
   token=RestrictedWriterAdmissionToken('restricted_writer_admission_token',authorization_id,True,old_token.project_id,old_token.chapter_id,old_token.contract_id,old_token.contract_version,old_token.contract_content_hash,old_token.projection_hash,old_token.context_fingerprint,old_token.run_id,n.isoformat(),expires.isoformat(),'')
   return replace(token,signature=self.__mac.sign(self._RESTRICTED_DOMAIN,_unsigned(token)))
 def _evaluate_authority_locked(self,cid:str)->AdmissionAuthorityState:
  lc=ContractLifecycleCoordinator(self.project_root);p=lc.read_pointer(cid);d=lc.load_current(cid) if p else None
  if p is None or d is None or NarrativeDecisionCodec.content_hash(d)!=p.content_hash:raise WriterAdmissionError('missing_or_drifted_current')
  e=ContractRecordStore(self.project_root).find_exact(contract_id=cid,contract_version=p.contract_version,contract_hash=p.content_hash,baseline_fingerprint=p.baseline_fingerprint,ruleset_version=p.ruleset_version)
  if e is None or e.reviewer_result is None:raise WriterAdmissionError('missing_exact_contract_records')
  if (e.approval_record_id,authoritative_record_hash(e.approval),e.reviewer_record_id,e.reviewer_result.result_hash)!=(p.approval_record_id,p.approval_record_hash,p.reviewer_result_id,p.reviewer_result_hash):raise WriterAdmissionError('activation_binding_drift')
  if e.approval.full_contract.status!=ApprovalStatus.APPROVED or any(x.status not in {ApprovalStatus.APPROVED,ApprovalStatus.NOT_APPLICABLE} for _,x in e.approval.approvals):raise WriterAdmissionError('approval_not_current')
  dh=_hash({'dispositions':[[i,authoritative_record_hash(x)] for i,x in sorted(e.disposition_records)]})
  if dh!=p.disposition_set_hash:raise WriterAdmissionError('disposition_set_drift')
  try:a=self._resolver.resolve_manifest(self.project_root,e.baseline.entries)
  except ResolverError as x:raise WriterAdmissionError(x.issue.code) from x
  c=CausalDependencyAnalyzer().analyze(d,a.profile,a.fact_snapshots,a.previous_chapter,a.change_requests);pf=ContractPreflightValidator().validate(d,a.evidence_resolver,c);rv=validate_reviewer_gate(e.reviewer_result,e.dispositions,contract_id=cid,contract_version=p.contract_version,contract_content_hash=p.content_hash,baseline_fingerprint=p.baseline_fingerprint,ruleset_version=p.ruleset_version,semantic_asset_versions=p.semantic_asset_versions)
  if not c.is_resolved or not pf.is_ready or not rv.is_ready:raise WriterAdmissionError('writer_admission_blocked')
  pending=self._pending(cid,p.contract_version)
  if pending:raise WriterAdmissionError('pending_revision')
  pr=AdmittedContractProjection(cid,p.contract_version,p.content_hash,NarrativeDecisionCodec.encode_v2(d));ex=(ContextExclusion(cid,p.contract_version),);ph=_hash(asdict(pr));eh=_hash([asdict(x) for x in ex]);sh=_hash({'pointer':p.to_dict(),'approval':[[n,x.status.value] for n,x in e.approval.approvals],'dispositions':dh,'pending':list(pending)})
  return AdmissionAuthorityState(p,d,sh,pr,ph,ex,eh)
 def _pending(self,cid,v):
  try:return tuple(sorted(x.id for x in ContractLifecycleCoordinator(self.project_root).store.list() if x.id.startswith(cid+'-v') and x.status==MemoryStatus.CANDIDATE and int(x.id.rsplit('-v',1)[1])>v))
  except Exception as e:raise WriterAdmissionError('pending_revision_query_failed') from e
 def _grant(self,g):
  if not isinstance(g,AdmissionGrant) or g.token_type!='admission_grant' or not self.__mac.verify(self._GRANT_DOMAIN,_unsigned(g),g.signature):raise WriterAdmissionError('invalid_grant')
  _expiry(g.expires_at)
 def _token(self,t,r,c):
  if not isinstance(t,WriterAdmissionToken) or t.token_type!='writer_admission_token' or not self.__mac.verify(self._TOKEN_DOMAIN,_unsigned(t),t.signature):raise WriterAdmissionError('invalid_token')
  _expiry(t.expires_at)
  if t.run_id!=r or t.context_fingerprint!=c:raise WriterAdmissionError('token_binding_mismatch')
 def _restricted(self,t,r,c):
  if type(t) is not RestrictedWriterAdmissionToken or t.token_type!='restricted_writer_admission_token' or t.restricted_old_run is not True or not self.__mac.verify(self._RESTRICTED_DOMAIN,_unsigned(t),t.signature):raise WriterAdmissionError('invalid_restricted_token')
  _expiry(t.expires_at)
  if t.run_id!=r or t.context_fingerprint!=c:raise WriterAdmissionError('token_binding_mismatch')

def _unsigned(x):p=asdict(x);p.pop('signature',None);return p
def _canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def _hash(x):return hashlib.sha256(_canonical(x)).hexdigest()
def _sha(x):
 if not isinstance(x,str) or len(x)!=64 or any(c not in '0123456789abcdef' for c in x):raise WriterAdmissionError('invalid_fingerprint')
def _text(x):
 if not isinstance(x,str) or not x.strip():raise WriterAdmissionError('value_required')
def _expiry(x):
 try:d=datetime.fromisoformat(x)
 except ValueError as e:raise WriterAdmissionError('invalid_expiry') from e
 if d.tzinfo is None or d<=datetime.now(timezone.utc):raise WriterAdmissionError('expired')
