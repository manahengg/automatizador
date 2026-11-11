"""Desglose en Excel de una base de precios (ver lectores/base_precios.py).

Hojas:
  Partidas         una fila por partida: capítulos, precio y cuánto es mano de obra / materiales / maquinaria / %,
                   material principal e incoherencias. Con filtros.
  Descomposición   cada línea de cada partida (rendimiento x precio = subtotal).
  Materiales       precio de cada material (lo que se compara con los distribuidores) y en qué partidas se usa.
  Mano de obra y maquinaria
  Incoherencias    lo que no cuadra dentro de la propia base.
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as L
from ..lectores import base_precios as B

FUENTE = 'Arial'
F_T = Font(name=FUENTE, size=13, bold=True)
F_N = Font(name=FUENTE, size=9)
F_B = Font(name=FUENTE, size=9, bold=True)
F_CAB = Font(name=FUENTE, size=9, bold=True, color='FFFFFF')
F_GRIS = Font(name=FUENTE, size=9, italic=True, color='666666')
R_CAB = PatternFill('solid', fgColor='1F4E78')
R_AVISO = PatternFill('solid', fgColor='FCE4D6')
FINO = Side(style='thin', color='BFBFBF')
BORDE = Border(left=FINO, right=FINO, top=FINO, bottom=FINO)
EUR = '#,##0.00 €;-#,##0.00 €;"-"'
PCT = '0%'
ARRIBA = Alignment(vertical='top', wrap_text=True)


def _tabla(ws, fila, cab, filas, anchos, formatos=None, alto_cab=30):
    formatos = formatos or {}
    for i, t in enumerate(cab, 1):
        c = ws.cell(fila, i, t)
        c.font, c.fill, c.border = F_CAB, R_CAB, BORDE
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[fila].height = alto_cab
    for r, vals in enumerate(filas, fila + 1):
        for i, v in enumerate(vals, 1):
            c = ws.cell(r, i, v)
            c.font, c.border, c.alignment = F_N, BORDE, ARRIBA
            if i in formatos:
                c.number_format = formatos[i]
    for i, a in enumerate(anchos, 1):
        ws.column_dimensions[L(i)].width = a
    ultima = fila + max(1, len(filas))
    ws.auto_filter.ref = 'A%d:%s%d' % (fila, L(len(cab)), ultima)
    ws.freeze_panes = ws.cell(fila + 1, 3)
    return ultima


def escribir(ruta_base, salida):
    b = B.analizar(ruta_base)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Partidas'
    ws['A1'] = 'Desglose de la base de precios — %s (precios a %s)' % (b['titulo'], b['fecha'] or '?')
    ws['A1'].font = F_T
    ws['A2'] = ('Cada partida = mano de obra + materiales + maquinaria + medios auxiliares (%). Para comparar con los '
                'distribuidores se usa el precio de los MATERIALES (hoja "Materiales"); el precio de la partida incluye '
                'la instalación.')
    ws['A2'].font = F_GRIS
    cab = ['Capítulo', 'Subcapítulo', 'Grupo', 'Código', 'Ud', 'Resumen', 'Descripción', 'Precio partida',
           'Mano de obra', 'Materiales', 'Maquinaria', 'Medios aux. (%)', '% mano de obra', 'Material principal',
           'Precio material principal', 'Incoherencias']
    filas = []
    for cod, p in sorted(b['partidas'].items(), key=lambda t: (t[1]['ruta'], t[0])):
        ruta = (p['ruta'] + ['', '', ''])[:3]
        mats = [x for x in b['descomp'].get(cod, []) if x['tipo'] == 'P' and not B.GENERICOS.match(x['resumen'])]
        ppal = max(mats, key=lambda x: x['subtotal'] or 0) if mats else None
        r = len(filas) + 5
        filas.append(ruta + [cod, p['ud'], p['resumen'], p['ampliada'], p['precio'], p['mano_obra'], p['materiales'],
                             p['maquinaria'], p['porcentajes'], '=IF(H{0}>0,I{0}/H{0},"")'.format(r),
                             ('%s %s' % (ppal['codigo'], ppal['resumen'])) if ppal else '',
                             ppal['precio'] if ppal else None, '\n'.join(p['incoherencias'])])
    ult = _tabla(ws, 4, cab, filas, [22, 26, 26, 12, 5, 40, 60, 11, 11, 11, 11, 11, 9, 40, 11, 50],
                 {8: EUR, 9: EUR, 10: EUR, 11: EUR, 12: EUR, 13: PCT, 15: EUR})
    for r in range(5, ult + 1):
        ws.row_dimensions[r].height = 24
        if ws.cell(r, 16).value:
            for c in range(1, 17):
                ws.cell(r, c).fill = R_AVISO

    ws = wb.create_sheet('Descomposición')
    cab = ['Código partida', 'Resumen partida', 'Línea', 'Tipo', 'Código', 'Ud', 'Descripción', 'Precio',
           'Rendimiento', 'Subtotal']
    filas = []
    for cod, p in sorted(b['partidas'].items()):
        for x in b['descomp'].get(cod, []):
            filas.append([cod, p['resumen'], x['linea'], B.TIPOS.get(x['tipo'], x['tipo']), x['codigo'], x['ud'],
                          x['resumen'], x['precio'], x['rend'], x['subtotal']])
    _tabla(ws, 1, cab, filas, [13, 40, 6, 18, 12, 5, 45, 10, 10, 10], {8: EUR, 10: EUR})

    ws = wb.create_sheet('Materiales')
    cab = ['Código', 'Ud', 'Descripción', 'Precio', 'Nº partidas que lo usan', 'Capítulo (1ª partida)',
           'Partidas que lo usan']
    filas = []
    for cod, el in sorted(b['elementos'].items()):
        if el['tipo'] != 'P' or el.get('precio') is None:
            continue
        usos = el['usos']
        ruta = b['partidas'][usos[0]]['ruta'] if usos else []
        filas.append([cod, el['ud'], el['ampliada'] if len(el.get('ampliada') or '') > len(el['resumen']) + 5
                      else el['resumen'], el['precio'], len(usos), ' > '.join(ruta[-2:]),
                      '; '.join('%s %s' % (u, b['partidas'][u]['resumen']) for u in usos[:6])
                      + (' (+%d)' % (len(usos) - 6) if len(usos) > 6 else '')])
    _tabla(ws, 1, cab, filas, [12, 5, 55, 11, 10, 40, 70], {4: EUR})

    ws = wb.create_sheet('Mano de obra y maquinaria')
    filas = [[cod, B.TIPOS.get(el['tipo']), el['ud'], el['resumen'], el['precio'], len(
        [1 for d in b['descomp'].values() for x in d if x['codigo'] == cod])]
             for cod, el in sorted(b['elementos'].items()) if el['tipo'] in ('O', 'M')]
    _tabla(ws, 1, ['Código', 'Tipo', 'Ud', 'Descripción', 'Precio', 'Nº partidas'], filas, [12, 14, 5, 45, 11, 10],
           {5: EUR})

    ws = wb.create_sheet('Incoherencias')
    filas = [[cod, p['resumen'], ' > '.join(p['ruta'][-2:]), t] for cod, p in sorted(b['partidas'].items())
             for t in p['incoherencias']]
    _tabla(ws, 1, ['Código', 'Partida', 'Capítulo', 'Incoherencia'], filas, [13, 45, 40, 90])
    wb.save(salida)
    return salida
