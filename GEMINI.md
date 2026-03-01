# pimage - Freelance CM4 Adaptation

Logiciel "béton" pour prototype d'appareil photo CM4 avec écran DSI et contrôles physiques.

## Nouvelles Fonctionnalités (Adaptation CM4)

- **Encodeur Rotatif (BCM 17, 18, 27)**: Navigation dans les réglages et capture physique via callbacks GPIO interrompus.
- **Time-lapse complet**: Nouveau menu dédié pour configurer l'intervalle (1s à 1h). Indicateur visuel "REC" clignotant avec compteur de photos.
- **Support Pro (RAW & Bracketing)**: Capture simultanée JPG + DNG (RAW) et mode Bracketing d'exposition (3 photos auto).
- **Aides à la prise de vue**: Histogramme Live et Focus Peaking (surlignage des zones nettes en rouge) en temps réel.
- **Connectivité & Workflow**: Auto-sync Wi-Fi (rsync), Monitoring batterie I2C et Interface Web (Remote Control via Flask sur le port 5000).
- **Interface "Shifting"**: Le menu bascule à gauche ou à droite de l'écran (Preview décalée) pour optimiser l'ergonomie (Modes SYSTEM et TIMELAPSE décalés).
- **Galerie Intégrée**: Lancement d'un diaporama via `fbi` directement depuis l'interface.
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
