#!/bin/bash
# Build file .deb cho FolderSync (offline, gom san wheels)
# Chay tu thu muc goc cua repo: ./packaging/build-deb.sh [version]
set -e
cd "$(dirname "$0")/.."

VER="${1:-1.0.0}"
PKG="packaging/deb/foldersync_${VER}_amd64"
WHEELS_DIR="packaging/deb/wheels"

echo "== Buoc 1: tai wheels (neu chua co) =="
mkdir -p "$WHEELS_DIR"
if ! ls "$WHEELS_DIR"/*.whl >/dev/null 2>&1; then
    pip download --quiet --dest "$WHEELS_DIR" --only-binary :all: \
        "PyQt6==6.7.1" "PyQt6-Fluent-Widgets==1.7.0"
fi
echo "   wheels: $(ls "$WHEELS_DIR"/*.whl | wc -l) file"

echo "== Buoc 2: dung cay thu muc package =="
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN"
mkdir -p "$PKG/opt/foldersync/wheels"
mkdir -p "$PKG/usr/bin"
mkdir -p "$PKG/usr/share/applications"
mkdir -p "$PKG/usr/share/icons/hicolor/256x256/apps"

# DEBIAN/control
cat > "$PKG/DEBIAN/control" <<EOF
Package: foldersync
Version: $VER
Section: utils
Priority: optional
Architecture: amd64
Depends: python3, python3-venv, rsync, cifs-utils
Maintainer: Gà <dkt999@local>
Description: Đồng bộ thư mục/ổ đĩa mạng theo lịch
 Port Python + PyQt6 của FolderSyncApp (C# WinForms).
 Đồng bộ ổ đĩa mạng về máy theo giờ hẹn, hỗ trợ mount SMB/CIFS
 qua giao diện, tự khởi động cùng hệ thống.
 .
 Bao gồm sẵn wheels PyQt6 để cài đặt offline.
EOF

# DEBIAN/postinst
cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e
APP_DIR="/opt/foldersync"
VENV_DIR="$APP_DIR/venv"
echo "FolderSync: dang tao moi truong ao..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet --no-index --find-links "$APP_DIR/wheels" \
    "PyQt6==6.7.1" "PyQt6-Fluent-Widgets==1.7.0"
chmod +x /usr/bin/foldersync
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
echo "FolderSync da cai xong. Chay: foldersync"
EOF

# DEBIAN/prerm
cat > "$PKG/DEBIAN/prerm" <<'EOF'
#!/bin/bash
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    rm -rf /opt/foldersync/venv
fi
EOF
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/prerm"
chmod 755 "$PKG/DEBIAN"

# App files
cp main.py requirements.txt "$PKG/opt/foldersync/"
cp -r foldersync "$PKG/opt/foldersync/"
cp "$WHEELS_DIR"/*.whl "$PKG/opt/foldersync/wheels/"
find "$PKG/opt/foldersync" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
find "$PKG/opt/foldersync" -name "*.pyc" -delete 2>/dev/null || true

# Wrapper + desktop + icon
cat > "$PKG/usr/bin/foldersync" <<'EOF'
#!/bin/bash
exec /opt/foldersync/venv/bin/python /opt/foldersync/main.py "$@"
EOF
chmod 755 "$PKG/usr/bin/foldersync"

cat > "$PKG/usr/share/applications/foldersync.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=FolderSync
Comment=Công cụ đồng bộ thư mục theo lịch
Exec=/usr/bin/foldersync
Icon=foldersync
Terminal=false
Categories=Utility;
StartupWMClass=FolderSync
EOF

if [ -f "foldersync/assets/icon-256.png" ]; then
    cp "foldersync/assets/icon-256.png" \
       "$PKG/usr/share/icons/hicolor/256x256/apps/foldersync.png"
fi

echo "== Buoc 3: build .deb =="
dpkg-deb --build "$PKG" "packaging/foldersync_${VER}_amd64.deb"
echo ""
echo "Xong: packaging/foldersync_${VER}_amd64.deb ($(du -h "packaging/foldersync_${VER}_amd64.deb" | cut -f1))"
echo "Cai dat: sudo dpkg -i packaging/foldersync_${VER}_amd64.deb"
echo "Go cai dat: sudo apt remove foldersync"
