"""Excel con el formato de hoja que usa el ERP (cabecera Cap. / Part. / Ud. / Titulo/Concepto / Medición / Importe / Total / Total Cap.).

Probado con la hoja de ejemplo de la certificación de venta. Tolera números guardados como texto y filas de
etiquetas ("Total 01", "TOTAL PRESUPUESTADO") que no son partidas.
"""
import warnings
import openpyxl
from . import _xl
from ..modelo import Documento, Capitulo, Partida

warnings.filterwarnings('ignore')


def _cabecera(ws):
    for r in range(1, 30):
        fila = [ws.cell(r, c).value for c in range(1, 9)]
        if fila[0] == 'Cap.' and fila[1] == 'Part.' and isinstance(fila[3], str) and fila[3].startswith('Titulo'):
            return r
    return None


def reconoce(ruta):
    if not str(ruta).lower().endswith(('.xlsx', '.xlsm')):
        return False
    try:
        return _cabecera(_xl.cargar(ruta, read_only=True, data_only=True).worksheets[0]) is not None
    except Exception:
        return False


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(',', '.'))
        except ValueError:
            return None
    return None


def _cod(c):
    return str(c).replace('·', '').strip() if c not in (None, '') else None


def leer(ruta):
    ws = _xl.cargar(ruta, data_only=True).worksheets[0]
    cab = _cabecera(ws)
    doc = Documento(tipo='certificacion', origen=str(ruta))
    titulo = ws.cell(1, 4).value
    if isinstance(titulo, str):
        doc.nombre = ' '.join(titulo.split())
    cap, grupos, declarado = None, {}, 0.0
    hay_declarado = False
    for r in range(cab + 1, ws.max_row + 1):
        A, B, C, D, E, F, H = (ws.cell(r, c).value for c in (1, 2, 3, 4, 5, 6, 8))
        if A == 'Cap.' or all(ws.cell(r, c).value is None for c in range(1, 9)):
            continue
        D = D.strip() if isinstance(D, str) else D
        if A and not B:                                       # capítulo
            cap = Capitulo(titulo=D or '', codigo=_cod(A))
            doc.capitulos.append(cap)
            grupos = {}
            if _num(H) is not None:
                declarado += _num(H)
                hay_declarado = True
        elif A and B and cap is not None:
            codigo = _cod(B)
            if _num(E) is None:                               # cabecera de subcapítulo
                grupos[codigo] = Capitulo(titulo=D or '', codigo=codigo)
                cap.hijos.append(grupos[codigo])
            else:
                p = Partida(descripcion=D or '', cantidad=_num(E), precio=_num(F), unidad=(C or '').strip() or 'ud',
                            codigo=codigo)
                if '.' in codigo:
                    padre = codigo.split('.')[0]
                    if padre not in grupos:
                        grupos[padre] = Capitulo(titulo='', codigo=padre)
                        cap.hijos.append(grupos[padre])
                    grupos[padre].hijos.append(p)
                else:
                    cap.hijos.append(p)
    if hay_declarado:
        doc.total_declarado = round(declarado, 2)
    doc.validar()
    return doc
