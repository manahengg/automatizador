"""Base de precios oficial exportada a Excel en formato FIEBDC "aplanado" (p. ej. BASE DE PRECIOS JUNTA DE EXTREMADURA).

Una fila por relación padre -> hijo:
    Cód. Familia/Cap./Padre | Tipo | Código elemento | ud | Descripción resumida | Precio de fecha | Precio de coste |
    Descomposición: Línea | Descomposición: Cantidad/Rendimiento | Descomposición: Subtotal | Descripción ampliada
Tipos:  '#' capítulo · 'C' partida (precio unitario de obra = mano de obra + materiales + maquinaria + %)
        'O' mano de obra · 'P' material · 'M' maquinaria · '%' medios auxiliares / costes indirectos
Si el padre es un capítulo ('E12ECM#') la fila declara la partida; si el padre es una partida ('E12ECM060') la fila es
una línea de su descomposición (rendimiento x precio = subtotal).

Para comparar con los distribuidores interesa el precio de los MATERIALES ('P'): son precios de material sin mano de
obra, como los de una oferta. Las partidas 'C' llevan instalación, así que se guardan en el desglose (Excel aparte) pero
no se comparan con las ofertas.
"""
import collections
import re
from . import _xl
from ..modelo import Documento, Capitulo, Partida
from .. import electrico as E

TIPOS = {'O': 'Mano de obra', 'P': 'Material', 'M': 'Maquinaria', '%': 'Medios auxiliares (%)', 'C': 'Partida auxiliar'}
GENERICOS = re.compile(r'^(pequeño material|parte proporcional|p\.p\.|agua\b|material auxiliar|medios auxiliares)', re.I)


def _texto(v):
    return re.sub(r'\s+', ' ', str(v).replace('_x000D_', ' ')).strip() if v is not None else ''


def _filas(ruta):
    ws = _xl.cargar(ruta, read_only=True, data_only=True).worksheets[0]
    for k, r in enumerate(ws.iter_rows(values_only=True)):
        if k == 0:
            continue
        r = list(r) + [None] * (11 - len(r))
        if r[1] is None and r[2] is None:
            continue
        yield {'padre': _texto(r[0]), 'tipo': _texto(r[1]), 'codigo': _texto(r[2]), 'ud': _texto(r[3]) or 'ud',
               'resumen': _texto(r[4]), 'fecha': r[5], 'precio': r[6] if isinstance(r[6], (int, float)) else None,
               'linea': r[7], 'rend': r[8] if isinstance(r[8], (int, float)) else None,
               'subtotal': r[9] if isinstance(r[9], (int, float)) else None, 'ampliada': _texto(r[10])}


def reconoce(ruta):
    try:
        ws = _xl.cargar(ruta, read_only=True, data_only=True).worksheets[0]
        cab = [_texto(c).lower() for c in next(ws.iter_rows(max_row=1, values_only=True))]
        return (len(cab) >= 10 and cab[0].startswith('cód. familia') and cab[1].startswith('tipo')
                and any(c.startswith('precio de coste') for c in cab))
    except Exception:
        return False


def analizar(ruta):
    """Estructura completa de la base: capítulos, partidas con su descomposición, elementos simples e incoherencias."""
    caps, partidas, elementos, descomp = {}, {}, {}, collections.defaultdict(list)
    hijos_cap = collections.defaultdict(list)
    fecha = None
    for f in _filas(ruta):
        if f['fecha'] is not None and fecha is None and hasattr(f['fecha'], 'strftime'):
            fecha = f['fecha'].strftime('%d/%m/%Y')
        if f['tipo'] == '#':
            caps[f['codigo']] = {'codigo': f['codigo'], 'titulo': f['resumen'], 'padre': f['padre']}
            hijos_cap[f['padre']].append(f['codigo'])
        elif f['padre'].endswith('#'):                       # partida (o elemento suelto) dentro de un capítulo
            if f['tipo'] == 'C':
                partidas[f['codigo']] = dict(f, capitulo=f['padre'])
                hijos_cap[f['padre']].append(f['codigo'])
            el = elementos.setdefault(f['codigo'], dict(f))
            if f['ampliada'] and not el.get('ampliada'):
                el['ampliada'] = f['ampliada']
        else:                                               # línea de la descomposición de f['padre']
            descomp[f['padre']].append(f)
            el = elementos.setdefault(f['codigo'], dict(f))
            if el.get('precio') is None:
                el['precio'] = f['precio']
    for d in descomp.values():
        d.sort(key=lambda x: float(x['linea']) if str(x['linea'] or '').replace('.', '', 1).isdigit() else 0)

    def ruta_cap(c):
        out, vistos = [], set()
        while c in caps and c not in vistos and caps[c]['titulo'] and not c.startswith(('BASE', 'ZZZ')):
            vistos.add(c)
            out.insert(0, caps[c]['titulo'])
            c = caps[c]['padre']
        return out

    usos = collections.defaultdict(list)                   # material -> partidas que lo usan
    for cod, p in partidas.items():
        p['ruta'] = ruta_cap(p['capitulo'])
        tot = collections.Counter()
        for x in descomp.get(cod, []):
            tot[x['tipo']] += x['subtotal'] or 0
            if x['tipo'] == 'P':
                usos[x['codigo']].append(cod)
        p['mano_obra'], p['materiales'] = round(tot['O'], 2), round(tot['P'] + tot['C'], 2)
        p['maquinaria'], p['porcentajes'] = round(tot['M'], 2), round(tot['%'], 2)
        p['suma'] = round(sum(tot.values()), 2)
        p['incoherencias'] = _incoherencias(p, descomp.get(cod, []))
    for cod, el in elementos.items():
        el['usos'] = usos.get(cod, [])
    return {'fecha': fecha, 'capitulos': caps, 'hijos_cap': hijos_cap, 'partidas': partidas, 'descomp': descomp,
            'elementos': elementos, 'titulo': next((c['titulo'] for c in caps.values() if c['codigo'].startswith('BASE')),
                                                   'Base de precios')}


