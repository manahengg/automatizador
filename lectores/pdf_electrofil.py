"""Oferta de proveedor en PDF con la maqueta de Electrofil (probado con una oferta real).

Otro proveedor tendrá otra maqueta: se añade un lector nuevo con el mismo esquema y se registra en detectar.py.
"""
import re
import pdfplumber
from ..modelo import Documento, Capitulo, Partida
from ..texto import reparar_mojibake

NUM = r'\d{1,3}(?:\.\d{3})*,\d+'
RE_PRECIO = re.compile(
    r'^(?P<desc>.*?)\s+(?P<cant>%s)\s+(?P<precio>\d{1,3}(?:\.\d{3})*,\d{4})'
    r'\s+(?P<dto>\d{1,3},\d{2})\s+(?P<parcial>%s)$' % (NUM, NUM))
RE_SOLO_CANT = re.compile(r'^(?P<desc>[A-ZÁÉÍÓÚÑ].*?)\s+(?P<cant>\d{1,3}(?:\.\d{3})*,\d{2})$')
RE_CABECERA = re.compile(r'^CODIGO\s+CONCEPTO\s+CANTIDAD')
RE_PIE = re.compile(r'^P[aá]gina\s+\d+/\d+$')


def n(s):
    return float(s.replace('.', '').replace(',', '.'))


def reconoce(ruta):
    try:
        with pdfplumber.open(ruta) as pdf:
            texto = reparar_mojibake(pdf.pages[0].extract_text() or '').upper()
    except Exception:
        return False
    return 'ELECTROFIL' in texto and 'CODIGO' in texto and 'CONCEPTO' in texto and 'CANTIDAD' in texto


def _buscar(texto, patron):
    m = re.search(patron, texto)
    return m.group(1).strip() if m else None


def leer(ruta):
    doc = Documento(tipo='oferta_proveedor', origen=str(ruta), proveedor='Electrofil')
    capitulos, claves = [], {}
    grupo = seccion = ''
    textos, ultima = [], None
    with pdfplumber.open(ruta) as pdf:
        for pag in pdf.pages:
            texto = reparar_mojibake(pag.extract_text() or '')
            textos.append(texto)
            dentro = False
            for linea in texto.split('\n'):
                linea = linea.strip()
                if RE_CABECERA.match(linea):
                    dentro = True
                    continue
                if not dentro or not linea:
                    continue
                if linea.startswith('Importes') or RE_PIE.match(linea):
                    break
                m = RE_PRECIO.match(linea)
                solo = None if m else RE_SOLO_CANT.match(linea)
                if linea.startswith('***') and not m:
                    grupo = linea.strip('* ').strip()
                    continue
                if linea.startswith('*') and not m:
                    seccion = linea.strip('* ').rstrip(':').strip()
                    continue
                if m or solo:
                    clave = (grupo, seccion)
                    if clave not in claves:
                        cap = Capitulo(titulo=('%s - %s' % clave).strip(' -'))
                        capitulos.append(cap)
                        claves[clave] = cap
                    if m:
                        lista, dto = n(m['precio']), n(m['dto'])
                        ultima = Partida(descripcion=m['desc'].lstrip('* ').strip(), cantidad=n(m['cant']),
                                         precio=lista * (1 - dto / 100), precio_lista=lista, dto_pct=dto,
                                         importe_declarado=n(m['parcial']))
                    else:
                        ultima = Partida(descripcion=solo['desc'].strip(), cantidad=n(solo['cant']), precio=None,
                                         notas=['Sin precio en la oferta'])
                    claves[clave].hijos.append(ultima)
                    continue
                if ultima is not None:          # segunda línea de la descripción anterior
                    ultima.descripcion += ' ' + linea
    todo = '\n'.join(textos)
    doc.capitulos = capitulos
    doc.referencia = _buscar(todo, r'Nº PRESUP:\s*(\S+)')
    doc.fecha = _buscar(todo, r'FECHA:\s*(\d\d/\d\d/\d{4})')
    doc.validez = _buscar(todo, r'VALIDEZ OFERTA:\s*(\d\d/\d\d/\d{4})')
    sub = _buscar(todo, r'SUBTOTAL EURO:\s*(%s)' % NUM)
    doc.total_declarado = n(sub) if sub else None
    doc.condiciones = {
        'forma_pago': _buscar(todo, r'FORMA DE PAGO:\s*([^\n]*)'),
        'portes': _buscar(todo, r'PORTES:\s*([^\n]*)'),
        'plazo_entrega': _buscar(todo, r'PLAZO ENTREGA:[ \t]*([^\n]*)'),
        'iva_declarado': _buscar(todo, r'IVA:\s*(%s)' % NUM),
        'total_declarado_con_iva': _buscar(todo, r'\bTOTAL:\s*(%s)' % NUM),
    }
    if not doc.condiciones['plazo_entrega']:
        doc.avisar('revisar', 'La oferta no indica plazo de entrega.')
    if doc.condiciones['portes'] and 'CONVENIR' in doc.condiciones['portes'].upper():
        doc.avisar('aviso', 'Portes "a convenir": no están incluidos en el precio.')
    if re.search(r'confirmad', todo, re.I):
        doc.avisar('aviso', 'El proveedor indica que los precios se confirman al recibir el pedido en firme.')
    if re.search(r'RAEE', todo):
        doc.avisar('aviso', 'La oferta menciona tasa RAEE aparte.')
    doc.validar()
    return doc
