"""Modelo que aprende de las decisiones de las personas (fase 2).

Dos piezas, las dos locales y rápidas:

1) MEMORIA de decisiones (lo que hace que se apliquen en obras futuras)
   Para cada pareja posible (línea del proveedor, partida del cliente) se buscan decisiones anteriores parecidas por
   SIGNIFICADO en los dos lados: misma clase de partida (>= 0,93) y misma clase de línea (>= 0,90).
   - Alguien la casó / aceptó / pidió  -> suma (más si es el mismo proveedor) y se explica: "en la obra X, Fulano...".
   - Alguien la descasó                -> resta.

2) MODELO DE CONFIANZA (regresión logística entrenada con las decisiones)
   Cada decisión guarda los RASGOS de la pareja elegida y de las alternativas que había (puntuación de reglas,
   parecido de significado, familia, cantidad, código). Con eso se entrena, en segundos y en este PC, la probabilidad
   de que un emparejamiento sea correcto. Decide si queda "aplicado" o "a revisar". Hasta tener datos suficientes
   (MIN_MUESTRAS con aciertos y errores) se usan los umbrales de siempre.
"""
import json
import math
import threading

import numpy as np

UMBRAL_MAT, UMBRAL_LIN = 0.93, 0.90
PESO_MEMORIA, PESO_NEGATIVA = 0.6, 0.6
MIN_MUESTRAS = 30
RASGOS = ['reglas', 'semantica', 'misma_familia', 'cantidad', 'codigo', 'gramas']
_LOCK = threading.Lock()
_EST = {'clave': None, 'dec': [], 'vm': None, 'vl': None, 'modelo': None, 'n': 0, 'n_pos': 0, 'n_neg': 0}


# ------------------------------------------------------------------------------------------------ rasgos
def rasgos(l, m, conocidas=None):
    """Vector de rasgos de la pareja (para entrenar y para predecir). Necesita preparar_idf/semántica hechos."""
    from . import emparejar as M
    reglas = M.puntuar(l, m, conocidas, memoria=False)
    sem = M.sim_semantica(l, m)
    fl, fm = l.atributos.get('familia'), m.atributos.get('familia')
    q1, q2 = l.partida.cantidad or 0, m.cantidad or 0
    cant = (1.0 - min(1.0, abs(q1 / q2 - 1))) if q1 and q2 else 0.5
    a, b = M._cod(l.referencia), M._cod(m.codigo)
    return [round(reglas, 4), round(sem[1], 4) if sem else 0.0, 1.0 if fl and fl == fm else 0.0, round(cant, 4),
            1.0 if len(a) >= 4 and a == b else 0.0, round(M.sim_gramas(l, m), 4)]


def muestras_de_decision(materiales, lineas_prov, l_elegida, m, puntos=None, conocidas=None):
    """[(rasgos, etiqueta)] de una decisión: la pareja elegida (1) y las otras líneas candidatas para m (0)."""
    out = [(rasgos(l_elegida, m, conocidas), 1)]
    if puntos:
        otras = [x for x in lineas_prov if x is not l_elegida
                 and any(mid == m.id for _, mid in (puntos.get(x.i) or [])[:3])]
        for x in otras[:4]:
            out.append((rasgos(x, m, conocidas), 0))
    return out


# ------------------------------------------------------------------------------------------------ carga
def _texto_mat(d):
    m = d.get('material') or {}
    return ' '.join(x for x in [m.get('resumen') or '', m.get('texto') or '', (m.get('partida') or '')[:160]] if x)


def cargar(bbdd):
    """Lee las decisiones activas de la BBDD (solo si han cambiado) y entrena el modelo de confianza."""
    from . import semantica as SE
    with _LOCK:
        fila = bbdd.c.execute('SELECT COUNT(*), MAX(id), SUM(activo) FROM decision').fetchone()
        clave = tuple(fila)
        if clave == _EST['clave']:
            return _EST
        dec = []
        X, y = [], []
        for r in bbdd.c.execute('SELECT * FROM decision WHERE activo=1 ORDER BY id'):
            try:
                d = json.loads(r['datos'] or '{}')
            except ValueError:
                continue
            pos = r['accion'] in ('casar', 'aceptar', 'pedido')
            dec.append({'uid': r['uid'], 'accion': r['accion'], 'positiva': pos, 'obra': r['obra'],
                        'proveedor': r['proveedor'], 'usuario': r['usuario'], 'cuando': r['cuando'],
                        'mat': _texto_mat(d), 'mat_codigo': r['mat_codigo'], 'mat_resumen': r['mat_texto'],
                        'lin': (d.get('linea') or {}).get('desc') or '', 'lin_ref': (d.get('linea') or {}).get('ref')})
            for x, etiqueta in d.get('muestras') or []:
                if len(x) == len(RASGOS):
                    X.append(x)
                    y.append(etiqueta if pos else 0)
        _EST.update(clave=clave, dec=dec, vm=None, vl=None)
        if dec and SE.disponible():
            _EST['vm'] = SE.vectores([x['mat'] for x in dec])
            _EST['vl'] = SE.vectores([x['lin'] for x in dec])
        _EST['n'], _EST['n_pos'], _EST['n_neg'] = len(y), sum(y), len(y) - sum(y)
        _EST['modelo'] = _entrenar(np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)) \
            if len(y) >= MIN_MUESTRAS and 0 < sum(y) < len(y) else None
        return _EST


