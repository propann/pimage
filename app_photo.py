#!/usr/bin/env python3
"""Mini camera app for Raspberry Pi 4 / CM4 with touchscreen-first controls.

Features:
- Live preview via Picamera2 + pygame display
- One-tap photo capture
- Quick setting panels (exposure/awb/color/focus-ish controls)
- "Glitch" presets for creative looks

Designed for DSI touch displays in landscape.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pygame

try:
    from picamera2 import Picamera2
except ImportError:  # pragma: no cover - not available on non-RPi dev machines
    Picamera2 = None


SCREEN_W = 800
SCREEN_H = 480
PANEL_W = 320
PREVIEW_W = SCREEN_W - PANEL_W
BUTTON_H = 56
MARGIN = 12
PHOTO_DIR = Path.home() / "photos"


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


GLITCH_PRESETS = {
    "clean": {
        "Saturation": 1.0,
        "Contrast": 1.0,
        "Sharpness": 1.0,
        "Brightness": 0.0,
        "ExposureValue": 0.0,
    },
    "acid": {
        "Saturation": 2.0,
        "Contrast": 1.4,
        "Sharpness": 2.0,
        "Brightness": 0.15,
        "ExposureValue": 0.5,
    },
    "noir": {
        "Saturation": 0.0,
        "Contrast": 1.6,
        "Sharpness": 1.8,
        "Brightness": -0.05,
        "ExposureValue": -0.7,
    },
    "dream": {
        "Saturation": 1.5,
        "Contrast": 0.7,
        "Sharpness": 0.1,
        "Brightness": 0.25,
        "ExposureValue": 0.3,
    },
    "burn": {
        "Saturation": 1.8,
        "Contrast": 1.9,
        "Sharpness": 2.3,
        "Brightness": 0.35,
        "ExposureValue": 1.3,
    },
}


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
        self.font = pygame.font.SysFont("DejaVuSans", 23)
        self.small = pygame.font.SysFont("DejaVuSans", 18)

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

        self.message = "Ready"
        self.message_until = 0.0
        self.last_capture = "-"
        self.apply_all_controls()

    def notify(self, text: str, timeout: float = 1.6) -> None:
        self.message = text
        self.message_until = time.time() + timeout

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

    def apply_glitch(self, name: str) -> None:
        preset = GLITCH_PRESETS[name]
        for param in self.params:
            if param.key in preset:
                param.value = preset[param.key]
        self.apply_all_controls()
        self.notify(f"Mode {name}")

    def capture(self) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = PHOTO_DIR / f"img_{ts}.jpg"
        self.camera.capture_file(str(path))
        self.last_capture = path.name
        self.notify(f"Saved {path.name}", timeout=2.2)

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
        elif action.startswith("glitch:"):
            self.apply_glitch(action.split(":", 1)[1])

    def buttons(self) -> List[Tuple[pygame.Rect, str, str]]:
        x = PREVIEW_W + MARGIN
        y = MARGIN
        w = PANEL_W - 2 * MARGIN
        out: List[Tuple[pygame.Rect, str, str]] = []

        def add(title: str, action: str) -> None:
            nonlocal y
            rect = pygame.Rect(x, y, w, BUTTON_H)
            out.append((rect, title, action))
            y += BUTTON_H + 8

        add("CAPTURE", "capture")
        add("PARAM -", "param_down")
        add("PARAM +", "param_up")
        add("PARAM PREV", "prev")
        add("PARAM NEXT", "next")
        add("AE ON/OFF", "toggle_ae")
        add("AWB NEXT", "next_awb")
        add("GLITCH ACID", "glitch:acid")
        add("GLITCH NOIR", "glitch:noir")
        add("GLITCH DREAM", "glitch:dream")
        add("GLITCH BURN", "glitch:burn")
        add("RESET CLEAN", "glitch:clean")
        add("QUIT", "quit")
        return out

    def draw(self, frame) -> None:
        surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
        self.screen.blit(surf, (0, 0))

        panel = pygame.Rect(PREVIEW_W, 0, PANEL_W, SCREEN_H)
        pygame.draw.rect(self.screen, (18, 18, 18), panel)

        for i, (rect, title, _action) in enumerate(self.buttons()):
            color = (55, 55, 55)
            if i == self.selected + 1:
                color = (95, 85, 50)
            pygame.draw.rect(self.screen, color, rect, border_radius=8)
            pygame.draw.rect(self.screen, (120, 120, 120), rect, width=2, border_radius=8)
            label = self.small.render(title, True, (230, 230, 230))
            self.screen.blit(label, (rect.x + 12, rect.y + 17))

        param = self.params[self.selected]
        status = [
            f"Param: {param.label} = {param.value:.2f}",
            f"AE: {'ON' if self.auto_exposure else 'OFF'}",
            f"AWB: {self.awb_modes[self.awb_mode_idx][0]}",
            f"Last: {self.last_capture}",
        ]
        y = SCREEN_H - 100
        pygame.draw.rect(self.screen, (0, 0, 0), (0, y, PREVIEW_W, 100))
        for line in status:
            txt = self.small.render(line, True, (240, 240, 240))
            self.screen.blit(txt, (14, y + 6))
            y += 22

        if time.time() < self.message_until:
            msg = self.font.render(self.message, True, (255, 220, 120))
            self.screen.blit(msg, (18, 16))

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
                            self.handle_action("prev")
                        if event.key == pygame.K_RIGHT:
                            self.handle_action("next")
                        if event.key == pygame.K_a:
                            self.handle_action("toggle_ae")
                        if event.key == pygame.K_w:
                            self.handle_action("next_awb")
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
