# Architecture AVPPi

Ce document fournit un aperçu simple de l’organisation interne du projet.

## Composants applicatifs

- **FastAPI** (`app/api.py`, `app/main.py`)  
  Fournit les routes REST consommées par le frontend : statut du lecteur, liste des médias, commandes VLC, gestion rclone, planification horaire, paramètres généraux.

- **ApplicationCore** (`app/core.py`)  
  Orchestration centrale : instancie le contrôleur VLC, le gestionnaire rclone, le scanner de médias, le gestionnaire d’état et les services auxiliaires. Au démarrage, charge la playlist, applique le volume mémorisé et lance la lecture.

- **Contrôleur VLC** (`app/vlc_controller.py`)  
  Encapsule libVLC : playlist en boucle, play/pause/précédent/suivant, volume, insertion à chaud, conversion d’URL en noms lisibles.

- **Scheduler** (`app/scheduler.py`)  
  Thread dédié qui vérifie toutes les 30 s si l’heure et le jour courants se trouvent dans la plage active définie via l’interface. Déclenche `play()` ou `pause()` en conséquence.

- **SyncScheduler** (`app/sync_scheduler.py`)  
  Vérifie les paramètres de synchronisation quotidienne et déclenche un `rclone sync` automatique une fois par jour à l’heure configurée.

- **PlaybackWatchdog** (`app/watchdog.py`)  
  Surveille l’avancement de VLC ; si la vidéo reste figée trop longtemps alors qu’elle devrait jouer, il relance le lecteur pour éviter les blocages.

- **MediaSanitizer** (`app/sanitizer.py`)  
  Analyse les vidéos via ffprobe et, sur demande, les ré-encode avec ffmpeg vers un profil H.264/AAC sûr avant de reconstruire la playlist.

- **Gestion rclone** (`app/rclone_manager.py`)  
  Exécute les commandes rclone (config, test, sync), journalise les sorties et expose les logs récents à l’API.

- **État persistant** (`app/state_manager.py`)  
  Stocke `data/state.json` et les paramètres dynamiques : langue, volume, options rclone, configuration des schedulers.

- **Frontend** (`app/web/templates`, `app/web/static`)  
  Page unique en HTML/CSS/JS. Le script `app/web/static/js/app.js` charge les locales FR/EN, gère les vues Player/Settings/Rclone, rafraîchit le statut, pilote la playlist et envoie les mises à jour de planification.

## Pilote kiosque

- L’installation configure un autologin GDM sur une session Openbox minimale (`/usr/share/xsessions/avppi-openbox.desktop`).
- L’autostart (`~/.config/openbox/autostart`) applique un fond noir, désactive DPMS/veille, masque la souris (`unclutter`) et lance uvicorn dans `/opt/avppi`.
- VLC est lancé par libVLC, sans fenêtre, centré sur l’écran HDMI.

## Scripts

- `scripts/install.sh` : installation complète (packages système, compilation Python 3.12.5, venv, déploiement du code, configuration Openbox, création de `/etc/avppi/config.yaml`, permissions).
- `scripts/update.sh` : mise à jour en place (pull git, venv recréée, configuration réappliquée).

## Journaux

- `/var/log/avppi/app.log` : événements applicatifs.
- `/var/log/avppi/playback.log` : interactions VLC et messages du scheduler.
- `/var/log/avppi/rclone.log` : logs rclone.
- `/var/log/avppi/kiosk.log` : sortie de l’Openbox autostart (traces uvicorn/VLC).

## Flux de démarrage

1. Boot → GDM ouvre la session `avppi`.  
2. Openbox autostart configure l’écran et lance uvicorn.  
3. FastAPI charge la configuration, initialise ApplicationCore, scanne les médias, démarre VLC et le scheduler.  
4. Le frontend, servi par FastAPI, contrôle l’ensemble depuis un navigateur local.
