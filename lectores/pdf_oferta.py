"""Oferta de proveedor en PDF, de CUALQUIER proveedor, leída por columnas.

Cómo funciona (sin plantillas por proveedor):
  1. Se obtienen las palabras de cada página con su posición (texto del PDF o OCR si es un escaneo).
  2. Se busca la fila de cabecera de la tabla (CÓDIGO / DESCRIPCIÓN / CANTIDAD / PRECIO / DTO / IMPORTE y sinónimos)
     y se toma la posición horizontal de cada columna. Las páginas sin cabecera reutilizan la última vista.
  3. Cada línea con números bajo las columnas numéricas es una LÍNEA DE OFERTA ("ancla"). Las líneas de solo texto
     son continuación de la descripción (de la línea anterior o, si están pegadas encima, de la siguiente),
     o títulos de sección (*** CABLEADO ***, PLANTA SÓTANO...).
  4. Los números se asignan a cantidad/precio/dto/importe por posición y se comprueba que
     cantidad x precio x (1 - dto) = importe; si no cuadra se prueban otras asignaciones.

Probado con Electrofil, Electromercantil (números con caracteres pegados) y Sonepar (escaneado -> OCR).
"""
import itertools
import os
import re

from .. import pdfpalabras as P
from ..modelo import Documento, Capitulo, Partida
from ..texto import normalizar_busqueda

COLUMNAS = {
    'item': {'ITEM', 'POS', 'POS.', 'LIN', 'LIN.', 'Nº', 'LINEA'},
    'codigo': {'CODIGO', 'CÓDIGO', 'COD', 'COD.', 'REFERENCIA', 'REF', 'REF.', 'ARTICULO', 'ARTÍCULO'},
    'marca': {'PROVEEDOR', 'MARCA', 'FABRICANTE'},
    'descripcion': {'CONCEPTO', 'DESCRIPCION', 'DESCRIPCIÓN', 'DENOMINACION', 'DENOMINACIÓN', 'DESIGNACION',
                    'DESIGNACIÓN', 'PRODUCTO', 'ARTICULO/DESCRIPCION'},
    'cantidad': {'CANTIDAD', 'CANT', 'CANT.', 'UDS', 'UDS.', 'UNIDADES', 'UNID.'},
    'precio': {'PRECIO', 'NETO', 'PVP', 'P.UNIT', 'P.UNIT.', 'TARIFA', 'P/U', 'PRECIO/UD'},
    'dto': {'DTO', 'DTO.', '%DTO', '%DTO.', '%', 'DESC.', 'DESCUENTO', '%DESC'},
    'importe': {'IMPORTE', 'PARCIAL', 'TOTAL', 'SUBTOTAL', 'NETO TOTAL'},
}
NUMERICAS = ('cantidad', 'precio', 'dto', 'importe')
FIN_TABLA = re.compile(r'^(P[aá]gina\s+\d+\s*/\s*\d+|P[aá]g\.?:?\s*\d|Suma y sigue|SUBTOTAL\b|Importes\b|TOTAL VENTA|'
                       r'Vendedor\s*:|Fecha Validez|Base imponible|TOTAL BRUTO|TOTAL NETO|Precios:)', re.I)
PROVEEDORES_CONOCIDOS = ('ELECTROMERCANTIL', 'ELECTROFIL', 'SONEPAR', 'REXEL', 'SALTOKI', 'FEGIME', 'GRUPO ELEKTRA',
                         'ELECTRO STOCKS', 'DIELECTRO', 'COMERCIAL ELECTRICA', 'ELECTRICIDAD MARTOS', 'YESTE')
MARCAS = ('ERCO', 'PHILIPS', 'SCHNEIDER', 'SIMON', 'LEGRAND', 'ABB', 'HAGER', 'IGUZZINI', 'TROX', 'LAMP', 'ORBIS')


def reconoce(ruta):
    return str(ruta).lower().endswith('.pdf')


def _clave_col(texto):
    t = texto.upper().strip(':')
    for k, sin in COLUMNAS.items():
        if t in sin:
            return k
    return None


