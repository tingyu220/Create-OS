from __future__ import annotations
from pathlib import Path
import hashlib, json, os
from creative_os.domains.project_authority import project_authority_lock

class WriterExecutionAuthorityStore:
    TYPES={"intent","receipt","reconciliation"}
    def __init__(self, project_root:str|Path):
        self.project_root=Path(project_root); self.root=self.project_root/'.creative_os'/'writer-execution'; self.records_path=self.root/'records.jsonl'; self.head_path=self.root/'head.json'; self.journal_path=self.root/'journal.json'
    @staticmethod
    def _canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    @classmethod
    def _hash(cls,x): return hashlib.sha256(cls._canon(x).encode()).hexdigest()
    def _recover_locked(self):
        if not self.records_path.exists(): return ()
        out=[]; previous='0'*64
        try:
            for line in self.records_path.read_text(encoding='utf-8').splitlines():
                env=json.loads(line)
                if set(env)!={"schema_version","sequence","previous_hash","record","entry_hash"}: raise ValueError
                if env['schema_version']!=1 or env['sequence']!=len(out)+1 or env['previous_hash']!=previous or env['entry_hash']!=self._hash({k:v for k,v in env.items() if k!='entry_hash'}): raise ValueError
                rec=env['record']
                if rec['type'] not in self.TYPES: raise ValueError
                out.append(rec); previous=env['entry_hash']
            if self.head_path.exists() and json.loads(self.head_path.read_text(encoding='utf-8'))!={"count":len(out),"head_hash":previous}: raise ValueError
            return tuple(out)
        except Exception as e: raise ValueError('tampered') from e
    def recover(self):
        with project_authority_lock(self.project_root): return self._recover_locked()
    def _append_locked(self, typ, rid, payload):
        records=self._recover_locked(); previous='0'*64
        if records: previous=json.loads(self.records_path.read_text(encoding='utf-8').splitlines()[-1])['entry_hash']
        rec={"type":typ,"id":rid,"payload":payload,"content_hash":self._hash(payload)}; base={"schema_version":1,"sequence":len(records)+1,"previous_hash":previous,"record":rec}; env={**base,"entry_hash":self._hash(base)}
        self.root.mkdir(parents=True,exist_ok=True); self.journal_path.write_text(self._canon({"state":"prepared","envelope":env})+'\n',encoding='utf-8')
        with self.records_path.open('a',encoding='utf-8',newline='\n') as f:f.write(self._canon(env)+'\n'); f.flush(); os.fsync(f.fileno())
        self.head_path.write_text(self._canon({"count":len(records)+1,"head_hash":env['entry_hash']})+'\n',encoding='utf-8'); self.journal_path.unlink(missing_ok=True); return rec
    def append_intent(self,payload):
        if set(payload)!={"run_id","project_id","chapter","request_hash","context_fingerprint","idempotency_key"}: raise ValueError('intent_schema')
        with project_authority_lock(self.project_root):
            for r in self._recover_locked():
                if r['type']=='intent' and r['id']==payload['run_id']:
                    if r['payload']==payload:return r
                    raise ValueError('intent_conflict')
            return self._append_locked('intent',payload['run_id'],payload)
    def append_local_receipt(self,run_id,payload):
        with project_authority_lock(self.project_root):
            intent=next((r for r in self._recover_locked() if r['type']=='intent' and r['id']==run_id),None)
            if intent is None or payload.get('request_hash')!=intent['payload']['request_hash']: raise ValueError('receipt_binding')
            normalized={**payload,"run_id":run_id,"local_mac":self._hash({"domain":"writer_execution_receipt","run_id":run_id,"payload":payload})}
            for r in self._recover_locked():
                if r['type']=='receipt' and r['id']==run_id:
                    if r['payload']==normalized:return r
                    raise ValueError('receipt_conflict')
            return self._append_locked('receipt',run_id,normalized)
    def append_reconciliation_decision(self,run_id,payload):
        required={"decision_id","actor","reason","provider_request_id","provider_result_hash"}
        if set(payload)!=required or not payload['actor'].strip() or not payload['reason'].strip() or len(payload['provider_result_hash'])!=64: raise ValueError('reconciliation_schema')
        with project_authority_lock(self.project_root):
            if not any(r['type']=='receipt' and r['id']==run_id for r in self._recover_locked()): raise ValueError('receipt_missing')
            normalized={**payload,"run_id":run_id,"previous_authority_hash":self._head_hash_locked()}; return self._append_locked('reconciliation',payload['decision_id'],normalized)
    def _head_hash_locked(self): return json.loads(self.head_path.read_text(encoding='utf-8'))['head_hash'] if self.head_path.exists() else '0'*64
    def load_exact(self,typ,rid,content_hash):
        with project_authority_lock(self.project_root):
            for r in self._recover_locked():
                if r['type']==typ and r['id']==rid:
                    if r['content_hash']!=content_hash: raise ValueError('content_hash_mismatch')
                    return r['payload']
        raise KeyError(rid)
