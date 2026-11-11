"""PEDIDO a un proveedor (ya no es una petición de presupuesto): las líneas de SU oferta que se le compran.

Dos usos (obra.Resultado):
  - pedido completo al distribuidor más barato en total (totales_proveedores): todo lo que oferta
  - pedidos del reparto (adjudicacion): a cada distribuidor, solo los materiales en los que es el más barato
Cada línea va con la referencia y la descripción DEL PROVEEDOR (para que la reconozca) y su precio neto ofertado; la
cantidad a pedir es la de su oferta (editable, en amarillo) y al lado se muestra lo que necesita el proyecto.
Sin logo y sin el nombre del cliente.
"""
import datetime
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, Protection
from openpyxl.utils import get_column_letter as L

FUENTE = 'Arial'
F_TIT = Font(name=FUENTE, size=16, bold=True, color='1F4E78')
F_N = Font(name=FUENTE, size=9)
F_B = Font(name=FUENTE, size=9, bold=True)
F_CAB = Font(name=FUENTE, size=9, bold=True, color='FFFFFF')
F_GRIS = Font(name=FUENTE, size=9, italic=True, color='595959')
F_CAP = Font(name=FUENTE, size=10, bold=True, color='1F4E78')
F_AVISO = Font(name=FUENTE, size=8, color='C00000')
R_CAB = PatternFill('solid', fgColor='1F4E78')
R_CAP = PatternFill('solid', fgColor='DDEBF7')
R_SUB = PatternFill('solid', fgColor='F2F2F2')
R_TOT = PatternFill('solid', fgColor='BDD7EE')
R_IN = PatternFill('solid', fgColor='FFF2CC')
R_DIF = PatternFill('solid', fgColor='FCE4D6')
FINO = Side(style='thin', color='BFBFBF')
BORDE = Border(left=FINO, right=FINO, top=FINO, bottom=FINO)
EUR = '#,##0.00 €;-#,##0.00 €;""'
EUR4 = '#,##0.0000 €;-#,##0.0000 €;""'
CANT = '#,##0.##'
ARRIBA = Alignment(vertical='top', wrap_text=True)

COLUMNAS = [('Nº', 5), ('Ref. proveedor', 15), ('Descripción (según su oferta)', 50), ('Ud', 5), ('Cantidad', 10),
            ('Precio neto', 12), ('Importe', 13), ('Partida de obra', 34), ('Necesario según proyecto', 14),
            ('Observaciones', 40)]
C_CANT, C_PRECIO, C_IMP = 5, 6, 7
F_CABECERA = 11


def _num(x):
    return ('%.2f' % x).rstrip('0').rstrip('.').replace('.', ',') if x is not None else ''


def lineas_pedido(res, proveedor, material_ids=None):
    """[(material, oferta, [(linea, cantidad)])] de un distribuidor, en el orden del presupuesto."""
    pv = next(p for p in res.proveedores if p['nombre'] == proveedor)
    out, vistas = [], set()
    for m in res.materiales:
        o = pv['ofertas'].get(m.id)
        if o is None or o.precio is None or (material_ids is not None and m.id not in material_ids):
            continue
        filas = []
        for k, l in enumerate([o.principal] + list(o.extras)):
            if l.partida.opcional or l.partida.precio is None or getattr(l, 'uid', id(l)) in vistas:
                continue
            vistas.add(getattr(l, 'uid', id(l)))
            cant = l.partida.cantidad
            if k == 0 and o.cant_necesaria is not None:
                cant = o.cant_necesaria                     # FV: los módulos necesarios para la potencia pedida
            elif not cant:
                cant = m.cantidad                           # precio suelto / catálogo: la cantidad del proyecto
            filas.append((l, cant))
        if filas:
            out.append((m, o, filas))
    return out


