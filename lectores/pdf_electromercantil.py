"""Oferta de proveedor en PDF con la maqueta de Electromercantil (columnas: PROVEEDOR REFERENCIA DESCRIPCIÓN CANTIDAD
NETO VENTA UD TOTAL VENTA). Probado con una oferta real.

Se lee por POSICIÓN de cada palabra en la página (no por texto plano): en este PDF algunos precios salen con el
dígito partido en el texto ("7 70,80" es 770,80) y las descripciones ocupan 2-3 líneas alrededor de la línea de números.

Precio: el PDF imprime el precio unitario redondeado y el total de línea con más decimales; se usa total/cantidad
(lo que realmente cobra el proveedor) para que las sumas cuadren con los totales impresos.
"""
import collections
import datetime
import re

import pdfplumber

from ..modelo import Capitulo, Documento, Partida

# Bandas de columna (puntos PDF, medidas sobre la oferta real)
X_BRAND = (105, 140)
X_REF = (140, 217)
X_DESC = (217, 392)
X_CANT = (392, 432)
X_PRECIO = (432, 484)
X_TOTAL = (484, 570)
VENTANA = 9          # distancia vertical máxima entre una palabra y la línea de números de su fila


def n(s):
    return float(s.replace('.', '').replace(',', '.'))


def reconoce(ruta):
    try:
        with pdfplumber.open(ruta) as pdf:
            t = reparar_mojibake(pdf.pages[0].extract_text() or '').upper()
    except Exception:
        return False
    return 'CLIENTE:' in t and 'NETO VENTA' in t and 'REFERENCIA' in t and 'CANTIDAD' in t


def _en(w, banda):
    return banda[0] <= w['x0'] < banda[1]


def _lineas(palabras, tol=3.5):
    """Agrupa palabras en líneas visuales por su coordenada vertical."""
    out = []
    for w in sorted(palabras, key=lambda w: (w['top'], w['x0'])):
        if out and abs(out[-1][0] - w['top']) <= tol:
            out[-1][1].append(w)
        else:
            out.append([w['top'], [w]])
    return [(t, sorted(ws, key=lambda w: w['x0'])) for t, ws in out]


def _unir(palabras):
    return ''.join(w['text'] for w in sorted(palabras, key=lambda w: w['x0']))


def _marca(paginas):
    """El nombre de la marca/proveedor de columna 1 (el que se repite en cada línea, p. ej. ERCO)."""
    c = collections.Counter(w['text'] for pal in paginas for w in pal if _en(w, X_BRAND))
    return c.most_common(1)[0][0] if c else None


def _filas_de_pagina(palabras, marca, es_primera, es_ultima):
    """Devuelve eventos en orden vertical: ('capitulo', texto) o ('fila', dict)."""
    y0 = 0.0
    if es_primera:
        m = [w['top'] for w in palabras if w['text'] == 'Medición']
        y0 = (m[0] + 4) if m else 0.0
    y1 = 1e9
    if es_ultima:
        t = [w['top'] for w in palabras if w['text'] == 'TOTAL' and w['x0'] > 470]
        y1 = (t[0] - 2) if t else 1e9
    pal = [w for w in palabras if y0 <= w['top'] < y1]
    anclas = sorted((w for w in pal if w['text'] == marca and _en(w, X_BRAND)), key=lambda w: w['top'])
    cerca = lambda w: any(abs(w['top'] - a['top']) <= VENTANA for a in anclas)
    eventos = []
    # capítulos: líneas a la izquierda que no pertenecen a ninguna fila
    sueltas = [w for w in pal if w['x0'] < X_REF[1] and w['text'] != marca and not cerca(w)]
    for top, ws in _lineas(sueltas):
        eventos.append((top, 'capitulo', ' '.join(w['text'] for w in ws).strip()))
    for a in anclas:
        propias = [w for w in pal if abs(w['top'] - a['top']) <= VENTANA]
        desc = [w for w in pal if _en(w, X_DESC) and min(anclas, key=lambda b: abs(b['top'] - w['top'])) is a]
        lineas_desc = [' '.join(w['text'] for w in ws) for _, ws in _lineas(desc)]
        extra_precio = [w for w in propias if w['x0'] >= X_PRECIO[0]]
        eventos.append((a['top'], 'fila', {
            'ref': _unir([w for w in propias if _en(w, X_REF) and abs(w['top'] - a['top']) <= 4]),
            'desc': ' '.join(lineas_desc).strip(),
            'cant': _unir([w for w in propias if _en(w, X_CANT) and abs(w['top'] - a['top']) <= 4]),
            'precio_txt': _unir([w for w in extra_precio if _en(w, X_PRECIO)]),
            'total_txt': _unir([w for w in extra_precio if _en(w, X_TOTAL)]),
            'texto_derecha': ' '.join(w['text'] for w in sorted(extra_precio, key=lambda w: (round(w['top']), w['x0'])))}))
    eventos.sort(key=lambda e: e[0])
    return [(k, v) for _, k, v in eventos]


def _importe(txt):
    txt = txt.replace('€', '')
    return n(txt) if re.fullmatch(r'\d{1,3}(?:\.\d{3})*,\d{2}', txt) else None


