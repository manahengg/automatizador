"""Punto de entrada de la app instalada en Windows. El acceso directo ejecuta, con el Python embebido oficial (firmado):
    python\\python.exe app\\automatizador\\windows\\lanzador.py

- Guarda obras y base de datos de precios en %LOCALAPPDATA%\\ComparadorOfertas (sobreviven a reinstalar/actualizar).
- Usa el puerto 8765 o, si está ocupado, el primero libre.
- Abre el navegador. Cerrar esta ventana cierra la app.
"""
import os
import socket
import sys


def puerto_libre(preferido=8765):
    for p in [preferido] + list(range(8766, 8800)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    raise SystemExit('No hay ningún puerto libre entre 8765 y 8799.')


LIBRERIAS = [('pdfplumber', 'leer PDF'), ('openpyxl', 'crear el Excel'), ('pypdfium2', 'OCR de PDF escaneados'),
             ('numpy', 'OCR de PDF escaneados'), ('rapidocr_onnxruntime', 'OCR de PDF escaneados')]


def comprobar_librerias():
    """Si Windows (Smart App Control) bloquea alguna DLL de una librería, lo dice claramente en vez de fallar luego."""
    import importlib
    malas = []
    for mod, para in LIBRERIAS:
        try:
            importlib.import_module(mod)
        except Exception as e:  # ImportError / OSError "DLL load failed" / bloqueo de directiva
            malas.append((mod, para, str(e).splitlines()[0][:160] if str(e) else type(e).__name__))
    for mod, para, err in malas:
        print('AVISO: no se pudo cargar %s (sirve para %s): %s' % (mod, para, err))
    if malas:
        print('Si el error habla de "directiva de Control de aplicaciones" o "4551", Windows ha bloqueado esa DLL.'
              '\nLa app se abre igual; lo demás funciona.\n')


def main():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    os.environ.setdefault('AUTOMATIZADOR_DATOS', os.path.join(base, 'ComparadorOfertas'))
    if os.name == 'nt':
        os.system('title Comparador de ofertas - NO CIERRES ESTA VENTANA mientras uses la app')
    comprobar_librerias()
    from automatizador.app_web import servir
    print('Comparador de ofertas de material eléctrico')
    print('Para cerrar la app cierra esta ventana.\n')
    servir(puerto_libre(), abrir='--no-abrir' not in sys.argv)


if __name__ == '__main__':
    main()
