#!/bin/bash
# Script de synchronisation automatique pour PImage
# À personnaliser selon ton environnement

# Dossier local des photos
LOCAL_DIR="$HOME/photos"

# DESTINATION DISTANTE (Exemple : user@mon-ordinateur:/chemin/photos)
# REMPLACE PAR TON SERVEUR/PC
REMOTE_TARGET="azoth@localhost:/tmp/pimage_sync"

# Vérifie si le réseau est disponible (ping rapide)
if ping -c 1 -W 1 8.8.8.8 > /dev/null 2>&1; then
    # Synchronise les fichiers JPG et DNG
    # --ignore-existing : ne renvoie pas ce qui est déjà là
    # -u : uniquement si le fichier est plus récent
    rsync -au "$LOCAL_DIR/" "$REMOTE_TARGET" 2>/dev/null
    exit 0
else
    exit 1
fi