def escribir(res, proveedor, ruta, material_ids=None, datos=None, motivo=''):
    datos = datos or {}
    pv = next(p for p in res.proveedores if p['nombre'] == proveedor)
    grupos = lineas_pedido(res, proveedor, material_ids)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Pedido'
    ws['A1'] = 'PEDIDO'
    ws['A1'].font = F_TIT
    hoy = datetime.date.today()
    cod = datos.get('cod') or ''
    ofertas = '; '.join('%s%s' % (os.path.basename(d['archivo']), (' (%s)' % d['doc'].fecha) if d['doc'].fecha else '')
                        for d in pv['docs'])
    izq = [('Proveedor', proveedor), ('Obra', datos.get('descripcion') or res.obra.nombre), ('Código de obra', cod),
           ('Fecha del pedido', hoy.strftime('%d/%m/%Y')), ('Según su oferta', ofertas)]
    for k, (t, v) in enumerate(izq, 3):
        ws.cell(k, 1, t + ':').font = F_B
        ws.merge_cells(start_row=k, start_column=1, end_row=k, end_column=2)
        ws.cell(k, 3, v).font = F_N
    der = [('Nº de pedido', '%s-%s-%s' % (cod or 'PED', ''.join(c for c in proveedor.upper() if c.isalnum())[:10],
                                          hoy.strftime('%Y%m%d'))),
           ('Dirección de entrega', ''), ('Persona de contacto', ''), ('Plazo de entrega', ''), ('Forma de pago', '')]
    for k, (t, v) in enumerate(der, 3):
        ws.cell(k, 8, t + ':').font = F_B
        c = ws.cell(k, 9, v)
        c.font, c.fill, c.border, c.protection = F_N, R_IN, BORDE, Protection(locked=False)
        ws.merge_cells(start_row=k, start_column=9, end_row=k, end_column=10)
    ws.cell(9, 1, (motivo + '  ' if motivo else '') + 'Precios netos según su oferta. Importes SIN IVA. Rogamos '
                  'confirmen el pedido y el plazo de entrega; cualquier cambio de artículo o cantidad debe comunicarse '
                  'antes de servirlo.').font = F_GRIS
    ws.merge_cells(start_row=9, start_column=1, end_row=9, end_column=len(COLUMNAS))
    ws.row_dimensions[9].height = 26
    ws.cell(9, 1).alignment = ARRIBA
    for i, (t, a) in enumerate(COLUMNAS, 1):
        c = ws.cell(F_CABECERA, i, t)
        c.font, c.fill, c.border = F_CAB, R_CAB, BORDE
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[L(i)].width = a
    ws.row_dimensions[F_CABECERA].height = 28

    r = F_CABECERA + 1
    cap_actual, ini, n = None, r, 0

    def cerrar(fin):
        nonlocal r
        if cap_actual is None or fin < ini:
            return
        ws.cell(r, 3, 'Total %s' % cap_actual).font = F_B
        c = ws.cell(r, C_IMP, '=SUBTOTAL(9,%s%d:%s%d)' % (L(C_IMP), ini, L(C_IMP), fin))
        c.font, c.number_format = F_B, EUR
        for i in range(1, len(COLUMNAS) + 1):
            ws.cell(r, i).fill, ws.cell(r, i).border = R_SUB, BORDE
        r += 1

    for m, o, filas in grupos:
        cod_cap = ((m.ruta_codigos[-1] if m.ruta_codigos else '') or '').rstrip('#')
        tit = m.ruta[-1] if m.ruta else 'SIN CAPÍTULO'
        cap = tit if not cod_cap or tit.startswith(cod_cap) else '%s  %s' % (cod_cap, tit)
        if cap != cap_actual:
            cerrar(r - 1)
            cap_actual = cap
            ws.cell(r, 1, cap).font = F_CAP
            for i in range(1, len(COLUMNAS) + 1):
                ws.cell(r, i).fill = R_CAP
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(COLUMNAS))
            r += 1
            ini = r
        avisos = [t for g, t in o.alertas if g in ('alta', 'media')]
        for k, (l, cant) in enumerate(filas):
            n += 1
            p = l.partida
            ws.cell(r, 1, n)
            ws.cell(r, 2, p.referencia or p.codigo or '')
            ws.cell(r, 3, p.descripcion)
            ws.cell(r, 4, p.unidad)
            ws.cell(r, C_CANT, cant)
            ws.cell(r, C_PRECIO, round(p.precio, 4))
            ws.cell(r, C_IMP, '={c}{r}*{p}{r}'.format(c=L(C_CANT), p=L(C_PRECIO), r=r))
            if k == 0:
                ws.cell(r, 8, '%s %s' % ((m.codigo or '').strip(), (m.partida.resumen or m.descripcion)[:80]))
                ws.cell(r, 9, '%s %s' % (_num(m.cantidad), m.unidad or ''))
                obs = list(avisos)
                if o.cant_prov and m.cantidad and o.cant_necesaria is None and abs(o.cant_prov - m.cantidad) > 0.01 * m.cantidad:
                    obs.insert(0, 'Su oferta trae %s; el proyecto necesita %s %s.' % (_num(o.cant_prov), _num(m.cantidad),
                                                                                      m.unidad or ''))
                    ws.cell(r, 9).fill = R_DIF
                ws.cell(r, 10, '\n'.join(obs[:3]))
            else:
                ws.cell(r, 8, '(complemento de la línea anterior)')
            for i in range(1, len(COLUMNAS) + 1):
                c = ws.cell(r, i)
                c.font = F_AVISO if i == 10 else F_N
                c.border, c.alignment = BORDE, ARRIBA
            c = ws.cell(r, C_CANT)
            c.fill, c.number_format, c.protection = R_IN, CANT, Protection(locked=False)
            ws.cell(r, C_PRECIO).number_format = EUR4
            ws.cell(r, C_IMP).number_format = EUR
            ws.row_dimensions[r].height = max(15, 12 * (len(p.descripcion) // 60 + 1))
            r += 1
    cerrar(r - 1)
    ws.cell(r, 3, 'TOTAL PEDIDO (sin IVA)').font = F_B
    c = ws.cell(r, C_IMP, '=SUBTOTAL(9,%s%d:%s%d)' % (L(C_IMP), F_CABECERA + 1, L(C_IMP), r - 1))
    c.font, c.number_format = F_B, EUR
    for i in range(1, len(COLUMNAS) + 1):
        ws.cell(r, i).fill, ws.cell(r, i).border = R_TOT, BORDE
    ws.freeze_panes = 'D%d' % (F_CABECERA + 1)
    ws.print_title_rows = '%d:%d' % (F_CABECERA, F_CABECERA)
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.center.text = 'Pedido %s · Página &P de &N' % der[0][1]
    wb.save(ruta)
    return {'lineas': n, 'materiales': len(grupos)}
