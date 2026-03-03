from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DEFAULT_SCREEN_W = 800
DEFAULT_SCREEN_H = 480
DEFAULT_PANEL_W = 320
CONFIG_FILE = Path("config.yaml")
LEGACY_CONFIG_FILE = Path("config.json")


class ConfigError(ValueError):
    """Raised when configuration cannot be validated."""


@dataclass
class AppConfig:
    photos_path: str = str(Path.home() / "photos")
    screen_w: int = DEFAULT_SCREEN_W
    screen_h: int = DEFAULT_SCREEN_H
    panel_w: int = DEFAULT_PANEL_W
    camera_index: int = 0
    camera2_enabled: bool = False
    default_grid: str = "thirds"
    fan_pwm: int = 35

    def to_dict(self) -> Dict[str, object]:
        return {
            "paths": {"photos": self.photos_path},
            "screen": {"width": self.screen_w, "height": self.screen_h, "panel_width": self.panel_w},
            "camera": {"index": self.camera_index, "sensor2_enabled": self.camera2_enabled},
            "overlay": {"default_grid": self.default_grid, "histogram_interval_ms": 500},
            "cooling": {"fan_pwm": self.fan_pwm, "curve": [[45, 25], [60, 55], [75, 90]]},
        }


def _as_int(data: Dict[str, Any], section: str, key: str, default: int, minimum: int, maximum: int) -> int:
    value = data.get(section, {}).get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{section}.{key} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise ConfigError(f"{section}.{key} must be between {minimum} and {maximum}")
    return parsed


def load_config(path: Path = CONFIG_FILE) -> AppConfig:
    cfg = AppConfig()
    if not path.exists() and LEGACY_CONFIG_FILE.exists():
        raw = json.loads(LEGACY_CONFIG_FILE.read_text(encoding="utf-8"))
    elif path.exists():
        text = path.read_text(encoding="utf-8")
        if yaml is not None:
            raw = yaml.safe_load(text) or {}
        else:
            try:
                raw = json.loads(text) if text.strip() else {}
            except json.JSONDecodeError:
                raw = {}
    else:
        raw = {}

    if raw:
        cfg.photos_path = str(raw.get("paths", {}).get("photos", cfg.photos_path))
        cfg.screen_w = _as_int(raw, "screen", "width", cfg.screen_w, 320, 4096)
        cfg.screen_h = _as_int(raw, "screen", "height", cfg.screen_h, 240, 2160)
        cfg.panel_w = _as_int(raw, "screen", "panel_width", cfg.panel_w, 160, cfg.screen_w - 80)
        cfg.camera_index = _as_int(raw, "camera", "index", cfg.camera_index, 0, 4)
        cfg.camera2_enabled = bool(raw.get("camera", {}).get("sensor2_enabled", cfg.camera2_enabled))
        cfg.default_grid = str(raw.get("overlay", {}).get("default_grid", cfg.default_grid))
        cfg.fan_pwm = _as_int(raw, "cooling", "fan_pwm", cfg.fan_pwm, 0, 100)

    if yaml is not None:
        serialized = yaml.safe_dump(cfg.to_dict(), sort_keys=False, allow_unicode=True)
    else:
        serialized = json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2)
    path.write_text(serialized, encoding="utf-8")
    return cfg
