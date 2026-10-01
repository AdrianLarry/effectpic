#!/usr/bin/env bash
set -e

echo "=== Construyendo paquete .deb para EffectPic ==="
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$PROJECT_DIR/build_deb"
DIST_DIR="$PROJECT_DIR/dist"

mkdir -p "$DIST_DIR"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/opt/effectpic/docs"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/128x128/apps"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/64x64/apps"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/48x48/apps"

# 1. Copiar código y requisitos a /opt/effectpic
cp "$PROJECT_DIR/effectpic.py" "$BUILD_DIR/opt/effectpic/effectpic.py"
cp "$PROJECT_DIR/requirements.txt" "$BUILD_DIR/opt/effectpic/requirements.txt"
if [ -f "$PROJECT_DIR/docs/licencias_ia.md" ]; then
    cp "$PROJECT_DIR/docs/licencias_ia.md" "$BUILD_DIR/opt/effectpic/docs/licencias_ia.md"
fi

# 2. Copiar iconos
cp "$PROJECT_DIR/assets/icons/effectpic.svg" "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps/effectpic.svg"
cp "$PROJECT_DIR/assets/icons/effectpic_256.png" "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps/effectpic.png"
cp "$PROJECT_DIR/assets/icons/effectpic_128.png" "$BUILD_DIR/usr/share/icons/hicolor/128x128/apps/effectpic.png"
cp "$PROJECT_DIR/assets/icons/effectpic_64.png" "$BUILD_DIR/usr/share/icons/hicolor/64x64/apps/effectpic.png"
cp "$PROJECT_DIR/assets/icons/effectpic_48.png" "$BUILD_DIR/usr/share/icons/hicolor/48x48/apps/effectpic.png"

# 3. Lanzador /usr/bin/effectpic
cat << 'EOF' > "$BUILD_DIR/usr/bin/effectpic"
#!/usr/bin/env bash
set -e

# Lanzador del sistema para EffectPic (/usr/bin/effectpic)
APP_DIR="/opt/effectpic"
USER_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/effectpic"
USER_VENV="$USER_DATA_DIR/venv"
REQ_FILE="$APP_DIR/requirements.txt"
U2NET_CACHE_DIR="$HOME/.rembg/models/u2net"

mkdir -p "$USER_DATA_DIR"

# 1. Entorno de ejecución aislado en espacio de usuario
if [ ! -d "$USER_VENV" ]; then
    python3 -m venv --system-site-packages "$USER_VENV"
fi

PYTHON_EXEC="$USER_VENV/bin/python3"
PIP_EXEC="$USER_VENV/bin/pip"

# 2. Verificación de dependencias de IA (rembg, onnxruntime, pillow)
if ! "$PYTHON_EXEC" -c "import rembg, onnxruntime, PIL" &>/dev/null; then
    if [ -f "$REQ_FILE" ]; then
        "$PIP_EXEC" install --quiet -r "$REQ_FILE" || true
    else
        "$PIP_EXEC" install --quiet "rembg==2.0.85" "onnxruntime==1.30.0" "pillow==12.3.0" || true
    fi
fi

# 3. Detección de modelo local U2-Net (u2net.onnx)
mkdir -p "$U2NET_CACHE_DIR"
MODEL_PATH="$U2NET_CACHE_DIR/u2net.onnx"
if [ ! -f "$MODEL_PATH" ]; then
    if [ -f "$HOME/.u2net/u2net.onnx" ]; then
        ln -sf "$HOME/.u2net/u2net.onnx" "$MODEL_PATH"
    fi
fi

# 4. Lanzar EffectPic pasando todos los argumentos (e.g. rutas de imágenes abiertas)
exec "$PYTHON_EXEC" "$APP_DIR/effectpic.py" "$@"
EOF
chmod 755 "$BUILD_DIR/usr/bin/effectpic"

# 4. Archivo .desktop
cat << 'EOF' > "$BUILD_DIR/usr/share/applications/effectpic.desktop"
[Desktop Entry]
Name=EffectPic
GenericName=Editor Fotográfico
Comment=Editor fotográfico y desenfoque de fondo local para redes sociales
Exec=/usr/bin/effectpic %F
Icon=effectpic
Terminal=false
Type=Application
Categories=Graphics;Photography;GTK;
MimeType=image/jpeg;image/png;image/webp;
StartupNotify=true
Keywords=photo;editor;blur;bokeh;social;instagram;portrait;
EOF
chmod 644 "$BUILD_DIR/usr/share/applications/effectpic.desktop"

# 5. Archivo DEBIAN/control
cat << 'EOF' > "$BUILD_DIR/DEBIAN/control"
Package: effectpic
Version: 1.0.0
Section: graphics
Priority: optional
Architecture: all
Maintainer: AdrianLarry <familystyle@outlook.es>
Depends: python3 (>= 3.10), python3-venv, python3-gi, python3-gi-cairo, gir1.2-gtk-4.0, python3-pil
Homepage: https://github.com/AdrianLarry/effectpic
Description: Editor fotográfico para redes sociales con Modo Retrato IA
 EffectPic permite adaptar imágenes a formatos 1:1, 4:5, 9:16 y 16:9
 incorporando recorte interactivo, retoques de color, carrusel por lotes,
 historial de deshacer/rehacer y desenfoque bokeh con IA U2-Net y GTK4.
EOF
chmod 644 "$BUILD_DIR/DEBIAN/control"

# 6. Scripts postinst y postrm
cat << 'EOF' > "$BUILD_DIR/DEBIAN/postinst"
#!/bin/sh
set -e

if [ "$1" = "configure" ]; then
    if which update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if which gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi

exit 0
EOF
chmod 755 "$BUILD_DIR/DEBIAN/postinst"

cat << 'EOF' > "$BUILD_DIR/DEBIAN/postrm"
#!/bin/sh
set -e

if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if which update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if which gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi

exit 0
EOF
chmod 755 "$BUILD_DIR/DEBIAN/postrm"

# Permisos para el resto de archivos
find "$BUILD_DIR" -type d -exec chmod 755 {} +
chmod 644 "$BUILD_DIR/opt/effectpic/effectpic.py"
chmod 644 "$BUILD_DIR/opt/effectpic/requirements.txt"
if [ -f "$BUILD_DIR/opt/effectpic/docs/licencias_ia.md" ]; then
    chmod 644 "$BUILD_DIR/opt/effectpic/docs/licencias_ia.md"
fi
find "$BUILD_DIR/usr/share/icons" -type f -exec chmod 644 {} +

# 7. Compilar el paquete .deb con dpkg-deb
DEB_NAME="effectpic_1.0.0_all.deb"
dpkg-deb --build --root-owner-group "$BUILD_DIR" "$DIST_DIR/$DEB_NAME"

echo "✓ Paquete generado exitosamente en: $DIST_DIR/$DEB_NAME"
dpkg -I "$DIST_DIR/$DEB_NAME"
