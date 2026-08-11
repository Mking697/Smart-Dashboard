#!/usr/bin/env bash
#
# One-shot setup for the AI Smart Dashboard on a fresh Ubuntu EC2 instance.
#
#   curl -fsSL https://raw.githubusercontent.com/Mking697/Smart-Dashboard/main/deploy/aws-setup.sh | bash
#
# Afterwards the app is reachable on port 80 at the instance's own public DNS
# name - no domain purchase needed:
#
#   http://ec2-XX-XX-XX-XX.ap-south-1.compute.amazonaws.com
#
set -euo pipefail

REPO_URL="https://github.com/Mking697/Smart-Dashboard.git"
APP_DIR="$HOME/Smart-Dashboard"
SERVICE_NAME="dashboard"
SWAP_FILE="/swapfile"
SWAP_SIZE="2G"

say() { printf "\n\033[1;34m==>\033[0m %s\n" "$1"; }
die() { printf "\n\033[1;31mSTOPPED:\033[0m %s\n" "$1" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# This script claims port 80 and replaces Nginx's enabled sites. On an instance
# that is already serving something, that would take the other project offline -
# so refuse to run rather than break it.
say "0/7  Safety check"

if [ -d /etc/nginx/sites-enabled ]; then
    OTHER_SITES="$(find /etc/nginx/sites-enabled -maxdepth 1 -type l -o -maxdepth 1 -type f \
        | xargs -r -n1 basename \
        | grep -v -x -e default -e dashboard || true)"
    if [ -n "$OTHER_SITES" ]; then
        die "This instance already serves other Nginx sites:
    $(echo "$OTHER_SITES" | tr '\n' ' ')

  This script takes over port 80 and would knock them offline.
  Launch a separate EC2 instance for the dashboard and run it there."
    fi
fi

for PORT_IN_USE in 80 8501; do
    if command -v ss >/dev/null && ss -ltn "sport = :$PORT_IN_USE" 2>/dev/null | grep -q LISTEN; then
        if [ "$PORT_IN_USE" = 80 ] && ! systemctl is-active --quiet nginx; then
            die "Something other than Nginx is already listening on port $PORT_IN_USE.
  Use a fresh instance so the running project is not disturbed."
        fi
    fi
done

echo "    nothing else is being served here - safe to continue"

# --------------------------------------------------------------------------- #
say "1/7  System packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip git nginx

# --------------------------------------------------------------------------- #
# A 1 GB t3.micro runs out of memory while pip builds pandas, and again when a
# large sheet is loaded. Swap costs nothing and prevents both.
say "2/7  Swap space"
if [ ! -f "$SWAP_FILE" ]; then
    sudo fallocate -l "$SWAP_SIZE" "$SWAP_FILE"
    sudo chmod 600 "$SWAP_FILE"
    sudo mkswap "$SWAP_FILE"
    sudo swapon "$SWAP_FILE"
    echo "$SWAP_FILE none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
    echo "    ${SWAP_SIZE} swap added"
else
    echo "    swap already present, skipping"
fi

# --------------------------------------------------------------------------- #
say "3/7  Application code"
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
else
    git clone --depth 1 "$REPO_URL" "$APP_DIR"
fi

# --------------------------------------------------------------------------- #
say "4/7  Python environment"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet
echo "    dependencies installed"

# --------------------------------------------------------------------------- #
say "5/7  API key"
if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" <<'ENVFILE'
# Gemini - powers the AI briefing, deep dive and chat
GEMINI_API_KEY=paste_your_key_here

# Brevo - sends the signup verification codes.
# The sender address must be verified in your Brevo account or mail is rejected.
BREVO_API_KEY=paste_your_brevo_key_here
BREVO_SENDER_EMAIL=noreply@yourdomain.com
BREVO_SENDER_NAME=AI Smart Dashboard
ENVFILE
    chmod 600 "$APP_DIR/.env"
    echo "    .env created - fill in your keys before using AI or signup"
else
    echo "    .env already exists, left untouched"
fi

# --------------------------------------------------------------------------- #
say "6/7  Service (starts on boot, restarts on crash)"
sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<SERVICE
[Unit]
Description=AI Smart Dashboard (Streamlit)
After=network.target

[Service]
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/streamlit run app.py \\
    --server.port 8501 \\
    --server.address 127.0.0.1 \\
    --server.headless true \\
    --browser.gatherUsageStats false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

# --------------------------------------------------------------------------- #
say "7/7  Nginx on port 80"
# Streamlit talks over websockets - without the Upgrade headers the page loads
# but never finishes connecting.
sudo tee /etc/nginx/sites-available/dashboard >/dev/null <<'NGINX'
server {
    listen 80 default_server;
    server_name _;

    client_max_body_size 50M;   # room for large spreadsheet uploads

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
        proxy_buffering off;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/dashboard
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# --------------------------------------------------------------------------- #
# Newer instances require IMDSv2, where every metadata read needs a token first.
IMDS_TOKEN="$(curl -fsS -X PUT --max-time 3 \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60" \
    http://169.254.169.254/latest/api/token 2>/dev/null || true)"

PUBLIC_DNS="$(curl -fsS --max-time 3 \
    ${IMDS_TOKEN:+-H "X-aws-ec2-metadata-token: $IMDS_TOKEN"} \
    http://169.254.169.254/latest/meta-data/public-hostname 2>/dev/null || true)"

printf "\n\033[1;32mDone.\033[0m\n"
if [ -n "$PUBLIC_DNS" ]; then
    echo "Open:  http://${PUBLIC_DNS}"
else
    echo "Open:  http://<your-instance-public-DNS>"
fi
echo
echo "Reminders:"
echo "  - Security Group must allow inbound HTTP (port 80) from 0.0.0.0/0"
echo "  - Put your real key in ${APP_DIR}/.env, then: sudo systemctl restart ${SERVICE_NAME}"
echo "  - Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
echo "  - Update:  cd ${APP_DIR} && git pull && sudo systemctl restart ${SERVICE_NAME}"
