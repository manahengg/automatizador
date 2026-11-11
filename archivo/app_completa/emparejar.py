"""Casar las líneas de cada oferta de proveedor con los MATERIALES del presupuesto del cliente.

Unidad de comparación = material (una partida del cliente puede dar varios: 4x35+1x16 -> 1x35 y 1x16).
Para cada pareja (línea, material) se calcula una puntuación con:
    código igual/prefijo · familia · atributos técnicos · texto · cantidad · planta/capítulo · equivalencias aprendidas
Asignación:
    1. Línea PRINCIPAL de cada material: mejor pareja global, una línea por material (umbral UMBRAL_PRINCIPAL).
    2. COMPLEMENTOS: líneas sobrantes que encajan con un material ya cubierto (tapa de bandeja, placas, bases de un
       puesto de trabajo, módulos de un gestor...) o que están entre dos líneas del mismo material en la oferta.
    3. Cánones RAEE: van con la línea a la que acompañan.
    4. El resto queda "sin casar" (el proveedor oferta algo que no está en el presupuesto o no se ha reconocido).
Las correcciones manuales (fijadas por la persona) mandan siempre.
"""
import collections
import dataclasses
import re

from . import electrico as E
from .modelo import Capitulo

UMBRAL_PRINCIPAL = 0.42
UMBRAL_COMPLEMENTO = 0.40
UMBRAL_SEGURO = 0.75
PLANTAS = ('sotano', 'baja', 'primera', 'segunda', 'tercera', 'cuarta', 'cubierta', 'cripta', 'nave', 'entreplanta')
STOP = {'de', 'del', 'la', 'las', 'el', 'los', 'y', 'e', 'en', 'con', 'para', 'por', 'a', 'un', 'una', 'o', 'ud', 'uds',
        'segun', 'incluido', 'incluida', 'incluso', 'suministro', 'instalado', 'instalada', 'totalmente', 'equivalente',
        'tipo', 'marca', 'modelo', 'mm', 'mm2', 'm', 'al', 'se', 'su', 'sus', 'que', 'como', 'p', 'pp', 'parte',
        'proporcional', 'montaje', 'montado', 'conexionado', 'colocacion', 'medios', 'auxiliares', 'material', 'pequeno',
        'cpr', 'color', 'gris', 'blanco', 'negro', 'reglamento', 'ue', 'marcado', 'ce', 'replanteo', 'accesorios'}


@dataclasses.dataclass
class Material:
    id: str                 # '12' o '12a'
    n: int                  # nº de partida en la licitación (orden)
    partida: object
    ruta: list              # títulos de capítulos
    ruta_codigos: list
    descripcion: str        # material interpretado
    cantidad: float
    unidad: str
    factor: float
    nota: str
    atributos: dict
    primero: bool           # primer material de su partida (lleva los datos de la partida en el Excel)
    n_mats: int = 1
    tokens: set = dataclasses.field(default_factory=set)
    plantas: set = dataclasses.field(default_factory=set)
    alertas_cliente: list = dataclasses.field(default_factory=list)

    @property
    def codigo(self):
        return self.partida.codigo or ''

    @property
    def clave(self):
        return E.clave_material(self.atributos)


@dataclasses.dataclass
class Linea:
    proveedor: str
    i: int                  # posición en la oferta
    partida: object
    seccion: str
    atributos: dict
    tokens: set
    plantas: set

    @property
    def referencia(self):
        return self.partida.referencia or ''

    @property
    def es_accesorio(self):
        """Accesorio que se vende aparte de su artículo (tapa, perfil, difusor, driver, junta, alimentación...)."""
        return es_accesorio_texto(self.partida.descripcion)

    @property
    def es_canon(self):
        return self.partida.canon_de is not None or self.atributos.get('familia') == 'canon'


@dataclasses.dataclass
class Asignacion:
    material_id: str
    linea: Linea
    tipo: str               # 'principal' | 'complemento' | 'canon'
    puntuacion: float
    origen: str = 'auto'    # 'auto' | 'manual' | 'aprendido'


SINONIMOS = {'tapa': 'cubierta', 'conmutado': 'conmutador', 'schuco': 'schuko', 'corrug': 'corrugado',
             'downl': 'downlight', 'fotov': 'fotovoltaico', 'fotovoltaicos': 'fotovoltaico', 'paneles': 'modulo',
             'interr': 'interruptor', 'emergencias': 'emergencia'}


RE_ACCESORIO = re.compile(r'(^|[^a-z])(acc\.?|accesorio|lampacc|perfil|difusor|driver|drv\d|drv\b|tapa final|end cover|joint|'
                          r'union|kit (de )?(montaje|suspension)|soporte|alimentacion (dcha|izq|derecha|izquierda)|'
                          r'cable de suspension|steel cable|embellecedor|marco de empotrar|rejilla)')


def _pegado(texto):
    """Texto sin espacios ni signos, para buscar nombres de modelo dentro de palabras pegadas por el OCR."""
    return re.sub(r'[^a-z0-9]', '', E.norm(texto))


def _es_pegada(palabra):
    """Palabra con varias palabras pegadas por el OCR ('lum.techoplatg3600x6003200830prism'), no un código de artículo
    ('lampf2sf500lo208300'): larga y con al menos dos tramos de 4+ letras."""
    return len(palabra) >= 14 and len(re.findall(r'[a-z]{4,}', palabra)) >= 2


ACCESORIOS_PEGADOS = ('acc.', 'accesorio', 'lampacc', 'perfilempotr', 'perfil', 'difusor', 'driver', 'drv', 'tapafinal',
                      'endcover', 'joint', 'alimentaciondcha', 'alimentacionizq', 'steelcable', 'soporte',
                      'embellecedor', 'rejilla')


def es_accesorio_texto(texto):
    """Se mira el principio de la descripción ('FIL45 ACC. ...', 'PERFIL ...'), donde se dice qué es el artículo.
    También sin espacios, porque el OCR puede pegar las palabras ('ALIMENTACIONDCHA.P/CRL', 'TAPAFINALPARACARRIL')."""
    n = E.norm(texto)
    if RE_ACCESORIO.search(n[:25]):
        return True
    pegado = re.sub(r'[^a-z0-9.]', '', n)[:22]
    return any(p in pegado for p in ACCESORIOS_PEGADOS)


