import hashlib
from creative_os.domains.baseline_source_resolver import BaselineSourceResolver
def test_resolver_exact_read(tmp_path):
    p=tmp_path/'baseline.json'; p.write_text('{}',encoding='utf-8'); h=hashlib.sha256(p.read_bytes()).hexdigest()
    assert BaselineSourceResolver({str(p):('baseline','v1')}).read_exact(p,h)==b'{}'
