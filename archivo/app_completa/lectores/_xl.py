"""Carga de Excel que NO deja el fichero abierto (en Windows un fichero abierto no se puede mover/archivar)."""
import warnings
import openpyxl

warnings.filterwarnings('ignore')


def cargar(ruta, **kw):
    kw.pop('read_only', None)          # siempre en memoria: así se puede cerrar el fichero ya
    libro = openpyxl.load_workbook(ruta, **kw)
    libro.close()
    return libro
