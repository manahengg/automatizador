"""Conocimiento del sector eléctrico: leer las características técnicas de un texto, convertir una partida del cliente
en los MATERIALES (con su cantidad real) que hay que comprar, y detectar textos sin sentido o materiales distintos.

Todo es determinista (reglas), así que se puede revisar y ampliar a mano:
  * FAMILIAS        palabras que identifican qué es (cable, tubo, downlight...)
  * atributos()     sección, tipo de cable, diámetro, W, lm, K, IP, polos, amperios, mA, fases, kWp...
  * materiales()    una partida -> 1..n materiales con cantidad (4x35+1x16 x 27,5 m -> 110 m 1x35 + 27,5 m 1x16)
  * revisar_partida()   incoherencias en el propio texto del cliente
  * comparar()      diferencias técnicas entre lo pedido y lo ofertado
"""
import re
import unicodedata

SECCIONES_NORMALIZADAS = {0.5, 0.75, 1, 1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300, 400, 500, 630}

# (familia, patrones). Se prueban en orden: la primera que aparece en el texto gana. Se mira primero el título.
FAMILIAS = [
    ('canon', r'\bcanon\b|ecoraee|\braee\b|ecopila|ges\.? logistica'),
    ('servicio', r'legalizacion|tramit|expediente|honorarios|proyecto de|ensayos y pruebas|alquiler|puesta en marcha|'
                 r'configuracion|programacion|visita a la obra|vinculacion'),
    ('ayudas', r'ayudas? (de )?albanileria'),
    ('reinstalacion', r'reinstalacion|desmontaje|retirada|desmontar'),
    ('puesto_trabajo', r'puesto (de )?trabajo|caja (de )?(pared|tomas|empotrar).*(element|modul)|cajetin|kit ?caja'),
    ('tapa_arqueta', r'tapa (de )?arqueta|tapa ?iberdrola|tapa\w* .*m2.?t2'),
    ('arqueta', r'\barqueta'),
    ('bandeja', r'\bbandeja|\btbpe\b|\bbpe-?c\b'),
    ('canal', r'canal (protectora|aislante)|canaleta|\bcanal\b'),
    ('tubo', r'\btubos?\b|canalizacion de tubo|manguito'),
    ('pararrayos', r'pararrayos|\bpdc\b|nimbus|mastil|contador (de )?rayos|cabezal|barra equipotencial'),
    ('toma_tierra', r'toma de tierra|\bpica\b|picas?\b|cobre desnudo|grapa'),
    ('modulo_fv', r'modulo ?f(oto)?v|panel(es)? (solar|fotovolt)|\bfv\b.*\d+ ?wp|placa solar|fotovoltaic'),
    ('inversor', r'\binversor'),
    ('sai', r'\bsai\b|\bups\b'),
    ('rack', r'\brack\b|armario environ|patch panel|pacth panel|panel de ventilacion|pasahilos|bandeja 19'),
    ('cable_datos', r'\butp\b.*cable|cable .*(cat ?6|categoria 6|utp|coaxial)|coaxial'),
    ('rj45', r'rj ?45|keystone|conector hembra'),
    ('analizador', r'analizador'),
    ('gestor', r'gestor energetico|line.?eds|powerstudio|modulo exp'),
    ('trafo_corriente', r'transformador(es)? (de )?(corriente|trifasico mc)|\bmc3?-?\d|\btrafo'),
    ('cuadro', r'\bcuadro|armario (de )?(poliester|metalic)|caja de distribucion|envolvente'),
    ('diferencial', r'diferencial|\bid\b \dp'),
    ('magnetotermico', r'magnetotermico|\bpia\b|interruptor automatico'),
    ('sobretensiones', r'sobretensi|limitador'),
    ('fusible', r'fusible|base helio'),
    ('detector', r'detector|det\.? ?movim|sensor de (movimiento|presencia)|dicromat'),
    ('emergencia', r'emergencia|blq\.? ?auto'),
    ('downlight', r'downlight|downl\b|downl\.'),
    ('pantalla_estanca', r'estanca|damp proof|wt007|pantalla led|lestc'),
    ('rail', r'\brail\b|carril|\btrack\b|acoplamiento|alimentacion trifasica t\.?t|conexion angular|tubo estructural'),
    ('proyector', r'proyector|parscan|lightscan|spot\b|rejilla de panal|pieza especial de conexion'),
    ('luminaria', r'luminaria|lumin\.|luminar\b|lampara|fine led|tira (de )?led|led strip|strip led|lineal|panel led|\bled\b.*\d+ ?lm|lima\b|ledlima'),
    ('control_iluminacion', r'pastilla rele|botonera|casambi|pantalla tactil|pasarela|bluetooth.*escenas|sistema de control|sist\.? control'),
    ('interruptor', r'interruptor|conmutador|pulsador'),
    ('base_enchufe', r'base (de )?ench|schuko|schuco|toma de corriente|\btc\b'),
    ('marco', r'\bmarco|placa (vd|voz)|tapa ciega|adaptador'),
    ('smart_meter', r'smart meter|contador|vatimetro|\bct kit'),
    ('caja', r'caja de registro|caja de derivacion|registro sec|\bregistro\b'),
    ('cable', r'\bcable|conductor|derivacion individual|linea (de )?(alimentacion|distribucion|bt)|manguera|'
              r'\brz1-?k|h07z1|h07v|rv-?k|xz1|afumex|exzhellent|alsecure|sumsave|ecoclass|afirenas|harmohny|retenax'),
]
# familias que se consideran la misma cosa a efectos de emparejar
COMPATIBLES = [
    {'tubo', 'canal'}, {'luminaria', 'proyector', 'pantalla_estanca', 'downlight'}, {'emergencia', 'luminaria'},
    {'arqueta', 'tapa_arqueta'}, {'puesto_trabajo', 'base_enchufe', 'rj45', 'marco', 'caja'},
    {'interruptor', 'marco'}, {'base_enchufe', 'marco'}, {'gestor', 'analizador', 'trafo_corriente'},
    {'pararrayos', 'toma_tierra'}, {'modulo_fv', 'inversor', 'fusible', 'sobretensiones', 'smart_meter', 'cuadro', 'diferencial', 'magnetotermico'},
    {'cuadro', 'magnetotermico', 'diferencial', 'sobretensiones'}, {'rail', 'proyector'}, {'control_iluminacion', 'proyector'},
    {'bandeja', 'canal'}, {'cable', 'cable_datos'},
]
TERMINOS_OPTICOS = r'\b(wide flood|extra wide flood|flood|spot|wall ?wash|haz)\b'


