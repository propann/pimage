from __future__ import annotations

import numpy as np


def apply_effect(frame: np.ndarray, effect_name: str) -> np.ndarray:
    out = frame.astype(np.float32)
    if effect_name == "noir":
        g = out[:, :, 0] * 0.3 + out[:, :, 1] * 0.59 + out[:, :, 2] * 0.11
        out[:, :, 0] = g
        out[:, :, 1] = g
        out[:, :, 2] = g
    elif effect_name == "vintage":
        out[:, :, 0] *= 1.08
        out[:, :, 2] *= 0.82
    return np.clip(out, 0, 255).astype(np.uint8)
