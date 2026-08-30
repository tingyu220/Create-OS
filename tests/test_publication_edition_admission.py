from pathlib import Path
import pytest
from creative_os.domains.publication_edition import ActivePublicationEdition, bind_edition

def test_legacy_projects_have_explicit_edition_projection(tmp_path):
    edition=ActivePublicationEdition.load(tmp_path)
    assert edition.edition_id == 'legacy-default'

def test_edition_binding_rejects_stale_value(tmp_path):
    edition=ActivePublicationEdition.load(tmp_path)
    with pytest.raises(ValueError, match='stale_publication_edition'):
        edition.require('source-v1')

def test_binding_is_restart_stable(tmp_path):
    assert bind_edition({},tmp_path)==bind_edition({},tmp_path)
