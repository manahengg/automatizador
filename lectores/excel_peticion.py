"""Petición de oferta (exportadores/excel_peticion.py) devuelta RELLENA por el proveedor.

Cada fila lleva el código de su material: la línea se casa directamente con él (obra.PREFIJO_PETICION).
Los precios se calculan de "Precio unitario" y "Dto. %" (no de las fórmulas, por si el fichero no está recalculado).
"""
from . import _xl
from ..modelo import Documento, Capitulo, Partida
from ..exportadores import excel_peticion as X


def reconoce(ruta):
    try:
        wb = _xl.cargar(ruta, read_only=True, data_only=True)
        return '_datos' in wb.sheetnames and wb['_datos']['A1'].value == X.MARCA
    except Exception:
        return False


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace('€', '').replace('.', '').replace(',', '.').strip()) if v not in (None, '') else None
    except ValueError:
        return None


def leer(ruta, progreso=None):
    wb = _xl.cargar(ruta, data_only=True)
    ws = wb.worksheets[0]
    empresa = ws.cell(2, 8).value
    doc = Documento(tipo='oferta_proveedor', origen=str(ruta), nombre='Petición de oferta rellena',
                    proveedor=str(empresa).strip() if empresa else None, validez=ws.cell(4, 8).value)
    cap = None
    sin_precio = 0
    for r in range(X.F_CABECERA + 1, ws.max_row + 1):
        cod = ws.cell(r, X.C_COD).value
        a = ws.cell(r, 1).value
        if not cod:
            if a and not ws.cell(r, 4).value and not str(a).startswith('Total'):
                cap = Capitulo(titulo=str(a))
                doc.capitulos.append(cap)
            continue
        precio, dto = _num(ws.cell(r, X.C_PRECIO).value), _num(ws.cell(r, X.C_DTO).value)
        if precio is None:
            sin_precio += 1
            continue
        if cap is None:
            cap = Capitulo(titulo='Oferta')
            doc.capitulos.append(cap)
        marca = ws.cell(r, X.C_MARCA).value
        ref = ws.cell(r, X.C_REF).value
        obs = ws.cell(r, X.C_OBS).value
        desc = str(ws.cell(r, 5).value or '')
        if marca:
            desc = '%s — %s' % (marca, desc)
        p = Partida(descripcion=desc, cantidad=_num(ws.cell(r, X.C_CANT).value) or 0,
                    precio=round(precio * (1 - (dto or 0) / 100), 4), unidad=str(ws.cell(r, 3).value or 'ud'),
                    codigo='PET:' + str(cod).strip(), referencia=str(ref).strip() if ref else None,
                    precio_lista=precio if dto else None, dto_pct=dto, marca=str(marca) if marca else None)
        if obs:
            p.notas = [str(obs)]
        cap.hijos.append(p)
    n = sum(1 for _ in doc.partidas())
    doc.avisar('info', 'Petición de oferta devuelta: %d materiales con precio, %d sin precio (no ofertados).'
               % (n, sin_precio))
    return doc
