#!/usr/bin/env bash

set -euo pipefail

REPO_URL="https://github.com/Kaquaoify/AVPPi.git"
INSTALL_DIR="/opt/avppi"
SERVICE_NAME="avppi"
SERVICE_USER="avppi"
PYTHON_VERSION="3.12.5"
PY_PREFIX="/opt/avppi/python-${PYTHON_VERSION}"
PYTHON_BIN="${PY_PREFIX}/bin/python3.12"
CONFIG_DIR="/etc/avppi"
MEDIA_DIR="${MEDIA_DIR:-${INSTALL_DIR}/AVPPi-medias}"
LOG_DIR="${INSTALL_DIR}/logs"
CONFIG_TEMPLATE="${INSTALL_DIR}/config/app_config.yaml"

if [[ "${EUID}" -ne 0 ]]; then
  echo "This installer must be executed with sudo or as root."
  exit 1
fi

echo "[1/9] Installing system dependencies"
apt-get update
apt-get install -y \
  python3 python3-venv python3-pip \
  git vlc rclone \
  xserver-xorg-video-dummy xinit \
  openbox x11-xserver-utils unclutter \
  unzip curl ffmpeg

if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  echo "[2/9] Creating system user ${SERVICE_USER}"
  useradd --system --create-home --shell /bin/bash "${SERVICE_USER}"
fi
usermod -a -G video,audio,render "${SERVICE_USER}" || true

echo "[3/9] Cloning or updating repository"
if [[ -d "${INSTALL_DIR}/.git" ]]; then
  git -C "${INSTALL_DIR}" fetch --all --prune
  git -C "${INSTALL_DIR}" reset --hard origin/main
else
  rm -rf "${INSTALL_DIR}"
  git clone "${REPO_URL}" "${INSTALL_DIR}"
fi

chmod +x "${INSTALL_DIR}/scripts/"*.sh || true
install -d -m 750 "${MEDIA_DIR}" "${INSTALL_DIR}/data"
install -d -m 755 "${LOG_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}" "${MEDIA_DIR}" "${LOG_DIR}"
sudo -u "${SERVICE_USER}" git config --global --add safe.directory "${INSTALL_DIR}" || true
git config --global --add safe.directory "${INSTALL_DIR}" || true

ensure_python() {
  if [[ -x "${PYTHON_BIN}" ]]; then
    echo "[4/9] Reusing existing Python ${PYTHON_VERSION}"
    return
  fi
  echo "[4/9] Building Python ${PYTHON_VERSION} from source (this may take a while)"
  apt-get install -y \
    build-essential \
    libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
    libncurses5-dev libncursesw5-dev libffi-dev liblzma-dev \
    libgdbm-dev libgdbm-compat-dev libnss3-dev uuid-dev tk-dev wget

  TMP_DIR=$(mktemp -d)
  cleanup() { rm -rf "${TMP_DIR}"; }
  trap cleanup EXIT
  pushd "${TMP_DIR}" >/dev/null
  PY_TARBALL="Python-${PYTHON_VERSION}.tgz"
  curl -fsSLO "https://www.python.org/ftp/python/${PYTHON_VERSION}/${PY_TARBALL}"
  tar -xf "${PY_TARBALL}"
  cd "Python-${PYTHON_VERSION}"
  ./configure --enable-optimizations --with-ensurepip=install --prefix "${PY_PREFIX}"
  make -j"$(nproc)"
  make altinstall
  ln -sf "${PY_PREFIX}/bin/python3.12" "${PY_PREFIX}/bin/python3"
  popd >/dev/null
  trap - EXIT
  cleanup
}

ensure_python

echo "[5/9] Creating Python virtual environment"
rm -rf "${INSTALL_DIR}/.venv"
"${PYTHON_BIN}" -m venv "${INSTALL_DIR}/.venv"

export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip wheel
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo "[6/9] Preparing directories"
mkdir -p "${MEDIA_DIR}" "${LOG_DIR}" "${CONFIG_DIR}" "${INSTALL_DIR}/data"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}" "${MEDIA_DIR}" "${LOG_DIR}"
chmod 750 "${MEDIA_DIR}"

