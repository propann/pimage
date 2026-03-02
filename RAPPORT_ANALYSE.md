# Rapport d’analyse du code `pimage`

## Périmètre analysé
- `app_photo.py`
- `README.md`

## Synthèse rapide
Le projet pose une bonne base de caméra tactile Raspberry Pi (capture, réglages, profils, effets, grilles), mais l’implémentation actuelle n’est pas exécutable en l’état car une partie du mode galerie/encodeur est référencée sans être implémentée.

## Points bloquants (à corriger en priorité)

1. **Références à des méthodes inexistantes dans `CameraApp`**
   - `enter_gallery`
   - `gallery_button_rects`
   - `handle_gallery_action`
   - `handle_encoder_input`

   Ces appels existent dans `handle_action`, `click` et `run`, mais les méthodes ne sont pas définies.

2. **Constantes GPIO manquantes**
   - `ENC_CLK`
   - `ENC_DT`
   - `ENC_SW`

   Elles sont utilisées dans `setup_encoder` mais non déclarées.

3. **Attributs potentiellement non initialisés**
   - `gallery_mode`
   - `slideshow`
   - `gallery_files`
   - `next_slide_at`
   - `slide_every_s`
   - `encoder_enabled`
   - `focus_idx`

   Ils sont lus dans la boucle principale et dans la gestion du clic, mais leur initialisation n’apparaît pas.

## Écarts fonctionnels vs vision produit (README)

### Fonctionnalités présentes
- Capture JPG locale et preview live.
- Menus `Capture/Tune/Color/Effect/System`.
- Réglages caméra (AE, AWB, gain, expo, etc.).
- Profils couleur, effets de preview, grilles de cadrage.
- Sauvegarde/chargement de profils utilisateurs.

### Fonctionnalités annoncées ou implicites incomplètes
- **Mode galerie** : action présente (`gallery`) mais flux non implémenté.
- **Support encodeur GPIO** : méthode de setup présente mais intégration incomplète/inopérante.
- **Robustesse profils** : pas de gestion d’erreurs JSON/corruption fichier.
- **Portabilité dev** : dépendances RPi strictes, pas de mode simulation/no-camera.

## Dette technique / qualité

1. **Absence de tests**
   - Aucun test unitaire (effets, profils, logique menu).
   - Aucun test d’intégration minimal avec mock caméra.

2. **Faible tolérance aux erreurs I/O**
   - `json.loads(PROFILE_FILE.read_text())` sans `try/except` sur JSON invalide.
   - `capture_file` sans gestion explicite des erreurs de stockage.

3. **Couplage fort UI / logique / hardware**
   - La logique métier (profils/effets/menus) est imbriquée dans la classe UI.
   - Rend les tests et évolutions plus coûteux.

4. **Configuration figée**
   - Résolution, panel, fps cible, dossiers et mappings clavier/GPIO en constantes statiques.
   - Pas de fichier de configuration utilisateur.

## Plan d’action recommandé

### Phase 1 — Remise en état exécutable (critique)
1. Déclarer les constantes GPIO manquantes (ou désactiver proprement le bloc encodeur si absent).
2. Initialiser tous les attributs utilisés (`gallery_mode`, `encoder_enabled`, etc.) dans `__init__`.
3. Soit:
   - implémenter les 4 méthodes manquantes (galerie + encodeur),
   - soit retirer temporairement les appels pour livrer un cœur stable.
4. Ajouter un check CI lint minimal (au moins `ruff check`).

### Phase 2 — Robustesse et UX
1. Fiabiliser la sérialisation profils (`try/except`, backup, reset safe).
2. Ajouter messages d’erreur utilisateur (stockage plein, caméra indisponible, profil corrompu).
3. Ajouter mode fenêtré debug (non fullscreen) pour développement desktop.

### Phase 3 — Qualité logicielle
1. Extraire la logique profils/effets/menus dans modules séparés.
2. Introduire tests unitaires sur:
   - `apply_effect`
   - `apply_color_profile`
   - transitions de menus/actions.
3. Ajouter un pipeline CI: lint + tests.

## Priorités finales
- **P0 (immédiat)**: corriger méthodes/constantes/attributs manquants pour supprimer les erreurs d’exécution.
- **P1 (court terme)**: robustesse JSON + gestion d’erreurs capture.
- **P2 (moyen terme)**: modularisation + tests + CI.
