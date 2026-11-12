# PlutoRadar AESS — actualización de la interfaz

## Cambios

- En **Monitor → Espectro Doppler**, el selector **Escala** cambia en tiempo real el semiancho visible: ±90, ±180, ±500 Hz; ±1, ±2, ±5, ±10 o ±20 kHz.
- El selector **Unidades** presenta la frecuencia en **Auto / Hz / kHz / MHz / GHz** en el espectro, el espectrograma, la lectura Doppler y su historial, sin convertir erróneamente los datos físicos.
- El motor procesa la banda elegida y reduce los puntos del gráfico cuando es necesario, conservando los máximos espectrales para no perder picos al ampliar el campo visual.
- En **Análisis** hay una nueva gráfica de **respuesta teórica del filtro FIR de rechazo** con vistas de 400–600 Hz, 0–2 kHz y 0–20 kHz. Se estima con una ventana Hamming; según el archivo GRC suministrado, el rechazo está entre **495 y 505 Hz**, con banda de transición de **5 Hz**.
- Los archivos de Windows verifican realmente que Tkinter puede abrir una ventana y que NumPy, Pillow y ZeroMQ son importables. Incluye reparación explícita del entorno virtual.

## Límites importantes

- La adquisición ZMQ de este proyecto muestrea a **48 kS/s**, por lo que solo hay datos de banda base hasta **±24 kHz** (límite de Nyquist). Seleccionar MHz o GHz únicamente cambia las **unidades de presentación**. No aumenta la frecuencia capturada ni modifica la portadora de 2.4 GHz.
- En el GRC original, `zeromq_pub_sink_0` (puerto **5557**) recibe la salida de `low_pass_filter_0`, **antes** del bloque `band_reject_filter_0`. Por eso la gráfica del filtro es una **estimación matemática**, NO una medición real de su atenuación. Para obtener respuesta medida antes/después harían falta dos puntos de adquisición y una prueba con señal conocida; esta actualización no los inventa.
- El LPF de GNU Radio usa un corte dependiente de `tono_frec * 2`, lo cual limita las componentes que llegan al stream ZMQ RX aunque la escala gráfica muestre frecuencias mayores.
- Cambiar la escala visible tampoco cambia el algoritmo de detección Doppler, que sigue buscando picos en el intervalo preexistente de 6 a 180 Hz.
- Para cambiar el **rechazo físico** (frecuencia central o ancho), hay que editar la configuración del filtro en GNU Radio; esta versión solo lo visualiza.

## Instalación en Windows

1. **Extrae este ZIP en una carpeta NUEVA.** No incluyas ni reutilices la carpeta `.venv` anterior; puede contener Pillow dañado.
2. Ejecuta `INSTALAR_WINDOWS.bat` y, cuando termine, `INICIAR_PLUTO.bat`.
3. Mantén GNU Radio y el PlutoSDR encendidos, con ZeroMQ PUB complex64 Bind en `tcp://127.0.0.1:5557` para RX y `tcp://127.0.0.1:5558` para referencia TX.
4. Si la instalación falla con `_imaging`, usa `REPARAR_ENTORNO.bat`. Si falla con **`Can't find a usable init.tcl`**, repara Python desde el instalador oficial, seleccionando el componente **tcl/tk and IDLE**; ni un ZIP ni pip pueden reemplazar esos archivos faltantes de Python.

Puedes comprobar el enlace entre GNU Radio y la aplicación con `COMPROBAR_ZMQ.bat`.

## Archivos modificados

`native_app.py`, `motor_cw.py`, `radar_core.py`, `display_utils.py`, `filter_response.py`, `INSTALAR_WINDOWS.bat`, `INICIAR_PLUTO.bat`, `REPARAR_ENTORNO.bat`, `comprobar_entorno.py`, `README_CAMBIOS.md`.

El `.grc` original, configuración ZeroMQ, seguimiento radial y los archivos de recursos permanecen sin modificación.
