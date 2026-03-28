#!/bin/bash
set -euo pipefail

echo "[1/3] Installing socat..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y socat

echo "[2/3] Writing remote-browser-host-proxy service..."
cat <<'EOF' | sudo tee /etc/systemd/system/remote-browser-host-proxy.service
[Unit]
Description=Expose SSH reverse-tunneled remote browser bridge to Docker containers
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/socat TCP-LISTEN:8319,bind=0.0.0.0,reuseaddr,fork TCP:127.0.0.1:8318
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

echo "[3/3] Enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable remote-browser-host-proxy
sudo systemctl restart remote-browser-host-proxy
sleep 2
sudo systemctl --no-pager --full status remote-browser-host-proxy | grep -E 'Loaded:|Active:' || true
echo
echo "Proxy check:"
curl -sS --max-time 5 http://127.0.0.1:8319/health || true
