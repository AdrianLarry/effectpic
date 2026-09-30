#!/usr/bin/env python3

import os
import sys
import glob

# Auto-detección del entorno virtual local (.venv):
# Si se ejecuta con el Python del sistema (/bin/python3 effectpic.py)
# sin activar el venv, se incorporan automáticamente los paquetes de .venv
# para que rembg, onnxruntime y dependencias estén disponibles de inmediato.
_dir_base = os.path.dirname(os.path.abspath(__file__))
_venv_sites = glob.glob(os.path.join(_dir_base, ".venv", "lib", "python*", "site-packages"))
for _p in _venv_sites:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import gi
gi.require_version("Gtk", "4.0")

import copy
import re
import tempfile
import threading

from gi.repository import Gtk, Gio, Gdk, GdkPixbuf, GLib
from PIL import Image, ImageOps, ImageFilter, ImageEnhance

# Sesión ONNX Runtime de inferencia rembg (Singleton reutilizable)
_rembg_session = None

def obtener_sesion_rembg(modelo="u2net"):
    """
    Obtiene o inicializa una sesión de inferencia de rembg con el modelo
    especificado explícitamente (u2net por defecto, bajo licencia Apache 2.0).
    Reutiliza la misma sesión para evitar recargas del archivo ONNX.
    """
    global _rembg_session
    if _rembg_session is None:
        import rembg
        _rembg_session = rembg.new_session(modelo)
    return _rembg_session


# Nombre visible -> resolución REAL de salida
FORMATOS = {
    "Social · Cuadrado 1:1": (1080, 1080),
    "Social · Retrato 4:5": (1080, 1350),
    "Social · Vertical 9:16": (1080, 1920),
    "Social · Wide 16:9": (1920, 1080),
}

# Presets de retoque rápido: (Brillo, Contraste, Saturación)
PRESETS_RETOQUE = {
    "— Presets —": (0, 0, 0),
    "Normal": (0, 0, 0),
    "Vívido": (5, 20, 30),
    "Cálido": (8, 12, 18),
    "Dramático": (-5, 35, -10),
    "Vintage": (12, -15, -20),
    "B&N Clásico": (0, 25, -100),
    "B&N Suave": (10, 5, -100),
}

CSS_ESTILO = """
window.main-window {
    background-color: #0f1013;
    color: #e2e8f0;
}

/* Header & Top Bar */
.top-bar {
    background-color: #17181f;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 8px 14px;
}

.app-title {
    font-size: 15px;
    font-weight: 800;
    letter-spacing: -0.4px;
    color: #ffffff;
}

.app-tag {
    font-size: 10px;
    font-weight: 700;
    color: #a5b4fc;
    background: rgba(99, 102, 241, 0.2);
    border: 1px solid rgba(99, 102, 241, 0.35);
    border-radius: 6px;
    padding: 2px 6px;
}

/* Buttons */
button {
    border-radius: 8px;
    font-weight: 600;
    color: #f8fafc;
    background-color: #262835;
    border: 1px solid rgba(255, 255, 255, 0.14);
    transition: all 120ms ease-in-out;
}

button:hover {
    background-color: #35384a;
    border-color: rgba(255, 255, 255, 0.28);
    color: #ffffff;
}

button:active {
    background-color: #1e1f2b;
}

button:disabled {
    background-color: rgba(255, 255, 255, 0.03);
    color: rgba(255, 255, 255, 0.22);
    border: 1px solid rgba(255, 255, 255, 0.05);
}

.btn-abrir {
    background: #2b2e40;
    border: 1px solid rgba(255, 255, 255, 0.18);
    color: #ffffff;
    font-weight: 700;
    padding: 6px 14px;
}
.btn-abrir:hover {
    background: #393d55;
    border-color: rgba(255, 255, 255, 0.32);
}

/* Compare Button */
.btn-comparar {
    background: #202436;
    border: 1px solid #3b82f6;
    color: #93c5fd;
    font-weight: 600;
}
.btn-comparar:hover {
    background: #28314a;
    border-color: #60a5fa;
    color: #bfdbfe;
}
.btn-comparar:checked {
    background: rgba(16, 185, 129, 0.25);
    border: 1px solid #10b981;
    color: #34d399;
    font-weight: 700;
    box-shadow: 0 0 10px rgba(16, 185, 129, 0.3);
}
.btn-comparar:disabled {
    background-color: rgba(255, 255, 255, 0.03);
    color: rgba(255, 255, 255, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.05);
}

/* DropDowns */
dropdown > button {
    background-color: #262835;
    border: 1px solid rgba(255, 255, 255, 0.14);
    color: #f8fafc;
    border-radius: 8px;
    font-weight: 600;
}
dropdown > button:hover {
    background-color: #35384a;
    border-color: rgba(255, 255, 255, 0.28);
}
dropdown > button:disabled {
    background-color: rgba(255, 255, 255, 0.03);
    color: rgba(255, 255, 255, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.05);
}

.badge-info {
    font-size: 12px;
    font-weight: 600;
    color: #94a3b8;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 4px 10px;
}

/* Empty State */
.empty-state-card {
    border: 2px dashed rgba(255, 255, 255, 0.14);
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.02);
    padding: 48px 56px;
}
.empty-state-card:hover {
    border-color: rgba(99, 102, 241, 0.45);
    background: rgba(99, 102, 241, 0.04);
}

.empty-icon {
    color: #818cf8;
}

.empty-title {
    font-size: 20px;
    font-weight: 800;
    color: #f8fafc;
    letter-spacing: -0.3px;
}

.empty-subtitle {
    font-size: 13px;
    color: #94a3b8;
}

.format-pill {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: #64748b;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 6px;
    padding: 2px 8px;
}

/* Canvas Frame */
.canvas-frame {
    border-radius: 12px;
}

/* Bottom Cards */
.card-dock {
    background-color: #17181f;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 8px 14px;
}

.dock-label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #94a3b8;
}

/* Segmented Buttons */
.segmented-box {
    background: rgba(0, 0, 0, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 3px;
}
.segmented-box button {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px 12px;
    font-weight: 600;
    font-size: 12px;
    color: #94a3b8;
}
.segmented-box button:checked {
    background: #2a2d3d;
    color: #ffffff;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
}

/* Sliders */
scale trough {
    background-color: rgba(255, 255, 255, 0.1);
    border-radius: 999px;
    min-height: 4px;
    min-width: 4px;
}
scale highlight {
    background: #6366f1;
    border-radius: 999px;
}
scale slider {
    background-color: #ffffff;
    border: 2px solid #6366f1;
    border-radius: 50%;
    min-width: 14px;
    min-height: 14px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}
scale slider:hover {
    background-color: #c7d2fe;
}

/* Export Button */
.btn-exportar-principal {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
    color: #ffffff;
    font-weight: 700;
    font-size: 13px;
    border-radius: 10px;
    border: none;
    padding: 8px 20px;
    box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4);
}
.btn-exportar-principal:hover {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
    box-shadow: 0 6px 22px rgba(99, 102, 241, 0.6);
}
.btn-exportar-principal:disabled {
    background: rgba(255, 255, 255, 0.06);
    color: rgba(255, 255, 255, 0.25);
    box-shadow: none;
}

/* Filmstrip */
.carrusel-strip {
    background: #17181f;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
}
.carrusel-card {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 10px;
    padding: 4px;
}
.carrusel-card-active {
    border-color: #6366f1;
    background: rgba(99, 102, 241, 0.12);
}

/* Badge & Spinner de IA (Modo Retrato) */
.badge-ia {
    font-size: 11px;
    font-weight: 700;
    color: #a5b4fc;
    background: rgba(99, 102, 241, 0.15);
    border: 1px solid rgba(99, 102, 241, 0.35);
    border-radius: 6px;
    padding: 2px 8px;
}
.badge-ia-ready {
    color: #34d399;
    background: rgba(16, 185, 129, 0.15);
    border-color: rgba(16, 185, 129, 0.35);
}
"""


class ItemCarrusel:

    def __init__(self, ruta):
        self.ruta = ruta
        self.nombre = os.path.basename(ruta)
        self.modo = "blur"
        self.blur_valor = 50.0
        self.zoom = 100.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.brillo = 0.0
        self.contraste = 0.0
        self.saturacion = 0.0

        # Máscara binaria/escala de grises ('L') del sujeto calculada por IA (u2net)
        # Se almacena en la foto activa para no recalcularla en cada ajuste.
        # No se duplica en el historial de deshacer/rehacer.
        self.mascara_sujeto = None

        self.historial_deshacer = []
        self.historial_rehacer = []
        self.estado_actual = None
        self.estado_inicial = None

        self.miniatura_texture = None
        self._cargar_miniatura()

    def _cargar_miniatura(self):
        try:
            pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                self.ruta,
                80,
                80,
                True
            )
            self.miniatura_texture = Gdk.Texture.new_for_pixbuf(pix)
        except Exception as e:
            print("Error cargando miniatura:", e)

    def guardar_desde_ventana(self, win):
        if win.modo_retrato.get_active():
            self.modo = "retrato"
        elif win.modo_recortar.get_active():
            self.modo = "recortar"
        else:
            self.modo = "blur"
        self.blur_valor = win.blur_valor
        self.zoom = win.zoom_ajuste.get_value()
        self.offset_x = win.offset_x
        self.offset_y = win.offset_y
        self.brillo = win.brillo_valor
        self.contraste = win.contraste_valor
        self.saturacion = win.saturacion_valor
        self.historial_deshacer = list(win.historial_deshacer)
        self.historial_rehacer = list(win.historial_rehacer)
        self.estado_actual = copy.deepcopy(win.estado_actual)
        self.estado_inicial = copy.deepcopy(win.estado_inicial)

    def cargar_en_ventana(self, win):
        win.ruta_actual = self.ruta
        win.historial_deshacer = list(self.historial_deshacer)
        win.historial_rehacer = list(self.historial_rehacer)
        win.estado_actual = copy.deepcopy(self.estado_actual)
        win.estado_inicial = copy.deepcopy(self.estado_inicial)

        estado = {
            "formato_idx": win.selector.get_selected(),
            "modo": self.modo,
            "blur_valor": self.blur_valor,
            "zoom": self.zoom,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "brillo": self.brillo,
            "contraste": self.contraste,
            "saturacion": self.saturacion
        }
        win.aplicar_estado(estado)
        if win.estado_actual is None:
            win.estado_actual = win.obtener_estado_actual()
            win.estado_inicial = copy.deepcopy(win.estado_actual)
        self.guardar_desde_ventana(win)


class EffectPic(Gtk.Application):

    def __init__(self):
        super().__init__(
            application_id="com.effectpic.app",
            flags=Gio.ApplicationFlags.HANDLES_OPEN
        )

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.cargar_estilos_css()

    def cargar_estilos_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS_ESTILO.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def do_activate(self):
        self.ventana = EffectPicWindow(self)
        self.ventana.present()

    def do_open(self, files, n_files, hint):
        self.ventana = EffectPicWindow(self)
        self.ventana.present()

        if n_files > 0:
            rutas = [files[i].get_path() for i in range(n_files) if files[i].get_path()]
            if rutas:
                self.ventana.cargar_carrusel(rutas)


