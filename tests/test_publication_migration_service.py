from pathlib import Path
import pytest
from creative_os.domains.publication_migration_service import PublicationMigrationService

def test_service_exposes_isolated_target_and_exact_manifest(tmp_path):
    service=PublicationMigrationService(tmp_path)
    assert service.target_root.name == 'civilization-publication-v2'
    with pytest.raises(ValueError, match='manifest_exact'):
        service.snapshot('missing', 'a'*64)

def test_service_rejects_wrong_edition_and_drift(tmp_path):
    service=PublicationMigrationService(tmp_path, target_edition_id='target-v2')
    with pytest.raises(ValueError, match='edition'):
        service.rebuild_content_batch('m1','b1',1,2,source_edition_id='target-v2')

def test_service_recovery_reads_store_not_caller_fixture(tmp_path):
    service=PublicationMigrationService(tmp_path)
    with pytest.raises(ValueError, match='manifest_exact'):
        service.verify_batch('m1','b1','a'*64)
