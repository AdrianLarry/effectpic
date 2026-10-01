# EffectPic 📸✨

> **Editor fotográfico nativo para redes sociales con composición dinámica, retoque de color y Modo Retrato con IA local.**

[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Ubuntu-orange.svg)](https://ubuntu.com)
[![Toolkit](https://img.shields.io/badge/GUI-GTK4%20%7C%20Libadwaita%20Style-blue.svg)](https://www.gtk.org)
[![Python](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org)
[![Inference](https://img.shields.io/badge/AI-U2--Net%20%28100%25%20Offline%29-indigo.svg)](https://github.com/danielgatis/rembg)
[![License](https://img.shields.io/badge/License-Apache%202.0%20%2F%20GPL-purple.svg)](docs/licencias_ia.md)

---

## 🌟 Características Principales

### 📐 Formatos y Relaciones de Aspecto
- **Social · Cuadrado 1:1** (1080 × 1080 px) — Ideal para feeds de Instagram, Facebook y fotos de perfil.
- **Social · Retrato 4:5** (1080 × 1350 px) — Maximiza el área visual en feeds verticales sin cortes indeseados.
- **Social · Vertical 9:16** (1080 × 1920 px) — Formato completo para Instagram Stories, Reels, TikTok y YouTube Shorts.
- **Social · Wide 16:9** (1920 × 1080 px) — Paisajes, banners y miniaturas de YouTube.

---

### 🎨 Tres Modos de Renderizado
1. **Ajustar + Blur:** Mantiene la imagen original completa y sin cortes en el centro, rellenando los laterales o bandas con una versión desenfocada (`GaussianBlur` proporcional al lienzo) y sutilmente oscurecida para máxima legibilidad.
2. **Recortar Interactivo:** Llena el lienzo completamente permitiendo encuadrar libremente mediante arrastre con el ratón (`pan`), control de zoom suave (100% a 300%) y botón para recentrar con un toque.
3. **Modo Retrato con IA (Bokeh Local):** Segmentación automática del sujeto mediante inferencia de red neuronal U2-Net ejecutada íntegramente en la CPU local, manteniendo al sujeto nítido en primer plano y desenfocando el fondo de forma realista. Funciona **100% offline**, sin enviar ninguna imagen a servidores externos.

---

### 🎛️ Retoque Fotográfico y Presets
- Ajustes finos mediante controles deslizantes de **Brillo**, **Contraste** y **Saturación** (-100 a +100).
- **Presets de estilo instantáneo:**
  - *Vívido* (colores vivos y punch contrastado)
  - *Cálido* (tonos dorados y acogedores)
  - *Dramático* (sombras profundas y alto impacto)
  - *Vintage* (estilo retro suave y desaturado)
  - *B&N Clásico* & *B&N Suave* (monocromáticos equilibrados)
- Botón **"Reiniciar retoques"** para restaurar valores a 0 en cualquier momento.

---

### ⏪ Historial No Destructivo (Undo / Redo) & Comparador
- **Deshacer (`Ctrl+Z`)** y **Rehacer (`Ctrl+Shift+Z` / `Ctrl+Y`)** completos con botones dedicados en la barra superior.
- **Botón "Restaurar"** para regresar la foto al estado original recién cargado.
- **Comparador Antes / Después:** Conmutador visual o atajo manteniendo presionada la tecla **`Espacio`** o **`\`** para contrastar al vuelo la imagen editada con la foto original.

---

### 🎞️ Modo Carrusel y Procesamiento por Lotes
- Soporte para **arrastrar y soltar (Drag & Drop)** múltiples imágenes directamente sobre la ventana.
- Tira horizontal de miniaturas para navegar, reordenar y organizar las fotos.
- Botón **"Copiar estilo a todas"** para replicar formato, modo, blur y ajustes de color a todo el lote con un solo clic.
- **Exportación en lote:** Guarda todas las imágenes numeradas secuencialmente (`01_nombre_1080x1080.jpg`) con compresión JPEG de alta fidelidad (calidad 95, subsampling 4:4:4).

---

## 🚀 Instalación en Ubuntu / Debian (.deb)

### Descargar e instalar el paquete oficial `.deb`:

```bash
# Instalar paquete deb
sudo apt install ./dist/effectpic_1.0.0_all.deb
```

Una vez instalado, EffectPic se integra directamente con el sistema:
- Puedes lanzarlo desde el menú de aplicaciones de tu escritorio buscando **EffectPic**.
- También puedes ejecutarlo desde la terminal con el comando:
  ```bash
  effectpic [ruta_a_la_foto.jpg ...]
  ```

---

## ⌨️ Atajos de Teclado

| Atajo | Acción |
|---|---|
| <kbd>Ctrl</kbd> + <kbd>Z</kbd> | Deshacer última acción |
| <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>Z</kbd> o <kbd>Ctrl</kbd> + <kbd>Y</kbd> | Rehacer acción |
| Mantener <kbd>Espacio</kbd> o <kbd>\</kbd> | Previsualizar imagen original |
| Arrastre de ratón | Mover / encuadrar imagen en modo Recortar o Retrato |

---

## 💻 Ejecución en Modo Desarrollo

Si deseas ejecutar el código directamente desde el repositorio:

```bash
# 1. Clonar el repositorio
git clone https://github.com/AdrianLarry/effectpic.git
cd effectpic

# 2. Iniciar con el script de lanzamiento
./run_effectpic.sh
```

---

## 🔒 Privacidad y Licencias

- **100% Local y Privado:** Ningún dato, telemetría o imagen abandona tu equipo.
- **Modelo de IA:** Utiliza [U2-Net](https://github.com/xuebinqin/U-2-Net) bajo licencia **Apache 2.0** compatible con distribución y uso personal/comercial. Consulta [docs/licencias_ia.md](docs/licencias_ia.md) para más detalles.
