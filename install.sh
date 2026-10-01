#!/usr/bin/env bash
# Install csc-openconnect for the current user so `csc-openconnect` runs from anywhere.
#   ./install.sh              install or update
#   ./install.sh --uninstall  remove
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/csc-openconnect"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/csc-openconnect"

if [[ "${1:-}" == "--uninstall" ]]; then
	rm -rf "$APP_DIR" "$LAUNCHER"
	echo "Removed $APP_DIR and $LAUNCHER"
	echo "Playwright's browser download in ~/.cache/ms-playwright was left in place."
	exit 0
fi

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
if ! python3 -c 'import venv, ensurepip' 2>/dev/null; then
	echo "Python's venv module is missing (on Debian/Ubuntu: sudo apt install python3-venv)" >&2
	exit 1
fi

echo "==> Setting up virtualenv in $APP_DIR"
mkdir -p "$APP_DIR" "$BIN_DIR"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$SRC_DIR/requirements.txt"

echo "==> Installing Chromium for Playwright (this can take a while)"
"$APP_DIR/venv/bin/playwright" install chromium

echo "==> Installing script and launcher"
install -m 755 "$SRC_DIR/csc-openconnect.py" "$APP_DIR/csc-openconnect.py"
cat > "$LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
exec "$APP_DIR/venv/bin/python" "$APP_DIR/csc-openconnect.py" "\$@"
LAUNCH
chmod 755 "$LAUNCHER"

echo
echo "Installed: $LAUNCHER"
# On Debian, openconnect lives in /usr/sbin, which isn't on a normal user's PATH (sudo's is fine).
PATH="$PATH:/usr/sbin:/sbin" command -v openconnect >/dev/null || echo "WARNING: openconnect is not installed (e.g. sudo apt install openconnect)"
case ":$PATH:" in
	*":$BIN_DIR:"*) ;;
	*) echo "WARNING: $BIN_DIR is not on your PATH; add it to your shell profile." ;;
esac
echo "If Chromium fails to start for missing libraries, run: sudo $APP_DIR/venv/bin/playwright install-deps chromium"
echo "Usage: csc-openconnect vpn.mycompany.com"
