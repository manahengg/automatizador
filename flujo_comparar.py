"""Comandos 'comparar' y 'aplicar': orquestan lectura, emparejamiento, hoja de revisión y BC3."""
import datetime
import hashlib
import json
import os
import shutil

from . import comparar as cmp
from .detectar import detectar
from .exportadores import bc3 as exp_bc3, comparacion as exp_cmp, diferencias as exp_dif, comparativa as exp_comp
from .procesar import _nombre_seguro, nombre_corto


def _leer(ruta):
    lector, motivo = detectar(ruta)
    if lector is None:
        raise ValueError('%s: %s' % (os.path.basename(ruta), motivo))
    return lector.leer(ruta)


def _sha(ruta):
    with open(ruta, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


_DOCS, _PAREJAS = {}, {}      # cachés en memoria: leer un PDF y emparejar cuesta segundos; con la app se pide muchas veces


def _clave(ruta):
    return (os.path.abspath(ruta), os.path.getmtime(ruta), os.path.getsize(ruta))


def _leer_cache(ruta):
    k = _clave(ruta)
    if k not in _DOCS:
        _DOCS[k] = _leer(ruta)
    return _DOCS[k]


def _emparejar_cache(lic_p, of_p, lic, of):
    k = (_clave(lic_p), _clave(of_p))
    if k not in _PAREJAS:
        _PAREJAS[k] = cmp.emparejar(lic, of)
    return _PAREJAS[k]


def _estados(parejas, elegidas):
    """Estado de cada línea elegida: el del programa si se quedó con su propuesta; 'elegido a mano' si no."""
    return {p.oferta.n: (p.estado if p.lic and elegidas.get(p.oferta.n) == p.lic.n else 'elegido a mano')
            for p in parejas if p.oferta.n in elegidas}


def _emitir(carpeta, lic, of, parejas, elegidas, cfg, nombre_bc3, revisado=False, reescribir_empar=False):
    """Escribe los ficheros de un proveedor (BC3, diferencias, LEEME y, si se pide, emparejamiento.xlsx) para unas elecciones."""
    doc, resumen = cmp.construir(lic, of, elegidas)
    exp_bc3.escribir(doc, os.path.join(carpeta, nombre_bc3), nombre=doc.nombre, propietario=cfg['bc3']['propietario'])
    if reescribir_empar:
        exp_cmp.escribir(parejas, cmp.hojas(lic), resumen, os.path.join(carpeta, 'emparejamiento.xlsx'), of.avisos, elegidas=elegidas)
    exp_dif.escribir(cmp.hojas(lic), cmp.hojas(of), elegidas, _estados(parejas, elegidas), resumen['proveedor'],
                     os.path.join(carpeta, 'diferencias.xlsx'))
    _leeme(carpeta, resumen, parejas, nombre_bc3, revisado=revisado)
    return resumen


def _resultado(carpeta, lic, of, parejas, elegidas, resumen):
    return {'carpeta': carpeta, 'resumen': resumen, 'parejas': parejas, 'avisos_oferta': of.avisos, 'lic': lic,
            'of_doc': of, 'of_hojas': cmp.hojas(of), 'elegidas': elegidas, 'proveedor': resumen['proveedor']}


def _leeme(carpeta, resumen, parejas, nombre_bc3, revisado=False):
    n = {e: sum(p.estado == e for p in parejas) for e in ('seguro', 'revisar', 'sin pareja')}
    t = ['COMPARACIÓN OFERTA %s <-> LICITACIÓN%s' % (resumen['proveedor'].upper(), ' (REVISADA)' if revisado else ''), '',
         'Partidas incluidas: %d' % resumen['partidas'],
         'Importe con precios de la licitación: %.2f €' % resumen['importe_licitacion'],
         'Importe con precios de %s:  %.2f €  (%+.2f %%)' % (resumen['proveedor'], resumen['importe_proveedor'],
                                                             resumen['diferencia_pct'] or 0), '']
    if not revisado:
        t += ['Emparejamiento: %d seguras, %d a revisar, %d sin pareja.' % (n['seguro'], n['revisar'], n['sin pareja']), '',
              'SIGUIENTE PASO: abre emparejamiento.xlsx, mira las filas amarillas y rojas, corrige la columna',
              '"%s" si hace falta y ejecuta:  python -m automatizador aplicar "%s"' % (exp_cmp.COL_EDITABLE, carpeta), '']
    t += ['Diferencias partida a partida: diferencias.xlsx (resumen por capítulo, detalle y mayores diferencias).', '']
    t += ['Para m4PRO: importa %s como presupuesto nuevo del proyecto de la licitación.' % nombre_bc3,
          'Sus partidas llevan los mismos códigos y cantidades que la licitación; solo cambia el precio.']
    with open(os.path.join(carpeta, 'LEEME.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(t) + '\n')


def _base_oferta(ruta_oferta):
    return _nombre_seguro(os.path.splitext(os.path.basename(ruta_oferta))[0])[:28].rstrip(' ._-')


def comparar_ficheros(ruta_lic, ruta_oferta, cfg, destino=None):
    sello = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    base = _base_oferta(ruta_oferta)
    carpeta = (os.path.join(destino, base) if destino
               else os.path.join(cfg['carpetas']['salida'], '%s_comparacion_%s' % (sello, base)))
    orig = os.path.join(carpeta, 'originales')
    os.makedirs(orig, exist_ok=True)
    lic_copia = os.path.join(orig, nombre_corto(os.path.basename(ruta_lic)))
    of_copia = os.path.join(orig, nombre_corto(os.path.basename(ruta_oferta)))
    if lic_copia == of_copia:
        of_copia = os.path.join(orig, 'oferta_' + os.path.basename(of_copia))
    try:
        shutil.copy2(ruta_lic, lic_copia)
        shutil.copy2(ruta_oferta, of_copia)
        lic, of = _leer_cache(lic_copia), _leer_cache(of_copia)
    except Exception:
        shutil.rmtree(carpeta, ignore_errors=True)       # no dejar carpetas vacías de intentos fallidos
        raise
    parejas = _emparejar_cache(lic_copia, of_copia, lic, of)
    elegidas = {p.oferta.n: p.lic.n for p in parejas if p.lic}
    nombre_bc3 = 'licitacion_con_precios_%s.bc3' % _nombre_seguro((of.proveedor or 'PROVEEDOR').strip())[:30]
    resumen = _emitir(carpeta, lic, of, parejas, elegidas, cfg, nombre_bc3, reescribir_empar=True)
    with open(os.path.join(carpeta, 'emparejamiento.json'), 'w', encoding='utf-8') as f:
        json.dump({'licitacion': os.path.basename(lic_copia), 'oferta': os.path.basename(of_copia),
                   'sha_licitacion': _sha(lic_copia), 'sha_oferta': _sha(of_copia), 'bc3': nombre_bc3,
                   'elegidas': {str(k): v for k, v in elegidas.items()}}, f, indent=1)
    return _resultado(carpeta, lic, of, parejas, elegidas, resumen)


def _meta(carpeta):
    with open(os.path.join(carpeta, 'emparejamiento.json'), encoding='utf-8') as f:
        return json.load(f)


def _cargar(carpeta):
    """Lee (con caché) los originales de la carpeta de un proveedor. Devuelve (lic, of, parejas, meta, rutas)."""
    meta = _meta(carpeta)
    lic_p, of_p = os.path.join(carpeta, 'originales', meta['licitacion']), os.path.join(carpeta, 'originales', meta['oferta'])
    if _sha(lic_p) != meta['sha_licitacion'] or _sha(of_p) != meta['sha_oferta']:
        raise ValueError('Los ficheros originales de esta carpeta han cambiado desde que se hizo el emparejamiento.')
    lic, of = _leer_cache(lic_p), _leer_cache(of_p)
    return lic, of, _emparejar_cache(lic_p, of_p, lic, of), meta


def _validar(elegidas, lic, of):
    nl, no = {h.n for h in cmp.hojas(lic)}, {h.n for h in cmp.hojas(of)}
    malas = [(o, l) for o, l in elegidas.items() if o not in no or l not in nl]
    if malas:
        raise ValueError('Números que no existen (línea oferta, nº licitación): %s' % malas)
    return no


def aplicar(ruta, cfg):
    """Orden 'aplicar': lee la columna editable de emparejamiento.xlsx y genera el BC3 *_revisado."""
    carpeta = ruta if os.path.isdir(ruta) else os.path.dirname(os.path.abspath(ruta))
    if not os.path.exists(os.path.join(carpeta, 'emparejamiento.json')):
        return aplicar_todo(carpeta, cfg)
    lic, of, parejas, meta = _cargar(carpeta)
    elegidas = exp_cmp.leer_elecciones(os.path.join(carpeta, 'emparejamiento.xlsx'))
    no = _validar(elegidas, lic, of)
    nombre = meta['bc3'].replace('.bc3', '_revisado.bc3')
    resumen = _emitir(carpeta, lic, of, parejas, elegidas, cfg, nombre, revisado=True)
    r = _resultado(carpeta, lic, of, parejas, elegidas, resumen)
    r.update(bc3=nombre, sin_incluir=len(no) - len(elegidas))
    return r


def _escribir_comparativa(carpeta, lic, resultados):
    return exp_comp.escribir(cmp.hojas(lic), resultados, os.path.join(carpeta, 'comparativa.xlsx'), lic.nombre)


def _leeme_comparativa(carpeta, app=False):
    t = ['COMPARATIVA DE OFERTAS', '',
         'comparativa.xlsx   -> resumen, importes por capítulo y por partida de cada proveedor',
         'Una carpeta por proveedor con:',
         '  licitacion_con_precios_<proveedor>.bc3   para importar en m4PRO',
         '  emparejamiento.xlsx                      qué línea de la oferta se ha asignado a cada partida de la licitación',
         '  diferencias.xlsx                         detalle partida a partida', '']
    t.append('Si cambias algún emparejamiento en la app, se regeneran todos los ficheros.' if app else
             'Si corriges algún emparejamiento:  python -m automatizador aplicar "%s"' % carpeta)
    with open(os.path.join(carpeta, 'LEEME.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(t) + '\n')


def comparativa(ruta_lic, rutas_ofertas, cfg, progreso=None, app=False):
    """UNA orden: licitación + N ofertas -> BC3 por proveedor, hojas de revisión y comparativa.xlsx.

    progreso: función opcional que recibe un texto con lo que se está haciendo (la usa la app para mostrarlo)."""
    avisar = progreso or (lambda texto: None)
    sello = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    carpeta = os.path.join(cfg['carpetas']['salida'], '%s_comparativa' % sello)
    os.makedirs(carpeta, exist_ok=True)
    resultados = []
    try:
        for k, of in enumerate(rutas_ofertas, 1):
            avisar('Leyendo y emparejando la oferta %d de %d: %s' % (k, len(rutas_ofertas), os.path.basename(of)))
            resultados.append(comparar_ficheros(ruta_lic, of, cfg, destino=carpeta))
        avisar('Generando la comparativa en Excel…')
        _escribir_comparativa(carpeta, resultados[0]['lic'], resultados)
    except Exception:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise
    _leeme_comparativa(carpeta, app)
    return {'carpeta': carpeta, 'resultados': resultados}


def _subs(carpeta):
    subs = sorted(d for d in os.listdir(carpeta) if os.path.exists(os.path.join(carpeta, d, 'emparejamiento.json')))
    if not subs:
        raise ValueError('No hay carpetas de proveedor con emparejamiento.json en %s' % carpeta)
    return subs


def aplicar_todo(carpeta, cfg):
    """Aplica las correcciones de cada subcarpeta de proveedor y rehace comparativa.xlsx."""
    resultados = [aplicar(os.path.join(carpeta, d), cfg) for d in _subs(carpeta)]
    _escribir_comparativa(carpeta, resultados[0]['lic'], resultados)
    return {'carpeta': carpeta, 'resultados': resultados}


# ---------------------------------------------------------------------------------------------- para la app
def anadir_ofertas(carpeta, rutas_ofertas, cfg, progreso=None):
    """Añade uno o varios presupuestos a una comparativa YA hecha, sin repetir nada de lo anterior.

    Reutiliza la licitación original guardada, empareja solo las ofertas nuevas, respeta las elecciones que ya
    hubieras hecho con los demás proveedores y rehace comparativa.xlsx con todos."""
    avisar = progreso or (lambda texto: None)
    subs = _subs(carpeta)
    meta = _meta(os.path.join(carpeta, subs[0]))
    lic = os.path.join(carpeta, subs[0], 'originales', meta['licitacion'])
    nuevas, vistos = [], set()
    for of in rutas_ofertas:
        b = _base_oferta(of)
        if b in subs or b in vistos:
            raise ValueError('Ya hay un presupuesto con el nombre "%s". Cambia el nombre del fichero o quita antes el anterior.' % b)
        vistos.add(b)
    try:
        for k, of in enumerate(rutas_ofertas, 1):
            avisar('Leyendo y emparejando el presupuesto nuevo %d de %d: %s' % (k, len(rutas_ofertas), os.path.basename(of)))
            nuevas.append(os.path.basename(comparar_ficheros(lic, of, cfg, destino=carpeta)['carpeta']))
        avisar('Rehaciendo la comparativa con todos los presupuestos…')
        return regenerar(carpeta, {}, cfg)
    except Exception:
        for d in nuevas:                                   # si algo falla, la comparativa queda como estaba
            shutil.rmtree(os.path.join(carpeta, d), ignore_errors=True)
        raise


def quitar_oferta(carpeta, sub, cfg):
    """Quita un presupuesto de la comparativa (borra su carpeta) y rehace comparativa.xlsx con los demás."""
    subs = _subs(carpeta)
    if sub not in subs:
        raise ValueError('No existe ese presupuesto en la comparativa.')
    if len(subs) == 1:
        raise ValueError('Es el único presupuesto: no se puede quitar. Crea una comparativa nueva si lo necesitas.')
    shutil.rmtree(os.path.join(carpeta, sub))
    return regenerar(carpeta, {}, cfg)


def _elegidas_guardadas(meta, parejas):
    if 'elegidas' in meta:
        return {int(k): v for k, v in meta['elegidas'].items()}
    return {p.oferta.n: p.lic.n for p in parejas if p.lic}


def regenerar(carpeta, elecciones, cfg):
    """Rehace TODOS los ficheros de una comparativa con las elecciones de una persona, sin pasar por el Excel.

    elecciones: {nombre de subcarpeta del proveedor: {nº línea oferta: nº partida licitación}}. Un proveedor que no
    aparezca conserva sus elecciones anteriores. Si algo no cuadra (nº inexistente, dos líneas para la misma partida)
    se lanza ValueError ANTES de tocar ningún fichero."""
    subs = _subs(carpeta)
    cargados = {}
    for d in subs:
        lic, of, parejas, meta = _cargar(os.path.join(carpeta, d))
        el = elecciones.get(d)
        el = {int(o): int(l) for o, l in el.items()} if el is not None else _elegidas_guardadas(meta, parejas)
        _validar(el, lic, of)
        cmp.construir(lic, of, el)                      # comprueba duplicados ("más de un precio")
        cargados[d] = (lic, of, parejas, meta, el)
    resultados = []
    for d, (lic, of, parejas, meta, el) in cargados.items():
        ruta = os.path.join(carpeta, d)
        resumen = _emitir(ruta, lic, of, parejas, el, cfg, meta['bc3'], revisado=True, reescribir_empar=True)
        meta['elegidas'] = {str(k): v for k, v in el.items()}
        with open(os.path.join(ruta, 'emparejamiento.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=1)
        resultados.append(_resultado(ruta, lic, of, parejas, el, resumen))
    _escribir_comparativa(carpeta, resultados[0]['lic'], resultados)
    _leeme_comparativa(carpeta, app=True)
    return {'carpeta': carpeta, 'resultados': resultados}


def datos_revision(carpeta):
    """Todo lo que la pantalla de revisión necesita, en estructuras simples (JSON)."""
    corto = exp_comp.S.corto
    lic, provs, usadas = None, [], set()

    def ref(h):
        if h is None:
            return None
        return {'n': h.n, 'desc': corto(h.partida.descripcion, 150), 'ruta': corto(h.ruta, 60), 'codigo': h.partida.codigo,
                'cant': h.partida.cantidad, 'precio': h.partida.precio}

    for d in _subs(carpeta):
        lic, of, parejas, meta = _cargar(os.path.join(carpeta, d))
        el = _elegidas_guardadas(meta, parejas)
        usadas |= set(el.values())
        _, resumen = cmp.construir(lic, of, el)
        filas = []
        for p in parejas:
            o = p.oferta.partida
            filas.append({'n': p.oferta.n, 'ruta': corto(p.oferta.ruta, 60), 'desc': corto(o.descripcion, 220),
                          'cant': o.cantidad, 'precio': o.precio, 'estado': p.estado, 'motivos': p.motivos,
                          'parecido': round(p.parecido, 2), 'propuesta': ref(p.lic),
                          'alternativas': [dict(ref(h), parecido=round(s, 2), motivo=cmp._explicar_candidato(p.oferta, h, s)) for s, h in p.alternativas],
                          'elegida': el.get(p.oferta.n)})
        suma = round(sum(x.importe_exacto for x in of.partidas()), 2)
        impreso = of.total_declarado
        provs.append({'id': d, 'nombre': resumen['proveedor'], 'fecha': of.fecha, 'validez': of.validez,
                      'caducada': exp_comp._caducada(of.validez), 'condiciones': exp_comp._condiciones(of),
                      'avisos': [{'nivel': a.nivel, 'texto': a.texto} for a in of.avisos if a.nivel in ('revisar', 'aviso')],
                      'resumen': resumen, 'impreso': impreso, 'suma': suma,
                      'cuadra': None if impreso is None else abs(suma - impreso) <= 0.05, 'filas': filas})
    L = [{'n': h.n, 'etiqueta': '%d · %s · %s' % (h.n, corto(h.ruta.split(' / ')[-1], 28), corto(h.partida.descripcion, 70)),
          'precio': h.partida.precio, 'cant': h.partida.cantidad} for h in cmp.hojas(lic)]
    cliente = round(sum(h.partida.importe for h in cmp.hojas(lic) if h.n in usadas), 2)
    return {'licitacion': lic.nombre, 'cliente_total': cliente, 'n_comparadas': len(usadas), 'lic_partidas': L, 'proveedores': provs}
