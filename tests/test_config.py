from pathlib import Path

import pytest

from pimage.config import ConfigError, load_config


def test_load_config_writes_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    cfg = load_config(path)
    assert cfg.screen_w == 800
    assert path.exists()


def test_load_config_rejects_invalid_screen(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text('{"screen": {"width": "oops"}}', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)
