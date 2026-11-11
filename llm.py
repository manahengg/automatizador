"""Modelo de lenguaje LOCAL que redacta (fase 4): explicar una partida, resumir la obra y responder preguntas.

Motor: onnxruntime-genai (Microsoft) en el procesador; modelos Phi de Microsoft cuantizados a 4 bits:
    llm-phi4   Phi-4-mini-instruct (3.800 M parámetros, ~4,7 GB, ~5 GB de RAM): mejor en español (por defecto)
    llm-phi35  Phi-3.5-mini-instruct (~2,6 GB): más ligero, para PCs de 8 GB
Va BAJO DEMANDA (unos 5-10 tokens/s en un PC normal: 15-60 s por respuesta, que se ve mientras se escribe).

Fiabilidad: el modelo NO busca nada por su cuenta. La app le da una FICHA con los datos (la de analisis_partida.py, o
un resumen de la obra / las partidas relacionadas con la pregunta) y le prohíbe inventar. Si la respuesta propone
cambios, solo puede ser con líneas "PROPUESTA: aceptar <Nº>" o "PROPUESTA: ver <Nº>", que la pantalla convierte en
botones que la persona confirma: el modelo nunca cambia nada solo.
"""
import json
import re
import threading
import time

from . import compartido as C
from . import modelos

_PHI4 = 'microsoft/Phi-4-mini-instruct-onnx'
_D4 = 'cpu_and_mobile/cpu-int4-rtn-block-32-acc-level-4/'
_PHI35 = 'microsoft/Phi-3.5-mini-instruct-onnx'
_D35 = 'cpu_and_mobile/cpu-int4-awq-block-128-acc-level-4/'
_F35 = 'phi-3.5-mini-instruct-cpu-int4-awq-block-128-acc-level-4.onnx'
modelos.registrar('llm-phi4', {
    'repo': _PHI4, 'titulo': 'Lenguaje: Phi-4-mini (recomendado, PC de 16 GB)', 'mb': 4720,
    'ficheros': {_D4 + f: f for f in ('added_tokens.json', 'config.json', 'genai_config.json', 'merges.txt',
                                      'special_tokens_map.json', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json',
                                      'model.onnx', 'model.onnx.data')}})
modelos.registrar('llm-phi35', {
    'repo': _PHI35, 'titulo': 'Lenguaje: Phi-3.5-mini (ligero, PC de 8 GB)', 'mb': 2660,
    'ficheros': {_D35 + f: f for f in ('config.json', 'genai_config.json', 'special_tokens_map.json', 'tokenizer.json',
                                       'tokenizer_config.json', _F35, _F35 + '.data')}})
PREFERENCIA = ('llm-phi4', 'llm-phi35')

SISTEMA = ("Eres el asistente de compras de una empresa instaladora de material eléctrico. Respondes en español de "
           "España, en frases cortas y claras, para un técnico. Usa SOLO los datos que te dan entre DATOS; no inventes "
           "cantidades, precios, modelos, proveedores ni acciones. Si algo no está en los datos, di que no consta. "
           "No repitas los datos enteros: interprétalos.")
_LOCK = threading.Lock()
_EST = {'modelo': None, 'tok': None, 'nombre': None, 'error': None}


def nombre_modelo():
    """El modelo de lenguaje disponible en este PC (el configurado, o el mejor que haya)."""
    pref = (C.config().get('modelo_llm') or '').strip()
    for n in ([pref] if pref else []) + list(PREFERENCIA):
        if n in modelos.MODELOS and modelos.ruta(n):
            return n
    return None


def disponible():
    try:
        import onnxruntime_genai  # noqa: F401
    except Exception:
        return False
    return bool(nombre_modelo())


def estado():
    try:
        import onnxruntime_genai  # noqa: F401
        motor = True
    except Exception as e:
        motor = False
        _EST['error'] = 'motor no instalado: %s' % e
    return {'motor': motor, 'modelo': nombre_modelo(), 'cargado': _EST['nombre'], 'error': _EST['error'],
            'modelos': [modelos.estado(n) for n in PREFERENCIA]}


def _cargar():
    n = nombre_modelo()
    if not n:
        raise RuntimeError('No hay ningún modelo de lenguaje descargado (Aprendizaje → Modelos de IA locales).')
    if _EST['nombre'] != n:
        import onnxruntime_genai as og
        _EST['modelo'] = og.Model(modelos.ruta(n))
        _EST['tok'] = og.Tokenizer(_EST['modelo'])
        _EST['nombre'] = n
    return _EST['modelo'], _EST['tok']


