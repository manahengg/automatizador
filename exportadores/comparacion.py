"""Libro Excel de revisión del emparejamiento oferta <-> licitación (editable por una persona)."""
import openpyxl
from xlsxwriter.utility import xl_rowcol_to_cell as celda

from . import estilo as S

COL_EDITABLE = 'Nº licitación (editable)'
HOJA = 'Emparejamiento'
CABECERA = ['Estado', 'Línea oferta', 'Capítulo oferta', 'Descripción oferta', 'Cant. oferta', 'Precio oferta',
            COL_EDITABLE, 'Código licitación', 'Capítulo licitación', 'Descripción licitación', 'Cant. licitación',
            'Precio licitación', 'Dif. precio %', 'Parecido', 'Margen', 'Alternativa 1 (nº)', 'Alternativa 1',
            'Alternativa 2 (nº)', 'Alternativa 2', 'Motivos'] + sum(([f'Candidata {i} (nº)', f'Candidata {i} · descripción y puntuación'] for i in range(3, 9)), [])
ANCHOS = [12, 8, 24, 46, 10, 12, 15, 16, 24, 46, 10, 12, 10, 9, 8, 10, 34, 10, 34, 60] + sum(([10, 48] for _ in range(3, 9)), [])
HDR = 3          # fila (0-based) de la cabecera en la hoja Emparejamiento


