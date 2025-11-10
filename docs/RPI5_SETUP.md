# Installation d’AVPPi sur Raspberry Pi 5

Ce guide décrit l’intégralité de la préparation d’un Raspberry Pi 5 pour exécuter AVPPi : installation d’Ubuntu Desktop, configuration SSH, déploiement du projet et autorisation rclone depuis un PC Windows.

## Matériel requis

- Raspberry Pi 5 (4 Go ou 8 Go recommandés)
- Carte microSD ou SSD compatible
- Clavier, souris et moniteur pour le Pi
- Un PC Windows (pour l’outil Raspberry Pi Imager et rclone)
- Connexion réseau filaire ou Wi‑Fi

## 1. Préparer Ubuntu Desktop 25.04/25.10

1. Télécharger **Raspberry Pi Imager** : <https://www.raspberrypi.com/software/>
2. Lancer l’imager (sur Windows), choisir :
   - *Operating System* → **Other general-purpose OS** → **Ubuntu Desktop 25.04/25.10 (64-bit)**.
   - *Storage* → la carte microSD/SSD.
3. Écrire l’image, insérer le support dans le Pi, démarrer et terminer l’assistant Ubuntu (langue, fuseau, utilisateur).

## 2. Mettre à jour le Pi et installer les dépendances

Sur le Pi (clavier/écran) ou via SSH :

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl openssh-server git
```

Vérifier que SSH est actif :

```bash
systemctl status ssh
```

Lister l’adresse IP :

```bash
hostname -I
```

## 3. Se connecter en SSH depuis Windows

1. Depuis le PC Windows, ouvrir **PowerShell**.
2. Se connecter au Pi :

```powershell
ssh utilisateur@adresse_du_pi
```

(accepter la clé et saisir le mot de passe configuré plus tôt).

## 4. Installer AVPPi

Toujours en SSH (ou directement sur le Pi) :

```bash
sudo bash -c "curl -fsSL https://raw.githubusercontent.com/Kaquaoify/AVPPi/main/scripts/install.sh \
  -o /tmp/avppi_install.sh && bash /tmp/avppi_install.sh"
```

## 5. Télécharger rclone sur Windows

1. Aller sur <https://rclone.org/downloads/>.
2. Télécharger la version **Windows (64-bit)** et extraire l’archive (ex. `rclone-v1.xx.x-windows-amd64`).
3. Ouvrir **PowerShell** dans ce dossier (clic droit → *Ouvrir dans Terminal* ou `Shift + clic droit` → *PowerShell ici*).

## 6. Autoriser rclone (Drive)

Toujours dans PowerShell (dossier rclone) :

```powershell
.\rclone authorize drive
```

1. Suivre le lien généré (copier/coller dans un navigateur), s’authentifier sur Google, autoriser rclone et copier le token complet.
2. Coller ce token dans l’interface web AVPPi (page Rclone).

## 7. Vérifications finales

1. Rejoindre `http://<IP_du_Pi> OU <HOSTNAME>.local:8000/` depuis le réseau local.
2. Vérifier la lecture (la première synchro automatique se lance au boot, un log apparaît dans `/opt/avppi/logs/app.log`).

---
