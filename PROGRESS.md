# Journal d'avancement - PImage Pro Adaptation

## 🎯 Objectif : Pack "Qualité Image & Aide Pro" (Catégorie 1)

| Module | Description | État |
| :--- | :--- | :--- |
| **1. Support RAW (DNG)** | Capture simultanée JPG + DNG pour post-traitement. | ✅ Terminé |
| **2. Bracketing d'exposition** | Mode 3 photos (EV -1, 0, +1) en une pression. | ✅ Terminé |
| **3. Histogramme Live** | Graphe de luminance en temps réel sur l'UI. | ✅ Terminé |
| **4. Focus Peaking** | Surlignage des zones nettes en rouge sur la preview. | ✅ Terminé |

---

## ✅ Terminé (Adaptation CM4 Initiale)
- [x] Encodeur Rotatif (Callbacks GPIO)
- [x] Interface "Shifting" (Preview décalée)
- [x] Galerie via `fbi`
- [x] Logging & Service Systemd
- [x] Moteur de Time-lapse complet

## 🎯 Objectif : Pack "Connectivité & Workflow" (Catégorie 2)

| Module | Description | État |
| :--- | :--- | :--- |
| **1. Auto-Upload Wi-Fi** | Synchronisation `rsync` dès qu'un réseau est détecté. | ⏳ En cours |
| **2. Interface Web** | Mini serveur Flask pour contrôle smartphone. | ⏳ En attente |
| **3. Monitoring Batterie** | Affichage du % de batterie (UPS support). | ⏳ En attente |

---

## ✅ Terminé (Adaptation CM4 & Pro Pack)
- [x] Encodeur Rotatif, Shifting UI, Galerie, Service, Time-lapse
- [x] RAW/DNG, Bracketing, Histogramme, Focus Peaking

## 🛠️ À Faire (Prochaines étapes)
1. Finir la logique de détection réseau & rsync.
2. Ajouter le mode vidéo (Catégorie 3).