def _tokens(texto):
    n = E.norm(texto)
    n = re.sub(r'[^a-z0-9.,/+-]+', ' ', n)
    # el OCR pega palabras ('downl.kombic 100red.1500ip43'): se separa también por puntos y cambios letra/número
    n = re.sub(r'(?<=[a-z])\.(?=[a-z0-9])|(?<=\d)\.(?=[a-z])', ' ', n)
    n = re.sub(r'(?<=[a-z]{2})(?=\d)|(?<=\d)(?=[a-z]{2})', ' ', n)
    out = set()
    for t in n.split():
        t = t.strip('.,')
        if len(t) > 1 and t not in STOP:
            out.add(SINONIMOS.get(t, t))
    return out


def _plantas(texto):
    n = E.norm(texto)
    return {p for p in PLANTAS if re.search(r'\b%s\b' % p, n)}


def _cod(x):
    return re.sub(r'[^A-Z0-9]', '', str(x or '').upper())


def materiales_cliente(doc):
    out, n = [], 0

    def rec(cap, ruta, codigos):
        nonlocal n
        r, c = ruta + [cap.titulo], codigos + [cap.codigo or '']
        for h in cap.hijos:
            if isinstance(h, Capitulo):
                rec(h, r, c)
                continue
            n += 1
            mats = E.materiales(h)
            alertas = E.revisar_partida(h)
            for k, m in enumerate(mats):
                texto = (h.resumen or '') + ' ' + (h.descripcion or '')[:300] + ' ' + m['descripcion']
                out.append(Material(id='%d%s' % (n, m['sufijo']), n=n, partida=h, ruta=r, ruta_codigos=c,
                                    descripcion=m['descripcion'], cantidad=m['cantidad'], unidad=m['unidad'],
                                    factor=m['factor'], nota=m['nota'], atributos=m['atributos'], primero=(k == 0),
                                    n_mats=len(mats), tokens=_tokens(texto), plantas=_plantas(' '.join(r)),
                                    alertas_cliente=alertas if k == 0 else []))
    for cap in doc.capitulos:
        rec(cap, [], [])
    return out


def clave_capitulo(codigos, titulos):
    """Identificador estable de un capítulo: la ruta de códigos (o títulos si no tiene código)."""
    return ' / '.join((c or t or '').strip() for c, t in zip(codigos, titulos))


def clave_material_cap(m):
    return clave_capitulo(m.ruta_codigos, m.ruta)


def arbol_capitulos(doc):
    """Árbol de capítulos del presupuesto del cliente para elegir cuáles hacemos.
    [{'clave', 'codigo', 'titulo', 'nivel', 'partidas' (propias y de subcapítulos), 'importe', 'hijos': [...]}]"""
    def nodo(cap, codigos, titulos, nivel):
        cods, tits = codigos + [cap.codigo or ''], titulos + [cap.titulo]
        hijos, n, imp = [], 0, 0.0
        for h in cap.hijos:
            if isinstance(h, Capitulo):
                x = nodo(h, cods, tits, nivel + 1)
                hijos.append(x)
                n += x['partidas']
                imp += x['importe']
            else:
                n += 1
                imp += h.importe
        return {'clave': clave_capitulo(cods, tits), 'codigo': (cap.codigo or '').rstrip('#'), 'titulo': cap.titulo,
                'nivel': nivel, 'partidas': n, 'importe': round(imp, 2), 'hijos': hijos,
                'propias': sum(1 for h in cap.hijos if not isinstance(h, Capitulo))}
    return [nodo(c, [], [], 0) for c in doc.capitulos]


def lineas_oferta(doc, proveedor):
    out = []
    for cap in doc.capitulos:
        for p in cap.partidas():
            l = Linea(proveedor=proveedor, i=len(out), partida=p, seccion=cap.titulo,
                      atributos=E.atributos(p.descripcion), tokens=_tokens(p.descripcion), plantas=_plantas(cap.titulo))
            # texto pegado por el OCR ('LUM.TECHOPLATG3600X6003200830PRISM'): se guarda para buscar dentro
            l.pegado = _pegado(p.descripcion) if any(_es_pegada(t) for t in E.norm(p.descripcion).split()) else ''
            l.gramas = _gramas(p.descripcion[:70])
            out.append(l)
    return out


# ------------------------------------------------------------------------------------------- puntuación
_IDF, _IDF_MAX = {}, 1.0
_IDF_G, _IDF_G_MAX = {}, 1.0


def _gramas(texto, n=4):
    """Trozos de 4 caracteres del texto SIN espacios: 'KOMBIC70SF1500' y 'KOMBIC 70 SF 1500' comparten casi todos,
    así que se reconocen aunque el OCR pegue o separe las palabras."""
    t = re.sub(r'[^a-z0-9]', '', E.norm(texto))
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def sim_gramas(l, m):
    """0..1: cuánto del texto de la línea (pesado por rareza en el presupuesto) aparece en el título del material."""
    gl, gm = getattr(l, 'gramas', None), getattr(m, 'gramas', None)
    if not gl or not gm:
        return 0.0
    total = sum(_IDF_G.get(g, _IDF_G_MAX) for g in gl)
    return sum(_IDF_G.get(g, _IDF_G_MAX) for g in gl & gm) / total if total else 0.0


def preparar_idf(materiales):
    """Rareza de cada palabra en el presupuesto del cliente (log de N / nº de materiales que la contienen)."""
    global _IDF, _IDF_MAX
    import math
    df = collections.Counter(t for m in materiales for t in m.tokens)
    n = max(1, len(materiales))
    _IDF = {t: math.log(1 + n / c) for t, c in df.items()}
    _IDF_MAX = math.log(1 + n)
    global _IDF_G, _IDF_G_MAX
    for m in materiales:
        if not hasattr(m, 'gramas'):
            m.gramas = _gramas((m.partida.resumen or m.descripcion[:120]) + ' ' + (m.codigo or ''))
    dg = collections.Counter(g for m in materiales for g in m.gramas)
    _IDF_G = {g: math.log(1 + n / c) for g, c in dg.items()}
    _IDF_G_MAX = math.log(1 + n)


_SEM = {}                     # parecido de significado línea x material (semantica.py), si el modelo está disponible
PESO_SEM = 0.25


