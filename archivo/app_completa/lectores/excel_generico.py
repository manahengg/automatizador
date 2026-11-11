"""Excel de formato libre (de un proveedor que no conocemos): detecta la fila de cabecera por sinónimos.

IMPORTANTE: este lector NO se ha probado con ficheros reales de proveedores (solo con una hoja sintética en los tests).
Por eso siempre deja un aviso "revisar" con el mapeo de columnas que ha supuesto.
"""
import re
import warnings
import openpyxl
from . import _xl
from ..modelo import Documento, Capitulo, Partida

warnings.filterwarnings('ignore')

SINONIMOS = {
    'codigo': ['codigo', 'código', 'cod', 'cod.', 'ref', 'ref.', 'referencia', 'artículo', 'articulo'],
    'descripcion': ['descripcion', 'descripción', 'concepto', 'titulo/concepto', 'resumen', 'partida', 'texto',
                    'denominación', 'denominacion', 'producto'],
    'unidad': ['ud', 'ud.', 'unidad', 'u.m.', 'um'],
    'cantidad': ['cantidad', 'cant', 'cant.', 'medicion', 'medición', 'unidades', 'uds', 'uds.'],
    'precio': ['precio', 'precio unitario', 'pvp', 'p.unit', 'p. unit.', 'precio/ud', 'precio ud', 'importe unitario',
               'precio unit.', 'precio neto'],
    'dto': ['dto', 'dto.', '% dto', '%dto', 'descuento', '% descuento'],
    'importe': ['importe', 'total', 'parcial', 'importe total', 'subtotal'],
}


def _norm(v):
    return re.sub(r'\s+', ' ', str(v)).strip().lower() if v is not None else ''


def _mapear(fila):
    mapa = {}
    for i, v in enumerate(fila):
        for campo, sin in SINONIMOS.items():
            if campo not in mapa and _norm(v) in sin:
                mapa[campo] = i
    return mapa


def _buscar_cabecera(ws):
    for r in range(1, 60):
        fila = [ws.cell(r, c).value for c in range(1, 20)]
        mapa = _mapear(fila)
        if {'descripcion', 'cantidad', 'precio'} <= set(mapa):
            return r, mapa
    return None, None


def reconoce(ruta):
    if not str(ruta).lower().endswith(('.xlsx', '.xlsm')):
        return False
    try:
        r, _ = _buscar_cabecera(_xl.cargar(ruta, read_only=True, data_only=True).worksheets[0])
        return r is not None
    except Exception:
        return False


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace('€', '').replace(' ', '')
        if re.fullmatch(r'-?\d{1,3}(\.\d{3})*,\d+', s):
            s = s.replace('.', '').replace(',', '.')
        elif re.fullmatch(r'-?\d+,\d+', s):
            s = s.replace(',', '.')
        try:
            return float(s)
        except ValueError:
            return None
    return None


def leer(ruta):
    ws = _xl.cargar(ruta, data_only=True).worksheets[0]
    cab, mapa = _buscar_cabecera(ws)
    doc = Documento(tipo='oferta_proveedor', origen=str(ruta))
    cap = None
    for r in range(cab + 1, ws.max_row + 1):
        def v(campo):
            return ws.cell(r, mapa[campo] + 1).value if campo in mapa else None
        desc, cant, precio = v('descripcion'), _num(v('cantidad')), _num(v('precio'))
        if desc is None or str(desc).strip() == '':
            continue
        desc = str(desc).strip()
        if re.match(r'^(sub)?total\b|^base imponible|^iva\b', desc, re.I):
            if doc.total_declarado is None and _num(v('importe')) is not None and re.match(r'^(sub)?total', desc, re.I):
                doc.total_declarado = _num(v('importe'))
            continue
        if cant is None and precio is None:                     # fila de título -> nuevo capítulo
            cap = Capitulo(titulo=desc)
            doc.capitulos.append(cap)
            continue
        if cant is None:
            continue
        if cap is None:
            cap = Capitulo(titulo='SIN CAPÍTULO')
            doc.capitulos.append(cap)
        dto = _num(v('dto'))
        neto = None if precio is None else precio * (1 - (dto or 0) / 100)
        cap.hijos.append(Partida(descripcion=desc, cantidad=cant, precio=neto,
                                 unidad=str(v('unidad') or 'ud').strip(), codigo=str(v('codigo')).strip() if v('codigo') else None,
                                 precio_lista=precio if dto else None, dto_pct=dto,
                                 importe_declarado=_num(v('importe'))))
    nombres = {c: _norm(ws.cell(cab, i + 1).value) for c, i in mapa.items()}
    doc.avisar('revisar', 'Excel de formato libre: se ha supuesto este mapeo de columnas (fila %d): %s. '
                          'Confirmar la primera vez que llegue una oferta de este proveedor.' % (
                              cab, ', '.join('%s=«%s»' % (c, n) for c, n in nombres.items())))
    doc.validar()
    return doc