def _cabecera(linea):
    """Si la línea es la cabecera de la tabla devuelve {columna: (x0, x1)}; si no, None."""
    cols, ultima = {}, None
    for w in linea['palabras']:
        k = _clave_col(w['text'])
        if k and k not in cols:
            cols[k] = [w['x0'], w['x1']]
            ultima = k
        elif ultima and (k == ultima or (k is None and w['x0'] - cols[ultima][1] < 12)):
            cols[ultima][1] = w['x1']          # 'NETO VENTA UD', '% DTO', 'TOTAL VENTA' -> una sola columna
        else:
            ultima = None
    tiene_num = sum(k in cols for k in NUMERICAS)
    if 'descripcion' in cols and tiene_num >= 2 and len(cols) >= 3:
        return {k: tuple(v) for k, v in cols.items()}
    return None


def _distancia(w, col):
    cx, ccx = (w['x0'] + w['x1']) / 2, (col[0] + col[1]) / 2
    return min(abs(cx - ccx), abs(w['x1'] - col[1]), abs(w['x0'] - col[0]))


def _asignar_numeros(nums, cols):
    """nums: palabras numéricas de la zona derecha (orden x). Devuelve {columna: valor} coherente."""
    disponibles = [k for k in NUMERICAS if k in cols]
    valores = [P.numero(w['text']) for w in nums]
    # 1) por posición
    por_pos, usadas = {}, set()
    for w, v in sorted(zip(nums, valores), key=lambda t: min(_distancia(t[0], cols[k]) for k in disponibles)):
        orden = sorted((k for k in disponibles if k not in usadas), key=lambda k: _distancia(w, cols[k]))
        if orden:
            por_pos[orden[0]] = v
            usadas.add(orden[0])
    if _cuadra(por_pos) is not False:
        return por_pos
    # 2) cualquier asignación ordenada (de izquierda a derecha) que cuadre
    for combo in itertools.combinations(disponibles, len(valores)):
        prueba = dict(zip(combo, valores))
        if _cuadra(prueba):
            return prueba
    return por_pos


def _cuadra(d):
    """True si cantidad*precio*(1-dto) ≈ importe; None si faltan datos para comprobarlo; False si no cuadra."""
    c, p, i = d.get('cantidad'), d.get('precio'), d.get('importe')
    if None in (c, p, i):
        return None
    dto = d.get('dto') or 0
    calc = c * p * (1 - dto / 100)
    return abs(calc - i) <= max(0.06, abs(i) * 0.004)


def _quitar_item(w, cols):
    """El OCR a veces pega el nº de ítem al código ('320GENC1690116NGP'): se quitan los caracteres que caen en la
    columna de ítem."""
    t = w['text']
    if 'item' in cols and 'codigo' in cols and w['x0'] < cols['item'][0] + 6 and len(t) > 4:
        ancho = (w['x1'] - w['x0']) / len(t)
        est = (cols['item'][1] - 3 - w['x0']) / ancho if ancho else 0
        validos = [n for n in (1, 2, 3) if t[:n].isdigit() and abs(n - est) <= 1.2]
        if validos:
            n = min(validos, key=lambda n: abs(n - est))
            return t[n:]
    return t


def _es_codigo(t):
    return bool(re.search(r'\d', t)) and len(t) >= 3 or bool(re.fullmatch(r'[A-Z0-9.\-_/+]{6,}', t))