def _entrenar(X, y, vueltas=600, l2=0.01):
    """Regresión logística con descenso de gradiente (numpy): w·x + b -> probabilidad de acierto."""
    media, desv = X.mean(0), X.std(0) + 1e-6
    Z = (X - media) / desv
    w, b = np.zeros(Z.shape[1], dtype=np.float32), 0.0
    peso = np.where(y == 1, 0.5 / max(1, y.sum()), 0.5 / max(1, (1 - y).sum())) * len(y)   # clases equilibradas
    for _ in range(vueltas):
        p = 1 / (1 + np.exp(-(Z @ w + b)))
        g = (p - y) * peso
        w -= 0.1 * (Z.T @ g / len(y) + l2 * w)
        b -= 0.1 * g.mean()
    p = 1 / (1 + np.exp(-(Z @ w + b)))
    acierto = float(((p >= 0.5) == (y == 1)).mean())
    return {'w': w, 'b': b, 'media': media, 'desv': desv, 'acierto': acierto, 'n': int(len(y))}


def probabilidad(x):
    mod = _EST.get('modelo')
    if not mod:
        return None
    z = (np.array(x, dtype=np.float32) - mod['media']) / mod['desv']
    return float(1 / (1 + math.exp(-(float(z @ mod['w']) + mod['b']))))


def estado():
    mod = _EST.get('modelo')
    return {'decisiones': len(_EST['dec']), 'muestras': _EST['n'], 'aciertos': _EST['n_pos'], 'errores': _EST['n_neg'],
            'entrenado': bool(mod), 'acierto_entrenamiento': round(mod['acierto'], 3) if mod else None,
            'min_muestras': MIN_MUESTRAS,
            'pesos': {k: round(float(v), 3) for k, v in zip(RASGOS, mod['w'])} if mod else None}


# ------------------------------------------------------------------------------------------------ memoria
def preparar_memoria(materiales, lineas, proveedor):
    """Evidencia de decisiones anteriores para cada pareja (línea, material). -> dict para emparejar.puntuar."""
    from . import semantica as SE
    dec = _EST['dec']
    if not dec or _EST['vm'] is None or not materiales or not lineas:
        return None
    vm = SE.vectores([SE.texto_material(m) for m in materiales])
    vl = SE.vectores([SE.texto_linea(l) for l in lineas])
    if vm is None or vl is None:
        return None
    Sm = vm @ _EST['vm'].T              # materiales x decisiones
    Sl = vl @ _EST['vl'].T              # líneas x decisiones
    okm = Sm >= UMBRAL_MAT
    if not okm.any():
        return None
    cols = np.where(okm.any(0))[0]       # solo decisiones con alguna partida parecida en esta obra
    mejor = {}
    for d in cols:
        filas_l = np.where(Sl[:, d] >= UMBRAL_LIN)[0]
        if not len(filas_l):
            continue
        filas_m = np.where(okm[:, d])[0]
        info = dec[d]
        for a in filas_l:
            for b in filas_m:
                ev = min(float(Sm[b, d]), float(Sl[a, d]))
                k = (lineas[a].i, materiales[b].id)
                signo = 1 if info['positiva'] else -1
                prev = mejor.get(k)
                if prev is None or ev > prev[0] or (ev == prev[0] and signo < 0):
                    mejor[k] = (ev, signo, info)
    return {'pares': mejor, 'proveedor': (proveedor or '').lower()}


def bonificacion(mem, l, m):
    """(puntos a sumar, explicación) por lo aprendido para la pareja."""
    if not mem:
        return 0.0, None
    x = mem['pares'].get((l.i, m.id))
    if not x:
        return 0.0, None
    ev, signo, info = x
    mismo = (info['proveedor'] or '').lower() == mem['proveedor']
    if signo > 0:
        f = max(0.0, min(1.0, (ev - UMBRAL_LIN) / 0.06))
        puntos = PESO_MEMORIA * (0.5 + 0.5 * f) * (1.0 if mismo else 0.75)
    else:
        # "esto NO va aquí": muy fuerte si es prácticamente la misma línea del mismo proveedor
        f = max(0.0, min(1.0, (ev - UMBRAL_LIN) / 0.05))
        puntos = -(PESO_NEGATIVA + 0.9 * f) * (1.0 if mismo else 0.6)
    verbo = {'casar': 'casó a mano', 'aceptar': 'aceptó', 'pedido': 'pidió', 'descasar': 'DESCASÓ'}.get(info['accion'], '')
    texto = ('%s: en la obra "%s", %s %s una línea parecida (%d %%) %s"%s" para la partida %s%s.' % (
        'Aplicado por lo aprendido' if signo > 0 else 'Penalizado por lo aprendido', info['obra'] or '?',
        info['usuario'] or 'alguien', verbo, round(ev * 100), ('de %s ' % info['proveedor']) if info['proveedor'] else '',
        (info['lin'] or '')[:60], info['mat_codigo'] or '', (' "%s"' % (info['mat_resumen'] or '')[:50])))
    return puntos, texto
