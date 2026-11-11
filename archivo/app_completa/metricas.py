"""¿Está aprendiendo? (fase 5): números para saber si el aprendizaje funciona antes de ampliarlo.

Por obra:
    propuestos      emparejamientos que la app puso sola (automáticos + aprendidos), principales de distribuidores
    corregidos      correcciones manuales en esa obra (casar / descasar)
    sin_corregir    % de lo propuesto que no hubo que corregir = propuestos / (propuestos + corregidos)
    aceptados       confirmados con ✔ o pedidos
    aprendidos      emparejamientos aplicados por lo aprendido (fase 2); deshechos = corregidos que eran aprendidos
    horas_pedido    desde la primera oferta subida hasta el primer pedido generado
    desviaciones    ofertas con "precio fuera de lo normal" (fase 3)
Las obras se ordenan por fecha: si el aprendizaje funciona, sin_corregir sube y las horas bajan con el tiempo.
"""
import datetime
import json


def _fecha(t):
    try:
        return datetime.datetime.fromisoformat((t or '')[:19])
    except ValueError:
        return None


def por_obra(o, r, bbdd):
    nombre = o.nombre
    propuestos = aprendidos = desviaciones = 0
    for pv in r.distribuidores:
        for of in pv['ofertas'].values():
            if of.origen != 'manual':
                propuestos += 1
            if of.origen == 'aprendido':
                aprendidos += 1
            if any(t.startswith('Precio fuera de lo normal') for _, t in of.alertas):
                desviaciones += 1
    filas = [dict(x) for x in bbdd.c.execute('SELECT accion, cuando, datos, activo FROM decision WHERE obra=?', (nombre,))]
    corr = [f for f in filas if f['accion'] in ('casar', 'descasar') and f['activo']]
    deshechos = 0
    for f in corr:
        try:
            if json.loads(f['datos'] or '{}').get('origen_antes') == 'aprendido':
                deshechos += 1
        except ValueError:
            pass
    aceptados = sum(1 for f in filas if f['accion'] in ('aceptar', 'pedido') and f['activo'])
    primera_oferta = min((_fecha(h['cuando']) for h in o.estado['historial'] if h['tipo'] == 'proveedor'
                          and _fecha(h['cuando'])), default=None)
    primer_pedido = min((_fecha(f['cuando']) for f in filas if f['accion'] == 'pedido' and _fecha(f['cuando'])),
                        default=None)
    horas = round((primer_pedido - primera_oferta).total_seconds() / 3600, 1) \
        if primera_oferta and primer_pedido and primer_pedido >= primera_oferta else None
    total = propuestos + len(corr)
    return {'obra': nombre, 'creada': o.estado.get('creada'), 'propuestos': propuestos, 'corregidos': len(corr),
            'sin_corregir': round(propuestos / total, 3) if total else None, 'aceptados': aceptados,
            'aprendidos': aprendidos, 'deshechos': deshechos, 'horas_pedido': horas, 'desviaciones': desviaciones,
            'materiales': len(r.materiales)}


def calcular(obras_y_resultados, bbdd):
    from . import aprendizaje as A
    filas = [por_obra(o, r, bbdd) for o, r in obras_y_resultados]
    filas.sort(key=lambda f: f['creada'] or '')
    prop = sum(f['propuestos'] for f in filas)
    corr = sum(f['corregidos'] for f in filas)
    apr = sum(f['aprendidos'] for f in filas)
    des = sum(f['deshechos'] for f in filas)
    A.cargar(bbdd)
    return {'obras': filas,
            'global': {'obras': len(filas), 'propuestos': prop, 'corregidos': corr,
                       'sin_corregir': round(prop / (prop + corr), 3) if prop + corr else None,
                       'aprendidos': apr, 'deshechos': des,
                       'acierto_aprendido': round(1 - des / (apr + des), 3) if apr + des else None,
                       'desviaciones': sum(f['desviaciones'] for f in filas)},
            'modelo': A.estado()}