def leer(ruta, progreso=None):
    pags = P.paginas(ruta, progreso)
    proveedor = _adivinar_proveedor(ruta, pags)
    doc = Documento(tipo='oferta_proveedor', origen=str(ruta), proveedor=proveedor)
    if any(p['ocr'] for p in pags):
        doc.avisar('aviso', 'PDF escaneado: leído con OCR. Revisa especialmente códigos y cantidades.')
    cols = None
    filas = []        # cada fila: dict(anclas, seccion)
    texto_total = []
    seccion = 'GENERAL'
    for npag, pag in enumerate(pags):
        lins = P.lineas(pag['palabras'])
        texto_total.extend(l['texto'] for l in lins)
        # una página con cabecera propia empieza a leer tras ella (se salta el membrete repetido);
        # una página sin cabecera continúa la tabla de la anterior desde arriba
        dentro = cols is not None and not any(_cabecera(l) for l in lins)
        anclas_pag, sueltas = [], []
        for l in lins:
            cab = _cabecera(l)
            if cab:
                cols, dentro = cab, True
                continue
            if not dentro:
                continue
            if FIN_TABLA.match(l['texto']):
                dentro = False
                continue
            info = _clasificar(l, cols)
            if info['tipo'] == 'seccion':
                seccion = info['texto']
                sueltas.append(('seccion', l, info))
            elif info['tipo'] == 'ancla':
                info['seccion'] = seccion
                if pag['ocr'] and not info['desc']:
                    _rescatar_desc(ruta, npag, l, info, cols)
                anclas_pag.append((l, info))
                sueltas.append(('ancla', l, info))
            else:
                sueltas.append(('texto', l, info))
        _repartir_continuaciones(sueltas)
        filas.extend(info for _, info in anclas_pag)

    caps = {}
    previa = None
    for f in filas:
        cap = caps.get(f['seccion'])
        if cap is None:
            cap = caps[f['seccion']] = Capitulo(titulo=f['seccion'])
        d = f['num']
        desc = _limpiar_desc(' '.join(f['desc']))
        notas = []
        opcional = bool(re.search(r'\bOPCIONAL\b', desc, re.I))
        if opcional:
            notas.append('OPCIONAL')
        cant = d.get('cantidad')
        precio_lista = d.get('precio')
        dto = d.get('dto')
        importe = d.get('importe')
        if precio_lista is None and importe is not None and cant:
            precio_lista = importe / cant
        neto = None
        if precio_lista is not None:
            neto = precio_lista * (1 - (dto or 0) / 100)
            if importe is not None and cant:
                if _cuadra(d) is False and abs(importe / cant - neto) > max(0.01, neto * 0.01):
                    notas.append('precio neto deducido del importe impreso (no cuadra con precio y dto)')
                neto = importe / cant           # el importe impreso da el precio real con todos sus decimales
        if cant is None and importe and neto:
            cant = round(importe / neto, 3)        # la cantidad no se leyó pero precio e importe sí
            notas.append('cantidad deducida de importe/precio')
        if cant is None:
            notas.append('sin cantidad en la oferta (solo precio)' if neto is not None else 'sin cantidad')
            cant = 0.0
        if neto is None:
            notas.append('sin precio en la oferta')
        es_canon = bool(re.search(r'CANON|ECORAEE|RAEE|Ges\. Log', desc, re.I)) and not f['codigo']
        if es_canon:
            notas.append('CANON/TASA de la línea anterior')
        p = Partida(descripcion=desc, cantidad=cant, precio=neto, unidad='ud', referencia=f['codigo'],
                    precio_lista=precio_lista, dto_pct=dto, importe_declarado=importe, notas=notas)
        p.marca = f.get('marca')
        p.opcional = opcional
        p.canon_de = previa if es_canon else None
        cap.hijos.append(p)
        if not es_canon:
            previa = p
    doc.capitulos = [c for c in caps.values() if c.hijos]
    if not doc.capitulos:
        raise ValueError('No he encontrado la tabla de la oferta (cabecera con DESCRIPCIÓN, CANTIDAD, PRECIO/IMPORTE).')
    _datos_generales(doc, '\n'.join(texto_total))
    doc.validar()
    return doc


