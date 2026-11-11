"""Excel de la comparativa: cliente frente a todos los proveedores, material a material.

Hojas:
  Comparativa         una fila por material (las partidas que se desglosan ocupan varias filas con las celdas de la
                      partida combinadas). Por proveedor: código, cantidad ofertada, diferencia de cantidad, precio,
                      importe y diferencia con el cliente. Al final: más bajo, P.U. más barato, P.U. más barato x cantidad,
                      mejor precio de la BBDD y alertas. Subtotales por capítulo con SUBTOTAL (no se cuentan dos veces).
  Resumen             importes por capítulo y proveedor (fórmulas SUMIFS sobre la hoja Comparativa) y datos de cada oferta.
  Alertas             todo lo que conviene revisar: textos sin sentido del cliente, diferencias técnicas, cantidades,
                      precios más baratos en la BBDD, líneas sin casar.
  Lineas proveedores  cada línea de cada oferta y a qué partida se ha casado.
  BBDD precios        precios históricos registrados para los materiales de esta obra.

Todos los cálculos son fórmulas: si se corrige un precio o una cantidad en el Excel, todo se recalcula
(incluido el verde del más barato, que es formato condicional).
"""
import datetime

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

from .. import emparejar as M

FUENTE = 'Arial'
F_NORMAL = Font(name=FUENTE, size=9)
F_NEGRITA = Font(name=FUENTE, size=9, bold=True)
F_TITULO = Font(name=FUENTE, size=14, bold=True)
F_CAB = Font(name=FUENTE, size=9, bold=True, color='FFFFFF')
F_ALERTA = Font(name=FUENTE, size=9, color='C00000')
F_GRIS = Font(name=FUENTE, size=8, italic=True, color='666666')
R_CAB = PatternFill('solid', fgColor='1F4E78')
R_PROV = ['2E75B6', '548235', 'BF8F00', '7030A0', 'C55A11', '2F5597', '806000', '375623']
R_SUB = PatternFill('solid', fgColor='D9E1F2')
R_TOTAL = PatternFill('solid', fgColor='B4C6E7')
R_VERDE = PatternFill('solid', fgColor='C6EFCE')
R_AMARILLO = PatternFill('solid', fgColor='FFF2CC')
R_NARANJA = PatternFill('solid', fgColor='F8CBAD')
R_PARTIDA = PatternFill('solid', fgColor='F2F2F2')
FINO = Side(style='thin', color='BFBFBF')
BORDE = Border(left=FINO, right=FINO, top=FINO, bottom=FINO)
EUR = '#,##0.00 €;-#,##0.00 €;"-"'
EUR4 = '#,##0.0000 €;-#,##0.0000 €;"-"'
CANT = '#,##0.##;-#,##0.##;0'
DIFCANT = '"+"#,##0.##;"−"#,##0.##;"="'
ENVOLVER = Alignment(wrap_text=True, vertical='top')
ARRIBA = Alignment(vertical='top')
CENTRO = Alignment(horizontal='center', vertical='center', wrap_text=True)

FIJAS = ['Capítulo', 'Nº licit.', 'Código cliente', 'Descripción cliente (partida)', 'Material a comprar (interpretado)',
         'Ud', 'Cant. partida', 'Cant. material', 'Precio cliente', 'Importe cliente']
BLOQUE = ['Código proveedor', 'Cant. ofertada', 'Cant. prov − cliente', 'Unitario', 'Total', 'Dif. vs cliente']
FINALES = ['Más bajo', 'P.U. más barato', 'P.U. más barato × cant.', 'Mejor precio BBDD', 'Proveedor BBDD (fecha · obra)',
           'Alertas y observaciones']
ANCHOS_FIJAS = [22, 6, 13, 42, 30, 5, 9, 10, 10, 12]
ANCHOS_BLOQUE = [16, 9, 10, 10, 12, 12]
ANCHOS_FINALES = [14, 11, 13, 11, 26, 60]


def _capitulo(m):
    return ' / '.join(m.ruta[-1:]) if m.ruta else 'SIN CAPÍTULO'


def _cap_cod(m):
    c = (m.ruta_codigos[-1] if m.ruta_codigos else '') or ''
    c = c.rstrip('#')
    return ('%s %s' % (c, _capitulo(m))).strip() if c and not _capitulo(m).startswith(c) else _capitulo(m)


