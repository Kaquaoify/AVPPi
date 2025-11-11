# AVPPi

AVPPi est une solution open-source qui transforme un poste **Ubuntu Desktop 25.04** en lecteur d’affichage dynamique autonome. Le système démarre une session Openbox épurée, désactive toute mise en veille et diffuse en boucle les vidéos stockées sous `/opt/avppi/AVPPi-medias` grâce à libVLC. Une interface web, accessible sur le réseau local, offre les commandes essentielles (lecture/pause, précédent/suivant, volume, insertion dans la playlist) ainsi que l’accès aux réglages rclone et aux paramètres de planification horaire.

## Points clés

- **Lecture continue** : VLC tourne sans décoration, plein écran, avec une playlist reconstruite à partir des fichiers présents sur le disque.
- **Interface web FR/EN** : tableau de bord du lecteur, liste des médias, page de configuration rclone protégée par mot de passe, section paramètres (langue, rescan, redémarrage, scheduler).
- **Planification** : option pour définir jours et plages horaires durant lesquelles la lecture se lance automatiquement.
- **Synchronisation quotidienne** : déclenchement automatique d’un `rclone sync` chaque jour à l’heure configurée (06h00 par défaut), avec possibilité de désactiver la fonction.
- **Synchronisation Drive** : la page rclone permet de coller un token, tester la connexion et lancer une sync manuelle vers le dossier local.
- **Lecture résiliente** : VLC tourne en décodage logiciel avec un cache élargi pour minimiser les blocages.
- **Sanitisation optionnelle** : depuis l’onglet Rclone, un bouton permet de re-encoder automatiquement les vidéos douteuses (ffmpeg) pour garantir une lecture fluide.
- **Scripts d’installation/mise à jour** : `scripts/install.sh` et `scripts/update.sh` installent les paquets requis, compilent Python 3.12.5, créent la venv, génèrent `/etc/avppi/config.yaml`, configurent Openbox (autologin GDM, fond noir, unclutter, lancement uvicorn) et assurent les bons droits sur `/opt/avppi` et `/var/log/avppi`.
- **Journaux dédiés** : `app.log`, `playback.log`, `rclone.log` sont créés sous `/var/log/avppi`, plus un `kiosk.log` pour la session Openbox.

## Installation rapide

```bash
sudo bash -c "curl -fsSL https://raw.githubusercontent.com/Kaquaoify/AVPPi/main/scripts/install.sh \
  -o /tmp/avppi_install.sh && bash /tmp/avppi_install.sh"
```

Une fois l’installation terminée, déposer les vidéos dans `/opt/avppi/AVPPi-medias` ou lancer la synchronisation rclone via l’interface `http://<machine>:8000/`.

> **Installation Raspberry Pi 5** : voir le guide dédié qui couvre la préparation d’Ubuntu Desktop, la configuration SSH et l’autorisation rclone côté Windows.  
> [Consulter le tutoriel RPi 5](docs/RPI5_SETUP.md)

## Développement

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Structure succincte

- `app/` : API FastAPI, contrôleur VLC, scheduler, gestion rclone, frontend (HTML/CSS/JS).
- `config/app_config.yaml` : configuration par défaut copiée vers `/etc/avppi/config.yaml`.
- `locales/` : fichiers de traduction.
- `scripts/` : installation et mise à jour automatisées.
- `docs/architecture.md` : description de l’architecture logicielle.
