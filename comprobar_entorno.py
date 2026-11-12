"""Verificación de arranque local de Python/Tk/Pillow/NumPy/ZeroMQ."""
import sys


def main():
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
    except Exception as exc:
        print('ERROR Tcl/Tk: no se pudo crear la ventana de Tkinter.')
        print(repr(exc))
        print('Repara la instalacion BASE de Python y activa "tcl/tk and IDLE".')
        return 1
    try:
        import numpy
        import zmq
        from PIL import Image, ImageTk
        Image.new('RGB', (2, 2))
    except Exception as exc:
        print('ERROR de dependencias: ', repr(exc))
        print('Prueba REPARAR_ENTORNO.bat para reinstalar las bibliotecas de cero.')
        return 1
    print('ENTORNO OK:',sys.version.split()[0], 'NumPy',numpy.__version__,
          'Pillow',Image.__version__, 'ZeroMQ',zmq.__version__)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