def escribir(res, ruta):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Comparativa'
    provs = res.proveedores
    np_ = len(provs)
    c_ini = {}                                     # columna inicial del bloque de cada proveedor
    col = len(FIJAS) + 1
    for k in range(np_):
        c_ini[k] = col
        col += len(BLOQUE)
    c_fin = col                                    # primera columna final
    c_nivel1 = c_fin + len(FINALES)                # columnas auxiliares (ocultas): capítulo de primer nivel y
    c_capfila = c_nivel1 + 1                       # capítulo repetido en cada fila (para los SUMIFS del Resumen)
    ultima_col = c_capfila

    # ---------------------------------------------------------------- cabecera
    ws['A1'] = 'Comparativa de ofertas — %s' % res.obra.nombre
    ws['A1'].font = F_TITULO
    caps = res.obra.estado.get('capitulos')
    ws['A2'] = 'Presupuesto del cliente: %s  ·  %d partidas, %d materiales%s  ·  Generado el %s' % (
        res.cliente.nombre or res.obra.estado['cliente']['archivo'], len({m.n for m in res.materiales}),
        len(res.materiales), ('  ·  Solo los capítulos que hacemos (%d de %d materiales del presupuesto)' % (
            len(res.materiales), getattr(res.obra, 'total_materiales', len(res.materiales)))) if caps is not None else '',
        datetime.datetime.now().strftime('%d/%m/%Y %H:%M'))
    ws['A2'].font = F_GRIS
    ws['A3'] = ('Verde = unitario/total más bajo de la fila · Amarillo en el código = emparejamiento a revisar · '
                'Naranja = el proveedor oferta algo distinto a lo pedido · "Cant. material" = cantidad real a comprar '
                'interpretando la descripción (p. ej. 4x35 mm² unipolar x 27,5 m = 110 m) · '
                'Dif. vs cliente = importe del cliente − total del proveedor (positivo = margen)')
    ws['A3'].font = F_GRIS
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=min(ultima_col - 1, 16))
    ws.row_dimensions[3].height = 24
    ws['A3'].alignment = ENVOLVER
    F_HDR, F_COL = 5, 6
    for i, t in enumerate(FIJAS, 1):
        _cab(ws, F_COL, i, t, R_CAB)
    ws.merge_cells(start_row=F_HDR, start_column=1, end_row=F_HDR, end_column=len(FIJAS))
    _cab(ws, F_HDR, 1, 'PRESUPUESTO DEL CLIENTE', R_CAB)
    for k, pv in enumerate(provs):
        relleno = PatternFill('solid', fgColor=R_PROV[k % len(R_PROV)])
        for j, t in enumerate(BLOQUE):
            _cab(ws, F_COL, c_ini[k] + j, t, relleno)
        ws.merge_cells(start_row=F_HDR, start_column=c_ini[k], end_row=F_HDR, end_column=c_ini[k] + len(BLOQUE) - 1)
        _cab(ws, F_HDR, c_ini[k], pv['nombre'].upper() + (' (REFERENCIA)' if pv.get('referencia') else ''), relleno)
        if pv.get('referencia'):
            ws.cell(F_HDR, c_ini[k]).comment = Comment('Base de precios de referencia: se compara, pero no cuenta para '
                                                       'el "Más bajo" ni para el reparto entre distribuidores.',
                                                       'Automatizador')
    for j, t in enumerate(FINALES):
        _cab(ws, F_COL, c_fin + j, t, R_CAB)
    ws.merge_cells(start_row=F_HDR, start_column=c_fin, end_row=F_HDR, end_column=c_fin + len(FINALES) - 1)
    _cab(ws, F_HDR, c_fin, 'MEJOR OPCIÓN', R_CAB)
    _cab(ws, F_COL, c_nivel1, 'Capítulo nivel 1', R_CAB)
    _cab(ws, F_COL, c_capfila, 'Capítulo (fila)', R_CAB)
    ws.row_dimensions[F_COL].height = 30
    for i, a in enumerate(ANCHOS_FIJAS, 1):
        ws.column_dimensions[L(i)].width = a
    for k in range(np_):
        for j, a in enumerate(ANCHOS_BLOQUE):
            ws.column_dimensions[L(c_ini[k] + j)].width = a
    for j, a in enumerate(ANCHOS_FINALES):
        ws.column_dimensions[L(c_fin + j)].width = a
    ws.column_dimensions[L(c_nivel1)].hidden = True
    ws.column_dimensions[L(c_capfila)].hidden = True
    ws.freeze_panes = ws.cell(row=F_COL + 1, column=6)

    # ---------------------------------------------------------------- filas
    fila = F_COL + 1
    primera_datos = fila
    alertas = []                 # (nº, código, proveedor, gravedad, tipo, texto)
    grupos = []                  # (capítulo, fila_ini, fila_fin)
    cap_actual, ini_cap = None, fila
    mats = res.materiales
    por_partida = {}
    for m in mats:
        por_partida.setdefault(m.n, []).append(m)

    def cerrar_capitulo(fin):
        nonlocal fila
        if cap_actual is None or fin < ini_cap:
            return
        _subtotal(ws, fila, 'Total %s' % cap_actual, ini_cap, fin, provs, c_ini, c_fin, R_SUB)
        grupos.append((cap_actual, ini_cap, fin))
        fila += 1

    i = 0
    while i < len(mats):
        m = mats[i]
        cap = _cap_cod(m)
        if cap != cap_actual:
            cerrar_capitulo(fila - 1)
            cap_actual, ini_cap = cap, fila
        grupo = por_partida[m.n]
        f0, f1 = fila, fila + len(grupo) - 1
        p = m.partida
        for k_m, mm in enumerate(grupo):
            r = fila
            ws.cell(r, 1, cap).font = F_NORMAL
            ws.cell(r, c_nivel1, (m.ruta[0] if m.ruta else 'SIN CAPÍTULO'))
            ws.cell(r, c_capfila, cap)
            ws.cell(r, 2, '%d%s' % (mm.n, mm.id[len(str(mm.n)):]) if len(grupo) > 1 else mm.n)
            ws.cell(r, 3, p.codigo or '')
            if k_m == 0:
                ws.cell(r, 4, (p.resumen + ' — ' if p.resumen and p.resumen not in p.descripcion[:len(p.resumen) + 5]
                               else '') + (p.descripcion or '')[:700])
                ws.cell(r, 6, p.unidad)
                ws.cell(r, 7, p.cantidad)
                ws.cell(r, 9, p.precio)
                ws.cell(r, 10, '=IF(OR(G{0}="",I{0}=""),"",G{0}*I{0})'.format(r))
            ws.cell(r, 5, mm.descripcion + (' (%s)' % mm.nota if mm.nota else ''))
            ws.cell(r, 8, mm.cantidad)
            if mm.nota:
                ws.cell(r, 8).comment = Comment('Cantidad interpretada: %s' % mm.nota, 'Automatizador')
            textos = []
            for a in mm.alertas_cliente:
                textos.append('CLIENTE: ' + a)
                alertas.append((m.n, p.codigo, '(cliente)', 'media', 'Texto del cliente', a))
            precios_ref = []
            for k, pv in enumerate(provs):
                c = c_ini[k]
                o = pv['ofertas'].get(mm.id)
                lp, lq, li = L(c + 3), L(c + 1), L(c + 4)
                if not pv.get('referencia'):
                    precios_ref.append(('%s%d' % (lp, r), pv['nombre']))
                if o:
                    cc = ws.cell(r, c, o.codigos if o.codigos.replace('(s/c)', '').strip(' +') else
                                 '(sin código) ' + o.principal.partida.descripcion[:40])
                    cc.comment = Comment(('%s\n\nPuntuación %.2f · %s' % (o.descripcion[:500], o.puntuacion, o.estado)),
                                         pv['nombre'])
                    if o.cant_prov is not None:
                        ws.cell(r, c + 1, o.cant_prov)
                    ws.cell(r, c + 2, '=IF({0}{1}="","",{0}{1}-H{1})'.format(lq, r))
                    if o.precio is not None:
                        ws.cell(r, c + 3, round(o.precio, 4))
                    graves = [t for g, t in o.alertas if g == 'alta']
                    if graves:
                        cc.fill = R_NARANJA
                    elif o.estado == 'revisar':
                        cc.fill = R_AMARILLO
                    for g, t in o.alertas:
                        textos.append('%s: %s' % (pv['nombre'], t))
                        alertas.append((m.n, p.codigo, pv['nombre'], g, 'Oferta distinta / cantidad', t))
                    if o.estado == 'revisar' and not o.alertas:
                        alertas.append((m.n, p.codigo, pv['nombre'], 'baja', 'Emparejamiento',
                                        'Emparejamiento con poca seguridad (%.2f): comprobar que "%s" corresponde a la partida.'
                                        % (o.puntuacion, o.principal.partida.descripcion[:60])))
                if o and o.cant_necesaria is not None:
                    ws.cell(r, c + 4, '=IF({0}{1}="","",{0}{1}*{2})'.format(lp, r, o.cant_necesaria))
                    ws.cell(r, c + 4).comment = Comment('Importe = precio x %s unidades necesarias para este proveedor '
                                                        '(cálculo por potencia).' % o.cant_necesaria, 'Automatizador')
                    ws.cell(r, c + 2, '=IF({0}{1}="","",{0}{1}-{2})'.format(lq, r, o.cant_necesaria))
                else:
                    ws.cell(r, c + 4, '=IF({0}{1}="","",{0}{1}*H{1})'.format(lp, r))
                for j in range(len(BLOQUE)):
                    ws.cell(r, c + j).border = BORDE
            # columnas finales
            lista = ','.join(ref for ref, _ in precios_ref)
            if precios_ref:
                expr = '""'
                for ref, nom in reversed(precios_ref):
                    expr = 'IF(%s=MIN(%s),"%s",%s)' % (ref, lista, nom.replace('"', "'"), expr)
                ws.cell(r, c_fin, '=IF(COUNT(%s)=0,"",%s)' % (lista, expr))
                ws.cell(r, c_fin + 1, '=IF(COUNT(%s)=0,"",MIN(%s))' % (lista, lista))
                ws.cell(r, c_fin + 2, '=IF({0}{1}="","",{0}{1}*H{1})'.format(L(c_fin + 1), r))
            h = res.historico.get(mm.id)
            if h:
                mej = h['mejor']
                ws.cell(r, c_fin + 3, round(mej['precio_neto'], 4))
                ws.cell(r, c_fin + 4, '%s (%s · %s)' % (mej['proveedor'], mej['fecha'] or '', mej['obra']))
                ws.cell(r, c_fin + 4).comment = Comment('\n'.join(
                    '%s: %.4f € (%s, %s) — %s' % (x['proveedor'], x['precio_neto'], x['fecha'] or '', x['obra'],
                                                  x['descripcion'][:60]) for x in h['ultimos'][:10]), 'BBDD')
                if h['aviso']:
                    textos.append('BBDD: ' + h['aviso'])
                    alertas.append((m.n, p.codigo, mej['proveedor'], 'media', 'Precio más barato en la BBDD', h['aviso']))
                    ws.cell(r, c_fin + 3).fill = R_VERDE
                    ws.cell(r, c_fin + 4).fill = R_VERDE
            for t in res.avisos_aprendidos(mm):
                textos.append('APRENDIDO: ' + t)
                alertas.append((m.n, p.codigo, '(aprendido)', 'media', 'Caso aprendido / óptimo BBDD', t))
            ws.cell(r, c_fin + 5, '\n'.join(textos))
            ws.cell(r, c_fin + 5).font = F_ALERTA
            ws.cell(r, c_fin + 5).alignment = ENVOLVER
            for cidx in range(1, c_fin + len(FINALES)):
                cel = ws.cell(r, cidx)
                cel.border = BORDE
                if cel.font != F_ALERTA:
                    cel.font = F_NORMAL
                if cidx in (4, 5, 1):
                    cel.alignment = ENVOLVER
                elif cel.alignment != ENVOLVER:
                    cel.alignment = ARRIBA
            fila += 1
        if len(grupo) > 1:
            for pv in provs:
                tiene = [mm.id for mm in grupo if mm.id in pv['ofertas']]
                if tiene and len(tiene) < len(grupo):
                    faltan = [mm for mm in grupo if mm.id not in pv['ofertas']]
                    t = 'oferta PARCIAL de la partida: no se ha encontrado %s (la diferencia con el cliente solo ' \
                        'incluye lo ofertado).' % ', '.join('"%s"' % mm.descripcion for mm in faltan)
                    cel = ws.cell(f0, c_fin + 5)
                    cel.value = ((cel.value + '\n') if cel.value else '') + '%s: %s' % (pv['nombre'], t)
                    alertas.append((m.n, p.codigo, pv['nombre'], 'media', 'Oferta parcial', t))
        # celdas de partida (combinadas si hay varios materiales) y diferencias por partida
        for k, pv in enumerate(provs):
            c = c_ini[k]
            rango = '%s%d:%s%d' % (L(c + 4), f0, L(c + 4), f1)
            ws.cell(f0, c + 5, '=IF(OR(COUNT({0})=0,J{1}=""),"",J{1}-SUM({0}))'.format(rango, f0))
        if f1 > f0:
            for cidx in [1, 2, 3, 4, 6, 7, 9, 10] + [c_ini[k] + 5 for k in range(np_)]:
                if cidx == 2:
                    continue
                ws.merge_cells(start_row=f0, start_column=cidx, end_row=f1, end_column=cidx)
            for r in range(f0, f1 + 1):
                for cidx in range(1, 11):
                    ws.cell(r, cidx).fill = R_PARTIDA
        i += len(grupo)
    cerrar_capitulo(fila - 1)
    ultima_datos = fila - 1
    _subtotal(ws, fila, 'TOTAL PRESUPUESTO', primera_datos, ultima_datos, provs, c_ini, c_fin, R_TOTAL)
    fila_total = fila

    # ---------------------------------------------------------------- formatos numéricos y verde
    for r in range(primera_datos, fila_total + 1):
        ws.cell(r, 7).number_format = CANT
        ws.cell(r, 8).number_format = CANT
        ws.cell(r, 9).number_format = EUR
        ws.cell(r, 10).number_format = EUR
        for k in range(np_):
            c = c_ini[k]
            ws.cell(r, c + 1).number_format = CANT
            ws.cell(r, c + 2).number_format = DIFCANT
            ws.cell(r, c + 3).number_format = EUR4
            ws.cell(r, c + 4).number_format = EUR
            ws.cell(r, c + 5).number_format = EUR
        ws.cell(r, c_fin + 1).number_format = EUR4
        ws.cell(r, c_fin + 2).number_format = EUR
        ws.cell(r, c_fin + 3).number_format = EUR4
    dist = [k for k in range(np_) if not provs[k].get('referencia')]
    if dist:
        refs = ','.join('$%s%d' % (L(c_ini[k] + 3), primera_datos) for k in dist)
        for k in dist:
            for desp in (3, 4):
                col_l = L(c_ini[k] + desp)
                prec = '$%s%d' % (L(c_ini[k] + 3), primera_datos)
                regla = FormulaRule(formula=['AND(ISNUMBER(%s),COUNT(%s)>0,%s=MIN(%s))' % (prec, refs, prec, refs)],
                                    fill=R_VERDE, font=Font(name=FUENTE, size=9, bold=True, color='006100'))
                ws.conditional_formatting.add('%s%d:%s%d' % (col_l, primera_datos, col_l, ultima_datos), regla)
    ws.auto_filter.ref = 'A%d:%s%d' % (F_COL, L(c_fin + len(FINALES) - 1), ultima_datos)

    _hoja_resumen(wb, res, grupos, c_ini, c_fin, primera_datos, ultima_datos, c_capfila)
    _reparto(wb['Resumen'], res, c_ini, c_fin, primera_datos, ultima_datos)
    _hoja_alertas(wb, res, alertas)
    _hoja_lineas(wb, res)
    _hoja_bbdd(wb, res)
    wb.save(ruta)
    return ruta


