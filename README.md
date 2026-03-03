# pimage

Mini application photo orientée Raspberry Pi 4 / CM4 + écran tactile DSI.

## Vision du projet

`pimage` transforme un Raspberry Pi en **appareil photo créatif autonome**:
- interface plein écran tactile,
- workflow orienté terrain (capture rapide + profils),
- réglages photo manuels et styles visuels temps réel.

Le but est d'avoir une base solide pour un boîtier custom (CM4 + capteur CSI + écran 800x480).

## Fonctionnalités actuelles (vérifiées dans le code)

### 1) Capture + interface
- Preview live via **Picamera2** + rendu Pygame.
- UI tactile orientée écran 800x480.
- Capture photo JPG dans le dossier défini par `config.yaml` (`paths.photos`).

### 2) Menus de configuration
L'interface est organisée en **menus**:
- `Capture`
- `Tune`
- `Color`
- `Effect`
- `System`

Cela permet d'utiliser la caméra comme un appareil avec modes dédiés plutôt qu'une simple liste de boutons.

### 3) Contrôle caméra
Réglages disponibles:
- Exposure Value
- Brightness
- Contrast
- Saturation

> Note: la version actuelle applique ces contrôles via `set_controls`.

### 4) Effets créatifs live
Effets de preview:
- `none`
- `noir`
- `vintage`

> Note: les effets sont appliqués sur le flux de preview, pas comme pipeline ISP officiel.

### 5) Grilles d'aide au cadrage
Sélecteur de grilles en overlay:
- `thirds`
- `golden`
- `diagonals`
- `dense-6x6`
- `crop-guides`

### 6) HUD et popup de réglage
- Panneau gauche (navigation) + cartes HUD à droite.
- Popup slider pour ajuster ouverture/vitesse/ISO/EV/Kelvin/ventilation (valeurs UI).

### 7) Édition post-capture
- Vue `Edit` avec:
  - crop draggable,
  - ratios `1:1`, `4:3`, `16:9`,
  - rotate, flip, undo,
  - sliders brightness/contrast/saturation/hue,
  - export JPG.

### 8) Configuration persistante
- `config.yaml` est lu/écrit automatiquement.
- Migration legacy `config.json` supportée au chargement.

---

## Installation (Raspberry Pi OS Bookworm)

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-pygame python3-numpy
pip install pygame-vkeyboard
```

## Lancer l'app

```bash
python3 app_photo.py
```

## Contrôles clavier (debug)

- `Space`/`Enter`: capture
- `↑`/`↓`: paramètre +/-
- `←`/`→`: menu précédent/suivant
- `a`: auto exposure ON/OFF
- `w`: AWB suivant
- `p`: profil couleur suivant
- `e`: effet suivant
- `g`: grille suivante
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


## Nouveautés UI/UX

- Menus animés en slide-in/fade (0.4s, easing `easeOutQuad`) avec blur léger du preview derrière le panneau.
- Popup modale de renommage avec overlay semi-transparent + clavier tactile (`pygame-vkeyboard` si disponible, fallback clavier physique).
- Nouvelle vue **Edit** post-capture: crop draggable (ratios 1:1 / 4:3 / 16:9), réglages brightness/contrast/saturation/hue, rotate/flip, undo (stack max 5), export JPG.
- `config.yaml` centralise chemins, résolution et paramètres caméra; menu **System** inclut le toggle *Capteur 2* et la sauvegarde de config.

## HUD v2 « Pro Overlay Mode »

- Interface recentrée sur le preview plein écran avec overlays.
- Nouveau module `overlays.py` pour les grilles (tiers, golden+spirale, diagonales, 6x6, crop guides) et histogramme live RGB (~500ms).
- Nouveau module `ui_hud.py` pour cartes encadrées cliquables + popup slider et panneaux latéraux animés (easeOut).
- Configuration migrée vers `config.yaml` (`overlay.default_grid`, `cooling.fan_pwm`, courbe ventilateur, toggle capteur2).

---

## Vérification rapide du dépôt

Contrôles exécutés pour cette mise à jour:

```bash
python3 -m py_compile app_photo.py overlays.py ui_hud.py
```

Résultat: compilation Python OK (aucune erreur syntaxique).