def preparar_semantica(materiales, lineas):
    """Calcula el parecido de significado de cada línea con cada material (fase 1). Sin modelo, no hace nada."""
    _SEM.clear()
    try:
        from . import semantica as SE
        if not materiales or not lineas or not SE.disponible():
            return
        vm = SE.vectores([SE.texto_material(m) for m in materiales])
        vl = SE.vectores([SE.texto_linea(l) for l in lineas])
        if vm is None or vl is None:
            return
        import numpy as np
        C = vl @ vm.T
        _SEM.update(C=C, med=np.median(C, axis=1), fila={l.i: k for k, l in enumerate(lineas)},
                    col={m.id: k for k, m in enumerate(materiales)})
    except Exception:
        _SEM.clear()


def sim_semantica(l, m):
    """(parecido, parecido relativo 0..1) o None: cuánto más se parece la línea a este material que a la media."""
    if not _SEM:
        return None
    r, c = _SEM['fila'].get(l.i), _SEM['col'].get(m.id)
    if r is None or c is None:
        return None
    v = float(_SEM['C'][r, c])
    return v, max(0.0, min(1.0, (v - float(_SEM['med'][r])) / 0.10))


_MEM = {}                     # memoria de decisiones aprendidas para esta oferta (aprendizaje.py, fase 2)


def preparar_memoria(materiales, lineas):
    _MEM.clear()
    try:
        from . import aprendizaje as A
        x = A.preparar_memoria(materiales, lineas, lineas[0].proveedor if lineas else '')
        if x:
            _MEM['x'] = x
    except Exception:
        _MEM.clear()


def bonificacion_aprendida(l, m):
    if not _MEM:
        return 0.0, None
    from . import aprendizaje as A
    return A.bonificacion(_MEM['x'], l, m)


def puntuar(l, m, conocidas=None, memoria=True):
    """0..~1.5. Cuanto más alto, más seguro que la línea l es el material m."""
    s = 0.0
    a, b = _cod(l.referencia), _cod(m.codigo)
    if len(a) >= 4 and len(b) >= 4:
        if a == b:
            s += 0.6
        elif (a.startswith(b) or b.startswith(a)) and min(len(a), len(b)) >= 5:
            s += 0.35
    fl, fm = l.atributos.get('familia'), m.atributos.get('familia')
    comp = E.compatibles(fl, fm)
    if comp is True:
        s += (0.3 if fl == fm else 0.12) if fl not in ('servicio', 'reinstalacion', 'ayudas') else 0.0
    elif comp is False:
        s -= 0.45
    al, am = l.atributos, m.atributos
    for clave, peso, castigo in (('seccion', 0.3, 0.5), ('diametro', 0.25, 0.15), ('tipo_cable', 0.08, 0.06),
                                 ('optica', 0.2, 0.45), ('longitud_mm', 0.15, 0.4), ('posicion', 0.12, 0.3),
                                 ('temp_color', 0.05, 0.1), ('material', 0.05, 0.3), ('ip', 0.1, 0.1)):
        x, y = al.get(clave), am.get(clave)
        if x is not None and y is not None:
            s += peso if x == y else -castigo
    for clave in ('potencia_w', 'lumenes', 'amperios'):
        x, y = al.get(clave), am.get(clave)
        if x and y:
            s += 0.1 if set(x) & set(y) else (-0.05 if clave != 'potencia_w' else -0.08)
    tt = al.get('tipo_tubo') or set()
    if tt and am.get('tipo_tubo'):
        s += 0.05 if tt & am['tipo_tubo'] else -0.03
    if l.tokens and m.tokens:
        comun = l.tokens & m.tokens
        if getattr(l, 'pegado', ''):
            # palabras del presupuesto que aparecen DENTRO del texto pegado de la línea
            extra = {t for t in m.tokens - comun if len(t) >= 4 and not t.isdigit() and _IDF.get(t, 0) > 1.5
                     and t in l.pegado}
            comun = comun | extra
        if _IDF:
            # palabras raras en el presupuesto (nombres de modelo: KOMBIC, FIL45...) pesan mucho más que las comunes
            peso_l = sum(_IDF.get(t, _IDF_MAX) for t in l.tokens) or 1.0
            s += 0.45 * sum(_IDF.get(t, _IDF_MAX) for t in comun) / peso_l
        else:
            n_c = len(comun)
            s += 0.3 * (0.6 * n_c / max(1, min(len(l.tokens), 12)) + 0.4 * n_c / max(1, len(l.tokens | m.tokens)) * 3)
        # parecido por trozos de caracteres (robusto a palabras pegadas o partidas por el OCR)
        s += 0.35 * sim_gramas(l, m)
        # números de modelo (3+ cifras: 1400, 1960, 35558...): coincidir suma; si los hay en ambos y ninguno coincide, resta
        nl = {t for t in l.tokens if t.isdigit() and len(t) >= 3}
        nm = {t for t in m.tokens if t.isdigit() and len(t) >= 3}
        if nl and nm:
            s += 0.12 * len(nl & nm) / len(nl) if nl & nm else -0.12
    q1, q2 = l.partida.cantidad or 0, m.cantidad or 0
    if q1 and q2 and (m.unidad or '').lower().rstrip('.') in ('m', 'ml'):
        lm = _metros_pieza(l.partida.descripcion)       # rollos / piezas de N m frente a metros del cliente
        if lm and abs(q1 * lm / q2 - 1) < abs(q1 / q2 - 1):
            q1 = q1 * lm
    if q1 and q2:
        r = q1 / q2
        if 0.995 <= r <= 1.005:
            s += 0.2 + (0.05 if fl and fl == fm else 0)
        elif 0.97 <= r <= 1.1:
            s += 0.1 + (0.03 if fl and fl == fm else 0)
        elif 0.85 <= r <= 1.35:
            s += 0.05
        elif r < 0.25 or r > 4:
            s -= 0.04
    if fl in ('servicio', 'reinstalacion', 'ayudas') and not (len(a) >= 4 and a == b):
        s -= 0.15                      # trámites y servicios: solo si el texto coincide de verdad
    if l.partida.opcional:
        s -= 0.05
    if l.partida.precio is None:
        s -= 0.06
    if l.plantas and m.plantas:
        s += 0.2 if l.plantas & m.plantas else -0.35
    sem = sim_semantica(l, m)
    if sem and s >= 0.35:
        # el texto dice lo mismo aunque con otras palabras: desempata entre candidatos que ya se parecen por reglas,
        # pero no crea parejas de la nada (sin esto casaba 'kit ventiladores rack' como complemento de un enchufe)
        s += PESO_SEM * sem[1]
    if conocidas:
        k = conocidas.get((l.proveedor.lower(), _cod(l.referencia) or E.norm(l.partida.descripcion)[:60]))
        if k and (k == m.clave or k == ('cli:' + _cod(m.codigo)) or k == 'desc:' + E.norm(m.partida.resumen or m.descripcion)[:60]):
            s += 0.6
    if memoria and _MEM:
        s += bonificacion_aprendida(l, m)[0]      # decisiones parecidas de las personas (fase 2)
    return s