def _cab(ws, r, c, texto, relleno):
    cel = ws.cell(r, c, texto)
    cel.font = F_CAB
    cel.fill = relleno
    cel.alignment = CENTRO
    cel.border = BORDE


def _subtotal(ws, r, texto, a, b, provs, c_ini, c_fin, relleno):
    ws.cell(r, 1, texto)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
    cols = [10] + [c_ini[k] + d for k in range(len(provs)) for d in (4, 5)] + [c_fin + 2]
    for c in cols:
        ws.cell(r, c, '=SUBTOTAL(9,{0}{1}:{0}{2})'.format(L(c), a, b))
    for c in range(1, c_fin + len(FINALES)):
        cel = ws.cell(r, c)
        cel.font = F_NEGRITA
        cel.fill = relleno
        cel.border = BORDE


def _hoja_resumen(wb, res, grupos, c_ini, c_fin, f_ini, f_fin, c_capfila):
    ws = wb.create_sheet('Resumen')
    provs = res.proveedores
    ws['A1'] = 'Resumen por capítulo — %s' % res.obra.nombre
    ws['A1'].font = F_TITULO
    ws['A2'] = ('Importes calculados con las cantidades de material del cliente. "Dif." = importe cliente − importe '
                'proveedor en las partidas que ese proveedor oferta. "Partidas ofertadas" cuenta los materiales con precio.')
    ws['A2'].font = F_GRIS
    cab = ['Capítulo', 'Importe cliente']
    for pv in provs:
        cab += ['%s · total' % pv['nombre'], '%s · dif. vs cliente' % pv['nombre'], '%s · materiales ofertados' % pv['nombre']]
    cab += ['Mejor combinación (P.U. más barato × cant.)', 'Materiales en el capítulo']
    r = 4
    for i, t in enumerate(cab, 1):
        _cab(ws, r, i, t, R_CAB)
    ws.row_dimensions[r].height = 42
    comp = "'Comparativa'!"
    rng = lambda col: '%s$%s$%d:$%s$%d' % (comp, L(col), f_ini, L(col), f_fin)   # noqa: E731
    r += 1
    ini = r
    for nombre, criterio_col in [(g[0], c_capfila) for g in grupos]:
        ws.cell(r, 1, nombre)
        crit = '%s,$A%d' % (rng(criterio_col), r)
        ws.cell(r, 2, '=SUMIFS(%s,%s)' % (rng(10), crit))
        c = 3
        for k, pv in enumerate(provs):
            ws.cell(r, c, '=SUMIFS(%s,%s)' % (rng(c_ini[k] + 4), crit))
            ws.cell(r, c + 1, '=SUMIFS(%s,%s)' % (rng(c_ini[k] + 5), crit))
            ws.cell(r, c + 2, '=COUNTIFS(%s,%s,"<>")' % (crit, rng(c_ini[k] + 3)))
            c += 3
        ws.cell(r, c, '=SUMIFS(%s,%s)' % (rng(c_fin + 2), crit))
        ws.cell(r, c + 1, '=COUNTIFS(%s)' % crit)
        r += 1
    fin = r - 1
    ws.cell(r, 1, 'TOTAL')
    for c in range(2, len(cab) + 1):
        ws.cell(r, c, '=SUM(%s%d:%s%d)' % (L(c), ini, L(c), fin))
    for rr in range(ini, r + 1):
        for c in range(1, len(cab) + 1):
            cel = ws.cell(rr, c)
            cel.border = BORDE
            cel.font = F_NEGRITA if rr == r else F_NORMAL
            if rr == r:
                cel.fill = R_TOTAL
            if c >= 2:
                es_cuenta = (c - 3) % 3 == 2 and c < 3 + 3 * len(provs) or c == len(cab)
                cel.number_format = '0' if es_cuenta else EUR
    ws.column_dimensions['A'].width = 40
    for c in range(2, len(cab) + 1):
        ws.column_dimensions[L(c)].width = 15
    # datos de cada oferta
    r += 3
    ws.cell(r, 1, 'Ofertas cargadas').font = F_NEGRITA
    r += 1
    cab2 = ['Proveedor', 'Fichero', 'Fecha', 'Validez', 'Líneas leídas', 'Líneas casadas', 'Líneas sin casar',
            'Total del documento', 'Suma de líneas leídas', '¿Cuadra?', 'Avisos de la lectura']
    for i, t in enumerate(cab2, 1):
        _cab(ws, r, i, t, R_CAB)
    for pv in provs:
      for x in pv.get('docs') or [{'doc': pv['doc'], 'archivo': pv['archivo']}]:
        r += 1
        d = x['doc']
        suma = round(sum(p.importe_exacto for p in d.partidas() if p.precio is not None), 2)
        cuadra = '' if d.total_declarado is None else ('Sí' if abs(suma - d.total_declarado) <= 0.05 else
                                                         'NO (dif. %.2f €)' % (suma - d.total_declarado))
        lineas_doc = [l for l in pv['lineas'] if getattr(l, 'huella', x.get('huella')) == x.get('huella')]
        sin_doc = [l for l in pv['sin'] if getattr(l, 'huella', x.get('huella')) == x.get('huella')]
        vals = [pv['nombre'], x['archivo'].split('/')[-1], d.fecha, d.validez, len(lineas_doc),
                len(lineas_doc) - len(sin_doc), len(sin_doc), d.total_declarado, suma, cuadra,
                '\n'.join(a.texto for a in d.avisos if a.nivel != 'info' and 'importe calculado' not in a.texto)[:1500]]
        for i, v in enumerate(vals, 1):
            cel = ws.cell(r, i, v)
            cel.font = F_NORMAL
            cel.border = BORDE
            cel.alignment = ENVOLVER
            if i in (8, 9):
                cel.number_format = EUR
        if cuadra.startswith('NO'):
            ws.cell(r, 10).font = F_ALERTA
    ws.column_dimensions['K'].width = 70
    ws.freeze_panes = 'B5'


