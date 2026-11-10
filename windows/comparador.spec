# Receta de PyInstaller:  pyinstaller windows/comparador.spec   (ejecutar desde la carpeta PADRE del repositorio
# o con la variable REPO apuntando al repositorio). Genera dist/ComparadorOfertas/ComparadorOfertas.exe
import os
from PyInstaller.utils.hooks import collect_all

REPO = os.environ.get('REPO') or os.path.abspath(os.path.join(SPECPATH, '..'))
PADRE = os.path.dirname(REPO)          # el paquete se importa como "automatizador" desde la carpeta padre

datas, binaries, ocultos = [], [], ['automatizador', 'automatizador.app_web', 'automatizador.lectores.excel_obra',
                                    'automatizador.lectores.excel_erp', 'automatizador.lectores.excel_generico']
for paquete in ('rapidocr_onnxruntime', 'onnxruntime', 'pypdfium2', 'pypdfium2_raw', 'pdfplumber', 'pdfminer',
                'openpyxl', 'shapely', 'pyclipper'):
    try:
        d, b, h = collect_all(paquete)
        datas += d
        binaries += b
        ocultos += h
    except Exception as e:
        print('aviso: no se pudo recoger', paquete, e)

datas.append((os.path.join(REPO, 'recursos'), os.path.join('automatizador', 'recursos')))   # logo de la app y el Excel

a = Analysis([os.path.join(REPO, 'windows', 'lanzador.py')], pathex=[PADRE], binaries=binaries, datas=datas,
             hiddenimports=ocultos, excludes=['tkinter', 'matplotlib', 'IPython', 'pytest', 'pandas'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ComparadorOfertas', console=True,
          icon=os.path.join(REPO, 'windows', 'icono.ico') if os.path.exists(os.path.join(REPO, 'windows', 'icono.ico')) else None)
coll = COLLECT(exe, a.binaries, a.datas, name='ComparadorOfertas')
