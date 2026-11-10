"""Comparativa de ofertas: la licitación frente a VARIOS proveedores en un solo libro Excel.

El programa enseña los números y lo que hay que vigilar; la elección del proveedor es de una persona.
Hojas: Resumen (tarjetas, tabla, avisos, gráfico) · Por capítulo · Por partida (con filtros y totales vivos).
"""
import collections
import datetime

from xlsxwriter.utility import xl_col_to_name as col_name, xl_rowcol_to_cell as celda

from ..modelo import r2
from . import estilo as S


def _fila_precios(lic_hojas, resultados):
    """Para cada partida de licitación con precio de algún proveedor: {'hoja', 'of': [partida|None por proveedor]}"""
    por, mapas = [], []
    for r in resultados:
        O = {h.n: h for h in r['of_hojas']}
        mapas.append({ln: O[on].partida for on, ln in r['elegidas'].items()})
    for h in lic_hojas:
        if any(h.n in m for m in mapas):
            por.append({'hoja': h, 'of': [m.get(h.n) for m in mapas]})
    return por


def _imp(lic_partida, of_partida):
    """Importe de la partida de licitación al precio del proveedor (None si no lo valora)."""
    if of_partida is None or of_partida.precio is None or of_partida.precio == 0:
        return None
    return round(lic_partida.cantidad * r2(of_partida.precio), 2)


ETIQUETAS = [('forma_pago', 'forma de pago'), ('plazo_entrega', 'plazo de entrega'), ('portes', 'portes'), ('iva', 'IVA'),
             ('ecoraee', 'ECORAEE'), ('garantia', 'garantía')]


def _condiciones(doc):
    c = doc.condiciones
    partes = []
    for clave, nombre in ETIQUETAS:
        v = c.get(clave)
        if clave == 'plazo_entrega' and not v:
            v = 'NO INDICADO'
        if v:
            partes.append('%s: %s' % (nombre, v))
    if c.get('netos_condicionados'):
        partes.append('NETOS SOLO PARA EL TOTAL DE LAS PARTIDAS')
    return '; '.join(partes)


def _caducada(validez):
    try:
        return datetime.datetime.strptime(validez, '%d/%m/%Y').date() < datetime.date.today()
    except (TypeError, ValueError):
        return False


