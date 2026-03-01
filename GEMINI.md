# pimage - Freelance CM4 Adaptation

Logiciel "béton" pour prototype d'appareil photo CM4 avec écran DSI et contrôles physiques.

## Nouvelles Fonctionnalités (Adaptation CM4)

- **Encodeur Rotatif (BCM 17, 18, 27)**: Navigation dans les réglages et capture physique via callbacks GPIO interrompus.
- **Modes Créatifs**: Mode Vidéo (H.264), Mode Rafale (5, 10, 20 images), Retardateur (2s, 5s, 10s) et Time-lapse complet.
- **Support Pro (RAW & Bracketing)**: Capture simultanée JPG + DNG (RAW), mode Bracketing d'exposition (3 photos auto) et Verrouillage AWB (Balance des blancs).
- **Aides à la prise de vue**: Histogramme Live et Focus Peaking (surlignage des zones nettes en rouge) en temps réel.
- **Sécurité & Robustesse**: Monitoring de l'espace disque, surveillance thermique CPU, bouton OFF (shutdown propre) et forçage de l'écriture SD (os.sync) après chaque capture.
- **Galerie Native**: Visionneuse d'images intégrée avec fonction de suppression (Delete) pour le tri sur le terrain.
- **Logging Robuste**: Logs persistants dans `~/pimage.log` pour le debug terrain.
- **Service Systemd**: Prêt pour l'autostart en mode kiosque.

## Configuration Matérielle (GPIO)

| Composant | Pin BCM | Fonction |
|-----------|---------|----------|
| ENC_CLK   | 17      | Clock Encodeur |
| ENC_DT    | 18      | Data Encodeur |
| ENC_SW    | 27      | Switch (Capture/Valide) |

## Installation & Autostart

1. **Dépendances système**:
   ```bash
   sudo apt install -y python3-picamera2 python3-pygame python3-numpy fbi
   ```

2. **Installation du service**:
   ```bash
   sudo cp pimage.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable pimage.service
   sudo systemctl start pimage.service
   ```

## Structure du Code

- `app_photo.py`: Cœur applicatif avec gestion asynchrone des GPIO et UI Pygame.
- `pimage.service`: Définition du service systemd.
- `~/photos`: Répertoire de stockage des captures.

## Notes de développement

- Le driver vidéo `kmsdrm` est recommandé pour les performances optimales sur RPi (configuré dans le service).
- L'encodeur utilise un debounce logiciel de 300ms pour le switch afin d'éviter les doubles captures.