def emparejar(materiales, lineas, manuales=None, conocidas=None):
    """Devuelve (asignaciones: list[Asignacion], sin_casar: list[Linea]).

    manuales: {nº línea: material_id | None}  -> fijado por la persona (None = no casar)."""
    manuales = manuales or {}
    por_id = {m.id: m for m in materiales}
    asign, usadas, cubiertos = [], set(), set()
    for li, mid in manuales.items():
        l = next((x for x in lineas if x.i == li), None)
        if l is None:
            continue
        usadas.add(li)
        if mid and mid in por_id:
            tipo = 'canon' if l.es_canon else ('principal' if mid not in cubiertos else 'complemento')
            asign.append(Asignacion(mid, l, tipo, 1.0, 'manual'))
            cubiertos.add(mid)
    normales = [l for l in lineas if l.i not in usadas and not l.es_canon]
    preparar_idf(materiales)
    preparar_semantica(materiales, lineas)
    preparar_memoria(materiales, lineas)
    puntos = {}
    for l in normales:
        fila = []
        for m in materiales:
            fila.append((puntuar(l, m, conocidas), m.id))
        fila.sort(reverse=True)
        puntos[l.i] = fila[:8]
    # 1) principales: mejor pareja global
    cand = sorted(((sc, l.i, mid) for l in normales for sc, mid in puntos[l.i]
                   if sc >= UMBRAL_PRINCIPAL and _puede_ser_principal(l, por_id[mid], sc)), reverse=True)
    por_i = {l.i: l for l in lineas}
    hecho = set()
    for sc, li, mid in cand:
        if li in hecho or mid in cubiertos:
            continue
        asign.append(Asignacion(mid, por_i[li], 'principal', sc))
        hecho.add(li)
        cubiertos.add(mid)
    # 1b) parejas "mejor mutua" algo por debajo del umbral si son de la misma familia
    mejor_linea = {}
    for l in normales:
        if l.i in hecho:
            continue
        for sc, mid in puntos[l.i][:1]:
            if mid not in cubiertos and sc > mejor_linea.get(mid, (-9, None))[0]:
                mejor_linea[mid] = (sc, l.i)
    for mid, (sc, li) in mejor_linea.items():
        l = por_i[li]
        mm_ = por_id[mid]
        misma_fam = l.atributos.get('familia') and l.atributos.get('familia') == mm_.atributos.get('familia')
        misma_cant = bool(l.partida.cantidad and mm_.cantidad) and abs(l.partida.cantidad / mm_.cantidad - 1) < 0.005
        if sc >= (0.28 if misma_fam else 0.18) and not l.es_accesorio \
                and (misma_fam or (misma_cant and sim_gramas(l, mm_) >= 0.2)) \
                and li not in hecho and mid not in cubiertos:
            asign.append(Asignacion(mid, l, 'principal', sc))
            hecho.add(li)
            cubiertos.add(mid)
    # 1c) mejora local: las líneas de un mismo bloque de la oferta suelen ir a la misma partida
    _mejorar(asign, materiales, lineas, normales, puntos, por_id, hecho, cubiertos, conocidas)
    # 2) complementos
    partida_de = {m.id: m.n for m in materiales}
    resto = [l for l in normales if l.i not in hecho]
    mat_por_linea = {a.linea.i: a.material_id for a in asign}
    for l in resto:
        if l.es_accesorio and not (puntos[l.i] and puntos[l.i][0][0] >= 0.6):
            continue                                    # los accesorios se colocan en el paso 2b
        mejor = next(((sc, mid) for sc, mid in puntos[l.i] if mid in cubiertos), None)
        prev = next((mat_por_linea[j] for j in range(l.i - 1, max(-1, l.i - 6), -1) if j in mat_por_linea), None)
        sig = next((mat_por_linea[j] for j in range(l.i + 1, l.i + 6) if j in mat_por_linea), None)
        elegido = None
        fam = l.atributos.get('familia')
        if prev and sig and partida_de.get(prev) == partida_de.get(sig):
            # entre dos líneas de la misma partida: va con ellas si es compatible (bases y placas de un puesto)
            cand = [x for x in (prev, sig) if E.compatibles(fam, por_id[x].atributos.get('familia'))
                    and not _choca(por_id[x], l)]
            if cand:
                elegido = (puntuar(l, por_id[cand[0]], conocidas), cand[0])
        if not elegido and mejor and (mejor[0] >= UMBRAL_COMPLEMENTO or
                      mejor[0] >= 0.33 and fam and fam == por_id[mejor[1]].atributos.get('familia')) \
                and not _choca(por_id[mejor[1]], l):
            elegido = mejor
        if not elegido:
            # accesorio que sigue a su artículo en la oferta (tapa tras la bandeja, protecciones tras el inversor...)
            for j in range(l.i - 1, max(-1, l.i - 9), -1):
                if j in mat_por_linea:
                    mid = mat_por_linea[j]
                    fm = por_id[mid].atributos.get('familia')
                    sc = puntuar(l, por_id[mid], conocidas)
                    if ((E.compatibles(fam, fm) and sc >= 0.1) or (j == l.i - 1 and sc >= 0.2)) \
                            and not _choca(por_id[mid], l):
                        elegido = (sc, mid)
                    break
        if not elegido and prev and sig and partida_de.get(prev) == partida_de.get(sig):
            sc = next((sc for sc, mid in puntos[l.i] if mid == prev), None)
            sc = sc if sc is not None else puntuar(l, por_id[prev], conocidas)
            if sc >= 0.1:
                elegido = (sc, prev)
        if elegido:
            asign.append(Asignacion(elegido[1], l, 'complemento', elegido[0]))
            mat_por_linea[l.i] = elegido[1]
            hecho.add(l.i)
    # 2b) accesorios sueltos: van con el artículo cercano (hasta 8 líneas antes) con el que comparten nombre de modelo
    #     (FIL45, FINE LED, STORMBELL...); si no comparten nada, con el inmediatamente anterior
    for l in normales:
        if l.i in hecho or not l.es_accesorio:
            continue
        mejor_acc, mejor_peso = None, 0.0
        for j in range(l.i - 1, max(-1, l.i - 9), -1):
            if j not in mat_por_linea or por_i[j].es_accesorio:
                continue                        # se compara con artículos principales, no con otros accesorios
            otra = por_i[j]
            raras = {t for t in (l.tokens & otra.tokens) if _IDF.get(t, _IDF_MAX) > 1.5 and not t.isdigit()}
            peso = sum(_IDF.get(t, _IDF_MAX) for t in raras)
            if getattr(l, 'pegado', ''):
                peso += sum(_IDF.get(t, 0) for t in otra.tokens if len(t) >= 4 and t in l.pegado and not t.isdigit())
            peso *= max(0.3, 1 - 0.1 * (l.i - j - 1))        # a igualdad, el artículo más cercano en la oferta
            if peso > mejor_peso:
                mejor_acc, mejor_peso = mat_por_linea[j], peso
        if mejor_acc is None:                    # sin nada en común: con el artículo principal más cercano anterior
            mejor_acc = next((mat_por_linea[j] for j in range(l.i - 1, max(-1, l.i - 9), -1)
                              if j in mat_por_linea and not por_i[j].es_accesorio), None)
        if mejor_acc and not _choca(por_id[mejor_acc], l, ignorar_familia=True):
            asign.append(Asignacion(mejor_acc, l, 'complemento', puntuar(l, por_id[mejor_acc], conocidas)))
            mat_por_linea[l.i] = mejor_acc
            hecho.add(l.i)
    # 2c) por posición: una línea suelta entre dos líneas principales casadas con las partidas n1 y n2, si entre ellas hay
    #     UNA sola partida sin oferta con la misma cantidad (p. ej. el OCR perdió la descripción: '.234')
    principales = {a.linea.i: por_id[a.material_id] for a in asign if a.tipo == 'principal'}
    for l in normales:
        if l.i in hecho or not l.partida.cantidad or l.partida.precio is None:
            continue
        ant = next((principales[j] for j in range(l.i - 1, -1, -1) if j in principales), None)
        sig = next((principales[j] for j in range(l.i + 1, len(lineas)) if j in principales), None)
        if not ant or not sig or ant.n >= sig.n:
            continue
        huecos = [m for m in materiales if ant.n < m.n < sig.n and m.id not in cubiertos and m.cantidad
                  and abs(m.cantidad / l.partida.cantidad - 1) < 0.005]
        if len(huecos) == 1:
            a = Asignacion(huecos[0].id, l, 'principal', 0.15)
            a.por_posicion = True
            asign.append(a)
            cubiertos.add(huecos[0].id)
            hecho.add(l.i)
            mat_por_linea[l.i] = huecos[0].id
    # 3) cánones con su línea
    for l in lineas:
        if l.i in usadas or not l.es_canon:
            continue
        madre = l.partida.canon_de
        j = next((x.i for x in lineas if x.partida is madre), None)
        if j is None:
            j = next((k for k in range(l.i - 1, -1, -1) if k in mat_por_linea), None)
        if j is not None and j in mat_por_linea:
            asign.append(Asignacion(mat_por_linea[j], l, 'canon', 1.0))
            hecho.add(l.i)
    # lo que una persona DESCASÓ (misma línea del mismo proveedor) no se vuelve a casar solo en ninguna pasada
    vetadas = {a.linea.i for a in asign if a.origen != 'manual' and vetado(a.linea, por_id.get(a.material_id))}
    if vetadas:
        asign = [a for a in asign if a.linea.i not in vetadas]
        hecho -= vetadas
    sin = [l for l in lineas if l.i not in hecho and not (l.i in usadas and manuales.get(l.i))]
    return asign, sin, puntos


