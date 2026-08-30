import json
from creative_os.domains.source_contract_candidate import *
def test_candidate_hash_roundtrip():
 v=ContractCandidate('narrative-chapter-005',1,{'narrative_goal':'continue'},(EvidenceBinding('source-edition-x',5,1,0,'a'*64,'intent'),),('missing_pov',))
 assert json.loads(encode_candidate(v))['candidate_hash']==v.candidate_hash