def _clasificar(l, cols):
    ps = l['palabras']
    num_cols = [cols[k] for k in NUMERICAS if k in cols]
    borde = min(c[0] for c in num_cols) - 4
    desc_x0 = cols['descripcion'][0]
    cod_col = cols.get('codigo')
    if cod_col:
        desc_ini = min(desc_x0, cod_col[1] + 6)
    else:
        desc_ini = desc_x0 - 15
    nums = [w for w in ps if w['x1'] > borde and P.es_numero(w['text'])]
    izq = [w for w in ps if not (w['x1'] > borde and (P.es_numero(w['text']) or w['text'] in ('€', 'NETO', '%')))]
    texto = ' '.join(w['text'] for w in izq).strip()
    numeros = _asignar_numeros(nums, cols) if nums else {}
    if texto.startswith('*'):
        limpio = texto.strip('* :').strip()
        if numeros.get('precio') is None and numeros.get('importe') is None:
            return {'tipo': 'seccion', 'texto': limpio or 'GENERAL'}
    tiene_num = any(numeros.get(k) is not None for k in NUMERICAS)
    if not tiene_num:
        # títulos de sección: texto en mayúsculas que empieza a la izquierda de la columna de descripción
        solo_marca = 'marca' in cols and len(izq) == 1 and _distancia(izq[0], cols['marca']) < 25
        if izq and texto.upper() == texto and not re.search(r'\d', izq[0]['text']) and len(texto) < 60 and not solo_marca \
                and re.search(r'[A-ZÁÉÍÓÚÑ]{3}', texto) and (izq[-1]['x1'] < desc_ini or
                                                         re.match(r'(PLANTA|CAP[IÍ]TULO|ZONA|EDIFICIO|NAVE)\b', texto)):
            return {'tipo': 'seccion', 'texto': texto.strip(': ')}
        return {'tipo': 'texto', 'desc': [texto] if texto else []}
    # línea de oferta
    codigo, marca, desc = None, None, []
    for i, w in enumerate(izq):
        t = w['text']
        if cols.get('item') and i == 0 and re.fullmatch(r'\d{1,4}', t) and w['x1'] < cols['item'][1] + 15:
            continue
        if marca is None and 'marca' in cols and _distancia(w, cols['marca']) < 25 and not desc and \
                (not cod_col or _distancia(w, cols['marca']) < _distancia(w, cod_col)):
            marca = t
            continue
        if codigo is None and not desc and w['x0'] < desc_ini + 2 and _es_codigo(t.upper()):
            codigo = _quitar_item(w, cols)
            continue
        if codigo is None and not desc and cod_col and w['x0'] < desc_ini - 2 and len(t) >= 3:
            codigo = t
            continue
        desc.append(t)
    if codigo is None and desc and _es_codigo(desc[0]) and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-_/]{4,}', desc[0]) \
            and re.search(r'\d', desc[0]) and len(desc) > 1:
        codigo = desc.pop(0)            # la descripción empieza por una referencia ('10340001020050C Sumsave…')
        if desc and desc[0] == '-':
            desc.pop(0)
    return {'tipo': 'ancla', 'num': numeros, 'codigo': codigo, 'marca': marca, 'desc': [' '.join(desc)] if desc else [],
            'top': l['top'], 'altura': l['altura']}


def _rescatar_desc(ruta, npag, l, info, cols):
    """El OCR de página completa a veces se salta un texto: se repite el OCR solo en la celda de descripción."""
    x0 = cols['descripcion'][0] - 10
    x1 = min(c[0] for k, c in cols.items() if k in NUMERICAS) - 2
    try:
        t = P.ocr_zona(ruta, npag, x0, l['top'] - 3, x1, l['bottom'] + 2)
    except Exception:
        return
    if t.strip():
        info['desc'] = [t.strip()]


def _repartir_continuaciones(sueltas):
    """Las líneas de texto se pegan a la línea de oferta anterior; si están pegadas encima de la siguiente
    (maquetas con descripción centrada verticalmente, p. ej. Electromercantil) se pegan a la siguiente."""
    for i, (tipo, l, info) in enumerate(sueltas):
        if tipo != 'texto' or not info['desc']:
            continue
        ant = next((sueltas[j] for j in range(i - 1, -1, -1) if sueltas[j][0] != 'texto'), None)
        sig = next((sueltas[j] for j in range(i + 1, len(sueltas)) if sueltas[j][0] != 'texto'), None)
        h = l['altura'] or 6
        destino = None
        if sig and sig[0] == 'ancla' and sig[1]['top'] - l['top'] < h * 0.75:
            destino = sig
        elif ant and ant[0] == 'ancla':
            destino = ant
        if destino:
            if destino is sig:
                destino[2]['desc'].insert(0, ' '.join(info['desc']))
            else:
                destino[2]['desc'].extend(info['desc'])