def generar(datos, pregunta, max_tokens=260, al_escribir=None):
    """Respuesta del modelo a `pregunta` usando SOLO `datos`. al_escribir(texto_parcial) se llama mientras escribe."""
    import onnxruntime_genai as og
    with _LOCK:                                    # una respuesta a la vez (el procesador va al 100 %)
        model, tok = _cargar()
        msgs = json.dumps([{'role': 'system', 'content': SISTEMA},
                           {'role': 'user', 'content': 'DATOS:\n%s\n\nPREGUNTA: %s' % (datos, pregunta)}],
                          ensure_ascii=False)
        prompt = tok.apply_chat_template(msgs, add_generation_prompt=True)
        ids = tok.encode(prompt)
        p = og.GeneratorParams(model)
        p.set_search_options(max_length=len(ids) + max_tokens, temperature=0.0)
        g = og.Generator(model, p)
        g.append_tokens(ids)
        st = tok.create_stream()
        out, n, t0 = '', 0, time.time()
        while not g.is_done() and n < max_tokens:
            g.generate_next_token()
            out += st.decode(g.get_next_tokens()[0])
            n += 1
            if al_escribir and n % 4 == 0:
                al_escribir(out)
        texto = _sin_repeticiones(out.strip())
        return {'texto': texto, 'tokens': n, 'segundos': round(time.time() - t0, 1), 'modelo': _EST['nombre'],
                'propuestas': propuestas(texto)}


def _sin_repeticiones(texto):
    """Quita frases repetidas (los modelos pequeños a veces entran en bucle) y una frase final cortada."""
    vistas, out = set(), []
    for fr in re.split(r'(?<=[.!?])\s+|\n+', texto):
        k = re.sub(r'\W+', ' ', fr.lower()).strip()
        if not k or k in vistas:
            continue
        vistas.add(k)
        out.append(fr.strip())
    if out and not re.search(r'[.!?)»"]$', out[-1]) and len(out) > 1 and not out[-1].upper().startswith('PROPUESTA'):
        out.pop()
    return '\n'.join(x for x in out if x)


def propuestas(texto):
    """Líneas 'PROPUESTA: aceptar 12' / 'PROPUESTA: ver 12' -> [{'accion', 'id'}] (la persona las confirma)."""
    out = []
    for acc, ident in re.findall(r'PROPUEST[AO]S?:?\s*(aceptar|ver|revisar)\s+(?:la\s+)?(?:partida\s+)?(?:n[ºo.]*\s*)?'
                                 r'([0-9]+[a-z]?)', texto, re.I):
        acc = 'ver' if acc.lower() == 'revisar' else acc
        x = {'accion': acc.lower(), 'id': ident}
        if x not in out:
            out.append(x)
    return out


# ------------------------------------------------------------------------------------------------ datos
def _eur(x):
    return ('%.2f €' % x).replace('.', ',') if x is not None else 'no consta'


def hechos_partida(f):
    """Frases con lo que la app ya ha calculado de la partida: el modelo solo las ordena y recomienda."""
    q = f['que_es']
    ud = q['unidad'] or 'ud'
    h = ['Se necesitan %s %s de "%s".' % (('%g' % (q['cantidad'] or 0)).replace('.', ','), ud, q['material'][:90])]
    for c in f['comprobaciones']:
        h.append('El texto del cliente tiene una incoherencia: %s' % c)
    dist = [o for o in f['ofertas'] if not o['referencia']]
    refs = [o for o in f['ofertas'] if o['referencia']]
    if not dist:
        h.append('Ningún distribuidor lo ha ofertado.')
    for o in dist:
        txt = '%s lo oferta a %s/%s' % (o['proveedor'], _eur(o['precio']), ud)
        if o['estado'] == 'revisar':
            txt += '; la app no está segura de que su línea sea este material'
        h.append(txt + '.')
        for a in o['alertas']:
            h.append('Aviso sobre %s: %s' % (o['proveedor'], a['t'][:220]))
        if o.get('aprendido'):
            h.append('Lo aprendido de decisiones anteriores: %s' % o['aprendido'][:200])
    if len(dist) > 1 and f['mejor']['proveedor']:
        h.append('El más barato es %s.' % f['mejor']['proveedor'])
    for o in refs:
        if o['precio'] and f['mejor']['precio']:
            h.append('La base de referencia %s (no se le compra) tiene %s/%s: el mejor distribuidor está %s.' % (
                o['proveedor'], _eur(o['precio']), ud, 'por debajo' if f['mejor']['precio'] <= o['precio'] else 'POR ENCIMA'))
    pe = f['precio_esperado']
    if pe:
        h.append('En otras obras se ha pagado/ofertado alrededor de %s/%s (%d precios).' % (_eur(pe['valor']), ud, pe['n']))
    for a in (f['antecedentes'] or [])[:2]:
        h.append('Antecedente: en la obra "%s" una partida parecida la dio más barata %s a %s.' % (
            a['obra'], a['mejor_proveedor'] or 'nadie', _eur(a['mejor_precio'])))
    h.append('Riesgo calculado: %d sobre 100%s.' % (f['riesgo'], (' por: ' + '; '.join(f['motivos'])) if f['motivos'] else ''))
    return '\n'.join('- ' + x for x in h)