class EffectPicWindow(Gtk.ApplicationWindow):

    def __init__(self, app):
        super().__init__(application=app)

        self.set_title("EffectPic")
        self.set_default_size(1180, 840)
        self.add_css_class("main-window")

        # Soporte para arrastrar y soltar imágenes directamente a la ventana
        target_drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target_drop.connect("drop", self._archivos_soltados)
        self.add_controller(target_drop)

        self.ruta_actual = None
        self.preview_temporal = None
        self.preview_temporal_original = None
        self.tecla_comparar_activa = False

        # Secuencia de detección para invalidar resultados obsoletos
        self._secuencia_deteccion = 0

        # Modo Carrusel
        self.carrusel = []
        self.indice_activo = 0

        # Estado del recorte interactivo
        self.zoom_recorte = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.drag_inicio_x = 0.0
        self.drag_inicio_y = 0.0
        self.drag_offset_x = 0.0
        self.drag_offset_y = 0.0

        # Historial de Deshacer / Rehacer
        self.historial_deshacer = []
        self.historial_rehacer = []
        self.estado_actual = None
        self.estado_inicial = None
        self._bloquear_registro = False
        self._arrastrando_slider = False
        self._timer_slider = None

        # Ajustes de imagen (Brillo, Contraste, Saturación)
        self.brillo_valor = 0.0
        self.contraste_valor = 0.0
        self.saturacion_valor = 0.0

        # ============================================================
        # CONTENEDOR PRINCIPAL
        # ============================================================

        principal = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12
        )

        principal.set_margin_top(12)
        principal.set_margin_bottom(12)
        principal.set_margin_start(14)
        principal.set_margin_end(14)

        self.set_child(principal)

        # ============================================================
        # BARRA SUPERIOR (HEADER ESTUDIO)
        # ============================================================

        barra = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10
        )
        barra.add_css_class("top-bar")

        principal.append(barra)

        # Logotipo / Nombre de la app
        caja_marca = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4
        )
        caja_marca.set_valign(Gtk.Align.CENTER)
        caja_marca.set_margin_end(6)

        icono_marca = Gtk.Image.new_from_icon_name("camera-photo-symbolic")
        caja_marca.append(icono_marca)

        lbl_marca = Gtk.Label(label="EffectPic")
        lbl_marca.add_css_class("app-title")
        caja_marca.append(lbl_marca)

        lbl_tag = Gtk.Label(label="STUDIO")
        lbl_tag.add_css_class("app-tag")
        caja_marca.append(lbl_tag)

        barra.append(caja_marca)

        sep_marca = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        barra.append(sep_marca)

        # Botón Abrir con ícono
        boton_abrir = Gtk.Button()
        boton_abrir.add_css_class("btn-abrir")
        caja_btn_abrir = Gtk.Box(spacing=6)
        caja_btn_abrir.append(Gtk.Image.new_from_icon_name("document-open-symbolic"))
        caja_btn_abrir.append(Gtk.Label(label="Abrir"))
        boton_abrir.set_child(caja_btn_abrir)
        boton_abrir.set_tooltip_text("Abrir una o varias fotos (o arrastralas a la ventana)")
        boton_abrir.connect("clicked", self.abrir_imagen)
        barra.append(boton_abrir)

        # Botones Deshacer y Rehacer agrupados
        caja_undo_redo = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        caja_undo_redo.add_css_class("linked")

        self.boton_deshacer = Gtk.Button()
        caja_btn_undo = Gtk.Box(spacing=4)
        caja_btn_undo.append(Gtk.Image.new_from_icon_name("edit-undo-symbolic"))
        caja_btn_undo.append(Gtk.Label(label="Deshacer"))
        self.boton_deshacer.set_child(caja_btn_undo)
        self.boton_deshacer.set_tooltip_text("Deshacer última acción (Ctrl+Z)")
        self.boton_deshacer.set_sensitive(False)
        self.boton_deshacer.connect("clicked", lambda b: self.deshacer())
        caja_undo_redo.append(self.boton_deshacer)

        self.boton_rehacer = Gtk.Button()
        caja_btn_redo = Gtk.Box(spacing=4)
        caja_btn_redo.append(Gtk.Image.new_from_icon_name("edit-redo-symbolic"))
        caja_btn_redo.append(Gtk.Label(label="Rehacer"))
        self.boton_rehacer.set_child(caja_btn_redo)
        self.boton_rehacer.set_tooltip_text("Rehacer última acción (Ctrl+Shift+Z)")
        self.boton_rehacer.set_sensitive(False)
        self.boton_rehacer.connect("clicked", lambda b: self.rehacer())
        caja_undo_redo.append(self.boton_rehacer)

        barra.append(caja_undo_redo)

        self.boton_restaurar = Gtk.Button(label="Restaurar")
        self.boton_restaurar.set_tooltip_text("Restaurar al estado original")
        self.boton_restaurar.set_sensitive(False)
        self.boton_restaurar.connect("clicked", lambda b: self.restaurar_original())
        barra.append(self.boton_restaurar)

        sep_barra1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        barra.append(sep_barra1)

        self.boton_comparar = Gtk.ToggleButton(label="Comparar")
        self.boton_comparar.add_css_class("btn-comparar")
        self.boton_comparar.set_tooltip_text("Alternar o mantener [Espacio] para ver original")
        self.boton_comparar.set_sensitive(False)
        self.boton_comparar.connect("toggled", self.comparar_toggled)
        barra.append(self.boton_comparar)

        sep_barra2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        barra.append(sep_barra2)

        lbl_formato = Gtk.Label(label="Formato:")
        lbl_formato.add_css_class("dock-label")
        barra.append(lbl_formato)

        self.selector = Gtk.DropDown.new_from_strings(
            list(FORMATOS.keys())
        )
        self.selector.set_selected(0)
        self.selector.connect("notify::selected", self.formato_cambiado)
        barra.append(self.selector)

        self.info = Gtk.Label(label="Ninguna imagen abierta")
        self.info.add_css_class("badge-info")
        self.info.set_hexpand(True)
        self.info.set_halign(Gtk.Align.END)
        barra.append(self.info)

        # ============================================================
        # ÁREA DE PREVISUALIZACIÓN Y EMPTY STATE
        # ============================================================

        self.area_preview = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL
        )
        self.area_preview.set_hexpand(True)
        self.area_preview.set_vexpand(True)
        self.area_preview.set_halign(Gtk.Align.FILL)
        self.area_preview.set_valign(Gtk.Align.FILL)

        principal.append(self.area_preview)

        # Estado vacío (Empty State)
        self.caja_vacia = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14
        )
        self.caja_vacia.add_css_class("empty-state-card")
        self.caja_vacia.set_halign(Gtk.Align.CENTER)
        self.caja_vacia.set_valign(Gtk.Align.CENTER)
        self.caja_vacia.set_hexpand(True)
        self.caja_vacia.set_vexpand(True)

        icono_vacio = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
        icono_vacio.set_pixel_size(72)
        icono_vacio.add_css_class("empty-icon")
        self.caja_vacia.append(icono_vacio)

        lbl_vacio_tit = Gtk.Label(label="Arrastrá tus fotos acá")
        lbl_vacio_tit.add_css_class("empty-title")
        self.caja_vacia.append(lbl_vacio_tit)

        lbl_vacio_sub = Gtk.Label(label="o hacé clic abajo para abrir una imagen o carrusel")
        lbl_vacio_sub.add_css_class("empty-subtitle")
        self.caja_vacia.append(lbl_vacio_sub)

        btn_vacio_abrir = Gtk.Button()
        btn_vacio_abrir.add_css_class("btn-abrir")
        caja_btn_vacio = Gtk.Box(spacing=8)
        caja_btn_vacio.append(Gtk.Image.new_from_icon_name("document-open-symbolic"))
        caja_btn_vacio.append(Gtk.Label(label="Elegir fotos..."))
        btn_vacio_abrir.set_child(caja_btn_vacio)
        btn_vacio_abrir.connect("clicked", self.abrir_imagen)
        self.caja_vacia.append(btn_vacio_abrir)

        caja_pills = Gtk.Box(spacing=6)
        caja_pills.set_halign(Gtk.Align.CENTER)
        for fmt in ("JPG", "PNG", "WEBP"):
            p = Gtk.Label(label=fmt)
            p.add_css_class("format-pill")
            caja_pills.append(p)
        self.caja_vacia.append(caja_pills)

        self.area_preview.append(self.caja_vacia)

        # Lienzo (inicialmente oculto hasta cargar imagen)
        self.marco = Gtk.AspectFrame(
            xalign=0.5,
            yalign=0.5,
            ratio=1.0,
            obey_child=False
        )
        self.marco.add_css_class("canvas-frame")
        self.marco.set_halign(Gtk.Align.CENTER)
        self.marco.set_valign(Gtk.Align.CENTER)
        self.marco.set_visible(False)

        self.area_preview.append(self.marco)

        self.imagen = Gtk.Picture()
        self.imagen.set_can_shrink(True)
        self.imagen.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.imagen.set_hexpand(True)
        self.imagen.set_vexpand(True)

        self.marco.set_child(self.imagen)

        self.gesto_arrastre = Gtk.GestureDrag()
        self.gesto_arrastre.connect("drag-begin", self.arrastre_iniciado)
        self.gesto_arrastre.connect("drag-update", self.arrastre_actualizado)
        self.gesto_arrastre.connect("drag-end", self.arrastre_terminado)
        self.imagen.add_controller(self.gesto_arrastre)

        self.area_preview.connect("notify::width", self.recalcular_lienzo)
        self.area_preview.connect("notify::height", self.recalcular_lienzo)

        # ============================================================
        # TIRA DE MINIATURAS (MODO CARRUSEL)
        # ============================================================

        self.scroll_carrusel = Gtk.ScrolledWindow()
        self.scroll_carrusel.add_css_class("carrusel-strip")
        self.scroll_carrusel.set_policy(
            Gtk.PolicyType.AUTOMATIC,
            Gtk.PolicyType.NEVER
        )
        self.scroll_carrusel.set_size_request(-1, 115)
        self.scroll_carrusel.set_visible(False)

        self.caja_tira = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8
        )
        self.caja_tira.set_margin_start(12)
        self.caja_tira.set_margin_end(12)
        self.caja_tira.set_margin_top(6)
        self.caja_tira.set_margin_bottom(6)

        self.scroll_carrusel.set_child(self.caja_tira)
        principal.append(self.scroll_carrusel)

        # ============================================================
        # DOCK INFERIOR (TARJETAS DE CONTROL)
        # ============================================================

        dock_inferior = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8
        )
        principal.append(dock_inferior)

        # ------------------------------------------------------------
        # TARJETA 1: MODO Y COMPOSICIÓN
        # ------------------------------------------------------------
        dock_modo = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=14
        )
        dock_modo.add_css_class("card-dock")
        dock_inferior.append(dock_modo)

        lbl_modo = Gtk.Label(label="Modo:")
        lbl_modo.add_css_class("dock-label")
        dock_modo.append(lbl_modo)

        caja_seg = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        caja_seg.add_css_class("segmented-box")
        caja_seg.add_css_class("linked")

        self.modo_blur = Gtk.ToggleButton(label="Ajustar + Blur")
        self.modo_recortar = Gtk.ToggleButton(label="Recortar")
        self.modo_retrato = Gtk.ToggleButton(label="Modo Retrato")
        self.modo_recortar.set_group(self.modo_blur)
        self.modo_retrato.set_group(self.modo_blur)
        self.modo_blur.set_active(True)

        self.modo_blur.connect("toggled", self.modo_cambiado)
        self.modo_recortar.connect("toggled", self.modo_cambiado)
        self.modo_retrato.connect("toggled", self.modo_cambiado)

        caja_seg.append(self.modo_blur)
        caja_seg.append(self.modo_recortar)
        caja_seg.append(self.modo_retrato)
        dock_modo.append(caja_seg)

        # Indicador IA (spinner y badge para detección en segundo plano)
        self.spinner_ia = Gtk.Spinner()
        self.spinner_ia.set_visible(False)
        self.lbl_estado_ia = Gtk.Label(label="")
        self.lbl_estado_ia.add_css_class("badge-ia")
        self.lbl_estado_ia.set_visible(False)
        dock_modo.append(self.spinner_ia)
        dock_modo.append(self.lbl_estado_ia)

        sep_dm1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        dock_modo.append(sep_dm1)

        lbl_blur = Gtk.Label(label="Blur:")
        lbl_blur.add_css_class("dock-label")
        dock_modo.append(lbl_blur)

        self.blur_valor = 50
        self.blur_ajuste = Gtk.Adjustment(value=50, lower=0, upper=100, step_increment=1, page_increment=10, page_size=0)
        self.blur_slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.blur_ajuste)
        self.blur_slider.set_size_request(160, -1)
        self.blur_slider.set_draw_value(True)
        self.blur_slider.set_digits(0)
        self.blur_slider.connect("value-changed", self.blur_cambiado)
        gesto_blur = Gtk.GestureDrag()
        gesto_blur.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesto_blur.connect("drag-begin", self._slider_drag_begin)
        gesto_blur.connect("drag-end", self._slider_drag_end)
        self.blur_slider.add_controller(gesto_blur)
        dock_modo.append(self.blur_slider)

        sep_dm2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        dock_modo.append(sep_dm2)

        self.zoom_label = Gtk.Label(label="Zoom:")
        self.zoom_label.add_css_class("dock-label")
        self.zoom_ajuste = Gtk.Adjustment(value=100, lower=100, upper=300, step_increment=1, page_increment=10, page_size=0)
        self.zoom_slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.zoom_ajuste)
        self.zoom_slider.set_size_request(160, -1)
        self.zoom_slider.set_draw_value(True)
        self.zoom_slider.set_digits(0)
        self.zoom_slider.connect("value-changed", self.zoom_cambiado)
        gesto_zoom = Gtk.GestureDrag()
        gesto_zoom.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesto_zoom.connect("drag-begin", self._slider_drag_begin)
        gesto_zoom.connect("drag-end", self._slider_drag_end)
        self.zoom_slider.add_controller(gesto_zoom)

        self.boton_centrar = Gtk.Button(label="Centrar")
        self.boton_centrar.connect("clicked", self.centrar_recorte)

        self.zoom_label.set_sensitive(False)
        self.zoom_slider.set_sensitive(False)
        self.boton_centrar.set_sensitive(False)

        dock_modo.append(self.zoom_label)
        dock_modo.append(self.zoom_slider)
        dock_modo.append(self.boton_centrar)

        espacio_modo = Gtk.Box()
        espacio_modo.set_hexpand(True)
        dock_modo.append(espacio_modo)

        self.boton_exportar = Gtk.Button(label="Exportar")
        self.boton_exportar.add_css_class("btn-exportar-principal")
        self.boton_exportar.set_sensitive(False)
        self.boton_exportar.connect("clicked", self.exportar_click)
        dock_modo.append(self.boton_exportar)

        # ------------------------------------------------------------
        # TARJETA 2: RETOQUE Y COLOR
        # ------------------------------------------------------------
        dock_retoque = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=14
        )
        dock_retoque.add_css_class("card-dock")
        dock_inferior.append(dock_retoque)

        lbl_retoque = Gtk.Label(label="Retoque:")
        lbl_retoque.add_css_class("dock-label")
        dock_retoque.append(lbl_retoque)

        self.selector_presets = Gtk.DropDown.new_from_strings(
            list(PRESETS_RETOQUE.keys())
        )
        self.selector_presets.set_selected(0)
        self.selector_presets.set_sensitive(False)
        self.selector_presets.set_tooltip_text("Estilos y filtros de retoque rápido")
        self.selector_presets.connect("notify::selected", self.preset_cambiado)
        dock_retoque.append(self.selector_presets)

        sep_dr1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        dock_retoque.append(sep_dr1)

        # Brillo
        lbl_b = Gtk.Label(label="Brillo:")
        lbl_b.add_css_class("dock-label")
        dock_retoque.append(lbl_b)
        self.brillo_ajuste = Gtk.Adjustment(value=0, lower=-100, upper=100, step_increment=1, page_increment=10, page_size=0)
        self.brillo_slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.brillo_ajuste)
        self.brillo_slider.set_size_request(130, -1)
        self.brillo_slider.set_draw_value(True)
        self.brillo_slider.set_digits(0)
        self.brillo_slider.connect("value-changed", self.brillo_cambiado)
        dock_retoque.append(self.brillo_slider)

        # Contraste
        lbl_c = Gtk.Label(label="Contraste:")
        lbl_c.add_css_class("dock-label")
        dock_retoque.append(lbl_c)
        self.contraste_ajuste = Gtk.Adjustment(value=0, lower=-100, upper=100, step_increment=1, page_increment=10, page_size=0)
        self.contraste_slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.contraste_ajuste)
        self.contraste_slider.set_size_request(130, -1)
        self.contraste_slider.set_draw_value(True)
        self.contraste_slider.set_digits(0)
        self.contraste_slider.connect("value-changed", self.contraste_cambiado)
        dock_retoque.append(self.contraste_slider)

        # Saturación
        lbl_s = Gtk.Label(label="Saturación:")
        lbl_s.add_css_class("dock-label")
        dock_retoque.append(lbl_s)
        self.saturacion_ajuste = Gtk.Adjustment(value=0, lower=-100, upper=100, step_increment=1, page_increment=10, page_size=0)
        self.saturacion_slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.saturacion_ajuste)
        self.saturacion_slider.set_size_request(130, -1)
        self.saturacion_slider.set_draw_value(True)
        self.saturacion_slider.set_digits(0)
        self.saturacion_slider.connect("value-changed", self.saturacion_cambiado)
        dock_retoque.append(self.saturacion_slider)

        # Gestos de arrastre
        for s in (self.brillo_slider, self.contraste_slider, self.saturacion_slider):
            gesto = Gtk.GestureDrag()
            gesto.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            gesto.connect("drag-begin", self._slider_drag_begin)
            gesto.connect("drag-end", self._slider_drag_end)
            s.add_controller(gesto)

        espacio_retoque = Gtk.Box()
        espacio_retoque.set_hexpand(True)
        dock_retoque.append(espacio_retoque)

        self.boton_reset_ajustes = Gtk.Button(label="Reiniciar retoques")
        self.boton_reset_ajustes.set_tooltip_text("Restablecer brillo, contraste y saturación a 0")
        self.boton_reset_ajustes.set_sensitive(False)
        self.boton_reset_ajustes.connect("clicked", self.reiniciar_ajustes_color)
        dock_retoque.append(self.boton_reset_ajustes)

        # ============================================================
        # ATAJOS DE TECLADO Y ACCIONES (DESHACER / REHACER)
        # ============================================================

        self.accion_deshacer = Gio.SimpleAction.new("deshacer", None)
        self.accion_deshacer.connect("activate", lambda a, p: self.deshacer())
        self.accion_deshacer.set_enabled(False)
        self.add_action(self.accion_deshacer)

        self.accion_rehacer = Gio.SimpleAction.new("rehacer", None)
        self.accion_rehacer.connect("activate", lambda a, p: self.rehacer())
        self.accion_rehacer.set_enabled(False)
        self.add_action(self.accion_rehacer)

        app.set_accels_for_action("win.deshacer", ["<Control>z"])
        app.set_accels_for_action("win.rehacer", ["<Control><Shift>z", "<Control>y"])

        controlador_teclado = Gtk.EventControllerKey()
        controlador_teclado.connect("key-pressed", self.tecla_presionada)
        controlador_teclado.connect("key-released", self.tecla_soltada)
        self.add_controller(controlador_teclado)

    # ================================================================
    # ABRIR IMAGEN
    # ================================================================

    # ================================================================
    # ABRIR IMAGEN / CARRUSEL
    # ================================================================

    def abrir_imagen(self, boton):

        dialogo = Gtk.FileDialog()
        dialogo.set_title("Abrir imagen o carrusel")

        filtro = Gtk.FileFilter()
        filtro.set_name("Imágenes")

        filtro.add_mime_type("image/jpeg")
        filtro.add_mime_type("image/png")
        filtro.add_mime_type("image/webp")

        filtros = Gio.ListStore.new(
            Gtk.FileFilter
        )

        filtros.append(filtro)

        dialogo.set_filters(filtros)
        dialogo.set_default_filter(filtro)

        dialogo.open_multiple(
            self,
            None,
            self.imagenes_seleccionadas
        )

    def imagenes_seleccionadas(
        self,
        dialogo,
        resultado
    ):

        try:
            lista_archivos = dialogo.open_multiple_finish(
                resultado
            )

            n = lista_archivos.get_n_items()
            rutas = [
                lista_archivos.get_item(i).get_path()
                for i in range(n)
                if lista_archivos.get_item(i).get_path()
            ]

            if rutas:
                self.cargar_carrusel(rutas)

        except GLib.Error:
            pass

        except Exception as e:
            print(
                "Error seleccionando imágenes:",
                e
            )

    def agregar_fotos_carrusel(self, boton=None):

        dialogo = Gtk.FileDialog()
        dialogo.set_title("Agregar fotos al carrusel")

        filtro = Gtk.FileFilter()
        filtro.set_name("Imágenes")

        filtro.add_mime_type("image/jpeg")
        filtro.add_mime_type("image/png")
        filtro.add_mime_type("image/webp")

        filtros = Gio.ListStore.new(Gtk.FileFilter)
        filtros.append(filtro)

        dialogo.set_filters(filtros)
        dialogo.set_default_filter(filtro)

        dialogo.open_multiple(
            self,
            None,
            self.fotos_para_agregar_seleccionadas
        )

    def fotos_para_agregar_seleccionadas(self, dialogo, resultado):

        try:
            lista_archivos = dialogo.open_multiple_finish(resultado)
            n = lista_archivos.get_n_items()
            rutas = [
                lista_archivos.get_item(i).get_path()
                for i in range(n)
                if lista_archivos.get_item(i).get_path()
            ]

            if rutas:
                for r in rutas:
                    self.carrusel.append(ItemCarrusel(r))
                self.actualizar_interfaz_carrusel()

        except GLib.Error:
            pass

        except Exception as e:
            print("Error agregando fotos al carrusel:", e)

    # ================================================================
    # GESTIÓN DEL CARRUSEL
    # ================================================================

    def cargar_imagen(self, ruta):
        self.cargar_carrusel([ruta])

    def cargar_carrusel(self, rutas):
        if not rutas:
            return

        items = []
        for r in rutas:
            if os.path.isfile(r):
                items.append(ItemCarrusel(r))

        if not items:
            return

        self.carrusel = items
        self.indice_activo = 0

        # Reiniciar ajustes de color a valores por defecto (0)
        self._bloquear_registro = True
        try:
            self.brillo_ajuste.set_value(0)
            self.contraste_ajuste.set_value(0)
            self.saturacion_ajuste.set_value(0)
            self.brillo_valor = 0.0
            self.contraste_valor = 0.0
            self.saturacion_valor = 0.0
            if hasattr(self, "selector_presets"):
                self.selector_presets.set_selected(0)
        finally:
            self._bloquear_registro = False

        self.carrusel[0].cargar_en_ventana(self)

        ruta_primera = self.carrusel[0].ruta
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(ruta_primera)
            ancho = pixbuf.get_width()
            alto = pixbuf.get_height()
            self.info.set_text(f"Original: {ancho} × {alto} px")
        except Exception:
            pass

        self.generar_preview()
        self.boton_comparar.set_active(False)
        self.generar_preview_original()

        if hasattr(self, "caja_vacia"):
            self.caja_vacia.set_visible(False)
        if hasattr(self, "marco"):
            self.marco.set_visible(True)

        if len(self.carrusel) > 1:
            self.set_title(
                f"EffectPic — Carrusel [1/{len(self.carrusel)}] — {self.carrusel[0].nombre}"
            )
        else:
            self.set_title(f"EffectPic — {self.carrusel[0].nombre}")

        self.boton_exportar.set_sensitive(True)
        self.actualizar_sensibilidad_undo_redo()
        self.actualizar_interfaz_carrusel()

    def _archivos_soltados(self, target, value, x, y):
        if isinstance(value, Gdk.FileList):
            archivos = value.get_files()
            rutas = [f.get_path() for f in archivos if f.get_path()]
            rutas_validas = [
                r for r in rutas
                if os.path.isfile(r) and r.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
            ]
            if rutas_validas:
                self.cargar_carrusel(rutas_validas)
                return True
        return False

    def seleccionar_item_carrusel(self, nuevo_indice):
        if nuevo_indice == self.indice_activo or not (0 <= nuevo_indice < len(self.carrusel)):
            return

        # Sincronizamos la foto actual antes de cambiar
        if self.carrusel and 0 <= self.indice_activo < len(self.carrusel):
            self.carrusel[self.indice_activo].guardar_desde_ventana(self)

        self.indice_activo = nuevo_indice
        self.carrusel[nuevo_indice].cargar_en_ventana(self)

        ruta_act = self.carrusel[nuevo_indice].ruta
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(ruta_act)
            ancho = pixbuf.get_width()
            alto = pixbuf.get_height()
            self.info.set_text(f"Original: {ancho} × {alto} px")
        except Exception:
            pass

        # Gestión del estado de IA al cambiar de foto
        if hasattr(self, "modo_retrato") and self.modo_retrato.get_active():
            if self.carrusel[nuevo_indice].mascara_sujeto is None:
                self.iniciar_deteccion_sujeto(self.carrusel[nuevo_indice])
            else:
                self.spinner_ia.stop()
                self.spinner_ia.set_visible(False)
                self.lbl_estado_ia.remove_css_class("badge-ia")
                self.lbl_estado_ia.add_css_class("badge-ia-ready")
                self.lbl_estado_ia.set_text("IA lista")
                self.lbl_estado_ia.set_visible(True)
        elif hasattr(self, "spinner_ia"):
            self.spinner_ia.stop()
            self.spinner_ia.set_visible(False)
            self.lbl_estado_ia.set_visible(False)

        self.generar_preview()
        self.boton_comparar.set_active(False)
        self.generar_preview_original()
        self.actualizar_sensibilidad_undo_redo()
        self.actualizar_interfaz_carrusel()

        if hasattr(self, "selector_presets"):
            preset_encontrado = 0
            for p_idx, (p_nom, p_vals) in enumerate(PRESETS_RETOQUE.items()):
                if p_idx > 0 and (round(self.brillo_valor), round(self.contraste_valor), round(self.saturacion_valor)) == p_vals:
                    preset_encontrado = p_idx
                    break
            self._bloquear_registro = True
            try:
                self.selector_presets.set_selected(preset_encontrado)
            finally:
                self._bloquear_registro = False

        self.set_title(
            f"EffectPic — Carrusel [{nuevo_indice+1}/{len(self.carrusel)}] — {self.carrusel[nuevo_indice].nombre}"
        )

    def mover_item_carrusel(self, indice, delta):
        nuevo_indice = indice + delta
        if 0 <= nuevo_indice < len(self.carrusel):
            if self.carrusel and 0 <= self.indice_activo < len(self.carrusel):
                self.carrusel[self.indice_activo].guardar_desde_ventana(self)

            self.carrusel[indice], self.carrusel[nuevo_indice] = (
                self.carrusel[nuevo_indice],
                self.carrusel[indice]
            )

            if self.indice_activo == indice:
                self.indice_activo = nuevo_indice
            elif self.indice_activo == nuevo_indice:
                self.indice_activo = indice

            self.actualizar_interfaz_carrusel()

    def eliminar_item_carrusel(self, indice):
        if not (0 <= indice < len(self.carrusel)):
            return

        if indice == self.indice_activo:
            self.carrusel.pop(indice)
            if not self.carrusel:
                self.ruta_actual = None
                self.scroll_carrusel.set_visible(False)
                if hasattr(self, "caja_vacia"):
                    self.caja_vacia.set_visible(True)
                if hasattr(self, "marco"):
                    self.marco.set_visible(False)
                self.info.set_text("Ninguna imagen abierta")
                self.set_title("EffectPic")
                self.boton_exportar.set_sensitive(False)
                self.boton_exportar.set_label("Exportar")
                self.imagen.set_filename(None)
                self.actualizar_sensibilidad_undo_redo()
                return
            else:
                self.indice_activo = max(0, min(indice, len(self.carrusel) - 1))
                self.carrusel[self.indice_activo].cargar_en_ventana(self)
                self.generar_preview()
                self.generar_preview_original()
        else:
            self.carrusel.pop(indice)
            if self.indice_activo > indice:
                self.indice_activo -= 1

        self.actualizar_interfaz_carrusel()

    def copiar_estilo_a_todas(self, boton=None):
        if len(self.carrusel) <= 1:
            return

        item_activo = self.carrusel[self.indice_activo]
        item_activo.guardar_desde_ventana(self)

        for i, item in enumerate(self.carrusel):
            if i != self.indice_activo:
                item.modo = item_activo.modo
                item.blur_valor = item_activo.blur_valor
                item.brillo = item_activo.brillo
                item.contraste = item_activo.contraste
                item.saturacion = item_activo.saturacion

                if item.estado_actual:
                    item.historial_deshacer.append(copy.deepcopy(item.estado_actual))
                    nuevo = copy.deepcopy(item.estado_actual)
                    nuevo["modo"] = item.modo
                    nuevo["blur_valor"] = item.blur_valor
                    nuevo["brillo"] = item.brillo
                    nuevo["contraste"] = item.contraste
                    nuevo["saturacion"] = item.saturacion
                    item.estado_actual = nuevo
                    item.historial_rehacer.clear()

        dialogo = Gtk.AlertDialog()
        dialogo.set_message("Estilo aplicado al carrusel")
        dialogo.set_detail(
            f"Se sincronizó el modo ({item_activo.modo}), blur y retoques en las {len(self.carrusel)} fotos."
        )
        dialogo.set_buttons(["Aceptar"])
        dialogo.show(self)

    def actualizar_interfaz_carrusel(self):
        while child := self.caja_tira.get_first_child():
            self.caja_tira.remove(child)

        total = len(self.carrusel)
        if total <= 1:
            self.scroll_carrusel.set_visible(False)
            if total == 1:
                self.boton_exportar.set_label("Exportar")
                self.boton_exportar.set_sensitive(True)
            return

        self.scroll_carrusel.set_visible(True)
        self.boton_exportar.set_label(f"Exportar carrusel ({total})")
        self.boton_exportar.set_sensitive(True)

        for i, item in enumerate(self.carrusel):
            tarjeta = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=4
            )
            tarjeta.add_css_class("carrusel-card")
            if i == self.indice_activo:
                tarjeta.add_css_class("carrusel-card-active")
            tarjeta.set_margin_start(4)
            tarjeta.set_margin_end(4)

            cabecera = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=2
            )

            lbl_num = Gtk.Label(label=f"#{i+1}")
            lbl_num.set_hexpand(True)
            lbl_num.set_halign(Gtk.Align.START)
            cabecera.append(lbl_num)

            if i > 0:
                btn_izq = Gtk.Button(label="◀")
                btn_izq.add_css_class("flat")
                btn_izq.set_tooltip_text("Mover foto a la izquierda")
                btn_izq.connect(
                    "clicked",
                    lambda b, idx=i: self.mover_item_carrusel(idx, -1)
                )
                cabecera.append(btn_izq)

            if i < total - 1:
                btn_der = Gtk.Button(label="▶")
                btn_der.add_css_class("flat")
                btn_der.set_tooltip_text("Mover foto a la derecha")
                btn_der.connect(
                    "clicked",
                    lambda b, idx=i: self.mover_item_carrusel(idx, 1)
                )
                cabecera.append(btn_der)

            btn_del = Gtk.Button(label="✕")
            btn_del.add_css_class("flat")
            btn_del.set_tooltip_text("Eliminar foto del carrusel")
            btn_del.connect(
                "clicked",
                lambda b, idx=i: self.eliminar_item_carrusel(idx)
            )
            cabecera.append(btn_del)

            tarjeta.append(cabecera)

            btn_img = Gtk.Button()
            btn_img.set_tooltip_text(f"Foto {i+1}: {item.nombre}")

            if item.miniatura_texture:
                pic = Gtk.Picture.new_for_paintable(item.miniatura_texture)
                pic.set_size_request(68, 68)
                pic.set_content_fit(Gtk.ContentFit.CONTAIN)
                btn_img.set_child(pic)
            else:
                btn_img.set_label(f"Foto {i+1}")

            if i == self.indice_activo:
                btn_img.add_css_class("suggested-action")

            btn_img.connect(
                "clicked",
                lambda b, idx=i: self.seleccionar_item_carrusel(idx)
            )
            tarjeta.append(btn_img)

            self.caja_tira.append(tarjeta)

        # Acciones globales de la tira
        caja_acciones = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6
        )
        caja_acciones.set_valign(Gtk.Align.CENTER)
        caja_acciones.set_margin_start(10)
        caja_acciones.set_margin_end(10)

        btn_mas = Gtk.Button(label="+ Agregar")
        btn_mas.set_tooltip_text("Añadir más fotos a este carrusel")
        btn_mas.connect("clicked", self.agregar_fotos_carrusel)
        caja_acciones.append(btn_mas)

        btn_copiar = Gtk.Button(label="Copiar estilo")
        btn_copiar.set_tooltip_text(
            "Copiar modo, blur y retoques de la foto activa a todas"
        )
        btn_copiar.connect("clicked", self.copiar_estilo_a_todas)
        caja_acciones.append(btn_copiar)

        self.caja_tira.append(caja_acciones)

    # ================================================================
    # FORMATO
    # ================================================================

    def obtener_formato_actual(self):

        indice = self.selector.get_selected()

        nombres = list(FORMATOS.keys())

        if indice >= len(nombres):
            return nombres[0], FORMATOS[nombres[0]]

        nombre = nombres[indice]

        return nombre, FORMATOS[nombre]

    def formato_cambiado(
        self,
        selector,
        parametro
    ):

        self.recalcular_lienzo()

        if self.ruta_actual:
            self.generar_preview()
            self.generar_preview_original()

        self.registrar_cambio()

    # ================================================================
    # TAMAÑO VISUAL DEL LIENZO
    # ================================================================

    def recalcular_lienzo(self, *args):

        ancho_disponible = self.area_preview.get_width()
        alto_disponible = self.area_preview.get_height()

        if ancho_disponible <= 0 or alto_disponible <= 0:
            return

        _, dimensiones = self.obtener_formato_actual()

        ancho_salida, alto_salida = dimensiones

        ratio = ancho_salida / alto_salida

        # AspectFrame se encargará de mantener
        # exactamente esta proporción.
        self.marco.set_ratio(ratio)

        # Tamaño máximo disponible para la preview.
        max_ancho = ancho_disponible - 30
        max_alto = alto_disponible - 30

        if max_ancho <= 0 or max_alto <= 0:
            return

        nuevo_ancho = max_ancho
        nuevo_alto = int(nuevo_ancho / ratio)

        if nuevo_alto > max_alto:
            nuevo_alto = max_alto
            nuevo_ancho = int(nuevo_alto * ratio)

        self.marco.set_size_request(
            nuevo_ancho,
            nuevo_alto
        )

        self.marco.set_hexpand(False)
        self.marco.set_vexpand(False)

    # ================================================================
    # CAMBIO DE MODO
    # ================================================================

    def modo_cambiado(self, boton):
        if not boton.get_active():
            return

        es_recorte = self.modo_recortar.get_active()
        es_retrato = self.modo_retrato.get_active()

        self.zoom_label.set_sensitive(es_recorte or es_retrato)
        self.zoom_slider.set_sensitive(es_recorte or es_retrato)
        self.boton_centrar.set_sensitive(es_recorte or es_retrato)

        self.blur_slider.set_sensitive(
            self.modo_blur.get_active() or es_retrato
        )

        if es_retrato and self.ruta_actual and self.carrusel and (0 <= self.indice_activo < len(self.carrusel)):
            item_actual = self.carrusel[self.indice_activo]
            if item_actual.mascara_sujeto is None:
                self.iniciar_deteccion_sujeto(item_actual)
            else:
                self.spinner_ia.stop()
                self.spinner_ia.set_visible(False)
                self.lbl_estado_ia.remove_css_class("badge-ia")
                self.lbl_estado_ia.add_css_class("badge-ia-ready")
                self.lbl_estado_ia.set_text("IA lista")
                self.lbl_estado_ia.set_visible(True)
        elif not es_retrato:
            self.spinner_ia.stop()
            self.spinner_ia.set_visible(False)
            self.lbl_estado_ia.set_visible(False)

        if self.ruta_actual:
            self.generar_preview()

        self.registrar_cambio()

    def iniciar_deteccion_sujeto(self, item):
        """
        Inicia la detección del sujeto en segundo plano con rembg (u2net en CPU).
        Incrementa el contador de secuencia para descartar resultados obsoletos
        si el usuario cambia de imagen durante la inferencia.
        """
        self._secuencia_deteccion += 1
        seq = self._secuencia_deteccion

        self.spinner_ia.start()
        self.spinner_ia.set_visible(True)
        self.lbl_estado_ia.remove_css_class("badge-ia-ready")
        self.lbl_estado_ia.add_css_class("badge-ia")
        self.lbl_estado_ia.set_text("IA detectando sujeto...")
        self.lbl_estado_ia.set_visible(True)

        hilo = threading.Thread(
            target=self._hilo_detectar_sujeto,
            args=(item, seq, item.ruta),
            daemon=True
        )
        hilo.start()

    def _hilo_detectar_sujeto(self, item, seq, ruta):
        try:
            import rembg
            session = obtener_sesion_rembg(modelo="u2net")
            with Image.open(ruta) as img:
                img = ImageOps.exif_transpose(img).convert("RGB")
                # only_mask=True produce máscara PIL en escala de grises modo 'L' (1 byte/px)
                mascara = rembg.remove(img, session=session, only_mask=True)
            GLib.idle_add(self._on_sujeto_detectado, item, mascara, seq)
        except Exception as e:
            GLib.idle_add(self._on_sujeto_error, item, str(e), seq)

    def _on_sujeto_detectado(self, item, mascara, seq):
        # 1. Guardamos la máscara en el item para reutilización
        item.mascara_sujeto = mascara

        # 2. Descartamos actualización de UI si el usuario cambió de foto
        # o si la secuencia ya no coincide con la última solicitada
        if not self.carrusel or not (0 <= self.indice_activo < len(self.carrusel)):
            return False
        if self.carrusel[self.indice_activo] is not item:
            return False
        if seq != self._secuencia_deteccion:
            return False

        self.spinner_ia.stop()
        self.spinner_ia.set_visible(False)
        self.lbl_estado_ia.remove_css_class("badge-ia")
        self.lbl_estado_ia.add_css_class("badge-ia-ready")
        self.lbl_estado_ia.set_text("IA lista")
        self.lbl_estado_ia.set_visible(True)

        if self.modo_retrato.get_active():
            self.generar_preview()

        return False

    def _on_sujeto_error(self, item, error_msg, seq):
        print(f"Error en detección de sujeto: {error_msg}")
        if seq == self._secuencia_deteccion:
            self.spinner_ia.stop()
            self.spinner_ia.set_visible(False)
            self.lbl_estado_ia.remove_css_class("badge-ia-ready")
            self.lbl_estado_ia.add_css_class("badge-ia")
            err_lower = error_msg.lower()
            if "rembg" in err_lower or "no module" in err_lower:
                self.lbl_estado_ia.set_text("Instalar rembg")
                self.lbl_estado_ia.set_tooltip_text("Falta rembg. Ejecuta ./run_effectpic.sh para configurar el entorno.")
            elif "download" in err_lower or "connection" in err_lower or "network" in err_lower:
                self.lbl_estado_ia.set_text("Sin conexión")
                self.lbl_estado_ia.set_tooltip_text("No se pudo descargar el modelo en primer uso. Las funciones normales siguen disponibles.")
            else:
                self.lbl_estado_ia.set_text("Error IA")
                self.lbl_estado_ia.set_tooltip_text(f"Error recuperable: {error_msg}. Las funciones normales siguen disponibles.")
            self.lbl_estado_ia.set_visible(True)
        return False

    def zoom_cambiado(self, slider):

        self.zoom_recorte = (
            slider.get_value() / 100.0
        )

        if (
            self.ruta_actual
            and (self.modo_recortar.get_active() or self.modo_retrato.get_active())
        ):
            self.generar_preview()

        if self._bloquear_registro or not self.ruta_actual:
            return

        if not self._arrastrando_slider:
            if self._timer_slider is not None:
                GLib.source_remove(self._timer_slider)
            self._timer_slider = GLib.timeout_add(300, self._finalizar_cambio_slider)

    def centrar_recorte(self, boton=None):

        self.offset_x = 0.0
        self.offset_y = 0.0
        self.zoom_ajuste.set_value(100)
        self.zoom_recorte = 1.0

        if (
            self.ruta_actual
            and (self.modo_recortar.get_active() or self.modo_retrato.get_active())
        ):
            self.generar_preview()

        self.registrar_cambio()

    def arrastre_iniciado(
        self,
        gesto,
        x,
        y
    ):

        if not (self.modo_recortar.get_active() or self.modo_retrato.get_active()):
            return

        self.drag_offset_x = self.offset_x
        self.drag_offset_y = self.offset_y

    def arrastre_actualizado(
        self,
        gesto,
        desplazamiento_x,
        desplazamiento_y
    ):

        if not (self.modo_recortar.get_active() or self.modo_retrato.get_active()):
            return

        ancho = self.imagen.get_width()
        alto = self.imagen.get_height()

        if ancho <= 0 or alto <= 0:
            return

        # Arrastramos la FOTO, no la ventana de recorte.
        nuevo_x = (
            self.drag_offset_x
            - (desplazamiento_x / ancho) * 2
        )

        nuevo_y = (
            self.drag_offset_y
            - (desplazamiento_y / alto) * 2
        )

        self.offset_x = max(-1.0, min(1.0, nuevo_x))
        self.offset_y = max(-1.0, min(1.0, nuevo_y))

        self.generar_preview()

    def arrastre_terminado(
        self,
        gesto,
        offset_x,
        offset_y
    ):

        if not (self.modo_recortar.get_active() or self.modo_retrato.get_active()):
            return

        self.registrar_cambio()

    def blur_cambiado(self, slider):

        self.blur_valor = slider.get_value()

        if (
            self.ruta_actual
            and (self.modo_blur.get_active() or self.modo_retrato.get_active())
        ):
            self.generar_preview()

        if self._bloquear_registro or not self.ruta_actual:
            return

        if not self._arrastrando_slider:
            if self._timer_slider is not None:
                GLib.source_remove(self._timer_slider)
            self._timer_slider = GLib.timeout_add(300, self._finalizar_cambio_slider)

    def brillo_cambiado(self, slider):

        self.brillo_valor = slider.get_value()

        if not self._bloquear_registro and hasattr(self, "selector_presets"):
            if self.selector_presets.get_selected() != 0:
                self._bloquear_registro = True
                try:
                    self.selector_presets.set_selected(0)
                finally:
                    self._bloquear_registro = False

        if self.ruta_actual:
            self.generar_preview()

        if self._bloquear_registro or not self.ruta_actual:
            return

        if not self._arrastrando_slider:
            if self._timer_slider is not None:
                GLib.source_remove(self._timer_slider)
            self._timer_slider = GLib.timeout_add(300, self._finalizar_cambio_slider)

    def contraste_cambiado(self, slider):

        self.contraste_valor = slider.get_value()

        if not self._bloquear_registro and hasattr(self, "selector_presets"):
            if self.selector_presets.get_selected() != 0:
                self._bloquear_registro = True
                try:
                    self.selector_presets.set_selected(0)
                finally:
                    self._bloquear_registro = False

        if self.ruta_actual:
            self.generar_preview()

        if self._bloquear_registro or not self.ruta_actual:
            return

        if not self._arrastrando_slider:
            if self._timer_slider is not None:
                GLib.source_remove(self._timer_slider)
            self._timer_slider = GLib.timeout_add(300, self._finalizar_cambio_slider)

    def saturacion_cambiado(self, slider):

        self.saturacion_valor = slider.get_value()

        if not self._bloquear_registro and hasattr(self, "selector_presets"):
            if self.selector_presets.get_selected() != 0:
                self._bloquear_registro = True
                try:
                    self.selector_presets.set_selected(0)
                finally:
                    self._bloquear_registro = False

        if self.ruta_actual:
            self.generar_preview()

        if self._bloquear_registro or not self.ruta_actual:
            return

        if not self._arrastrando_slider:
            if self._timer_slider is not None:
                GLib.source_remove(self._timer_slider)
            self._timer_slider = GLib.timeout_add(300, self._finalizar_cambio_slider)

    def preset_cambiado(self, selector, parametro):

        if self._bloquear_registro or not self.ruta_actual:
            return

        idx = selector.get_selected()
        nombres = list(PRESETS_RETOQUE.keys())
        if not (0 <= idx < len(nombres)):
            return

        nombre = nombres[idx]
        if nombre == "— Presets —":
            return

        brillo, contraste, saturacion = PRESETS_RETOQUE[nombre]

        self._bloquear_registro = True
        try:
            self.brillo_ajuste.set_value(brillo)
            self.contraste_ajuste.set_value(contraste)
            self.saturacion_ajuste.set_value(saturacion)
            self.brillo_valor = float(brillo)
            self.contraste_valor = float(contraste)
            self.saturacion_valor = float(saturacion)
        finally:
            self._bloquear_registro = False

        if self.ruta_actual:
            self.generar_preview()

        self.registrar_cambio()

    def reiniciar_ajustes_color(self, boton=None):

        if self.brillo_valor == 0 and self.contraste_valor == 0 and self.saturacion_valor == 0:
            return

        self._bloquear_registro = True
        try:
            self.brillo_ajuste.set_value(0)
            self.contraste_ajuste.set_value(0)
            self.saturacion_ajuste.set_value(0)
            self.brillo_valor = 0.0
            self.contraste_valor = 0.0
            self.saturacion_valor = 0.0
            if hasattr(self, "selector_presets"):
                self.selector_presets.set_selected(0)
        finally:
            self._bloquear_registro = False

        if self.ruta_actual:
            self.generar_preview()

        self.registrar_cambio()

    def _slider_drag_begin(self, gesto, x, y):
        self._arrastrando_slider = True
        if self._timer_slider is not None:
            GLib.source_remove(self._timer_slider)
            self._timer_slider = None

    def _slider_drag_end(self, gesto, x, y):
        self._arrastrando_slider = False
        self.registrar_cambio()

    def _finalizar_cambio_slider(self):
        self._timer_slider = None
        if not self._arrastrando_slider:
            self.registrar_cambio()
        return False

    # ================================================================
    # GESTIÓN DE HISTORIAL (DESHACER / REHACER)
    # ================================================================

    def obtener_estado_actual(self):
        if self.modo_retrato.get_active():
            modo = "retrato"
        elif self.modo_recortar.get_active():
            modo = "recortar"
        else:
            modo = "blur"

        return {
            "formato_idx": self.selector.get_selected(),
            "modo": modo,
            "blur_valor": round(float(self.blur_ajuste.get_value()), 2),
            "zoom": round(float(self.zoom_ajuste.get_value()), 2),
            "offset_x": round(float(self.offset_x), 4),
            "offset_y": round(float(self.offset_y), 4),
            "brillo": round(float(self.brillo_ajuste.get_value()), 2),
            "contraste": round(float(self.contraste_ajuste.get_value()), 2),
            "saturacion": round(float(self.saturacion_ajuste.get_value()), 2),
        }

    def registrar_cambio(self):
        if self._bloquear_registro or not self.ruta_actual:
            return

        if self._timer_slider is not None:
            GLib.source_remove(self._timer_slider)
            self._timer_slider = None

        nuevo_estado = self.obtener_estado_actual()

        # Si no hubo cambio real de valores, no agregamos paso
        if self.estado_actual is not None and nuevo_estado == self.estado_actual:
            return

        if self.estado_actual is not None:
            self.historial_deshacer.append(copy.deepcopy(self.estado_actual))

        self.estado_actual = copy.deepcopy(nuevo_estado)
        # Descartar rama de rehacer tras un nuevo cambio
        self.historial_rehacer.clear()
        self.actualizar_sensibilidad_undo_redo()

    def aplicar_estado(self, estado):
        self._bloquear_registro = True
        try:
            if self._timer_slider is not None:
                GLib.source_remove(self._timer_slider)
                self._timer_slider = None

            # 1. Formato
            if self.selector.get_selected() != estado["formato_idx"]:
                self.selector.set_selected(estado["formato_idx"])
                self.recalcular_lienzo()

            # 2. Modo
            modo = estado.get("modo", "blur")
            if modo == "recortar":
                if not self.modo_recortar.get_active():
                    self.modo_recortar.set_active(True)
            elif modo == "retrato":
                if not self.modo_retrato.get_active():
                    self.modo_retrato.set_active(True)
            else:
                if not self.modo_blur.get_active():
                    self.modo_blur.set_active(True)

            es_recorte = (modo == "recortar")
            es_retrato = (modo == "retrato")

            self.zoom_label.set_sensitive(es_recorte or es_retrato)
            self.zoom_slider.set_sensitive(es_recorte or es_retrato)
            self.boton_centrar.set_sensitive(es_recorte or es_retrato)
            self.blur_slider.set_sensitive(modo != "recortar")

            # 3. Blur
            self.blur_valor = estado["blur_valor"]
            self.blur_ajuste.set_value(estado["blur_valor"])

            # 4. Zoom y recorte
            self.zoom_recorte = estado["zoom"] / 100.0
            self.zoom_ajuste.set_value(estado["zoom"])
            self.offset_x = estado["offset_x"]
            self.offset_y = estado["offset_y"]

            # 5. Retoques de color
            self.brillo_valor = estado.get("brillo", 0.0)
            self.brillo_ajuste.set_value(self.brillo_valor)

            self.contraste_valor = estado.get("contraste", 0.0)
            self.contraste_ajuste.set_value(self.contraste_valor)

            self.saturacion_valor = estado.get("saturacion", 0.0)
            self.saturacion_ajuste.set_value(self.saturacion_valor)

            # 6. Previsualización
            if self.ruta_actual:
                self.generar_preview()

        finally:
            self._bloquear_registro = False

    def deshacer(self):
        if not self.historial_deshacer or not self.ruta_actual:
            return

        self.historial_rehacer.append(copy.deepcopy(self.estado_actual))
        estado_previo = self.historial_deshacer.pop()
        self.estado_actual = copy.deepcopy(estado_previo)
        self.aplicar_estado(estado_previo)
        self.actualizar_sensibilidad_undo_redo()

    def rehacer(self):
        if not self.historial_rehacer or not self.ruta_actual:
            return

        self.historial_deshacer.append(copy.deepcopy(self.estado_actual))
        estado_siguiente = self.historial_rehacer.pop()
        self.estado_actual = copy.deepcopy(estado_siguiente)
        self.aplicar_estado(estado_siguiente)
        self.actualizar_sensibilidad_undo_redo()

    def restaurar_original(self):
        if not self.ruta_actual or self.estado_inicial is None:
            return

        if self.obtener_estado_actual() == self.estado_inicial:
            return

        # Guardamos el estado actual en la pila de deshacer para que sea reversible con Ctrl+Z
        self.historial_deshacer.append(copy.deepcopy(self.estado_actual))
        self.historial_rehacer.clear()
        self.estado_actual = copy.deepcopy(self.estado_inicial)
        self.aplicar_estado(self.estado_inicial)
        self.actualizar_sensibilidad_undo_redo()

    def actualizar_sensibilidad_undo_redo(self):
        puede_deshacer = len(self.historial_deshacer) > 0 and self.ruta_actual is not None
        puede_rehacer = len(self.historial_rehacer) > 0 and self.ruta_actual is not None
        puede_restaurar = (
            self.ruta_actual is not None
            and self.estado_inicial is not None
            and self.obtener_estado_actual() != self.estado_inicial
        )
        hay_ajustes_color = (
            self.brillo_valor != 0
            or self.contraste_valor != 0
            or self.saturacion_valor != 0
        ) and self.ruta_actual is not None

        self.boton_deshacer.set_sensitive(puede_deshacer)
        self.boton_rehacer.set_sensitive(puede_rehacer)
        if hasattr(self, "boton_restaurar"):
            self.boton_restaurar.set_sensitive(puede_restaurar)
        if hasattr(self, "boton_reset_ajustes"):
            self.boton_reset_ajustes.set_sensitive(hay_ajustes_color)
        if hasattr(self, "boton_comparar"):
            self.boton_comparar.set_sensitive(self.ruta_actual is not None)
        if hasattr(self, "selector_presets"):
            self.selector_presets.set_sensitive(self.ruta_actual is not None)

        if hasattr(self, "accion_deshacer"):
            self.accion_deshacer.set_enabled(puede_deshacer)
        if hasattr(self, "accion_rehacer"):
            self.accion_rehacer.set_enabled(puede_rehacer)

        if self.carrusel and 0 <= self.indice_activo < len(self.carrusel):
            self.carrusel[self.indice_activo].guardar_desde_ventana(self)

    def tecla_presionada(self, controller, keyval, keycode, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if ctrl:
            if keyval in (Gdk.KEY_z, Gdk.KEY_Z):
                if shift:
                    self.rehacer()
                else:
                    self.deshacer()
                return True
            elif keyval in (Gdk.KEY_y, Gdk.KEY_Y):
                self.rehacer()
                return True

        # Comparar al mantener Espacio o barra invertida '\'
        if not ctrl and keyval in (Gdk.KEY_space, Gdk.KEY_backslash):
            if not self.tecla_comparar_activa and self.ruta_actual:
                self.tecla_comparar_activa = True
                self.mostrar_original()
                return True

        return False

    def tecla_soltada(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_space, Gdk.KEY_backslash):
            if self.tecla_comparar_activa:
                self.tecla_comparar_activa = False
                if hasattr(self, "boton_comparar") and self.boton_comparar.get_active():
                    self.mostrar_original()
                else:
                    self.mostrar_editada()
                return True
        return False

    # ================================================================
    # COMPARAR (ANTES Y DESPUÉS)
    # ================================================================

    def generar_preview_original(self):
        if not self.ruta_actual:
            return

        try:
            _, dimensiones = self.obtener_formato_actual()
            ancho_salida, alto_salida = dimensiones

            with Image.open(self.ruta_actual) as original:
                original = ImageOps.exif_transpose(original).convert("RGB")

                # Fondo neutro oscuro
                fondo = Image.new("RGB", (ancho_salida, alto_salida), (20, 20, 24))

                principal = ImageOps.contain(
                    original,
                    (ancho_salida, alto_salida),
                    method=Image.Resampling.LANCZOS
                )

                x = (ancho_salida - principal.width) // 2
                y = (alto_salida - principal.height) // 2
                fondo.paste(principal, (x, y))

            if self.preview_temporal_original:
                try:
                    os.remove(self.preview_temporal_original)
                except OSError:
                    pass

            fd, ruta_temporal = tempfile.mkstemp(
                suffix=".png",
                prefix="effectpic_orig_"
            )
            os.close(fd)
            fondo.save(ruta_temporal, "PNG")
            self.preview_temporal_original = ruta_temporal

        except Exception as e:
            print("Error generando preview original:", e)

    def mostrar_original(self):
        if not self.ruta_actual or not self.preview_temporal_original:
            return
        self.imagen.set_filename(self.preview_temporal_original)
        self.info.set_text("— ORIGINAL (Sin retoques) —")

    def mostrar_editada(self):
        if not self.ruta_actual or not self.preview_temporal:
            return
        self.imagen.set_filename(self.preview_temporal)
        _, dimensiones = self.obtener_formato_actual()
        self.info.set_text(f"Salida: {dimensiones[0]} × {dimensiones[1]} px")

    def comparar_toggled(self, boton):
        if boton.get_active():
            boton.set_label("Viendo Original")
            self.mostrar_original()
        else:
            boton.set_label("Comparar")
            self.mostrar_editada()

    # ================================================================
    # MOTOR EFFECTPIC
    # ================================================================

    def _aplicar_mejoras_valores(self, imagen, b, c, s):
        if b != 0:
            factor_b = max(0.0, 1.0 + (b / 100.0))
            imagen = ImageEnhance.Brightness(imagen).enhance(factor_b)

        if c != 0:
            factor_c = max(0.0, 1.0 + (c / 100.0))
            imagen = ImageEnhance.Contrast(imagen).enhance(factor_c)

        if s != 0:
            factor_s = max(0.0, 1.0 + (s / 100.0))
            imagen = ImageEnhance.Color(imagen).enhance(factor_s)

        return imagen

    def aplicar_mejoras(self, imagen):
        return self._aplicar_mejoras_valores(
            imagen,
            self.brillo_valor,
            self.contraste_valor,
            self.saturacion_valor
        )

    def generar_imagen_para_item(self, item, ancho_salida, alto_salida):
        if item.modo == "recortar":
            with Image.open(item.ruta) as original:
                original = ImageOps.exif_transpose(original).convert("RGB")
                original = self._aplicar_mejoras_valores(
                    original,
                    item.brillo,
                    item.contraste,
                    item.saturacion
                )

                ow, oh = original.size
                escala_base = max(ancho_salida / ow, alto_salida / oh)
                zoom_factor = max(1.0, item.zoom / 100.0)
                escala = escala_base * zoom_factor

                nuevo_ancho = max(ancho_salida, round(ow * escala))
                nuevo_alto = max(alto_salida, round(oh * escala))

                redimensionada = original.resize(
                    (nuevo_ancho, nuevo_alto),
                    resample=Image.Resampling.LANCZOS
                )

                sobrante_x = nuevo_ancho - ancho_salida
                sobrante_y = nuevo_alto - alto_salida

                x = int(sobrante_x * (item.offset_x + 1.0) / 2.0) if sobrante_x > 0 else 0
                y = int(sobrante_y * (item.offset_y + 1.0) / 2.0) if sobrante_y > 0 else 0

                x = max(0, min(sobrante_x, x))
                y = max(0, min(sobrante_y, y))

                return redimensionada.crop((x, y, x + ancho_salida, y + alto_salida))

        elif item.modo == "retrato":
            mascara = item.mascara_sujeto
            if mascara is None:
                try:
                    import rembg
                    session = obtener_sesion_rembg(modelo="u2net")
                    with Image.open(item.ruta) as img_orig:
                        img_orig = ImageOps.exif_transpose(img_orig).convert("RGB")
                        mascara = rembg.remove(img_orig, session=session, only_mask=True)
                        item.mascara_sujeto = mascara
                except Exception as e_ia:
                    print(f"Error calculando máscara IA para item {item.nombre}: {e_ia}")

            return self.generar_imagen_retrato(
                item.ruta,
                ancho_salida,
                alto_salida,
                mascara=mascara,
                blur_valor=item.blur_valor,
                zoom=item.zoom,
                offset_x=item.offset_x,
                offset_y=item.offset_y,
                brillo=item.brillo,
                contraste=item.contraste,
                saturacion=item.saturacion
            )

        else:  # "blur"
            with Image.open(item.ruta) as original:
                original = ImageOps.exif_transpose(original).convert("RGB")
                original = self._aplicar_mejoras_valores(
                    original,
                    item.brillo,
                    item.contraste,
                    item.saturacion
                )

                tamaño_salida = (ancho_salida, alto_salida)
                fondo = ImageOps.fit(
                    original,
                    tamaño_salida,
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5)
                )

                intensidad = item.blur_valor / 100.0
                radio_blur = intensidad * (min(ancho_salida, alto_salida) * 0.06)
                if radio_blur > 0:
                    fondo = fondo.filter(ImageFilter.GaussianBlur(radius=radio_blur))

                capa_oscura = Image.new("RGB", tamaño_salida, (0, 0, 0))
                fondo = Image.blend(fondo, capa_oscura, 0.12)

                principal = ImageOps.contain(
                    original,
                    tamaño_salida,
                    method=Image.Resampling.LANCZOS
                )

                px = (ancho_salida - principal.width) // 2
                py = (alto_salida - principal.height) // 2
                fondo.paste(principal, (px, py))

                return fondo

    def generar_imagen_retrato(
        self,
        ruta,
        ancho_salida,
        alto_salida,
        mascara=None,
        blur_valor=50.0,
        zoom=100.0,
        offset_x=0.0,
        offset_y=0.0,
        brillo=0.0,
        contraste=0.0,
        saturacion=0.0
    ):
        """
        Genera la imagen en Modo Retrato combinando:
        1. Sujeto nítido en primer plano según la máscara 'L' de rembg (u2net).
        2. Fondo desenfocado mediante GaussianBlur proporcional al tamaño del lienzo.
        3. Recorte/zoom interactivo coordinado con idéntica geometría en foto y máscara.
        """
        with Image.open(ruta) as original:
            original = ImageOps.exif_transpose(original).convert("RGB")
            original = self._aplicar_mejoras_valores(
                original,
                brillo,
                contraste,
                saturacion
            )

            ow, oh = original.size
            escala_base = max(ancho_salida / ow, alto_salida / oh)
            zoom_factor = max(1.0, zoom / 100.0)
            escala = escala_base * zoom_factor

            nuevo_ancho = max(ancho_salida, round(ow * escala))
            nuevo_alto = max(alto_salida, round(oh * escala))

            redim_img = original.resize(
                (nuevo_ancho, nuevo_alto),
                resample=Image.Resampling.LANCZOS
            )

            sobrante_x = nuevo_ancho - ancho_salida
            sobrante_y = nuevo_alto - alto_salida

            x = int(sobrante_x * (offset_x + 1.0) / 2.0) if sobrante_x > 0 else 0
            y = int(sobrante_y * (offset_y + 1.0) / 2.0) if sobrante_y > 0 else 0

            x = max(0, min(sobrante_x, x))
            y = max(0, min(sobrante_y, y))

            crop_img = redim_img.crop((x, y, x + ancho_salida, y + alto_salida))

            # Si la máscara de IA todavía no está calculada, devolvemos la imagen encuadrada
            if mascara is None:
                return crop_img

            # La máscara se escala y recorta con la misma geometría exacta
            redim_mask = mascara.resize(
                (nuevo_ancho, nuevo_alto),
                resample=Image.Resampling.BILINEAR
            )
            crop_mask = redim_mask.crop((x, y, x + ancho_salida, y + alto_salida))

            # Escalar el radio del blur proporcionalmente a la resolución de salida
            intensidad = blur_valor / 100.0
            radio_blur = intensidad * (min(ancho_salida, alto_salida) * 0.06)

            if radio_blur > 0:
                fondo_blur = crop_img.filter(ImageFilter.GaussianBlur(radius=radio_blur))
                # Leve oscurecimiento sutil para separar al sujeto del fondo
                capa_oscura = Image.new("RGB", (ancho_salida, alto_salida), (0, 0, 0))
                fondo_blur = Image.blend(fondo_blur, capa_oscura, 0.04 * intensidad)
                return Image.composite(crop_img, fondo_blur, crop_mask)
            else:
                return crop_img

    def generar_imagen_blur(
        self,
        ruta,
        ancho_salida,
        alto_salida
    ):

        with Image.open(ruta) as original:

            # Corrige automáticamente imágenes cuya
            # orientación esté guardada en EXIF.
            original = ImageOps.exif_transpose(
                original
            )

            original = original.convert("RGB")
            original = self.aplicar_mejoras(original)

            tamaño_salida = (
                ancho_salida,
                alto_salida
            )

            # --------------------------------------------------------
            # FONDO
            # --------------------------------------------------------
            # FIT llena todo el lienzo manteniendo proporción.
            # Lo que sobra queda fuera y se recorta.
            # --------------------------------------------------------

            fondo = ImageOps.fit(
                original,
                tamaño_salida,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5)
            )

            # 0 = prácticamente sin desenfoque
            # 100 = desenfoque muy intenso
            intensidad = self.blur_valor / 100.0

            radio_blur = intensidad * (
                min(ancho_salida, alto_salida) * 0.06
            )

            fondo = fondo.filter(
                ImageFilter.GaussianBlur(
                    radius=radio_blur
                )
            )

            # Oscurecemos muy levemente el fondo.
            # Ayuda a separar visualmente la foto principal.
            capa_oscura = Image.new(
                "RGB",
                tamaño_salida,
                (0, 0, 0)
            )

            fondo = Image.blend(
                fondo,
                capa_oscura,
                0.12
            )

            # --------------------------------------------------------
            # IMAGEN PRINCIPAL
            # --------------------------------------------------------
            # CONTAIN garantiza que entra COMPLETA.
            # Nunca se deforma ni se recorta.
            # --------------------------------------------------------

            principal = ImageOps.contain(
                original,
                tamaño_salida,
                method=Image.Resampling.LANCZOS
            )

            x = (
                ancho_salida
                - principal.width
            ) // 2

            y = (
                alto_salida
                - principal.height
            ) // 2

            fondo.paste(
                principal,
                (x, y)
            )

            return fondo

    # ================================================================
    # MOTOR RECORTAR
    # ================================================================

    def generar_imagen_recorte(
        self,
        ruta,
        ancho_salida,
        alto_salida
    ):

        with Image.open(ruta) as original:

            original = ImageOps.exif_transpose(
                original
            ).convert("RGB")

            original = self.aplicar_mejoras(original)

            ow, oh = original.size

            # Escala mínima necesaria para cubrir
            # completamente el canvas.
            escala_base = max(
                ancho_salida / ow,
                alto_salida / oh
            )

            escala = (
                escala_base * self.zoom_recorte
            )

            nuevo_ancho = max(
                ancho_salida,
                round(ow * escala)
            )

            nuevo_alto = max(
                alto_salida,
                round(oh * escala)
            )

            redimensionada = original.resize(
                (nuevo_ancho, nuevo_alto),
                resample=Image.Resampling.LANCZOS
            )

            sobrante_x = nuevo_ancho - ancho_salida
            sobrante_y = nuevo_alto - alto_salida

            x = int(sobrante_x * (self.offset_x + 1.0) / 2.0) if sobrante_x > 0 else 0
            y = int(sobrante_y * (self.offset_y + 1.0) / 2.0) if sobrante_y > 0 else 0

            x = max(0, min(sobrante_x, x))
            y = max(0, min(sobrante_y, y))

            resultado = redimensionada.crop(
                (x, y, x + ancho_salida, y + alto_salida)
            )

            return resultado

    # ================================================================
    # GENERAR PREVISUALIZACIÓN
    # ================================================================

    def generar_preview(self):

        if not self.ruta_actual:
            return

        try:

            nombre_formato, dimensiones = (
                self.obtener_formato_actual()
            )

            ancho_salida, alto_salida = (
                dimensiones
            )

            if self.modo_recortar.get_active():
                resultado = self.generar_imagen_recorte(
                    self.ruta_actual,
                    ancho_salida,
                    alto_salida
                )
            elif self.modo_retrato.get_active():
                item_activo = self.carrusel[self.indice_activo] if self.carrusel and (0 <= self.indice_activo < len(self.carrusel)) else None
                mascara = item_activo.mascara_sujeto if item_activo else None
                resultado = self.generar_imagen_retrato(
                    self.ruta_actual,
                    ancho_salida,
                    alto_salida,
                    mascara=mascara,
                    blur_valor=self.blur_valor,
                    zoom=self.zoom_ajuste.get_value(),
                    offset_x=self.offset_x,
                    offset_y=self.offset_y,
                    brillo=self.brillo_valor,
                    contraste=self.contraste_valor,
                    saturacion=self.saturacion_valor
                )
            else:
                resultado = self.generar_imagen_blur(
                    self.ruta_actual,
                    ancho_salida,
                    alto_salida
                )

            # Para la interfaz no necesitamos guardar
            # permanentemente nada.
            #
            # Creamos un PNG temporal que GTK puede mostrar.

            if self.preview_temporal:

                try:
                    os.remove(
                        self.preview_temporal
                    )
                except OSError:
                    pass

            fd, ruta_temporal = (
                tempfile.mkstemp(
                    suffix=".png",
                    prefix="effectpic_"
                )
            )

            os.close(fd)

            resultado.save(
                ruta_temporal,
                "PNG"
            )

            self.preview_temporal = (
                ruta_temporal
            )

            self.imagen.set_filename(
                ruta_temporal
            )

            self.info.set_text(
                f"Salida: "
                f"{ancho_salida} × "
                f"{alto_salida} px"
            )

        except Exception as e:

            print(
                "Error generando preview:",
                e
            )

    # ================================================================
    # EXPORTAR
    # ================================================================

    def exportar_click(self, boton=None):
        if not self.ruta_actual:
            return

        # Sincronizamos la foto activa antes de exportar
        if self.carrusel and 0 <= self.indice_activo < len(self.carrusel):
            self.carrusel[self.indice_activo].guardar_desde_ventana(self)

        if len(self.carrusel) > 1:
            self.exportar_carrusel()
        else:
            self.exportar_imagen(boton)

    def exportar_carrusel(self):
        if not self.carrusel:
            return

        dialogo = Gtk.FileDialog()
        dialogo.set_title("Seleccionar carpeta para exportar carrusel")

        carpeta_inicial = os.path.dirname(self.carrusel[0].ruta)
        if os.path.isdir(carpeta_inicial):
            dialogo.set_initial_folder(Gio.File.new_for_path(carpeta_inicial))

        dialogo.select_folder(
            self,
            None,
            self.carpeta_carrusel_seleccionada
        )

    def carpeta_carrusel_seleccionada(self, dialogo, resultado):
        try:
            carpeta = dialogo.select_folder_finish(resultado)
            ruta_carpeta = carpeta.get_path()
            if not ruta_carpeta:
                return

            _, dimensiones = self.obtener_formato_actual()
            ancho_salida, alto_salida = dimensiones
            sufijo = f"{ancho_salida}x{alto_salida}"

            total = len(self.carrusel)
            for i, item in enumerate(self.carrusel, start=1):
                img_final = self.generar_imagen_para_item(
                    item,
                    ancho_salida,
                    alto_salida
                )

                base_nombre = os.path.splitext(item.nombre)[0]
                base_nombre = re.sub(r'_\d+x\d+$', '', base_nombre)

                nombre_salida = f"{i:02d}_{base_nombre}_{sufijo}.jpg"
                ruta_salida = os.path.join(ruta_carpeta, nombre_salida)

                img_final.save(
                    ruta_salida,
                    "JPEG",
                    quality=95,
                    optimize=True,
                    subsampling=0
                )

            dialogo_alerta = Gtk.AlertDialog()
            dialogo_alerta.set_message("¡Carrusel exportado con éxito!")
            dialogo_alerta.set_detail(
                f"Se exportaron {total} imágenes en formato {ancho_salida} × {alto_salida} px en:\n{ruta_carpeta}"
            )
            dialogo_alerta.set_buttons(["Aceptar"])
            dialogo_alerta.show(self)

        except GLib.Error:
            # Cancelado por el usuario
            pass
        except Exception as e:
            print("Error exportando carrusel:", e)

    def exportar_imagen(self, boton):

        if not self.ruta_actual:
            return

        _, dimensiones = self.obtener_formato_actual()

        ancho_salida, alto_salida = dimensiones

        # Carpeta de la imagen original
        carpeta_original = os.path.dirname(
            self.ruta_actual
        )

        # Nombre original sin extensión
        nombre_original = os.path.splitext(
            os.path.basename(self.ruta_actual)
        )[0]
        nombre_original = re.sub(r'_\d+x\d+$', '', nombre_original)

        # Ejemplo: foto_1080x1080.jpg
        sufijo = f"{ancho_salida}x{alto_salida}"

        nombre_sugerido = (
            f"{nombre_original}_{sufijo}.jpg"
        )

        dialogo = Gtk.FileDialog()
        dialogo.set_title("Exportar imagen")

        archivo_sugerido = Gio.File.new_for_path(
            os.path.join(
                carpeta_original,
                nombre_sugerido
            )
        )

        dialogo.set_initial_file(
            archivo_sugerido
        )

        dialogo.save(
            self,
            None,
            self.exportacion_seleccionada
        )


    def exportacion_seleccionada(
        self,
        dialogo,
        resultado
    ):

        try:

            archivo = dialogo.save_finish(
                resultado
            )

            ruta_salida = archivo.get_path()

            if not ruta_salida:
                return

            # Si el usuario no escribió extensión,
            # agregamos JPG automáticamente.
            if not ruta_salida.lower().endswith(
                (".jpg", ".jpeg")
            ):
                ruta_salida += ".jpg"

            _, dimensiones = (
                self.obtener_formato_actual()
            )

            ancho_salida, alto_salida = (
                dimensiones
            )

            # IMPORTANTE:
            # volvemos siempre al original.
            # Nunca exportamos desde el preview temporal.
            if self.modo_recortar.get_active():
                resultado_final = self.generar_imagen_recorte(
                    self.ruta_actual,
                    ancho_salida,
                    alto_salida
                )
            elif self.modo_retrato.get_active():
                item_activo = self.carrusel[self.indice_activo] if self.carrusel and (0 <= self.indice_activo < len(self.carrusel)) else None
                mascara = item_activo.mascara_sujeto if item_activo else None
                if mascara is None:
                    try:
                        import rembg
                        session = obtener_sesion_rembg(modelo="u2net")
                        with Image.open(self.ruta_actual) as img_orig:
                            img_orig = ImageOps.exif_transpose(img_orig).convert("RGB")
                            mascara = rembg.remove(img_orig, session=session, only_mask=True)
                            if item_activo:
                                item_activo.mascara_sujeto = mascara
                    except Exception as e_ia:
                        print(f"Error calculando máscara IA en exportación: {e_ia}")

                resultado_final = self.generar_imagen_retrato(
                    self.ruta_actual,
                    ancho_salida,
                    alto_salida,
                    mascara=mascara,
                    blur_valor=self.blur_valor,
                    zoom=self.zoom_ajuste.get_value(),
                    offset_x=self.offset_x,
                    offset_y=self.offset_y,
                    brillo=self.brillo_valor,
                    contraste=self.contraste_valor,
                    saturacion=self.saturacion_valor
                )
            else:
                resultado_final = self.generar_imagen_blur(
                    self.ruta_actual,
                    ancho_salida,
                    alto_salida
                )

            resultado_final.save(
                ruta_salida,
                "JPEG",
                quality=95,
                optimize=True,
                subsampling=0
            )

            print(
                f"Imagen exportada: {ruta_salida}"
            )

            self.mostrar_exportacion_correcta(
                ruta_salida
            )

        except GLib.Error:
            # Usuario canceló Guardar como...
            pass

        except Exception as e:

            print(
                "Error exportando imagen:",
                e
            )


    # ================================================================
    # CONFIRMACIÓN
    # ================================================================

    def mostrar_exportacion_correcta(
        self,
        ruta
    ):

        dialogo = Gtk.AlertDialog()

        dialogo.set_message(
            "Imagen exportada correctamente"
        )

        dialogo.set_detail(
            os.path.basename(ruta)
        )

        dialogo.set_buttons([
            "Aceptar"
        ])

        dialogo.show(self)

if __name__ == "__main__":
    app = EffectPic()
    app.run()