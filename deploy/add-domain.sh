#!/usr/bin/env bash
#
# Point the dashboard at your own domain and switch it to HTTPS.
#
#   ./add-domain.sh autolyst.online you@example.com
#
# Run this only after the domain's A records already point at this instance -
# Let's Encrypt verifies ownership over HTTP, so DNS has to resolve first. The
# script checks that for you and stops early rather than burning a rate limit.
#
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"

say() { printf "\n\033[1;34m==>\033[0m %s\n" "$1"; }
die() { printf "\n\033[1;31mSTOPPED:\033[0m %s\n" "$1" >&2; exit 1; }

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    die "Usage: $0 <domain> <email>
  Example: $0 autolyst.online you@example.com

  The email is only used by Let's Encrypt to warn you if a renewal ever fails."
fi

# --------------------------------------------------------------------------- #
say "1/4  Checking that DNS points here"

IMDS_TOKEN="$(curl -fsS -X PUT --max-time 3 \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60" \
    http://169.254.169.254/latest/api/token 2>/dev/null || true)"

MY_IP="$(curl -fsS --max-time 3 \
    ${IMDS_TOKEN:+-H "X-aws-ec2-metadata-token: $IMDS_TOKEN"} \
    http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"

[ -n "$MY_IP" ] || die "Could not read this instance's public IP."
echo "    this server : $MY_IP"

RESOLVED="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)"
echo "    $DOMAIN -> ${RESOLVED:-(does not resolve yet)}"

if [ -z "$RESOLVED" ]; then
    die "$DOMAIN does not resolve yet.

  Add an A record at your registrar pointing $DOMAIN to $MY_IP,
  then wait a few minutes and run this again."
fi

if [ "$RESOLVED" != "$MY_IP" ]; then
    die "$DOMAIN currently points to $RESOLVED, not to this server ($MY_IP).

  Either the A record is wrong, or DNS has not finished propagating.
  Fix or wait, then run this again."
fi

echo "    DNS is correct"

# --------------------------------------------------------------------------- #
say "2/4  Telling Nginx about the domain"

sudo tee /etc/nginx/sites-available/dashboard >/dev/null <<NGINX
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};

    client_max_body_size 50M;   # room for large spreadsheet uploads

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
        proxy_buffering off;
    }
}
NGINX

sudo nginx -t
sudo systemctl reload nginx
echo "    Nginx now answers for ${DOMAIN}"

# --------------------------------------------------------------------------- #
say "3/4  Getting the HTTPS certificate"

sudo apt-get update -qq
sudo apt-get install -y -qq certbot python3-certbot-nginx

# --redirect sends every http:// visitor to https:// automatically.
sudo certbot --nginx \
    -d "$DOMAIN" -d "www.${DOMAIN}" \
    --non-interactive --agree-tos --redirect \
    -m "$EMAIL"

# --------------------------------------------------------------------------- #
say "4/4  Checking automatic renewal"

# Certificates last 90 days. Certbot installs a timer that renews them well
# before expiry - this proves it is armed, without waiting three months to find out.
sudo certbot renew --dry-run

printf "\n\033[1;32mDone.\033[0m\n"
echo "Open:  https://${DOMAIN}"
echo
echo "  - http:// now redirects to https:// on its own"
echo "  - Renewal is automatic; check it with: systemctl list-timers | grep certbot"
