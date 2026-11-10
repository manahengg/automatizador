"""Presupuesto / mediciones del CLIENTE en PDF (formato Presto, Arquímedes, m4PRO, TCQ...: "PRESUPUESTO Y MEDICIONES").

Estructura que se reconoce (no depende de un programa concreto, sino de la maqueta típica):

    CAPÍTULO 14 ELECTRICIDAD                      <- capítulos / subcapítulos / apartados
    14.01.01.01 m DERIVACIÓN INDIVIDUAL ...       <- código, unidad y resumen de la partida
    Derivación individual constituida por ...     <- descripción larga (puede ocupar varias líneas)
    RZ1-K(AS) 1 25,00 27,50 a*b*1.1               <- líneas de medición (se ignoran)
    ______________________
    27,50 23,92 657,80                            <- CANTIDAD  PRECIO  IMPORTE  (o solo cantidad si no hay precios)

Las cabeceras y pies de página se saltan y una partida puede continuar en la página siguiente.
"""
import re

from .. import pdfpalabras as P
from ..modelo import Documento, Capitulo, Partida

UNIDADES = {'m', 'm.', 'ml', 'ml.', 'm2', 'm2.', 'm²', 'm3', 'm³', 'ud', 'ud.', 'u', 'u.', 'uds', 'p.a.', 'pa', 'p.a',
            'kg', 'h', 'h.', 'mes', 'l', 't', 'pp', 'pza', 'km', 'jgo', 'ud/m'}
RE_CAP = re.compile(r'^(CAP[IÍ]TULO|SUBCAP[IÍ]TULO|APARTADO|SUBAPARTADO)\s+(\S+)\s+(.*)$', re.I)
RE_COD = re.compile(r'^[A-Z0-9][A-Z0-9.\-_/]*\d[A-Z0-9.\-_/]*$', re.I)
RE_FORMULA = re.compile(r'^[a-z]\*|\*[a-z0-9.]+$|^\(?[a-z]\)?$', re.I)
RE_PIE = re.compile(r'^(P[aá]gina\s+\d+|\d{1,2} de [a-záéíóú]+ de \d{4}$)', re.I)


def reconoce(ruta):
    if not str(ruta).lower().endswith('.pdf'):
        return False
    try:
        pags = P.paginas(ruta)[:2]
    except Exception:
        return False
    t = ' '.join(w['text'] for p in pags for w in p['palabras']).upper()
    return ('MEDICION' in t or 'PRESUPUESTO' in t) and 'RESUMEN' in t and ('CÓDIGO' in t or 'CODIGO' in t)


def _es_subrayado(l):
    return l['texto'].replace(' ', '').strip('_') == '' and len(l['texto']) > 8


