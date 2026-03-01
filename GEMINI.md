# pimage - Gemini CLI Context

This project is a Raspberry Pi-based camera application designed for use with a 7-inch DSI touchscreen (800x480). It provides a full-screen interactive UI for photo capture, manual camera tuning, and real-time creative effects.

## Project Overview

- **Purpose:** Transform a Raspberry Pi (RPi4/CM4) into a creative standalone camera.
- **Main Technologies:**
    - **Python 3**: Core logic.
    - **Picamera2**: Interface with the Raspberry Pi camera module (libcamera-based).
    - **Pygame**: UI rendering and event handling for the touchscreen.
    - **Numpy**: Fast image processing for real-time preview effects.
- **Architecture:**
    - `app_photo.py`: Monolithic application containing the `CameraApp` class which manages the camera lifecycle, UI state, and user interactions.
    - **UI Layout:** Landscape 800x480. Left side is the camera preview (480x480), right side is a 320px wide control panel with touch-friendly buttons.
    - **State Management:** Camera parameters are stored in `CameraParam` dataclasses; user profiles are persisted in `~/.pimage_profiles.json`.

## Building and Running

### Prerequisites

The application requires Raspberry Pi OS (Bookworm or newer) with `libcamera` support.

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-pygame python3-numpy
```

### Running the Application

```bash
python3 app_photo.py
```

*Note: Running from a TTY (not via SSH) is recommended for best performance on the Raspberry Pi's DRM display.*

### Key Controls

- **Touchscreen:** All buttons on the right panel are interactive.
- **Keyboard (for debugging):**
    - `Space`/`Enter`: Capture photo.
    - `Arrow Keys`: Navigate menus and parameters.
    - `a`: Toggle Auto Exposure.
    - `w`: Cycle AWB modes.
    - `p`: Cycle color profiles.
    - `e`: Cycle preview effects.
    - `g`: Cycle framing grids.
    - `Esc`: Quit.

## Project Structure

- `app_photo.py`: Main entry point and single-file codebase.
- `README.md`: General project description and hardware notes.
- `~/photos/`: Default directory where captured JPGs are saved.
- `~/.pimage_profiles.json`: Persistent storage for user settings (Slots A/B/C).

## Development Conventions

- **Typing:** Strict use of Python type hints (`from __future__ import annotations`).
- **Style:** Clean, modular structure within a single class. Logical grouping of constants (SCREEN_W, PANEL_W, etc.) at the top.
- **Testing:** Currently, there is no automated test suite. Manual verification on target hardware is the primary validation method.
- **Hardware Integration:**
    - Uses `RPi.GPIO` for optional rotary encoder support (constants like `ENC_CLK` may need verification in the code).
    - Designed specifically for the Raspberry Pi camera stack; may not run on non-RPi systems without mocking `Picamera2`.

## Current Features

1. **Capture Workflow:** Quick capture with live preview.
2. **Tuning:** Manual control over Exposure EV, Gain, Brightness, Contrast, Saturation, and Sharpness.
3. **Color Science:** Built-in profiles (Natural, Vivid, Cinema, Mono, Retro).
4. **Live Effects:** Real-time preview filters (Noir, Vintage, Cyber, Thermal).
5. **Composition Aids:** Multiple overlay grids (Thirds, Quarters, Golden Phi, etc.).
6. **Persistence:** Save and load camera configurations to slots.
