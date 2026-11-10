"""Libro de diferencias: licitación frente a la oferta de un proveedor, partida a partida."""
import collections

from xlsxwriter.utility import xl_rowcol_to_cell as celda

from ..modelo import r2
from . import estilo as S

corto = S.corto


def filas(lic_hojas, of_hojas, elegidas, estados):
    """Una fila (dict) por partida de licitación con precio del proveedor."""
    O = {o.n: o for o in of_hojas}
    por_lic = {ln: on for on, ln in elegidas.items()}
    cont, pos = collections.Counter(), {}
    for h in lic_hojas:                       # posición dentro de su capítulo = número de partida en m4PRO
        if h.n in por_lic:
            cont[h.ruta] += 1
            pos[h.n] = cont[h.ruta]
    out = []
    for h in lic_hojas:
        if h.n not in por_lic:
            continue
        on = por_lic[h.n]
        l, o = h.partida, O[on].partida
        pl, pp = l.precio, o.precio
        imp_l = l.importe
        imp_p = round(l.cantidad * r2(pp), 2) if pp is not None else 0.0
        out.append({'capitulo': h.ruta, 'pos': pos[h.n], 'codigo': l.codigo, 'descripcion': l.descripcion,
                    'cantidad': l.cantidad, 'precio_lic': pl, 'precio_prov': pp, 'imp_lic': imp_l, 'imp_prov': imp_p,
                    'dif_precio': (pp - pl) if pp is not None and pl is not None else None,
                    'dif_pct': (pp / pl - 1) if (pp is not None and pl) else None,
                    'dif_imp': round(imp_p - imp_l, 2), 'linea_oferta': on, 'estado': estados.get(on, '')})
    return out


CAB = ['Capítulo', 'Nº en m4PRO', 'Código concepto', 'Descripción', 'Cantidad', 'Precio licitación', 'Precio {p}',
       'Dif. €/ud', 'Dif. %', 'Importe licitación', 'Importe {p}', 'Dif. importe €', 'Línea de la oferta', 'Estado emparejamiento']
ANCHOS = [30, 9, 16, 62, 10, 13, 13, 11, 9, 15, 15, 15, 10, 16]