def leer(ruta, progreso=None):
    pags = P.paginas(ruta, progreso)
    lineas = []
    cols = None
    nombre = ''
    for pag in pags:
        lins = P.lineas(pag['palabras'])
        cab = None
        for i, l in enumerate(lins):
            up = [w['text'].upper() for w in l['palabras']]
            if 'RESUMEN' in up and ('CANTIDAD' in up or 'IMPORTE' in up):
                cab = i
                cols = {w['text'].upper(): (w['x0'], w['x1']) for w in l['palabras']}
                if not nombre and i >= 1:
                    nombre = lins[i - 1]['texto']
                break
        cuerpo = lins[cab + 1:] if cab is not None else lins
        if cuerpo and _es_subrayado(cuerpo[0]):
            cuerpo = cuerpo[1:]                                   # raya bajo la cabecera
        while cuerpo and (RE_PIE.match(cuerpo[-1]['texto']) or _es_subrayado(cuerpo[-1]) and len(cuerpo[-1]['texto']) > 80):
            cuerpo = cuerpo[:-1]                                   # pie de página
        lineas.extend(cuerpo)
    if cols is None:
        raise ValueError('No encuentro la cabecera CÓDIGO / RESUMEN / CANTIDAD del presupuesto.')
    x_uds = (cols.get('UDS') or cols.get('UDS.') or cols.get('N') or (cols['RESUMEN'][1] + 100, 0))[0] - 8
    x_cant = (cols.get('CANTIDAD') or (x_uds + 150, 0))[0] - 40
    x_resumen = cols['RESUMEN'][0]

    doc = Documento(tipo='presupuesto', origen=str(ruta), nombre=nombre)
    pila = []                 # [(nivel, Capitulo)]
    actual = None             # partida en curso: dict
    estado = None             # 'desc' | 'medicion' | 'total'

    def cap_actual():
        if not pila:
            c = Capitulo(titulo='SIN CAPÍTULO')
            doc.capitulos.append(c)
            pila.append((0, c))
        return pila[-1][1]

    def cerrar(cant=None, precio=None, importe=None):
        nonlocal actual
        if actual is None:
            return
        if cant is None:
            doc.avisar('revisar', 'No encuentro la cantidad de la partida %s.' % actual['codigo'])
            cant = 0.0
        desc = ' '.join(actual['desc']).strip()
        desc = re.sub(r'(\w)- (\w)', r'\1\2', desc)                # palabras cortadas con guion al final de línea
        p = Partida(descripcion=desc or actual['resumen'], cantidad=cant, precio=precio, unidad=actual['unidad'],
                    codigo=actual['codigo'], importe_declarado=importe)
        p.resumen = actual['resumen']
        cap_actual().hijos.append(p)
        actual = None

    niveles = {'CAPÍTULO': 1, 'CAPITULO': 1, 'SUBCAPÍTULO': 2, 'SUBCAPITULO': 2, 'APARTADO': 3, 'SUBAPARTADO': 4}
    for l in lineas:
        t = l['texto']
        ps = l['palabras']
        if t.upper().startswith('TOTAL '):
            continue
        m = RE_CAP.match(t)
        if m and ps[0]['x0'] >= x_resumen - 10:
            cerrar() if actual and estado != 'total' else None
            nivel = niveles.get(m.group(1).upper(), 1)
            while pila and pila[-1][0] >= nivel:
                pila.pop()
            c = Capitulo(titulo=m.group(3).strip(), codigo=m.group(2))
            (pila[-1][1].hijos if pila else doc.capitulos).append(c)
            pila.append((nivel, c))
            continue
        # ¿nueva partida? código a la izquierda + unidad + resumen
        if len(ps) >= 2 and ps[0]['x1'] < x_resumen + 5 and RE_COD.match(ps[0]['text']) \
                and (ps[1]['text'].lower() in UNIDADES or ps[1]['x0'] < x_resumen + 15):
            if actual:
                cerrar()
            tiene_ud = ps[1]['text'].lower() in UNIDADES
            resumen = ' '.join(w['text'] for w in ps[2 if tiene_ud else 1:])
            actual = {'codigo': ps[0]['text'], 'unidad': ps[1]['text'].rstrip('.') if tiene_ud else 'ud',
                      'resumen': resumen, 'desc': [], 'subrayado': False}
            estado = 'desc'
            continue
        if actual is None:
            continue
        if _es_subrayado(l):
            actual['subrayado'] = True
            continue
        nums = [w for w in ps if P.es_numero(w['text'])]
        if actual['subrayado'] and nums and len(nums) == len(ps) and nums[0]['x0'] >= x_cant:
            v = [P.numero(w['text']) for w in nums]
            if len(v) >= 3:
                cerrar(v[-3], v[-2], v[-1])
            elif len(v) == 2:
                cerrar(v[0], v[1], None)
            else:
                cerrar(v[0], None, None)
            estado = None
            continue
        ultimo = ps[-1]['text']
        es_medicion = (any(w['x0'] >= x_uds for w in nums) and (P.es_numero(ultimo) or RE_FORMULA.search(ultimo))
                       and len([w for w in ps if not P.es_numero(w['text'])]) <= 6)
        if es_medicion or estado == 'medicion':
            estado = 'medicion' if es_medicion or estado == 'medicion' else estado
            continue
        actual['desc'].append(t)
    if actual:
        cerrar()
    doc.capitulos = [c for c in doc.capitulos if any(True for _ in c.partidas())]
    if not doc.capitulos:
        raise ValueError('No he encontrado partidas en el PDF del presupuesto.')
    if all(p.precio is None for p in doc.partidas()):
        doc.avisar('info', 'Mediciones sin precios: se comparan solo cantidades y precios de proveedores.')
    doc.validar()
    return doc