def escribir(parejas, licitacion_hojas, resumen, ruta, avisos=(), elegidas=None):
    """elegidas: {nº línea oferta: nº licitación} para rellenar la columna editable con las decisiones de una persona
    (si es None se rellena con la propuesta del programa). Una fila cuya elección difiere de la propuesta se marca
    'elegido a mano'."""
    wb, E = S.nuevo_libro(ruta)
    NL = len(licitacion_hojas)

    def eleccion(p):
        if elegidas is None:
            return p.lic.n if p.lic else None
        return elegidas.get(p.oferta.n)

    def estado(p):
        e = eleccion(p)
        if elegidas is not None and e != (p.lic.n if p.lic else None):
            return 'elegido a mano' if e is not None else 'sin incluir'
        return p.estado

    ests = [estado(p) for p in parejas]
    cuenta = lambda x: sum(1 for e in ests if e == x)   # noqa: E731

    # ============================================================ Resumen
    ws = wb.add_worksheet('Resumen')
    NC = 8
    S.banner(ws, E, 'Emparejamiento de la oferta con la licitación',
             '%s  ·  %d líneas de oferta frente a %d partidas de licitación' % (resumen['proveedor'], len(parejas), NL), NC)
    for i, w in enumerate([22, 14, 14, 14, 14, 14, 14, 14]):
        ws.set_column(i, i, w)
    S.tarjeta(ws, E, 3, 0, 'LÍNEAS DE LA OFERTA', len(parejas), '0', ancho=2)
    S.tarjeta(ws, E, 3, 2, 'SEGURAS', cuenta('seguro'), '0', ancho=2, color=S.VERDE, nota='parecido alto y sin rival')
    S.tarjeta(ws, E, 3, 4, 'A REVISAR', cuenta('revisar') + cuenta('elegido a mano'), '0', ancho=2, color=S.AMBAR,
              nota='mirar la fila amarilla')
    S.tarjeta(ws, E, 3, 6, 'SIN PAREJA / SIN INCLUIR', cuenta('sin pareja') + cuenta('sin incluir'), '0', ancho=2, color=S.ROJO,
              nota='la eliges tú')
    S.tarjeta(ws, E, 7, 0, 'IMPORTE CON PRECIOS DE LA LICITACIÓN', resumen['importe_licitacion'], S.EUR, ancho=2,
              nota='de las partidas incluidas')
    S.tarjeta(ws, E, 7, 2, 'IMPORTE CON PRECIOS DE %s' % resumen['proveedor'].upper(), resumen['importe_proveedor'], S.EUR, ancho=2,
              color=S.NAVY)
    S.tarjeta(ws, E, 7, 4, 'DIFERENCIA', resumen['diferencia'], S.DEUR, ancho=2,
              color=S.VERDE if resumen['diferencia'] <= 0 else S.ROJO, nota='menos de lo presupuestado = verde')
    pct = (resumen['diferencia_pct'] or 0) / 100.0
    S.tarjeta(ws, E, 7, 6, 'DIFERENCIA %', pct, S.DPCT, ancho=2, color=S.VERDE if pct <= 0 else S.ROJO)
    fila = 11
    S.seccion(ws, E, fila, 'Cómo revisar', NC)
    pasos = ['1.  Ve a la hoja "%s". Verde = fiable · amarillo = mirar · rojo = sin pareja (la eliges tú).' % HOJA,
             '2.  Si una pareja está mal, escribe en la columna amarilla "%s" el nº correcto (búscalo en la hoja "Licitación").' % COL_EDITABLE,
             '3.  Para quitar una línea del resultado, deja vacía esa celda.',
             '4.  Guarda el Excel y ejecuta:  python -m automatizador aplicar <esta carpeta>   (o corrígelo en la app).']
    for t in pasos:
        fila += 1
        S.caja(ws, E, fila, NC, t, 'info', 120)
    if avisos:
        fila += 2
        S.seccion(ws, E, fila, 'Avisos de la lectura de la oferta', NC, color=S.AMBAR_TX)
        for a in avisos:
            fila += 1
            S.caja(ws, E, fila, NC, '[%s] %s' % (a.nivel.upper(), a.texto), 'aviso', 120)
    S.imprimir(ws, horizontal=False)

    # ============================================================ Emparejamiento
    we = wb.add_worksheet(HOJA)
    S.banner(we, E, 'Emparejamiento línea a línea',
             'Edita SOLO la columna amarilla. Pasa el ratón por su cabecera para ver las instrucciones.', len(CABECERA))
    for i, w in enumerate(ANCHOS):
        we.set_column(i, i, w)
    we.set_row(HDR, 36)
    for c, t in enumerate(CABECERA):
        we.write(HDR, c, t, E.cab() if c != 6 else E(bold=True, bg_color='#FFD60A', font_color='#000000', text_wrap=True,
                                                    align='center', border=1, border_color=S.BORDE))
    we.write_comment(HDR, 6, 'Número de la partida de la licitación que corresponde a esta línea.\n'
                             'Búscalo en la hoja "Licitación". Vacío = esta línea NO entra en el resultado.',
                     {'x_scale': 2.2, 'y_scale': 1.4})
    f_txt = E.celda(valign='top')
    f_num = E.celda(num_format=S.NUM, valign='top')
    f_eur = E.celda(num_format=S.EUR, valign='top')
    f_edit = E.celda(bold=True, bg_color='#FFF3A3', align='center', num_format='0', valign='top', border=2, border_color='#E0B400')
    primera = HDR + 1
    for j, p in enumerate(parejas):
        r = primera + j
        o = p.oferta.partida
        l = p.lic.partida if p.lic else None
        alt = list(p.alternativas) + [(None, None)] * max(0, 8 - len(p.alternativas))
        we.set_row(r, 30)
        we.write(r, 0, ests[j], E.celda(bold=True, align='center', valign='top'))
        we.write(r, 1, p.oferta.n, E.celda(num_format='0', align='center', valign='top'))
        we.write(r, 2, S.corto(p.oferta.ruta, 60), E.celda(valign='top', text_wrap=True))
        we.write(r, 3, S.corto(o.descripcion, 160), E.celda(valign='top', text_wrap=True))
        we.write(r, 4, o.cantidad, f_num)
        we.write(r, 5, o.precio, f_eur)
        e = eleccion(p)
        if e is None:
            we.write_blank(r, 6, None, f_edit)
        else:
            we.write(r, 6, e, f_edit)
        we.write(r, 7, l.codigo if l else None, f_txt)
        we.write(r, 8, S.corto(p.lic.ruta, 60) if l else None, E.celda(valign='top', text_wrap=True))
        we.write(r, 9, S.corto(l.descripcion, 160) if l else None, E.celda(valign='top', text_wrap=True))
        we.write(r, 10, l.cantidad if l else None, f_num)
        we.write(r, 11, l.precio if l else None, f_eur)
        if l and l.precio and o.precio is not None:
            we.write_formula(r, 12, '=IF(%s=0,"",%s/%s-1)' % (celda(r, 11), celda(r, 5), celda(r, 11)),
                             E.celda(num_format=S.DPCT, valign='top'), o.precio / l.precio - 1)
        else:
            we.write_blank(r, 12, None, f_txt)
        we.write(r, 13, round(p.parecido, 2) if p.lic else None, E.celda(num_format='0.00', valign='top'))
        we.write(r, 14, round(p.margen, 2) if p.lic else None, E.celda(num_format='0.00', valign='top'))
        we.write(r, 15, alt[0][1].n if alt[0][1] else None, E.celda(num_format='0', valign='top', align='center'))
        we.write(r, 16, S.corto(alt[0][1].partida.descripcion, 90) if alt[0][1] else None, E.celda(valign='top', text_wrap=True))
        we.write(r, 17, alt[1][1].n if alt[1][1] else None, E.celda(num_format='0', valign='top', align='center'))
        we.write(r, 18, S.corto(alt[1][1].partida.descripcion, 90) if alt[1][1] else None, E.celda(valign='top', text_wrap=True))
        we.write(r, 19, ' '.join(p.motivos), E.celda(valign='top', text_wrap=True))
        for k, (score, candidato) in enumerate(alt[2:8], start=20):
            if candidato:
                we.write(r, k, candidato.n, E.celda(num_format='0', valign='top', align='center'))
                we.write(r, k + 1, '%.0f%% · %s · %s' % (score * 100, S.corto(candidato.ruta, 45),
                          S.corto(candidato.partida.descripcion, 120)), E.celda(valign='top', text_wrap=True))
            else:
                we.write_blank(r, k, None, f_txt)
                we.write_blank(r, k + 1, None, f_txt)
    ult = primera + len(parejas) - 1
    if parejas:
        a = celda(primera, 0, False, True)
        for texto, bg, tx in (('seguro', S.VERDE_BG, S.VERDE_TX), ('revisar', S.AMBAR_BG, S.AMBAR_TX),
                              ('sin pareja', S.ROJO_BG, S.ROJO_TX), ('elegido a mano', S.AZUL_BG, S.AZUL_TX),
                              ('sin incluir', S.ROJO_BG, S.ROJO_TX)):
            we.conditional_format(primera, 0, ult, 0, {'type': 'cell', 'criteria': '==', 'value': '"%s"' % texto,
                                                       'format': E(bg_color=bg, font_color=tx, bold=True)})
            we.conditional_format(primera, 1, ult, 5, {'type': 'formula', 'criteria': '=%s="%s"' % (a, texto),
                                                       'format': E(bg_color=bg)}) if texto in ('revisar', 'sin pareja', 'elegido a mano') else None
        we.conditional_format(primera, 13, ult, 13, {'type': 'data_bar', 'bar_color': '#63BE7B', 'min_type': 'num', 'min_value': 0,
                                                     'max_type': 'num', 'max_value': 2, 'bar_solid': True})
        # Desplegable por línea con la propuesta y hasta 8 candidatas mejor puntuadas.
        # Se permite escribir otro número manualmente si el usuario quiere buscar fuera de la lista.
        for j, p in enumerate(parejas):
            fila_excel = primera + j
            opciones = []
            if p.lic:
                opciones.append(str(p.lic.n))
            opciones.extend(str(h.n) for _, h in p.alternativas if h.n not in {int(x) for x in opciones})
            opciones = opciones[:9]
            if opciones:
                we.data_validation(fila_excel, 6, fila_excel, 6, {
                    'validate': 'list', 'source': opciones, 'ignore_blank': True,
                    'input_title': 'Candidatas licitación',
                    'input_message': 'Elige una candidata. Consulta capítulo, descripción y puntuación en las columnas de la derecha. Vacío = no incluir.',
                    'error_type': 'warning', 'error_title': 'Número fuera de las candidatas',
                    'error_message': 'Puedes escribir otro número de la hoja Licitación si lo has comprobado.'})
        we.autofilter(HDR, 0, ult, len(CABECERA) - 1)
    we.freeze_panes(primera, 4)
    S.imprimir(we, repetir=(HDR, HDR))

    # ============================================================ Licitación
    wl = wb.add_worksheet('Licitación')
    S.banner(wl, E, 'Partidas de la licitación', 'Busca aquí el número (Nº) que debes escribir en la columna amarilla. Verde = ya asignada.', 9)
    for i, w in enumerate([7, 40, 16, 74, 6, 11, 13, 15, 14]):
        wl.set_column(i, i, w)
    for c, t in enumerate(['Nº', 'Capítulo', 'Código', 'Descripción', 'Ud', 'Cantidad', 'Precio', 'Importe', 'Línea de oferta asignada']):
        wl.write(HDR, c, t, E.cab())
    wl.set_row(HDR, 34)
    usadas = {}
    for j, p in enumerate(parejas):
        e = eleccion(p)
        if e is not None:
            usadas[e] = p.oferta.n
    for j, h in enumerate(licitacion_hojas):
        r = primera + j
        pt = h.partida
        wl.write(r, 0, h.n, E.celda(num_format='0', align='center', bold=True))
        wl.write(r, 1, S.corto(h.ruta, 70), E.celda())
        wl.write(r, 2, pt.codigo, E.celda())
        wl.write(r, 3, S.corto(pt.descripcion, 200), E.celda())
        wl.write(r, 4, pt.unidad, E.celda(align='center'))
        wl.write(r, 5, pt.cantidad, E.celda(num_format=S.NUM))
        wl.write(r, 6, pt.precio, E.celda(num_format=S.EUR))
        wl.write_formula(r, 7, '=ROUND(%s*ROUND(%s,2),2)' % (celda(r, 5), celda(r, 6)), E.celda(num_format=S.EUR), round(pt.importe, 2))
        if h.n in usadas:
            wl.write(r, 8, usadas[h.n], E.celda(num_format='0', align='center'))
        else:
            wl.write_blank(r, 8, None, E.celda())
    if licitacion_hojas:
        u2 = primera + len(licitacion_hojas) - 1
        wl.conditional_format(primera, 0, u2, 8, {'type': 'formula', 'criteria': '=%s<>""' % celda(primera, 8, False, True),
                                                  'format': E(bg_color=S.VERDE_BG)})
        wl.autofilter(HDR, 0, u2, 8)
    wl.freeze_panes(primera, 1)
    S.imprimir(wl, repetir=(HDR, HDR))
    wb.close()


def leer_elecciones(ruta):
    """Lee la hoja editada. Devuelve {nº línea oferta: nº licitación} solo para las filas con nº escrito."""
    wb = openpyxl.load_workbook(ruta, data_only=True)
    wb.close()
    ws = wb[HOJA]
    filas = list(ws.iter_rows(min_row=1, values_only=True))
    ini = next((i for i, f in enumerate(filas[:15]) if 'Línea oferta' in f and COL_EDITABLE in f), None)
    if ini is None:
        raise ValueError('No encuentro la cabecera de la hoja "%s" (columnas "Línea oferta" y "%s").' % (HOJA, COL_EDITABLE))
    cab = list(filas[ini])
    ci, ce = cab.index('Línea oferta'), cab.index(COL_EDITABLE)
    out = {}
    for fila in filas[ini + 1:]:
        if fila[ci] is None:
            continue
        v = fila[ce]
        if v is None or str(v).strip() == '':
            continue
        try:
            out[int(fila[ci])] = int(float(str(v).replace(',', '.')))
        except ValueError:
            raise ValueError('Línea de oferta %s: "%s" no es un número de la hoja Licitación.' % (fila[ci], v))
    return out