def _limpiar_desc(s):
    s = s.strip('* ').strip()
    s = re.sub(r'(\d),\s(\d)\b', r'\1,\2', s)          # 'LED 6, 1 w' -> 'LED 6,1 w'
    s = re.sub(r'^\(\*\)\s*', '', s)
    return re.sub(r'\s{2,}', ' ', s)


def proveedor_por_carpeta(ruta):
    """obras/<obra>/proveedores/<Proveedor>/oferta.pdf -> 'Proveedor'."""
    partes = os.path.normpath(os.path.abspath(ruta)).split(os.sep)
    if len(partes) >= 3 and partes[-3].lower() == 'proveedores':
        return partes[-2].strip().title()
    return None


def _adivinar_proveedor(ruta, pags):
    por_carpeta = proveedor_por_carpeta(ruta)
    if por_carpeta:
        return por_carpeta
    nombre = os.path.basename(ruta).upper()
    texto = ' '.join(w['text'] for p in pags for w in p['palabras']).upper().replace(' ', '')
    for lista in (PROVEEDORES_CONOCIDOS, MARCAS):       # primero distribuidores, después fabricantes
        for prov in lista:
            if prov in nombre or prov.replace(' ', '') in texto:
                return prov.title()
    return os.path.splitext(os.path.basename(ruta))[0][:30]


def _buscar(texto, patron, flags=re.I):
    m = re.search(patron, texto, flags)
    return m.group(1).strip() if m else None


def _datos_generales(doc, texto):
    doc.fecha = _buscar(texto, r'\bFECHA:\s*(\d\d/\d\d/\d{4})', 0) or \
        _buscar(re.sub(r'(?i)con fecha \S+', '', texto[:1500]), r'\b(\d\d/\d\d/\d{4})\b')
    doc.validez = _buscar(texto, r'VALIDEZ(?: OFERTA)?:?\s*(\d\d/\d\d/\d{4})') or _buscar(texto, r'Fecha Validez\s*:?\s*(\d\d/\d\d/\d{4})')
    doc.referencia = _buscar(texto, r'N[ºo°] ?PRESUP:?\s*(\S+)')
    num = r'((?:\d{1,3}(?:\.\d{3})+|\d+),\d{2})'
    for pat in (r'SUBTOTAL EURO:?\s*' + num, r'TOTAL VENTA[^\d]*' + num, r'Total Neto[^\d]*' + num,
                r'Base imponible[^\d]*' + num, r'IMP\.?\s*BRUTO:?\s*' + num, r'NETOS[^\n]*?' + num + r'\s*€'):
        v = _buscar(texto, pat)
        if v:
            doc.total_declarado = P.numero(v)
            tasas = _buscar(texto, r'SUBTOTAL TASAS:?\s*' + num)
            if tasas:                                   # Electrofil suma los cánones aparte
                doc.total_declarado = round(doc.total_declarado + P.numero(tasas), 2)
            break
    doc.condiciones = {'portes': _buscar(texto, r'PORTES:?\s*([^\n.]*)'),
                       'forma_pago': _buscar(texto, r'FORMA DE PAGO:?\s*([^\n.]*)')}
    if re.search(r'RAEE', texto) and re.search(r'NO INCLUIDO|incrementar', texto, re.I):
        doc.avisar('aviso', 'La oferta indica que la tasa RAEE no está incluida o se añadirá aparte.')
    if re.search(r'confirmad|sujetos a (las )?variaciones', texto, re.I):
        doc.avisar('aviso', 'Precios sujetos a confirmación/variación por el proveedor.')
    if re.search(r'QUEDANDO\s+ANULADOS SI SE SUPRIME', texto, re.I):
        doc.avisar('aviso', 'Los netos solo son válidos si se compra el total de las partidas.')


def clave_texto(p):
    return normalizar_busqueda(p.descripcion)
