"""Prepara la carpeta que instala el instalador de Windows, SIN ejecutables propios sin firmar.

Por qué: Windows 11 (Smart App Control / Control de aplicaciones) bloquea los .exe sin firma digital y sin
reputación. Un .exe hecho con PyInstaller es distinto en cada compilación, así que nunca tiene reputación y se bloquea.
En su lugar se instala:
    python/   Python "embebido" OFICIAL de python.org (python.exe y DLLs firmados por la Python Software Foundation)
              + las librerías tal como se publican en PyPI (ficheros idénticos en todo el mundo, con reputación)
    app/      el código de la app (ficheros .py de texto, que no son ejecutables)
El acceso directo abre:  python\\python.exe app\\automatizador\\windows\\lanzador.py

Uso (en Windows, desde la carpeta que contiene "automatizador"):
    python automatizador\\windows\\empaquetar.py  [carpeta_destino]
Requiere el mismo Python X.Y que el embebido (para que pip elija las ruedas correctas).
"""
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

PY_VERSION = os.environ.get('PY_EMBED_VERSION', '3.12.10')
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUIR = {'obras', 'tests', '__pycache__', '.git', '.github', 'build', 'dist', 'paquete', 'venv', '.venv',
           'automatizador_datos'}


LEEME = """COMPARADOR DE OFERTAS - instalación

1. ANTES de descomprimir: clic derecho en el ZIP > Propiedades > marca "Desbloquear" > Aceptar.
2. Descomprime el ZIP (clic derecho > Extraer todo).
3. Doble clic en "Instalar.bat". Si sale "Windows protegió su PC": "Más información" > "Ejecutar de todas formas".
4. Se crea el acceso directo "Comparador de ofertas" en el escritorio y en el menú Inicio, y se abre la app.
   Se abre una ventana negra (es el servidor): no la cierres mientras uses la app.

No hay ningún .exe propio: se usa el python.exe oficial de python.org (firmado) para que Smart App Control no lo
bloquee. Tus obras y precios están en %LOCALAPPDATA%\\ComparadorOfertas y no se borran al actualizar.
Para actualizar: descarga el ZIP nuevo y repite los pasos.
"""


def main(destino):
    destino = os.path.abspath(destino)
    shutil.rmtree(destino, ignore_errors=True)
    dpy, dapp = os.path.join(destino, 'python'), os.path.join(destino, 'app', 'automatizador')
    os.makedirs(dpy)
    # 1) Python embebido oficial
    mayor = ''.join(PY_VERSION.split('.')[:2])                     # '312'
    if sys.version_info[:2] != tuple(int(x) for x in PY_VERSION.split('.')[:2]):
        raise SystemExit('Ejecuta este script con Python %s (es %s)' % (PY_VERSION, sys.version.split()[0]))
    url = 'https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip' % (PY_VERSION, PY_VERSION)
    print('Descargando', url)
    with urllib.request.urlopen(url, timeout=120) as r:
        zipfile.ZipFile(io.BytesIO(r.read())).extractall(dpy)
    # 2) rutas de importación: librerías y código de la app (el ._pth sustituye a sys.path en el Python embebido)
    with open(os.path.join(dpy, 'python%s._pth' % mayor), 'w', encoding='ascii') as f:
        f.write('python%s.zip\n.\nLib\\site-packages\n..\\app\nimport site\n' % mayor)
    # 3) librerías, tal cual se publican en PyPI (solo ruedas precompiladas)
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', '--only-binary=:all:',
                           '--target', os.path.join(dpy, 'Lib', 'site-packages'),
                           '-r', os.path.join(REPO, 'requirements.txt')])
    # 4) código de la app
    shutil.copytree(REPO, dapp, ignore=lambda d, nombres: [n for n in nombres if n in EXCLUIR or n.endswith('.pyc')])
    shutil.copy2(os.path.join(REPO, 'windows', 'icono.ico'), os.path.join(destino, 'icono.ico'))
    # 5) instalación sin .exe propio: Instalar.bat -> python.exe oficial + windows/instalar.py
    for f in ('Instalar.bat', 'Abrir Comparador.bat'):
        with open(os.path.join(REPO, 'windows', f), encoding='ascii') as e, \
                open(os.path.join(destino, f), 'w', encoding='ascii', newline='\r\n') as s:
            s.write(e.read())
    with open(os.path.join(destino, 'LEEME.txt'), 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write(LEEME)
    print('Paquete listo en', destino)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'paquete')
