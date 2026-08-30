from pathlib import Path
import hashlib

class BaselineSourceResolver:
    """跨工作树只读 exact resolver；禁止复制与路径推断。"""
    def __init__(self, allowed: dict[str, tuple[str, str]]):
        self.allowed = {str(Path(k).resolve()): v for k, v in allowed.items()}
    def read_exact(self, path: str | Path, expected_hash: str) -> bytes:
        key=str(Path(path).resolve())
        if key not in self.allowed: raise ValueError("source_not_registered")
        data=Path(key).read_bytes()
        if hashlib.sha256(data).hexdigest()!=expected_hash: raise ValueError("source_hash_drift")
        return data