CONFIG_FILE="${CONFIG_DIR}/config.yaml"
"${INSTALL_DIR}/.venv/bin/python" - <<'PY' "${CONFIG_TEMPLATE}" "${CONFIG_FILE}" "${MEDIA_DIR}" "${LOG_DIR}" "${SERVICE_USER}"
import sys
from pathlib import Path

import yaml

template_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
media_dir = sys.argv[3]
log_dir = sys.argv[4]
service_user = sys.argv[5]
template = yaml.safe_load(template_path.read_text()) or {}
config = template.copy()
config["media_directory"] = media_dir
config["log_directory"] = log_dir
config["rclone_binary"] = config.get("rclone_binary", "/usr/bin/rclone")
config["rclone_config_path"] = f"/home/{service_user}/.config/rclone/rclone.conf"
output_path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
PY
chown "${SERVICE_USER}:${SERVICE_USER}" "${CONFIG_FILE}"

mkdir -p "${LOG_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${LOG_DIR}"

echo "[7/8] Skipping systemd service (managed via Openbox autostart)"

echo "[8b/8] Disabling desktop power management"
mkdir -p /etc/dconf/db/local.d
cat >/etc/dconf/db/local.d/00-avppi <<'EOF'
[org/gnome/desktop/session]
idle-delay=uint32 0

[org/gnome/settings-daemon/plugins/power]
sleep-inactive-ac-type='nothing'
sleep-inactive-battery-type='nothing'
sleep-inactive-ac-timeout=0
sleep-inactive-battery-timeout=0

[org/gnome/desktop/background]
picture-uri=''
picture-uri-dark=''
primary-color='#000000'
secondary-color='#000000'
color-shading-type='solid'

[org/gnome/desktop/screensaver]
picture-uri=''
primary-color='#000000'
secondary-color='#000000'
color-shading-type='solid'
EOF
mkdir -p /etc/dconf/profile
cat >/etc/dconf/profile/user <<'EOF'
user-db:user
system-db:local
EOF
dconf update || true
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target || true

echo "[8c/8] Enabling automatic login"
SESSION_NAME="avppi-openbox"
cat >/usr/share/xsessions/${SESSION_NAME}.desktop <<'EOF'
[Desktop Entry]
Name=AVPPi Kiosk
Comment=Minimal session for AVPPi
Exec=/usr/bin/openbox-session
TryExec=/usr/bin/openbox-session
Type=Application
DesktopNames=AVPPi
EOF

install -d -m 755 /home/${SERVICE_USER}/.config/openbox
KIOSK_LOG="${LOG_DIR}/kiosk.log"
cat >/home/${SERVICE_USER}/.config/openbox/autostart <<EOF
#!/bin/sh
xsetroot -solid black
xset -dpms
xset s off
unclutter --timeout 0 --jitter 0 &
cd /opt/avppi && /opt/avppi/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >>${KIOSK_LOG} 2>&1 &
EOF
install -m 644 "${INSTALL_DIR}/config/openbox/rc.xml" /home/${SERVICE_USER}/.config/openbox/rc.xml
chown -R "${SERVICE_USER}:${SERVICE_USER}" /home/${SERVICE_USER}/.config
chmod +x /home/${SERVICE_USER}/.config/openbox/autostart
touch "${KIOSK_LOG}"
chown "${SERVICE_USER}:${SERVICE_USER}" "${KIOSK_LOG}"

mkdir -p /etc/gdm3
cat >/etc/gdm3/custom.conf <<EOF
[daemon]
AutomaticLoginEnable=true
AutomaticLogin=${SERVICE_USER}
AutomaticLoginSession=${SESSION_NAME}
EOF

mkdir -p /var/lib/AccountsService/users
cat >/var/lib/AccountsService/users/${SERVICE_USER} <<EOF
[User]
Session=${SESSION_NAME}
XSession=${SESSION_NAME}
SystemAccount=true
EOF
chmod 600 /var/lib/AccountsService/users/${SERVICE_USER}

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${PY_PREFIX}" || true

echo "avppi ALL=(ALL) NOPASSWD: /sbin/reboot" >/etc/sudoers.d/avppi-reboot
chmod 440 /etc/sudoers.d/avppi-reboot
chown root:root /etc/sudoers.d/avppi-reboot

echo "Installation complete."
echo "Log files: ${LOG_DIR}"
echo "Media directory: ${MEDIA_DIR}"
