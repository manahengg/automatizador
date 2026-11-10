"""Comparar una OFERTA de proveedor con la LICITACIÓN (presupuesto base).

Qué hace:
  1. Empareja cada línea de la oferta con la partida de la licitación que le corresponde.
  2. Construye un presupuesto nuevo con las partidas de la LICITACIÓN (mismos códigos, textos y cantidades)
     pero al PRECIO del proveedor, para importarlo en m4PRO junto al original y comparar partida a partida.

Qué NO hace: no decide por ti. Cada pareja lleva un estado:
   seguro      parecido alto y sin rival cercano  -> se incluye
   revisar     hay una propuesta pero hay que mirarla (rival cercano, cantidades distintas, parecido flojo) -> se incluye marcada
   sin pareja  no hay candidata creíble          -> NO se incluye; la eliges tú en la hoja de revisión
"""
import collections
import dataclasses
import functools
import difflib
import re
import unicodedata

from .texto import normalizar_busqueda

from .modelo import Capitulo, Documento, Partida

UMBRAL_SEGURO = 0.86      # solo se considera fiable con coincidencia fuerte
UMBRAL_MARGEN = 0.12     # diferencia mínima con la segunda candidata
UMBRAL_MINIMO = 0.68     # asignación automática conservadora
MAX_ALTERNATIVAS = 8


@functools.lru_cache(maxsize=20000)
def norm(s):
    return normalizar_busqueda(s)


@dataclasses.dataclass
class Hoja:
    """Una partida de un documento con su posición (nº) y la ruta de capítulos que la contiene."""
    n: int
    partida: Partida
    ruta: str


def hojas(doc):
    out = []

    def rec(cap, ruta):
        r = ruta + [cap.titulo]
        for h in cap.hijos:
            if isinstance(h, Capitulo):
                rec(h, r)
            else:
                out.append(Hoja(len(out) + 1, h, ' / '.join(r)))
    for c in doc.capitulos:
        rec(c, [])
    return out


@dataclasses.dataclass
class Pareja:
    oferta: Hoja
    lic: Hoja = None                 # partida de la licitación propuesta (None = sin pareja)
    parecido: float = 0.0
    margen: float = 0.0
    estado: str = 'sin pareja'
    motivos: list = dataclasses.field(default_factory=list)
    alternativas: list = dataclasses.field(default_factory=list)   # [(parecido, Hoja)] hasta 2


def _contexto(rutas):
    """Palabras que distinguen un capítulo de la oferta de los demás (p. ej. 'sotano', 'primera')."""
    toks = {r: {t for t in norm(r).split() if len(t) > 2} for r in set(rutas)}
    if len(toks) < 2:
        return {r: set() for r in toks}
    veces = collections.Counter(t for ts in toks.values() for t in ts)
    return {r: {t for t in ts if veces[t] == 1} for r, ts in toks.items()}   # palabras exclusivas de ese capítulo


def _cod(x):
    return re.sub(r'[^A-Z0-9]', '', str(x or '').upper())


def _bonus_codigo(o, l):
    """Pista por referencia de producto: igual = +0.5; una es prefijo de la otra (88888 / 88888A) = +0.3."""
    a, b = _cod(o.referencia), _cod(l.codigo)
    if len(a) < 5 or len(b) < 5:
        return 0.0
    if a == b:
        return 0.5
    return 0.3 if (a.startswith(b) or b.startswith(a)) else 0.0


# Familias de términos técnicos: sirven para descubrir candidatos, NO para declarar
# equivalencia automática. La persona siempre puede revisar las alternativas.
_FAMILIAS = (
    {"cable", "conductor", "conductores", "cableado", "hilo", "manguera"},
    {"derivacion", "alimentacion", "linea", "circuito", "tendido", "conexion"},
    {"cuadro", "armario", "envolvente", "cofre"},
    {"tubo", "tuberia", "canalizacion", "canaleta", "bandeja"},
    {"cobre", "cu", "cob", "conductor"},
    {"halogeno", "halogenos", "librehalogenos", "lszh", "z1"},
    {"proteccion", "magnetotermico", "automatico", "interruptor"},
    {"diferencial", "id", "interruptordiferencial"},
    {"luminaria", "lampara", "led", "alumbrado"},
    {"toma", "enchufe", "base", "schuko"},
    {"instalar", "montaje", "colocacion", "suministro", "instalacion"},
)
_MAPA_FAMILIAS = {t: i for i, fam in enumerate(_FAMILIAS) for t in fam}
_STOP = {"de", "del", "la", "las", "el", "los", "y", "e", "en", "con", "para", "por", "a", "un", "una", "ud", "uds", "segun", "incluido", "incluida", "suministro"}


def _tokens(texto):
    return {t for t in norm(texto).split() if len(t) > 1 and t not in _STOP}


def _familias(tokens):
    return {_MAPA_FAMILIAS[t] for t in tokens if t in _MAPA_FAMILIAS}


