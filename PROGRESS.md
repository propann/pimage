# Journal d'avancement - PImage Pro Adaptation

## 🎯 Objectif : Pack "Connectivité & Workflow" (Catégorie 2)

| Module | Description | État |
| :--- | :--- | :--- |
| **1. Auto-Upload Wi-Fi** | Synchronisation `rsync` automatique en arrière-plan. | ✅ Terminé |
| **2. Monitoring Batterie** | Affichage du % de batterie (UPS support via I2C). | ⏳ En cours |
| **3. Interface Web** | Mini serveur Flask pour contrôle smartphone. | ⏳ En attente |

---

## ✅ Terminé (Adaptation CM4 & Pro Pack)
- [x] Encodeur Rotatif, Shifting UI, Galerie, Service, Time-lapse
- [x] RAW/DNG, Bracketing, Histogramme, Focus Peaking
- [x] Auto-sync Wi-Fi (Worker asynchrone + script rsync)

## 🛠️ À Faire (Prochaines étapes)
1. Intégrer la lecture batterie via I2C (ex: PiSugar/Waveshare).
2. Créer l'interface Web (API Flask + Stream).
