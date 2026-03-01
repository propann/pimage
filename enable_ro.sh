#!/bin/bash
# Script pour basculer le PImage en mode "Indestructible" (Read-Only)

echo "--- PImage System Protection ---"

# 1. Vérifie si raspi-config est là
if ! command -v raspi-config &> /dev/null; then
    echo "Erreur: Ce script doit être lancé sur Raspberry Pi OS."
    exit 1
fi

# 2. Demande confirmation
read -p "Voulez-vous activer la protection SD (Overlay FS) ? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# 3. Activation de l'Overlay FS via raspi-config (non-interactif)
echo "Activation de l'Overlay FS..."
sudo raspi-config nonint enable_overlayfs

# 4. Activation de la protection en écriture du boot
sudo raspi-config nonint enable_bootro

echo "--- IMPORTANT ---"
echo "Le système sera en lecture seule après le redémarrage."
echo "Tes photos dans ~/photos doivent être sur une partition séparée"
echo "ou un support USB pour rester persistantes."
echo "-----------------"
echo "Redémarrage requis : sudo reboot"