def vetado(l, m):
    """La pareja fue descasada por una persona (decisión parecida >= 97 % del mismo proveedor)."""
    if not _MEM or m is None:
        return False
    x = _MEM['x']['pares'].get((l.i, m.id))
    return bool(x) and x[1] < 0 and x[0] >= 0.97 and (x[2]['proveedor'] or '').lower() == _MEM['x']['proveedor']


def _parecida(a, b):
    return bool(a and b) and 0.8 <= a / b <= 1.25


def _puede_ser_principal(l, m, sc=0.0):
    """Un accesorio (tapa, perfil, driver...) solo es la línea principal de una partida que también es un accesorio, o
    cuando casa claramente con ella (p. ej. una partida 'Alimentación trifásica derecha' del propio presupuesto)."""
    return not l.es_accesorio or sc >= 0.6 or es_accesorio_texto((m.partida.resumen or '') + ' ' + m.descripcion)


def _choca(m, l, ignorar_familia=False):
    """True si la línea contradice claramente al material (no puede ser un accesorio suyo).
    ignorar_familia: para accesorios (el cable de suspensión de una luminaria es un cable, pero va con ella)."""
    return any(g == 'alta' and not (ignorar_familia and 'otro tipo' in t) for g, t in E.comparar(m.atributos, l.atributos))


