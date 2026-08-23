from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os, threading, uuid
from creative_os.domains.project_authority import project_authority_lock

class ProjectAuthorityLockError(RuntimeError): pass

@dataclass(frozen=True, slots=True)
class LockContext:
    project_root: str
    lock_id: str
    owner_thread: int
    process_id: int

class ProjectAuthorityTransaction:
    _active=threading.local()
    def __init__(self, project_root:str|Path): self.project_root=Path(project_root).absolute()
    def acquire(self): return _TransactionScope(self)
    def _enter(self):
        if getattr(self._active,'context',None) is not None: raise ProjectAuthorityLockError('nested lock rejected')
        cm=project_authority_lock(self.project_root); cm.__enter__()
        ctx=LockContext(str(self.project_root),uuid.uuid4().hex,threading.get_ident(),os.getpid()); self._active.context=ctx
        return cm,ctx
    def _exit(self,cm): self._active.context=None; cm.__exit__(None,None,None)
    def assert_context(self, context:LockContext):
        active=getattr(self._active,'context',None)
        if active is None or context != active or context.project_root != str(self.project_root) or context.owner_thread != threading.get_ident() or context.process_id != os.getpid(): raise ProjectAuthorityLockError('lock context identity invalid')
        return True
    def recover_operation(self, operation_id:str, *, domain_record_hash:str, checkpoint_hash:str|None):
        if not operation_id or len(domain_record_hash)!=64: raise ProjectAuthorityLockError('operation binding invalid')
        if checkpoint_hash is None: return 'append_checkpoint'
        if len(checkpoint_hash)!=64: raise ProjectAuthorityLockError('checkpoint binding invalid')
        return 'complete'

class _TransactionScope:
    def __init__(self, owner): self.owner=owner; self.cm=None; self.context=None
    def __enter__(self): self.cm,self.context=self.owner._enter(); return self.context
    def __exit__(self, exc_type, exc, tb): self.owner._exit(self.cm)
