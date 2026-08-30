from __future__ import annotations
from pathlib import Path
import hashlib,json,os
from creative_os.domains.project_authority import project_authority_lock

class ProductionReadinessStore:
    def __init__(self, project_root:str|Path):
        self.project_root=Path(project_root); self.root=self.project_root/'.creative_os'/'readiness-authority'; self.records_path=self.root/'records.jsonl'; self.head_path=self.root/'head.json'; self.journal_path=self.root/'journal.json'
    @staticmethod
    def _canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    @classmethod
    def _hash(cls,x): return hashlib.sha256(cls._canon(x).encode()).hexdigest()
    def recover(self):
        with project_authority_lock(self.project_root): return self._recover_locked()
    def _recover_locked(self):
        if not self.records_path.exists(): return ()
        out=[]; previous='0'*64
        try:
            for line in self.records_path.read_text(encoding='utf-8').splitlines():
                env=json.loads(line); expected=self._hash({k:v for k,v in env.items() if k!='entry_hash'})
                if set(env)!={"schema_version","sequence","previous_hash","record","entry_hash"} or env['schema_version']!=1 or env['sequence']!=len(out)+1 or env['previous_hash']!=previous or env['entry_hash']!=expected: raise ValueError
                out.append(env['record']); previous=env['entry_hash']
            if self.head_path.exists() and json.loads(self.head_path.read_text(encoding='utf-8'))!={"count":len(out),"head_hash":previous}: raise ValueError
            return tuple(out)
        except Exception as e: raise ValueError('tampered') from e
    def _append_locked(self,typ,payload):
        records=self._recover_locked(); previous='0'*64
        if records: previous=json.loads(self.records_path.read_text(encoding='utf-8').splitlines()[-1])['entry_hash']
        rid=f"{typ}:{len(records)+1}"; rec={"record_type":typ,"record_id":rid,"payload":payload,"content_hash":self._hash(payload)}; base={"schema_version":1,"sequence":len(records)+1,"previous_hash":previous,"record":rec}; env={**base,"entry_hash":self._hash(base)}
        self.root.mkdir(parents=True,exist_ok=True); self.journal_path.write_text(self._canon({"state":"prepared","envelope":env})+'\n',encoding='utf-8')
        with self.records_path.open('a',encoding='utf-8',newline='\n') as f:f.write(self._canon(env)+'\n'); f.flush(); os.fsync(f.fileno())
        self.head_path.write_text(self._canon({"count":len(records)+1,"head_hash":env['entry_hash']})+'\n',encoding='utf-8'); self.journal_path.unlink(missing_ok=True); return rec
    def append_audit(self,payload):
        if set(payload)!={"audit_hash","status","ruleset_hash"} or payload['status'] not in {'ready','blocked'}: raise ValueError('audit_schema')
        with project_authority_lock(self.project_root):
            for r in self._recover_locked():
                if r['record_type']=='audit' and r['payload']==payload:return r
            return self._append_locked('audit',payload)
    def append_approval(self,payload):
        if set(payload)!={"audit_record_id","audit_hash","actor","reason","decision"} or payload['decision']!='approved' or not payload['actor'].strip() or not payload['reason'].strip(): raise ValueError('approval_schema')
        with project_authority_lock(self.project_root):
            audit=next((r for r in self._recover_locked() if r['record_id']==payload['audit_record_id'] and r['record_type']=='audit'),None)
            if audit is None or audit['content_hash']!=payload['audit_hash']: raise ValueError('stale')
            return self._append_locked('approval',payload)
    def load_exact(self,typ,rid,content_hash):
        with project_authority_lock(self.project_root):
            for r in self._recover_locked():
                if r['record_type']==typ and r['record_id']==rid:
                    if r['content_hash']!=content_hash: raise ValueError('content_hash_mismatch')
                    return r['payload']
        raise KeyError(rid)
