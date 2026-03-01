#!/usr/bin/env python3
"""Mini camera app for Raspberry Pi 4 / CM4 with touchscreen-first controls.

Features:
- Live preview via Picamera2 + pygame display
- One-tap photo capture
- Quick setting panels (exposure/awb/color/focus-ish controls)
- Creative color profiles, realtime effects, and persistent user slots
- Multiple framing grids overlay modes

Designed for DSI touch displays in landscape.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pygame

try:
    from picamera2 import Picamera2
except ImportError:  # pragma: no cover - not available on non-RPi dev machines
    Picamera2 = None


SCREEN_W = 800
SCREEN_H = 480
PANEL_W = 320
PREVIEW_W = SCREEN_W - PANEL_W
BUTTON_H = 46
MARGIN = 10
PHOTO_DIR = Path.home() / "photos"
PROFILE_FILE = Path.home() / ".pimage_profiles.json"
GRID_COLOR = (0, 220, 180)


@dataclass
class CameraParam:
    label: str
    key: str
    min_val: float
    max_val: float
    step: float
    value: float

    def inc(self) -> None:
        self.value = min(self.max_val, self.value + self.step)

    def dec(self) -> None:
        self.value = max(self.min_val, self.value - self.step)


class Menu(str, Enum):
    CAPTURE = "Capture"
    TUNE = "Tune"
    COLOR = "Color"
    EFFECT = "Effect"
    SYSTEM = "System"


COLOR_PROFILES: Dict[str, Dict[str, float]] = {
    "natural": {"Saturation": 1.0, "Contrast": 1.0, "Sharpness": 1.0, "Brightness": 0.0},
    "vivid": {"Saturation": 1.8, "Contrast": 1.25, "Sharpness": 1.5, "Brightness": 0.05},
    "cinema": {"Saturation": 0.85, "Contrast": 0.92, "Sharpness": 0.7, "Brightness": -0.02},
    "mono": {"Saturation": 0.0, "Contrast": 1.45, "Sharpness": 1.4, "Brightness": 0.0},
    "retro": {"Saturation": 1.2, "Contrast": 0.88, "Sharpness": 0.5, "Brightness": 0.12},
}

EFFECTS = ["none", "noir", "vintage", "cyber", "thermal"]
GRIDS = [
    "off",
    "thirds",
    "quarters",
    "crosshair",
    "diagonal-x",
    "triangles",
    "golden-phi",
    "dense-6x6",
]


class CameraApp:
    def __init__(self) -> None:
        if Picamera2 is None:
            raise RuntimeError(
                "Picamera2 is not installed. Use Raspberry Pi OS + sudo apt install python3-picamera2"
            )

        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        pygame.init()
        pygame.display.set_caption("PImage Camera")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("DejaVuSans", 21)
        self.small = pygame.font.SysFont("DejaVuSans", 17)

        self.camera = Picamera2()
        config = self.camera.create_preview_configuration(
            main={"size": (PREVIEW_W, SCREEN_H), "format": "RGB888"},
            buffer_count=3,
        )
        self.camera.configure(config)
        self.camera.start()

        self.params: List[CameraParam] = [
            CameraParam("Expo EV", "ExposureValue", -8.0, 8.0, 0.2, 0.0),
            CameraParam("Gain", "AnalogueGain", 1.0, 16.0, 0.2, 1.0),
            CameraParam("Bright", "Brightness", -1.0, 1.0, 0.05, 0.0),
            CameraParam("Contrast", "Contrast", 0.0, 2.5, 0.05, 1.0),
            CameraParam("Saturation", "Saturation", 0.0, 3.0, 0.05, 1.0),
            CameraParam("Sharp", "Sharpness", 0.0, 4.0, 0.1, 1.0),
            CameraParam("Exposure µs", "ExposureTime", 100, 30000, 100, 8000),
        ]
        self.selected = 0
        self.auto_exposure = True
        self.awb_mode_idx = 0
        self.awb_modes: List[Tuple[str, int]] = [
            ("Auto", 0),
            ("Tungsten", 1),
            ("Fluo", 2),
            ("Indoor", 3),
            ("Daylight", 4),
            ("Cloudy", 5),
        ]

        self.menu_order = [Menu.CAPTURE, Menu.TUNE, Menu.COLOR, Menu.EFFECT, Menu.SYSTEM]
        self.menu_idx = 0
        self.color_profile = "natural"
        self.effect_idx = 0
        self.grid_idx = 1

        self.message = "Ready"
        self.message_until = 0.0
        self.last_capture = "-"
        self.hardware_summary = self.describe_hardware()

        self.apply_color_profile("natural", notify=False)
        self.apply_all_controls()

    def notify(self, text: str, timeout: float = 1.6) -> None:
        self.message = text
        self.message_until = time.time() + timeout

    def describe_hardware(self) -> str:
        try:
            controls = getattr(self.camera, "camera_controls", {})
            ccount = len(controls)
            sensor = self.camera.camera_properties.get("Model", "Unknown")
            return f"Sensor={sensor} controls={ccount}"
        except Exception:
            return "Sensor info unavailable"

    def save_profile(self, slot: str) -> None:
        payload = {
            "auto_exposure": self.auto_exposure,
            "awb_mode_idx": self.awb_mode_idx,
            "color_profile": self.color_profile,
            "effect_idx": self.effect_idx,
            "grid_idx": self.grid_idx,
            "params": {p.key: p.value for p in self.params},
        }
        data = {}
        if PROFILE_FILE.exists():
            data = json.loads(PROFILE_FILE.read_text())
        data[slot] = payload
        PROFILE_FILE.write_text(json.dumps(data, indent=2))
        self.notify(f"Profile {slot} saved")

    def load_profile(self, slot: str) -> None:
        if not PROFILE_FILE.exists():
            self.notify("No saved profile file")
            return
        data = json.loads(PROFILE_FILE.read_text())
        if slot not in data:
            self.notify(f"Slot {slot} is empty")
            return
        saved = data[slot]
        self.auto_exposure = bool(saved.get("auto_exposure", True))
        self.awb_mode_idx = int(saved.get("awb_mode_idx", 0)) % len(self.awb_modes)
        self.effect_idx = int(saved.get("effect_idx", 0)) % len(EFFECTS)
        self.grid_idx = int(saved.get("grid_idx", 1)) % len(GRIDS)
        self.color_profile = str(saved.get("color_profile", "natural"))

        values = saved.get("params", {})
        for param in self.params:
            if param.key in values:
                param.value = float(values[param.key])
        self.apply_all_controls()
        self.notify(f"Profile {slot} loaded")

    def apply_all_controls(self) -> None:
        controls: Dict[str, float | int | bool] = {
            "AeEnable": self.auto_exposure,
            "AwbMode": self.awb_modes[self.awb_mode_idx][1],
        }
        for param in self.params:
            if param.key == "ExposureTime" and self.auto_exposure:
                continue
            controls[param.key] = int(param.value) if param.key == "ExposureTime" else param.value
        self.camera.set_controls(controls)

    def apply_color_profile(self, name: str, notify: bool = True) -> None:
        if name not in COLOR_PROFILES:
            return
        self.color_profile = name
        for param in self.params:
            if param.key in COLOR_PROFILES[name]:
                param.value = COLOR_PROFILES[name][param.key]
        self.apply_all_controls()
        if notify:
            self.notify(f"Color profile: {name}")

    def cycle_color_profile(self, direction: int = 1) -> None:
        names = list(COLOR_PROFILES.keys())
        idx = names.index(self.color_profile)
        self.apply_color_profile(names[(idx + direction) % len(names)])

    def cycle_effect(self, direction: int = 1) -> None:
        self.effect_idx = (self.effect_idx + direction) % len(EFFECTS)
        self.notify(f"Effect: {EFFECTS[self.effect_idx]}")

    def cycle_grid(self, direction: int = 1) -> None:
        self.grid_idx = (self.grid_idx + direction) % len(GRIDS)
        self.notify(f"Grid: {GRIDS[self.grid_idx]}")

    def apply_effect(self, frame: np.ndarray) -> np.ndarray:
        effect = EFFECTS[self.effect_idx]
        out = frame.astype(np.float32)

        if effect == "noir":
            gray = out[:, :, 0] * 0.3 + out[:, :, 1] * 0.59 + out[:, :, 2] * 0.11
            out[:, :, 0] = gray
            out[:, :, 1] = gray
            out[:, :, 2] = gray
        elif effect == "vintage":
            out[:, :, 0] *= 1.10
            out[:, :, 1] *= 1.0
            out[:, :, 2] *= 0.82
        elif effect == "cyber":
            out[:, :, 0] *= 0.7
            out[:, :, 1] *= 1.25
            out[:, :, 2] *= 1.3
        elif effect == "thermal":
            lum = (out[:, :, 0] + out[:, :, 1] + out[:, :, 2]) / 3.0
            out[:, :, 0] = np.clip((lum - 64) * 2.5, 0, 255)
            out[:, :, 1] = np.clip((lum - 16) * 1.7, 0, 255)
            out[:, :, 2] = np.clip(255 - lum * 1.2, 0, 255)

        return np.clip(out, 0, 255).astype(np.uint8)

    def draw_grid(self) -> None:
        mode = GRIDS[self.grid_idx]
        if mode == "off":
            return

        w, h = PREVIEW_W, SCREEN_H
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)

        def vline(x: float, alpha: int = 165, thick: int = 1) -> None:
            pygame.draw.line(overlay, (*GRID_COLOR, alpha), (int(x), 0), (int(x), h), thick)

        def hline(y: float, alpha: int = 165, thick: int = 1) -> None:
            pygame.draw.line(overlay, (*GRID_COLOR, alpha), (0, int(y)), (w, int(y)), thick)

        if mode == "thirds":
            vline(w / 3)
            vline(2 * w / 3)
            hline(h / 3)
            hline(2 * h / 3)
        elif mode == "quarters":
            for i in range(1, 4):
                vline((w / 4) * i)
                hline((h / 4) * i)
        elif mode == "crosshair":
            vline(w / 2, alpha=190, thick=2)
            hline(h / 2, alpha=190, thick=2)
        elif mode == "diagonal-x":
            pygame.draw.line(overlay, (*GRID_COLOR, 160), (0, 0), (w, h), 1)
            pygame.draw.line(overlay, (*GRID_COLOR, 160), (w, 0), (0, h), 1)
        elif mode == "triangles":
            # Dynamic symmetry-ish aid: one diagonal + two triangles from opposite corners.
            pygame.draw.line(overlay, (*GRID_COLOR, 170), (0, h), (w, 0), 1)
            pygame.draw.line(overlay, (*GRID_COLOR, 150), (0, 0), (w * 0.5, h), 1)
            pygame.draw.line(overlay, (*GRID_COLOR, 150), (w, h), (w * 0.5, 0), 1)
        elif mode == "golden-phi":
            phi = 0.61803398875
            vline(w * phi)
            vline(w * (1 - phi))
            hline(h * phi)
            hline(h * (1 - phi))
        elif mode == "dense-6x6":
            for i in range(1, 6):
                vline((w / 6) * i, alpha=120)
                hline((h / 6) * i, alpha=120)

        self.screen.blit(overlay, (0, 0))

    def capture(self) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = PHOTO_DIR / f"img_{ts}.jpg"
        self.camera.capture_file(str(path))
        self.last_capture = path.name
        self.notify(f"Saved {path.name}", timeout=2.2)

    def current_menu(self) -> Menu:
        return self.menu_order[self.menu_idx]

    def handle_action(self, action: str) -> None:
        if action == "capture":
            self.capture()
        elif action == "quit":
            raise SystemExit
        elif action == "param_up":
            self.params[self.selected].inc()
            self.apply_all_controls()
        elif action == "param_down":
            self.params[self.selected].dec()
            self.apply_all_controls()
        elif action == "next":
            self.selected = (self.selected + 1) % len(self.params)
        elif action == "prev":
            self.selected = (self.selected - 1) % len(self.params)
        elif action == "toggle_ae":
            self.auto_exposure = not self.auto_exposure
            self.apply_all_controls()
            self.notify(f"AE {'ON' if self.auto_exposure else 'OFF'}")
        elif action == "next_awb":
            self.awb_mode_idx = (self.awb_mode_idx + 1) % len(self.awb_modes)
            self.apply_all_controls()
            self.notify(f"AWB {self.awb_modes[self.awb_mode_idx][0]}")
        elif action == "profile_next":
            self.cycle_color_profile(1)
        elif action == "profile_prev":
            self.cycle_color_profile(-1)
        elif action == "effect_next":
            self.cycle_effect(1)
        elif action == "effect_prev":
            self.cycle_effect(-1)
        elif action == "grid_next":
            self.cycle_grid(1)
        elif action == "grid_prev":
            self.cycle_grid(-1)
        elif action == "menu_next":
            self.menu_idx = (self.menu_idx + 1) % len(self.menu_order)
        elif action == "menu_prev":
            self.menu_idx = (self.menu_idx - 1) % len(self.menu_order)
        elif action.startswith("save:"):
            self.save_profile(action.split(":", 1)[1])
        elif action.startswith("load:"):
            self.load_profile(action.split(":", 1)[1])

    def menu_buttons(self) -> List[Tuple[str, str]]:
        menu = self.current_menu()
        if menu == Menu.CAPTURE:
            return [
                ("CAPTURE", "capture"),
                ("GRID PREV", "grid_prev"),
                ("GRID NEXT", "grid_next"),
                ("NEXT MENU", "menu_next"),
                ("PREV MENU", "menu_prev"),
                ("QUIT", "quit"),
            ]
        if menu == Menu.TUNE:
            return [
                ("PARAM -", "param_down"),
                ("PARAM +", "param_up"),
                ("PARAM PREV", "prev"),
                ("PARAM NEXT", "next"),
                ("AE ON/OFF", "toggle_ae"),
                ("AWB NEXT", "next_awb"),
                ("NEXT MENU", "menu_next"),
            ]
        if menu == Menu.COLOR:
            return [
                ("PROFILE PREV", "profile_prev"),
                ("PROFILE NEXT", "profile_next"),
                ("SAVE SLOT A", "save:A"),
                ("LOAD SLOT A", "load:A"),
                ("SAVE SLOT B", "save:B"),
                ("LOAD SLOT B", "load:B"),
                ("NEXT MENU", "menu_next"),
            ]
        if menu == Menu.EFFECT:
            return [
                ("EFFECT PREV", "effect_prev"),
                ("EFFECT NEXT", "effect_next"),
                ("GRID PREV", "grid_prev"),
                ("GRID NEXT", "grid_next"),
                ("CAPTURE", "capture"),
                ("NEXT MENU", "menu_next"),
                ("PREV MENU", "menu_prev"),
            ]
        return [
            ("GRID PREV", "grid_prev"),
            ("GRID NEXT", "grid_next"),
            ("SAVE SLOT A", "save:A"),
            ("LOAD SLOT A", "load:A"),
            ("SAVE SLOT B", "save:B"),
            ("LOAD SLOT B", "load:B"),
            ("NEXT MENU", "menu_next"),
        ]

    def buttons(self) -> List[Tuple[pygame.Rect, str, str]]:
        x = PREVIEW_W + MARGIN
        y = 60
        w = PANEL_W - 2 * MARGIN
        out: List[Tuple[pygame.Rect, str, str]] = []

        for title, action in self.menu_buttons():
            rect = pygame.Rect(x, y, w, BUTTON_H)
            out.append((rect, title, action))
            y += BUTTON_H + 7
        return out

    def draw(self, frame: np.ndarray) -> None:
        frame_fx = self.apply_effect(frame)
        surf = pygame.surfarray.make_surface(frame_fx.swapaxes(0, 1))
        self.screen.blit(surf, (0, 0))
        self.draw_grid()

        panel = pygame.Rect(PREVIEW_W, 0, PANEL_W, SCREEN_H)
        pygame.draw.rect(self.screen, (18, 18, 18), panel)

        title = self.font.render(f"MENU: {self.current_menu().value}", True, (235, 235, 235))
        self.screen.blit(title, (PREVIEW_W + MARGIN, 16))

        for rect, title, _action in self.buttons():
            color = (55, 55, 55)
            pygame.draw.rect(self.screen, color, rect, border_radius=8)
            pygame.draw.rect(self.screen, (120, 120, 120), rect, width=2, border_radius=8)
            label = self.small.render(title, True, (230, 230, 230))
            self.screen.blit(label, (rect.x + 12, rect.y + 13))

        param = self.params[self.selected]
        status = [
            f"Param: {param.label} = {param.value:.2f}",
            f"AE: {'ON' if self.auto_exposure else 'OFF'} / AWB: {self.awb_modes[self.awb_mode_idx][0]}",
            f"Profile: {self.color_profile} / Effect: {EFFECTS[self.effect_idx]}",
            f"Grid: {GRIDS[self.grid_idx]}",
            f"Last: {self.last_capture}",
            self.hardware_summary,
        ]
        y = SCREEN_H - 130
        pygame.draw.rect(self.screen, (0, 0, 0), (0, y, PREVIEW_W, 130))
        for line in status:
            txt = self.small.render(line, True, (240, 240, 240))
            self.screen.blit(txt, (12, y + 4))
            y += 21

        if time.time() < self.message_until:
            msg = self.font.render(self.message, True, (255, 220, 120))
            self.screen.blit(msg, (16, 14))

        pygame.display.flip()

    def click(self, pos: Tuple[int, int]) -> None:
        for rect, _title, action in self.buttons():
            if rect.collidepoint(pos):
                self.handle_action(action)
                return

    def run(self) -> None:
        try:
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        raise SystemExit
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            raise SystemExit
                        if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                            self.handle_action("capture")
                        if event.key == pygame.K_UP:
                            self.handle_action("param_up")
                        if event.key == pygame.K_DOWN:
                            self.handle_action("param_down")
                        if event.key == pygame.K_LEFT:
                            self.handle_action("menu_prev")
                        if event.key == pygame.K_RIGHT:
                            self.handle_action("menu_next")
                        if event.key == pygame.K_a:
                            self.handle_action("toggle_ae")
                        if event.key == pygame.K_w:
                            self.handle_action("next_awb")
                        if event.key == pygame.K_p:
                            self.handle_action("profile_next")
                        if event.key == pygame.K_e:
                            self.handle_action("effect_next")
                        if event.key == pygame.K_g:
                            self.handle_action("grid_next")
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        self.click(event.pos)

                frame = self.camera.capture_array()
                self.draw(frame)
                self.clock.tick(28)
        finally:
            self.camera.stop()
            pygame.quit()


def main() -> int:
    if os.geteuid() != 0:
        print("[INFO] Run from tty on Raspberry Pi for best DRM performance.")
    app = CameraApp()
    app.run()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
