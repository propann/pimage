from pathlib import Path

from pimage.storage import atomic_write_bytes, build_capture_filename, enforce_quota


def test_atomic_write_bytes(tmp_path: Path) -> None:
    target = tmp_path / "x.jpg"
    atomic_write_bytes(target, b"abc")
    assert target.read_bytes() == b"abc"


def test_build_capture_filename_contains_profile() -> None:
    name = build_capture_filename(profile="vintage")
    assert name.endswith("_vintage.jpg")


def test_enforce_quota_deletes_oldest(tmp_path: Path) -> None:
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    a.write_bytes(b"a" * 10)
    b.write_bytes(b"b" * 10)
    removed = enforce_quota(tmp_path, quota_bytes=10)
    assert removed >= 1
