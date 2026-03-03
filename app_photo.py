#!/usr/bin/env python3
"""PImage camera app with animated menus, touch keyboard modal and post-capture editor."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pygame

try:
    from picamera2 import Picamera2
except ImportError:  # pragma: no cover
    Picamera2 = None

try:  # optional dependency: pip install pygame-vkeyboard
    import vkeyboard
except ImportError:  # pragma: no cover
    vkeyboard = None


SCREEN_W = 800
SCREEN_H = 480
PANEL_W = 320
PREVIEW_W = SCREEN_W - PANEL_W
BUTTON_H = 44
MARGIN = 10
CONFIG_FILE = Path("config.json")


class Menu(str, Enum):
    CAPTURE = "Capture"
    TUNE = "Tune"
    COLOR = "Color"
    EFFECT = "Effect"
    SYSTEM = "System"


class View(str, Enum):
    CAMERA = "camera"
    EDIT = "edit"


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


@dataclass
class AppConfig:
    photos_path: str = str(Path.home() / "photos")
    screen_w: int = SCREEN_W
    screen_h: int = SCREEN_H
    panel_w: int = PANEL_W
    camera_index: int = 0
    camera2_enabled: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            "paths": {"photos": self.photos_path},
            "screen": {"width": self.screen_w, "height": self.screen_h, "panel_width": self.panel_w},
            "camera": {"index": self.camera_index, "sensor2_enabled": self.camera2_enabled},
        }


def load_config(path: Path = CONFIG_FILE) -> AppConfig:
    cfg = AppConfig()
    if path.exists():
        raw = json.loads(path.read_text())
        cfg.photos_path = str(raw.get("paths", {}).get("photos", cfg.photos_path))
        cfg.screen_w = int(raw.get("screen", {}).get("width", cfg.screen_w))
        cfg.screen_h = int(raw.get("screen", {}).get("height", cfg.screen_h))
        cfg.panel_w = int(raw.get("screen", {}).get("panel_width", cfg.panel_w))
        cfg.camera_index = int(raw.get("camera", {}).get("index", cfg.camera_index))
        cfg.camera2_enabled = bool(raw.get("camera", {}).get("sensor2_enabled", cfg.camera2_enabled))
    path.write_text(json.dumps(cfg.to_dict(), indent=2))
    return cfg


class CameraApp:
    def __init__(self) -> None:
        if Picamera2 is None:
            raise RuntimeError("Picamera2 manquant sur cette machine")

        self.config = load_config()
        self.photo_dir = Path(self.config.photos_path)
        self.photo_dir.mkdir(parents=True, exist_ok=True)

        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("DejaVuSans", 22)
        self.small = pygame.font.SysFont("DejaVuSans", 17)

        self.camera = Picamera2(self.config.camera_index)
        self.cam2 = Picamera2(1) if self.config.camera2_enabled else None
        preview_cfg = self.camera.create_preview_configuration(
            main={"size": (PREVIEW_W, SCREEN_H), "format": "RGB888"},
            buffer_count=3,
        )
        self.camera.configure(preview_cfg)
        self.camera.start()

        self.params = [
            CameraParam("Expo EV", "ExposureValue", -8.0, 8.0, 0.2, 0.0),
            CameraParam("Brightness", "Brightness", -1.0, 1.0, 0.05, 0.0),
            CameraParam("Contrast", "Contrast", 0.0, 2.5, 0.05, 1.0),
            CameraParam("Saturation", "Saturation", 0.0, 3.0, 0.05, 1.0),
        ]
        self.selected = 0
        self.message = "Ready"
        self.message_until = 0.0
        self.last_capture = "-"
        self.menu_order = [Menu.CAPTURE, Menu.TUNE, Menu.COLOR, Menu.EFFECT, Menu.SYSTEM]
        self.menu_idx = 0
        self.prev_menu_idx = 0
        self.menu_anim_start = 0.0
        self.menu_anim_duration = 0.4

        self.view = View.CAMERA
        self.effect_idx = 0
        self.effects = ["none", "noir", "vintage"]

        self.rename_modal = False
        self.rename_text = ""
        self.keyboard_widget = None
        self.caps = False

        self.edit_surface: Optional[pygame.Surface] = None
        self.edit_history: List[pygame.Surface] = []
        self.crop_rect = pygame.Rect(80, 60, 260, 220)
        self.crop_drag = False
        self.crop_ratio_idx = 0
        self.crop_ratios = [(1, 1), (4, 3), (16, 9)]
        self.edit_selected_slider = 0
        self.edit_sliders: Dict[str, float] = {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0, "hue": 0.0}

        self.apply_controls()

    def notify(self, txt: str, timeout: float = 1.6) -> None:
        self.message = txt
        self.message_until = time.time() + timeout

    def current_menu(self) -> Menu:
        return self.menu_order[self.menu_idx]

    def ease_out_quad(self, t: float) -> float:
        return 1 - (1 - t) * (1 - t)

    def gaussian_blur_preview(self, arr: np.ndarray) -> np.ndarray:
        # léger blur 3x3 compatible Pi4
        kernel = np.array([1.0, 2.0, 1.0], dtype=np.float32)
        kernel = kernel / kernel.sum()
        out = arr.astype(np.float32)
        temp = np.zeros_like(out)
        for i, w in enumerate(kernel):
            temp += np.roll(out, i - 1, axis=1) * w
        out2 = np.zeros_like(temp)
        for i, w in enumerate(kernel):
            out2 += np.roll(temp, i - 1, axis=0) * w
        return np.clip(out2, 0, 255).astype(np.uint8)

    def apply_effect(self, frame: np.ndarray) -> np.ndarray:
        fx = self.effects[self.effect_idx]
        out = frame.astype(np.float32)
        if fx == "noir":
            g = out[:, :, 0] * 0.3 + out[:, :, 1] * 0.59 + out[:, :, 2] * 0.11
            out[:, :, 0] = g
            out[:, :, 1] = g
            out[:, :, 2] = g
        elif fx == "vintage":
            out[:, :, 0] *= 1.08
            out[:, :, 2] *= 0.82
        return np.clip(out, 0, 255).astype(np.uint8)

    def apply_controls(self) -> None:
        controls = {p.key: p.value for p in self.params}
        self.camera.set_controls(controls)

    def menu_buttons(self) -> List[Tuple[str, str]]:
        menu = self.current_menu()
        if menu == Menu.CAPTURE:
            return [("CAPTURE", "capture"), ("RENOMMER", "rename"), ("EDIT LAST", "edit"), ("NEXT", "menu_next")]
        if menu == Menu.TUNE:
            return [("PARAM -", "param_down"), ("PARAM +", "param_up"), ("NEXT PARAM", "next_param"), ("NEXT", "menu_next")]
        if menu == Menu.COLOR:
            return [("FX PREV", "fx_prev"), ("FX NEXT", "fx_next"), ("NEXT", "menu_next"), ("PREV", "menu_prev")]
        if menu == Menu.EFFECT:
            return [("CAPTURE", "capture"), ("EDIT", "edit"), ("NEXT", "menu_next"), ("PREV", "menu_prev")]
        return [("Hardware: capteur2", "toggle_sensor2"), ("Sauver config", "save_config"), ("NEXT", "menu_next"), ("PREV", "menu_prev")]

    def buttons(self) -> List[Tuple[pygame.Rect, str, str]]:
        x, y = PREVIEW_W + MARGIN, 60
        w = PANEL_W - 2 * MARGIN
        out = []
        for title, action in self.menu_buttons():
            out.append((pygame.Rect(x, y, w, BUTTON_H), title, action))
            y += BUTTON_H + 8
        return out

    def capture(self) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self.photo_dir / f"img_{ts}.jpg"
        self.camera.capture_file(str(out))
        self.last_capture = out.name
        self.notify(f"Saved {out.name}", 2.0)
        self.load_last_into_editor()

    def push_undo(self) -> None:
        if self.edit_surface is None:
            return
        self.edit_history.append(self.edit_surface.copy())
        self.edit_history = self.edit_history[-5:]

    def load_last_into_editor(self) -> None:
        if self.last_capture == "-":
            return
        path = self.photo_dir / self.last_capture
        if not path.exists():
            return
        self.edit_surface = pygame.image.load(str(path)).convert()
        self.edit_history = [self.edit_surface.copy()]

    def edit_apply_sliders(self) -> None:
        if self.edit_surface is None:
            return
        arr = pygame.surfarray.array3d(self.edit_history[-1]).swapaxes(0, 1).astype(np.float32)
        arr += self.edit_sliders["brightness"] * 60.0
        arr = (arr - 127.5) * self.edit_sliders["contrast"] + 127.5
        gray = arr.mean(axis=2, keepdims=True)
        arr = gray + (arr - gray) * self.edit_sliders["saturation"]
        hue_shift = self.edit_sliders["hue"]
        arr[:, :, 0] = np.roll(arr[:, :, 0], int(hue_shift), axis=0)
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        self.edit_surface = pygame.surfarray.make_surface(arr.swapaxes(0, 1))

    def open_rename_modal(self) -> None:
        self.rename_modal = True
        self.rename_text = ""
        if vkeyboard:
            layout = vkeyboard.QwertyLayout(vkeyboard.Key) if hasattr(vkeyboard, "QwertyLayout") else None
            self.keyboard_widget = vkeyboard.VKeyboard(
                self.screen,
                text_consumer=self.on_virtual_key,
                main_layout=layout,
                show_text=False,
            )

    def on_virtual_key(self, text: str) -> None:
        self.rename_text = text

    def rename_last(self) -> None:
        if self.last_capture == "-":
            return
        src = self.photo_dir / self.last_capture
        if not src.exists() or not self.rename_text.strip():
            return
        dst = self.photo_dir / f"{self.rename_text.strip()}.jpg"
        src.rename(dst)
        self.last_capture = dst.name
        self.notify(f"Renommé: {dst.name}")

    def save_edited(self) -> None:
        if self.edit_surface is None:
            return
        out = self.photo_dir / f"edit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        pygame.image.save(self.edit_surface, str(out))
        self.last_capture = out.name
        self.notify(f"Edit saved: {out.name}")

    def handle_action(self, action: str) -> None:
        if action == "capture":
            self.capture()
        elif action == "rename":
            self.open_rename_modal()
        elif action == "edit":
            self.load_last_into_editor()
            if self.edit_surface is not None:
                self.view = View.EDIT
        elif action == "menu_next":
            self.prev_menu_idx = self.menu_idx
            self.menu_idx = (self.menu_idx + 1) % len(self.menu_order)
            self.menu_anim_start = time.time()
        elif action == "menu_prev":
            self.prev_menu_idx = self.menu_idx
            self.menu_idx = (self.menu_idx - 1) % len(self.menu_order)
            self.menu_anim_start = time.time()
        elif action == "next_param":
            self.selected = (self.selected + 1) % len(self.params)
        elif action == "param_up":
            self.params[self.selected].inc()
            self.apply_controls()
        elif action == "param_down":
            self.params[self.selected].dec()
            self.apply_controls()
        elif action == "fx_next":
            self.effect_idx = (self.effect_idx + 1) % len(self.effects)
        elif action == "fx_prev":
            self.effect_idx = (self.effect_idx - 1) % len(self.effects)
        elif action == "toggle_sensor2":
            self.config.camera2_enabled = not self.config.camera2_enabled
            self.notify(f"Capteur 2 {'ON' if self.config.camera2_enabled else 'OFF'}")
        elif action == "save_config":
            CONFIG_FILE.write_text(json.dumps(self.config.to_dict(), indent=2))
            self.notify("config.json sauvegardé")

    def draw_camera_view(self, frame: np.ndarray) -> None:
        canvas = pygame.Surface((SCREEN_W, SCREEN_H))
        frame = self.apply_effect(frame)
        surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
        canvas.blit(surf, (0, 0))

        t = min(1.0, (time.time() - self.menu_anim_start) / self.menu_anim_duration) if self.menu_anim_start else 1.0
        eased = self.ease_out_quad(t)

        blurred = self.gaussian_blur_preview(frame)
        blur_surf = pygame.surfarray.make_surface(blurred.swapaxes(0, 1))
        blur_surf.set_alpha(90)
        canvas.blit(blur_surf, (0, 0))

        panel = pygame.Surface((PANEL_W, SCREEN_H), pygame.SRCALPHA)
        panel.fill((18, 18, 18, int(220 * eased)))
        title = self.font.render(f"MENU: {self.current_menu().value}", True, (235, 235, 235))
        panel.blit(title, (MARGIN, 16))
        for rect, title, _ in self.buttons():
            local = rect.move(-PREVIEW_W, 0)
            pygame.draw.rect(panel, (60, 60, 60), local, border_radius=8)
            pygame.draw.rect(panel, (120, 120, 120), local, width=1, border_radius=8)
            panel.blit(self.small.render(title, True, (240, 240, 240)), (local.x + 10, local.y + 12))

        x_offset = int((1 - eased) * PANEL_W)
        canvas.blit(panel, (PREVIEW_W + x_offset, 0))

        hud = self.small.render(f"Last: {self.last_capture}", True, (255, 255, 200))
        canvas.blit(hud, (14, SCREEN_H - 28))

        if time.time() < self.message_until:
            canvas.blit(self.font.render(self.message, True, (255, 220, 120)), (12, 10))

        if self.rename_modal:
            modal = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            modal.fill((0, 0, 0, 150))
            pygame.draw.rect(modal, (30, 30, 30, 240), (60, 70, SCREEN_W - 120, SCREEN_H - 140), border_radius=14)
            modal.blit(self.font.render("Renommer la photo", True, (240, 240, 240)), (90, 94))
            modal.blit(self.small.render(self.rename_text or "...", True, (255, 255, 180)), (90, 140))
            ok = pygame.Rect(530, 360, 80, 42)
            cancel = pygame.Rect(620, 360, 110, 42)
            pygame.draw.rect(modal, (80, 130, 80), ok, border_radius=8)
            pygame.draw.rect(modal, (130, 80, 80), cancel, border_radius=8)
            modal.blit(self.small.render("OK", True, (255, 255, 255)), (560, 373))
            modal.blit(self.small.render("Annuler", True, (255, 255, 255)), (644, 373))
            canvas.blit(modal, (0, 0))
            if self.keyboard_widget:
                self.keyboard_widget.draw()

        self.screen.blit(canvas, (0, 0))
        pygame.display.flip()

    def draw_edit_view(self) -> None:
        if self.edit_surface is None:
            self.view = View.CAMERA
            return
        canvas = pygame.Surface((SCREEN_W, SCREEN_H))
        scaled = pygame.transform.smoothscale(self.edit_surface, (PREVIEW_W, SCREEN_H))
        canvas.blit(scaled, (0, 0))

        pygame.draw.rect(canvas, (255, 255, 0), self.crop_rect, width=2)
        ratio_txt = f"Ratio {self.crop_ratios[self.crop_ratio_idx][0]}:{self.crop_ratios[self.crop_ratio_idx][1]}"
        canvas.blit(self.small.render(ratio_txt, True, (255, 240, 160)), (14, 12))

        panel = pygame.Rect(PREVIEW_W, 0, PANEL_W, SCREEN_H)
        pygame.draw.rect(canvas, (20, 20, 20), panel)
        y = 20
        labels = ["brightness", "contrast", "saturation", "hue"]
        for idx, lbl in enumerate(labels):
            val = self.edit_sliders[lbl]
            canvas.blit(self.small.render(f"{lbl}: {val:.2f}", True, (230, 230, 230)), (PREVIEW_W + 14, y))
            pygame.draw.line(canvas, (120, 120, 120), (PREVIEW_W + 14, y + 24), (SCREEN_W - 16, y + 24), 2)
            knob_x = int(PREVIEW_W + 14 + ((val + 1) / 2) * (PANEL_W - 40)) if lbl != "contrast" else int(PREVIEW_W + 14 + (val / 2) * (PANEL_W - 40))
            pygame.draw.circle(canvas, (180, 240, 255), (knob_x, y + 24), 6)
            y += 66

        cmds = ["RATIO", "ROT90", "FLIP", "UNDO", "CROP", "SAVE", "BACK"]
        for i, cmd in enumerate(cmds):
            rect = pygame.Rect(PREVIEW_W + 14, 300 + i * 24, PANEL_W - 28, 22)
            pygame.draw.rect(canvas, (65, 65, 65), rect, border_radius=6)
            canvas.blit(self.small.render(cmd, True, (255, 255, 255)), (rect.x + 8, rect.y + 3))

        self.screen.blit(canvas, (0, 0))
        pygame.display.flip()

    def handle_edit_click(self, pos: Tuple[int, int]) -> None:
        if pos[0] < PREVIEW_W and self.crop_rect.collidepoint(pos):
            self.crop_drag = True
            return
        x, y = pos
        if x < PREVIEW_W:
            return
        cmd_index = (y - 300) // 24
        if 0 <= cmd_index < 7:
            cmd = ["ratio", "rot", "flip", "undo", "crop", "save", "back"][cmd_index]
            if cmd == "ratio":
                self.crop_ratio_idx = (self.crop_ratio_idx + 1) % len(self.crop_ratios)
                w_ratio, h_ratio = self.crop_ratios[self.crop_ratio_idx]
                self.crop_rect.height = int(self.crop_rect.width * h_ratio / w_ratio)
            elif cmd == "rot" and self.edit_surface is not None:
                self.push_undo()
                self.edit_surface = pygame.transform.rotate(self.edit_surface, -90)
            elif cmd == "flip" and self.edit_surface is not None:
                self.push_undo()
                self.edit_surface = pygame.transform.flip(self.edit_surface, True, False)
            elif cmd == "undo" and len(self.edit_history) > 1:
                self.edit_history.pop()
                self.edit_surface = self.edit_history[-1].copy()
            elif cmd == "crop" and self.edit_surface is not None:
                self.push_undo()
                src = pygame.transform.smoothscale(self.edit_surface, (PREVIEW_W, SCREEN_H))
                cropped = src.subsurface(self.crop_rect).copy()
                self.edit_surface = cropped
            elif cmd == "save":
                self.save_edited()
            elif cmd == "back":
                self.view = View.CAMERA

    def click(self, pos: Tuple[int, int]) -> None:
        if self.view == View.EDIT:
            self.handle_edit_click(pos)
            return

        if self.rename_modal:
            if pygame.Rect(530, 360, 80, 42).collidepoint(pos):
                self.rename_last()
                self.rename_modal = False
                self.keyboard_widget = None
            elif pygame.Rect(620, 360, 110, 42).collidepoint(pos):
                self.rename_modal = False
                self.keyboard_widget = None
            return

        for rect, _t, action in self.buttons():
            if rect.collidepoint(pos):
                self.handle_action(action)
                return

    def run(self) -> None:
        try:
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        raise SystemExit
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        if self.view == View.EDIT:
                            self.view = View.CAMERA
                        elif self.rename_modal:
                            self.rename_modal = False
                        else:
                            raise SystemExit
                    if event.type == pygame.KEYDOWN and self.rename_modal:
                        if event.key == pygame.K_BACKSPACE:
                            self.rename_text = self.rename_text[:-1]
                        elif event.key == pygame.K_RETURN:
                            self.rename_last()
                            self.rename_modal = False
                        elif event.key == pygame.K_TAB:
                            self.caps = not self.caps
                        elif event.unicode:
                            ch = event.unicode.upper() if self.caps else event.unicode
                            self.rename_text += ch
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        self.click(event.pos)
                    if event.type == pygame.MOUSEBUTTONUP:
                        self.crop_drag = False
                    if event.type == pygame.MOUSEMOTION and self.view == View.EDIT and self.crop_drag:
                        self.crop_rect.center = event.pos

                if self.view == View.CAMERA:
                    frame = self.camera.capture_array()
                    self.draw_camera_view(frame)
                else:
                    self.draw_edit_view()
                self.clock.tick(30)
        finally:
            self.camera.stop()
            if self.cam2:
                self.cam2.stop()
            pygame.quit()


def main() -> int:
    app = CameraApp()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