def leer(ruta):
    doc = Documento(tipo='oferta_proveedor', origen=str(ruta))
    with pdfplumber.open(ruta) as pdf:
        paginas = [p.extract_words(x_tolerance=1.5) for p in pdf.pages]
        textos = [reparar_mojibake(p.extract_text() or '') for p in pdf.pages]
    todo = '\n'.join(textos)
    web = re.search(r'www\.([a-z0-9\-]+)\.', todo, re.I)
    doc.proveedor = web.group(1).capitalize() if web else 'Proveedor'
    marca = _marca(paginas)
    if not marca:
        raise ValueError('No se encuentra la columna de proveedor/marca en el PDF.')
    m = re.search(r'FECHA:\s*(\d{2}/\d{2}/\d{4})', todo)
    doc.fecha = m.group(1) if m else None
    m = re.search(r'PROYECTO:\s*(.+)', todo)
    doc.nombre = ('Oferta %s - %s' % (doc.proveedor, m.group(1).strip())) if m else 'Oferta %s' % doc.proveedor

    caps, cap, ultima, compuesto = [], None, None, False
    for i, pal in enumerate(paginas):
        for tipo, v in _filas_de_pagina(pal, marca, i == 0, i == len(paginas) - 1):
            if tipo == 'capitulo':
                cap = Capitulo(titulo=v)
                caps.append(cap)
                compuesto = False
                continue
            if cap is None:
                cap = Capitulo(titulo='SIN CAPÍTULO')
                caps.append(cap)
            total = _importe(v['total_txt'])
            cant = n(v['cant']) if re.fullmatch(r'\d{1,3}(?:\.\d{3})*(?:,\d+)?', v['cant']) else None
            ofertado_en_otra = bool(re.search(r'[A-Za-z]{3,}', v['texto_derecha']))     # "OFERTADO EN EL SISTEMA DE CONTROL"
            if total is None and compuesto and ultima is not None and not ofertado_en_otra:
                # componente (sin precio) de una partida a precio global: se añade a su descripción
                ultima.descripcion += ' | %s%s' % (v['desc'], (' (x%s)' % v['cant']) if v['cant'] else '')
                continue
            if cant is None:
                ultima.descripcion += ' ' + v['desc'] if ultima else ''
                continue
            p = Partida(descripcion=v['desc'], cantidad=cant, precio=None, referencia=v['ref'] or None)
            if total is not None and cant:
                p.importe_declarado = total
                p.precio = round(total / cant, 4)
                imp = _importe(v['precio_txt'])
                if imp is not None:
                    p.notas.append('Precio unitario impreso %.2f; total impreso calculado con más decimales.' % imp)
                elif v['precio_txt']:
                    p.notas.append('Precio unitario impreso %s' % v['precio_txt'])
            elif ofertado_en_otra:
                p.notas.append(v['texto_derecha'].strip().capitalize())
            cap.hijos.append(p)
            ultima = p
            compuesto = 'COMPUESTO POR' in v['desc'].upper() and total is not None

    doc.capitulos = [c for c in caps if c.hijos]
    # --- condiciones y total
    m = re.search(r'correspondiente\s+(\d{1,3}(?:\.\d{3})*,\d{2})\s*€', todo)
    doc.total_declarado = n(m.group(1)) if m else None
    cond = doc.condiciones
    if re.search(r'IVA NO INCLUIDO', todo, re.I):
        cond['iva'] = 'no incluido'
        doc.avisar('aviso', 'IVA no incluido en los precios.')
    if re.search(r'ECORAEE NO INCLUIDO', todo, re.I):
        cond['ecoraee'] = 'no incluido'
        doc.avisar('aviso', 'Tasa ECORAEE no incluida.')
    if re.search(r'PORTES DE ENV[IÍ]O NO INCLUIDOS', todo, re.I):
        cond['portes'] = 'pueden conllevar portes no incluidos'
        doc.avisar('aviso', 'La oferta puede conllevar portes de envío no incluidos en el precio.')
    g = re.search(r'Garant[ií]a:\s*(.+?)(?:\n|IVA)', todo)
    if g:
        cond['garantia'] = g.group(1).strip()
    if re.search(r'EFECTIVOS PARA EL TOTAL DE LAS PARTIDAS', todo, re.I):
        cond['netos_condicionados'] = True
        doc.avisar('revisar', 'Los netos son efectivos SOLO para el total de las partidas y quedan anulados si se suprime '
                              'alguna: no se pueden cotizar a mano las líneas sueltas más baratas.')
    doc.avisar('revisar', 'La oferta no indica plazo de entrega.')
    v = re.search(r'Validez de la oferta:\s*UN MES', todo, re.I)
    if v and doc.fecha:
        d = datetime.datetime.strptime(doc.fecha, '%d/%m/%Y').date()
        mes = d.month % 12 + 1
        anyo = d.year + (1 if d.month == 12 else 0)
        try:
            fin = d.replace(year=anyo, month=mes)
        except ValueError:
            fin = d.replace(year=anyo, month=mes, day=28)
        doc.validez = fin.strftime('%d/%m/%Y')
        cond['validez'] = 'un mes desde %s (hasta %s)' % (doc.fecha, doc.validez)
    doc.validar()
    return doc
