#!/usr/bin/env bash

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/avppi}"
SERVICE_NAME="${SERVICE_NAME:-avppi}"
SERVICE_USER="${SERVICE_USER:-avppi}"
PYTHON_VERSION="3.12.5"
PY_PREFIX="/opt/avppi/python-${PYTHON_VERSION}"
PYTHON_BIN="${PY_PREFIX}/bin/python3.12"
CONFIG_FILE="${CONFIG_FILE:-/etc/avppi/config.yaml}"
CONFIG_TEMPLATE="${INSTALL_DIR}/config/app_config.yaml"
MEDIA_DIR="${MEDIA_DIR:-${INSTALL_DIR}/AVPPi-medias}"
LOG_DIR="${INSTALL_DIR}/logs"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this update script with sudo."
  exit 1
fi

if [[ ! -d "${INSTALL_DIR}" ]]; then
  echo "Installation directory ${INSTALL_DIR} not found."
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python ${PYTHON_VERSION} not found at ${PYTHON_BIN}. Run scripts/install.sh first."
  exit 1
fi

echo "[1/4] Fetching latest code"
git -C "${INSTALL_DIR}" fetch --all --prune
git -C "${INSTALL_DIR}" reset --hard origin/main
chmod +x "${INSTALL_DIR}/scripts/"*.sh || true
install -d -m 750 "${MEDIA_DIR}" "${INSTALL_DIR}/data"
install -d -m 755 "${LOG_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}" "${MEDIA_DIR}" "${LOG_DIR}"

VENV_DIR="${INSTALL_DIR}/.venv"
echo "[2/4] Rebuilding virtual environment"
rm -rf "${VENV_DIR}"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"

export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
"${VENV_DIR}/bin/pip" install --upgrade pip wheel
"${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo "[3/4] Skipping systemd service (Openbox autostart handles AVPPi)"

if [[ -f "${CONFIG_FILE}" ]]; then
  "${VENV_DIR}/bin/python" - <<'PY' "${CONFIG_TEMPLATE}" "${CONFIG_FILE}" "${MEDIA_DIR}" "${LOG_DIR}" "${SERVICE_USER}"
import sys
from pathlib import Path

import yaml

template_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
media_dir = sys.argv[3]
log_dir = sys.argv[4]
service_user = sys.argv[5]

template = yaml.safe_load(template_path.read_text()) or {}
current = yaml.safe_load(output_path.read_text()) if output_path.exists() else {}

for key, value in template.items():
    current[key] = value

current["media_directory"] = media_dir
current["log_directory"] = log_dir
current["rclone_binary"] = current.get("rclone_binary", "/usr/bin/rclone")
current["rclone_config_path"] = f"/home/{service_user}/.config/rclone/rclone.conf"

output_path.write_text(yaml.safe_dump(current, sort_keys=False, allow_unicode=True))
PY
  chown "${SERVICE_USER}:${SERVICE_USER}" "${CONFIG_FILE}"
fi

mkdir -p "${LOG_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${LOG_DIR}"

echo "[4/4] Reloading kiosk configuration"

echo "[4b/4] Ensuring desktop power settings disabled"
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

echo "[4c/4] Enabling automatic login"
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

echo "Update completed."

echo "avppi ALL=(ALL) NOPASSWD: /sbin/reboot" >/etc/sudoers.d/avppi-reboot
chmod 440 /etc/sudoers.d/avppi-reboot
chown root:root /etc/sudoers.d/avppi-reboot
