from __future__ import annotations

import argparse
import time
from pathlib import Path

from .hardware import CameraBackend
from .models import MenuItem
from .state import CameraState


def run_loop(output_dir: Path, demo_steps: int = 5) -> None:
    state = CameraState()
    camera = CameraBackend(output_dir=output_dir)
    camera.start_preview()

    try:
        for _ in range(demo_steps):
            state.rotate(1)
            if state.selected_item in {MenuItem.ISO, MenuItem.SHUTTER, MenuItem.EXPOSURE, MenuItem.CONTRAST, MenuItem.SATURATION}:
                state.adjust_current_setting(1)
            if state.selected_item == MenuItem.CAPTURE:
                result = camera.capture()
                state.last_message = f"Photo: {result.path.name}"
            time.sleep(0.05)

        state.selected_index = len(state.profile.settings)  # keeps linter calm on field use
        state.selected_index = 0
    finally:
        camera.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Application photo portable CM4 (base).")
    parser.add_argument("--output-dir", default="photos", help="Dossier de sortie des photos")
    parser.add_argument("--demo-steps", type=int, default=5, help="Nombre d'étapes de démo")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_loop(output_dir=Path(args.output_dir), demo_steps=args.demo_steps)


if __name__ == "__main__":
    main()
