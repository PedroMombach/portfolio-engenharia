"""Atomic local writes and portable archive member names."""

import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path


def atomic_write(path: Path, writer: Callable[[Path], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, suffix=path.suffix)
    os.close(handle)
    temporary = Path(name)
    try:
        writer(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def slug(value: str) -> str:
    return re.sub(r"[^\w-]+", "_", value, flags=re.UNICODE).strip("_")[:80] or "document"
