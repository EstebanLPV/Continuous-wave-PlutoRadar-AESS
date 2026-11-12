# Continuous-wave-PlutoRadar-AESS

Radar Doppler de onda continua (CW) basado en PlutoSDR y GNU Radio, con procesamiento de señales en tiempo real, análisis espectral, filtrado de rechazo de banda y visualización 2.5D.

## Instalar en Windows

1. Descarga [PlutoRadar-Setup-x64.exe](https://github.com/EstebanLPV/Continuous-wave-PlutoRadar-AESS/releases/latest/download/PlutoRadar-Setup-x64.exe).
2. Ejecuta el instalador en Windows 10 u 11 de 64 bits.
3. Abre **PlutoRadar AESS** desde el menú Inicio.

El instalador incluye Python, Tcl/Tk, NumPy, Pillow y ZeroMQ. Se instala en tu cuenta de Windows y se puede quitar desde **Configuración → Aplicaciones**.

## Usar con PlutoSDR

1. Instala GNU Radio con los bloques IIO (PlutoSDR) y ZeroMQ. Conecta la placa y verifica que GNU Radio pueda comunicarse con ella.
2. En GNU Radio Companion, abre y ejecuta el archivo `radar (1).grc` incluido en el repositorio y en la carpeta de instalación. Puedes abrir la guía de esa carpeta desde el menú Inicio.
3. Abre PlutoRadar AESS y revisa la pestaña **Adquisición**.

| Puerto TCP local | Señal |
| --- | --- |
| 5557 | RX antes del filtro |
| 5558 | Referencia TX |
| 5559 | RX después del filtro |

El diagrama entrega muestras I/Q a 48 kS/s al monitor. Calibra el signo Doppler con un movimiento de prueba. La vista 2.5D muestra movimiento radial relativo y la medición de rechazo depende de la señal de entrada.

## Ejecutar desde código fuente

En Windows, ejecuta `INSTALAR_WINDOWS.bat` y después `INICIAR_PLUTO.bat`.

GitHub Actions genera el instalador y comprueba la instalación, el arranque y la desinstalación en Windows. La prueba automatizada se ejecuta sin una placa conectada.