def norm(s):
    s = unicodedata.normalize('NFD', str(s or '').lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace('×', 'x').replace('²', '2').replace('ø', ' d ').replace('Ø', ' d ')
    return re.sub(r'\s+', ' ', s).strip()


def _f(x):
    return float(x.replace(',', '.'))


def familia(texto, titulo=''):
    if not titulo:
        titulo = (texto or '')[:45]           # en ofertas la primera parte de la descripción dice qué es
    for t in (titulo, texto):
        n = norm(t)
        if not n:
            continue
        for fam, pat in FAMILIAS:
            if re.search(pat, n):
                return fam
    # texto de OCR con palabras pegadas ('TUBOENCHUFABLEMETRICO16'): se busca sin espacios ni límites de palabra
    todo = norm(titulo + ' ' + texto)
    if not any(len(w) >= 14 and re.search(r'[a-z]{4}', w) for w in todo.split()):
        return None                         # el texto no tiene palabras pegadas: no se busca dentro de las palabras
    pegado = todo.replace(' ', '')
    for fam, pat in FAMILIAS:
        if fam in ('canon', 'servicio', 'caja', 'marco'):
            continue
        p2 = pat.replace('\\b', '').replace(' ?', '').replace(' ', '')
        try:
            if re.search(p2, pegado):
                return fam
        except re.error:
            continue
    return None


def compatibles(a, b):
    if not a or not b:
        return None
    if a == b:
        return True
    return any(a in g and b in g for g in COMPATIBLES)


# ---------------------------------------------------------------------------------------------- atributos
TIPOS_CABLE = [('RZ1-K', r'rz1-?k'), ('H07Z1-K', r'h?07z1-?k'), ('RV-K', r'\brv-?k\b'), ('XZ1', r'\bxz1\b|xz1\s*\('),
               ('H07V-K', r'h07v-?k'), ('SZ1-K', r'sz1-?k'), ('H05VV-F', r'h05vv'), ('RZ1MZ1-K', r'rz1mz1'),
               ('HEPRZ1', r'heprz1'), ('VV-K', r'\bvv-?k\b')]


def formacion_cable(n):
    """'4x35mm2+1x16mm2' / '3(1x150)+1x95' / '1x2,5' / '5g6' -> [(nº conductores, sección)]."""
    m = re.search(r'(\d{1,3}(?:[.,]\d+)?)\s*mm2? de seccion', n)
    seccion_texto = _f(m.group(1)) if m else None
    m = re.search(r'unipolar(?:es)?\s+(?:de\s+)?(\d{1,3}(?:[.,]\d+)?)\s*mm', n)
    if m and not re.search(r'\d\s*[xg]\s*\d', n.split('unipolar')[1][:20]):
        return [(1, _f(m.group(1)))]
    n = n.replace(' x ', 'x').replace('mm2', '').replace('mm', '')
    out = []
    m = re.search(r'(\d+)\s*\(\s*1\s*x\s*(\d+(?:[.,]\d+)?)\s*\)(?:\s*\+\s*(\d+)\s*x\s*(\d+(?:[.,]\d+)?))?', n)
    if m:
        out.append((int(m.group(1)), _f(m.group(2))))
        if m.group(3):
            out.append((int(m.group(3)), _f(m.group(4))))
        return out
    m = re.search(r'\b(\d{1,2})\s*[xg]\s*(\d{1,3}(?:[.,]\d+)?)\b(?:\s*\+\s*(?:tt\s*)?(\d{1,2})\s*[xg]\s*(\d{1,3}(?:[.,]\d+)?))?', n)
    if m:
        out.append((int(m.group(1)), _f(m.group(2))))
        if m.group(3):
            out.append((int(m.group(3)), _f(m.group(4))))
        return out
    if seccion_texto:
        return [(1, seccion_texto)]
    return out


MARCAS_LIBRES = ('afumex', 'exzhellent', 'alsecure', 'sumsave', 'afirenas', 'toxfree', 'tox free', 'harmohny',
                 'ecoclass', 'eurocable z1', 'hersatene', 'superflex z1', 'erivolt')
MARCAS_CON = ('retenax', 'wirepol', 'tuperplas')


def halogenos(texto, at=None):
    """¿Lleva halógenos? -> ('libre' | 'contiene' | None, motivo).

    Se deduce, por este orden: texto explícito, designación normalizada del cable (Z1 = poliolefina libre de halógenos;
    V = PVC, que lleva cloro), clase CPR con a1 (baja acidez), marcas conocidas y material (PVC) de tubos y canales."""
    n = norm(texto)
    at = at if at is not None else atributos(texto)
    if re.search(r'con halogen|contiene halogen', n):
        return 'contiene', 'el texto indica que contiene halógenos'
    if re.search(r'libre(s)? de halogen|libre hal|sin halogen|cero halogen|0 ?% halogen|halogen.?free|\blszh\b|'
                 r'\bls0h\b|\blsoh\b|\bzh\b|\(as\)|\bas\+?\b|\blh\b|corrug\.?lh|\brlh|\bnhxh', n):
        return 'libre', 'el texto lo indica (AS / libre de halógenos / LH)'
    tc = at.get('tipo_cable')
    if tc in ('RZ1-K', 'H07Z1-K', 'XZ1', 'SZ1-K', 'RZ1MZ1-K', 'HEPRZ1'):
        return 'libre', 'designación %s: aislamiento/cubierta de poliolefina "Z1", libre de halógenos' % tc
    if tc in ('RV-K', 'H07V-K', 'VV-K', 'H05VV-F'):
        return 'contiene', 'designación %s: cubierta/aislamiento de PVC ("V"), que contiene halógenos (cloro)' % tc
    if re.search(r'z1-?k|\bz1\b|es07z1', n):
        return 'libre', 'designación con Z1 (poliolefina libre de halógenos)'
    for mca in MARCAS_LIBRES:
        if mca in n:
            return 'libre', 'la gama "%s" es libre de halógenos' % mca
    for mca in MARCAS_CON:
        if mca in n:
            return 'contiene', 'la gama "%s" es de PVC' % mca
    if re.search(r'\b[bcde]2?ca[- ]?s\d[a-z]?,? ?d\d,? ?a1\b', n):
        return 'libre', 'clase CPR con a1 (baja acidez, propia de cables libres de halógenos)'
    if re.search(r'\bpvc\b|policloruro', n):
        return 'contiene', 'es de PVC (contiene cloro, un halógeno)'
    if re.search(r'poliolefin|polietileno|polipropileno|\bpe\b|\bpp\b', n) and at.get('familia') in ('tubo', 'canal', 'bandeja'):
        return 'libre', 'material poliolefínico (PE/PP), sin halógenos'
    return None, 'no se ha podido deducir del texto'


def atributos(texto, titulo=''):
    """Características técnicas que aparecen en el texto. Claves solo si se encuentran."""
    n = norm(titulo + ' ' + texto)
    a = {}
    fam = familia(texto, titulo)
    if fam:
        a['familia'] = fam
    if fam in ('cable', 'cable_datos', None):
        form = formacion_cable(norm(titulo)) or formacion_cable(n)
        if form:
            a['formacion'] = form
            a['seccion'] = form[0][1]
        for nombre, pat in TIPOS_CABLE:
            if re.search(pat, n):
                a['tipo_cable'] = nombre
                break
        if re.search(r'\(as\)|\bas\b|libre de halogen|lszh|cca-s1|afumex|alsecure|exzhellent', n):
            a['libre_halogenos'] = True
        if re.search(r'aluminio|\d\s*al\b|\ba[li]2\b|\)\s*al\b|\bal xz1|xz1.*\bal\b', n):
            a['material'] = 'Al'
        elif re.search(r'\bcu\b|cobre', n):
            a['material'] = 'Cu'
        if re.search(r'unipolar', n):
            a['polaridad'] = 'unipolar'
        elif re.search(r'multipolar|manguera|\d+g\d', n):
            a['polaridad'] = 'multipolar'
        if re.search(r'0[.,]6/1 ?kv|1000 ?v', n):
            a['tension'] = '0,6/1kV'
        elif re.search(r'750 ?v|450/750', n):
            a['tension'] = '450/750V'
    if fam in ('tubo', 'canal', 'bandeja', None) or 'tubo' in n:
        m = re.search(r'\b(?:d|dn|diametro|m|d\.)\s*[=.-]?\s*(\d{2,3})\s*(?:mm)?\b', n) or \
            re.search(r'\b(\d{2,3})\s*mm\.? de diametro', n) or re.search(r'\bm-?(\d{2,3})\b', n)
        if m:
            a['diametro'] = int(m.group(1))
        for t, pat in (('corrugado', 'corrug'), ('rigido', 'rigido'), ('flexible', 'flexible'), ('acero', 'acero'),
                       ('pvc', 'pvc'), ('polietileno', 'polietileno'), ('policarbonato', 'policarbonato'),
                       ('enchufable', 'enchufable')):
            if re.search(pat, n):
                a.setdefault('tipo_tubo', set()).add(t)
        m = re.search(r'(\d{2,3})\s*x\s*(\d{2,3})', n)
        if m and fam in ('bandeja', 'canal'):
            a['dimensiones'] = tuple(sorted((int(m.group(1)), int(m.group(2)))))
    if fam in ('cable', 'cable_datos', 'tubo', 'canal', 'bandeja'):
        a['halogenos'], a['halogenos_motivo'] = halogenos(titulo + ' ' + texto, a)
    w = re.findall(r'(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d{1,4}(?:,\d+)?|\d{1,4}\.\d)\s*w\b(?!p)', n)
    if w:
        a['potencia_w'] = sorted({float(x.replace('.', '')) if re.fullmatch(r'\d{1,3}(?:\.\d{3})+', x) else _f(x)
                                  for x in w})
    m = re.findall(r'(\d{1,2}(?:[.,]\d+)?)\s*kwp', n)
    if m:
        a['kwp'] = _f(m[0])
    m = re.findall(r'(\d{2,4})\s*wp\b', n)
    if m:
        a['wp'] = int(m[0])
    elif fam == 'modulo_fv' and a.get('potencia_w') and 200 <= a['potencia_w'][0] <= 800:
        a['wp'] = int(a['potencia_w'][0])          # en módulos FV la potencia en W es la potencia pico
    lm = re.findall(r'(\d{1,2}\.?\d{3}|\d{2,5})\s*(?:lm|lumenes|lumens)\b', n)
    if lm:
        a['lumenes'] = sorted({int(x.replace('.', '')) for x in lm})
    k = re.findall(r'\b(2700|3000|3500|4000|5000|6500)\s*k\b', n) or re.findall(r'/8(27|30|40|65)\b|led\d+/8(30|40)', n)
    if k:
        v = k[0] if isinstance(k[0], str) else next(x for x in k[0] if x)
        a['temp_color'] = int(v) if len(v) == 4 else int(v) * 100
    ip = re.findall(r'\bip[- ]?(\d{2,3})\b', n) or re.findall(r'\bip([0-6]\d)(?=\d)', n)   # 'ip6524v' (pegado por OCR)
    if ip:
        a['ip'] = ip
    ma = re.findall(r'(\d{2,3})\s*ma\b', n)
    if ma:
        a['sensibilidad_ma'] = sorted({int(x) for x in ma})
    amp = re.findall(r'(?<![\d.,x])(\d{1,3})\s*a\b(?!c)', n)
    if amp and fam in ('magnetotermico', 'diferencial', 'base_enchufe', 'interruptor', 'fusible', 'sobretensiones', 'cuadro'):
        a['amperios'] = sorted({int(x) for x in amp})
    p = re.findall(r'\b(\d)\s*p\b|\b(\d)p\+n', n)
    if p:
        a['polos'] = sorted({int(x or y) for x, y in p})
    if re.search(r'monofasic|\b1ph\b|single phase|230 ?v 50', n):
        a.setdefault('fases', set()).add('monofásico')
    if re.search(r'trifasic|\b3ph\b|400 ?v|tri-tri', n):
        a.setdefault('fases', set()).add('trifásico')
    m = re.search(r'\b(extra wide flood|wide flood|wall ?wash|flood|spot|oval flood|narrow spot)\b', n)
    if m:
        a['optica'] = m.group(1).replace('wallwash', 'wall wash')
    m = re.search(r'\bl\s*=\s*(\d+(?:[.,]\d+)?)\s*(m|mm)\b', n)
    if m:
        a['longitud_mm'] = _f(m.group(1)) * (1000 if m.group(2) == 'm' else 1)
    for pos in ('inicio', 'intermedia', 'final', 'derecha', 'izquierda'):
        if re.search(r'\b%s\b' % pos, n):
            a['posicion'] = pos
    if re.search(r'\bdali\b', n):
        a['dali'] = True
    if re.search(r'bluetooth', n):
        a['bluetooth'] = True
    return a


# ---------------------------------------------------------------------------------------------- materiales
def _desc_cable(n_cond, seccion, at):
    s = ('%g' % seccion).replace('.', ',')
    partes = ['Cable 1x%s mm²' % s if n_cond == 1 else 'Cable %dx%s mm²' % (n_cond, s)]
    if at.get('tipo_cable'):
        partes.append(at['tipo_cable'] + ('(AS)' if at.get('libre_halogenos') and at['tipo_cable'] != 'XZ1' else ''))
    if at.get('material'):
        partes.append(at['material'])
    return ' '.join(partes)


def materiales(partida, titulo=''):
    """Materiales que hay que comprar para una partida del cliente, con la cantidad REAL.

    Devuelve [{'sufijo', 'descripcion', 'factor', 'cantidad', 'unidad', 'atributos', 'nota'}].
    El primero es el material principal. Si no hay nada que desglosar devuelve un único material con factor 1.
    """
    titulo = titulo or getattr(partida, 'resumen', '') or ''
    texto = partida.descripcion or ''
    at = atributos(texto, titulo)
    q = partida.cantidad or 0
    ud = partida.unidad or 'ud'
    nt = norm(titulo) or norm(texto[:120])
    out = []
    fam = at.get('familia')
    form = at.get('formacion') or []
    if fam == 'cable' and form:
        n_total = sum(c for c, _ in form)
        multipolar = at.get('polaridad') == 'multipolar'
        unipolar = at.get('polaridad') == 'unipolar' or re.search(r'\d\s*\(\s*1\s*x', norm(titulo + ' ' + texto))
        if n_total > 1 and unipolar and not multipolar:
            for i, (c, s) in enumerate(form):
                a2 = dict(at, seccion=s, formacion=[(1, s)])
                out.append({'sufijo': 'abcdef'[i] if len(form) > 1 else '', 'descripcion': _desc_cable(1, s, at),
                            'factor': c, 'cantidad': round(c * q, 3), 'unidad': ud, 'atributos': a2,
                            'nota': '%d conductores unipolares x %s %s' % (c, _num(q), ud) if c > 1 else
                                    '1 conductor x %s %s' % (_num(q), ud)})
            return out
        if n_total > 1 and not multipolar and not unipolar:
            at['_duda_polaridad'] = True
        c, s = form[0]
        out.append({'sufijo': '', 'descripcion': _desc_cable(c, s, at) if not multipolar or len(form) == 1 else titulo,
                    'factor': 1, 'cantidad': q, 'unidad': ud, 'atributos': at, 'nota': ''})
        return out
    m = re.match(r'^\s*(\d{1,2})\s+tubos?\b', nt)
    if m and int(m.group(1)) > 1:
        f = int(m.group(1))
        return [{'sufijo': '', 'descripcion': titulo, 'factor': f, 'cantidad': round(f * q, 3), 'unidad': ud,
                 'atributos': at, 'nota': '%d tubos x %s %s de canalización' % (f, _num(q), ud)}]
    if fam == 'modulo_fv':
        nd = norm(texto)
        mp = re.search(r'(\d+) (?:paneles|modulos|placas)', nd)
        if mp:
            npan = int(mp.group(1))
            a1 = dict(at)
            out.append({'sufijo': 'a', 'descripcion': 'Módulos fotovoltaicos (%s)' % (
                '%s kWp en total' % _num(at['kwp']) if at.get('kwp') else 'paneles'), 'factor': npan,
                'cantidad': npan * q, 'unidad': 'ud', 'atributos': a1,
                'nota': '%d paneles por sistema x %s' % (npan, _num(q))})
            if 'inversor' in nd:
                fa = {'familia': 'inversor'}
                if at.get('fases'):
                    fa['fases'] = at['fases'] - ({'monofásico'} if 'trifas' in nd and 'monofas' not in nd else set())
                out.append({'sufijo': 'b', 'descripcion': 'Inversor%s' % (' trifásico' if 'trifas' in nd else ''),
                            'factor': 1, 'cantidad': q, 'unidad': 'ud', 'atributos': fa, 'nota': ''})
            return out
    if fam == 'puesto_trabajo':
        rj = re.search(r'(\d+)\s*rj\s*-?45', nt) or re.search(r'(\w+) tomas de comunicacion', norm(texto))
        tc = re.findall(r'(\d+)\s*tc', nt)
        out.append({'sufijo': 'a', 'descripcion': 'Puesto de trabajo (caja + tomas de corriente%s)' % (
            ' %s' % '+'.join(tc) if tc else ''), 'factor': 1, 'cantidad': q, 'unidad': ud, 'atributos': at, 'nota': ''})
        if rj:
            n = _numero_palabra(rj.group(1))
            if n:
                out.append({'sufijo': 'b', 'descripcion': 'Conector RJ45 cat.6', 'factor': n, 'cantidad': n * q,
                            'unidad': 'ud', 'atributos': {'familia': 'rj45'},
                            'nota': '%d RJ45 por puesto x %s puestos' % (n, _num(q))})
        return out
    return [{'sufijo': '', 'descripcion': titulo or texto[:80], 'factor': 1, 'cantidad': q, 'unidad': ud,
             'atributos': at, 'nota': ''}]


def _numero_palabra(s):
    pal = {'un': 1, 'una': 1, 'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'ocho': 8}
    return int(s) if s.isdigit() else pal.get(s)


def _num(x):
    return ('%.2f' % x).rstrip('0').rstrip('.').replace('.', ',')


def clave_material(at):
    """Clave canónica para encontrar el mismo material en otras ofertas/obras (base de datos de precios)."""
    fam = at.get('familia')
    if not fam:
        return None
    partes = [fam]
    if fam in ('cable', 'cable_datos'):
        if at.get('formacion'):
            partes.append('+'.join('%dx%g' % cs for cs in at['formacion']))
        partes += [at.get('tipo_cable') or '', 'Al' if at.get('material') == 'Al' else '']
    elif fam in ('tubo', 'canal'):
        partes += [str(at.get('diametro') or ''), '/'.join(sorted(at.get('tipo_tubo') or []))]
    elif fam == 'bandeja':
        partes.append('x'.join(map(str, at.get('dimensiones') or ())))
    else:
        if at.get('potencia_w'):
            partes.append('%gW' % at['potencia_w'][0])
        if at.get('lumenes'):
            partes.append('%dlm' % at['lumenes'][0])
        if at.get('amperios'):
            partes.append('%dA' % at['amperios'][0])
        if at.get('polos'):
            partes.append('%dP' % at['polos'][0])
        if at.get('wp'):
            partes.append('%dWp' % at['wp'])
        if at.get('optica'):
            partes.append(at['optica'])
        if at.get('longitud_mm'):
            partes.append('L%g' % at['longitud_mm'])
        if at.get('posicion'):
            partes.append(at['posicion'])
    clave = '|'.join(partes).rstrip('|')
    return clave if clave != fam else None


# ---------------------------------------------------------------------------------------------- revisión
def revisar_partida(partida, titulo=''):
    """Incoherencias del texto del CLIENTE. Devuelve lista de textos."""
    titulo = titulo or getattr(partida, 'resumen', '') or ''
    texto = partida.descripcion or ''
    nt, nd = norm(titulo), norm(texto)
    out = []
    for ip in re.findall(r'\bip[- ]?(\d{2,})\b', nd + ' ' + nt):
        if len(ip) != 2 or int(ip[0]) > 6:
            out.append('Grado de protección "IP%s" no existe (IP lleva 2 cifras: sólidos 0-6 y líquidos 0-9).' % ip)
    at_t, at_d = atributos('', titulo), atributos(texto, '')
    for clave, nombre in (('potencia_w', 'potencia (W)'), ('lumenes', 'flujo (lm)'), ('seccion', 'sección (mm²)'),
                          ('diametro', 'diámetro (mm)'), ('kwp', 'potencia pico (kWp)')):
        vt, vd = at_t.get(clave), at_d.get(clave)
        if vt is None or vd is None:
            continue
        lt = vt if isinstance(vt, list) else [vt]
        ld = vd if isinstance(vd, list) else [vd]
        if not set(lt) & set(ld):
            out.append('El título indica %s %s y la descripción %s: revisar cuál es el correcto.' % (
                nombre, '/'.join(_num(x) for x in lt), '/'.join(_num(x) for x in ld)))
    if re.search(r'conexion (a )?red', nt) and re.search(r'sin conexion a (la )?red|aislad', nd):
        out.append('El título dice "conexión a red" pero la descripción dice "sin conexión a red" (aislada): contradicción.')
    fam = familia(texto, titulo)
    if fam not in ('proyector', 'luminaria', 'downlight', 'pantalla_estanca', 'emergencia', 'rail', None) and \
            re.search(TERMINOS_OPTICOS, nd):
        out.append('La descripción incluye características de óptica de luminaria ("%s") en una partida de %s: '
                   'parece texto copiado de otra partida.' % (re.search(TERMINOS_OPTICOS, nd).group(1), fam.replace('_', ' ')))
    at = atributos(texto, titulo)
    if at.get('familia') == 'cable':
        for c, s in at.get('formacion') or []:
            if s not in SECCIONES_NORMALIZADAS:
                out.append('Sección de cable %s mm² no normalizada.' % _num(s))
        if re.search(r'\d\s*x\s*\(\s*\d\s*x\s*\(', nd):
            out.append('Formación de cable con paréntesis anidados (p. ej. 4x(4x(1x240))): texto mal escrito, aclarar.')
        tc, ten = at.get('tipo_cable'), at.get('tension')
        if tc == 'H07Z1-K' and ten == '0,6/1kV':
            out.append('H07Z1-K es un cable de 450/750 V, no de 0,6/1 kV como indica el texto.')
        if tc in ('RZ1-K', 'XZ1', 'RV-K') and ten == '450/750V':
            out.append('%s es un cable de 0,6/1 kV, no de 450/750 V.' % tc)
        if at.get('_duda_polaridad') is True:
            out.append('Cable con varios conductores sin indicar si es unipolar o multipolar: la cantidad de material '
                       'se ha dejado igual a la de la partida.')
    if 'conexion red' in nt and 'monofas' in nd and 'trifas' in nd:
        pass
    if partida.precio == 0:
        out.append('Partida con precio 0,00 en el presupuesto del cliente.')
    if re.search(r'\b1[.,]00\s*w\b', nd) and re.search(r'1[.,]000\s*w', nt):
        out.append('El título dice 1.000 W y la descripción "1.00W": errata en la descripción.')
    return out


def comparar(at_cli, at_prov):
    """Diferencias técnicas entre lo que pide el cliente y lo que oferta el proveedor. Lista de (gravedad, texto)."""
    out = []
    fc, fp = at_cli.get('familia'), at_prov.get('familia')
    if fc and fp and compatibles(fc, fp) is False:
        out.append(('alta', 'Oferta un producto de otro tipo (%s) que lo pedido (%s).' % (fp.replace('_', ' '), fc.replace('_', ' '))))
    sc, sp = at_cli.get('seccion'), at_prov.get('seccion')
    if sc and sp and abs(sc - sp) > 1e-6 and fc == 'cable':
        out.append(('alta', 'Sección distinta: pedida %s mm², ofertada %s mm².' % (_num(sc), _num(sp))))
    tc, tp = at_cli.get('tipo_cable'), at_prov.get('tipo_cable')
    if tc and tp and tc != tp:
        extra = ''
        if tc == 'RZ1-K' and tp == 'H07Z1-K':
            extra = ' (H07Z1-K es de 450/750 V, no 0,6/1 kV)'
        out.append(('alta' if extra else 'media', 'Tipo de cable distinto: pedido %s, ofertado %s%s.' % (tc, tp, extra)))
    if at_cli.get('halogenos') == 'libre' and fp in ('cable', 'cable_datos', 'tubo', 'canal', 'bandeja'):
        hp, motivo = at_prov.get('halogenos'), at_prov.get('halogenos_motivo') or ''
        if hp == 'contiene':
            out.append(('alta', 'Se pide libre de halógenos y lo ofertado CONTIENE halógenos: %s.' % motivo))
        elif hp is None:
            out.append(('baja', 'Se pide libre de halógenos y no se ha podido confirmar en la descripción de la oferta: '
                                'revisar la ficha técnica.'))
    mc, mp = at_cli.get('material'), at_prov.get('material')
    if mc and mp and mc != mp:
        out.append(('alta', 'Material del conductor distinto: pedido %s, ofertado %s.' % (mc, mp)))
    dc, dp = at_cli.get('diametro'), at_prov.get('diametro')
    if dc and dp and dc != dp:
        out.append(('alta', 'Diámetro distinto: pedido Ø%d mm, ofertado Ø%d mm.' % (dc, dp)))
    ttc, ttp = at_cli.get('tipo_tubo') or set(), at_prov.get('tipo_tubo') or set()
    for a, b in (('corrugado', 'rigido'), ('rigido', 'corrugado'), ('corrugado', 'acero')):
        if a in ttc and b in ttp and a not in ttp:
            out.append(('media', 'Tubo %s pedido y ofertado %s.' % (a, 'rígido' if b == 'rigido' else b)))
    wc, wp = at_cli.get('potencia_w'), at_prov.get('potencia_w')
    if wc and wp and fc not in ('detector', 'modulo_fv', 'inversor') and not set(wc) & set(wp):
        dif = abs(wp[0] - wc[0]) / max(wc[0], 1)
        if dif > 0.1:
            out.append(('media', 'Potencia distinta: pedida %s W, ofertada %s W.' % (_num(wc[0]), _num(wp[0]))))
    lc, lp = at_cli.get('lumenes'), at_prov.get('lumenes')
    if lc and lp and max(lp) < min(lc) * 0.97:
        out.append(('media', 'Flujo luminoso inferior al pedido: %d lm ofertados frente a %d lm.' % (max(lp), min(lc))))
    kc, kp = at_cli.get('temp_color'), at_prov.get('temp_color')
    if kc and kp and kc != kp:
        out.append(('media', 'Temperatura de color distinta: pedida %d K, ofertada %d K.' % (kc, kp)))
    ipc, ipp = at_cli.get('ip'), at_prov.get('ip')
    if ipc and ipp:
        try:
            if int(ipp[0][:2]) < int(ipc[0][:2]):
                out.append(('media', 'Grado de protección inferior: pedido IP%s, ofertado IP%s.' % (ipc[0], ipp[0])))
        except ValueError:
            pass
    fc_, fp_ = at_cli.get('fases') or set(), at_prov.get('fases') or set()
    if fc_ and fp_ and not fc_ & fp_:
        out.append(('alta', 'Pedido %s y ofertado %s.' % ('/'.join(sorted(fc_)), '/'.join(sorted(fp_)))))
    ac, ap = at_cli.get('amperios'), at_prov.get('amperios')
    if ac and ap and not set(ac) & set(ap) and fc in ('magnetotermico', 'diferencial'):
        out.append(('alta', 'Intensidad distinta: pedida %s A, ofertada %s A.' % (ac, ap)))
    if fc == 'arqueta' and fp == 'tapa_arqueta':
        out.append(('media', 'Solo se oferta la TAPA, no la arqueta completa.'))
    oc, op = at_cli.get('optica'), at_prov.get('optica')
    if oc and op and oc != op:
        out.append(('alta', 'Óptica distinta: pedida "%s", ofertada "%s".' % (oc, op)))
    lc_, lp_ = at_cli.get('longitud_mm'), at_prov.get('longitud_mm')
    if lc_ and lp_ and abs(lc_ - lp_) > 1:
        out.append(('alta', 'Longitud distinta: pedida %s mm, ofertada %s mm.' % (_num(lc_), _num(lp_))))
    if at_cli.get('dali') and fp in ('downlight', 'luminaria', 'pantalla_estanca', 'proyector') and not at_prov.get('dali'):
        out.append(('baja', 'Se pide regulable DALI y la oferta no lo indica.'))
    return out
