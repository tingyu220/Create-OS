from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl


_LOCKS: dict[str, threading.RLock] = {}
_GUARD = threading.Lock()
_DEPTH = threading.local()


@contextmanager
def project_authority_lock(project_root: str | Path) -> Iterator[None]:
    root = Path(project_root).absolute()
    path = root / ".creative_os" / "memory" / "contracts" / ".project-authority.lock"
    key = str(path)
    with _GUARD:
        lock = _LOCKS.setdefault(key, threading.RLock())
    with lock:
        depths = getattr(_DEPTH, "values", {})
        depth = depths.get(key, 0)
        if depth:
            depths[key] = depth + 1
            _DEPTH.values = depths
            try:
                yield
            finally:
                depths[key] -= 1
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"\0"); stream.flush()
            stream.seek(0)
            if os.name == "nt": msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else: fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            depths[key] = 1; _DEPTH.values = depths
            try:
                yield
            finally:
                depths.pop(key, None)
                stream.seek(0)
                if os.name == "nt": msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
