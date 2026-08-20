from __future__ import annotations

import contextlib
import fcntl
import time
from pathlib import Path
from typing import Iterator


@contextlib.contextmanager
def file_lock(
    path: Path,
    *,
    timeout_seconds: float = 600.0,
    poll_seconds: float = 0.1,
) -> Iterator[None]:
    """Acquire an interprocess advisory lock stored at *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    deadline = time.monotonic() + timeout_seconds

    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for lock: {path}")
                time.sleep(poll_seconds)
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
