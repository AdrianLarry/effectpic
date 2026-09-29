#!/usr/bin/env python3

import gi
gi.require_version("Gtk", "4.0")

import copy
import os
import re
import tempfile

from gi.repository import Gtk, Gio, Gdk, GdkPixbuf, GLib
from PIL import Image, ImageOps, ImageFilter, ImageEnhance


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
        self.modo = "recortar" if win.modo_recortar.get_active() else "blur"
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
        self.set_default_size(1100, 800)

        self.ruta_actual = None
        self.preview_temporal = None
        self.preview_temporal_original = None
        self.tecla_comparar_activa = False

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
        principal.set_margin_start(12)
        principal.set_margin_end(12)

        self.set_child(principal)

        # ============================================================
        # BARRA SUPERIOR
        # ============================================================

        barra = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10
        )

        principal.append(barra)

        boton_abrir = Gtk.Button(label="Abrir imagen")
        boton_abrir.connect("clicked", self.abrir_imagen)
        barra.append(boton_abrir)

        # Botones Deshacer y Rehacer
        self.boton_deshacer = Gtk.Button(label="Deshacer")
        self.boton_deshacer.set_tooltip_text("Deshacer última acción (Ctrl+Z)")
        self.boton_deshacer.set_sensitive(False)
        self.boton_deshacer.connect("clicked", lambda b: self.deshacer())
        barra.append(self.boton_deshacer)

        self.boton_rehacer = Gtk.Button(label="Rehacer")
        self.boton_rehacer.set_tooltip_text("Rehacer última acción (Ctrl+Shift+Z)")
        self.boton_rehacer.set_sensitive(False)
        self.boton_rehacer.connect("clicked", lambda b: self.rehacer())
        barra.append(self.boton_rehacer)

        self.boton_restaurar = Gtk.Button(label="Restaurar")
        self.boton_restaurar.set_tooltip_text("Restaurar al estado original")
        self.boton_restaurar.set_sensitive(False)
        self.boton_restaurar.connect("clicked", lambda b: self.restaurar_original())
        barra.append(self.boton_restaurar)

        self.boton_comparar = Gtk.ToggleButton(label="Comparar")
        self.boton_comparar.set_tooltip_text(
            "Alternar o mantener [Espacio] para ver original"
        )
        self.boton_comparar.set_sensitive(False)
        self.boton_comparar.connect(
            "toggled",
            self.comparar_toggled
        )
        barra.append(self.boton_comparar)

        separador_barra = Gtk.Separator(
            orientation=Gtk.Orientation.VERTICAL
        )
        barra.append(separador_barra)

        barra.append(Gtk.Label(label="Formato:"))

        self.selector = Gtk.DropDown.new_from_strings(
            list(FORMATOS.keys())
        )

        self.selector.set_selected(0)

        self.selector.connect(
            "notify::selected",
            self.formato_cambiado
        )

        barra.append(self.selector)

        self.info = Gtk.Label(
            label="Ninguna imagen abierta"
        )

        self.info.set_hexpand(True)
        self.info.set_halign(Gtk.Align.END)

        barra.append(self.info)

        # ============================================================
        # ÁREA DE PREVISUALIZACIÓN
        # ============================================================

        self.area_preview = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL
        )

        self.area_preview.set_hexpand(True)
        self.area_preview.set_vexpand(True)

        self.area_preview.set_halign(Gtk.Align.FILL)
        self.area_preview.set_valign(Gtk.Align.FILL)

        principal.append(self.area_preview)

        # ============================================================
        # LIENZO
        # ============================================================

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

        self.gesto_arrastre = Gtk.GestureDrag()
        self.gesto_arrastre.connect(
            "drag-begin",
            self.arrastre_iniciado
        )
        self.gesto_arrastre.connect(
            "drag-update",
            self.arrastre_actualizado
        )
        self.gesto_arrastre.connect(
            "drag-end",
            self.arrastre_terminado
        )
        self.imagen.add_controller(
            self.gesto_arrastre
        )

        self.area_preview.connect(
            "notify::width",
            self.recalcular_lienzo
        )

        self.area_preview.connect(
            "notify::height",
            self.recalcular_lienzo
        )

        # ============================================================
        # TIRA DE MINIATURAS (MODO CARRUSEL)
        # ============================================================

        self.scroll_carrusel = Gtk.ScrolledWindow()
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
        self.caja_tira.set_margin_top(4)
        self.caja_tira.set_margin_bottom(4)

        self.scroll_carrusel.set_child(self.caja_tira)
        principal.append(self.scroll_carrusel)

        # ============================================================
        # PANEL INFERIOR
        # ============================================================

        separador = Gtk.Separator(
            orientation=Gtk.Orientation.HORIZONTAL
        )

        principal.append(separador)

        panel = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=18
        )

        principal.append(panel)

        panel.append(
            Gtk.Label(label="Modo:")
        )

        self.modo_blur = Gtk.CheckButton(
            label="Ajustar + Blur"
        )

        self.modo_recortar = Gtk.CheckButton(
            label="Recortar"
        )

        self.modo_color = Gtk.CheckButton(
            label="Ajustar + Color"
        )

        self.modo_recortar.set_group(
            self.modo_blur
        )

        self.modo_color.set_group(
            self.modo_blur
        )

        self.modo_blur.set_active(True)

        self.modo_blur.connect("toggled", self.modo_cambiado)
        self.modo_recortar.connect("toggled", self.modo_cambiado)

        # Blur ya funciona.
        self.modo_blur.set_sensitive(True)

        # Los otros dos todavía no.
        self.modo_recortar.set_sensitive(True)
        self.modo_color.set_sensitive(False)

        panel.append(self.modo_blur)
        panel.append(self.modo_recortar)
        panel.append(self.modo_color)

        self.blur_valor = 50

        self.blur_ajuste = Gtk.Adjustment(
            value=50,
            lower=0,
            upper=100,
            step_increment=1,
            page_increment=10,
            page_size=0
        )

        self.blur_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.blur_ajuste
        )

        self.blur_slider.set_size_request(180, -1)
        self.blur_slider.set_draw_value(True)
        self.blur_slider.set_digits(0)

        self.blur_slider.connect(
            "value-changed",
            self.blur_cambiado
        )

        gesto_blur = Gtk.GestureDrag()
        gesto_blur.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesto_blur.connect("drag-begin", self._slider_drag_begin)
        gesto_blur.connect("drag-end", self._slider_drag_end)
        self.blur_slider.add_controller(gesto_blur)

        panel.append(Gtk.Label(label="Blur:"))
        panel.append(self.blur_slider)

        self.zoom_label = Gtk.Label(label="Zoom:")
        self.zoom_ajuste = Gtk.Adjustment(
            value=100,
            lower=100,
            upper=300,
            step_increment=1,
            page_increment=10,
            page_size=0
        )
        self.zoom_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.zoom_ajuste
        )
        self.zoom_slider.set_size_request(180, -1)
        self.zoom_slider.set_draw_value(True)
        self.zoom_slider.set_digits(0)
        self.zoom_slider.connect(
            "value-changed",
            self.zoom_cambiado
        )

        gesto_zoom = Gtk.GestureDrag()
        gesto_zoom.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesto_zoom.connect("drag-begin", self._slider_drag_begin)
        gesto_zoom.connect("drag-end", self._slider_drag_end)
        self.zoom_slider.add_controller(gesto_zoom)

        self.boton_centrar = Gtk.Button(
            label="Centrar"
        )
        self.boton_centrar.connect(
            "clicked",
            self.centrar_recorte
        )

        self.zoom_label.set_sensitive(False)
        self.zoom_slider.set_sensitive(False)
        self.boton_centrar.set_sensitive(False)

        panel.append(self.zoom_label)
        panel.append(self.zoom_slider)
        panel.append(self.boton_centrar)

        espacio = Gtk.Box()
        espacio.set_hexpand(True)

        panel.append(espacio)

        self.boton_exportar = Gtk.Button(
            label="Exportar"
        )

        self.boton_exportar.set_sensitive(False)

        self.boton_exportar.connect(
            "clicked",
            self.exportar_click
        )

        panel.append(self.boton_exportar)

        # ============================================================
        # PANEL DE RETOQUES (BRILLO, CONTRASTE, SATURACIÓN)
        # ============================================================

        panel_ajustes = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=14
        )

        principal.append(panel_ajustes)

        panel_ajustes.append(
            Gtk.Label(label="Retoque:")
        )

        self.selector_presets = Gtk.DropDown.new_from_strings(
            list(PRESETS_RETOQUE.keys())
        )
        self.selector_presets.set_selected(0)
        self.selector_presets.set_sensitive(False)
        self.selector_presets.set_tooltip_text("Estilos y filtros de retoque rápido")
        self.selector_presets.connect(
            "notify::selected",
            self.preset_cambiado
        )
        panel_ajustes.append(self.selector_presets)

        # Brillo (-100 a +100, defecto 0)
        self.brillo_ajuste = Gtk.Adjustment(
            value=0,
            lower=-100,
            upper=100,
            step_increment=1,
            page_increment=10,
            page_size=0
        )
        self.brillo_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.brillo_ajuste
        )
        self.brillo_slider.set_size_request(130, -1)
        self.brillo_slider.set_draw_value(True)
        self.brillo_slider.set_digits(0)
        self.brillo_slider.connect(
            "value-changed",
            self.brillo_cambiado
        )

        panel_ajustes.append(Gtk.Label(label="Brillo:"))
        panel_ajustes.append(self.brillo_slider)

        # Contraste (-100 a +100, defecto 0)
        self.contraste_ajuste = Gtk.Adjustment(
            value=0,
            lower=-100,
            upper=100,
            step_increment=1,
            page_increment=10,
            page_size=0
        )
        self.contraste_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.contraste_ajuste
        )
        self.contraste_slider.set_size_request(130, -1)
        self.contraste_slider.set_draw_value(True)
        self.contraste_slider.set_digits(0)
        self.contraste_slider.connect(
            "value-changed",
            self.contraste_cambiado
        )

        panel_ajustes.append(Gtk.Label(label="Contraste:"))
        panel_ajustes.append(self.contraste_slider)

        # Saturación (-100 a +100, defecto 0)
        self.saturacion_ajuste = Gtk.Adjustment(
            value=0,
            lower=-100,
            upper=100,
            step_increment=1,
            page_increment=10,
            page_size=0
        )
        self.saturacion_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.saturacion_ajuste
        )
        self.saturacion_slider.set_size_request(130, -1)
        self.saturacion_slider.set_draw_value(True)
        self.saturacion_slider.set_digits(0)
        self.saturacion_slider.connect(
            "value-changed",
            self.saturacion_cambiado
        )

        panel_ajustes.append(Gtk.Label(label="Saturación:"))
        panel_ajustes.append(self.saturacion_slider)

        # Gestos de arrastre para registrar 1 solo paso al soltar
        for s in (self.brillo_slider, self.contraste_slider, self.saturacion_slider):
            gesto = Gtk.GestureDrag()
            gesto.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            gesto.connect("drag-begin", self._slider_drag_begin)
            gesto.connect("drag-end", self._slider_drag_end)
            s.add_controller(gesto)

        self.boton_reset_ajustes = Gtk.Button(
            label="Reiniciar retoques"
        )
        self.boton_reset_ajustes.set_tooltip_text(
            "Restablecer brillo, contraste y saturación a 0"
        )
        self.boton_reset_ajustes.set_sensitive(False)
        self.boton_reset_ajustes.connect(
            "clicked",
            self.reiniciar_ajustes_color
        )
        panel_ajustes.append(self.boton_reset_ajustes)

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

        self.boton_exportar.set_sensitive(True)
        self.actualizar_sensibilidad_undo_redo()
        self.actualizar_interfaz_carrusel()

        if len(self.carrusel) > 1:
            self.set_title(
                f"EffectPic — Carrusel [1/{len(self.carrusel)}] — {self.carrusel[0].nombre}"
            )
        else:
            self.set_title(f"EffectPic — {self.carrusel[0].nombre}")

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
                self.info.set_text("Ninguna imagen abierta")
                self.set_title("EffectPic")
                self.boton_exportar.set_sensitive(False)
                self.boton_exportar.set_label("Exportar")
                self.imagen.set_filename(None)
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

        # Los botones agrupados disparan "toggled" tanto al
        # activarse como al desactivarse.
        if not boton.get_active():
            return

        es_recorte = self.modo_recortar.get_active()
        self.zoom_label.set_sensitive(es_recorte)
        self.zoom_slider.set_sensitive(es_recorte)
        self.boton_centrar.set_sensitive(es_recorte)

        self.blur_slider.set_sensitive(
            self.modo_blur.get_active()
        )

        if self.ruta_actual:
            self.generar_preview()

        self.registrar_cambio()

    def zoom_cambiado(self, slider):

        self.zoom_recorte = (
            slider.get_value() / 100.0
        )

        if (
            self.ruta_actual
            and self.modo_recortar.get_active()
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
            and self.modo_recortar.get_active()
        ):
            self.generar_preview()

        self.registrar_cambio()

    def arrastre_iniciado(
        self,
        gesto,
        x,
        y
    ):

        if not self.modo_recortar.get_active():
            return

        self.drag_offset_x = self.offset_x
        self.drag_offset_y = self.offset_y

    def arrastre_actualizado(
        self,
        gesto,
        desplazamiento_x,
        desplazamiento_y
    ):

        if not self.modo_recortar.get_active():
            return

        ancho = self.imagen.get_width()
        alto = self.imagen.get_height()

        if ancho <= 0 or alto <= 0:
            return

        # Arrastramos la FOTO, no la ventana de recorte.
        # Por eso invertimos el sentido respecto del crop.
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

        if not self.modo_recortar.get_active():
            return

        self.registrar_cambio()

    def blur_cambiado(self, slider):

        self.blur_valor = slider.get_value()

        if (
            self.ruta_actual
            and self.modo_blur.get_active()
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
        return {
            "formato_idx": self.selector.get_selected(),
            "modo": "recortar" if self.modo_recortar.get_active() else "blur",
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
            es_recorte = (estado["modo"] == "recortar")
            if es_recorte:
                if not self.modo_recortar.get_active():
                    self.modo_recortar.set_active(True)
            else:
                if not self.modo_blur.get_active():
                    self.modo_blur.set_active(True)

            self.zoom_label.set_sensitive(es_recorte)
            self.zoom_slider.set_sensitive(es_recorte)
            self.boton_centrar.set_sensitive(es_recorte)
            self.blur_slider.set_sensitive(not es_recorte)

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
        with Image.open(item.ruta) as original:
            original = ImageOps.exif_transpose(original).convert("RGB")
            original = self._aplicar_mejoras_valores(
                original,
                item.brillo,
                item.contraste,
                item.saturacion
            )

            tamaño_salida = (ancho_salida, alto_salida)

            if item.modo == "recortar":
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

            else:  # "blur"
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