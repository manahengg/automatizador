"""Bases de precios GLOBALES (p. ej. la de la Junta de Extremadura): un proveedor de referencia presente en TODAS las obras.

De dónde salen:
  recursos/bases_precios/*.xlsx              incluidas con la app (la de la Junta 2026): están siempre
  <carpeta compartida>/bases_precios/*.xlsx  las que sube cualquier persona en "Base de datos de precios"
Cada obra las añade sola a su análisis como proveedor de REFERENCIA (columna propia, se casa en modo catálogo, avisa
cuando es más barata que los distribuidores; no cuenta para el "más bajo" ni recibe pedidos). Sus precios se guardan una
vez en la BBDD de precios (obra "(bases de precios)").
Quitar una base: la subida se borra; una incluida con la app se desactiva con un fichero marca
'desactivada_<huella>' en la carpeta compartida (nunca se modifica un fichero existente).
"""
import hashlib
import os
import re
import shutil

from . import compartido as C

OBRA_BBDD = '(bases de precios)'
INCLUIDAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recursos', 'bases_precios')


def _huella(ruta):
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for trozo in iter(lambda: f.read(1 << 20), b''):
            h.update(trozo)
    return h.hexdigest()[:20]


def dir_compartida():
    return os.path.join(C.carpeta_compartida(), 'bases_precios')


def _desactivadas():
    d = dir_compartida()
    if not os.path.isdir(d):
        return set()
    return {n[len('desactivada_'):] for n in os.listdir(d) if n.startswith('desactivada_')}


def listar(todas=False):
    """[{'ruta', 'archivo', 'huella', 'origen': 'app'|'compartida', 'activa'}]"""
    out, vistas = [], set()
    off = _desactivadas()
    for origen, d in (('compartida', dir_compartida()), ('app', INCLUIDAS)):
        if not os.path.isdir(d):
            continue
        for n in sorted(os.listdir(d)):
            if not n.lower().endswith(('.xlsx', '.xlsm')) or n.startswith('~$'):
                continue
            ruta = os.path.join(d, n)
            h = _huella(ruta)
            if h in vistas:
                continue
            vistas.add(h)
            x = {'ruta': ruta, 'archivo': re.sub(r'^[0-9a-f]{10}_', '', n), 'huella': h, 'origen': origen,
                 'activa': h not in off}
            if x['activa'] or todas:
                out.append(x)
    return out


def anadir(ruta_origen, nombre_fichero=None):
    from .lectores import base_precios
    if not base_precios.reconoce(ruta_origen):
        raise ValueError('No es una base de precios en el formato esperado (Excel con columnas "Cód. Familia/Cap./Padre", '
                         '"Tipo", "Código elemento", "Precio de coste"...).')
    h = _huella(ruta_origen)
    d = dir_compartida()
    os.makedirs(d, exist_ok=True)
    marca = os.path.join(d, 'desactivada_' + h)
    if os.path.exists(marca):
        os.remove(marca)                    # se vuelve a activar
    if any(b['huella'] == h for b in listar(todas=True)):
        return h
    nombre = re.sub(r'[^\w\-. ]+', '_', os.path.basename(nombre_fichero or ruta_origen))
    destino = os.path.join(d, '%s_%s' % (h[:10], nombre))
    tmp = os.path.join(d, '~$' + os.path.basename(destino))
    shutil.copyfile(ruta_origen, tmp)
    os.replace(tmp, destino)
    return h


def quitar(huella):
    b = next((x for x in listar(todas=True) if x['huella'] == huella), None)
    if not b:
        raise ValueError('No existe esa base de precios.')
    if b['origen'] == 'compartida':
        os.remove(b['ruta'])
    else:
        d = dir_compartida()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'desactivada_' + huella), 'w') as f:
            f.write('desactivada por %s\n' % C.usuario())