def _hoja_partidas(wb, E, titulo, subtitulo, datos, proveedor, nombre_hoja):
    ws = wb.add_worksheet(nombre_hoja)
    NC = len(CAB)
    S.banner(ws, E, titulo, subtitulo, NC)
    for i, w in enumerate(ANCHOS):
        ws.set_column(i, i, w)
    R_TOT, R_CAB = 2, 3
    first = R_CAB + 1
    last = first + len(datos) - 1
    ws.set_row(R_CAB, 34)
    for c, t in enumerate(CAB):
        ws.write(R_CAB, c, t.format(p=proveedor), E.cab())
    f_txt, f_eur, f_num = E.celda(), E.celda(num_format=S.EUR), E.celda(num_format=S.NUM)
    for j, d in enumerate(datos):
        r = first + j
        ws.write(r, 0, corto(d['capitulo'], 50), f_txt)
        ws.write(r, 1, d['pos'], E.celda(num_format='0', align='center'))
        ws.write(r, 2, d['codigo'], f_txt)
        ws.write(r, 3, corto(d['descripcion'], 110), f_txt)
        ws.write(r, 4, d['cantidad'], f_num)
        ws.write(r, 5, d['precio_lic'], f_eur)
        if d['precio_prov'] is None:
            ws.write_blank(r, 6, None, f_eur)
        else:
            ws.write(r, 6, d['precio_prov'], f_eur)
        ws.write_formula(r, 7, '=IF(ISNUMBER(%s),%s-%s,"")' % (celda(r, 6), celda(r, 6), celda(r, 5)),
                         E.celda(num_format=S.DEUR), d['dif_precio'] if d['dif_precio'] is not None else '')
        ws.write_formula(r, 8, '=IF(AND(ISNUMBER(%s),%s<>0),%s/%s-1,"")' % (celda(r, 6), celda(r, 5), celda(r, 6), celda(r, 5)),
                         E.celda(num_format=S.DPCT), d['dif_pct'] if d['dif_pct'] is not None else '')
        ws.write_formula(r, 9, '=ROUND(%s*ROUND(%s,2),2)' % (celda(r, 4), celda(r, 5)), f_eur, round(d['imp_lic'], 2))
        ws.write_formula(r, 10, '=ROUND(%s*ROUND(N(%s),2),2)' % (celda(r, 4), celda(r, 6)), f_eur, round(d['imp_prov'], 2))
        ws.write_formula(r, 11, '=%s-%s' % (celda(r, 10), celda(r, 9)), E.celda(num_format=S.DEUR, bold=True), d['dif_imp'])
        ws.write(r, 12, d['linea_oferta'], E.celda(num_format='0', align='center'))
        ws.write(r, 13, d['estado'], E.celda(align='center'))
    tf = E(bold=True, bg_color=S.CLARO, num_format=S.EUR, top=2, bottom=2, top_color=S.AZUL, bottom_color=S.AZUL)
    ws.set_row(R_TOT, 22)
    ws.write(R_TOT, 0, 'TOTAL filas visibles', E(bold=True, bg_color=S.CLARO, top=2, bottom=2, top_color=S.AZUL, bottom_color=S.AZUL))
    for c in range(1, NC):
        ws.write(R_TOT, c, '', tf)
    if datos:
        ti = sum(d['imp_lic'] for d in datos)
        tp = sum(d['imp_prov'] for d in datos)
        rg = lambda c: '%s:%s' % (celda(first, c), celda(last, c))   # noqa: E731
        ws.write_formula(R_TOT, 9, '=SUBTOTAL(109,%s)' % rg(9), tf, round(ti, 2))
        ws.write_formula(R_TOT, 10, '=SUBTOTAL(109,%s)' % rg(10), tf, round(tp, 2))
        ws.write_formula(R_TOT, 11, '=SUBTOTAL(109,%s)' % rg(11), E(bold=True, bg_color=S.CLARO, num_format=S.DEUR, top=2, bottom=2,
                                                                  top_color=S.AZUL, bottom_color=S.AZUL), round(tp - ti, 2))
        g = celda(first, 6, False, True)
        # sin precio -> ámbar; más barato -> verde; más caro -> rojo
        for col in (6, 7, 8, 10, 11):
            ws.conditional_format(first, col, last, col, {'type': 'formula', 'criteria': '=NOT(ISNUMBER(%s))' % g, 'stop_if_true': True,
                                                          'format': E(bg_color=S.AMBAR_BG)})
        for col in (7, 8, 11):
            ws.conditional_format(first, col, last, col, {'type': 'formula', 'criteria': '=%s<0' % celda(first, 11, False, True),
                                                          'format': E(bg_color=S.VERDE_BG, font_color=S.VERDE_TX)})
            ws.conditional_format(first, col, last, col, {'type': 'formula', 'criteria': '=%s>0' % celda(first, 11, False, True),
                                                          'format': E(bg_color=S.ROJO_BG, font_color=S.ROJO_TX)})
        e = celda(first, 13, False, True)
        for texto, bg, tx in (('seguro', S.VERDE_BG, S.VERDE_TX), ('revisar', S.AMBAR_BG, S.AMBAR_TX),
                              ('elegido a mano', S.AZUL_BG, S.AZUL_TX)):
            ws.conditional_format(first, 13, last, 13, {'type': 'formula', 'criteria': '=%s="%s"' % (e, texto),
                                                        'format': E(bg_color=bg, font_color=tx, bold=True)})
        ws.autofilter(R_CAB, 0, last, NC - 1)
    ws.freeze_panes(first, 4)
    S.imprimir(ws, repetir=(R_CAB, R_CAB))
    return ws


