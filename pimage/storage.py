from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class StorageStatus:
    free_bytes: int
    total_bytes: int
    read_only: bool


def get_storage_status(path: Path) -> StorageStatus:
    usage = shutil.disk_usage(path)
    read_only = not os.access(path, os.W_OK)
    return StorageStatus(free_bytes=usage.free, total_bytes=usage.total, read_only=read_only)


def build_capture_filename(prefix: str = "img", profile: str = "default", ext: str = ".jpg") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}_{profile}{ext}"


def atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def enforce_quota(photo_dir: Path, quota_bytes: int) -> int:
    files = sorted((f for f in photo_dir.glob("*.jpg") if f.is_file()), key=lambda p: p.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    removed = 0
    for file_path in files:
        if total <= quota_bytes:
            break
        size = file_path.stat().st_size
        file_path.unlink(missing_ok=True)
        total -= size
        removed += 1
    return removed