def datos_partida(f):
    """Ficha de la partida (analisis_partida.py) en texto con etiquetas para el modelo."""
    q, pe = f['que_es'], f['precio_esperado']
    l = ['Partida Nº %s · código %s · %s' % (f['id'], f['codigo'] or '-', f['capitulo']),
         'Título del cliente: %s' % (f['resumen'] or '-')[:200],
         'Qué es: %s%s' % (q['familia'], (' · ' + ' · '.join(q['caracteristicas'])) if q['caracteristicas'] else ''),
         'Material a comprar: %s · cantidad %s %s%s' % (q['material'], ('%g' % (q['cantidad'] or 0)).replace('.', ','),
                                                         q['unidad'] or '', (' (%s)' % q['nota']) if q['nota'] else ''),
         'Precio del cliente: %s' % _eur(q['precio_cliente'])]
    if f['comprobaciones']:
        l.append('Incoherencias en el texto del cliente: ' + ' | '.join(f['comprobaciones']))
    for o in f['ofertas'] or []:
        l.append('Oferta de %s%s: %s · %s/ud%s · estado %s%s%s' % (
            o['proveedor'], ' (precio de REFERENCIA, no se le compra)' if o['referencia'] else '',
            (o['descripcion'] or '')[:120], _eur(o['precio']),
            (' · %+d %% frente al esperado' % round(o['desviacion'] * 100)) if o['desviacion'] is not None else '',
            o['estado'], (' · confianza %d %%' % round(o['confianza'] * 100)) if o['confianza'] is not None else '',
            (' · avisos: ' + ' | '.join(a['t'][:160] for a in o['alertas'])) if o['alertas'] else ''))
        if o.get('aprendido'):
            l.append('  Aprendido: ' + o['aprendido'][:200])
    if not f['ofertas']:
        l.append('Ofertas: ningún proveedor lo ha ofertado')
    if f['mejor']['proveedor']:
        l.append('Más barato entre distribuidores: %s a %s/ud' % (f['mejor']['proveedor'], _eur(f['mejor']['precio'])))
    l.append('Precio esperado (otras obras y referencias): %s' % (
        '%s/ud según %d precios (de %s a %s)' % (_eur(pe['valor']), pe['n'], _eur(pe['min']), _eur(pe['max'])) if pe
        else 'no consta'))
    for a in (f['antecedentes'] or [])[:3]:
        l.append('Antecedente: obra "%s", partida %s "%s" (parecido %d %%), más barato %s a %s' % (
            a['obra'], a['codigo'] or '', (a['resumen'] or a['texto'] or '')[:80], round(a['parecido'] * 100),
            a['mejor_proveedor'] or 'nadie', _eur(a['mejor_precio'])))
    l.append('Riesgo calculado por la app: %d/100%s' % (f['riesgo'], (' (' + '; '.join(f['motivos']) + ')') if f['motivos'] else ''))
    return '\n'.join(l)


def datos_obra(r):
    """Resumen de la obra para el modelo: proveedores, reparto y partidas a revisar."""
    from . import analisis_partida as AP
    l = ['Obra: %s · %d materiales del presupuesto' % (r.obra.nombre, len(r.materiales))]
    for x in r.totales_proveedores():
        l.append('Distribuidor %s: oferta %d materiales, total %s con las cantidades del proyecto%s' % (
            x['proveedor'], x['materiales'], _eur(x['total']), ' (el más barato en total)' if x['ganador'] else ''))
    filas, total, sin = r.reparto()
    l.append('Comprando cada material al más barato: %s en total; %d materiales sin oferta de nadie' % (_eur(total), sin))
    gan = next((x for x in r.totales_proveedores() if x['ganador']), None)
    if gan and len(r.distribuidores) > 1:
        dif = gan['total'] - total
        l.append('Pedir todo a %s cuesta %s; repartir al más barato cuesta %s: el reparto ahorra %s (pero son %d pedidos)'
                 % (gan['proveedor'], _eur(gan['total']), _eur(total), _eur(dif), sum(1 for x in filas if x['materiales'])))
    elif gan:
        l.append('Solo hay un distribuidor con ofertas (%s): no hay alternativa con la que comparar.' % gan['proveedor'])
    for x in filas:
        if x['materiales']:
            l.append('  Reparto: a %s %d materiales por %s' % (x['proveedor'], x['materiales'], _eur(x['importe'])))
    refs = [pv['nombre'] for pv in r.proveedores if pv.get('referencia')]
    if refs:
        n_ref = sum(len(v) for v in r.avisos_referencia.values())
        l.append('Base de referencia %s: %d avisos de precio más barato que los distribuidores' % (', '.join(refs), n_ref))
    rv = AP.a_revisar(r.fichas, maximo=12)
    l.append('Partidas a revisar (de más a menos riesgo):' if rv else 'Partidas a revisar: ninguna destacada')
    for f in rv:
        l.append('  Nº %s %s "%s": riesgo %d (%s)' % (f['id'], f['codigo'], (f['resumen'] or '')[:70], f['riesgo'],
                                                     '; '.join(f['motivos'])[:200]))
    return '\n'.join(l)


