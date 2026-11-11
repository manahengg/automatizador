"""Análisis partida a partida (fase 3): una FICHA por material con todo lo que la app sabe de él.

    que_es          tipo de producto y características leídas del texto, material y cantidad real a comprar
    comprobaciones  incoherencias del texto del cliente (IP imposible, potencias distintas, paréntesis sin cerrar...)
    ofertas         cada proveedor: precio, estado, confianza del modelo, lo aprendido, alertas
    precio_esperado mediana de lo pagado/ofertado antes por el mismo material o partidas parecidas (otras obras) y la
                    base de referencia (Junta): "≈ 4,20 €/m según 7 precios"
    antecedentes    partidas parecidas de otras obras: qué se ofertó, quién fue el más barato, a qué precio
    riesgo          0-100 con sus motivos, para ordenar qué revisar primero
Además añade a las ofertas la alerta "precio fuera de lo normal" cuando se aleja mucho del precio esperado.
"""
import statistics

from . import electrico as E

NOMBRES_ATR = [('seccion', 'sección %s mm²'), ('tipo_cable', '%s'), ('material', '%s'), ('diametro', 'Ø%s mm'),
               ('potencia_w', '%s W'), ('lumenes', '%s lm'), ('temp_color', '%s K'), ('ip', 'IP%s'), ('polos', '%s polos'),
               ('amperios', '%s A'), ('sensibilidad_ma', '%s mA'), ('kwp', '%s kWp'), ('optica', 'óptica %s'),
               ('longitud_mm', '%s mm'), ('wp', '%s Wp'), ('tension', '%s'), ('fases', '%s'), ('dimensiones', '%s'),
               ('polaridad', '%s'), ('halogenos', 'halógenos: %s')]


def _fmt(v):
    if isinstance(v, (set, frozenset, list, tuple)):
        return '/'.join(dict.fromkeys(_fmt(x) for x in sorted(v, key=str)))
    if isinstance(v, float):
        return ('%g' % v).replace('.', ',')
    return str(v)


def caracteristicas(at):
    out = []
    for k, patron in NOMBRES_ATR:
        v = at.get(k)
        if v not in (None, '', set(), []):
            out.append(patron % _fmt(v))
    return out


def _precio_esperado(res, m):
    """Mediana de precios unitarios de otras obras para este material (mismo material o partidas muy parecidas)."""
    vals, fuentes = [], []
    h = res.historico.get(m.id)
    if h:
        for f in h['ultimos']:
            if f.get('precio_neto'):
                vals.append(f['precio_neto'])
                fuentes.append('%s %.4g € (%s, obra "%s")' % (f['proveedor'], f['precio_neto'], f.get('fecha') or '',
                                                              f['obra']))
    for p in res.parecidas.get(m.id, []):
        if p.get('mejor_precio') and p['parecido'] >= 0.93 and (p.get('unidad') or '').lower() == (m.unidad or '').lower():
            vals.append(p['mejor_precio'])
            fuentes.append('%s %.4g € (partida parecida %d %% en "%s")' % (p.get('mejor_proveedor') or '?',
                                                                         p['mejor_precio'], round(p['parecido'] * 100),
                                                                         p['obra']))
    for pv in res.proveedores:
        if pv.get('referencia') and m.id in pv['ofertas'] and pv['ofertas'][m.id].precio:
            vals.append(pv['ofertas'][m.id].precio)
            fuentes.append('%s %.4g € (referencia)' % (pv['nombre'], pv['ofertas'][m.id].precio))
    if len(vals) < 2:
        return None
    return {'valor': round(statistics.median(vals), 4), 'n': len(vals), 'min': round(min(vals), 4),
            'max': round(max(vals), 4), 'fuentes': fuentes[:8]}


