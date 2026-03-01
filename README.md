# pimage

Mini application photo orientée Raspberry Pi 4 / CM4 + écran tactile DSI.

## Vision du projet

`pimage` transforme un Raspberry Pi en **appareil photo créatif autonome**:
- interface plein écran tactile,
- workflow orienté terrain (capture rapide + profils),
- réglages photo manuels et styles visuels temps réel.

Le but est d'avoir une base solide pour un boîtier custom (CM4 + capteur CSI + écran 800x480).

## Fonctionnalités actuelles

### 1) Capture + interface
- Preview live plein écran via **Picamera2**.
- UI tactile Pygame avec gros boutons adaptés à un écran DSI.
- Capture photo JPG dans `~/photos`.
- Galerie photo intégrée (navigation, suppression, slideshow).

### 2) Menus de configuration
L'interface est organisée en **menus**:
- `Capture`
- `Tune`
- `Color`
- `Effect`
- `System`
- `Gallery` (mode dédié de lecture photos)

Cela permet d'utiliser la caméra comme un appareil avec modes dédiés plutôt qu'une simple liste de boutons.

### 3) Contrôle caméra
Réglages disponibles:
- Exposure Value
- Analogue Gain
- Brightness
- Contrast
- Saturation
- Sharpness
- ExposureTime (manuel si AE OFF)
- AE ON/OFF
- AWB presets (auto/tungsten/fluo/indoor/daylight/cloudy)

### 4) Profils couleur
Profils intégrés:
- `natural`
- `vivid`
- `cinema`
- `mono`
- `retro`

Chaque profil applique une signature colorimétrique cohérente.

### 5) Effets créatifs live
Effets de preview:
- `none`
- `noir`
- `vintage`
- `cyber`
- `thermal`

> Note: les effets sont appliqués sur le flux de preview, pas comme pipeline ISP officiel.

### 6) Grilles d'aide au cadrage
Sélecteur de grilles directement dans les menus `Capture`, `Effect` et `System`:
- `off`
- `thirds` (règle des tiers)
- `quarters` (4 lignes d'aide principales)
- `crosshair`
- `diagonal-x`
- `triangles`
- `golden-phi`
- `dense-6x6`

### 7) Profils utilisateur persistants
- Sauvegarde/chargement de slots `A/B/C`
- Fichier: `~/.pimage_profiles.json`

Pratique pour basculer entre configurations de prises de vues (jour, nuit, portrait, style artistique, etc.).

### 8) Analyse matérielle runtime
Au lancement, l'app récupère un résumé matériel depuis Picamera2:
- modèle capteur (si exposé)
- nombre de contrôles caméra disponibles
- présence encodeur (`ENC=yes/no`)

Ce résumé est affiché en overlay pour aider le tuning matériel.

### 9) Encodeur GPIO (optionnel)
Support d'un encodeur rotatif sur GPIO BCM:
- `CLK=17`
- `DT=18`
- `SW=27`

Utilisation:
- rotation: déplacement focus boutons / photo précédente-suivante en galerie
- pression: validation action active

Si `RPi.GPIO` n'est pas disponible, l'app continue sans encodeur.

---

## Installation (Raspberry Pi OS Bookworm)

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-pygame python3-numpy
```

## Lancer l'app

```bash
python3 app_photo.py
```

## Contrôles clavier (debug)

- `Space`/`Enter`: capture
- `↑`/`↓`: paramètre +/-
- `←`/`→`: menu précédent/suivant (ou prev/next photo en galerie)
- `Backspace`: ouvrir/fermer galerie
- `Delete`: supprimer photo courante (galerie)
- `a`: auto exposure ON/OFF
- `w`: AWB suivant
- `p`: profil couleur suivant
- `e`: effet suivant
- `g`: grille suivante (ou retour caméra depuis galerie)
- `Esc`: quitter

---

## Étude rapide des possibilités hardware (RPi4/CM4)

### Ce que le matériel permet bien
- Appareil photo embarqué compact basse conso.
- Démarrage rapide, usage kiosque, écran tactile direct.
- Contrôle ISP via Picamera2 (expo, gains, couleurs, netteté).
- Pipeline extensible Python (post-traitements, UI custom, logique métier).

### Axes d'évolution réalistes
1. **Gestion stockage robuste**
   - auto-rotation, nettoyage quota, export USB/Wi‑Fi.
2. **Workflow photo avancé**
   - rafale, retardateur, bracketing expo, histogramme live.
3. **Color science**
   - profils caméra par capteur/lentille, LUT 3D, matching look-cinéma.
4. **Expérience appareil complet**
   - battery HUD (I2C), boutons GPIO physiques, mode galerie.
5. **Qualité image**
   - calibration optique, gestion bruit ISO, anti-flicker, verrouillage expo/AWB précis.

### Limites typiques à anticiper
- Performances CPU/GPU si effets lourds en Python pur.
- Capteurs CSI très variables (latence, rolling shutter, dynamique).
- Contraintes thermiques en boîtier fermé.

---

## Notes hardware

- Pensé pour écran 800x480 en paysage.
- Panneau de contrôle à droite, preview caméra à gauche.
- Sauvegarde locale recommandée sur stockage fiable (overlay fs désactivé recommandé).

## Idées “fou-fou” pour la suite

- Mode **"Dream Scanner"**: effet génératif piloté par capteur IMU/GPIO.
- Profils automatiques selon heure/lumière (day/night adaptation).
- Capture + style + impression instantanée (ESC/POS).
- Passage en mode “studio” avec contrôle remote via WebSocket.
