import pytest

np = pytest.importorskip("numpy")

from pimage.effects import apply_effect


def test_apply_effect_noir_outputs_gray_channels() -> None:
    frame = np.array([[[10, 100, 200]]], dtype=np.uint8)
    out = apply_effect(frame, "noir")
    assert out[0, 0, 0] == out[0, 0, 1] == out[0, 0, 2]


def test_apply_effect_unknown_is_identity_shape() -> None:
    frame = np.zeros((4, 5, 3), dtype=np.uint8)
    out = apply_effect(frame, "none")
    assert out.shape == frame.shape