def _bonus_codigo(o, l):
    a = _cod(o.referencia or o.codigo)
    b = _cod(l.codigo or l.referencia)
    if len(a) < 5 or len(b) < 5:
        return 0.0
    if a == b:
        return 0.18
    if a.startswith(b) or b.startswith(a):
        return 0.10
    return 0.0


def _parecido(o, ctx_o, l, toks_ruta_l):
    """Puntuación 0..1. No confunde parecido textual con equivalencia técnica."""
    po, pl = o.partida, l.partida
    a, b = norm(po.descripcion), norm(pl.descripcion)
    if not a or not b:
        return 0.0
    sec = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    ta, tb = _tokens(po.descripcion), _tokens(pl.descripcion)
    solape = len(ta & tb) / max(1, len(ta))
    union = len(ta & tb) / max(1, len(ta | tb))
    fa, fb = _familias(ta), _familias(tb)
    sem = len(fa & fb) / max(1, len(fa | fb))
    # Relación funcional habitual: una derivación/alimentación puede describirse
    # comercialmente como cable/conductor. Solo eleva la candidatura, no la valida.
    relacionados = {(0, 1), (1, 0)}
    if any((x, y) in relacionados for x in fa for y in fb):
        sem = max(sem, 0.35)
    # Referencias técnicas habituales (RZ1-K, 0,6/1 kV, secciones, polos, IP...).
    tec_a = {t for t in ta if re.search(r"\d", t) or "rz" in t or t.startswith("ip")}
    tec_b = {t for t in tb if re.search(r"\d", t) or "rz" in t or t.startswith("ip")}
    tecnico = len(tec_a & tec_b) / max(1, len(tec_a)) if tec_a else 0.0
    score = 0.25 * sec + 0.25 * solape + 0.15 * union + 0.25 * sem + 0.10 * tecnico
    if po.cantidad is not None and pl.cantidad is not None and abs(po.cantidad - pl.cantidad) < 1e-9:
        score += 0.035
    if po.unidad and pl.unidad and norm(po.unidad) == norm(pl.unidad):
        score += 0.025
    score += _bonus_codigo(po, pl)
    # El contexto de capítulo es solo una pista débil; nunca resta puntos.
    if ctx_o and ctx_o & toks_ruta_l:
        score += 0.025
    return min(1.0, score)


def _explicar_candidato(o, l, puntuacion):
    a, b = _tokens(o.partida.descripcion), _tokens(l.partida.descripcion)
    motivos = []
    comunes = sorted(a & b)
    if comunes:
        motivos.append("términos coincidentes: " + ", ".join(comunes[:8]))
    familias = _familias(a) & _familias(b)
    if familias:
        motivos.append("familias técnicas relacionadas: " + ", ".join(str(x + 1) for x in sorted(familias)))
    if o.partida.cantidad is not None and abs(o.partida.cantidad - l.partida.cantidad) < 1e-9:
        motivos.append("misma cantidad")
    if _bonus_codigo(o.partida, l.partida):
        motivos.append("referencia/código coincidente")
    if any((x, y) in {(0, 1), (1, 0)} for x in _familias(a) for y in _familias(b)):
        motivos.append("relación funcional posible: derivación/alimentación ↔ cable/conductor")
    if not motivos:
        motivos.append("coincidencia textual débil; comprobar manualmente")
    return "%.0f%% — %s" % (puntuacion * 100, "; ".join(motivos))


def emparejar(licitacion, oferta):
    L, O = hojas(licitacion), hojas(oferta)
    if not O or not L:
        return [Pareja(oferta=o, motivos=["No hay partidas en la licitación para comparar."]) for o in O]
    ctx = _contexto([o.ruta for o in O])
    toks_l = {l.n: set(norm(l.ruta).split()) for l in L}
    puntos = {}
    for o in O:
        for l in L:
            puntos[(o.n, l.n)] = _parecido(o, ctx.get(o.ruta, set()), l, toks_l[l.n])

    # La asignación automática sigue siendo uno a uno. Los candidatos adicionales
    # se conservan para el desplegable y para la hoja Excel de revisión.
    asig, usadas = {}, set()
    for (on, ln), sc in sorted(puntos.items(), key=lambda kv: -kv[1]):
        if on in asig or ln in usadas or sc < UMBRAL_MINIMO:
            continue
        asig[on] = ln
        usadas.add(ln)
    _ordenar_gemelos(O, L, asig)

    porn = {l.n: l for l in L}
    parejas = []
    for o in O:
        p = Pareja(oferta=o)
        ranking = sorted(((puntos[(o.n, l.n)], l) for l in L), key=lambda t: -t[0])
        if o.n in asig:
            l = porn[asig[o.n]]
            p.lic, p.parecido = l, puntos[(o.n, l.n)]
            rivales = [(s, r) for s, r in ranking if r.n != l.n and not _gemelos(l, r)]
            p.margen = p.parecido - (rivales[0][0] if rivales else 0.0)
            p.alternativas = rivales[:MAX_ALTERNATIVAS]
            _clasificar(p)
        else:
            p.alternativas = ranking[:MAX_ALTERNATIVAS]
            if p.alternativas:
                p.motivos.append("No se asigna automáticamente. Revisa los candidatos desplegables; pueden ser partidas relacionadas, no necesariamente equivalentes.")
            else:
                p.motivos.append("No hay partidas de licitación para comparar.")
        parejas.append(p)
    return parejas


