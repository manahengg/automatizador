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


def _tokens(texto):
    n = E.norm(texto)
    n = re.sub(r'[^a-z0-9.,/+-]+', ' ', n)
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


def lineas_oferta(doc, proveedor):
    out = []
    for cap in doc.capitulos:
        for p in cap.partidas():
            out.append(Linea(proveedor=proveedor, i=len(out), partida=p, seccion=cap.titulo,
                             atributos=E.atributos(p.descripcion), tokens=_tokens(p.descripcion),
                             plantas=_plantas(cap.titulo)))
    return out


# ------------------------------------------------------------------------------------------- puntuación
def puntuar(l, m, conocidas=None):
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
                                 ('temp_color', 0.05, 0.1), ('material', 0.05, 0.3)):
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
        comun = len(l.tokens & m.tokens)
        s += 0.3 * (0.6 * comun / max(1, min(len(l.tokens), 12)) + 0.4 * comun / max(1, len(l.tokens | m.tokens)) * 3)
    q1, q2 = l.partida.cantidad or 0, m.cantidad or 0
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
    if conocidas:
        k = conocidas.get((l.proveedor.lower(), _cod(l.referencia) or E.norm(l.partida.descripcion)[:60]))
        if k and (k == m.clave or k == ('cli:' + _cod(m.codigo)) or k == 'desc:' + E.norm(m.partida.resumen or m.descripcion)[:60]):
            s += 0.6
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
    puntos = {}
    for l in normales:
        fila = []
        for m in materiales:
            fila.append((puntuar(l, m, conocidas), m.id))
        fila.sort(reverse=True)
        puntos[l.i] = fila[:8]
    # 1) principales: mejor pareja global
    cand = sorted(((sc, l.i, mid) for l in normales for sc, mid in puntos[l.i] if sc >= UMBRAL_PRINCIPAL), reverse=True)
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
        if sc >= 0.28 and l.atributos.get('familia') and l.atributos.get('familia') == por_id[mid].atributos.get('familia') \
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
    sin = [l for l in lineas if l.i not in hecho and not (l.i in usadas and manuales.get(l.i))]
    return asign, sin, puntos


def _parecida(a, b):
    return bool(a and b) and 0.8 <= a / b <= 1.25


def _choca(m, l):
    """True si la línea contradice claramente al material (no puede ser un accesorio suyo)."""
    return any(g == 'alta' for g, _ in E.comparar(m.atributos, l.atributos))


def _mejorar(asign, materiales, lineas, normales, puntos, por_id, hecho, cubiertos, conocidas, vueltas=3):
    """Busqueda local sobre las líneas PRINCIPALES: mover una línea a un material sin cubrir o intercambiar dos,
    si mejora puntuación + 'bono de bloque' (otra línea cercana en la oferta va a la misma partida del cliente)."""
    BONO = 0.12
    principales = {a.linea.i: a for a in asign if a.tipo == 'principal' and a.origen == 'auto'}

    def mapa():
        return {a.linea.i: por_id[a.material_id].n for a in asign if a.tipo == 'principal'}

    def bono(li, n, m_actual):
        return BONO if any(m_actual.get(j) == n for j in range(li - 6, li + 7) if j != li) else 0.0

    candidatos = {l.i: [(sc, mid) for sc, mid in puntos[l.i] if sc >= 0.2] for l in normales}
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
                antes = a.puntuacion + b.puntuacion + bono(a.linea.i, ma.n, mm) + bono(b.linea.i, mb.n, mm)
                despues = pab + pba + bono(a.linea.i, mb.n, mm) + bono(b.linea.i, ma.n, mm)
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

    @property
    def estado(self):
        if self.origen == 'manual':
            return 'manual'
        if any(g == 'alta' for g, _ in self.alertas) or self.puntuacion < UMBRAL_SEGURO:
            return 'revisar'
        return 'seguro'


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
        if ppal.partida.precio is not None:
            if cant:
                o.precio = suma / cant + sueltas
            else:
                o.precio = ppal.partida.precio + sueltas
            o.cant_prov = cant
            o.importe = round(o.precio * (m.cantidad or 0), 2)
        o.codigos = ' + '.join(dict.fromkeys(x.referencia or '(s/c)' for x in [ppal] + extras if not x.es_canon))
        o.descripcion = ppal.partida.descripcion + (' (+%d líneas: %s)' % (
            len(extras), '; '.join(x.partida.descripcion[:40] for x in extras)) if extras else '')
        for g, t in E.comparar(m.atributos, ppal.atributos):
            o.alertas.append((g, t))
        if ppal.partida.opcional:
            o.alertas.append(('media', 'La línea está marcada como OPCIONAL en la oferta.'))
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


def comparacion_cantidad(cant_prov, cant_mat):
    """Texto corto para la columna 'cantidad del proveedor frente a la del cliente'."""
    if cant_prov is None or not cant_mat:
        return ''
    d = cant_prov - cant_mat
    if abs(d) <= max(0.005, cant_mat * 0.005):
        return '='
    return '%s %s (%+.0f%%)' % ('más' if d > 0 else 'menos', E._num(abs(d)), d / cant_mat * 100)