def datos_pregunta(r, pregunta, maximo=8):
    """Partidas relacionadas con la pregunta (por significado y palabras) + resumen de la obra."""
    from . import semantica as SE
    fichas = list(r.fichas.values())
    elegidas = []
    palabras = [w for w in re.findall(r'\w{4,}', pregunta.lower())]

    def texto_f(f):
        return ((f['resumen'] or '') + ' ' + f['que_es']['material'] + ' ' + ' '.join(f['que_es']['caracteristicas'])
                + ' ' + ' '.join(o['proveedor'] + ' ' + ' '.join(a['t'] for a in o['alertas']) for o in f['ofertas'])
                + ' ' + ' '.join(f['motivos'])).lower()
    if fichas and SE.disponible():
        vq = SE.vectores([pregunta], 'query')
        vf = SE.vectores([texto_f(f) for f in fichas], 'passage')
        if vq is not None and vf is not None:
            import numpy as np
            sim = vf @ vq[0]
            # significado + palabras de la pregunta presentes (también en los avisos) + que tenga ofertas
            extra = np.array([0.03 * sum(w in texto_f(f) for w in palabras) / max(1, len(palabras))
                              + (0.01 if f['ofertas'] else 0) for f in fichas])
            orden = (sim + extra).argsort()[::-1]
            elegidas = [fichas[i] for i in orden[:maximo]]
    if not elegidas:
        elegidas = sorted(fichas, key=lambda f: -sum(w in json.dumps(f, ensure_ascii=False).lower()
                                                    for w in palabras))[:maximo]
    tot = r.totales_proveedores()
    l = ['Obra "%s": %d materiales; distribuidores: %s.' % (
        r.obra.nombre, len(r.materiales), ', '.join('%s (%d materiales, %s)' % (x['proveedor'], x['materiales'],
                                                                           _eur(x['total'])) for x in tot) or 'ninguno'),
         '', 'PARTIDAS RELACIONADAS CON LA PREGUNTA (cada una con sus hechos):']
    for f in elegidas:
        q = f['que_es']
        hechos = ['se necesitan %s %s' % (('%g' % (q['cantidad'] or 0)).replace('.', ','), q['unidad'] or 'ud')]
        if q['caracteristicas']:
            hechos.append('características: ' + ', '.join(q['caracteristicas'][:5]))
        for c in f['comprobaciones']:
            hechos.append('INCOHERENCIA del cliente: ' + c[:150])
        dist = [o for o in f['ofertas'] if not o['referencia']]
        if not dist:
            hechos.append('ningún distribuidor lo oferta')
        for o in f['ofertas']:
            hechos.append('%s %s %s/%s' % ('referencia' if o['referencia'] else 'oferta de', o['proveedor'],
                                          _eur(o['precio']), q['unidad'] or 'ud'))
            for a in o['alertas'][:3]:
                hechos.append('AVISO (%s): %s' % (o['proveedor'], a['t'][:170]))
        l.append('- Partida Nº %s (código %s) "%s": %s.' % (f['id'], f['codigo'], (f['resumen'] or '')[:70],
                                                            '; '.join(hechos)))
    return '\n'.join(l)


PREGUNTA_PARTIDA = ('Con estos HECHOS, escribe para el técnico de compras 2-4 frases: qué pasa con la partida y qué '
                    'conviene hacer (aceptar, pedir aclaración al proveedor o al cliente, revisar el precio). No añadas '
                    'datos que no estén en los hechos. Si todo está bien, dilo en una frase.')
PREGUNTA_OBRA = ('Haz un resumen de la obra para el jefe de compras en 4-7 frases: a quién conviene pedir y por qué, el '
                 'ahorro SOLO si aparece en los datos, y las 3 partidas que más hay que revisar con su motivo, citándolas '
                 'como "Nº <número> (<código>)" tal como aparecen.')
PREGUNTA_LIBRE = ('Responde a la pregunta usando los hechos de cada partida. Cita las partidas como "Nº <número> '
                  '(<código>)". Si ninguna cumple, dilo. ')
INSTRUCCION_PROPUESTAS = ('Si recomiendas aceptar o revisar partidas concretas, añade al final una línea por partida '
                          'con el formato exacto "PROPUESTA: aceptar <Nº>" o "PROPUESTA: ver <Nº>".')
