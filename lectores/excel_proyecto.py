"""Proyecto / petición de ofertas del CLIENTE en Excel (p. ej. "Peticion ofertas": Orden · Designación · Cantidad · Precio).

- Busca la fila de cabecera (código/orden + designación/descripción + cantidad) en cualquier hoja.
- La unidad suele ir al principio de la designación ("Ud.", "M", "Ml"...): se separa.
- Si hay filas de capítulo (código sin cantidad) se usan; si no, los capítulos se deducen del código de la partida
  (08.02.22 -> capítulo 08 > 08.02) y se nombran según lo que contienen (Cableado, Iluminación, Mecanismos...).
- Un proyecto puede venir en VARIOS Excel (cada uno con partidas de varios capítulos): obra.py los combina con
  combinar_documentos().
"""
import collections
import os
import re

from . import _xl
from ..modelo import Capitulo, Documento, Partida
from .. import electrico as E

CAB_CODIGO = ('orden', 'codigo', 'código', 'cod', 'cod.', 'ref', 'referencia', 'nº', 'n.º', 'item', 'partida')
CAB_DESC = ('designacion', 'designación', 'descripcion', 'descripción', 'concepto', 'resumen', 'designación de las partidas',
            'texto', 'denominacion', 'denominación')
CAB_CANT = ('cantidad', 'cant', 'cant.', 'medicion', 'medición', 'uds', 'unidades')
CAB_PRECIO = ('precio', 'precio unitario', 'p.unit', 'pu')
CAB_UD = ('ud', 'ud.', 'unidad', 'um', 'u.m.')
UNIDADES = {'ud', 'ud.', 'uds', 'u', 'u.', 'm', 'm.', 'ml', 'ml.', 'm2', 'm²', 'm3', 'm³', 'kg', 'h', 'pa', 'p.a.', 'pp', 'mes',
            'l', 't', 'km', 'jgo', 'pza'}
NOMBRES = {'cable': 'Cableado', 'cable_datos': 'Cableado de datos', 'tubo': 'Canalizaciones', 'bandeja': 'Canalizaciones',
           'luminaria': 'Iluminación', 'downlight': 'Iluminación', 'proyector': 'Iluminación', 'pantalla_estanca': 'Iluminación',
           'emergencia': 'Alumbrado de emergencia', 'rail': 'Iluminación', 'interruptor': 'Mecanismos',
           'base_enchufe': 'Mecanismos', 'marco': 'Mecanismos', 'puesto_trabajo': 'Mecanismos', 'rj45': 'Mecanismos',
           'detector': 'Detección / control', 'cuadro': 'Cuadros y protecciones', 'magnetotermico': 'Cuadros y protecciones',
           'diferencial': 'Cuadros y protecciones', 'reinstalacion': 'Desmontajes', 'servicio': 'Varios / servicios',
           'ayudas': 'Ayudas y varios', 'modulo_fv': 'Fotovoltaica', 'inversor': 'Fotovoltaica', 'rack': 'Telecomunicaciones'}


def _n(v):
    return re.sub(r'\s+', ' ', str(v or '')).strip().lower()


def _num(v):
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace('€', '').replace(' ', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def _cabecera(ws):
    for fila in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 40)):
        textos = {i: _n(c.value) for i, c in enumerate(fila) if c.value is not None}
        col = {}
        for i, t in textos.items():
            if 'desc' not in col and any(t == x or t.startswith(x) for x in CAB_DESC):
                col['desc'] = i
            elif 'cod' not in col and t in CAB_CODIGO:
                col['cod'] = i
            elif 'cant' not in col and t in CAB_CANT:
                col['cant'] = i
            elif 'precio' not in col and t in CAB_PRECIO:
                col['precio'] = i
            elif 'ud' not in col and t in CAB_UD:
                col['ud'] = i
        if 'desc' in col and 'cant' in col:
            return fila[0].row, col
    return None, None


def reconoce(ruta):
    if not str(ruta).lower().endswith(('.xlsx', '.xlsm')):
        return False
    try:
        libro = _xl.cargar(ruta, data_only=True)
    except Exception:
        return False
    return any(_cabecera(ws)[0] for ws in libro.worksheets)


def _separar(desig):
    """'Ud. LUMINAR. LAMP L01.- 20W ... Suministro e instalación ...' -> (unidad, resumen, descripción)."""
    t = re.sub(r'[ \t]+', ' ', str(desig or '')).strip()
    unidad = 'ud'
    m = re.match(r'^([A-Za-z²³.]{1,4})\s+(.*)$', t, re.S)
    if m and m.group(1).lower() in UNIDADES:
        unidad = m.group(1).rstrip('.').lower()
        t = m.group(2)
    corte = re.search(r'\s(Suministro|Desmontaje para|Unidad de|Preparaci|Realizaci|Incluye|Partida)', t[15:])
    resumen = t[:15 + corte.start()] if corte else t.split('\n')[0]
    return unidad, resumen.strip()[:160], t


def _clave_cod(c):
    return tuple(int(x) if x.isdigit() else x for x in re.split(r'[.\-]', c) if x != '')


