# pimage - Freelance CM4 Pro Edition 📸

Logiciel "béton" et complet pour transformer un **Raspberry Pi 4 / CM4** en appareil photo créatif autonome avec écran tactile DSI 7" et contrôles physiques.

## 🌟 Points Forts (Édition Pro)

- **Contrôle Physique Complet** : Support de l'encodeur rotatif (BCM 17, 18) et bouton de capture (BCM 27) via interruptions GPIO.
- **Support Pro Photo** : Capture simultanée JPG + **RAW (DNG)** et mode **Bracketing d'exposition** (3 photos auto à -1, 0, +1 EV).
- **Aides à la Prise de Vue** : **Histogramme Live** (luminance) et **Focus Peaking** (surlignage rouge des zones nettes) en temps réel.
- **Modes Créatifs** : 
    - **Vidéo** : Enregistrement H.264 (.mp4) avec timer et indicateur REC.
    - **Rafale (Burst)** : Séquences rapides de 5, 10 ou 20 images.
    - **Time-lapse** : Intervalle réglable de 1s à 1h avec compteur.
    - **Retardateur** : Délai de 2s, 5s ou 10s avant capture.
- **Connectivité & Workflow** : 
    - **Auto-Sync Wi-Fi** : Synchronisation automatique via `rsync` en arrière-plan.
    - **Interface Web Remote** : Déclencheur à distance via Flask (port 5000) avec actions autorisées filtrées.
- **Interface Intelligente (Shifting UI)** : Le menu tactile bascule à gauche ou à droite pour ne pas masquer le sujet, selon le mode.
- **Monitoring Système** : Affichage en temps réel du **% Batterie (I2C)** et de la **Température CPU**.
- **Galerie Native** : Visionneuse d'images fluide intégrée à Pygame (navigation tactile/encodeur).
- **Robustesse Terrain** : Sauvegarde automatique des préférences utilisateur dans `~/.pimage_profiles.json`.

---

## 🛠️ Installation (Raspberry Pi OS Bookworm)

Configuration Pi4 détaillée (pas à pas, vérifications, dépannage):
- `docs/PI4_SETUP.md`

### 1. Dépendances système
```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-pygame python3-numpy python3-flask python3-opencv python3-smbus2 fbi rsync
```

### 2. Cloner le projet
```bash
git clone https://github.com/votre-username/pimage.git
cd pimage
git checkout freelance-cm4-adaptation
```

### 3. Configurer l'Auto-Sync (Optionnel)
Modifie `sync_photos.sh` avec l'adresse IP de ton serveur de destination :
```bash
nano sync_photos.sh
```

---

## 🚀 Lancer l'Application

```bash
python3 app_photo.py
```

### Mode sans encodeur (tactile uniquement)
- L'application reste 100% utilisable au tactile sans encodeur branché.
- L'encodeur peut être activé/désactivé depuis le menu **SYSTEM** (`ENC ON/OFF`).
- Pour forcer le démarrage sans encodeur :
```bash
PIMAGE_ENCODER=0 python3 app_photo.py
```

### Installation du Service (Autostart)
```bash
sudo cp pimage.service /etc/systemd/system/
sudo systemctl enable --now pimage.service
```

---

## 🎹 Contrôles

| Action | Contrôle Physique | Clavier (Debug) |
| :--- | :--- | :--- |
| **Capturer** | Clic Encodeur (Menu Capture) | `Espace` / `Entrée` |
| **Naviguer Menu** | Clic Encodeur (Autres Menus) | `Flèches Gauche/Droite` |
| **Régler Paramètre**| Rotation Encodeur | `Flèches Haut/Bas` |
| **Quitter Galerie** | Clic Encodeur | `Echap` |

---

## 📁 Structure du Projet
- `app_photo.py` : Cœur de l'application (multithreadé).
- `pimage.service` : Configuration pour le démarrage automatique.
- `sync_photos.sh` : Script de synchronisation Wi-Fi.
- `docs/PI4_SETUP.md` : Configuration précise Raspberry Pi 4 + checklist de validation.
- `PROGRESS.md` : Journal d'avancement détaillé.
- `GEMINI.md` : Contexte technique pour l'IA.
- `AGENTS.md` : Guide contributeur (standards code, tests, commits/PR).

---

## 📝 Notes Hardware
- **Écran** : Optimisé pour 800x480 (DSI 7").
- **Batterie** : Support générique I2C (testé avec PiSugar et Waveshare UPS).
- **Température** : Surveillance recommandée pour le CM4 en boîtier fermé.
