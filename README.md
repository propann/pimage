# pimage

Application photo Python pensée pour Raspberry Pi (Picamera2 + Pygame), avec interface tactile et petit module CLI.

## Objectif du dépôt

Le projet fournit deux choses complémentaires :

- une application caméra interactive (`app_photo.py`) pour capturer et retoucher rapidement des images ;
- un package Python (`pimage/`) pour la configuration, le logging, le stockage et quelques effets.

## État actuel (aligné sur le code)

### 1) Lancement

- Entrypoint package : `python3 -m pimage` (redirige vers `pimage.cli:main`).
- Le CLI initialise les logs, charge/valide la configuration, puis lance l'UI caméra.
- Option utile : `--check-config` valide la configuration et quitte sans lancer l'interface.

### 2) Configuration

La config est gérée par `pimage/config.py` :

- fichier principal : `config.yaml` ;
- migration legacy : lit `config.json` si `config.yaml` n'existe pas ;
- validation des bornes (résolution, largeur de panneau, index caméra, PWM ventilateur, etc.) ;
- réécriture automatique du fichier avec une structure normalisée.

Champs principaux écrits dans la config :

- `paths.photos`
- `screen.width`, `screen.height`, `screen.panel_width`
- `camera.index`, `camera.sensor2_enabled`
- `overlay.default_grid`, `overlay.histogram_interval_ms`
- `cooling.fan_pwm`, `cooling.curve`

### 3) Interface caméra (`app_photo.py`)

Fonctionnalités implémentées :

- preview live via Picamera2 dans la zone image ;
- menus/couches UI (capture, réglages, couleur, système) ;
- capture JPEG dans `paths.photos` avec nom horodaté (`img_YYYYMMDD_HHMMSS_<profil>.jpg`) ;
- vérification stockage avant capture (lecture seule + espace disque minimum) ;
- effets preview : `none`, `noir`, `vintage` ;
- grilles de cadrage via `overlays.py` ;
- histogramme RGB overlay ;
- popup de renommage post-capture (clavier tactile si `pygame-vkeyboard` est installé) ;
- vue d'édition basique : crop, rotation, flip, undo, sliders luminosité/contraste/saturation/teinte, export JPEG.

### 4) Module stockage (`pimage/storage.py`)

Le module fournit :

- état stockage (`free_bytes`, `total_bytes`, `read_only`) ;
- génération de noms de captures ;
- écriture atomique binaire (`*.tmp` puis replace) ;
- nettoyage quota sur les JPG les plus anciens.

### 5) Effets (`pimage/effects.py`)

Effets NumPy disponibles :

- `noir` (conversion niveaux de gris) ;
- `vintage` (canaux colorimétriques modifiés) ;
- effet inconnu : image conservée (hors clipping/type).

## Installation (Raspberry Pi OS)

Exemple minimal :

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-pygame python3-numpy
pip install pygame-vkeyboard pyyaml
```

## Utilisation

```bash
python3 -m pimage
```

Validation config seule :

```bash
python3 -m pimage --check-config
```

## Tests disponibles

Le dépôt contient des tests unitaires/smoke sur :

- la configuration,
- le stockage,
- les effets,
- le mode `--check-config`.

Lancement :

```bash
pytest
```

## Limites connues

- L'application UI dépend fortement du matériel Raspberry Pi (Picamera2 requis).
- Les réglages HUD (ouverture, vitesse, ISO, Kelvin) servent actuellement surtout d'interface et ne représentent pas tous des contrôles matériels directs appliqués au capteur.
- Les effets sont appliqués côté preview/traitement logiciel, pas via un pipeline ISP avancé.
