#!/usr/bin/env python3

import gi
gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, Gio, GdkPixbuf


FORMATOS = {
    "Social · Cuadrado 1:1": (1, 1),
    "Social · Retrato 4:5": (4, 5),
    "Social · Vertical 9:16": (9, 16),
    "Social · Wide 16:9": (16, 9),
}


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
            ruta = files[0].get_path()
            if ruta:
                self.ventana.cargar_imagen(ruta)


class EffectPicWindow(Gtk.ApplicationWindow):

    def __init__(self, app):
        super().__init__(application=app)

        self.set_title("EffectPic")
        self.set_default_size(1100, 800)

        self.ruta_actual = None

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

        self.info = Gtk.Label(label="Ninguna imagen abierta")
        self.info.set_hexpand(True)
        self.info.set_halign(Gtk.Align.END)

        barra.append(self.info)

        # ============================================================
        # ÁREA GENERAL DE PREVISUALIZACIÓN
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

        self.marco = Gtk.Frame()

        self.marco.set_halign(Gtk.Align.CENTER)
        self.marco.set_valign(Gtk.Align.CENTER)

        self.area_preview.append(self.marco)

        self.imagen = Gtk.Picture()

        self.imagen.set_can_shrink(True)
        self.imagen.set_content_fit(Gtk.ContentFit.CONTAIN)

        self.imagen.set_hexpand(True)
        self.imagen.set_vexpand(True)

        self.marco.set_child(self.imagen)

        # Escuchamos cambios de tamaño del área disponible.
        self.area_preview.connect(
            "notify::width",
            self.recalcular_lienzo
        )

        self.area_preview.connect(
            "notify::height",
            self.recalcular_lienzo
        )

        # ============================================================
        # PANEL INFERIOR
        # ============================================================

        separador = Gtk.Separator(
            orientation=Gtk.Orientation.HORIZONTAL
        )
        principal.append(separador)

        panel_inferior = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=18
        )

        principal.append(panel_inferior)

        panel_inferior.append(
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

        self.modo_recortar.set_group(self.modo_blur)
        self.modo_color.set_group(self.modo_blur)

        self.modo_blur.set_active(True)

        # Todavía no funcionan.
        self.modo_blur.set_sensitive(False)
        self.modo_recortar.set_sensitive(False)
        self.modo_color.set_sensitive(False)

        panel_inferior.append(self.modo_blur)
        panel_inferior.append(self.modo_recortar)
        panel_inferior.append(self.modo_color)

        espacio = Gtk.Box()
        espacio.set_hexpand(True)
        panel_inferior.append(espacio)

        self.boton_exportar = Gtk.Button(
            label="Exportar"
        )

        self.boton_exportar.set_sensitive(False)

        panel_inferior.append(self.boton_exportar)

    # ================================================================
    # ABRIR IMAGEN
    # ================================================================

    def abrir_imagen(self, boton):

        dialogo = Gtk.FileDialog()
        dialogo.set_title("Abrir imagen")

        filtro = Gtk.FileFilter()
        filtro.set_name("Imágenes")

        filtro.add_mime_type("image/jpeg")
        filtro.add_mime_type("image/png")
        filtro.add_mime_type("image/webp")

        filtros = Gio.ListStore.new(Gtk.FileFilter)
        filtros.append(filtro)

        dialogo.set_filters(filtros)
        dialogo.set_default_filter(filtro)

        dialogo.open(
            self,
            None,
            self.imagen_seleccionada
        )

    def imagen_seleccionada(self, dialogo, resultado):

        try:
            archivo = dialogo.open_finish(resultado)
            ruta = archivo.get_path()

            if ruta:
                self.cargar_imagen(ruta)

        except Exception as e:
            print("Selección cancelada o error:", e)

    # ================================================================
    # CARGAR IMAGEN
    # ================================================================

    def cargar_imagen(self, ruta):

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(ruta)

            ancho = pixbuf.get_width()
            alto = pixbuf.get_height()

            self.ruta_actual = ruta

            self.imagen.set_filename(ruta)

            self.info.set_text(
                f"{ancho} × {alto} px"
            )

            nombre = ruta.split("/")[-1]

            self.set_title(
                f"EffectPic — {nombre}"
            )

        except Exception as e:
            print("Error cargando imagen:", e)

    # ================================================================
    # CAMBIO DE FORMATO
    # ================================================================

    def formato_cambiado(self, selector, parametro):

        self.recalcular_lienzo()

    # ================================================================
    # CALCULAR TAMAÑO DEL LIENZO
    # ================================================================

    def recalcular_lienzo(self, *args):

        ancho_disponible = self.area_preview.get_width()
        alto_disponible = self.area_preview.get_height()

        if ancho_disponible <= 0 or alto_disponible <= 0:
            return

        indice = self.selector.get_selected()

        nombres = list(FORMATOS.keys())

        if indice >= len(nombres):
            return

        nombre_formato = nombres[indice]

        proporcion_ancho, proporcion_alto = FORMATOS[
            nombre_formato
        ]

        ratio = proporcion_ancho / proporcion_alto

        # Dejamos un pequeño margen alrededor del lienzo.
        max_ancho = ancho_disponible - 30
        max_alto = alto_disponible - 30

        if max_ancho <= 0 or max_alto <= 0:
            return

        # Intentamos ocupar primero todo el ancho disponible.
        nuevo_ancho = max_ancho
        nuevo_alto = int(nuevo_ancho / ratio)

        # Si no entra verticalmente, calculamos desde la altura.
        if nuevo_alto > max_alto:
            nuevo_alto = max_alto
            nuevo_ancho = int(nuevo_alto * ratio)

        self.marco.set_size_request(
            nuevo_ancho,
            nuevo_alto
        )


app = EffectPic()
app.run()