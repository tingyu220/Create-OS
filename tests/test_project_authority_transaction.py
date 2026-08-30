from pathlib import Path
import pytest
from creative_os.domains.project_authority_transaction import ProjectAuthorityTransaction, ProjectAuthorityLockError

def test_nested_or_foreign_lock_context_is_rejected(tmp_path: Path):
    tx=ProjectAuthorityTransaction(tmp_path)
    with tx.acquire() as context:
        with pytest.raises(ProjectAuthorityLockError, match="nested"):
            tx.acquire().__enter__()
        with pytest.raises(ProjectAuthorityLockError, match="identity"):
            tx.assert_context(type(context)(context.project_root, "foreign", context.owner_thread, context.process_id))

def test_lock_context_allows_owner_internal_method_only_under_same_lock(tmp_path: Path):
    tx=ProjectAuthorityTransaction(tmp_path)
    with tx.acquire() as context:
        assert tx.assert_context(context) is True
    with pytest.raises(ProjectAuthorityLockError):
        tx.assert_context(context)

def test_domain_record_then_checkpoint_recovery_is_idempotent(tmp_path: Path):
    tx=ProjectAuthorityTransaction(tmp_path)
    operation="op-1"
    with tx.acquire() as context:
        assert tx.recover_operation(operation, domain_record_hash="a"*64, checkpoint_hash=None) == "append_checkpoint"
    with tx.acquire() as context:
        assert tx.recover_operation(operation, domain_record_hash="a"*64, checkpoint_hash="b"*64) == "complete"