def escribir(lic_hojas, of_hojas, elegidas, estados, proveedor, ruta):
    datos = filas(lic_hojas, of_hojas, elegidas, estados)
    wb, E = S.nuevo_libro(ruta)

    # ============================================================ Resumen por capítulo
    ws = wb.add_worksheet('Resumen por capítulo')
    NC = 6
    ta = sum(d['imp_lic'] for d in datos)
    tb = sum(d['imp_prov'] for d in datos)
    S.banner(ws, E, 'Licitación frente a %s' % proveedor, '%d partidas comparadas · el importe de cada partida usa la regla de m4PRO '
                                                           '(precio a 2 decimales × cantidad)' % len(datos), NC)
    for i, w in enumerate([70, 10, 18, 18, 16, 12]):
        ws.set_column(i, i, w)
    S.tarjeta(ws, E, 3, 0, 'IMPORTE LICITACIÓN', round(ta, 2), S.EUR, ancho=1, nota='de las partidas comparadas')
    S.tarjeta(ws, E, 3, 1, 'IMPORTE %s' % proveedor.upper(), round(tb, 2), S.EUR, ancho=3, color=S.NAVY)
    d = tb - ta
    S.tarjeta(ws, E, 3, 4, 'DIFERENCIA', round(d, 2), S.DEUR, ancho=2, color=S.VERDE if d <= 0 else S.ROJO,
              nota=('%+.1f %% frente a la licitación' % ((tb / ta - 1) * 100)) if ta else '')
    ws.set_row(4, 32)
    por_cap = collections.OrderedDict()
    for x in datos:
        c = por_cap.setdefault(x['capitulo'], [0, 0.0, 0.0])
        c[0] += 1
        c[1] += x['imp_lic']
        c[2] += x['imp_prov']
    HC = 7
    ws.set_row(HC, 32)
    for c, t in enumerate(['Capítulo', 'Partidas', 'Importe licitación', 'Importe %s' % proveedor, 'Diferencia €', 'Diferencia %']):
        ws.write(HC, c, t, E.cab())
    r = HC
    for cap, (n, a, b) in por_cap.items():
        r += 1
        ws.write(r, 0, corto(cap, 90), E.celda())
        ws.write(r, 1, n, E.celda(num_format='0', align='center'))
        ws.write(r, 2, round(a, 2), E.celda(num_format=S.EUR))
        ws.write(r, 3, round(b, 2), E.celda(num_format=S.EUR))
        ws.write_formula(r, 4, '=%s-%s' % (celda(r, 3), celda(r, 2)), E.celda(num_format=S.DEUR), round(b - a, 2))
        ws.write_formula(r, 5, '=IF(%s=0,"",%s/%s-1)' % (celda(r, 2), celda(r, 3), celda(r, 2)), E.celda(num_format=S.DPCT),
                         (b / a - 1) if a else '')
    p1, p2 = HC + 1, r
    if p2 >= p1:
        for col in (4, 5):
            ws.conditional_format(p1, col, p2, col, {'type': 'formula', 'criteria': '=%s<0' % celda(p1, 4, False, True),
                                                     'format': E(bg_color=S.VERDE_BG, font_color=S.VERDE_TX)})
            ws.conditional_format(p1, col, p2, col, {'type': 'formula', 'criteria': '=%s>0' % celda(p1, 4, False, True),
                                                     'format': E(bg_color=S.ROJO_BG, font_color=S.ROJO_TX)})
    tt = E(bold=True, bg_color=S.CLARO, top=2, top_color=S.AZUL, num_format=S.EUR)
    ws.write(r + 1, 0, 'TOTAL', E(bold=True, bg_color=S.CLARO, top=2, top_color=S.AZUL))
    ws.write_formula(r + 1, 1, '=SUM(%s:%s)' % (celda(p1, 1), celda(p2, 1)), E(bold=True, bg_color=S.CLARO, top=2, top_color=S.AZUL,
                                                                             num_format='0', align='center'), len(datos))
    ws.write_formula(r + 1, 2, '=SUM(%s:%s)' % (celda(p1, 2), celda(p2, 2)), tt, round(ta, 2))
    ws.write_formula(r + 1, 3, '=SUM(%s:%s)' % (celda(p1, 3), celda(p2, 3)), tt, round(tb, 2))
    ws.write_formula(r + 1, 4, '=%s-%s' % (celda(r + 1, 3), celda(r + 1, 2)),
                     E(bold=True, bg_color=S.CLARO, top=2, top_color=S.AZUL, num_format=S.DEUR), round(tb - ta, 2))
    ws.write_formula(r + 1, 5, '=IF(%s=0,"",%s/%s-1)' % (celda(r + 1, 2), celda(r + 1, 3), celda(r + 1, 2)),
                     E(bold=True, bg_color=S.CLARO, top=2, top_color=S.AZUL, num_format=S.DPCT), (tb / ta - 1) if ta else '')
    if por_cap:
        ch = wb.add_chart({'type': 'bar'})
        ch.add_series({'name': 'Licitación', 'categories': ['Resumen por capítulo', p1, 0, p2, 0],
                       'values': ['Resumen por capítulo', p1, 2, p2, 2], 'fill': {'color': '#98A2B3'}})
        ch.add_series({'name': proveedor, 'categories': ['Resumen por capítulo', p1, 0, p2, 0],
                       'values': ['Resumen por capítulo', p1, 3, p2, 3], 'fill': {'color': S.AZUL}})
        ch.set_title({'name': 'Importe por capítulo', 'name_font': {'size': 12, 'color': S.NAVY}})
        ch.set_x_axis({'num_format': '#,##0 €', 'major_gridlines': {'visible': True, 'line': {'color': '#E4E7EC'}}})
        ch.set_y_axis({'reverse': True, 'num_font': {'size': 8}})
        ch.set_legend({'position': 'bottom'})
        ch.set_size({'width': 900, 'height': max(300, 80 + 38 * len(por_cap))})
        ws.insert_chart(r + 4, 0, ch, {'x_offset': 4})
    ws.activate()
    S.imprimir(ws, repetir=(HC, HC), una_pagina=len(por_cap) <= 12)

    _hoja_partidas(wb, E, 'Detalle por partida', 'Verde = %s más barato que la licitación · Rojo = más caro · Ámbar = sin precio' % proveedor,
                   datos, proveedor, 'Por partida')
    _hoja_partidas(wb, E, 'Mayores diferencias', 'Ordenadas de mayor ahorro a mayor sobrecoste (importe). Usa el filtro para quedarte con las que te interesen.',
                   sorted(datos, key=lambda x: x['dif_imp']), proveedor, 'Mayores diferencias')
    wb.close()
    return datos