def escribir(lic_hojas, resultados, ruta, nombre_licitacion=''):
    nombres = [r['proveedor'] for r in resultados]
    n = len(nombres)
    filas = _fila_precios(lic_hojas, resultados)
    wb, E = S.nuevo_libro(ruta)

    # ------------------------------------------------------------------ datos de proveedores
    stats, totales = [], []
    for k, r in enumerate(resultados):
        val = sin = 0
        base = prov = 0.0
        for f in filas:
            of = f['of'][k]
            if of is None:
                continue
            i = _imp(f['hoja'].partida, of)
            if i is None:
                sin += 1
            else:
                val += 1
                base += f['hoja'].partida.importe
                prov += i
        doc = r['of_doc']
        suma = round(sum(p.importe_exacto for p in doc.partidas()), 2)
        stats.append({'val': val, 'sin': sin, 'base': round(base, 2), 'prov': round(prov, 2), 'doc': doc, 'suma': suma,
                      'impreso': doc.total_declarado})
        totales.append((base, prov))
    mejor = min(range(n), key=lambda k: stats[k]['prov']) if n else None
    total_cliente = round(sum(f['hoja'].partida.importe for f in filas), 2)

    # ================================================================== RESUMEN
    ws = wb.add_worksheet('Resumen')
    NC = 13
    S.banner(ws, E, 'Comparativa de ofertas', (nombre_licitacion or 'Licitación') +
             '  ·  %d proveedor%s  ·  generado el %s' % (n, '' if n == 1 else 'es', datetime.date.today().strftime('%d/%m/%Y')), NC)
    for i, w in enumerate([20, 12, 14, 11, 11, 17, 16, 15, 11, 16, 16, 9, 70]):
        ws.set_column(i, i, w)
    # tarjetas: 3 columnas cada una, hasta 4 por fila
    fila = 3
    S.tarjeta(ws, E, fila, 0, 'CLIENTE (LICITACIÓN)', total_cliente, S.EUR, ancho=3, color='#667085',
              nota='precio máximo de las %d partidas comparadas' % len(filas))
    for k, st in enumerate(stats):
        if (k + 1) % 4 == 0:
            fila += 4
        col = ((k + 1) % 4) * 3
        d = (st['prov'] / st['base'] - 1) if st['base'] else 0
        es_mejor = (k == mejor and n > 1)
        S.tarjeta(ws, E, fila, col, nombres[k].upper() + ('   · importe más bajo' if es_mejor else ''), st['prov'],
                  S.EUR, ancho=3, color=S.VERDE if es_mejor else S.AZUL,
                  nota='%+.1f %% frente al Cliente (%s)  ·  %d partidas' % (d * 100, ('{:,.2f} €'.format(st['base'])
                                                                                         ).replace(',', 'X').replace('.', ',').replace('X', '.'), st['val']))
    fila += 4

    S.seccion(ws, E, fila, 'Resumen por proveedor', NC)
    fila += 1
    cab = ['Proveedor', 'Fecha oferta', 'Válida hasta', 'Partidas valoradas', 'Partidas sin precio',
           'Importe Cliente (mismas partidas)', 'Importe oferta', 'Diferencia €', 'Diferencia %',
           'Total impreso en la oferta', 'Suma de sus líneas', 'Cuadra', 'Condiciones']
    ws.set_row(fila, 44)
    for c, t in enumerate(cab):
        ws.write(fila, c, t, E.cab())
    fila_cab = fila
    ws.write_comment(fila, 5, 'Suma de la licitación SOLO de las partidas que este proveedor ha valorado.\n'
                              'Así la comparación es de lo mismo con lo mismo.', {'x_scale': 2})
    ws.write_comment(fila, 11, 'Compara el total que imprime la oferta con la suma de sus propias líneas.\n'
                               '"no" = hay algo en el total que no está en las líneas: pregunta al proveedor.', {'x_scale': 2})
    fila += 1
    ws.set_row(fila, 22)
    gris = dict(bg_color=S.GRIS, italic=True)
    ws.write(fila, 0, 'Cliente', E.celda(bold=True, **gris))
    for c in (1, 2, 4, 9, 10, 11):
        ws.write_blank(fila, c, None, E.celda(**gris))
    ws.write(fila, 3, len(filas), E.celda(num_format='0', **gris))
    ws.write(fila, 5, total_cliente, E.celda(num_format=S.EUR, **gris))
    ws.write(fila, 6, total_cliente, E.celda(num_format=S.EUR, bold=True, **gris))
    ws.write(fila, 7, 0, E.celda(num_format=S.DEUR, **gris))
    ws.write(fila, 8, 0, E.celda(num_format=S.DPCT, **gris))
    ws.write(fila, 12, 'Licitación: precios máximos del cliente. Es la referencia con la que se comparan las ofertas.', E.celda(**gris))
    fila_cliente = fila
    for k, st in enumerate(stats):
        fila += 1
        doc = st['doc']
        cuadra = 'sí' if st['impreso'] is not None and abs(st['suma'] - st['impreso']) <= 0.05 else (
            'no' if st['impreso'] is not None else '-')
        cad = _caducada(doc.validez)
        ws.set_row(fila, 32)
        t = E.celda(text_wrap=True, valign='top')
        ws.write(fila, 0, nombres[k], E.celda(bold=True, valign='top'))
        ws.write(fila, 1, doc.fecha or '', t)
        ws.write(fila, 2, ('%s (CADUCADA)' % doc.validez) if cad else (doc.validez or ''),
                 E.celda(text_wrap=True, valign='top', **({'bg_color': S.ROJO_BG, 'font_color': S.ROJO_TX, 'bold': True} if cad else {})))
        ws.write(fila, 3, st['val'], E.celda(num_format='0', valign='top'))
        ws.write(fila, 4, st['sin'], E.celda(num_format='0', valign='top'))
        ws.write(fila, 5, st['base'], E.celda(num_format=S.EUR, valign='top'))
        ws.write(fila, 6, st['prov'], E.celda(num_format=S.EUR, bold=True, valign='top'))
        ws.write_formula(fila, 7, '=%s-%s' % (celda(fila, 6), celda(fila, 5)), E.celda(num_format=S.DEUR, valign='top'),
                         round(st['prov'] - st['base'], 2))
        ws.write_formula(fila, 8, '=IF(%s=0,"",%s/%s-1)' % (celda(fila, 5), celda(fila, 6), celda(fila, 5)),
                         E.celda(num_format=S.DPCT, valign='top'), (st['prov'] / st['base'] - 1) if st['base'] else '')
        if st['impreso'] is None:
            ws.write_blank(fila, 9, None, E.celda())
        else:
            ws.write(fila, 9, st['impreso'], E.celda(num_format=S.EUR, valign='top'))
        ws.write(fila, 10, st['suma'], E.celda(num_format=S.EUR, valign='top'))
        ws.write(fila, 11, cuadra, E.celda(align='center', bold=True, valign='top',
                                           **({'bg_color': S.ROJO_BG, 'font_color': S.ROJO_TX} if cuadra == 'no' else {})))
        ws.write(fila, 12, _condiciones(doc), t)
    pri, ult = fila_cab + 2, fila          # los proveedores empiezan tras la fila del Cliente
    if n > 1:      # el importe oferta más bajo, en verde (solo informa: cada oferta puede cubrir partidas distintas)
        ws.conditional_format(pri, 6, ult, 6, {'type': 'formula', 'criteria': '=%s=MIN(%s:%s)' % (
            celda(pri, 6), celda(pri, 6, True, True), celda(ult, 6, True, True)),
            'format': E(bg_color=S.VERDE_BG, font_color=S.VERDE_TX, bold=True)})
    ws.conditional_format(pri, 11, ult, 11, {'type': 'cell', 'criteria': '==', 'value': '"sí"',
                                             'format': E(bg_color=S.VERDE_BG, font_color=S.VERDE_TX)})
    fila += 2

    # ---- a tener en cuenta
    S.seccion(ws, E, fila, 'A tener en cuenta antes de elegir', NC, color=S.AMBAR_TX)
    fila += 1
    hay = False
    for r in resultados:
        for a in r['of_doc'].avisos:
            if a.nivel in ('revisar', 'aviso'):
                S.caja(ws, E, fila, NC, '%s — %s: %s' % (r['proveedor'], a.nivel.upper(), a.texto), 'aviso', 235)
                fila += 1
                hay = True
    if any(st['sin'] for st in stats):
        S.caja(ws, E, fila, NC, 'Partidas sin precio: ' + '; '.join(
            '%s %d' % (nombres[k], st['sin']) for k, st in enumerate(stats) if st['sin']) +
            '. Esas partidas no entran en los importes (ver hoja "Por partida", celdas ámbar).', 'aviso', 235)
        fila += 1
        hay = True
    if any(r['of_doc'].condiciones.get('netos_condicionados') for r in resultados):
        teorico = 0.0
        for f in filas:
            im = [i for i in (_imp(f['hoja'].partida, of) for of in f['of']) if i is not None]
            teorico += min(im) if im else 0.0
        S.caja(ws, E, fila, NC, 'Referencia teórica (NO cotizable): eligiendo el más barato en cada partida saldrían '
                                '{:,.2f} € . Al menos una oferta exige aceptarse completa, así que no se puede mezclar '
                                'partida a partida.'.format(teorico), 'info', 235)
        fila += 1
        hay = True
    if not hay:
        S.caja(ws, E, fila, NC, 'Sin avisos.', 'ok')
        fila += 1
    S.caja(ws, E, fila, NC, 'La elección del proveedor es tuya: el programa solo muestra importes, diferencias y avisos.', 'info')
    fila += 2

    # ---- gráfico
    if n:
        ch = wb.add_chart({'type': 'column'})
        ch.add_series({'name': 'Cliente (mismas partidas)', 'categories': ['Resumen', pri, 0, ult, 0],
                       'values': ['Resumen', pri, 5, ult, 5], 'fill': {'color': '#98A2B3'}, 'gap': 80,
                       'data_labels': {'value': True, 'num_format': '#,##0', 'font': {'size': 8}}})
        ch.add_series({'name': 'Oferta', 'categories': ['Resumen', pri, 0, ult, 0], 'values': ['Resumen', pri, 6, ult, 6],
                       'fill': {'color': S.AZUL}, 'data_labels': {'value': True, 'num_format': '#,##0', 'font': {'size': 8}}})
        ch.set_title({'name': 'Importe de cada oferta frente al Cliente', 'name_font': {'size': 12, 'color': S.NAVY}})
        ch.set_y_axis({'num_format': '#,##0 €', 'major_gridlines': {'visible': True, 'line': {'color': '#E4E7EC'}}})
        ch.set_legend({'position': 'bottom'})
        ch.set_size({'width': 760, 'height': 330})
        ws.insert_chart(fila, 0, ch, {'x_offset': 4, 'y_offset': 4})
    ws.set_first_sheet()
    ws.activate()
    S.imprimir(ws)

    # ================================================================== POR CAPÍTULO
    wc = wb.add_worksheet('Por capítulo')
    NCc = 3 + n
    S.banner(wc, E, 'Importes por capítulo', 'El Cliente suma una vez cada partida que alguna oferta valora. Verde = importe más bajo del capítulo (el Cliente cuenta como uno más).', max(NCc, 4))
    wc.set_column(0, 0, 70)
    wc.set_column(1, NCc - 1, 18)
    cap = collections.OrderedDict()
    for f in filas:
        c = cap.setdefault(f['hoja'].ruta, {'lic': 0.0, 'of': [0.0] * n, 'nv': [0] * n})
        vals = [(k, _imp(f['hoja'].partida, of)) for k, of in enumerate(f['of'])]
        vals = [(k, i) for k, i in vals if i is not None]
        for k, i in vals:
            c['of'][k] += i
            c['nv'][k] += 1
        if vals:
            c['lic'] += f['hoja'].partida.importe
    hc = 4
    wc.set_row(hc, 34)
    for c, t in enumerate(['Capítulo', 'Importe Cliente'] + ['Importe %s' % x for x in nombres] + ['Más bajo']):
        wc.write(hc, c, t, E.cab())
    r = hc
    for ruta_cap, c in cap.items():
        r += 1
        wc.write(r, 0, S.corto(ruta_cap, 90), E.celda())
        wc.write(r, 1, round(c['lic'], 2), E.celda(num_format=S.EUR))
        cand = [(c['lic'], -1)] if c['lic'] else []
        for k in range(n):
            if c['nv'][k]:
                wc.write(r, 2 + k, round(c['of'][k], 2), E.celda(num_format=S.EUR))
                cand.append((c['of'][k], k))
            else:
                wc.write_blank(r, 2 + k, None, E.celda(bg_color=S.AMBAR_BG))
        wc.write(r, 2 + n, ('Cliente' if min(cand)[1] < 0 else nombres[min(cand)[1]]) if cand else '', E.celda(align='center'))
    p1, p2 = hc + 1, r
    if n > 1 and p2 >= p1:
        rng = '%s:%s' % (celda(p1, 1, False, True), celda(p1, 1 + n, False, True))
        wc.conditional_format(p1, 1, p2, 1 + n, {'type': 'formula', 'criteria': '=AND(COUNT(%s)>1,%s=MIN(%s))' % (
            rng, celda(p1, 1), rng), 'format': E(bg_color=S.VERDE_BG, font_color=S.VERDE_TX, bold=True)})
    # totales
    tot = E.celda(bold=True, bg_color=S.CLARO, num_format=S.EUR, top=2, top_color=S.AZUL)
    wc.write(r + 1, 0, 'TOTAL', E.celda(bold=True, bg_color=S.CLARO, top=2, top_color=S.AZUL))
    wc.write_formula(r + 1, 1, '=SUM(%s:%s)' % (celda(p1, 1), celda(p2, 1)), tot, round(sum(c['lic'] for c in cap.values()), 2))
    for k in range(n):
        wc.write_formula(r + 1, 2 + k, '=SUM(%s:%s)' % (celda(p1, 2 + k), celda(p2, 2 + k)), tot,
                         round(sum(c['of'][k] for c in cap.values()), 2))
    wc.write(r + 1, 2 + n, '', tot)
    wc.freeze_panes(hc + 1, 1)
    if cap:
        ch = wb.add_chart({'type': 'bar'})
        paleta = ['#98A2B3', S.AZUL, '#12B76A', '#F79009', '#7A5AF8', '#EE46BC']
        ch.add_series({'name': 'Cliente', 'categories': ['Por capítulo', p1, 0, p2, 0], 'values': ['Por capítulo', p1, 1, p2, 1],
                       'fill': {'color': paleta[0]}})
        for k in range(n):
            ch.add_series({'name': nombres[k], 'categories': ['Por capítulo', p1, 0, p2, 0],
                           'values': ['Por capítulo', p1, 2 + k, p2, 2 + k], 'fill': {'color': paleta[1 + k % 5]}})
        ch.set_title({'name': 'Por capítulo', 'name_font': {'size': 12, 'color': S.NAVY}})
        ch.set_x_axis({'num_format': '#,##0 €', 'major_gridlines': {'visible': True, 'line': {'color': '#E4E7EC'}}})
        ch.set_y_axis({'reverse': True, 'num_font': {'size': 8}})
        ch.set_legend({'position': 'bottom'})
        ch.set_size({'width': 900, 'height': max(280, 70 + 24 * len(cap) * (1 + n))})
        wc.insert_chart(r + 4, 0, ch, {'x_offset': 4})
    S.imprimir(wc, repetir=(hc, hc), una_pagina=len(cap) <= 12)

    # ================================================================== POR PARTIDA
    wp = wb.add_worksheet('Por partida')
    NP = 7 + 2 * n + 1 + n
    S.banner(wp, E, 'Precio de cada proveedor, partida a partida',
             'Verde = importe más bajo de la fila (el Cliente cuenta como uno más) · Ámbar = sin precio · Dif. = Cliente − oferta: positivo (verde) = la oferta es más barata · Los totales de la fila 3 siguen a los filtros', NP)
    anchos = [28, 8, 15, 58, 10, 12, 14] + [11, 14] * n + [14] + [15] * n
    for i, w in enumerate(anchos):
        wp.set_column(i, i, w)
    R_TOT, R_GRP, R_CAB = 2, 3, 4
    first = R_CAB + 1
    last = first + len(filas) - 1
    wp.set_row(R_CAB, 34)
    for c, t in enumerate(['Capítulo', 'Nº licit.', 'Código', 'Descripción', 'Cantidad', 'Precio Cliente', 'Importe Cliente']):
        wp.write(R_CAB, c, t, E.cab())
        if c < 5:
            wp.write(R_GRP, c, '', E.cab())
    wp.merge_range(R_GRP, 5, R_GRP, 6, 'Cliente', E(bold=True, font_color='#FFFFFF', bg_color='#667085', align='center'))
    for k in range(n):
        c0 = 7 + 2 * k
        wp.merge_range(R_GRP, c0, R_GRP, c0 + 1, nombres[k], E(bold=True, font_color='#FFFFFF', bg_color=S.NAVY, align='center'))
        wp.write(R_CAB, c0, 'Precio', E.cab())
        wp.write(R_CAB, c0 + 1, 'Importe', E.cab())
    cm, cd = 7 + 2 * n, 8 + 2 * n          # 'Más bajo' y, a continuación, una columna de diferencia por proveedor
    wp.write(R_GRP, cm, '', E.cab())
    wp.write(R_CAB, cm, 'Más bajo', E.cab())
    if n:
        txt = 'Diferencia con el Cliente (Cliente − oferta)'
        if n > 1:
            wp.merge_range(R_GRP, cd, R_GRP, cd + n - 1, txt, E(bold=True, font_color='#FFFFFF', bg_color='#667085', align='center'))
        else:
            wp.write(R_GRP, cd, txt, E(bold=True, font_color='#FFFFFF', bg_color='#667085', align='center', text_wrap=True))
    for k in range(n):
        wp.write(R_CAB, cd + k, 'Dif. %s' % nombres[k], E.cab())
    sumas = [0.0] * (1 + n)
    sumas_dif = [0.0] * n
    f_txt, f_eur = E.celda(), E.celda(num_format=S.EUR)
    for j, f in enumerate(filas):
        r = first + j
        h, pt = f['hoja'], f['hoja'].partida
        wp.write(r, 0, S.corto(h.ruta, 45), f_txt)
        wp.write(r, 1, h.n, E.celda(num_format='0', align='center'))
        wp.write(r, 2, pt.codigo, f_txt)
        wp.write(r, 3, S.corto(pt.descripcion, 110), E.celda(text_wrap=False))
        wp.write(r, 4, pt.cantidad, E.celda(num_format=S.NUM))
        wp.write(r, 5, pt.precio, f_eur)
        wp.write_formula(r, 6, '=ROUND(%s*ROUND(%s,2),2)' % (celda(r, 4), celda(r, 5)), f_eur, round(pt.importe, 2))
        sumas[0] += pt.importe
        importes, refs = [], []
        for k, of in enumerate(f['of']):
            c0 = 7 + 2 * k
            i = _imp(pt, of)
            importes.append(i)
            if of is None or of.precio is None:
                wp.write_blank(r, c0, None, f_eur)
                wp.write_blank(r, c0 + 1, None, f_eur)
            elif i is None:
                wp.write(r, c0, of.precio, f_eur)
                wp.write_blank(r, c0 + 1, None, f_eur)
            else:
                wp.write(r, c0, of.precio, f_eur)
                wp.write_formula(r, c0 + 1, '=ROUND(%s*ROUND(%s,2),2)' % (celda(r, 4), celda(r, c0)), f_eur, i)
                refs.append(celda(r, c0 + 1))
                sumas[1 + k] += i
        validos = [(i, k) for k, i in enumerate(importes) if i is not None]
        mini = min([(round(pt.importe, 2), -1)] + validos)
        wp.write(r, cm, ('Cliente' if mini[1] < 0 else nombres[mini[1]]) if validos else '', E.celda(align='center'))
        f_dif = E.celda(num_format=S.DEUR)
        for k, i in enumerate(importes):               # Cliente − oferta: positivo = la oferta es más barata que el Cliente
            if i is None:
                wp.write_blank(r, cd + k, None, f_dif)
            else:
                d = round(round(pt.importe, 2) - i, 2)
                sumas_dif[k] += d
                wp.write_formula(r, cd + k, '=IF(ISNUMBER(%s),%s-%s,"")' % (celda(r, 8 + 2 * k), celda(r, 6), celda(r, 8 + 2 * k)),
                                 f_dif, d)
    # fila de totales (SUBTOTAL: respeta los filtros)
    wp.set_row(R_TOT, 22)
    tf = E(bold=True, bg_color=S.CLARO, num_format=S.EUR, top=2, bottom=2, top_color=S.AZUL, bottom_color=S.AZUL)
    wp.write(R_TOT, 0, 'TOTAL filas visibles', E(bold=True, bg_color=S.CLARO, top=2, bottom=2, top_color=S.AZUL, bottom_color=S.AZUL))
    for c in range(1, NP):
        wp.write(R_TOT, c, '', tf)
    if filas:
        rng = lambda c: '%s:%s' % (celda(first, c), celda(last, c))   # noqa: E731
        wp.write_formula(R_TOT, 6, '=SUBTOTAL(109,%s)' % rng(6), tf, round(sumas[0], 2))
        for k in range(n):
            wp.write_formula(R_TOT, 8 + 2 * k, '=SUBTOTAL(109,%s)' % rng(8 + 2 * k), tf, round(sumas[1 + k], 2))
        tfd = E(bold=True, bg_color=S.CLARO, num_format=S.DEUR, top=2, bottom=2, top_color=S.AZUL, bottom_color=S.AZUL)
        for k in range(n):
            wp.write_formula(R_TOT, cd + k, '=SUBTOTAL(109,%s)' % rng(cd + k), tfd, round(sumas_dif[k], 2))
        if n:
            wp.conditional_format(first, cd, last, cd + n - 1, {'type': 'cell', 'criteria': '>', 'value': 0,
                                                                'format': E(bg_color=S.VERDE_BG, font_color=S.VERDE_TX)})
            wp.conditional_format(first, cd, last, cd + n - 1, {'type': 'cell', 'criteria': '<', 'value': 0,
                                                                'format': E(bg_color=S.ROJO_BG, font_color=S.ROJO_TX)})
        # formato condicional: más bajo de la fila (verde) y sin precio (ámbar)
        if n > 0:
            imps = ','.join(celda(first, c, False, True) for c in [6] + [8 + 2 * x for x in range(n)])
            for c0, ci in [(5, 6)] + [(7 + 2 * k, 8 + 2 * k) for k in range(n)]:
                wp.conditional_format(first, c0, last, c0 + 1, {
                    'type': 'formula', 'criteria': '=AND(ISNUMBER(%s),COUNT(%s)>1,%s=MIN(%s))' % (
                        celda(first, ci, False, True), imps, celda(first, ci, False, True), imps),
                    'format': E(bg_color=S.VERDE_BG, font_color=S.VERDE_TX)})
        for k in range(n):
            c0 = 7 + 2 * k
            wp.conditional_format(first, c0, last, c0 + 1, {
                'type': 'formula', 'criteria': '=NOT(ISNUMBER(%s))' % celda(first, c0 + 1, False, True),
                'format': E(bg_color=S.AMBAR_BG)})
        wp.autofilter(R_CAB, 0, last, NP - 1)
    wp.freeze_panes(first, 4)
    S.imprimir(wp, repetir=(R_GRP, R_CAB))

    wb.close()
    return {'proveedores': nombres, 'totales': totales}
