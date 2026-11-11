"""Registro de DECISIONES de las personas (fase 0 del aprendizaje).

Cada decisión se guarda con su contexto: la partida del cliente (texto, familia, características), la línea del proveedor
(referencia, descripción, precio) y, si los hay, los candidatos que había y lo que la app había propuesto antes.
Acciones:
    casar      la persona casa una línea del proveedor con una partida (corrección o confirmación manual)
    descasar   la persona dice que una línea NO va con la partida que le había puesto la app
    aceptar    la persona confirma con ✔ lo que la app propuso
    pedido     al generar un pedido, lo que se pide cuenta como aceptado (decisión implícita)
Se comparte como el resto del conocimiento: un fichero nuevo por evento en <compartida>/conocimiento (tipo 'decision')
y cada PC lo vuelca en su BBDD local (tabla decision). 'decision_olvidada' desactiva una decisión.
De aquí aprenden las fases siguientes (aprendizaje.py).
"""
import json

from . import compartido as C
from . import electrico as E

ACCIONES = ('casar', 'descasar', 'aceptar', 'pedido')
POSITIVAS = ('casar', 'aceptar', 'pedido')


def desc_material(m):
    at = {k: v for k, v in (m.atributos or {}).items() if isinstance(v, (str, int, float)) and not k.startswith('_')}
    return {'codigo': (m.codigo or '').strip(), 'resumen': (m.partida.resumen or '')[:200],
            'texto': (m.descripcion or '')[:300], 'partida': (m.partida.descripcion or '')[:600],
            'familia': m.atributos.get('familia'), 'clave': m.clave or '', 'unidad': m.unidad,
            'cantidad': m.cantidad, 'atributos': at}


def desc_linea(l):
    if l is None:
        return None
    p = l.partida
    return {'ref': p.referencia or p.codigo or '', 'desc': (p.descripcion or '')[:300],
            'familia': l.atributos.get('familia'), 'precio': p.precio, 'cantidad': p.cantidad, 'unidad': p.unidad,
            'uid': getattr(l, 'uid', None)}


def item(m, l, candidatos=None, antes=None, puntuacion=None):
    """Una decisión sobre la pareja (material m, línea l). candidatos: [(línea, puntuación)] que había."""
    return {'material': desc_material(m), 'linea': desc_linea(l),
            'candidatos': [dict(desc_linea(x), punt=round(s, 3)) for x, s in (candidatos or [])][:6],
            'antes': desc_material(antes) if antes is not None else None,
            'puntuacion': round(puntuacion, 3) if puntuacion is not None else None}


def registrar(bbdd, accion, obra, proveedor, items):
    """Escribe el evento compartido y lo aplica a la BBDD local."""
    if accion not in ACCIONES or not items:
        return None
    ev = C.escribir_evento(bbdd.dir_conocimiento(), 'decision',
                           {'accion': accion, 'obra': obra, 'proveedor': proveedor, 'items': items})
    bbdd._aplicar(ev)
    return ev


def olvidar(bbdd, uid):
    ev = C.escribir_evento(bbdd.dir_conocimiento(), 'decision_olvidada', {'uid': uid})
    bbdd._aplicar(ev)


def clave_texto(x):
    return E.norm(x or '')[:80]


def filas_de_evento(ev):
    """Evento 'decision' -> filas de la tabla decision."""
    d = ev['datos']
    out = []
    for k, it in enumerate(d.get('items') or []):
        m, l = it.get('material') or {}, it.get('linea') or {}
        out.append({'uid': '%s:%d' % (ev['id'], k), 'cuando': ev.get('cuando'), 'usuario': ev.get('usuario'),
                    'accion': d['accion'], 'obra': d.get('obra'), 'proveedor': d.get('proveedor'),
                    'mat_codigo': m.get('codigo'), 'mat_texto': m.get('resumen') or m.get('texto'),
                    'mat_familia': m.get('familia'), 'mat_clave': m.get('clave'),
                    'mat_key': clave_texto((m.get('resumen') or '') + ' ' + (m.get('texto') or '')),
                    'linea_ref': l.get('ref'), 'linea_desc': l.get('desc'), 'linea_familia': l.get('familia'),
                    'linea_key': clave_texto(l.get('desc')), 'precio': l.get('precio'),
                    'datos': json.dumps(it, ensure_ascii=False)})
    return out
