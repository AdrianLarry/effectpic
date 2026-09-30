#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EffectPic by Adri Pienso
---------
Aplicación de preparación, encuadre y retoque de imágenes para redes sociales.
Incluye:
- Formatos estándar de salida (1:1, 4:5, 9:16, 16:9).
- Modos: Ajustar + Blur, Recortar interactivo, Retrato Bokeh (IA) y Ajustar + Color.
- Panel de Retoque fotográfico: Brillo, Contraste, Saturación y Presets (Vívido, Cálido, etc.).
- Barra de herramientas con Historial (Deshacer / Rehacer), Restaurar y Comparar (Antes / Después).
- El Totii toco 2 cositas nomas :)
"""

import os
import sys

# Registrar directorios de DLLs de MSYS2 en Windows (necesario para onnxruntime, GTK, protobuf, etc.)
if sys.platform == "win32":
    for _directorio_dll in [r"C:\msys64\ucrt64\bin", r"C:\msys64\mingw64\bin"]:
        if os.path.exists(_directorio_dll) and hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(_directorio_dll)
            except Exception:
                pass

import gi
gi.require_version("Gtk", "4.0")

import tempfile
import threading
import subprocess

from gi.repository import Gtk, Gio, GdkPixbuf, GLib
from PIL import Image, ImageOps, ImageFilter, ImageEnhance

# Detección inteligente de rembg (directo en MSYS2 o vía Python 3.12 del sistema)
PYTHON_IA_EXTERNO = None
REMBG_DIRECTO = False

import contextlib
import io

try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import rembg
    REMBG_DIRECTO = True
except BaseException:
    REMBG_DIRECTO = False

if not REMBG_DIRECTO:
    for _candidato in [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"),
        r"C:\Users\nahva\AppData\Local\Programs\Python\Python312\python.exe",
        r"C:\Python312\python.exe",
    ]:
        if os.path.exists(_candidato):
            PYTHON_IA_EXTERNO = _candidato
            break

REMBG_DISPONIBLE = REMBG_DIRECTO or (PYTHON_IA_EXTERNO is not None)


# Nombre visible -> resolución REAL de salida
FORMATOS = {
    "Social · Cuadrado 1:1": (1080, 1080),
    "Social · Retrato 4:5": (1080, 1350),
    "Social · Vertical 9:16": (1080, 1920),
    "Social · Wide 16:9": (1920, 1080),
}

# Presets de retoque rápido
PRESETS_RETOQUE = {
    "Original": {"brillo": 0, "contraste": 0, "saturacion": 0},
    "Vívido": {"brillo": 5, "contraste": 20, "saturacion": 30},
    "Cálido": {"brillo": 5, "contraste": 10, "saturacion": 25},
    "Frío": {"brillo": 0, "contraste": 15, "saturacion": -10},
    "B&N": {"brillo": 5, "contraste": 30, "saturacion": -100},
}


class EffectPic(Gtk.Application):

    def __init__(self):
        super().__init__(
            application_id="com.effectpic.app",
            flags=Gio.ApplicationFlags.HANDLES_OPEN
        )

    def do_activate(self):
        # Preferir tema oscuro si el sistema lo soporta
        configuracion = Gtk.Settings.get_default()
        if configuracion and configuracion.find_property("gtk-application-prefer-dark-theme"):
            try:
                configuracion.set_property("gtk-application-prefer-dark-theme", True)
            except Exception:
                pass

        self.ventana = EffectPicWindow(self)
        self.ventana.present()

    def do_open(self, files, n_files, hint):
        configuracion = Gtk.Settings.get_default()
        if configuracion and configuracion.find_property("gtk-application-prefer-dark-theme"):
            try:
                configuracion.set_property("gtk-application-prefer-dark-theme", True)
            except Exception:
                pass

        self.ventana = EffectPicWindow(self)
        self.ventana.present()

        if n_files > 0:
            ruta = files[0].get_path()
            if ruta:
                self.ventana.cargar_imagen(ruta)


class EffectPicWindow(Gtk.ApplicationWindow):

    def __init__(self, app):
        super().__init__(application=app)

        self.set_title("EffectPic")
        self.set_default_size(1150, 850)

        # Estado del archivo e imagen
        self.ruta_actual = None
        self.preview_temporal = None

        # Estado del recorte interactivo
        self.zoom_recorte = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.drag_offset_x = 0.0
        self.drag_offset_y = 0.0

        # Estado de desenfoque
        self.blur_valor = 50

        # Estado de retoques (color y luz)
        self.brillo_valor = 0
        self.contraste_valor = 0
        self.saturacion_valor = 0

        # Estado de IA (Rembg)
        self.sujeto_recortado_cache = None
        self.procesando_ia = False

        # Modo comparación (Antes / Después)
        self.modo_comparando = False

        # Historial de cambios (Undo / Redo)
        self.historial_deshacer = []
        self.historial_rehacer = []
        self._bloqueo_historial = False
        self._timer_historial = None

        # ============================================================
        # CONTENEDOR PRINCIPAL
        # ============================================================
        principal = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10
        )
        principal.set_margin_top(12)
        principal.set_margin_bottom(12)
        principal.set_margin_start(14)
        principal.set_margin_end(14)

        self.set_child(principal)

        # ============================================================
        # BARRA SUPERIOR (Acciones, Historial, Formato e Info)
        # ============================================================
        barra = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8
        )
        principal.append(barra)

        # Abrir imagen
        self.boton_abrir = Gtk.Button(label="Abrir imagen")
        self.boton_abrir.connect("clicked", self.abrir_imagen)
        barra.append(self.boton_abrir)

        # Deshacer / Rehacer
        self.boton_deshacer = Gtk.Button(label="Deshacer")
        self.boton_deshacer.set_sensitive(False)
        self.boton_deshacer.connect("clicked", self.deshacer)
        barra.append(self.boton_deshacer)

        self.boton_rehacer = Gtk.Button(label="Rehacer")
        self.boton_rehacer.set_sensitive(False)
        self.boton_rehacer.connect("clicked", self.rehacer)
        barra.append(self.boton_rehacer)

        # Restaurar
        self.boton_restaurar = Gtk.Button(label="Restaurar")
        self.boton_restaurar.set_sensitive(False)
        self.boton_restaurar.connect("clicked", self.restaurar_original)
        barra.append(self.boton_restaurar)

        # Comparar (Antes / Después)
        self.boton_comparar = Gtk.ToggleButton(label="Comparar")
        self.boton_comparar.set_sensitive(False)
        self.boton_comparar.connect("toggled", self.comparar_cambiado)
        barra.append(self.boton_comparar)

        # Separador visual sutil
        sep_superior = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep_superior.set_margin_start(4)
        sep_superior.set_margin_end(4)
        barra.append(sep_superior)

        # Selector de formato
        barra.append(Gtk.Label(label="Formato:"))
        self.selector = Gtk.DropDown.new_from_strings(list(FORMATOS.keys()))
        self.selector.set_selected(0)
        self.selector.connect("notify::selected", self.formato_cambiado)
        barra.append(self.selector)

        # Información de resolución / estado
        self.info = Gtk.Label(label="Ninguna imagen abierta")
        self.info.set_hexpand(True)
        self.info.set_halign(Gtk.Align.END)
        barra.append(self.info)

        # ============================================================
        # ÁREA DE PREVISUALIZACIÓN (Lienzo interactivo)
        # ============================================================
        self.area_preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.area_preview.set_hexpand(True)
        self.area_preview.set_vexpand(True)
        self.area_preview.set_halign(Gtk.Align.FILL)
        self.area_preview.set_valign(Gtk.Align.FILL)
        principal.append(self.area_preview)

        self.marco = Gtk.AspectFrame(
            xalign=0.5,
            yalign=0.5,
            ratio=1.0,
            obey_child=False
        )
        self.marco.set_halign(Gtk.Align.CENTER)
        self.marco.set_valign(Gtk.Align.CENTER)
        self.area_preview.append(self.marco)

        self.imagen = Gtk.Picture()
        self.imagen.set_can_shrink(True)
        self.imagen.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.imagen.set_hexpand(True)
        self.imagen.set_vexpand(True)
        self.marco.set_child(self.imagen)

        # Gesto para arrastrar imagen en modo recorte
        self.gesto_arrastre = Gtk.GestureDrag()
        self.gesto_arrastre.connect("drag-begin", self.arrastre_iniciado)
        self.gesto_arrastre.connect("drag-update", self.arrastre_actualizado)
        self.imagen.add_controller(self.gesto_arrastre)

        self.area_preview.connect("notify::width", self.recalcular_lienzo)
        self.area_preview.connect("notify::height", self.recalcular_lienzo)

        # ============================================================
        # PANEL INFERIOR
        # ============================================================
        separador = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        principal.append(separador)

        panel_inferior = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10
        )
        principal.append(panel_inferior)

        # ------------------------------------------------------------
        # FILA 1: Modos principales, Blur, Zoom y Exportar
        # ------------------------------------------------------------
        fila1 = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12
        )
        panel_inferior.append(fila1)

        fila1.append(Gtk.Label(label="Modo:"))

        self.modo_blur = Gtk.CheckButton(label="Ajustar + Blur")
        self.modo_recortar = Gtk.CheckButton(label="Recortar")
        self.modo_ia = Gtk.CheckButton(label="Retrato Bokeh (IA)")
        self.modo_color = Gtk.CheckButton(label="Ajustar + Color")

        self.modo_recortar.set_group(self.modo_blur)
        self.modo_ia.set_group(self.modo_blur)
        self.modo_color.set_group(self.modo_blur)

        self.modo_blur.set_active(True)
        self.modo_blur.connect("toggled", self.modo_cambiado)
        self.modo_recortar.connect("toggled", self.modo_cambiado)
        self.modo_ia.connect("toggled", self.modo_cambiado)
        self.modo_color.connect("toggled", self.modo_cambiado)

        fila1.append(self.modo_blur)
        fila1.append(self.modo_recortar)
        fila1.append(self.modo_ia)
        fila1.append(self.modo_color)

        # Slider Blur
        self.blur_label = Gtk.Label(label="Blur:")
        self.blur_ajuste = Gtk.Adjustment(
            value=50, lower=0, upper=100,
            step_increment=1, page_increment=10, page_size=0
        )
        self.blur_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.blur_ajuste
        )
        self.blur_slider.set_size_request(130, -1)
        self.blur_slider.set_draw_value(True)
        self.blur_slider.set_value_pos(Gtk.PositionType.TOP)
        self.blur_slider.set_digits(0)
        self.blur_slider.connect("value-changed", self.blur_cambiado)

        fila1.append(self.blur_label)
        fila1.append(self.blur_slider)

        # Slider Zoom
        self.zoom_label = Gtk.Label(label="Zoom:")
        self.zoom_ajuste = Gtk.Adjustment(
            value=100, lower=100, upper=300,
            step_increment=1, page_increment=10, page_size=0
        )
        self.zoom_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.zoom_ajuste
        )
        self.zoom_slider.set_size_request(130, -1)
        self.zoom_slider.set_draw_value(True)
        self.zoom_slider.set_value_pos(Gtk.PositionType.TOP)
        self.zoom_slider.set_digits(0)
        self.zoom_slider.connect("value-changed", self.zoom_cambiado)

        self.boton_centrar = Gtk.Button(label="Centrar")
        self.boton_centrar.connect("clicked", self.centrar_recorte)

        self.zoom_label.set_sensitive(False)
        self.zoom_slider.set_sensitive(False)
        self.boton_centrar.set_sensitive(False)

        fila1.append(self.zoom_label)
        fila1.append(self.zoom_slider)
        fila1.append(self.boton_centrar)

        espacio_fila1 = Gtk.Box()
        espacio_fila1.set_hexpand(True)
        fila1.append(espacio_fila1)

        self.boton_exportar = Gtk.Button(label="Exportar")
        self.boton_exportar.set_sensitive(False)
        self.boton_exportar.connect("clicked", self.exportar_imagen)
        fila1.append(self.boton_exportar)

        # ------------------------------------------------------------
        # FILA 2: Retoques (Presets, Brillo, Contraste, Saturación)
        # ------------------------------------------------------------
        fila2 = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12
        )
        panel_inferior.append(fila2)

        fila2.append(Gtk.Label(label="Retoque:"))

        self.preset_selector = Gtk.DropDown.new_from_strings(
            list(PRESETS_RETOQUE.keys())
        )
        self.preset_selector.set_selected(0)
        self.preset_selector.connect(
            "notify::selected",
            self.preset_seleccionado
        )
        fila2.append(self.preset_selector)

        # Slider Brillo
        fila2.append(Gtk.Label(label="Brillo:"))
        self.brillo_ajuste = Gtk.Adjustment(
            value=0, lower=-100, upper=100,
            step_increment=1, page_increment=10, page_size=0
        )
        self.brillo_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.brillo_ajuste
        )
        self.brillo_slider.set_size_request(130, -1)
        self.brillo_slider.set_draw_value(True)
        self.brillo_slider.set_value_pos(Gtk.PositionType.TOP)
        self.brillo_slider.set_digits(0)
        self.brillo_slider.connect("value-changed", self.retoque_cambiado)
        fila2.append(self.brillo_slider)

        # Slider Contraste
        fila2.append(Gtk.Label(label="Contraste:"))
        self.contraste_ajuste = Gtk.Adjustment(
            value=0, lower=-100, upper=100,
            step_increment=1, page_increment=10, page_size=0
        )
        self.contraste_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.contraste_ajuste
        )
        self.contraste_slider.set_size_request(130, -1)
        self.contraste_slider.set_draw_value(True)
        self.contraste_slider.set_value_pos(Gtk.PositionType.TOP)
        self.contraste_slider.set_digits(0)
        self.contraste_slider.connect("value-changed", self.retoque_cambiado)
        fila2.append(self.contraste_slider)

        # Slider Saturación
        fila2.append(Gtk.Label(label="Saturación:"))
        self.saturacion_ajuste = Gtk.Adjustment(
            value=0, lower=-100, upper=100,
            step_increment=1, page_increment=10, page_size=0
        )
        self.saturacion_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.saturacion_ajuste
        )
        self.saturacion_slider.set_size_request(130, -1)
        self.saturacion_slider.set_draw_value(True)
        self.saturacion_slider.set_value_pos(Gtk.PositionType.TOP)
        self.saturacion_slider.set_digits(0)
        self.saturacion_slider.connect("value-changed", self.retoque_cambiado)
        fila2.append(self.saturacion_slider)

        # Botón Reiniciar retoques
        self.boton_reiniciar_retoques = Gtk.Button(label="Reiniciar retoques")
        self.boton_reiniciar_retoques.connect(
            "clicked",
            self.reiniciar_retoques
        )
        fila2.append(self.boton_reiniciar_retoques)

    # ================================================================
    # ABRIR Y CARGAR IMAGEN
    # ================================================================

    def abrir_imagen(self, boton):
        dialogo = Gtk.FileDialog()
        dialogo.set_title("Abrir imagen")

        filtro = Gtk.FileFilter()
        filtro.set_name("Imágenes (*.jpg, *.png, *.webp)")
        filtro.add_mime_type("image/jpeg")
        filtro.add_mime_type("image/png")
        filtro.add_mime_type("image/webp")

        filtros = Gio.ListStore.new(Gtk.FileFilter)
        filtros.append(filtro)

        dialogo.set_filters(filtros)
        dialogo.set_default_filter(filtro)
        dialogo.open(self, None, self.imagen_seleccionada)

    def imagen_seleccionada(self, dialogo, resultado):
        try:
            archivo = dialogo.open_finish(resultado)
            ruta = archivo.get_path()
            if ruta:
                self.cargar_imagen(ruta)
        except GLib.Error:
            pass
        except Exception as e:
            print("Error seleccionando imagen:", e)

    def cargar_imagen(self, ruta):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(ruta)
            ancho = pixbuf.get_width()
            alto = pixbuf.get_height()

            self.ruta_actual = ruta
            self.sujeto_recortado_cache = None
            self.procesando_ia = False

            # Limpiar historial para la nueva imagen
            self.historial_deshacer.clear()
            self.historial_rehacer.clear()
            self.actualizar_botones_historial()

            self.info.set_text(f"Original: {ancho} × {alto} px")
            nombre = os.path.basename(ruta)
            self.set_title(f"EffectPic — {nombre}")

            self.boton_exportar.set_sensitive(True)
            self.boton_restaurar.set_sensitive(True)
            self.boton_comparar.set_sensitive(True)

            # Si el modo actual es IA, iniciamos el análisis
            if self.modo_ia.get_active():
                self.iniciar_procesamiento_ia()
            else:
                self.generar_preview()

            # Guardamos estado inicial en historial
            self.guardar_estado(inmediato=True)

        except Exception as e:
            print("Error cargando imagen:", e)

    # ================================================================
    # MANEJO DEL LIENZO Y FORMATOS
    # ================================================================

    def obtener_formato_actual(self):
        indice = self.selector.get_selected()
        nombres = list(FORMATOS.keys())
        if indice >= len(nombres):
            return nombres[0], FORMATOS[nombres[0]]
        nombre = nombres[indice]
        return nombre, FORMATOS[nombre]

    def formato_cambiado(self, selector, parametro):
        self.recalcular_lienzo()
        if self.ruta_actual:
            self.generar_preview()
            self.guardar_estado()

    def recalcular_lienzo(self, *args):
        ancho_disponible = self.area_preview.get_width()
        alto_disponible = self.area_preview.get_height()

        if ancho_disponible <= 0 or alto_disponible <= 0:
            return

        _, dimensiones = self.obtener_formato_actual()
        ancho_salida, alto_salida = dimensiones
        ratio = ancho_salida / alto_salida

        self.marco.set_ratio(ratio)

        max_ancho = ancho_disponible - 30
        max_alto = alto_disponible - 30

        if max_ancho <= 0 or max_alto <= 0:
            return

        nuevo_ancho = max_ancho
        nuevo_alto = int(nuevo_ancho / ratio)

        if nuevo_alto > max_alto:
            nuevo_alto = max_alto
            nuevo_ancho = int(nuevo_alto * ratio)

        self.marco.set_size_request(nuevo_ancho, nuevo_alto)
        self.marco.set_hexpand(False)
        self.marco.set_vexpand(False)

    # ================================================================
    # MODOS DE OPERACIÓN
    # ================================================================

    def modo_cambiado(self, boton):
        if not boton.get_active():
            return

        es_recorte = self.modo_recortar.get_active()
        es_blur = self.modo_blur.get_active()
        es_ia = self.modo_ia.get_active()
        es_color = self.modo_color.get_active()

        # Sensibilidad de controles según modo
        self.zoom_label.set_sensitive(es_recorte)
        self.zoom_slider.set_sensitive(es_recorte)
        self.boton_centrar.set_sensitive(es_recorte)

        # Blur se usa en Ajustar + Blur y en Retrato Bokeh (IA)
        self.blur_label.set_sensitive(es_blur or es_ia)
        self.blur_slider.set_sensitive(es_blur or es_ia)

        if es_ia:
            if not REMBG_DISPONIBLE:
                self.mostrar_aviso_rembg()
                self.modo_blur.set_active(True)
                return

            if self.ruta_actual and self.sujeto_recortado_cache is None:
                self.iniciar_procesamiento_ia()
                return

        if self.ruta_actual:
            self.generar_preview()
            self.guardar_estado()

    def zoom_cambiado(self, slider):
        self.zoom_recorte = slider.get_value() / 100.0
        if self.ruta_actual and self.modo_recortar.get_active():
            self.generar_preview()
            self.guardar_estado()

    def centrar_recorte(self, boton=None):
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.zoom_ajuste.set_value(100)
        self.zoom_recorte = 1.0

        if self.ruta_actual and self.modo_recortar.get_active():
            self.generar_preview()
            self.guardar_estado(inmediato=True)

    def arrastre_iniciado(self, gesto, x, y):
        if not self.modo_recortar.get_active():
            return
        self.drag_offset_x = self.offset_x
        self.drag_offset_y = self.offset_y

    def arrastre_actualizado(self, gesto, desplazamiento_x, desplazamiento_y):
        if not self.modo_recortar.get_active():
            return

        ancho = self.imagen.get_width()
        alto = self.imagen.get_height()

        if ancho <= 0 or alto <= 0:
            return

        nuevo_x = self.drag_offset_x - (desplazamiento_x / ancho) * 2
        nuevo_y = self.drag_offset_y - (desplazamiento_y / alto) * 2

        self.offset_x = max(-1.0, min(1.0, nuevo_x))
        self.offset_y = max(-1.0, min(1.0, nuevo_y))

        self.generar_preview()
        self.guardar_estado()

    def blur_cambiado(self, slider):
        self.blur_valor = slider.get_value()
        if self.ruta_actual and (self.modo_blur.get_active() or self.modo_ia.get_active()):
            self.generar_preview()
            self.guardar_estado()

    # ================================================================
    # RETOQUES DE COLOR Y LUZ
    # ================================================================

    def retoque_cambiado(self, slider):
        self.brillo_valor = int(self.brillo_ajuste.get_value())
        self.contraste_valor = int(self.contraste_ajuste.get_value())
        self.saturacion_valor = int(self.saturacion_ajuste.get_value())

        if self.ruta_actual:
            self.generar_preview()
            self.guardar_estado()

    def preset_seleccionado(self, selector, parametro):
        if self._bloqueo_historial:
            return

        indice = selector.get_selected()
        nombres = list(PRESETS_RETOQUE.keys())
        if indice < len(nombres):
            nombre = nombres[indice]
            valores = PRESETS_RETOQUE[nombre]

            self._bloqueo_historial = True
            self.brillo_ajuste.set_value(valores["brillo"])
            self.contraste_ajuste.set_value(valores["contraste"])
            self.saturacion_ajuste.set_value(valores["saturacion"])
            self.brillo_valor = valores["brillo"]
            self.contraste_valor = valores["contraste"]
            self.saturacion_valor = valores["saturacion"]
            self._bloqueo_historial = False

            if self.ruta_actual:
                self.generar_preview()
                self.guardar_estado(inmediato=True)

    def reiniciar_retoques(self, boton=None):
        self._bloqueo_historial = True
        self.brillo_ajuste.set_value(0)
        self.contraste_ajuste.set_value(0)
        self.saturacion_ajuste.set_value(0)
        self.brillo_valor = 0
        self.contraste_valor = 0
        self.saturacion_valor = 0
        self.preset_selector.set_selected(0)
        self._bloqueo_historial = False

        if self.ruta_actual:
            self.generar_preview()
            self.guardar_estado(inmediato=True)

    def aplicar_retoques(self, imagen):
        """Aplica brillo, contraste y saturación a una imagen PIL RGB."""
        if self.brillo_valor != 0:
            factor_b = 1.0 + (self.brillo_valor / 100.0)
            imagen = ImageEnhance.Brightness(imagen).enhance(max(0.0, factor_b))

        if self.contraste_valor != 0:
            factor_c = 1.0 + (self.contraste_valor / 100.0)
            imagen = ImageEnhance.Contrast(imagen).enhance(max(0.0, factor_c))

        if self.saturacion_valor != 0:
            factor_s = 1.0 + (self.saturacion_valor / 100.0)
            imagen = ImageEnhance.Color(imagen).enhance(max(0.0, factor_s))

        return imagen

    # ================================================================
    # PROCESAMIENTO CON IA (REMBG / BOKEH)
    # ================================================================

    def iniciar_procesamiento_ia(self):
        if not self.ruta_actual or self.procesando_ia:
            return

        self.procesando_ia = True
        self.info.set_text("Procesando sujeto con IA (rembg)...")
        self.boton_exportar.set_sensitive(False)

        hilo = threading.Thread(
            target=self._hilo_rembg,
            args=(self.ruta_actual,),
            daemon=True
        )
        hilo.start()

    def _hilo_rembg(self, ruta):
        try:
            with Image.open(ruta) as orig:
                orig = ImageOps.exif_transpose(orig).convert("RGB")

                if REMBG_DIRECTO:
                    import rembg
                    recorte = rembg.remove(orig)
                elif PYTHON_IA_EXTERNO:
                    fd_in, ruta_in = tempfile.mkstemp(suffix=".png", prefix="in_rembg_")
                    os.close(fd_in)
                    fd_out, ruta_out = tempfile.mkstemp(suffix=".png", prefix="out_rembg_")
                    os.close(fd_out)

                    try:
                        orig.save(ruta_in, "PNG")
                        script = (
                            "from rembg import remove; from PIL import Image; "
                            "img = Image.open(r'''" + ruta_in + "'''); "
                            "out = remove(img); "
                            "out.save(r'''" + ruta_out + "''', 'PNG')"
                        )
                        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                        subprocess.run(
                            [PYTHON_IA_EXTERNO, "-c", script],
                            check=True,
                            capture_output=True,
                            creationflags=flags
                        )
                        with Image.open(ruta_out) as res:
                            recorte = res.copy()
                    finally:
                        for temp_f in [ruta_in, ruta_out]:
                            try:
                                if os.path.exists(temp_f):
                                    os.remove(temp_f)
                            except OSError:
                                pass
                else:
                    raise RuntimeError("No se encontró backend de IA (rembg).")

                GLib.idle_add(self._rembg_finalizado, recorte, None)
        except Exception as e:
            GLib.idle_add(self._rembg_finalizado, None, str(e))

    def _rembg_finalizado(self, recorte, error):
        self.procesando_ia = False
        self.boton_exportar.set_sensitive(True)

        if error:
            print("Error en rembg:", error)
            self.info.set_text("Error procesando IA")
            self.modo_blur.set_active(True)
            return

        self.sujeto_recortado_cache = recorte
        _, dimensiones = self.obtener_formato_actual()
        self.info.set_text(f"Salida: {dimensiones[0]} × {dimensiones[1]} px")
        self.generar_preview()

    def mostrar_aviso_rembg(self):
        dialogo = Gtk.AlertDialog()
        dialogo.set_message("Módulo IA de REMBG requerido")
        dialogo.set_detail(
            "Para activar el Modo Retrato Bokeh (IA), instala la librería rembg ejecutando:\n\n"
            "pip install rembg\n\n"
            "Una vez instalada, reinicia la aplicación."
        )
        dialogo.set_buttons(["Aceptar"])
        dialogo.show(self)

    # ================================================================
    # MOTORES DE GENERACIÓN DE IMAGEN
    # ================================================================

    def generar_imagen_blur(self, ruta, ancho_salida, alto_salida):
        with Image.open(ruta) as original:
            original = ImageOps.exif_transpose(original).convert("RGB")
            tamaño_salida = (ancho_salida, alto_salida)

            # Fondo desenfocado
            fondo = ImageOps.fit(
                original,
                tamaño_salida,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5)
            )

            intensidad = self.blur_valor / 100.0
            radio_blur = intensidad * (min(ancho_salida, alto_salida) * 0.06)

            if radio_blur > 0:
                fondo = fondo.filter(ImageFilter.GaussianBlur(radius=radio_blur))

            # Oscurecido sutil para contraste
            capa_oscura = Image.new("RGB", tamaño_salida, (0, 0, 0))
            fondo = Image.blend(fondo, capa_oscura, 0.12)

            # Imagen principal completa
            principal = ImageOps.contain(
                original,
                tamaño_salida,
                method=Image.Resampling.LANCZOS
            )

            x = (ancho_salida - principal.width) // 2
            y = (alto_salida - principal.height) // 2
            fondo.paste(principal, (x, y))

            return self.aplicar_retoques(fondo)

    def generar_imagen_recorte(self, ruta, ancho_salida, alto_salida):
        with Image.open(ruta) as original:
            original = ImageOps.exif_transpose(original).convert("RGB")
            ow, oh = original.size

            escala_base = max(ancho_salida / ow, alto_salida / oh)
            escala = escala_base * self.zoom_recorte

            nuevo_ancho = max(ancho_salida, round(ow * escala))
            nuevo_alto = max(alto_salida, round(oh * escala))

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

            return self.aplicar_retoques(resultado)

    def generar_imagen_bokeh_ia(self, ruta, ancho_salida, alto_salida):
        """Genera el efecto Bokeh con IA: fondo desenfocado + sujeto nítido superpuesto."""
        with Image.open(ruta) as original:
            original = ImageOps.exif_transpose(original).convert("RGB")
            tamaño_salida = (ancho_salida, alto_salida)

            # 1. Fondo completo de la escena
            fondo = ImageOps.fit(
                original,
                tamaño_salida,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5)
            )

            # 2. Desenfoque bokeh según slider Blur
            intensidad = self.blur_valor / 100.0
            radio_blur = intensidad * (min(ancho_salida, alto_salida) * 0.05)
            if radio_blur > 0:
                fondo = fondo.filter(ImageFilter.GaussianBlur(radius=radio_blur))

            # 3. Leve viñeta/sombra para dar profundidad
            capa_oscura = Image.new("RGB", tamaño_salida, (0, 0, 0))
            fondo = Image.blend(fondo, capa_oscura, 0.08)

            # 4. Superponer el sujeto nítido recortado con rembg
            if self.sujeto_recortado_cache is not None:
                sujeto_ajustado = ImageOps.fit(
                    self.sujeto_recortado_cache,
                    tamaño_salida,
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5)
                )
                fondo.paste(sujeto_ajustado, (0, 0), sujeto_ajustado)

            return self.aplicar_retoques(fondo)

    def generar_imagen_color(self, ruta, ancho_salida, alto_salida):
        """Modo Ajustar + Color de fondo sólido neutro/blanco."""
        with Image.open(ruta) as original:
            original = ImageOps.exif_transpose(original).convert("RGB")
            tamaño_salida = (ancho_salida, alto_salida)

            # Fondo neutro oscuro profesional
            fondo = Image.new("RGB", tamaño_salida, (24, 24, 26))

            principal = ImageOps.contain(
                original,
                tamaño_salida,
                method=Image.Resampling.LANCZOS
            )

            x = (ancho_salida - principal.width) // 2
            y = (alto_salida - principal.height) // 2
            fondo.paste(principal, (x, y))

            return self.aplicar_retoques(fondo)

    # ================================================================
    # GENERAR PREVISUALIZACIÓN Y COMPARACIÓN
    # ================================================================

    def generar_preview(self):
        if not self.ruta_actual:
            return

        try:
            nombre_formato, dimensiones = self.obtener_formato_actual()
            ancho_salida, alto_salida = dimensiones

            # Si el botón Comparar está activo, mostramos la foto original intacta
            if self.modo_comparando:
                with Image.open(self.ruta_actual) as original:
                    orig = ImageOps.exif_transpose(original).convert("RGB")
                    lienzo = Image.new("RGB", (ancho_salida, alto_salida), (20, 20, 22))
                    encaje = ImageOps.contain(orig, (ancho_salida, alto_salida))
                    x = (ancho_salida - encaje.width) // 2
                    y = (alto_salida - encaje.height) // 2
                    lienzo.paste(encaje, (x, y))
                    resultado = lienzo
                    self.info.set_text("Modo Comparar: Original sin retoques")
            else:
                if self.modo_recortar.get_active():
                    resultado = self.generar_imagen_recorte(
                        self.ruta_actual, ancho_salida, alto_salida
                    )
                elif self.modo_ia.get_active():
                    resultado = self.generar_imagen_bokeh_ia(
                        self.ruta_actual, ancho_salida, alto_salida
                    )
                elif self.modo_color.get_active():
                    resultado = self.generar_imagen_color(
                        self.ruta_actual, ancho_salida, alto_salida
                    )
                else:
                    resultado = self.generar_imagen_blur(
                        self.ruta_actual, ancho_salida, alto_salida
                    )

                if not self.procesando_ia:
                    self.info.set_text(f"Salida: {ancho_salida} × {alto_salida} px")

            # Guardar en archivo PNG temporal para el visor de GTK
            if self.preview_temporal:
                try:
                    os.remove(self.preview_temporal)
                except OSError:
                    pass

            fd, ruta_temporal = tempfile.mkstemp(
                suffix=".png", prefix="effectpic_"
            )
            os.close(fd)

            resultado.save(ruta_temporal, "PNG")
            self.preview_temporal = ruta_temporal
            self.imagen.set_filename(ruta_temporal)

        except Exception as e:
            print("Error generando preview:", e)

    def comparar_cambiado(self, boton):
        self.modo_comparando = boton.get_active()
        self.generar_preview()

    # ================================================================
    # HISTORIAL (DESHACER / REHACER / RESTAURAR)
    # ================================================================

    def obtener_estado_actual(self):
        modo_idx = 0
        if self.modo_recortar.get_active():
            modo_idx = 1
        elif self.modo_ia.get_active():
            modo_idx = 2
        elif self.modo_color.get_active():
            modo_idx = 3

        return {
            "formato": self.selector.get_selected(),
            "modo": modo_idx,
            "blur": self.blur_valor,
            "zoom": self.zoom_recorte,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "brillo": self.brillo_valor,
            "contraste": self.contraste_valor,
            "saturacion": self.saturacion_valor,
            "preset": self.preset_selector.get_selected(),
        }

    def aplicar_estado(self, estado):
        self._bloqueo_historial = True

        self.selector.set_selected(estado["formato"])

        modo_idx = estado["modo"]
        if modo_idx == 1:
            self.modo_recortar.set_active(True)
        elif modo_idx == 2:
            self.modo_ia.set_active(True)
        elif modo_idx == 3:
            self.modo_color.set_active(True)
        else:
            self.modo_blur.set_active(True)

        self.blur_ajuste.set_value(estado["blur"])
        self.blur_valor = estado["blur"]

        self.zoom_ajuste.set_value(estado["zoom"] * 100.0)
        self.zoom_recorte = estado["zoom"]

        self.offset_x = estado["offset_x"]
        self.offset_y = estado["offset_y"]

        self.brillo_ajuste.set_value(estado["brillo"])
        self.brillo_valor = estado["brillo"]

        self.contraste_ajuste.set_value(estado["contraste"])
        self.contraste_valor = estado["contraste"]

        self.saturacion_ajuste.set_value(estado["saturacion"])
        self.saturacion_valor = estado["saturacion"]

        self.preset_selector.set_selected(estado["preset"])

        self._bloqueo_historial = False
        self.generar_preview()
        self.actualizar_botones_historial()

    def guardar_estado(self, inmediato=False):
        if self._bloqueo_historial or not self.ruta_actual:
            return

        if self._timer_historial:
            GLib.source_remove(self._timer_historial)
            self._timer_historial = None

        if inmediato:
            self._ejecutar_guardado_historial()
        else:
            # Debounce de 350 ms para no inundar el historial al mover sliders
            self._timer_historial = GLib.timeout_add(
                350, self._ejecutar_guardado_historial
            )

    def _ejecutar_guardado_historial(self):
        self._timer_historial = None
        estado = self.obtener_estado_actual()

        # Evitar guardar duplicados consecutivos
        if self.historial_deshacer and self.historial_deshacer[-1] == estado:
            return False

        self.historial_deshacer.append(estado)
        if len(self.historial_deshacer) > 40:
            self.historial_deshacer.pop(0)

        # Cada cambio nuevo invalida el rehacer
        self.historial_rehacer.clear()
        self.actualizar_botones_historial()
        return False

    def deshacer(self, boton):
        if len(self.historial_deshacer) > 1:
            actual = self.historial_deshacer.pop()
            self.historial_rehacer.append(actual)
            anterior = self.historial_deshacer[-1]
            self.aplicar_estado(anterior)

    def rehacer(self, boton):
        if self.historial_rehacer:
            siguiente = self.historial_rehacer.pop()
            self.historial_deshacer.append(siguiente)
            self.aplicar_estado(siguiente)

    def restaurar_original(self, boton):
        """Restaura todos los parámetros al estado por defecto."""
        estado_defecto = {
            "formato": 0,
            "modo": 0,
            "blur": 50,
            "zoom": 1.0,
            "offset_x": 0.0,
            "offset_y": 0.0,
            "brillo": 0,
            "contraste": 0,
            "saturacion": 0,
            "preset": 0,
        }
        self.aplicar_estado(estado_defecto)
        self.guardar_estado(inmediato=True)

    def actualizar_botones_historial(self):
        self.boton_deshacer.set_sensitive(len(self.historial_deshacer) > 1)
        self.boton_rehacer.set_sensitive(len(self.historial_rehacer) > 0)

    # ================================================================
    # EXPORTACIÓN
    # ================================================================

    def exportar_imagen(self, boton):
        if not self.ruta_actual:
            return

        _, dimensiones = self.obtener_formato_actual()
        ancho_salida, alto_salida = dimensiones

        carpeta_original = os.path.dirname(self.ruta_actual)
        nombre_original = os.path.splitext(os.path.basename(self.ruta_actual))[0]
        sufijo = f"{ancho_salida}x{alto_salida}"
        nombre_sugerido = f"{nombre_original}_{sufijo}.jpg"

        dialogo = Gtk.FileDialog()
        dialogo.set_title("Exportar imagen")

        archivo_sugerido = Gio.File.new_for_path(
            os.path.join(carpeta_original, nombre_sugerido)
        )
        dialogo.set_initial_file(archivo_sugerido)
        dialogo.save(self, None, self.exportacion_seleccionada)

    def exportacion_seleccionada(self, dialogo, resultado):
        try:
            archivo = dialogo.save_finish(resultado)
            ruta_salida = archivo.get_path()

            if not ruta_salida:
                return

            if not ruta_salida.lower().endswith((".jpg", ".jpeg")):
                ruta_salida += ".jpg"

            _, dimensiones = self.obtener_formato_actual()
            ancho_salida, alto_salida = dimensiones

            # Siempre exportamos procesando desde el archivo original en HD
            if self.modo_recortar.get_active():
                resultado_final = self.generar_imagen_recorte(
                    self.ruta_actual, ancho_salida, alto_salida
                )
            elif self.modo_ia.get_active():
                resultado_final = self.generar_imagen_bokeh_ia(
                    self.ruta_actual, ancho_salida, alto_salida
                )
            elif self.modo_color.get_active():
                resultado_final = self.generar_imagen_color(
                    self.ruta_actual, ancho_salida, alto_salida
                )
            else:
                resultado_final = self.generar_imagen_blur(
                    self.ruta_actual, ancho_salida, alto_salida
                )

            resultado_final.save(
                ruta_salida,
                "JPEG",
                quality=95,
                optimize=True,
                subsampling=0
            )

            print(f"Imagen exportada con éxito: {ruta_salida}")
            self.mostrar_exportacion_correcta(ruta_salida)

        except GLib.Error:
            pass
        except Exception as e:
            print("Error exportando imagen:", e)

    def mostrar_exportacion_correcta(self, ruta):
        dialogo = Gtk.AlertDialog()
        dialogo.set_message("Imagen exportada correctamente")
        dialogo.set_detail(os.path.basename(ruta))
        dialogo.set_buttons(["Aceptar"])
        dialogo.show(self)


if __name__ == "__main__":
    app = EffectPic()
    app.run()