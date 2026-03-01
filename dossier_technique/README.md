# Topo Technique Projet Freelance Portable CM4

## Contexte
- **Objectif** : Appareil portable freelance (photo/video) basé sur Raspberry Pi CM4 pour usage "à mon compte".
- **Hardware** : CM4-NANO-B Waveshare, écran DSI 4" Waveshare (480x800, tactile Goodix), caméra OV5647 UC261 via CSI ruban, batterie 5V/3A+, encodeur rotatif KY-040.
- **Software** : Raspberry Pi OS Bookworm CLI, Picamera2 pour caméra, Pygame pour interface tactile, RPi.GPIO pour encodeur.
- **Firmware** : Version 2025-08-20, hash cd866525580337c0aee4b25880e1f5f9f674fb24, capabilities 0x0000007f.
- **Boot** : CLI multi-user.target, temps ~10-15s après optimisation, services conservés WiFi/Bluetooth/son.

## Configuration
- `config.txt` : DSI transform=1 (90° horaire), HDMI off, `dtoverlay=ov5647,cam0`, `dtparam=ov5647,clock-frequency=24000000`, `gpu_mem=128`.
- Logs clés : CSI/DSI bound vc4-drm, i2c mux OK, no I2C timeout, vc4-drm fb0 frame buffer device.
- Schémas : Encodeur CLK GPIO 17, DT 18, SW 27, VCC 3.3V, GND GND.
- Appareil : Script `app_photo.py` avec preview constant, menus overlay, réglages ISO / shutter / AWB / exposure / contrast / saturation.

## Développement
- Base Git de référence : <https://github.com/juckettd/RaspberryPiCM4Handheld7Inch>
- Code principal : Picamera2 + Pygame + RPi.GPIO (preview live, boutons, encodeur navigation).
- Autostart : service `app_photo.service` pour boot CLI auto.

## Tests
- Preview : fluide ~28fps, DRM DSI tactile.
- Capture : photos JPG sauvegardées, affichées via fbi.
- Encodeur : rotation sélectionne menu/réglage, bouton valide/capture.

## BOM approximatif
- CM4 + NANO-B : ~50€
- Écran DSI 4" : ~30€
- Caméra OV5647 : ~10€
- Encodeur KY-040 : ~5€
- Batterie PiSugar : ~25€
- Boîte bois custom : ~20€
- Total : ~140€

## Prochaines étapes
- Intégrer encodeur + batterie.
- Optimiser code pour menus décalés.
- Fabriquer boîte bois Tinkercad.