def _mejorar(asign, materiales, lineas, normales, puntos, por_id, hecho, cubiertos, conocidas, vueltas=3):
    """Busqueda local sobre las líneas PRINCIPALES: mover una línea a un material sin cubrir o intercambiar dos,
    si mejora puntuación + 'bono de bloque' (otra línea cercana en la oferta va a la misma partida del cliente)."""
    BONO = 0.12
    principales = {a.linea.i: a for a in asign if a.tipo == 'principal' and a.origen == 'auto'}

    def mapa():
        return {a.linea.i: por_id[a.material_id].n for a in asign if a.tipo == 'principal'}

    def bono(li, n, m_actual, excluir=()):
        return BONO if any(m_actual.get(j) == n for j in range(li - 6, li + 7) if j != li and j not in excluir) else 0.0

    candidatos = {l.i: [(sc, mid) for sc, mid in puntos[l.i] if sc >= 0.2 and _puede_ser_principal(l, por_id[mid], sc)]
                  for l in normales}
    for _ in range(vueltas):
        cambio = False
        mm = mapa()
        # mover a material sin cubrir
        for l in normales:
            actual = principales.get(l.i)
            val_act = (actual.puntuacion + bono(l.i, por_id[actual.material_id].n, mm)) if actual else 0.0
            for sc, mid in candidatos[l.i]:
                if mid in cubiertos:
                    continue
                v = sc + bono(l.i, por_id[mid].n, mm)
                if v >= UMBRAL_PRINCIPAL - 0.08 and v > val_act + 0.05:
                    if actual:
                        cubiertos.discard(actual.material_id)
                        actual.material_id, actual.puntuacion = mid, sc
                    else:
                        a = Asignacion(mid, l, 'principal', sc)
                        asign.append(a)
                        principales[l.i] = a
                        hecho.add(l.i)
                    cubiertos.add(mid)
                    cambio = True
                    mm = mapa()
                    break
        # intercambios entre dos principales
        lista = list(principales.values())
        for x in range(len(lista)):
            for y in range(x + 1, len(lista)):
                a, b = lista[x], lista[y]
                ma, mb = por_id[a.material_id], por_id[b.material_id]
                if ma.atributos.get('familia') != mb.atributos.get('familia'):
                    continue
                sa = dict(candidatos[a.linea.i]).get  # noqa
                pab = puntuar(a.linea, mb, conocidas)
                pba = puntuar(b.linea, ma, conocidas)
                # el bono no puede venir de las propias líneas que se intercambian (si no, cambiar siempre "compensa")
                ex = (a.linea.i, b.linea.i)
                antes = a.puntuacion + b.puntuacion + bono(a.linea.i, ma.n, mm, ex) + bono(b.linea.i, mb.n, mm, ex)
                despues = pab + pba + bono(a.linea.i, mb.n, mm, ex) + bono(b.linea.i, ma.n, mm, ex)
                if despues > antes + 0.05 and min(pab, pba) >= UMBRAL_PRINCIPAL - 0.15:
                    a.material_id, b.material_id = mb.id, ma.id
                    a.puntuacion, b.puntuacion = pab, pba
                    cambio = True
                    mm = mapa()
        if not cambio:
            break


# ------------------------------------------------------------------------------------------- resultado
@dataclasses.dataclass
class Oferta:
    """Lo que un proveedor oferta para un material: principal + complementos + cánones."""
    principal: Linea
    extras: list
    puntuacion: float
    origen: str
    precio: float = None          # € por unidad de material (incluye complementos y cánones)
    cant_prov: float = None
    importe: float = None         # precio x cantidad del material (cantidad del cliente interpretada)
    importe_ofertado: float = 0.0
    cant_necesaria: float = None  # si se calcula una cantidad propia para este proveedor (p. ej. nº de módulos FV)
    alertas: list = dataclasses.field(default_factory=list)
    codigos: str = ''
    descripcion: str = ''
    confianza: float = None       # probabilidad de acierto según el modelo entrenado con las decisiones (fase 2)
    aprendido: str = None         # explicación si se ha aplicado algo aprendido

    @property
    def estado(self):
        if self.origen == 'manual':
            return 'manual'
        if any(g == 'alta' for g, _ in self.alertas):
            return 'revisar'
        if self.confianza is not None:          # con el modelo entrenado manda su probabilidad
            return 'seguro' if self.confianza >= 0.8 or (self.aprendido and self.origen == 'aprendido') else 'revisar'
        if self.aprendido and self.origen == 'aprendido':
            return 'seguro'
        return 'revisar' if self.puntuacion < UMBRAL_SEGURO else 'seguro'


