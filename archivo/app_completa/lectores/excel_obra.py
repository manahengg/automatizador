"""Excel de obra/certificación con el formato libre de Tritón (probado con la certificación de Cintra).

Estructura: columnas A=capítulo, B=partida, C=unidad, D=concepto, E=medición, F=precio, G=importe.
Los códigos de nivel van con coma (001,001). Se leen los VALORES calculados (no las fórmulas).
"""
import re
import warnings
import openpyxl
from . import _xl
from ..modelo import Documento, Capitulo, Partida

warnings.filterwarnings('ignore')


def reconoce(ruta):
    if not str(ruta).lower().endswith(('.xlsx', '.xlsm')):
        return False
    try:
        ws = _xl.cargar(ruta, read_only=True).worksheets[0]
        for fila in ws.iter_rows(min_row=1, max_row=40, values_only=True):
            d = fila[3] if len(fila) > 3 else None
            if isinstance(d, str) and d.strip().upper().startswith('CERTIFICACI') and len(fila) >= 7:
                return True
    except Exception:
        return False
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
    return str(c).strip().replace(',', '.') if c not in (None, '') else None


def leer(ruta):
    libro = _xl.cargar(ruta)
    ws = libro.worksheets[0]
    wv = _xl.cargar(ruta, data_only=True).worksheets[0]
    doc = Documento(tipo='obra', origen=str(ruta))
    cap = grupo = None
    huerfanas = []              # (capítulo/grupo destino, Partida) para numerar al final
    en_tabla = False
    for r in range(1, ws.max_row + 1):
        A, B, C, D = (ws.cell(r, c).value for c in (1, 2, 3, 4))
        E, F, G = (wv.cell(r, c).value for c in (5, 6, 7))
        if isinstance(D, str) and D.strip().upper().startswith('CERTIFICACI'):
            en_tabla = True
            doc.tipo = 'certificacion'
            doc.nombre = D.strip().title()
            continue
        if not en_tabla:
            continue
        D = D.strip() if isinstance(D, str) else D
        etiqueta = D.upper() if isinstance(D, str) else ''
        if etiqueta.startswith('TOTAL PRESUPUESTADO') and _num(G) is not None:
            doc.total_declarado = _num(G)
        elif etiqueta.startswith('A DEDUCIR') and _num(F) is not None:
            doc.condiciones['a_deducir'] = _num(F)
        if A and not B:                                            # capítulo
            cap = Capitulo(titulo=D or '', codigo=_cod(A))
            doc.capitulos.append(cap)
            grupo = None
        elif A and B and cap is not None:
            formula_e = isinstance(ws.cell(r, 5).value, str) and str(ws.cell(r, 5).value).startswith('=')
            es_linea = _num(F) is not None and isinstance(E, (int, float))
            if es_linea and re.fullmatch(r'\d+([.,]\d+)+', str(B).strip()):      # línea de un grupo: 001,001
                if grupo is None or not _cod(B).startswith(grupo.codigo + '.'):
                    grupo = Capitulo(titulo='', codigo=_cod(B).split('.')[0])
                    cap.hijos.append(grupo)
                grupo.hijos.append(Partida(descripcion=D, cantidad=float(E), precio=float(F),
                                           unidad=(C or '').strip() or 'ud', codigo=_cod(B)))
            elif es_linea and not formula_e:                      # partida simple
                cap.hijos.append(Partida(descripcion=D, cantidad=float(E), precio=float(F),
                                         unidad=(C or '').strip() or 'ud', codigo=_cod(B)))
                grupo = None
            else:                                                 # cabecera de grupo con subpartidas
                grupo = Capitulo(titulo=D or '', codigo=_cod(B))
                cap.hijos.append(grupo)
        elif not A and not B and isinstance(D, str) and cap is not None and grupo is not None \
                and not etiqueta.startswith(('TOTAL', 'A DEDUCIR')) \
                and isinstance(E, (int, float)) and _num(F) not in (None, 0):
            # línea con cantidad y precio pero SIN código: se numera al final, detrás de las de su grupo
            huerfanas.append((grupo, Partida(descripcion=D, cantidad=float(E), precio=float(F), unidad='ud',
                                             notas=['Sin código en el origen: código asignado automáticamente'])))
    for grupo, p in huerfanas:
        mayor = max([int(h.codigo.split('.')[-1]) for h in grupo.hijos if isinstance(h, Partida) and h.codigo] or [0])
        p.codigo = '%s.%03d' % (grupo.codigo, mayor + 1)
        grupo.hijos.append(p)
        doc.avisar('revisar', 'La línea "%s" no tenía código en el origen: se le asigna %s (confirmar).' % (
            p.descripcion[:40], p.codigo))
    if doc.total_declarado is not None:
        doc.avisar('info', 'Total presupuestado que declara el fichero de origen: %.2f €.' % doc.total_declarado)
    doc.validar()
    return doc