def _incoherencias(p, lineas):
    out = []
    if p['precio'] is not None and p['suma'] and abs(p['suma'] - p['precio']) > max(0.02, p['precio'] * 0.005):
        out.append('La descomposición suma %.2f € y el precio de la partida es %.2f €.' % (p['suma'], p['precio']))
    mats = [x for x in lineas if x['tipo'] == 'P' and not GENERICOS.match(x['resumen'])]
    if not mats:
        return out
    titulo = p['resumen'] + ' ' + (p['ampliada'] or '')[:200]
    at = E.atributos(p['resumen'])
    fam = at.get('familia')
    # material principal: el de la misma familia con más importe (si no, el de más importe)
    mismas = [x for x in mats if E.atributos(x['resumen']).get('familia') == fam] or mats
    ppal = max(mismas, key=lambda x: x['subtotal'] or 0)
    ap = E.atributos(ppal['resumen'])
    for clave, nombre in (('seccion', 'sección'), ('tipo_cable', 'tipo de cable'), ('diametro', 'diámetro'),
                          ('ip', 'grado IP')):
        x, y = at.get(clave), ap.get(clave)
        if x is not None and y is not None and x != y and len([z for z in mismas
                                                               if E.atributos(z['resumen']).get(clave) == x]) == 0:
            out.append('El título dice %s %s pero el material de la descomposición es "%s" (%s %s).'
                       % (nombre, _fmt(x), ppal['resumen'], nombre, _fmt(y)))
    for clave, nombre in (('potencia_w', 'potencia'), ('amperios', 'intensidad')):
        x, y = at.get(clave), ap.get(clave)
        if x and y and not set(x) & set(y):
            out.append('El título dice %s %s pero el material es "%s".' % (nombre, '/'.join(_fmt(v) for v in x),
                                                                          ppal['resumen']))
    if 'halogen' in E.norm(titulo) or '(as)' in E.norm(titulo):
        for x in mats:
            if re.search(r'\bh07v|\brv-?k\b|\bpvc\b', E.norm(x['resumen'])) and 'libre' not in E.norm(x['resumen']):
                out.append('Partida libre de halógenos con material "%s" (lleva PVC).' % x['resumen'])
                break
    return out


def _fmt(v):
    if isinstance(v, (set, frozenset, list, tuple)):
        return '/'.join(_fmt(x) for x in v)
    return ('%g' % v).replace('.', ',') if isinstance(v, float) else str(v)


def leer(ruta, progreso=None):
    """Documento de 'proveedor de referencia': una línea por MATERIAL (P) con su precio, agrupadas por el capítulo de
    la primera partida que lo usa."""
    if progreso:
        progreso('Leyendo la base de precios…', None)
    b = analizar(ruta)
    nombre = re.sub(r'\s+', ' ', b['titulo']).strip().title()
    doc = Documento(tipo='base_precios', origen=str(ruta), nombre=nombre, proveedor=nombre, fecha=b['fecha'],
                    condiciones={'referencia': True})
    grupos = collections.OrderedDict()
    for cod, el in b['elementos'].items():
        if el['tipo'] != 'P' or el.get('precio') is None or GENERICOS.match(el['resumen']):
            continue
        usos = el['usos']
        ruta_c = b['partidas'][usos[0]]['ruta'] if usos else []
        titulo = ' > '.join(ruta_c[-2:]) if ruta_c else 'Materiales sin partida'
        desc = el['resumen']
        if el.get('ampliada') and len(el['ampliada']) > len(desc) + 5:
            desc = el['ampliada']
        part = Partida(descripcion=desc, cantidad=0, precio=float(el['precio']), unidad=el['ud'], codigo=cod,
                       referencia=cod, resumen=el['resumen'])
        if usos:
            part.notas = ['Se usa en %d partida(s): %s' % (len(usos), '; '.join(
                '%s %s' % (u, b['partidas'][u]['resumen']) for u in usos[:3]))]
        grupos.setdefault(titulo, []).append(part)
    for titulo, partes in grupos.items():
        doc.capitulos.append(Capitulo(titulo=titulo, hijos=partes))
    n_inc = sum(1 for p in b['partidas'].values() if p['incoherencias'])
    doc.avisar('info', 'Base de precios: %d partidas, %d materiales con precio (fecha %s). Es un precio de REFERENCIA: '
                       'no cuenta para el "más bajo" ni para el reparto entre distribuidores.'
               % (len(b['partidas']), sum(len(v) for v in grupos.values()), b['fecha'] or '?'))
    if n_inc:
        doc.avisar('aviso', '%d partidas de la base tienen incoherencias (título frente a descomposición): ver el '
                            'desglose.' % n_inc)
    return doc
