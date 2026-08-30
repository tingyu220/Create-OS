from pathlib import Path
import hashlib,json,os
from creative_os.domains.project_authority import project_authority_lock
from creative_os.domains.contract_fulfillment_store import ContractFulfillmentStore

class ContractFulfillmentReviewer:
    def __init__(self, project_root:str|Path):
        self.project_root=Path(project_root); self.root=self.project_root/'.creative_os'/'fulfillment-review'; self.path=self.root/'records.jsonl'
        self.store=ContractFulfillmentStore(self.project_root)
    @staticmethod
    def _canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    def append_verified_records(self, artifact):
        if set(artifact)!={"contract_hash","artifact_hash","evidence"} or len(artifact['contract_hash'])!=64 or len(artifact['artifact_hash'])!=64: raise ValueError('artifact_hash')
        for ev in artifact['evidence']:
            if set(ev)!={"field_path","source_id","source_version","source_hash"} or len(ev['source_hash'])!=64: raise ValueError('evidence_binding')
        rec={"contract_hash":artifact['contract_hash'],"artifact_hash":artifact['artifact_hash'],"evidence":artifact['evidence']}
        rec['record_hash']=hashlib.sha256(self._canon(rec).encode()).hexdigest()
        with project_authority_lock(self.project_root):
            current=self._read()
            if any(x==rec for x in current): return tuple(current)
            self.root.mkdir(parents=True,exist_ok=True)
            with self.path.open('a',encoding='utf-8',newline='\n') as f:f.write(self._canon(rec)+'\n');f.flush();os.fsync(f.fileno())
            return tuple(current+[rec])

    def append(self, artifact):
        """Append exact fulfillment evidence through the authority Store.

        Full production payloads may provide prevalidated ContractFulfillmentEvidenceRecord
        instances under ``records``; the compact legacy payload remains supported for
        compatibility and is still durably recorded for audit.
        """
        records = artifact.get("records") if isinstance(artifact, dict) else None
        if records is not None:
            appended = tuple(self.store.append(record) for record in records)
            return appended
        return self.append_verified_records(artifact)

    def recover(self):
        return self.store.recover()
    def _read(self): return [json.loads(x) for x in self.path.read_text(encoding='utf-8').splitlines()] if self.path.exists() else []
    def active(self, contract_hash):
        legacy = tuple(x for x in self._read() if x['contract_hash'] == contract_hash)
        if legacy:
            return legacy
        try:
            return self.store.active_records(contract_hash, 1, contract_hash)
        except Exception:
            return ()
