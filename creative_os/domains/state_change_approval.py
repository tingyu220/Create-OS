from pathlib import Path
import hashlib, json, os, uuid
from .project_authority import project_authority_lock

def _canon(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def _hash(v): return hashlib.sha256(_canon(v).encode()).hexdigest()

class StateChangeApprovalStore:
    def __init__(self, project_root:str|Path):
        self.root=Path(project_root)/'.creative_os'/'state-change'; self.records_path=self.root/'records.jsonl'; self.head_path=self.root/'head.json'; self.journal_path=self.root/'journal.json'
    def append(self,payload):
        with project_authority_lock(self.root.parent.parent):
            records=list(self.recover()); existing=next((r for r in records if r['record_id']==payload['record_id']),None)
            if existing is not None:
                if existing==payload:return existing
                raise ValueError('record_id_conflict')
            prev='0'*64
            if self.head_path.exists():
                prev=json.loads(self.head_path.read_text(encoding='utf-8'))['head_hash']
            env={'schema_version':1,'sequence':len(records)+1,'previous_hash':prev,'record':payload}; env['record_hash']=_hash(payload); env['entry_hash']=_hash({k:v for k,v in env.items() if k!='entry_hash'})
            self.root.mkdir(parents=True,exist_ok=True); prior=self.records_path.read_bytes() if self.records_path.exists() else b''
            self.journal_path.write_text(_canon({'state':'prepared','envelope':env})+'\n',encoding='utf-8')
            with self.records_path.open('wb') as f:f.write(prior); f.write((_canon(env)+'\n').encode()); f.flush(); os.fsync(f.fileno())
            self.head_path.write_text(_canon({'count':len(records)+1,'head_hash':env['entry_hash']})+'\n',encoding='utf-8'); self.journal_path.unlink(missing_ok=True); return payload
    def recover(self):
        if not self.records_path.exists():return ()
        out=[]; prev='0'*64
        try:
            for line in self.records_path.read_text(encoding='utf-8').splitlines():
                env=json.loads(line)
                if env['sequence']!=len(out)+1 or env['previous_hash']!=prev or env['record_hash']!=_hash(env['record']) or env['entry_hash']!=_hash({k:v for k,v in env.items() if k!='entry_hash'}):raise ValueError
                out.append(env['record']); prev=env['entry_hash']
            if self.head_path.exists() and json.loads(self.head_path.read_text())!={'count':len(out),'head_hash':prev}:raise ValueError
            return tuple(out)
        except Exception as e: raise ValueError('tampered') from e

class StateChangeApprovalService:
    def __init__(self, project_root:str|Path): self.project_root=Path(project_root); self.store=StateChangeApprovalStore(self.project_root)
    def approve(self,candidate,actor,reason):
        if not isinstance(candidate,dict) or not isinstance(actor,str) or not actor.strip() or not isinstance(reason,str) or not reason.strip() or not candidate.get('candidate_id'): raise ValueError('decision_invalid')
        ch=_hash(candidate); decision={'record_id':f"decision:{candidate['candidate_id']}",'kind':'decision','candidate_id':candidate['candidate_id'],'candidate':candidate,'candidate_hash':ch,'actor':actor,'reason':reason,'decision_hash':_hash({'candidate_hash':ch,'actor':actor,'reason':reason})}; return self.store.append(decision)
    def materialize(self,candidate):
        if not isinstance(candidate,dict) or not candidate.get('candidate_id'):raise ValueError('approval_required')
        decision=next((r for r in self.store.recover() if r.get('kind')=='decision' and r.get('candidate_id')==candidate['candidate_id']),None)
        if decision is None or decision['candidate_hash']!=_hash(candidate):raise ValueError('approval_required')
        baseline={'candidate_id':candidate['candidate_id'],'state':candidate.get('state'),'decision_hash':decision['decision_hash']}
        receipt={'record_id':f"materialization:{candidate['candidate_id']}",'kind':'materialization','candidate_id':candidate['candidate_id'],'candidate_hash':decision['candidate_hash'],'decision_hash':decision['decision_hash'],'actor':decision['actor'],'reason':decision['reason'],'next_baseline':baseline,'next_baseline_hash':_hash(baseline),'materialized':True}; return self.store.append(receipt)