def construir_ofertas(materiales, asignaciones):
    """{material_id: Oferta} para un proveedor."""
    por_mat = {}
    for a in asignaciones:
        por_mat.setdefault(a.material_id, []).append(a)
    mats = {m.id: m for m in materiales}
    out = {}
    for mid, lista in por_mat.items():
        m = mats[mid]
        lista.sort(key=lambda a: (a.tipo != 'principal', -a.puntuacion))
        pri = lista[0]
        if pri.tipo == 'canon':
            continue
        # principal = la línea de la misma familia que el material con más importe (la bandeja, no su tapa)
        fam_m = m.atributos.get('familia')
        mismas = [a for a in lista if a.tipo != 'canon' and a.linea.atributos.get('familia') == fam_m
                  and a.linea.partida.precio is not None and not a.linea.partida.opcional
                  and _parecida(a.linea.partida.cantidad, pri.linea.partida.cantidad)]
        if len(mismas) > 1 and pri.origen != 'manual':
            pri = max(mismas, key=lambda a: a.linea.partida.importe_exacto)
            lista.remove(pri)
            lista.insert(0, pri)
        ppal = pri.linea
        extras = [a.linea for a in lista[1:]]
        o = Oferta(principal=ppal, extras=extras, puntuacion=pri.puntuacion,
                   origen='manual' if any(a.origen == 'manual' for a in lista) else pri.origen)
        validas = [ppal] + [x for x in extras if not x.partida.opcional]
        cant = ppal.partida.cantidad or 0
        suma = sum(x.partida.importe_exacto for x in validas if x.partida.precio is not None and x.partida.cantidad)
        sueltas = sum(x.partida.precio for x in validas if x.partida.precio is not None and not x.partida.cantidad
                      and x is not ppal)
        o.importe_ofertado = round(suma, 2)
        # material en metros y proveedor que vende piezas de N m (rollo de 5 m, carril de 2 m): se pasa a metros
        nota_metros = None
        if (m.unidad or '').lower().rstrip('.') in ('m', 'ml') and m.cantidad and cant:
            piezas = [(x, _metros_pieza(x.partida.descripcion)) for x in validas
                      if not x.es_accesorio and x.partida.cantidad]
            piezas = [(x, lm) for x, lm in piezas if lm]
            if piezas:
                metros = sum(x.partida.cantidad * lm for x, lm in piezas)
                if abs(metros - m.cantidad) < abs(cant - m.cantidad):
                    nota_metros = ' + '.join('%s x %s m' % (E._num(x.partida.cantidad), E._num(lm)) for x, lm in piezas)
                    cant = metros
        if ppal.partida.precio is not None:
            if cant:
                o.precio = suma / cant + sueltas
            else:
                o.precio = ppal.partida.precio + sueltas
            o.cant_prov = cant
            o.importe = round(o.precio * (m.cantidad or 0), 2)
        if nota_metros:
            o.alertas.append(('baja', 'Se oferta en piezas (%s = %s m): el unitario se ha pasado a €/m.' % (
                nota_metros, E._num(cant))))
        # lo aprendido de las personas y la confianza del modelo entrenado (fase 2)
        bono, porque = bonificacion_aprendida(ppal, m)
        if porque and bono > 0:
            o.aprendido = porque
            if o.origen == 'auto':
                o.origen = 'aprendido'
        elif porque:
            o.aprendido = porque
        try:
            from . import aprendizaje as A
            o.confianza = A.probabilidad(A.rasgos(ppal, m))
        except Exception:
            o.confianza = None
        o.codigos = ' + '.join(dict.fromkeys(x.referencia or '(s/c)' for x in [ppal] + extras if not x.es_canon))
        o.descripcion = ppal.partida.descripcion + (' (+%d líneas: %s)' % (
            len(extras), '; '.join(x.partida.descripcion[:40] for x in extras)) if extras else '')
        for g, t in E.comparar(m.atributos, ppal.atributos):
            o.alertas.append((g, t))
        if ppal.partida.opcional:
            o.alertas.append(('media', 'La línea está marcada como OPCIONAL en la oferta.'))
        dif_modelo = _numeros_distintos(m.partida.resumen or m.descripcion, ppal.partida.descripcion)
        if dif_modelo:
            o.alertas.append(('media', 'Números de modelo/medidas distintos: el cliente pide %s y la oferta trae %s. '
                                       'Comprobar que es el mismo artículo.' % dif_modelo))
        if getattr(pri, 'por_posicion', False):
            o.alertas.append(('media', 'Casada por POSICIÓN: la línea "%s" no tiene una descripción legible, pero está entre '
                                       'las líneas de las partidas vecinas y tiene la misma cantidad. Comprobar.'
                              % ppal.partida.descripcion[:40]))
        if ppal.partida.precio is None:
            o.alertas.append(('media', 'El proveedor no da precio para esta línea.'))
        opc = [x for x in extras if x.partida.opcional]
        if opc:
            o.alertas.append(('baja', '%d línea(s) OPCIONAL(es) no sumadas: %s' % (
                len(opc), '; '.join(x.partida.descripcion[:40] for x in opc))))
        kwp_pedido = m.atributos.get('kwp')
        wp_mod = ppal.atributos.get('wp')
        if m.cantidad and cant and not (kwp_pedido and wp_mod):
            r = cant / m.cantidad
            if r < 0.97:
                o.alertas.append(('media', 'Cantidad ofertada menor que la necesaria: %s frente a %s.' % (
                    E._num(cant), E._num(m.cantidad))))
        kwp_pedido = m.atributos.get('kwp')
        wp_mod = ppal.atributos.get('wp')
        if kwp_pedido and wp_mod and ppal.atributos.get('familia') == 'modulo_fv':
            # Lo que se pide es una POTENCIA mínima: los módulos necesarios dependen de los Wp del módulo ofertado
            necesarios = int(-(-kwp_pedido * 1000 // wp_mod))
            ofertado_kwp = wp_mod * cant / 1000
            o.cant_necesaria = necesarios
            if o.precio is not None:
                o.importe = round(o.precio * necesarios, 2)
            texto = ('Se piden %s kWp: con módulos de %d Wp hacen falta %d (%s kWp). La oferta trae %s módulos = %s kWp'
                     % (E._num(kwp_pedido), wp_mod, necesarios, E._num(necesarios * wp_mod / 1000), E._num(cant),
                        E._num(ofertado_kwp)))
            if ofertado_kwp < kwp_pedido * 0.999:
                o.alertas.append(('alta', texto + ' → POTENCIA INSUFICIENTE (faltan %d módulos). El importe se calcula '
                                  'con los %d necesarios.' % (necesarios - cant, necesarios)))
            elif ofertado_kwp > kwp_pedido * 1.15:
                o.alertas.append(('media', texto + ' → sobredimensionado (+%.0f%%). El importe se compara con los %d '
                                  'necesarios.' % ((ofertado_kwp / kwp_pedido - 1) * 100, necesarios)))
            if m.cantidad and abs(necesarios - m.cantidad) > 0.5:
                o.alertas.append(('baja', 'El proyecto describe %s módulos; con el módulo ofertado bastan %d para la '
                                  'potencia pedida.' % (E._num(m.cantidad), necesarios)))
        out[mid] = o
    return out


def _numeros_modelo(texto):
    """Números de 3-5 cifras del principio del texto (modelos, medidas, lúmenes: 100, 2000, 1500, 600X600...)."""
    n = E.norm(texto)[:70]
    # números sueltos (no dentro de un código como 'cayp252m2t2' o '2700610-030'), que no empiecen por 0, que no sean
    # temperaturas de color ni lúmenes/vatios (esos los comprueban los atributos)
    nums = re.findall(r'(?<![a-z0-9.,\-])(\d{3,5})(?=$|ww\b|[^0-9.,a-z])', n)
    return {x for x in nums if not x.startswith('0') and x not in ('2700', '3000', '3500', '4000', '5000', '6500')}


def _numeros_distintos(titulo_cliente, desc_oferta):
    """('100, 2000', '1500') si cliente y oferta citan números de modelo distintos; None si coinciden o no hay."""
    nc, no = _numeros_modelo(titulo_cliente), _numeros_modelo(desc_oferta)
    # un número 'pegado' por el OCR a otro ('3400830') cuenta como presente
    pc = re.sub(r'[^0-9a-z]', '', E.norm(titulo_cliente))
    po = re.sub(r'[^0-9a-z]', '', E.norm(desc_oferta))
    faltan = {x for x in nc - no if x not in po}
    sobran = {x for x in no - nc if x not in pc}
    if not nc or not no or not faltan or not sobran or len(nc & no) >= len(faltan):
        return None
    return ', '.join(sorted(faltan, key=int)), ', '.join(sorted(sobran, key=int))


def _metros_pieza(texto):
    """Longitud de una pieza vendida por unidades: '5MX10' (rollo de 5 m), 'SUPF.2M' (carril de 2 m), 'L=3m',
    'RO.25M' (rollo de 25 m). None si no se indica."""
    n = E.norm(texto)
    for pat in (r'(?<![\d.,])(\d{1,3}(?:[.,]\d)?)\s*m\s*x\s*\d', r'\bro\.?\s*(\d{1,3})\s*m\b', r'\bl\s*=\s*(\d{1,2}(?:[.,]\d)?)\s*m\b',
                r'(?<![\d.,x])(\d{1,2}(?:[.,]\d)?)\s*m(?:ts|etros)?\b(?!m)', r'\.(\d{1,2})m\b'):
        mm = re.search(pat, n)
        if mm:
            v = float(mm.group(1).replace(',', '.'))
            if 0.3 <= v <= 500:
                return v
    return None


def comparacion_cantidad(cant_prov, cant_mat):
    """Texto corto para la columna 'cantidad del proveedor frente a la del cliente'."""
    if cant_prov is None or not cant_mat:
        return ''
    d = cant_prov - cant_mat
    if abs(d) <= max(0.005, cant_mat * 0.005):
        return '='
    return '%s %s (%+.0f%%)' % ('más' if d > 0 else 'menos', E._num(abs(d)), d / cant_mat * 100)


# ------------------------------------------------------------------------------------- catálogos de precios
UMBRAL_CATALOGO = 0.62


def emparejar_catalogo(materiales, lineas, manuales=None, conocidas=None):
    """Para una BASE DE PRECIOS (catálogo sin cantidades, p. ej. la de la Junta): a cada material del cliente se le da
    el artículo más parecido del catálogo, si se parece lo bastante. Un mismo artículo puede servir a varias partidas
    (al revés que en una oferta, donde cada línea es una cosa). Devuelve (asignaciones, sin_casar=[], puntos)."""
    manuales = manuales or {}
    por_id = {m.id: m for m in materiales}
    preparar_idf(materiales)
    preparar_semantica(materiales, [l for l in lineas if l.partida.precio is not None])
    preparar_memoria(materiales, [l for l in lineas if l.partida.precio is not None])
    asign, fijados, vetadas = [], set(), set()
    por_i = {l.i: l for l in lineas}
    for li, mid in manuales.items():
        l = por_i.get(li)
        if l is None:
            continue
        if mid and mid in por_id:
            asign.append(Asignacion(mid, l, 'principal', 1.0, 'manual'))
            fijados.add(mid)
        else:
            vetadas.add(li)
    # índice de candidatos: misma familia o compatibles; sin familia, palabras raras en común
    por_fam, por_tok = collections.defaultdict(list), collections.defaultdict(list)
    for l in lineas:
        if l.i in vetadas or l.partida.precio is None:
            continue
        por_fam[l.atributos.get('familia')].append(l)
        for t in l.tokens:
            if len(t) >= 4 and not t.isdigit():
                por_tok[t].append(l)
    puntos = {}
    for m in materiales:
        if m.id in fijados:
            continue
        fm = m.atributos.get('familia')
        if fm:
            cands = [l for f, ls in por_fam.items() if E.compatibles(f, fm) for l in ls]
        else:
            vistos = {}
            for t in m.tokens:
                if _IDF.get(t, 0) > 1.0:
                    for l in por_tok.get(t, ()):
                        vistos[l.i] = l
            cands = list(vistos.values())
        mejor = sorted(((puntuar(l, m, conocidas), l.i) for l in cands), reverse=True)[:12]
        for sc, li in mejor:
            if sc < UMBRAL_CATALOGO:
                break
            l = por_i[li]
            if _choca_catalogo(m, l) or any(g == 'alta' for g, t in E.comparar(m.atributos, l.atributos)):
                continue
            asign.append(Asignacion(m.id, l, 'principal', sc))
            puntos.setdefault(li, []).append((sc, m.id))
            break
    return asign, [], puntos


MATERIALES_CANAL = [('acero', r'acero|galvaniz|metalic|inox'), ('pvc', r'\bpvc\b'), ('policarbonato', r'policarbonato'),
                    ('polietileno', r'polietileno|\bpe\b'), ('poliamida', r'poliamida'), ('aluminio', r'alumin')]
TIPOS_BANDEJA = [('rejilla', r'rejilla|varilla'), ('ciega', r'ciega'), ('perforada', r'perforad'), ('escalera', r'escalera')]


def _choca_catalogo(m, l):
    """En un catálogo hay de todo: se descartan parecidos que son otra cosa (tubo de acero frente a policarbonato,
    bandeja de rejilla frente a ciega, 1x150 frente a 3x150, cable desnudo frente a aislado, la tapa de la bandeja...)."""
    if l.es_accesorio and not es_accesorio_texto(m.descripcion + ' ' + (m.partida.resumen or '')):
        return True
    tm = E.norm(m.descripcion + ' ' + (m.partida.resumen or '') + ' ' + m.partida.descripcion[:200])
    tl = E.norm(l.partida.descripcion)
    fam = m.atributos.get('familia')
    if re.match(r'(prueba|ensayo|legaliz|certific|document|tramit|honorario|gestion|desmontaje|retirada|ayuda)',
                E.norm(m.descripcion)):
        return True                     # servicios: un catálogo de materiales no tiene su precio
    if re.match(r'tapa\b', tl) and not re.match(r'tapa\b', E.norm(m.descripcion)):
        return True
    if fam in ('canal', 'bandeja'):
        dm = set(re.findall(r'(\d{2,3})\s*x\s*(\d{2,3})', tm)[:1])
        dl = set(re.findall(r'(\d{2,3})\s*x\s*(\d{2,3})', tl)[:1])
        if dm and dl and {tuple(sorted(x)) for x in dm} != {tuple(sorted(x)) for x in dl}:
            return True
    if fam in ('tubo', 'canal', 'bandeja'):
        for grupo in (MATERIALES_CANAL, TIPOS_BANDEJA if fam == 'bandeja' else []):
            a = {n for n, pat in grupo if re.search(pat, tm)}
            b = {n for n, pat in grupo if re.search(pat, tl)}
            if a and b and not a & b:
                return True
    if fam == 'cable':
        if ('desnudo' in tl) != ('desnudo' in tm):
            return True
        kv = lambda t: '1kv' if re.search(r'0[.,]6\s*/\s*1\s*kv|0[.,]6-1\s*kv|rz1|xz1|rv-?k', t) else (
            '750v' if re.search(r'750\s*v|450\s*/\s*750|h07', t) else None)
        if kv(tm) and kv(tl) and kv(tm) != kv(tl):
            return True
        fm, fl = m.atributos.get('formacion') or [], l.atributos.get('formacion') or []
        if fm and fl and fm[0][0] != fl[0][0] and not re.search(r'\(\s*1\s*x', tl):
            return True
        if m.atributos.get('material') and l.atributos.get('material') and m.atributos['material'] != l.atributos['material']:
            return True
    return False