def _reparto(ws, res, c_ini, c_fin, f_ini, f_fin):
    """Reparto entre distribuidores comprando cada material al más barato (fórmulas sobre la Comparativa)."""
    r = ws.max_row + 3
    ws.cell(r, 1, 'Reparto entre distribuidores (cada material al más barato)').font = F_NEGRITA
    ws.cell(r + 1, 1, 'Si se compra cada material al distribuidor con el unitario más bajo: cuánto se adjudica a cada '
                      'uno. "Si se le compra todo lo que oferta" = su total en la Comparativa. Las bases de precios de '
                      'referencia no cuentan.').font = F_GRIS
    r += 3
    cab = ['Distribuidor', 'Materiales adjudicados', 'Importe adjudicado', '% del total', 'Materiales que oferta',
           'Si se le compra todo lo que oferta']
    for i, t in enumerate(cab, 1):
        _cab(ws, r, i, t, R_CAB)
    ws.row_dimensions[r].height = 30
    comp = "'Comparativa'!"
    rng = lambda col: '%s$%s$%d:$%s$%d' % (comp, L(col), f_ini, L(col), f_fin)   # noqa: E731
    ini = r + 1
    dist = [(k, pv) for k, pv in enumerate(res.proveedores) if not pv.get('referencia')]
    fin = ini + len(dist) - 1
    for j, (k, pv) in enumerate(dist):
        rr = ini + j
        ws.cell(rr, 1, pv['nombre'])
        ws.cell(rr, 2, '=COUNTIFS(%s,$A%d)' % (rng(c_fin), rr))
        ws.cell(rr, 3, '=SUMIFS(%s,%s,$A%d)' % (rng(c_fin + 2), rng(c_fin), rr))
        ws.cell(rr, 4, '=IF(SUM($C$%d:$C$%d)=0,"",C%d/SUM($C$%d:$C$%d))' % (ini, fin, rr, ini, fin))
        ws.cell(rr, 5, '=COUNT(%s)' % rng(c_ini[k] + 3))
        ws.cell(rr, 6, '=SUMIFS(%s,%s,"<>")' % (rng(c_ini[k] + 4), rng(8)))    # solo filas de material
    rt = fin + 1
    ws.cell(rt, 1, 'TOTAL (mejor combinación)')
    ws.cell(rt, 2, '=SUM(B%d:B%d)' % (ini, fin))
    ws.cell(rt, 3, '=SUM(C%d:C%d)' % (ini, fin))
    ws.cell(rt + 1, 1, 'Materiales sin oferta de ningún distribuidor')
    ws.cell(rt + 1, 2, '=COUNTIFS(%s,"<>",%s,"")' % (rng(5), rng(c_fin)))
    for rr in range(ini, rt + 2):
        for c in range(1, 7):
            cel = ws.cell(rr, c)
            cel.border = BORDE
            cel.font = F_NEGRITA if rr == rt else F_NORMAL
            if rr == rt:
                cel.fill = R_TOTAL
            cel.number_format = {3: EUR, 4: '0.0%', 6: EUR}.get(c, '0')


