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
    from flask import Flask
except ImportError:
    Flask = None

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
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("DejaVuSans", 21)
        self.small = pygame.font.SysFont("DejaVuSans", 17)
        self.camera = Picamera2()
        config = self.camera.create_preview_configuration(main={"size": (PREVIEW_W, SCREEN_H), "format": "RGB888"}, buffer_count=3)
        self.camera.configure(config)
        self.camera.start()

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
        self.encoder_enabled = False

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
        if GPIO is None:
            return
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup([ENC_CLK, ENC_DT, ENC_SW], GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(ENC_CLK, GPIO.FALLING, callback=self._encoder_callback, bouncetime=5)
            GPIO.add_event_detect(ENC_SW, GPIO.FALLING, callback=self._button_callback, bouncetime=300)
            self.encoder_enabled = True
        except Exception as exc:
            logger.warning("GPIO encoder setup failed: %s", exc)

    def _encoder_callback(self, ch):
        if self.gallery_mode: self.handle_action("gal_next" if GPIO.input(ENC_DT) else "gal_prev")
        else: self.handle_action("param_up" if GPIO.input(ENC_DT) else "param_down")

    def _button_callback(self, ch):
        if self.gallery_mode: self.handle_action("gal_quit")
        elif self.current_menu() == Menu.CAPTURE: self.handle_action("capture")
        else: self.handle_action("menu_next")

    def notify(self, t, timeout=1.6): self.message, self.message_until = t, time.time() + timeout

    def apply_all_controls(self) -> None:
        ctrls = {"AeEnable": self.auto_exposure, "AwbMode": self.awb_modes[self.awb_mode_idx][1], "AwbLocked": self.awb_locked}
        for p in self.params:
            if p.key == "ExposureTime" and self.auto_exposure: continue
            ctrls[p.key] = int(p.value) if p.key == "ExposureTime" else p.value
        self.camera.set_controls(ctrls)

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
            scale = min(SCREEN_W/rect.width, SCREEN_H/rect.height)
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
        if m == Menu.CAPTURE: return [("CAPTURE", "capture"), ("BURST", "burst"), ("VIDEO", "toggle_video"), ("TIMER", "toggle_timer"), ("NEXT", "menu_next")]
        if m == Menu.TUNE: return [("P+", "param_up"), ("P-", "param_down"), ("NEXT P", "next"), ("AE", "toggle_ae"), ("AWB LOCK", "toggle_awb_lock"), ("NEXT", "menu_next")]
        if m == Menu.SYSTEM: return [("GALLERY", "gallery"), ("SYNC", "toggle_sync"), ("RAW", "toggle_raw"), ("PEAK", "toggle_peaking"), ("NEXT", "menu_next"), ("OFF", "shutdown"), ("QUIT", "quit")]
        return [("NEXT", "menu_next")]

    def buttons(self):
        is_left = (self.current_menu() == Menu.SYSTEM)
        x_base = 0 if is_left else PREVIEW_W
        return [(pygame.Rect(x_base+MARGIN, 60+(BUTTON_H+7)*i, PANEL_W-2*MARGIN, BUTTON_H), t, a) for i, (t, a) in enumerate(self.menu_buttons())]

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
                self.screen.blit(self.current_image, self.current_image.get_rect(center=(400,240)))
                # Delete button overlay
                pygame.draw.rect(self.screen, (150, 0, 0), (SCREEN_W-100, SCREEN_H-50, 90, 40), border_radius=5)
                self.screen.blit(self.small.render("DELETE", True, (255,255,255)), (SCREEN_W-85, SCREEN_H-40))
            pygame.display.flip(); return
        is_left = (self.current_menu() == Menu.SYSTEM)
        px, pax = (PANEL_W, 0) if is_left else (0, PREVIEW_W)
        self.screen.blit(pygame.surfarray.make_surface(self.apply_effect(frame).swapaxes(0,1)), (px, 0))
        pygame.draw.rect(self.screen, (20,20,20), (pax, 0, PANEL_W, SCREEN_H))
        for r, t, a in self.buttons():
            pygame.draw.rect(self.screen, (50,50,50), r, border_radius=5)
            self.screen.blit(self.small.render(t, True, (255,255,255)), (r.x+5, r.y+10))
        if self.video_active: pygame.draw.circle(self.screen, (255,0,0), (px+30, 30), 10)
        if self.battery_percent >= 0: self.screen.blit(self.small.render(f"BAT: {int(self.battery_percent)}%", True, (255,255,255)), (px+PREVIEW_W-80, 20))
        if self.cpu_temp > 0: self.screen.blit(self.small.render(f"{int(self.cpu_temp)}C", True, (255,100,0)), (px+PREVIEW_W-80, 40))
        if self.disk_free_mb > 0: self.screen.blit(self.small.render(f"SD: {self.disk_free_mb/1024:.1f}GB", True, (200,200,200)), (px+10, SCREEN_H-30))
        if time.time() < self.message_until:
            # Short transient status line to confirm toggles and failures.
            msg_surface = self.small.render(self.message, True, (255, 220, 120))
            self.screen.blit(msg_surface, (px + 10, 55))
        pygame.display.flip()

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
        """Expose minimal remote actions over HTTP for local network usage."""
        if Flask is None:
            return
        allowed_actions = {
            "capture", "burst", "toggle_video", "gallery",
            "gal_next", "gal_prev", "gal_quit",
            "menu_next", "menu_prev", "param_up", "param_down",
            "toggle_ae", "toggle_awb_lock", "toggle_raw", "toggle_peaking", "toggle_sync", "toggle_timer",
        }
        app = Flask(__name__)
        @app.route("/")
        def index(): return "PImage Remote <a href='/action/capture'>CAPTURE</a>"
        @app.route("/action/<cmd>")
        def action(cmd):
            if cmd not in allowed_actions:
                return "Unsupported action", 400
            self.handle_action(cmd)
            return "OK"
        app.run(host="0.0.0.0", port=5000)

    def run(self) -> None:
        try:
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT: raise SystemExit
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: raise SystemExit
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if self.gallery_mode:
                            x, y = event.pos
                            if y < 50 and x > SCREEN_W - 100: self.handle_action("gal_quit")
                            elif y > SCREEN_H - 60 and x > SCREEN_W - 120: self.handle_action("gal_delete")
                            elif x < SCREEN_W // 2: self.handle_action("gal_prev")
                            else: self.handle_action("gal_next")
                        else:
                            for r, t, a in self.buttons():
                                if r.collidepoint(event.pos): self.handle_action(a)
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_LEFT: self.handle_action("gal_prev" if self.gallery_mode else "menu_prev")
                        if event.key == pygame.K_RIGHT: self.handle_action("gal_next" if self.gallery_mode else "menu_next")
                        if event.key == pygame.K_UP: self.handle_action("param_up")
                        if event.key == pygame.K_DOWN: self.handle_action("param_down")
                        if event.key in (pygame.K_SPACE, pygame.K_RETURN): self.handle_action("capture")
                if self.timelapse_active and time.time()-self.timelapse_last_shot >= self.timelapse_interval: self.capture(); self.timelapse_last_shot = time.time()
                if self.timer_active and time.time()-self.timer_start_time >= self.self_timer_delay: self.timer_active = False; self.capture(force=True)
                if time.time()-self.last_cpu_check > 5:
                    try:
                        with open('/sys/class/thermal/thermal_zone0/temp') as f: self.cpu_temp = float(f.read())/1000.0
                    except (OSError, ValueError) as exc:
                        logger.debug("CPU temp read failed: %s", exc)
                    self.last_cpu_check = time.time()
                frame = self.camera.capture_array()
                self.last_web_frame = frame.copy()
                self.draw(frame)
                self.clock.tick(25)
        finally:
            if self.video_active:
                try:
                    self.camera.stop_recording()
                except Exception:
                    pass
            self.save_user_state()
            self.camera.stop()
            pygame.quit()

if __name__ == "__main__":
    app = CameraApp()
    app.run()
