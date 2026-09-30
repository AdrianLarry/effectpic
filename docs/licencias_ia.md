# Documentación Oficial de Licencias y Estado de Distribución: EffectPic

Este documento detalla y respalda formalmente las licencias aplicables al código fuente, los archivos de pesos binarios (modelos ONNX), el árbol de dependencias de tiempo de ejecución y el **estado de validación del paquete de distribución** para **EffectPic**.

---

## 1. Distinción Rigurosa: Hechos Documentados vs. Estatus de los Pesos

| Componente | Hechos Oficiales Documentados | Estatus Legal de los Pesos / Matices |
| :--- | :--- | :--- |
| **Código `rembg`** | Archivo `LICENSE` bajo **MIT License** (Copyright (c) 2020 Daniel Gatis). | La licencia MIT aplica exclusivamente al código fuente del software envoltorio de Python. **No existe una declaración explícita de Daniel Gatis que declare los pesos binarios `.onnx` bajo licencia MIT.** |
| **Código `xuebinqin/U-2-Net`** | Archivo `LICENSE` bajo **Apache License 2.0** (Copyright (c) 2020 Xuebin Qin). | Permisiva estándar para el código fuente del modelo. |
| **Pesos binarios `u2net.onnx`** | Conversión directa a formato ONNX de los checkpoints `u2net.pth` entrenados sobre el dataset **DUTS-TR**. Alojados públicamente en los lanzamientos de GitHub de `rembg` y Hugging Face. | **Sin licencia explícita para los pesos**: Ni Xuebin Qin ni Daniel Gatis han emitido una declaración formal o contrato de cesión comercial sobre los pesos `.onnx`. El modelo general `u2net` se distribuye sin un EULA prohibitivo (a diferencia de `u2net_portrait` o `isnet`), pero no puede afirmarse que esté cubierto por MIT ni que cuente con garantía legal de redistribución comercial. |
| **Pesos `isnet-general-use.onnx`** | Entrenados sobre el dataset **DIS5K**. | **Prohibición comercial documentada**: El acuerdo oficial `DIS5K-Dataset-Terms-of-Use.pdf` prohíbe explícitamente cualquier uso comercial (*"strictly prohibited for commercial use without prior written consent"*). |
| **Pesos `bria-rmbg`** | Licencia oficial **CC BY-NC 4.0** declarada por BRIA AI. | Estrictamente no comercial. |

---

## 2. Dependencias de Ejecución (Versiones Pinned Verificadas en CPU)

Probado y fijado en **Ubuntu 24.04 LTS (x86_64, Python 3.12)**:

| Dependencia | Versión Fijada | Licencia del Código |
| :--- | :--- | :--- |
| **`rembg`** | `2.0.85` | **MIT License** |
| **`onnxruntime`** | `1.30.0` | **MIT License** |
| **`pillow`** | `12.3.0` | **HPND License** (Estilo MIT) |
| **`numpy`** | `2.5.3` | **BSD 3-Clause** |
| **`scipy`** | `1.18.1` | **BSD 3-Clause** |
| **`numba`** | `0.67.0` | **BSD 2-Clause** |
| **`llvmlite`** | `0.49.0` | **BSD 2-Clause** |
| **`PyMatting`** | `1.1.16` | **MIT License** |
| **`pooch`** | `1.9.0` | **BSD 3-Clause** |
| **`GTK4` / `PyGObject`** | `4.14.2` / `3.48.2` | **LGPL-2.1-or-later** |

---

## 3. Metodología de Medición y Consumo de Memoria

* **Procesador (CPU)**: AMD Ryzen 7 5700G (8 núcleos / 16 hilos, base 3.8 GHz, boost 4.6 GHz).
* **Consumo de Memoria (`ru_maxrss`)**:
  En sistemas Linux, el valor devuelto por `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` representa el **pico histórico máximo de memoria residente (RSS high-water mark)** alcanzado por el proceso desde su inicio hasta el momento de la consulta (expresado en kilobytes). No mide la memoria viva instantánea liberada por el recolector de basura, sino la cota superior física demandada al sistema operativo durante la inferencia.
* **Medición de Tiempos**:
  Determinada mediante `time.perf_counter()` en CPU con tensores nativos de ONNX Runtime, promediando 20 iteraciones para la previsualización y 5 para la exportación completa.

---

## 4. Estado de Validación del Paquete de Distribución (`.deb`)

* **Estado**: **PENDIENTE de validación en máquina virtual (VM) o sistema limpio**.
* **Alcance de las pruebas locales ejecutadas**:
  Las pruebas realizadas en el entorno de desarrollo (`test_clean_install.sh`) constituyen una **prueba preliminar parcial en espacio de usuario**, con las siguientes limitaciones explícitas:
  1. `dpkg -x` únicamente verifica la extracción de archivos, no el proceso real de instalación mediante `apt` o `dpkg -i` (scripts `preinst`/`postinst`, dependencias del gestor de paquetes).
  2. El modelo de prueba fue copiado desde la caché local del usuario; no se evaluó la descarga autónoma desde la red en un sistema virgen.
  3. El bloqueo de red mediante `socket.connect` es una simulación interna en Python, no un aislamiento de red a nivel de interfaz del sistema operativo.
  4. No se verificó la integración real con el entorno de escritorio (lanzador en el menú de aplicaciones GNOME ni asociaciones MIME).
* **Requisito para aprobación final**:
  Instalación completa mediante `sudo apt install ./effectpic_1.0.0_all.deb` en una instalación limpia de Ubuntu 24.04 (en VM o hardware dedicado), validando:
  - Primer arranque y descarga guiada de dependencias/modelo.
  - Apertura desde el acceso directo del menú de aplicaciones de GNOME.
  - Segundo arranque en modo avión (sin interfaz de red) con verificación de funcionamiento local offline.