def _hoja_alertas(wb, res, alertas):
    ws = wb.create_sheet('Alertas')
    ws['A1'] = 'Alertas — revisar antes de decidir'
    ws['A1'].font = F_TITULO
    cab = ['Nº licit.', 'Código cliente', 'Proveedor', 'Gravedad', 'Tipo', 'Detalle']
    for i, t in enumerate(cab, 1):
        _cab(ws, 3, i, t, R_CAB)
    orden = {'alta': 0, 'media': 1, 'baja': 2}
    filas = sorted(alertas, key=lambda a: (orden.get(a[3], 3), a[0]))
    for pv in res.proveedores:
        for l in pv['sin']:
            if l.partida.precio is None and not l.partida.cantidad:
                continue
            filas.append(('', '', pv['nombre'], 'baja', 'Línea sin casar',
                          'Línea %d "%s" (%s) no corresponde a ninguna partida del cliente: no se compara.' % (
                              l.i + 1, l.partida.descripcion[:80], l.referencia or 's/c')))
    r = 4
    for a in filas:
        for i, v in enumerate(a, 1):
            cel = ws.cell(r, i, v)
            cel.font = F_ALERTA if a[3] == 'alta' and i == 6 else F_NORMAL
            cel.border = BORDE
            cel.alignment = ENVOLVER
        if a[3] == 'alta':
            ws.cell(r, 4).fill = R_NARANJA
        elif a[3] == 'media':
            ws.cell(r, 4).fill = R_AMARILLO
        r += 1
    for c, w in zip('ABCDEF', (8, 14, 16, 9, 24, 110)):
        ws.column_dimensions[c].width = w
    ws.auto_filter.ref = 'A3:F%d' % max(3, r - 1)
    ws.freeze_panes = 'A4'


