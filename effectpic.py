#!/usr/bin/env python3

import gi
gi.require_version("Gtk", "4.0")

import os
import tempfile

from gi.repository import Gtk, Gio, GdkPixbuf, GLib
from PIL import Image, ImageOps, ImageFilter


# Nombre visible -> resolución REAL de salida
FORMATOS = {
    "Social · Cuadrado 1:1": (1080, 1080),
    "Social · Retrato 4:5": (1080, 1350),
    "Social · Vertical 9:16": (1080, 1920),
    "Social · Wide 16:9": (1920, 1080),
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
        self.preview_temporal = None

        # Estado del recorte interactivo
        self.zoom_recorte = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.drag_inicio_x = 0.0
        self.drag_inicio_y = 0.0
        self.drag_offset_x = 0.0
        self.drag_offset_y = 0.0

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
            self.exportar_imagen
        )

        panel.append(self.boton_exportar)

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

        filtros = Gio.ListStore.new(
            Gtk.FileFilter
        )

        filtros.append(filtro)

        dialogo.set_filters(filtros)
        dialogo.set_default_filter(filtro)

        dialogo.open(
            self,
            None,
            self.imagen_seleccionada
        )

    def imagen_seleccionada(
        self,
        dialogo,
        resultado
    ):

        try:

            archivo = dialogo.open_finish(
                resultado
            )

            ruta = archivo.get_path()

            if ruta:
                self.cargar_imagen(ruta)

        except GLib.Error:
            # Cancelar el diálogo no es un error real.
            pass

        except Exception as e:
            print(
                "Error seleccionando imagen:",
                e
            )

    # ================================================================
    # CARGAR IMAGEN
    # ================================================================

    def cargar_imagen(self, ruta):

        try:

            pixbuf = GdkPixbuf.Pixbuf.new_from_file(
                ruta
            )

            ancho = pixbuf.get_width()
            alto = pixbuf.get_height()

            self.ruta_actual = ruta

            self.info.set_text(
                f"Original: {ancho} × {alto} px"
            )

            nombre = os.path.basename(ruta)

            self.set_title(
                f"EffectPic — {nombre}"
            )

            self.generar_preview()

            self.boton_exportar.set_sensitive(True)
        except Exception as e:

            print(
                "Error cargando imagen:",
                e
            )

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

    def zoom_cambiado(self, slider):

        self.zoom_recorte = (
            slider.get_value() / 100.0
        )

        if (
            self.ruta_actual
            and self.modo_recortar.get_active()
        ):
            self.generar_preview()

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

    def blur_cambiado(self, slider):

        self.blur_valor = slider.get_value()

        if (
            self.ruta_actual
            and self.modo_blur.get_active()
        ):
            self.generar_preview()

    # ================================================================
    # MOTOR EFFECTPIC
    # ================================================================

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

        # Ejemplo: foto_9x16.jpg
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

app = EffectPic()
app.run()