#!/usr/bin/env python3
"""PImage Pro Edition - CM4 Camera Software.
Features: RAW, Video, Burst, Timelapse, Web Remote, Battery & CPU Monitoring.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pygame

# Configuration Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / "pimage.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None
    logger.warning("Picamera2 not found.")

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

try:
    from smbus2 import SMBus
except ImportError:
    SMBus = None

try:
    from flask import Flask, Response, jsonify, render_template_string, request
except ImportError:
    Flask = None

try:
    import cv2
except ImportError:
    cv2 = None

SCREEN_W = 800
SCREEN_H = 480
PANEL_W = 200
PREVIEW_W = 600
BUTTON_H = 42
MARGIN = 8
PHOTO_DIR = Path.home() / "photos"
PROFILE_FILE = Path.home() / ".pimage_profiles.json"
GRID_COLOR = (0, 220, 180)
NEON_CYAN = (72, 230, 255)
NEON_MAGENTA = (255, 82, 214)
HUD_BG = (12, 16, 28)
THEMES = ["classic", "cyber", "minimal"]

ENC_CLK = 17
ENC_DT = 18
ENC_SW = 27

@dataclass
class CameraParam:
    label: str
    key: str
    min_val: float
    max_val: float
    step: float
    value: float
    def inc(self) -> None: self.value = min(self.max_val, self.value + self.step)
    def dec(self) -> None: self.value = max(self.min_val, self.value - self.step)

class Menu(str, Enum):
    CAPTURE = "Capture"
    TUNE = "Tune"
    COLOR = "Color"
    EFFECT = "Effect"
    TIMELAPSE = "Time-lapse"
    SYSTEM = "System"

COLOR_PROFILES: Dict[str, Dict[str, float]] = {
    "natural": {"Saturation": 1.0, "Contrast": 1.0, "Sharpness": 1.0, "Brightness": 0.0},
    "vivid": {"Saturation": 1.8, "Contrast": 1.25, "Sharpness": 1.5, "Brightness": 0.05},
    "cinema": {"Saturation": 0.85, "Contrast": 0.92, "Sharpness": 0.7, "Brightness": -0.02},
    "mono": {"Saturation": 0.0, "Contrast": 1.45, "Sharpness": 1.4, "Brightness": 0.0},
    "retro": {"Saturation": 1.2, "Contrast": 0.88, "Sharpness": 0.5, "Brightness": 0.12},
}

EFFECTS = ["none", "noir", "vintage", "cool", "cyber", "thermal", "glitch"]
GRIDS = ["off", "thirds", "quarters", "crosshair", "diagonal-x", "golden-phi"]

class CameraApp:
    def __init__(self) -> None:
        if Picamera2 is None: raise RuntimeError("Picamera2 missing")
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
        pygame.mouse.set_visible(False)
        self.screen_w, self.screen_h = self.screen.get_size()
        # Base control width (actual button widths are computed dynamically).
        self.panel_w = max(180, min(int(self.screen_w * 0.28), (self.screen_w // 2) - 24))
        self.preview_w = self.screen_w
        self.menu_x = max(8, int(self.screen_w * 0.25) - (self.panel_w // 2))
        # Default rotation is 0; set PIMAGE_ROTATE if the Linux display is not oriented correctly.
        self.display_rotation = int(os.getenv("PIMAGE_ROTATE", "0"))
        if self.display_rotation not in {0, 90, 180, 270}:
            self.display_rotation = 0
        # Rotate overlay button labels 90° left as requested.
        self.menu_label_rotation = -90
        self.edge_buttons_per_side = max(2, min(6, int(os.getenv("PIMAGE_BTNS_SIDE", "6"))))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("DejaVuSans", 21)
        self.small = pygame.font.SysFont("DejaVuSans", 19)
        self.pixel_font = pygame.font.SysFont("DejaVuSansMono", 10, bold=True)
        self.draw_startup_splash("Initializing display", 0.12)
        self.camera = Picamera2()
        self.draw_startup_splash("Configuring camera", 0.35)
        config = self.camera.create_preview_configuration(main={"size": (self.preview_w, self.screen_h), "format": "RGB888"}, buffer_count=3)
        self.camera.configure(config)
        self.camera.start()
        # Controls exposed by libcamera vary by sensor/driver version.
        self.supported_controls = set(self.camera.camera_controls.keys())
        self._unsupported_controls_logged: set[str] = set()
        logger.info(
            "Display layout: screen=%sx%s preview=%sx%s overlay_button_w=%s rotation=%s",
            self.screen_w,
            self.screen_h,
            self.preview_w,
            self.screen_h,
            self.panel_w,
            self.display_rotation,
        )

        self.params = [
            CameraParam("Expo EV", "ExposureValue", -8.0, 8.0, 0.2, 0.0),
            CameraParam("Gain", "AnalogueGain", 1.0, 16.0, 0.2, 1.0),
            CameraParam("Bright", "Brightness", -1.0, 1.0, 0.05, 0.0),
            CameraParam("Contrast", "Contrast", 0.0, 2.5, 0.05, 1.0),
            CameraParam("Saturation", "Saturation", 0.0, 3.0, 0.05, 1.0),
            CameraParam("Sharp", "Sharpness", 0.0, 4.0, 0.1, 1.0),
            CameraParam("Exposure µs", "ExposureTime", 100, 30000, 100, 8000),
        ]
        self.selected, self.auto_exposure = 0, True
        self.awb_mode_idx, self.awb_modes = 0, [("Auto", 0), ("Tungsten", 1), ("Fluo", 2), ("Indoor", 3), ("Daylight", 4), ("Cloudy", 5)]
        self.menu_order = [Menu.CAPTURE, Menu.TUNE, Menu.COLOR, Menu.EFFECT, Menu.TIMELAPSE, Menu.SYSTEM]
        self.menu_idx, self.color_profile, self.effect_idx, self.grid_idx = 0, "natural", 0, 1
        self.theme_idx = THEMES.index("cyber")
        self.timelapse_active, self.timelapse_interval, self.timelapse_last_shot, self.timelapse_count = False, 5.0, 0.0, 0
        self.raw_enabled, self.bracketing_enabled, self.peaking_enabled = False, False, False
        self.raw_available = True
        self.awb_locked = False
        self.auto_sync_enabled, self.sync_active, self.battery_percent = False, False, -1.0
        self.video_active, self.video_start_time, self.burst_count = False, 0.0, 5
        self.self_timer_delay, self.timer_active, self.timer_start_time = 0, False, 0.0
        self.cpu_temp, self.last_cpu_check, self.last_web_frame = 0.0, 0.0, None
        self.disk_free_mb = 0.0
        self.gallery_mode, self.gallery_files, self.gallery_index, self.current_image = False, [], 0, None
        self.gallery_base_image = None
        self.gallery_zoom, self.gallery_angle = 1.0, 0.0
        self.active_touches: Dict[int, Tuple[float, float]] = {}
        self.touch_taps: Dict[int, Tuple[float, float, float]] = {}
        self.gesture_baseline = None
        self.overlay_rotation = 0
        self.drawn_button_regions: List[Tuple[pygame.Rect, str]] = []
        self.ev_drag_active = False
        self.ev_slider_rect = pygame.Rect(0, 0, 0, 0)
        self.message, self.message_until, self.last_capture = "Ready", 0.0, "-"
        self.capture_failures = 0
        self.encoder_requested = os.getenv("PIMAGE_ENCODER", "1").strip().lower() not in {"0", "false", "off", "no"}
        self.encoder_enabled = False
        self.web_live_enabled = os.getenv("PIMAGE_WEB_LIVE", "0").strip().lower() in {"1", "true", "on", "yes"}
        self.frame_lock = threading.Lock()

        self.draw_startup_splash("Loading profiles", 0.62)
        self.apply_color_profile("natural", notify=False)
        self.load_user_state()
        self.apply_all_controls()
        self.setup_encoder()
        self.draw_startup_splash("Starting services", 0.86)
        threading.Thread(target=self.sync_worker, daemon=True).start()
        threading.Thread(target=self.battery_worker, daemon=True).start()
        threading.Thread(target=self.disk_worker, daemon=True).start()
        if Flask: threading.Thread(target=self.web_server_worker, daemon=True).start()
        self.draw_startup_splash("Ready", 1.0)

    def draw_startup_splash(self, text: str, progress: float) -> None:
        """Draw a cyber-style startup splash with loading bar."""
        colors = self.theme_colors()
        self.screen.fill(colors["hud_bg"])
        center = (self.screen_w // 2, self.screen_h // 2 - 20)
        r1 = min(self.screen_w, self.screen_h) // 4
        r2 = int(r1 * 0.68)
        pygame.draw.circle(self.screen, colors["accent_a"], center, r1, width=4)
        pygame.draw.circle(self.screen, colors["accent_b"], center, r2, width=3)
        pygame.draw.circle(self.screen, colors["frame_a"], center, int(r2 * 0.55), width=2)

        title = self.font.render("PIMAGE", True, colors["accent_a"])
        subtitle = self.small.render(text, True, (220, 220, 240))
        self.screen.blit(title, title.get_rect(center=(self.screen_w // 2, 56)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(self.screen_w // 2, self.screen_h - 82)))

        bar_w = min(420, self.screen_w - 120)
        bar_h = 16
        bx = (self.screen_w - bar_w) // 2
        by = self.screen_h - 52
        progress = max(0.0, min(1.0, progress))
        pygame.draw.rect(self.screen, (30, 40, 68), (bx, by, bar_w, bar_h), border_radius=8)
        pygame.draw.rect(self.screen, colors["accent_b"], (bx, by, int(bar_w * progress), bar_h), border_radius=8)
        pygame.draw.rect(self.screen, colors["accent_a"], (bx, by, bar_w, bar_h), width=1, border_radius=8)
        pygame.display.flip()
        pygame.event.pump()
        time.sleep(0.12)

    def load_user_state(self) -> None:
        """Load persisted user preferences from PROFILE_FILE when available."""
        if not PROFILE_FILE.exists():
            return
        try:
            data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
            self.raw_enabled = bool(data.get("raw_enabled", self.raw_enabled))
            self.peaking_enabled = bool(data.get("peaking_enabled", self.peaking_enabled))
            self.auto_sync_enabled = bool(data.get("auto_sync_enabled", self.auto_sync_enabled))
            self.awb_locked = bool(data.get("awb_locked", self.awb_locked))
            self.self_timer_delay = int(data.get("self_timer_delay", self.self_timer_delay))
            self.auto_exposure = bool(data.get("auto_exposure", self.auto_exposure))
            self.encoder_requested = bool(data.get("encoder_requested", self.encoder_requested))
            self.web_live_enabled = bool(data.get("web_live_enabled", self.web_live_enabled))
            self.effect_idx = int(data.get("effect_idx", self.effect_idx)) % len(EFFECTS)
            self.theme_idx = int(data.get("theme_idx", self.theme_idx)) % len(THEMES)
            profile_name = data.get("color_profile", self.color_profile)
            if isinstance(profile_name, str):
                self.apply_color_profile(profile_name, notify=False)
            logger.info("Loaded user state from %s", PROFILE_FILE)
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as exc:
            logger.warning("Failed to load user state: %s", exc)

    def save_user_state(self) -> None:
        """Persist user preferences to PROFILE_FILE atomically."""
        payload = {
            "raw_enabled": self.raw_enabled,
            "peaking_enabled": self.peaking_enabled,
            "auto_sync_enabled": self.auto_sync_enabled,
            "awb_locked": self.awb_locked,
            "self_timer_delay": self.self_timer_delay,
            "auto_exposure": self.auto_exposure,
            "encoder_requested": self.encoder_requested,
            "web_live_enabled": self.web_live_enabled,
            "effect_idx": self.effect_idx,
            "theme_idx": self.theme_idx,
            "color_profile": self.color_profile,
        }
        tmp_file = PROFILE_FILE.with_suffix(".tmp")
        try:
            tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp_file.replace(PROFILE_FILE)
        except OSError as exc:
            logger.warning("Failed to save user state: %s", exc)

    def theme_name(self) -> str:
        return THEMES[self.theme_idx % len(THEMES)]

    def theme_colors(self) -> dict:
        theme = self.theme_name()
        if theme == "classic":
            return {
                "hud_bg": (18, 22, 30),
                "accent_a": (205, 220, 235),
                "accent_b": (145, 170, 195),
                "frame_a": (190, 205, 220),
                "frame_b": (85, 98, 120),
                "btn_bg": (28, 34, 45, 150),
                "btn_edge": (205, 220, 235, 200),
                "btn_line": (140, 160, 185, 180),
                "text": (240, 240, 245),
                "info": (230, 232, 238),
                "fx": (210, 225, 240),
            }
        if theme == "minimal":
            return {
                "hud_bg": (10, 12, 16),
                "accent_a": (240, 240, 240),
                "accent_b": (165, 165, 165),
                "frame_a": (120, 120, 120),
                "frame_b": (80, 80, 80),
                "btn_bg": (10, 10, 10, 110),
                "btn_edge": (220, 220, 220, 130),
                "btn_line": (170, 170, 170, 120),
                "text": (245, 245, 245),
                "info": (225, 225, 225),
                "fx": (200, 200, 200),
            }
        return {
            "hud_bg": HUD_BG,
            "accent_a": NEON_CYAN,
            "accent_b": NEON_MAGENTA,
            "frame_a": (22, 30, 55),
            "frame_b": NEON_MAGENTA,
            "btn_bg": (16, 24, 40, 120),
            "btn_edge": (*NEON_CYAN, 150),
            "btn_line": (*NEON_MAGENTA, 160),
            "text": (240, 240, 240),
            "info": (220, 238, 255),
            "fx": NEON_CYAN,
        }

    def setup_encoder(self) -> None:
        """Configure GPIO events for the rotary encoder when available."""
        if not self.encoder_requested:
            self.encoder_enabled = False
            return
        if GPIO is None:
            logger.info("Encoder requested but RPi.GPIO is unavailable.")
            return
        if self.encoder_enabled:
            return
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup([ENC_CLK, ENC_DT, ENC_SW], GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(ENC_CLK, GPIO.FALLING, callback=self._encoder_callback, bouncetime=5)
            GPIO.add_event_detect(ENC_SW, GPIO.FALLING, callback=self._button_callback, bouncetime=300)
            self.encoder_enabled = True
        except Exception as exc:
            logger.warning("GPIO encoder setup failed: %s", exc)
            self.encoder_enabled = False
            self.encoder_requested = False

    def disable_encoder(self) -> None:
        """Disable encoder GPIO callbacks without impacting touch controls."""
        if GPIO is None or not getattr(self, "encoder_enabled", False):
            self.encoder_enabled = False
            return
        try:
            GPIO.remove_event_detect(ENC_CLK)
        except RuntimeError:
            pass
        try:
            GPIO.remove_event_detect(ENC_SW)
        except RuntimeError:
            pass
        try:
            GPIO.cleanup([ENC_CLK, ENC_DT, ENC_SW])
        except RuntimeError:
            pass
        self.encoder_enabled = False

    def _encoder_callback(self, ch):
        if not self.encoder_enabled or GPIO is None:
            return
        if self.gallery_mode: self.handle_action("gal_next" if GPIO.input(ENC_DT) else "gal_prev")
        else: self.handle_action("param_up" if GPIO.input(ENC_DT) else "param_down")

    def _button_callback(self, ch):
        if not self.encoder_enabled:
            return
        if self.gallery_mode: self.handle_action("gal_quit")
        elif self.current_menu() == Menu.CAPTURE: self.handle_action("capture")
        else: self.handle_action("menu_next")

    def handle_encoder_input(self) -> None:
        """Legacy compatibility hook.

        Older revisions called this method in the main loop for polled encoder
        handling. Current implementation uses GPIO interrupts, so this is
        intentionally a no-op.
        """
        return

    def recover_camera(self) -> bool:
        """Try to restart camera pipeline after a capture timeout/error."""
        for attempt in range(1, 4):
            try:
                self.camera.stop()
            except Exception:
                pass
            try:
                self.camera.start()
                logger.warning("Camera pipeline recovered (attempt %d).", attempt)
                self.capture_failures = 0
                return True
            except Exception as exc:
                logger.error("Camera restart attempt %d failed: %s", attempt, exc)
                time.sleep(0.5)
        return False

    def notify(self, t, timeout=1.6): self.message, self.message_until = t, time.time() + timeout

    def apply_all_controls(self) -> None:
        ctrls = {"AeEnable": self.auto_exposure, "AwbMode": self.awb_modes[self.awb_mode_idx][1], "AwbLocked": self.awb_locked}
        for p in self.params:
            if p.key == "ExposureTime" and self.auto_exposure: continue
            ctrls[p.key] = int(p.value) if p.key == "ExposureTime" else p.value
        filtered_ctrls = {}
        for name, value in ctrls.items():
            if name in self.supported_controls:
                filtered_ctrls[name] = value
            elif name not in self._unsupported_controls_logged:
                logger.info("Control '%s' unsupported on this camera, skipping.", name)
                self._unsupported_controls_logged.add(name)
        self.camera.set_controls(filtered_ctrls)

    def apply_color_profile(self, name, notify=True):
        if name not in COLOR_PROFILES: return
        self.color_profile = name
        for p in self.params:
            if p.key in COLOR_PROFILES[name]: p.value = COLOR_PROFILES[name][p.key]
        self.apply_all_controls()
        if notify: self.notify(f"Profile: {name}")

    def capture(self, force=False):
        if self.disk_free_mb < 100:
            self.notify("Disk Full!", timeout=3.0)
            return
        if self.self_timer_delay > 0 and not force:
            if not self.timer_active: self.timer_active, self.timer_start_time = True, time.time()
            else: self.timer_active = False
            return
        try:
            ts_base = datetime.now().strftime("%Y%m%d_%H%M%S")
            ev_steps = [-1.0, 0.0, 1.0] if self.bracketing_enabled else [0.0]
            orig_ev = next(p.value for p in self.params if p.key == "ExposureValue")
            for i, ev in enumerate(ev_steps):
                ts = f"{ts_base}_{i}" if self.bracketing_enabled else ts_base
                path = PHOTO_DIR / f"img_{ts}.jpg"
                if self.bracketing_enabled: self.camera.set_controls({"ExposureValue": orig_ev + ev}); time.sleep(0.1)
                self.camera.capture_file(str(path))
                if self.raw_enabled and self.raw_available:
                    try:
                        self.camera.capture_file(str(PHOTO_DIR / f"img_{ts}.dng"), format="dng")
                    except Exception as raw_exc:
                        # Some sensors/libcamera builds do not expose DNG output.
                        logger.warning("RAW/DNG capture unavailable: %s", raw_exc)
                        self.raw_available = False
                        self.raw_enabled = False
                        self.notify("RAW unsupported on this camera", timeout=2.5)
                        self.save_user_state()
            if self.bracketing_enabled: self.camera.set_controls({"ExposureValue": orig_ev})
            self.last_capture = f"img_{ts_base}.jpg"
            self.notify("Captured")
            # Force write to SD card to prevent corruption on power loss
            os.sync()
        except Exception as e: logger.error(e); self.notify("Error")

    def capture_burst(self):
        ts_base = datetime.now().strftime("%Y%m%d_%H%M%S")
        for i in range(self.burst_count):
            self.camera.capture_file(str(PHOTO_DIR / f"img_{ts_base}_b{i}.jpg"))
        self.notify("Burst Done")

    def open_gallery(self):
        self.gallery_files = sorted(list(PHOTO_DIR.glob("*.jpg")), reverse=True)
        if not self.gallery_files: return self.notify("No Photos")
        self.gallery_mode, self.gallery_index = True, 0
        self.load_gallery_image()

    def load_gallery_image(self):
        try:
            img = pygame.image.load(str(self.gallery_files[self.gallery_index])).convert()
            self.gallery_base_image = img
            self.gallery_zoom, self.gallery_angle = 1.0, 0.0
            self.active_touches.clear()
            self.touch_taps.clear()
            self.gesture_baseline = None
            self.current_image = img
        except (pygame.error, IndexError, FileNotFoundError) as exc:
            logger.warning("Failed to load gallery image: %s", exc)
            self.current_image = None
            self.gallery_base_image = None

    def handle_action(self, action):
        """Dispatch UI/keyboard/encoder actions to app state transitions."""
        if action == "capture": self.capture()
        elif action == "burst": self.capture_burst()
        elif action == "toggle_video":
            if not self.video_active:
                if self.disk_free_mb < 200:
                    self.notify("Disk low for video!")
                    return
                try:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    self.camera.start_recording(str(PHOTO_DIR / f"vid_{ts}.mp4"))
                    self.video_active, self.video_start_time = True, time.time()
                except Exception as exc:
                    logger.error("Failed to start video recording: %s", exc)
                    self.notify("Video error")
            else:
                try:
                    self.camera.stop_recording()
                    self.video_active = False
                except Exception as exc:
                    logger.error("Failed to stop video recording: %s", exc)
                    self.notify("Video stop error")
        elif action == "gallery": self.open_gallery()
        elif action == "gal_next": self.gallery_index = (self.gallery_index+1)%len(self.gallery_files); self.load_gallery_image()
        elif action == "gal_prev": self.gallery_index = (self.gallery_index-1)%len(self.gallery_files); self.load_gallery_image()
        elif action == "gal_delete":
            if self.gallery_files:
                try:
                    path = self.gallery_files[self.gallery_index]
                    path.unlink() # Delete JPG
                    # Also try to delete DNG if exists
                    dng = path.with_suffix(".dng")
                    if dng.exists(): dng.unlink()
                    logger.info(f"Deleted: {path}")
                    self.gallery_files.pop(self.gallery_index)
                    if not self.gallery_files: self.gallery_mode = False
                    else:
                        self.gallery_index %= len(self.gallery_files)
                        self.load_gallery_image()
                except Exception as e: logger.error(e)
        elif action == "gal_quit": self.gallery_mode = False
        elif action == "edit":
            self.notify("Edit module: coming soon", timeout=2.0)
        elif action == "param_up": self.params[self.selected].inc(); self.apply_all_controls()
        elif action == "param_down": self.params[self.selected].dec(); self.apply_all_controls()
        elif action == "next": self.selected = (self.selected+1)%len(self.params)
        elif action == "toggle_ae":
            self.auto_exposure = not self.auto_exposure
            self.apply_all_controls()
            self.notify(f"AE {'ON' if self.auto_exposure else 'OFF'}")
            self.save_user_state()
        elif action == "toggle_awb_lock":
            if "AwbLocked" not in self.supported_controls:
                self.notify("AWB LOCK unsupported")
                return
            self.awb_locked = not self.awb_locked
            self.apply_all_controls()
            self.notify(f"AWB LOCK {'ON' if self.awb_locked else 'OFF'}")
            self.save_user_state()
        elif action == "toggle_raw":
            if not self.raw_available:
                self.notify("RAW unsupported")
                return
            self.raw_enabled = not self.raw_enabled
            self.notify(f"RAW {'ON' if self.raw_enabled else 'OFF'}")
            self.save_user_state()
        elif action == "toggle_peaking":
            self.peaking_enabled = not self.peaking_enabled
            self.notify(f"PEAK {'ON' if self.peaking_enabled else 'OFF'}")
            self.save_user_state()
        elif action == "toggle_sync":
            self.auto_sync_enabled = not self.auto_sync_enabled
            self.notify(f"SYNC {'ON' if self.auto_sync_enabled else 'OFF'}")
            self.save_user_state()
        elif action == "toggle_timer":
            self.self_timer_delay = {0:2, 2:5, 5:10, 10:0}[self.self_timer_delay]
            self.notify(f"TIMER {self.self_timer_delay}s" if self.self_timer_delay else "TIMER OFF")
            self.save_user_state()
        elif action == "effect_next":
            self.effect_idx = (self.effect_idx + 1) % len(EFFECTS)
            self.notify(f"FX {EFFECTS[self.effect_idx].upper()}")
            self.save_user_state()
        elif action == "effect_prev":
            self.effect_idx = (self.effect_idx - 1) % len(EFFECTS)
            self.notify(f"FX {EFFECTS[self.effect_idx].upper()}")
            self.save_user_state()
        elif action == "toggle_theme":
            self.theme_idx = (self.theme_idx + 1) % len(THEMES)
            self.notify(f"Theme {self.theme_name().upper()}")
            self.save_user_state()
        elif action.startswith("theme_set_"):
            name = action.replace("theme_set_", "", 1)
            if name in THEMES:
                self.theme_idx = THEMES.index(name)
                self.notify(f"Theme {name.upper()}")
                self.save_user_state()
        elif action.startswith("effect_set_"):
            name = action.replace("effect_set_", "", 1)
            if name in EFFECTS:
                self.effect_idx = EFFECTS.index(name)
                self.notify(f"FX {name.upper()}")
                self.save_user_state()
        elif action == "toggle_encoder":
            self.encoder_requested = not self.encoder_requested
            if self.encoder_requested:
                self.setup_encoder()
                self.notify("ENC ON" if self.encoder_enabled else "ENC unavailable")
            else:
                self.disable_encoder()
                self.notify("ENC OFF")
            self.save_user_state()
        elif action == "menu_next": self.menu_idx = (self.menu_idx+1)%len(self.menu_order)
        elif action == "menu_prev": self.menu_idx = (self.menu_idx-1)%len(self.menu_order)
        elif action == "shutdown":
            self.notify("SHUTDOWN...")
            pygame.display.flip()
            time.sleep(1)
            subprocess.run(["sudo", "poweroff"], check=False)
        elif action == "quit": raise SystemExit

    def current_menu(self): return self.menu_order[self.menu_idx]
    def menu_buttons(self):
        m = self.current_menu()
        if m == Menu.CAPTURE:
            return [("BURST", "burst"), ("VIDEO", "toggle_video"), ("TIMER", "toggle_timer"), ("GALLERY", "gallery"), ("EDIT", "edit"), ("FX+", "effect_next"), ("FX-", "effect_prev"), ("RAW", "toggle_raw"), ("PEAK", "toggle_peaking"), ("SYNC", "toggle_sync"), ("AE", "toggle_ae"), ("NEXT", "menu_next")]
        if m == Menu.TUNE:
            return [("P+", "param_up"), ("P-", "param_down"), ("NEXT P", "next"), ("AE", "toggle_ae"), ("AWB", "toggle_awb_lock"), ("RAW", "toggle_raw"), ("PEAK", "toggle_peaking"), ("TIMER", "toggle_timer"), ("SYNC", "toggle_sync"), ("FX+", "effect_next"), ("NEXT", "menu_next"), ("BACK", "menu_prev")]
        if m == Menu.COLOR:
            return [("RAW", "toggle_raw"), ("PEAK", "toggle_peaking"), ("SYNC", "toggle_sync"), ("TIMER", "toggle_timer"), ("AE", "toggle_ae"), ("AWB", "toggle_awb_lock"), ("FX+", "effect_next"), ("FX-", "effect_prev"), ("BURST", "burst"), ("VIDEO", "toggle_video"), ("NEXT", "menu_next"), ("BACK", "menu_prev")]
        if m == Menu.EFFECT:
            return [("NONE", "effect_set_none"), ("NOIR", "effect_set_noir"), ("VINT", "effect_set_vintage"), ("COOL", "effect_set_cool"), ("CYBER", "effect_set_cyber"), ("THERM", "effect_set_thermal"), ("GLITCH", "effect_set_glitch"), ("RAW", "toggle_raw"), ("PEAK", "toggle_peaking"), ("SYNC", "toggle_sync"), ("NEXT", "menu_next"), ("BACK", "menu_prev")]
        if m == Menu.TIMELAPSE:
            return [("TIMER", "toggle_timer"), ("SYNC", "toggle_sync"), ("BURST", "burst"), ("VIDEO", "toggle_video"), ("GALLERY", "gallery"), ("RAW", "toggle_raw"), ("PEAK", "toggle_peaking"), ("FX+", "effect_next"), ("AE", "toggle_ae"), ("AWB", "toggle_awb_lock"), ("NEXT", "menu_next"), ("BACK", "menu_prev")]
        if m == Menu.SYSTEM:
            enc_label = f"ENC {'ON' if self.encoder_enabled else 'OFF'}"
            return [("GALLERY", "gallery"), (enc_label, "toggle_encoder"), ("TH-CLS", "theme_set_classic"), ("TH-CYB", "theme_set_cyber"), ("TH-MIN", "theme_set_minimal"), ("SYNC", "toggle_sync"), ("RAW", "toggle_raw"), ("PEAK", "toggle_peaking"), ("AE", "toggle_ae"), ("AWB", "toggle_awb_lock"), ("OFF", "shutdown"), ("BACK", "menu_prev")]
        return [("NEXT", "menu_next"), ("BACK", "menu_prev")]

    def buttons(self):
        requested_per_row = self.edge_buttons_per_side
        side_margin = 8
        row_gap = 8
        usable_w = self.screen_w - (side_margin * 2)
        min_button_w = 88
        auto_per_row = max(3, usable_w // min_button_w)
        per_row = max(3, min(requested_per_row, auto_per_row))
        max_visible = per_row * 2
        actions = self.menu_buttons()[:max_visible]
        top_actions = actions[:per_row]
        bot_actions = actions[per_row:per_row * 2]
        button_h = max(40, min(56, self.screen_h // 9))

        def make_row(row_actions, y):
            out = []
            if not row_actions:
                return out
            n = len(row_actions)
            gap = 6
            bw = max(min_button_w, int((usable_w - gap * (n - 1)) / n))
            total = bw * n + gap * (n - 1)
            start_x = (self.screen_w - total) // 2
            for i, (title, action) in enumerate(row_actions):
                x = start_x + i * (bw + gap)
                out.append((pygame.Rect(x, y, bw, button_h), title, action))
            return out

        edge_buttons = []
        edge_buttons.extend(make_row(top_actions, 8))
        edge_buttons.extend(make_row(bot_actions, self.screen_h - button_h - 8))
        # Dedicated center shutter button always available on preview.
        shutter_size = min(110, self.screen_h // 5)
        shutter_rect = pygame.Rect(
            (self.screen_w - shutter_size) // 2,
            (self.screen_h - shutter_size) // 2,
            shutter_size,
            shutter_size,
        )
        edge_buttons.append((shutter_rect, "SHOT", "capture"))
        return edge_buttons

    def apply_effect(self, frame):
        out = frame.astype(np.float32)
        effect = EFFECTS[self.effect_idx % len(EFFECTS)]
        if effect == "noir":
            lum = (0.299 * out[:, :, 0] + 0.587 * out[:, :, 1] + 0.114 * out[:, :, 2])
            out[:, :, 0] = lum
            out[:, :, 1] = lum
            out[:, :, 2] = lum
        elif effect == "vintage":
            out[:, :, 0] = np.clip(out[:, :, 0] * 1.10 + 12, 0, 255)
            out[:, :, 1] = np.clip(out[:, :, 1] * 0.95 + 6, 0, 255)
            out[:, :, 2] = np.clip(out[:, :, 2] * 0.80, 0, 255)
        elif effect == "cool":
            out[:, :, 0] = np.clip(out[:, :, 0] * 0.9, 0, 255)
            out[:, :, 2] = np.clip(out[:, :, 2] * 1.2 + 8, 0, 255)
        elif effect == "cyber":
            out[:, :, 1] = np.clip(out[:, :, 1] * 1.25, 0, 255)
            out[:, :, 2] = np.clip(out[:, :, 2] * 1.15 + 10, 0, 255)
        elif effect == "thermal":
            lum = np.clip((out[:, :, 0] + out[:, :, 1] + out[:, :, 2]) / 3.0, 0, 255)
            out[:, :, 0] = np.clip((lum - 100) * 2.2, 0, 255)
            out[:, :, 1] = np.clip((255 - np.abs(lum - 128) * 2.0), 0, 255)
            out[:, :, 2] = np.clip((180 - lum) * 2.0, 0, 255)
        elif effect == "glitch":
            shift = int((time.time() * 35) % 14) - 7
            out[:, :, 0] = np.roll(out[:, :, 0], shift, axis=1)
            out[:, :, 2] = np.roll(out[:, :, 2], -shift, axis=0)
        if self.peaking_enabled:
            lum = (out[:,:,0]+out[:,:,1]+out[:,:,2])/3.0
            dx, dy = np.abs(lum[1:-1,1:-1]-lum[1:-1,:-2]), np.abs(lum[1:-1,1:-1]-lum[:-2,1:-1])
            out[1:-1,1:-1][(dx+dy)>30] = [255, 0, 0]
        return np.clip(out, 0, 255).astype(np.uint8)

    def get_param(self, key: str) -> CameraParam | None:
        for p in self.params:
            if p.key == key:
                return p
        return None

    def update_exposure_slider(self, x: int) -> None:
        """Set ExposureValue quickly from slider X position."""
        if self.ev_slider_rect.width <= 0:
            return
        p = self.get_param("ExposureValue")
        if p is None:
            return
        ratio = (x - self.ev_slider_rect.x) / self.ev_slider_rect.width
        ratio = max(0.0, min(1.0, ratio))
        raw = p.min_val + ratio * (p.max_val - p.min_val)
        # Keep 0.2 EV steps for consistency with encoder/UI.
        stepped = round(raw / p.step) * p.step
        p.value = max(p.min_val, min(p.max_val, stepped))
        self.apply_all_controls()

    def draw(self, frame):
        colors = self.theme_colors()
        self.drawn_button_regions = []
        if self.gallery_mode:
            self.screen.fill((0,0,0))
            if self.gallery_base_image:
                rect = self.gallery_base_image.get_rect()
                base_scale = min(self.screen_w / rect.width, self.screen_h / rect.height)
                zoom = max(0.5, min(4.0, self.gallery_zoom))
                w = max(1, int(rect.width * base_scale * zoom))
                h = max(1, int(rect.height * base_scale * zoom))
                img = pygame.transform.smoothscale(self.gallery_base_image, (w, h))
                if abs(self.gallery_angle) > 0.1:
                    img = pygame.transform.rotate(img, self.gallery_angle)
                self.screen.blit(img, img.get_rect(center=(self.screen_w // 2, self.screen_h // 2)))
                # Gallery controls: back + delete.
                pygame.draw.rect(self.screen, (45, 45, 60), (10, 10, 90, 40), border_radius=6)
                self.screen.blit(self.small.render("BACK", True, (255,255,255)), (28, 20))
                pygame.draw.rect(self.screen, (45, 70, 55), (110, 10, 90, 40), border_radius=6)
                self.screen.blit(self.small.render("EDIT", True, (255,255,255)), (136, 20))
                pygame.draw.rect(self.screen, (150, 0, 0), (self.screen_w - 100, self.screen_h - 50, 90, 40), border_radius=5)
                self.screen.blit(self.small.render("DELETE", True, (255,255,255)), (self.screen_w - 85, self.screen_h - 40))
            pygame.display.flip(); return
        frame_surface = pygame.surfarray.make_surface(self.apply_effect(frame).swapaxes(0, 1))
        if self.display_rotation:
            frame_surface = pygame.transform.rotate(frame_surface, self.display_rotation)
        if frame_surface.get_size() != (self.screen_w, self.screen_h):
            frame_surface = pygame.transform.smoothscale(frame_surface, (self.screen_w, self.screen_h))
        px = 0
        self.screen.blit(frame_surface, (px, 0))
        pygame.draw.rect(self.screen, colors["frame_a"], (4, 4, self.screen_w - 8, self.screen_h - 8), width=1, border_radius=10)
        if self.theme_name() != "minimal":
            pygame.draw.rect(self.screen, colors["frame_b"], (6, 6, self.screen_w - 12, self.screen_h - 12), width=1, border_radius=10)
        for r, t, a in self.buttons():
            if a == "capture":
                # Center shutter rendered as neon HUD ring.
                cx, cy = r.center
                radius = r.width // 2
                pygame.draw.circle(self.screen, colors["accent_a"], (cx, cy), radius, width=4)
                pygame.draw.circle(self.screen, colors["accent_b"], (cx, cy), int(radius * 0.62), width=3)
                pygame.draw.circle(self.screen, (70, 90, 120), (cx, cy), int(radius * 0.28), width=2)
                self.drawn_button_regions.append((r, a))
            else:
                # Transparent edge buttons on top of full-screen preview.
                btn = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
                btn.fill(colors["btn_bg"])
                pygame.draw.rect(btn, colors["btn_edge"], pygame.Rect(0, 0, r.width, r.height), width=1, border_radius=8)
                pygame.draw.line(btn, colors["btn_line"], (8, r.height - 3), (r.width - 8, r.height - 3), width=2)
                if a.startswith("theme_set_"):
                    # Pixel-art style text for theme selector buttons.
                    tiny = self.pixel_font.render(t, False, colors["text"])
                    scale = 2
                    pix = pygame.transform.scale(tiny, (tiny.get_width() * scale, tiny.get_height() * scale))
                    btn.blit(pix, pix.get_rect(center=(r.width // 2, r.height // 2)))
                else:
                    label = self.small.render(t, True, colors["text"])
                    btn.blit(label, label.get_rect(center=(r.width // 2, r.height // 2)))
                if self.overlay_rotation:
                    btn = pygame.transform.rotate(btn, self.overlay_rotation)
                draw_rect = btn.get_rect(center=r.center)
                self.screen.blit(btn, draw_rect.topleft)
                self.drawn_button_regions.append((draw_rect, a))
        # Quick exposure slider (EV) for fast correction.
        slider_w = min(420, self.screen_w - 260)
        slider_h = 18
        slider_x = (self.screen_w - slider_w) // 2
        slider_y = self.screen_h - 34
        self.ev_slider_rect = pygame.Rect(slider_x, slider_y, slider_w, slider_h)
        ev_param = self.get_param("ExposureValue")
        if ev_param:
            track = pygame.Surface((slider_w, slider_h), pygame.SRCALPHA)
            track.fill((25, 35, 45, 120))
            self.screen.blit(track, (slider_x, slider_y))
            pygame.draw.rect(self.screen, (185, 220, 255, 140), self.ev_slider_rect, width=1, border_radius=9)
            ratio = (ev_param.value - ev_param.min_val) / (ev_param.max_val - ev_param.min_val)
            ratio = max(0.0, min(1.0, ratio))
            knob_x = slider_x + int(ratio * slider_w)
            pygame.draw.circle(self.screen, (255, 255, 255), (knob_x, slider_y + slider_h // 2), 9, width=2)
            ev_lbl = f"EV {ev_param.value:+.1f}"
            self.screen.blit(self.small.render(ev_lbl, True, (240, 240, 240)), (slider_x - 82, slider_y - 1))
        if self.video_active: pygame.draw.circle(self.screen, (255,0,0), (px+30, 30), 10)
        top_info = []
        if self.cpu_temp > 0:
            top_info.append(f"CPU {int(self.cpu_temp)}C")
        if self.disk_free_mb > 0:
            top_info.append(f"SD {self.disk_free_mb/1024:.1f}GB")
        if self.battery_percent >= 0:
            top_info.append(f"BAT {int(self.battery_percent)}%")
        if top_info:
            # Keep system info on the left side.
            self.screen.blit(self.small.render(" | ".join(top_info), True, colors["info"]), (10, (self.screen_h // 2) - 12))
        fx_lbl = f"FX {EFFECTS[self.effect_idx].upper()}"
        theme_lbl = f"TH {self.theme_name().upper()}"
        self.screen.blit(self.small.render(fx_lbl, True, colors["fx"]), (self.screen_w - 180, 12))
        self.screen.blit(self.small.render(theme_lbl, True, colors["fx"]), (self.screen_w - 180, 34))
        if time.time() < self.message_until:
            # Short transient status line to confirm toggles and failures.
            msg_surface = self.small.render(self.message, True, (255, 220, 120))
            self.screen.blit(msg_surface, (px + 10, 55))
        pygame.display.flip()

    def handle_pointer_press(self, x: int, y: int) -> None:
        """Handle touchscreen/mouse press using pixel coordinates."""
        if self.ev_slider_rect.collidepoint((x, y)):
            self.ev_drag_active = True
            self.update_exposure_slider(x)
            return
        if self.gallery_mode:
            if 10 <= x <= 100 and 10 <= y <= 50:
                self.handle_action("gal_quit")
            elif 110 <= x <= 200 and 10 <= y <= 50:
                self.handle_action("edit")
            elif y < 50 and x > self.screen_w - 100:
                self.handle_action("gal_quit")
            elif y > self.screen_h - 60 and x > self.screen_w - 120:
                self.handle_action("gal_delete")
            elif x < self.screen_w // 2:
                self.handle_action("gal_prev")
            else:
                self.handle_action("gal_next")
            return
        if self.drawn_button_regions:
            for r, a in self.drawn_button_regions:
                if r.collidepoint((x, y)):
                    self.handle_action(a)
                    return
        else:
            for r, _, a in self.buttons():
                if r.collidepoint((x, y)):
                    self.handle_action(a)
                    return

    def _touch_dist_angle(self) -> Tuple[float, float] | None:
        if len(self.active_touches) < 2:
            return None
        points = list(self.active_touches.values())[:2]
        (x1, y1), (x2, y2) = points
        dx, dy = (x2 - x1), (y2 - y1)
        dist = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx))
        return dist, ang

    def handle_finger_down(self, event) -> None:
        self.active_touches[event.finger_id] = (event.x, event.y)
        self.touch_taps[event.finger_id] = (event.x, event.y, time.time())
        if self.gallery_mode and len(self.active_touches) >= 2:
            da = self._touch_dist_angle()
            if da:
                dist, ang = da
                self.gesture_baseline = (dist, ang, self.gallery_zoom, self.gallery_angle)

    def handle_finger_up(self, event) -> None:
        tap = self.touch_taps.pop(event.finger_id, None)
        self.active_touches.pop(event.finger_id, None)
        self.ev_drag_active = False
        if self.gallery_mode and tap and len(self.active_touches) == 0:
            x0, y0, t0 = tap
            if time.time() - t0 < 0.25 and math.hypot(event.x - x0, event.y - y0) < 0.03:
                self.handle_pointer_press(int(event.x * self.screen_w), int(event.y * self.screen_h))
        if len(self.active_touches) < 2:
            self.gesture_baseline = None

    def handle_finger_motion(self, event) -> None:
        if event.finger_id not in self.active_touches:
            return
        self.active_touches[event.finger_id] = (event.x, event.y)
        tap = self.touch_taps.get(event.finger_id)
        if tap and math.hypot(event.x - tap[0], event.y - tap[1]) > 0.03:
            self.touch_taps.pop(event.finger_id, None)
        if not self.gallery_mode and self.ev_drag_active:
            self.update_exposure_slider(int(event.x * self.screen_w))
            return
        if not self.gallery_mode or len(self.active_touches) < 2:
            return
        da = self._touch_dist_angle()
        if not da:
            return
        if not self.gesture_baseline:
            self.gesture_baseline = (*da, self.gallery_zoom, self.gallery_angle)
            return
        base_dist, base_ang, zoom0, angle0 = self.gesture_baseline
        dist, ang = da
        if base_dist > 0.001:
            self.gallery_zoom = max(0.5, min(4.0, zoom0 * (dist / base_dist)))
        d_ang = ang - base_ang
        if d_ang > 180:
            d_ang -= 360
        elif d_ang < -180:
            d_ang += 360
        self.gallery_angle = angle0 + d_ang

    def disk_worker(self):
        """Refresh free disk space every minute to protect capture operations."""
        while True:
            try:
                st = os.statvfs(str(PHOTO_DIR))
                self.disk_free_mb = (st.f_bavail * st.f_frsize) / (1024 * 1024)
            except OSError as exc:
                logger.warning("Disk stat failed: %s", exc)
            time.sleep(60)

    def battery_worker(self):
        """Read battery percentage from known I2C UPS addresses when available."""
        while True:
            if SMBus:
                try:
                    with SMBus(1) as bus:
                        for addr, reg in [(0x75, 0x2A), (0x41, 0x24)]:
                            try:
                                self.battery_percent = float(bus.read_byte_data(addr, reg))
                                break
                            except OSError:
                                continue
                except OSError as exc:
                    logger.debug("Battery read skipped: %s", exc)
            time.sleep(30)

    def sync_worker(self):
        """Run optional photo sync script in background when auto-sync is enabled."""
        while True:
            if self.auto_sync_enabled:
                script = Path(__file__).parent / "sync_photos.sh"
                if script.exists():
                    self.sync_active = True
                    try:
                        subprocess.run([str(script)], check=False, timeout=120)
                    except (OSError, subprocess.SubprocessError) as exc:
                        logger.warning("Sync script failed: %s", exc)
                    finally:
                        self.sync_active = False
            time.sleep(60)

    def web_server_worker(self):
        """Expose a unified web control panel and optional MJPEG live preview."""
        if Flask is None:
            return
        allowed_actions = {
            "capture", "burst", "toggle_video", "gallery",
            "gal_next", "gal_prev", "gal_quit",
            "menu_next", "menu_prev", "param_up", "param_down",
            "toggle_ae", "toggle_awb_lock", "toggle_raw", "toggle_peaking", "toggle_sync", "toggle_timer", "toggle_encoder", "toggle_theme",
            "effect_next", "effect_prev",
        }
        app = Flask(__name__)
        page = """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>PImage Remote</title>
  <style>
    :root { --bg:#101418; --card:#1b232c; --accent:#00b894; --text:#eef3f8; --muted:#9bb0c4; --warn:#ff7675; }
    body { margin:0; font-family: system-ui, sans-serif; background:var(--bg); color:var(--text); }
    .wrap { max-width:1100px; margin:0 auto; padding:16px; display:grid; grid-template-columns: 2fr 1fr; gap:16px; }
    .card { background:var(--card); border-radius:12px; padding:14px; }
    h1,h2 { margin:0 0 10px 0; font-weight:700; }
    h1 { font-size:1.2rem; }
    h2 { font-size:1rem; color:var(--muted); }
    .live-wrap { aspect-ratio: 4 / 3; background:#000; border-radius:10px; overflow:hidden; display:flex; align-items:center; justify-content:center; }
    #live { width:100%; height:100%; object-fit:contain; background:#000; display:none; }
    .grid { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:8px; }
    button { border:0; border-radius:10px; padding:10px; color:#fff; background:#2c3e50; cursor:pointer; font-weight:600; }
    button.primary { background:var(--accent); color:#09241f; }
    button.warn { background:var(--warn); }
    .state { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:8px; font-size:.92rem; }
    .pill { background:#253140; border-radius:8px; padding:8px; }
    .muted { color:var(--muted); }
    label { display:flex; align-items:center; gap:8px; }
    @media (max-width: 900px) { .wrap { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="card">
      <h1>Controle PImage</h1>
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <label><input id="liveToggle" type="checkbox"> Live view active</label>
        <span id="statusMsg" class="muted">-</span>
      </div>
      <div class="live-wrap">
        <img id="live" alt="Live preview">
        <span id="liveOff" class="muted">Live desactive</span>
      </div>
      <h2 style="margin-top:14px;">Actions</h2>
      <div class="grid">
        <button class="primary" data-action="capture">CAPTURE</button>
        <button data-action="burst">BURST</button>
        <button data-action="toggle_video">VIDEO</button>
        <button data-action="toggle_timer">TIMER</button>
        <button data-action="gallery">GALLERY</button>
        <button data-action="gal_quit">EXIT GAL</button>
        <button data-action="toggle_raw">RAW</button>
        <button data-action="toggle_peaking">PEAK</button>
        <button data-action="toggle_sync">SYNC</button>
        <button data-action="toggle_ae">AE</button>
        <button data-action="toggle_awb_lock">AWB LOCK</button>
        <button data-action="toggle_encoder">ENC</button>
      </div>
    </section>
    <aside class="card">
      <h1>Etat Systeme</h1>
      <div class="state">
        <div class="pill">Menu: <b id="stMenu">-</b></div>
        <div class="pill">Message: <b id="stMessage">-</b></div>
        <div class="pill">Battery: <b id="stBat">-</b></div>
        <div class="pill">CPU: <b id="stCpu">-</b></div>
        <div class="pill">Disk: <b id="stDisk">-</b></div>
        <div class="pill">Video: <b id="stVideo">-</b></div>
        <div class="pill">RAW: <b id="stRaw">-</b></div>
        <div class="pill">Sync: <b id="stSync">-</b></div>
      </div>
    </aside>
  </div>
  <script>
    const live = document.getElementById("live");
    const liveOff = document.getElementById("liveOff");
    const liveToggle = document.getElementById("liveToggle");
    const statusMsg = document.getElementById("statusMsg");

    async function api(path, opts={}) {
      const res = await fetch(path, opts);
      if (!res.ok) throw new Error(await res.text());
      return res.headers.get("content-type")?.includes("application/json") ? res.json() : res.text();
    }
    async function sendAction(action) {
      statusMsg.textContent = "Action: " + action;
      try { await api("/api/action/" + action, { method: "POST" }); } catch (e) { statusMsg.textContent = "Erreur: " + e.message; }
    }
    function setLive(enabled) {
      if (enabled) {
        live.style.display = "block";
        liveOff.style.display = "none";
        live.src = "/stream.mjpg?t=" + Date.now();
      } else {
        live.style.display = "none";
        liveOff.style.display = "inline";
        live.src = "";
      }
    }
    async function toggleLive(enabled) {
      try {
        const state = await api("/api/live", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({enabled}) });
        liveToggle.checked = !!state.web_live_enabled;
        setLive(!!state.web_live_enabled);
      } catch (e) {
        statusMsg.textContent = "Live indisponible: " + e.message;
        liveToggle.checked = false;
        setLive(false);
      }
    }
    async function refreshState() {
      try {
        const st = await api("/api/state");
        document.getElementById("stMenu").textContent = st.menu;
        document.getElementById("stMessage").textContent = st.message;
        document.getElementById("stBat").textContent = st.battery;
        document.getElementById("stCpu").textContent = st.cpu_temp;
        document.getElementById("stDisk").textContent = st.disk;
        document.getElementById("stVideo").textContent = st.video_active ? "ON" : "OFF";
        document.getElementById("stRaw").textContent = st.raw_enabled ? "ON" : "OFF";
        document.getElementById("stSync").textContent = st.sync_enabled ? "ON" : "OFF";
        liveToggle.checked = !!st.web_live_enabled;
        if (st.web_live_enabled && !live.src) setLive(true);
      } catch (e) {
        statusMsg.textContent = "Etat indisponible";
      }
    }
    for (const btn of document.querySelectorAll("button[data-action]")) {
      btn.addEventListener("click", () => sendAction(btn.dataset.action));
    }
    liveToggle.addEventListener("change", (e) => toggleLive(e.target.checked));
    refreshState();
    setInterval(refreshState, 1200);
  </script>
</body>
</html>
"""

        def state_payload() -> dict:
            return {
                "menu": self.current_menu().value,
                "message": self.message,
                "battery": f"{int(self.battery_percent)}%" if self.battery_percent >= 0 else "N/A",
                "cpu_temp": f"{int(self.cpu_temp)}C" if self.cpu_temp > 0 else "N/A",
                "disk": f"{self.disk_free_mb/1024:.1f}GB" if self.disk_free_mb > 0 else "N/A",
                "video_active": self.video_active,
                "raw_enabled": self.raw_enabled,
                "sync_enabled": self.auto_sync_enabled,
                "web_live_enabled": self.web_live_enabled,
                "theme": self.theme_name(),
            }

        @app.route("/")
        def index():
            return render_template_string(page)

        @app.route("/api/state")
        def state():
            return jsonify(state_payload())

        @app.route("/api/action/<cmd>", methods=["POST"])
        def action(cmd):
            if cmd not in allowed_actions and not cmd.startswith("effect_set_") and not cmd.startswith("theme_set_"):
                return "Unsupported action", 400
            self.handle_action(cmd)
            return jsonify({"ok": True, "action": cmd, **state_payload()})

        @app.route("/api/live", methods=["POST"])
        def live_toggle():
            data = request.get_json(silent=True) or {}
            self.web_live_enabled = bool(data.get("enabled", False))
            self.save_user_state()
            return jsonify(state_payload())

        @app.route("/stream.mjpg")
        def stream():
            if cv2 is None:
                return "OpenCV missing (python3-opencv)", 503

            def generate():
                while True:
                    if not self.web_live_enabled:
                        time.sleep(0.2)
                        continue
                    with self.frame_lock:
                        frame = None if self.last_web_frame is None else self.last_web_frame.copy()
                    if frame is None:
                        time.sleep(0.05)
                        continue
                    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                    if not ok:
                        time.sleep(0.05)
                        continue
                    jpg = buf.tobytes()
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                    time.sleep(0.04)

            return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

        app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False)

    def run(self) -> None:
        try:
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT: raise SystemExit
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: raise SystemExit
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        self.handle_pointer_press(*event.pos)
                    if event.type == pygame.MOUSEBUTTONUP:
                        self.ev_drag_active = False
                    if event.type == pygame.MOUSEMOTION and self.ev_drag_active:
                        self.update_exposure_slider(event.pos[0])
                    if event.type == pygame.FINGERDOWN:
                        self.handle_finger_down(event)
                        if not self.gallery_mode:
                            tx = int(event.x * self.screen_w)
                            ty = int(event.y * self.screen_h)
                            self.handle_pointer_press(tx, ty)
                    if event.type == pygame.FINGERUP:
                        self.handle_finger_up(event)
                    if event.type == pygame.FINGERMOTION:
                        self.handle_finger_motion(event)
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_LEFT: self.handle_action("gal_prev" if self.gallery_mode else "menu_prev")
                        if event.key == pygame.K_RIGHT: self.handle_action("gal_next" if self.gallery_mode else "menu_next")
                        if event.key == pygame.K_UP: self.handle_action("param_up")
                        if event.key == pygame.K_DOWN: self.handle_action("param_down")
                        if event.key in (pygame.K_SPACE, pygame.K_RETURN): self.handle_action("capture")
                if self.timelapse_active and time.time()-self.timelapse_last_shot >= self.timelapse_interval: self.capture(); self.timelapse_last_shot = time.time()
                if self.timer_active and time.time()-self.timer_start_time >= self.self_timer_delay: self.timer_active = False; self.capture(force=True)
                self.handle_encoder_input()
                if time.time()-self.last_cpu_check > 5:
                    try:
                        with open('/sys/class/thermal/thermal_zone0/temp') as f: self.cpu_temp = float(f.read())/1000.0
                    except (OSError, ValueError) as exc:
                        logger.debug("CPU temp read failed: %s", exc)
                    self.last_cpu_check = time.time()
                try:
                    frame = self.camera.capture_array()
                except Exception as exc:
                    self.capture_failures += 1
                    logger.error("Frame capture failed (%d): %s", self.capture_failures, exc)
                    self.notify("Camera timeout - retry", timeout=2.0)
                    if not self.recover_camera():
                        self.notify("Camera unavailable", timeout=3.0)
                        time.sleep(1.0)
                    continue
                with self.frame_lock:
                    self.last_web_frame = frame.copy()
                self.draw(frame)
                self.clock.tick(25)
        except KeyboardInterrupt:
            logger.info("Interrupted by user (CTRL+C).")
        finally:
            if getattr(self, "video_active", False):
                try:
                    self.camera.stop_recording()
                except Exception:
                    pass
            self.disable_encoder()
            self.save_user_state()
            try:
                self.camera.stop()
            except BaseException as exc:
                logger.warning("Camera stop interrupted/failed: %s", exc)
            pygame.quit()

def main() -> int:
    app = CameraApp()
    app.run()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
