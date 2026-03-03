# À faire (priorité de correction)

## Fait dans ce patch
- Structure package `pimage/` + point d’entrée `python -m pimage`.
- Validation stricte de config (bornes/types) + migration legacy.
- Logging structuré avec rotation de fichiers (`logs/pimage.log`).
- Storage guard de base (lecture seule / espace faible avant capture).
- Base qualité: tests `pytest` + CI GitHub Actions (lint/typecheck/tests).

## Reste à faire (non couvert ici)
1. **Refactor complet de l’app monolithique**
   - déplacer `CameraApp` en modules `camera/`, `ui/`, `effects/`, `storage/`.
2. **Mode No Camera / Demo**
   - mock frame provider + smoke test démarrage sans Picamera2.
3. **Pipeline preview/export cohérent**
   - appliquer les mêmes effets au rendu final ou afficher un disclaimer UI explicite.
4. **Gestion quota disque dans l’app runtime**
   - purge FIFO automatique configurable + UI d’alerte.
5. **Contrats d’erreurs UI**
   - remonter des erreurs métier propres à l’écran (pas seulement `notify`).
6. **Observabilité terrain**
   - debug overlay FPS/latence/temp/mémoire + crash report structuré.
7. **Fonctionnel UX**
   - galerie, favoris, suppression confirmée, timer/rafale/bracketing, AE/AWB lock.
8. **Nom du projet**
   - traiter la collision potentielle avec le package PyPI `pimage`.