def analizar(res):
    """Calcula res.fichas {material_id: ficha} y añade las alertas de precio anómalo a las ofertas."""
    res.fichas = {}
    for m in res.materiales:
        esperado = _precio_esperado(res, m)
        ofertas = []
        motivos = []
        riesgo = 0
        for pv in res.proveedores:
            o = pv['ofertas'].get(m.id)
            if not o:
                continue
            desv = None
            if esperado and o.precio and not pv.get('referencia') and esperado['n'] >= 3:
                desv = o.precio / esperado['valor'] - 1
                if desv > 0.5 or desv < -0.5:
                    t = ('Precio fuera de lo normal: %.4g € frente a ≈ %.4g € esperado (%d precios de otras obras y '
                         'referencias, de %.4g a %.4g €). %s' % (
                             o.precio, esperado['valor'], esperado['n'], esperado['min'], esperado['max'],
                             'Comprobar que es el mismo artículo y la misma unidad.' if desv > 0.5 else
                             'Muy barato: comprobar que es el mismo artículo, la cantidad y la unidad.'))
                    if not any(t2.startswith('Precio fuera de lo normal') for _, t2 in o.alertas):
                        o.alertas.append(('media', t))
            ofertas.append({'proveedor': pv['nombre'], 'referencia': bool(pv.get('referencia')), 'precio': o.precio,
                            'importe': o.importe, 'codigos': o.codigos, 'descripcion': o.descripcion[:300],
                            'estado': o.estado, 'confianza': o.confianza, 'aprendido': o.aprendido,
                            'desviacion': round(desv, 3) if desv is not None else None,
                            'alertas': [{'g': g, 't': t} for g, t in o.alertas]})
        dist = [x for x in ofertas if not x['referencia']]
        nom, mejor = res.mas_barato(m)
        # riesgo: qué revisar primero
        if not dist:
            riesgo += 5                     # sin ofertas no hay nada que decidir todavía: no encabeza la lista
            motivos.append('ningún distribuidor lo oferta')
        graves = sum(1 for x in dist for a in x['alertas'] if a['g'] == 'alta')
        if graves:
            riesgo += min(40, 25 * graves)
            motivos.append('%d alerta(s) grave(s) en las ofertas' % graves)
        if m.alertas_cliente:
            riesgo += min(30, 20 * len(m.alertas_cliente))
            motivos.append('texto del cliente con incoherencias')
        if any(x['estado'] == 'revisar' for x in dist):
            riesgo += 20
            motivos.append('emparejamiento a revisar')
        bajas = [x['confianza'] for x in dist if x['confianza'] is not None and x['confianza'] < 0.6]
        if bajas:
            riesgo += 15
            motivos.append('confianza baja del modelo (%d %%)' % round(min(bajas) * 100))
        fuera = [x for x in dist if x['desviacion'] is not None and abs(x['desviacion']) > 0.5]
        if fuera:
            riesgo += 20
            motivos.append('precio fuera de lo normal (%s)' % ', '.join(x['proveedor'] for x in fuera))
        medias = [a['t'] for x in dist for a in x['alertas'] if a['g'] == 'media']
        if medias:
            riesgo += min(30, 15 * len(medias))
            primero = medias[0].split(':')[0][:70]
            motivos.append(primero + (' (+%d avisos más)' % (len(medias) - 1) if len(medias) > 1 else ''))
        conf = [x['confianza'] for x in dist if x['confianza'] is not None]
        res.fichas[m.id] = {
            'id': m.id, 'n': m.n, 'codigo': (m.codigo or '').strip(), 'resumen': m.partida.resumen or '',
            'descripcion': m.partida.descripcion or '', 'capitulo': ' / '.join(m.ruta[-2:]),
            'que_es': {'familia': (m.atributos.get('familia') or 'sin clasificar').replace('_', ' '),
                       'caracteristicas': caracteristicas(m.atributos), 'material': m.descripcion,
                       'cantidad': m.cantidad, 'unidad': m.unidad, 'nota': m.nota,
                       'cantidad_partida': m.partida.cantidad, 'precio_cliente': m.partida.precio},
            'comprobaciones': list(m.alertas_cliente),
            'ofertas': ofertas, 'mejor': {'proveedor': nom, 'precio': mejor},
            'precio_esperado': esperado,
            'antecedentes': [{k: p.get(k) for k in ('obra', 'codigo', 'resumen', 'texto', 'parecido', 'mejor_proveedor',
                                                     'mejor_precio', 'unidad', 'cantidad', 'ofertas')}
                             for p in res.parecidas.get(m.id, [])],
            'aprendido': res.avisos_aprendidos(m),
            'riesgo': min(100, riesgo), 'motivos': motivos,
            'confianza': round(min(conf), 3) if conf else None,
        }
    return res.fichas


def a_revisar(fichas, minimo=15, maximo=25):
    """Las partidas con ofertas y más riesgo, de mayor a menor (lo que hay que decidir)."""
    xs = sorted((f for f in fichas.values() if f['riesgo'] >= minimo and any(not o['referencia'] for o in f['ofertas'])),
                key=lambda f: (-f['riesgo'], f['n']))
    return xs[:maximo]
