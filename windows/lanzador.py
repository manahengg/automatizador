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


def main():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    os.environ.setdefault('AUTOMATIZADOR_DATOS', os.path.join(base, 'ComparadorOfertas'))
    if os.name == 'nt':
        os.system('title Comparador de ofertas - NO CIERRES ESTA VENTANA mientras uses la app')
    from automatizador.app_web import servir
    print('Comparador de ofertas de material eléctrico')
    print('Para cerrar la app cierra esta ventana.\n')
    servir(puerto_libre(), abrir='--no-abrir' not in sys.argv)


if __name__ == '__main__':
    main()