def leer(ruta, progreso=None):
    libro = _xl.cargar(ruta, data_only=True)
    nombre = os.path.splitext(os.path.basename(ruta))[0]
    filas, titulos_cap = [], {}
    for ws in libro.worksheets:
        f0, col = _cabecera(ws)
        if not f0:
            continue
        for r in ws.iter_rows(min_row=f0 + 1, values_only=True):
            def v(k):
                i = col.get(k)
                return r[i] if i is not None and i < len(r) else None
            cod = str(v('cod') or '').strip()
            desig = v('desc')
            if not desig or not str(desig).strip():
                continue
            cant = _num(v('cant'))
            if cant is None and cod:                          # fila de capítulo
                titulos_cap[cod.rstrip('.')] = str(desig).strip()
                continue
            if cant is None:
                continue
            ud, resumen, texto = _separar(desig)
            if v('ud'):
                ud = str(v('ud')).strip().rstrip('.').lower()
            filas.append({'cod': cod, 'ud': ud, 'resumen': resumen, 'texto': texto, 'cant': cant,
                          'precio': _num(v('precio')), 'hoja': ws.title})
    if not filas:
        raise ValueError('No encuentro partidas en el Excel (hace falta una cabecera con Designación/Descripción y Cantidad).')
    doc = Documento(tipo='presupuesto', origen=str(ruta), nombre=nombre)
    doc.capitulos = construir_capitulos(filas, titulos_cap)
    ceros = [f['cod'] for f in filas if not f['cant']]
    if ceros:
        doc.avisar('aviso', '%d partidas con cantidad 0 en el proyecto (%s%s).' % (
            len(ceros), ', '.join(ceros[:6]), '…' if len(ceros) > 6 else ''))
    return doc


def construir_capitulos(filas, titulos_cap):
    """Capítulos a partir de los códigos: 08.02.22 -> 08 > 08.02. Nombre: el de la fila de capítulo o uno deducido."""
    raiz = collections.OrderedDict()

    def nodo(dic, cod):
        if cod not in dic:
            dic[cod] = {'cap': Capitulo(titulo='', codigo=cod), 'hijos': collections.OrderedDict(), 'fams': collections.Counter()}
        return dic[cod]
    for f in sorted(filas, key=lambda f: _clave_cod(f['cod']) if f['cod'] else (9999,)):
        partes = [p for p in re.split(r'\.', f['cod'].strip()) if p] if f['cod'] else []
        niveles = ['.'.join(partes[:k]) for k in range(1, len(partes))][:3] or ['SIN CAPÍTULO']
        dic, cadena = raiz, []
        for c in niveles:
            nd = nodo(dic, c)
            cadena.append(nd)
            dic = nd['hijos']
        p = Partida(descripcion=f['texto'], cantidad=f['cant'], precio=f['precio'], unidad=f['ud'], codigo=f['cod'] or None,
                    resumen=f['resumen'])
        cadena[-1]['cap'].hijos.append(p)
        fam = E.familia(f['texto'], f['resumen'])
        for nd in cadena:
            nd['fams'][NOMBRES.get(fam, 'Varios')] += 1

    def cerrar(dic):
        out = []
        for cod, nd in dic.items():
            cap = nd['cap']
            nombre = titulos_cap.get(cod)
            if not nombre:
                top = [n for n, _ in nd['fams'].most_common(3) if n != 'Varios'] or ['Varios']
                nombre = ' · '.join(top[:2])
            cap.titulo = nombre
            hijos = cerrar(nd['hijos'])
            cap.hijos = hijos + cap.hijos
            out.append(cap)
        return out
    return cerrar(raiz)


def combinar_documentos(docs, nombre=''):
    """Un proyecto repartido en varios ficheros -> un único Documento con los capítulos unidos y ordenados por código."""
    if len(docs) == 1:
        return docs[0]
    total = Documento(tipo='presupuesto', origen=' + '.join(os.path.basename(d.origen) for d in docs),
                      nombre=nombre or ' + '.join(d.nombre for d in docs if d.nombre)[:120])

    def fusionar(destino, caps):
        for c in caps:
            gemelo = next((x for x in destino if (x.codigo or x.titulo) == (c.codigo or c.titulo)), None)
            if gemelo is None:
                gemelo = Capitulo(titulo=c.titulo, codigo=c.codigo)
                destino.append(gemelo)
            sub = [h for h in c.hijos if isinstance(h, Capitulo)]
            partidas = [h for h in c.hijos if not isinstance(h, Capitulo)]
            subdest = [h for h in gemelo.hijos if isinstance(h, Capitulo)]
            fusionar(subdest, sub)
            propias = [h for h in gemelo.hijos if not isinstance(h, Capitulo)] + partidas
            if all(p.codigo for p in propias):
                propias.sort(key=lambda p: _clave_cod(p.codigo))
            gemelo.hijos = subdest + propias
    for d in docs:
        fusionar(total.capitulos, d.capitulos)
        total.avisos.extend(d.avisos)

    def ordenar(caps):
        if all(c.codigo for c in caps):
            caps.sort(key=lambda c: _clave_cod(c.codigo.rstrip('#')))
        for c in caps:
            ordenar([h for h in c.hijos if isinstance(h, Capitulo)])
            sub = sorted([h for h in c.hijos if isinstance(h, Capitulo)], key=lambda x: _clave_cod(x.codigo or '9999')) \
                if all(isinstance(h, Capitulo) and h.codigo for h in c.hijos if isinstance(h, Capitulo)) else \
                [h for h in c.hijos if isinstance(h, Capitulo)]
            c.hijos = sub + [h for h in c.hijos if not isinstance(h, Capitulo)]
    ordenar(total.capitulos)
    return total