def _gemelos(a, b):
    """Dos partidas de licitación indistinguibles (mismo texto, cantidad, precio y planta): da igual cuál."""
    return (norm(a.partida.descripcion) == norm(b.partida.descripcion) and a.partida.cantidad == b.partida.cantidad
            and a.partida.precio == b.partida.precio and a.ruta == b.ruta)


def _ordenar_gemelos(O, L, asig):
    """Entre líneas gemelas se respeta el orden del documento (así el resultado es estable y coherente)."""
    porn = {l.n: l for l in L}
    grupos = collections.defaultdict(list)
    for o in O:
        if o.n in asig:
            grupos[(norm(o.partida.descripcion), o.partida.cantidad, o.ruta)].append(o.n)
    for ons in grupos.values():
        lns = sorted(asig[on] for on in ons)
        if all(_gemelos(porn[lns[0]], porn[x]) for x in lns):
            for on, ln in zip(sorted(ons), lns):
                asig[on] = ln


def _clasificar(p):
    o, l = p.oferta.partida, p.lic.partida
    if p.parecido < UMBRAL_SEGURO:
        p.motivos.append('Parecido flojo (%.2f).' % p.parecido)
    if p.margen < UMBRAL_MARGEN:
        p.motivos.append('Hay otra partida casi igual (margen %.2f): comprobar que es esta.' % p.margen)
    if o.cantidad is not None and abs(o.cantidad - l.cantidad) > 1e-9:
        p.motivos.append('Cantidad distinta: oferta %s, licitación %s.' % (_f(o.cantidad), _f(l.cantidad)))
    if o.precio is None:
        p.motivos.append('La oferta no da precio para esta línea (se importa a 0,00).')
    p.estado = 'revisar' if p.motivos else 'seguro'


def _f(x):
    return ('%.3f' % x).rstrip('0').rstrip('.')


def construir(licitacion, oferta, elegidas):
    """Presupuesto con las partidas de la LICITACIÓN al precio del proveedor.

    elegidas: {nº línea oferta: nº partida licitación}. Solo se incluyen las partidas elegidas.
    Devuelve (Documento, resumen dict).
    """
    L = {l.n: l for l in hojas(licitacion)}
    O = {o.n: o for o in hojas(oferta)}
    por_lic = collections.defaultdict(list)
    for on, ln in elegidas.items():
        por_lic[ln].append(on)
    dup = {ln: ons for ln, ons in por_lic.items() if len(ons) > 1}
    if dup:
        raise ValueError('Hay partidas de la licitación con más de un precio: ' + '; '.join(
            'licitación nº %d <- líneas de oferta %s' % (ln, ons) for ln, ons in dup.items()))
    proveedor = (oferta.proveedor or 'PROVEEDOR').strip()
    nuevo_por_id = {}
    for ln, (on,) in ((ln, tuple(ons)) for ln, ons in por_lic.items()):
        o, l = O[on].partida, L[ln].partida
        nota = ' [%s: %s' % (proveedor, o.descripcion.strip()[:90])
        if o.precio_lista is not None and o.dto_pct is not None:
            nota += '; lista %.2f, dto %.2f %%' % (o.precio_lista, o.dto_pct)
        nota += ']'
        nuevo_por_id[id(l)] = dataclasses.replace(
            l, precio=o.precio, precio_lista=None, dto_pct=None, descripcion=l.descripcion.strip() + nota)

    def clonar(cap):
        hijos = []
        for h in cap.hijos:
            if isinstance(h, Capitulo):
                c = clonar(h)
                if c.hijos:
                    hijos.append(c)
            elif id(h) in nuevo_por_id:
                hijos.append(nuevo_por_id[id(h)])
        return Capitulo(titulo=cap.titulo, codigo=cap.codigo, hijos=hijos)

    doc = Documento(tipo='comparacion', origen=oferta.origen, nombre='Licitacion a precios de %s' % proveedor,
                    proveedor=proveedor)
    doc.capitulos = [c for c in (clonar(c) for c in licitacion.capitulos) if c.hijos]
    base = sum(L[ln].partida.importe for ln in por_lic)
    prov = doc.importe
    resumen = {'proveedor': proveedor, 'partidas': len(por_lic), 'importe_licitacion': round(base, 2),
               'importe_proveedor': round(prov, 2), 'diferencia': round(prov - base, 2),
               'diferencia_pct': round((prov / base - 1) * 100, 2) if base else None}
    doc.avisar('info', 'Importe de las %d partidas elegidas: licitación %.2f €, %s %.2f € (%+.2f %%).' % (
        len(por_lic), base, proveedor, prov, resumen['diferencia_pct'] or 0))
    return doc, resumen
