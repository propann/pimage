# Configuration Raspberry Pi 4 (Précise)

Ce guide décrit la configuration minimale et vérifiable pour exécuter `pimage` de façon fiable sur Raspberry Pi 4.

## 1. Base système recommandée
1. Installer **Raspberry Pi OS Bookworm 64-bit** (à jour).
2. Mettre à jour:
```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

## 2. Interfaces à activer
Lancer:
```bash
sudo raspi-config
```
Activer:
- `Interface Options > Camera`
- `Interface Options > I2C` (si batterie/UPS I2C)
- `Boot / Auto Login` selon votre usage terrain

Puis vérifier:
```bash
libcamera-hello --list-cameras
ls /dev/i2c-1
```

## 3. Dépendances projet
```bash
sudo apt install -y \
  python3-picamera2 python3-pygame python3-numpy \
  python3-flask python3-opencv python3-smbus2 rsync
```

## 4. Clonage + lancement manuel
```bash
git clone https://github.com/propann/pimage.git
cd pimage
git checkout freelance-cm4-adaptation
python3 app_photo.py
```

Mode tactile-only (sans encodeur):
```bash
PIMAGE_ENCODER=0 python3 app_photo.py
```

## 5. Démarrage auto (systemd)
```bash
sudo cp pimage.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pimage.service
```
Vérifier:
```bash
systemctl status pimage.service --no-pager
journalctl -u pimage.service -n 100 --no-pager
```

## 6. Pré-check matériel
- Caméra détectée: `libcamera-hello --list-cameras`
- Dossier photo: `ls -ld ~/photos`
- Espace disque: `df -h ~`
- Temp CPU: `cat /sys/class/thermal/thermal_zone0/temp`
- I2C (optionnel): `sudo i2cdetect -y 1`

## 7. Validation fonctionnelle (checklist)
- L’app démarre sans traceback.
- Capture JPG fonctionne (fichier dans `~/photos`).
- Vidéo démarre/stoppe sans crash.
- Galerie ouvre/supprime une image.
- Toggle `SYNC`, `RAW`, `PEAK`, `ENC` affiche un feedback visuel.
- Redémarrage app: préférences conservées (`~/.pimage_profiles.json`).

## 8. Dépannage rapide
- Écran noir: vérifier service, droits utilisateur `azoth`, et logs `journalctl`.
- Erreur caméra: fermer tout autre process utilisant `/dev/media*`.
- Pas de batterie affichée: vérifier câblage I2C/adresse UPS.
- Encodeur absent: utiliser tactile-only et `ENC OFF`.
- `Camera frontend has timed out`:
  - Couper l'alimentation, rebrancher la nappe caméra (sens + verrouillage).
  - Tester avec une autre nappe CSI courte.
  - Vérifier une alim stable (5V/3A mini conseillé).
  - Vérifier qu'aucun autre service ne lit la caméra (`libcamera-hello`, motion, etc.).
