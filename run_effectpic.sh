#!/usr/bin/env bash
set -e

# EffectPic - Lanzador y Gestor de Entorno para Ubuntu
DIR_APP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$DIR_APP/.venv"
REQ_FILE="$DIR_APP/requirements.txt"
U2NET_CACHE_DIR="$HOME/.rembg/models/u2net"

echo "=========================================================="
echo " EffectPic — Editor Gráfico Local con Modo Retrato IA"
echo "=========================================================="

# [1/4] Comprobar Python3 y GTK4 del sistema
echo "[1/4] Comprobando entorno del sistema (Python 3 y GTK 4)..."
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Se requiere Python 3 para ejecutar EffectPic."
    echo "Instálalo con: sudo apt install -y python3 python3-venv python3-gi gir1.2-gtk-4.0"
    exit 1
fi

# Configurar entorno virtual local si no existe
if [ ! -d "$VENV_DIR" ]; then
    echo "      Creando entorno virtual local con librerías del sistema (.venv)..."
    python3 -m venv --system-site-packages "$VENV_DIR"
fi

PYTHON_EXEC="$VENV_DIR/bin/python3"
PIP_EXEC="$VENV_DIR/bin/pip"

# [2/4] Comprobar e instalar dependencias fijadas
echo "[2/4] Verificando dependencias de inferencia IA en CPU..."
IA_DISPONIBLE=true

if ! "$PYTHON_EXEC" -c "import rembg, onnxruntime, PIL" &>/dev/null; then
    echo "      Instalando versiones fijadas de rembg, onnxruntime y dependencias..."
    if [ -f "$REQ_FILE" ]; then
        if ! "$PIP_EXEC" install --quiet -r "$REQ_FILE"; then
            echo "      [AVISO RECUPERABLE] No se pudieron instalar las dependencias de IA (posiblemente sin conexión)."
            echo "      Las funciones estándar de EffectPic (Ajustar, Blur, Recorte, Retoques) seguirán disponibles."
            IA_DISPONIBLE=false
        fi
    else
        if ! "$PIP_EXEC" install --quiet "rembg==2.0.85" "onnxruntime==1.30.0" "pillow==12.3.0"; then
            echo "      [AVISO RECUPERABLE] Error instalando paquetes de rembg."
            IA_DISPONIBLE=false
        fi
    fi
fi

# [3/4] Comprobar modelo U2-Net (168 MB)
echo "[3/4] Comprobando modelo local U2-Net..."
mkdir -p "$U2NET_CACHE_DIR"
MODEL_PATH="$U2NET_CACHE_DIR/u2net.onnx"

if [ -f "$MODEL_PATH" ]; then
    echo "      Modelo U2-Net disponible en caché local ($MODEL_PATH)."
elif [ "$IA_DISPONIBLE" = true ]; then
    echo "      El modelo u2net.onnx no está en caché. Descargando por única vez..."
    if "$PYTHON_EXEC" -c "import rembg; rembg.new_session('u2net')" 2>/dev/null; then
        echo "      Modelo descargado con éxito. Funcionará 100% offline a partir de ahora."
    else
        echo "      [AVISO RECUPERABLE] No se pudo descargar el modelo U2-Net (¿sin conexión en primer arranque?)."
        echo "      El Modo Retrato intentará descargarlo cuando haya conexión disponible."
    fi
else
    echo "      [AVISO RECUPERABLE] Modelo no descargado porque las dependencias de IA no están listas."
fi

# [4/4] Iniciar EffectPic
echo "[4/4] Iniciando EffectPic..."
exec "$PYTHON_EXEC" "$DIR_APP/effectpic.py" "$@"