def _hoja_lineas(wb, res):
    ws = wb.create_sheet('Lineas proveedores')
    cab = ['Proveedor', 'Nº línea', 'Sección', 'Código', 'Descripción', 'Cantidad', 'Precio lista', 'Dto %', 'Precio neto',
           'Importe', 'Casada con Nº licit.', 'Código cliente', 'Material del cliente', 'Tipo', 'Puntuación', 'Origen',
           'Notas']
    for i, t in enumerate(cab, 1):
        _cab(ws, 1, i, t, R_CAB)
    mats = {m.id: m for m in res.materiales}
    r = 2
    for pv in res.proveedores:
        por_linea = {a.linea.i: a for a in pv['asign']}
        for l in pv['lineas']:
            if pv.get('catalogo') and l.i not in por_linea:
                continue                   # base de precios: solo los artículos que se han usado
            p = l.partida
            a = por_linea.get(l.i)
            m = mats.get(a.material_id) if a else None
            vals = [pv['nombre'], l.i + 1, l.seccion, p.referencia, p.descripcion, p.cantidad, p.precio_lista, p.dto_pct,
                    p.precio, '=IF(OR(F{0}="",I{0}=""),"",F{0}*I{0})'.format(r),
                    m.id if m else '', m.codigo if m else '', m.descripcion if m else '',
                    a.tipo if a else 'SIN CASAR', round(a.puntuacion, 2) if a else '', a.origen if a else '',
                    '; '.join(p.notas)]
            for i, v in enumerate(vals, 1):
                cel = ws.cell(r, i, v)
                cel.font = F_NORMAL
                cel.border = BORDE
            for i in (7, 9):
                ws.cell(r, i).number_format = EUR4
            ws.cell(r, 10).number_format = EUR
            ws.cell(r, 6).number_format = CANT
            if not a:
                ws.cell(r, 14).fill = R_AMARILLO
            r += 1
    for c, w in zip(range(1, 18), (14, 7, 18, 18, 55, 9, 10, 6, 10, 11, 8, 13, 35, 11, 9, 8, 30)):
        ws.column_dimensions[L(c)].width = w
    ws.auto_filter.ref = 'A1:Q%d' % max(1, r - 1)
    ws.freeze_panes = 'A2'


