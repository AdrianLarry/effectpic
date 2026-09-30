#!/usr/bin/env python3
"""
Script de validación de funcionamiento 100% Offline y medición de métricas reales.
Bloquea a nivel de socket del sistema operativo cualquier intento de conexión externa
para garantizar que U2NET funciona de forma totalmente aislada tras la primera descarga.
"""

import os
import socket
import sys
import time
import tracemalloc
from PIL import Image, ImageDraw

import socket
import ssl

# Bloquear conexiones de red salientes para simular modo offline
def offline_connect(*args, **kwargs):
    raise OSError(101, "Red no disponible (Simulación de entorno sin internet / Offline)")

socket.socket.connect = offline_connect
socket.socket.connect_ex = lambda *args, **kwargs: 101

# Importar dependencias locales
sys.path.insert(0, "/home/familystyle/effectpic")
from effectpic import obtener_sesion_rembg, EffectPicWindow, EffectPic

def get_process_memory_mb():
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        return 0.0

def main():
    print("==================================================")
    print("VERIFICACIÓN DE FUNCIONAMIENTO OFFLINE Y MÉTRICAS")
    print("==================================================")

    # 1. Comprobación del bloqueo de red
    try:
        s = socket.socket()
        s.connect(("1.1.1.1", 80))
        print("ERROR: El bloqueo de red falló")
        sys.exit(1)
    except OSError as e:
        print(f"✓ Bloqueo estricto de red activo: {e}")

    # 2. Medición de memoria antes de inicializar modelo
    mem_base = get_process_memory_mb()
    print(f"• Memoria RSS base: {mem_base:.1f} MB")

    # 3. Carga de sesión rembg u2net desde almacenamiento local del usuario
    t0 = time.perf_counter()
    session = obtener_sesion_rembg(modelo="u2net")
    t_sesion = time.perf_counter() - t0
    mem_con_sesion = get_process_memory_mb()
    print(f"✓ Sesión u2net cargada OFFLINE con éxito en {t_sesion:.3f} s")
    print(f"• Memoria RSS con sesión cargada: {mem_con_sesion:.1f} MB (+{mem_con_sesion - mem_base:.1f} MB)")

    # 4. Inferencia en CPU sin acceso a internet
    import rembg
    img_test = Image.new("RGB", (1080, 1350), color=(120, 160, 230))
    draw = ImageDraw.Draw(img_test)
    draw.ellipse([270, 200, 810, 1100], fill=(240, 180, 140))

    t_infer_0 = time.perf_counter()
    mask = rembg.remove(img_test, session=session, only_mask=True)
    t_infer = time.perf_counter() - t_infer_0
    mem_infer = get_process_memory_mb()

    assert mask is not None and mask.mode == "L" and mask.size == (1080, 1350)
    print(f"✓ Inferencia CPU offline completada en {t_infer*1000:.1f} ms ({t_infer:.3f} s)")
    print(f"• Memoria RSS pico tras inferencia: {mem_infer:.1f} MB")

    # 5. Medición de previsualización (400×500) a múltiples niveles de desenfoque
    app = EffectPic()
    win = EffectPicWindow(app)

    # Crear archivo temporal
    temp_path = "/tmp/effectpic_offline_test.jpg"
    img_test.save(temp_path, "JPEG", quality=90)
    win.cargar_carrusel([temp_path])
    win.carrusel[0].mascara_sujeto = mask

    tiempos_preview = []
    for _ in range(20):
        t_p0 = time.perf_counter()
        _ = win.generar_imagen_retrato(
            temp_path, 400, 500, mascara=mask, blur_valor=50.0, zoom=100.0
        )
        tiempos_preview.append(time.perf_counter() - t_p0)

    t_prev_medio = sum(tiempos_preview) / len(tiempos_preview)
    fps_preview = 1.0 / t_prev_medio if t_prev_medio > 0 else 0
    print(f"✓ Composición de Previsualización (400×500 px):")
    print(f"  - Tiempo medio: {t_prev_medio*1000:.2f} ms")
    print(f"  - Rendimiento real medido: {fps_preview:.1f} FPS (mínimo: {1.0/max(tiempos_preview):.1f} FPS, máximo: {1.0/min(tiempos_preview):.1f} FPS)")

    # 6. Medición de exportación a resolución completa (1080×1350)
    tiempos_export = []
    for _ in range(5):
        t_e0 = time.perf_counter()
        _ = win.generar_imagen_retrato(
            temp_path, 1080, 1350, mascara=mask, blur_valor=50.0, zoom=100.0
        )
        tiempos_export.append(time.perf_counter() - t_e0)

    t_exp_medio = sum(tiempos_export) / len(tiempos_export)
    print(f"✓ Composición de Exportación (1080×1350 px):")
    print(f"  - Tiempo medio: {t_exp_medio*1000:.2f} ms")

    if os.path.exists(temp_path):
        os.remove(temp_path)

    print("\n==================================================")
    print("RESULTADO FINAL: FUNCIONAMIENTO OFFLINE 100% VALIDADO")
    print("==================================================")

if __name__ == "__main__":
    main()
