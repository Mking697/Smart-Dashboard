#!/usr/bin/env bash
#
# Make PDF export work on a fresh Ubuntu server.
#
#   ~/Smart-Dashboard/deploy/install-pdf.sh
#
# Kaleido 1.x does not ship a browser - it drives one. On a desktop it finds the
# Chrome that is already there; a server has none, and Chrome needs a set of
# shared libraries that a minimal Ubuntu image does not install either. Without
# both, every export fails with a browser error and nothing explains why.
#
set -euo pipefail

APP_DIR="$HOME/Smart-Dashboard"
VENV="$APP_DIR/venv"

say() { printf "\n\033[1;34m==>\033[0m %s\n" "$1"; }
die() { printf "\n\033[1;31mSTOPPED:\033[0m %s\n" "$1" >&2; exit 1; }

[ -x "$VENV/bin/python" ] || die "No virtualenv at $VENV - run deploy/aws-setup.sh first."

# --------------------------------------------------------------------------- #
say "1/4  Python packages"
"$VENV/bin/pip" install --quiet --upgrade kaleido fpdf2
echo "    kaleido and fpdf2 installed"

# --------------------------------------------------------------------------- #
say "2/4  Shared libraries Chrome needs"
# Ubuntu 24.04 renamed a couple of these with a t64 suffix, so try both spellings
# and let the ones that do not exist on this release fall through.
sudo apt-get update -qq
for package in libnss3 libatk1.0-0t64 libatk1.0-0 libatk-bridge2.0-0t64 \
               libatk-bridge2.0-0 libcups2t64 libcups2 libgbm1 libasound2t64 \
               libasound2 libxkbcommon0 libxdamage1 libxfixes3 libxrandr2 \
               libpangocairo-1.0-0 libcairo2 libxcomposite1; do
    sudo apt-get install -y -qq "$package" 2>/dev/null || true
done
echo "    done"

# --------------------------------------------------------------------------- #
say "3/4  Chrome for Kaleido"
if "$VENV/bin/python" -c "
import sys
from choreographer.browsers import chromium
sys.exit(0 if chromium.Chromium.get_path() else 1)
" 2>/dev/null; then
    echo "    a browser is already available"
else
    "$VENV/bin/plotly_get_chrome" -y
    echo "    downloaded"
fi

# --------------------------------------------------------------------------- #
say "4/4  Proving it works"
"$VENV/bin/python" - <<'PYTEST'
import plotly.express as px
figure = px.bar(x=["A", "B", "C"], y=[3, 1, 2], title="export check")
png = figure.to_image(format="png", width=700, height=400)
print(f"    rendered a {len(png):,}-byte PNG")
PYTEST

printf "\n\033[1;32mPDF export is ready.\033[0m\n"
echo "  Restart the app so it picks up the new packages:"
echo "    sudo systemctl restart dashboard"
echo
echo "  Chrome needs a few hundred MB of RAM. On a 1 GB box, export one report"
echo "  at a time first and watch: sudo journalctl -u dashboard -f"