def _hoja_bbdd(wb, res):
    ws = wb.create_sheet('BBDD precios')
    ws['A1'] = 'Precios registrados en la base de datos para los materiales de esta obra (otras obras / fechas)'
    ws['A1'].font = F_NEGRITA
    cab = ['Nº licit.', 'Código cliente', 'Material', 'Proveedor', 'Precio neto', 'Fecha', 'Obra', 'Código proveedor',
           'Descripción del proveedor', 'Por qué se considera el mismo material']
    for i, t in enumerate(cab, 1):
        _cab(ws, 3, i, t, R_CAB)
    r = 4
    for m in res.materiales:
        h = res.historico.get(m.id)
        if not h:
            continue
        for x in h['filas'][:25]:
            vals = [m.id, m.codigo, m.descripcion, x['proveedor'], x['precio_neto'], x['fecha'], x['obra'], x['codigo'],
                    x['descripcion'], x['motivo']]
            for i, v in enumerate(vals, 1):
                cel = ws.cell(r, i, v)
                cel.font = F_NORMAL
                cel.border = BORDE
            ws.cell(r, 5).number_format = EUR4
            r += 1
    if r == 4:
        ws.cell(4, 1, 'Todavía no hay precios de otras obras para estos materiales: se irán acumulando con cada obra.').font = F_GRIS
    for c, w in zip(range(1, 11), (8, 14, 35, 16, 11, 11, 25, 18, 50, 40)):
        ws.column_dimensions[L(c)].width = w
    ws.freeze_panes = 'A4'
