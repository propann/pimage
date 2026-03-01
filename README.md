# PImage — Appareil photo portable CM4

Repo de départ pour construire un logiciel d'appareil photo **simple, rapide et agréable** inspiré des meilleurs boîtiers, adapté à ton prototype CM4 + écran DSI tactile.

## Ce qu'il y a dans ce repo

- `app_photo.py` : point d'entrée principal.
- `src/pimage_camera/` : logique du menu et du workflow photo.
- `dossier_technique/README.md` : topo technique prêt à enrichir avec logs + schémas.
- `tests/` : tests de la machine d'état du menu.

## Vision produit (UX)

- Interface minimaliste: **capture instantanée**, accès rapide galerie, réglages clairs.
- Navigation hybride tactile + encodeur.
- Paramètres en premier plan: ISO, shutter, exposure, contrast, saturation.
- Architecture prête pour ajouter:
  - preview DRM/Picamera2,
  - upload WiFi (Dropbox/Drive),
  - entrées Bluetooth,
  - profils de rendu ("street", "portrait", "nuit").

## Lancer une démo locale

```bash
python3 app_photo.py --output-dir photos --demo-steps 8
```

> Dans cet environnement, le backend est mocké pour permettre le développement sans matériel CM4.

## Tests

```bash
python3 -m pytest -q
```

## Étapes suivantes recommandées

1. Brancher le vrai backend Picamera2 dans `hardware.py`.
2. Ajouter l'UI Pygame (layout gauche preview / droite réglages).
3. Mapper l'encodeur GPIO (17/18/27) sur `rotate()` + `click()`.
4. Ajouter service systemd + logs boot dans `dossier_technique/`.
