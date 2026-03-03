from src.pimage_camera.models import MenuItem
from src.pimage_camera.state import CameraState


def test_rotate_wraps_menu():
    state = CameraState()
    for _ in range(20):
        state.rotate(1)
    assert state.selected_item in MenuItem


def test_quit_stops_running():
    state = CameraState()
    while state.selected_item != MenuItem.QUIT:
        state.rotate(1)
    state.click()
    assert state.running is False


def test_adjust_iso_updates_value():
    state = CameraState()
    while state.selected_item != MenuItem.ISO:
        state.rotate(1)
    previous = state.profile.settings[MenuItem.ISO].value
    state.adjust_current_setting(1)
    assert state.profile.settings[MenuItem.ISO].value == previous + 100
