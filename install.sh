#!/usr/bin/env bash
# Cai dat FolderSync tren Ubuntu.
#   ./install.sh            -> cai app + tao shortcut
#   ./install.sh --autostart -> cai app + bat tu khoi dong cung he thong
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/apps/foldersync"
VENV_DIR="$INSTALL_DIR/venv"

echo "== Kiem tra rsync + cifs-utils =="
needs=""
command -v rsync >/dev/null 2>&1 || needs="$needs rsync"
command -v mount.cifs >/dev/null 2>&1 || needs="$needs cifs-utils"
if [ -n "$needs" ]; then
    echo "Dang cai:$needs ..."
    sudo apt update && sudo apt install -y $needs
fi

echo "== Copy source vao $INSTALL_DIR =="
mkdir -p "$INSTALL_DIR"
cp -r "$APP_DIR"/main.py "$APP_DIR"/foldersync "$APP_DIR"/requirements.txt "$INSTALL_DIR"/

echo "== Tao venv va cai Python deps =="
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

echo "== Tao shortcut =="
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons"
# Icon goc port tu ban C# (uu tien PNG 256, fallback ico)
if [[ -f "$INSTALL_DIR/foldersync/assets/icon-256.png" ]]; then
  cp "$INSTALL_DIR/foldersync/assets/icon-256.png" "$HOME/.local/share/icons/foldersync.png"
elif [[ -f "$INSTALL_DIR/foldersync/assets/icon.ico" ]]; then
  cp "$INSTALL_DIR/foldersync/assets/icon.ico" "$HOME/.local/share/icons/foldersync.ico"
fi
cat > "$HOME/.local/share/applications/FolderSync.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=FolderSync
Comment=Cong cu dong bo thu muc theo lich
Exec=$VENV_DIR/bin/python $INSTALL_DIR/main.py
Icon=foldersync
Terminal=false
Categories=Utility;
EOF

if [[ "${1:-}" == "--autostart" ]]; then
    echo "== Bat tu khoi dong =="
    mkdir -p "$HOME/.config/autostart"
    sed 's|main.py|main.py --minimized|' \
        "$HOME/.local/share/applications/FolderSync.desktop" \
        > "$HOME/.config/autostart/FolderSync.desktop"
fi

echo ""
echo "Xong! Chay: $VENV_DIR/bin/python $INSTALL_DIR/main.py"
echo "(hoac mo FolderSync tu menu ung dung)"
