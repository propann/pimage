# pimage

Mini application photo orientée Raspberry Pi 4 / CM4 + écran tactile DSI.

## Fonctionnalités

- Preview live plein écran via **Picamera2**.
- UI tactile Pygame avec boutons larges.
- Capture photo JPG dans `~/photos`.
- Réglages rapides:
  - Exposure Value
  - Analogue Gain
  - Brightness
  - Contrast
  - Saturation
  - Sharpness
  - ExposureTime (manuel)
- Modes AWB (auto/tungsten/fluo/indoor/daylight/cloudy).
- Presets **glitch**: `acid`, `noir`, `dream`, `burn`, `clean`.

## Installation (Raspberry Pi OS Bookworm)

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-pygame
```

## Lancer l'app

```bash
python3 app_photo.py
```

### Contrôles clavier (debug)

- `Space`/`Enter`: capture
- `↑`/`↓`: paramètre +/-
- `←`/`→`: paramètre précédent/suivant
- `a`: auto exposure ON/OFF
- `w`: AWB suivant
- `Esc`: quitter

## Notes hardware

- Pensé pour écran 800x480 en paysage.
- Le panneau de contrôle est à droite, preview caméra à gauche.
- Les photos sont sauvegardées en local (overlay fs désactivé recommandé).
