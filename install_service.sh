#!/bin/bash

SERVICE_NAME="pasarguard"
SERVICE_DESCRIPTION="PasarGuard Service"
SERVICE_DOCUMENTATION="https://github.com/pasarguard/panel"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

install_dir_with_sentinel="$(pwd -P && printf x)" || {
  echo "Failed to resolve the installation directory." >&2
  exit 1
}
# The sentinel prevents command substitution from stripping a trailing newline
# from a valid (but unsupported) filesystem path before control-character
# validation below can reject it.
INSTALL_DIR=${install_dir_with_sentinel%x}
if printf '%s' "$INSTALL_DIR" | LC_ALL=C grep -q '[[:cntrl:]]'; then
  echo "Refusing to install from a path containing control characters." >&2
  exit 1
fi

# Escape characters that are significant inside systemd's double-quoted values.
SYSTEMD_INSTALL_DIR=${INSTALL_DIR//\\/\\\\}
SYSTEMD_INSTALL_DIR=${SYSTEMD_INSTALL_DIR//\"/\\\"}
SYSTEMD_INSTALL_DIR=${SYSTEMD_INSTALL_DIR//%/%%}

# Create the service file
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=$SERVICE_DESCRIPTION
Documentation=$SERVICE_DOCUMENTATION
After=network.target nss-lookup.target

[Service]
ExecStart="$SYSTEMD_INSTALL_DIR/.venv/bin/python3" "$SYSTEMD_INSTALL_DIR/main.py"
Restart=on-failure
WorkingDirectory="$SYSTEMD_INSTALL_DIR"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

echo "Service file created at: $SERVICE_FILE"
