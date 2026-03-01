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

EFFECTS = ["none", "noir", "vintage", "cyber", "thermal"]
GRIDS = ["off", "thirds", "quarters", "crosshair", "diagonal-x", "golden-phi"]

class CameraApp:
    def __init__(self) -> None:
        if Picamera2 is None: raise RuntimeError("Picamera2 missing")
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
        self.screen_w, self.screen_h = self.screen.get_size()
        self.panel_w = max(150, min(260, self.screen_w // 4))
        self.preview_w = self.screen_w
        self.menu_x = max(8, int(self.screen_w * 0.25) - (self.panel_w // 2))
        # Default to 90° left rotation for landscape-mounted displays.
        self.display_rotation = int(os.getenv("PIMAGE_ROTATE", "90"))
        if self.display_rotation not in {0, 90, 180, 270}:
            self.display_rotation = 0
        self.edge_buttons_per_side = max(2, min(4, int(os.getenv("PIMAGE_BTNS_SIDE", "3"))))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("DejaVuSans", 21)
        self.small = pygame.font.SysFont("DejaVuSans", 17)
        self.camera = Picamera2()
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
        self.timelapse_active, self.timelapse_interval, self.timelapse_last_shot, self.timelapse_count = False, 5.0, 0.0, 0
        self.raw_enabled, self.bracketing_enabled, self.peaking_enabled = False, False, False
        self.awb_locked = False
        self.auto_sync_enabled, self.sync_active, self.battery_percent = False, False, -1.0
        self.video_active, self.video_start_time, self.burst_count = False, 0.0, 5
        self.self_timer_delay, self.timer_active, self.timer_start_time = 0, False, 0.0
        self.cpu_temp, self.last_cpu_check, self.last_web_frame = 0.0, 0.0, None
        self.disk_free_mb = 0.0
        self.gallery_mode, self.gallery_files, self.gallery_index, self.current_image = False, [], 0, None
        self.message, self.message_until, self.last_capture = "Ready", 0.0, "-"
        self.capture_failures = 0
        self.encoder_requested = os.getenv("PIMAGE_ENCODER", "1").strip().lower() not in {"0", "false", "off", "no"}
        self.encoder_enabled = False
        self.web_live_enabled = os.getenv("PIMAGE_WEB_LIVE", "0").strip().lower() in {"1", "true", "on", "yes"}
        self.frame_lock = threading.Lock()

        self.apply_color_profile("natural", notify=False)
        self.load_user_state()
        self.apply_all_controls()
        self.setup_encoder()
        threading.Thread(target=self.sync_worker, daemon=True).start()
        threading.Thread(target=self.battery_worker, daemon=True).start()
        threading.Thread(target=self.disk_worker, daemon=True).start()
        if Flask: threading.Thread(target=self.web_server_worker, daemon=True).start()

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
            "color_profile": self.color_profile,
        }
        tmp_file = PROFILE_FILE.with_suffix(".tmp")
        try:
            tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp_file.replace(PROFILE_FILE)
        except OSError as exc:
            logger.warning("Failed to save user state: %s", exc)

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
                if self.raw_enabled: self.camera.capture_file(str(PHOTO_DIR / f"img_{ts}.dng"), format="dng")
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
            rect = img.get_rect()
            scale = min(self.screen_w / rect.width, self.screen_h / rect.height)
            self.current_image = pygame.transform.scale(img, (int(rect.width*scale), int(rect.height*scale)))
        except (pygame.error, IndexError, FileNotFoundError) as exc:
            logger.warning("Failed to load gallery image: %s", exc)
            self.current_image = None

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
            return [("BURST", "burst"), ("VIDEO", "toggle_video"), ("TIMER", "toggle_timer"), ("GALLERY", "gallery"), ("NEXT", "menu_next"), ("BACK", "menu_prev")]
        if m == Menu.TUNE:
            return [("P+", "param_up"), ("P-", "param_down"), ("NEXT P", "next"), ("AE", "toggle_ae"), ("AWB", "toggle_awb_lock"), ("BACK", "menu_prev")]
        if m == Menu.COLOR:
            return [("RAW", "toggle_raw"), ("PEAK", "toggle_peaking"), ("SYNC", "toggle_sync"), ("TIMER", "toggle_timer"), ("NEXT", "menu_next"), ("BACK", "menu_prev")]
        if m == Menu.EFFECT:
            return [("AE", "toggle_ae"), ("AWB", "toggle_awb_lock"), ("RAW", "toggle_raw"), ("PEAK", "toggle_peaking"), ("NEXT", "menu_next"), ("BACK", "menu_prev")]
        if m == Menu.TIMELAPSE:
            return [("TIMER", "toggle_timer"), ("SYNC", "toggle_sync"), ("BURST", "burst"), ("VIDEO", "toggle_video"), ("NEXT", "menu_next"), ("BACK", "menu_prev")]
        if m == Menu.SYSTEM:
            enc_label = f"ENC {'ON' if self.encoder_enabled else 'OFF'}"
            return [("GALLERY", "gallery"), (enc_label, "toggle_encoder"), ("SYNC", "toggle_sync"), ("RAW", "toggle_raw"), ("OFF", "shutdown"), ("BACK", "menu_prev")]
        return [("NEXT", "menu_next"), ("BACK", "menu_prev")]

    def buttons(self):
        max_visible = self.edge_buttons_per_side * 2
        actions = self.menu_buttons()[:max_visible]
        rows = max(1, min(self.edge_buttons_per_side, math.ceil(len(actions) / 2)))
        top_y = max(35, int(self.screen_h * 0.15))
        available_h = max(120, self.screen_h - top_y - 140)
        step = max(BUTTON_H + 10, available_h // max(1, rows))
        left_x = 10
        right_x = self.screen_w - self.panel_w - 10
        edge_buttons = []
        for idx, (title, action) in enumerate(actions):
            side_left = idx < rows
            row_idx = idx if side_left else idx - rows
            x = left_x if side_left else right_x
            y = top_y + row_idx * step
            edge_buttons.append((pygame.Rect(x, y, self.panel_w, BUTTON_H), title, action))
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
        if self.peaking_enabled:
            lum = (out[:,:,0]+out[:,:,1]+out[:,:,2])/3.0
            dx, dy = np.abs(lum[1:-1,1:-1]-lum[1:-1,:-2]), np.abs(lum[1:-1,1:-1]-lum[:-2,1:-1])
            out[1:-1,1:-1][(dx+dy)>30] = [255, 0, 0]
        return np.clip(out, 0, 255).astype(np.uint8)

    def draw(self, frame):
        if self.gallery_mode:
            self.screen.fill((0,0,0))
            if self.current_image:
                self.screen.blit(self.current_image, self.current_image.get_rect(center=(self.screen_w // 2, self.screen_h // 2)))
                # Delete button overlay
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
        for r, t, a in self.buttons():
            if a == "capture":
                # Central shutter button: outer ring only, transparent center.
                cx, cy = r.center
                radius = r.width // 2
                pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), radius, width=3)
            else:
                # Transparent edge buttons on top of full-screen preview.
                btn = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
                btn.fill((20, 30, 40, 100))
                self.screen.blit(btn, (r.x, r.y))
                pygame.draw.rect(self.screen, (180, 220, 255, 130), r, width=1, border_radius=8)
                # Rotate labels based on side so text reads toward image center.
                label = self.small.render(t, True, (240, 240, 240))
                label = pygame.transform.rotate(label, -90 if r.centerx < (self.screen_w // 2) else 90)
                self.screen.blit(label, label.get_rect(center=r.center))
        if self.video_active: pygame.draw.circle(self.screen, (255,0,0), (px+30, 30), 10)
        top_info = []
        if self.cpu_temp > 0:
            top_info.append(f"CPU {int(self.cpu_temp)}C")
        if self.disk_free_mb > 0:
            top_info.append(f"SD {self.disk_free_mb/1024:.1f}GB")
        if self.battery_percent >= 0:
            top_info.append(f"BAT {int(self.battery_percent)}%")
        if top_info:
            self.screen.blit(self.small.render(" | ".join(top_info), True, (235, 235, 235)), (10, 12))
        if time.time() < self.message_until:
            # Short transient status line to confirm toggles and failures.
            msg_surface = self.small.render(self.message, True, (255, 220, 120))
            self.screen.blit(msg_surface, (px + 10, 55))
        pygame.display.flip()

    def handle_pointer_press(self, x: int, y: int) -> None:
        """Handle touchscreen/mouse press using pixel coordinates."""
        if self.gallery_mode:
            if y < 50 and x > self.screen_w - 100:
                self.handle_action("gal_quit")
            elif y > self.screen_h - 60 and x > self.screen_w - 120:
                self.handle_action("gal_delete")
            elif x < self.screen_w // 2:
                self.handle_action("gal_prev")
            else:
                self.handle_action("gal_next")
            return
        for r, _, a in self.buttons():
            if r.collidepoint((x, y)):
                self.handle_action(a)
                return

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
            "toggle_ae", "toggle_awb_lock", "toggle_raw", "toggle_peaking", "toggle_sync", "toggle_timer", "toggle_encoder",
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
            }

        @app.route("/")
        def index():
            return render_template_string(page)

        @app.route("/api/state")
        def state():
            return jsonify(state_payload())

        @app.route("/api/action/<cmd>", methods=["POST"])
        def action(cmd):
            if cmd not in allowed_actions:
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
                    if event.type == pygame.FINGERDOWN:
                        tx = int(event.x * self.screen_w)
                        ty = int(event.y * self.screen_h)
                        self.handle_pointer_press(tx, ty)
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
