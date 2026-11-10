"""Procesa un documento de principio a fin: detectar -> leer -> validar -> exportar -> registrar -> archivar."""
import datetime
import json
import os
import shutil
import traceback

import yaml

from . import db
from .detectar import detectar
from .exportadores import bc3 as exp_bc3, revision


def cargar_config(ruta='config.yaml'):
    with open(ruta, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    base = os.path.dirname(os.path.abspath(ruta))
    cfg['_base'] = base
    datos = os.environ.get('AUTOMATIZADOR_DATOS') or base      # el lanzador portátil fija una carpeta de datos corta y escribible
    for k, v in cfg['carpetas'].items():
        cfg['carpetas'][k] = v if os.path.isabs(v) else os.path.join(datos, v)
        os.makedirs(cfg['carpetas'][k], exist_ok=True)
    cfg['_db'] = os.path.join(datos, 'datos', 'automatizador.db')
    return cfg


def nombre_corto(nombre, maximo=40):
    """Acorta un nombre de fichero conservando la extensión (Windows falla con rutas de más de 260 caracteres)."""
    base, ext = os.path.splitext(nombre)
    return base[:maximo].rstrip(' ._-') + ext if len(base) > maximo else nombre


def _nombre_seguro(nombre):
    return ''.join(c if c.isalnum() or c in '-_.' else '_' for c in nombre)


def _archivar(origen, destino_dir, sello, mover):
    destino = os.path.join(destino_dir, '%s_%s' % (sello, os.path.basename(origen)))
    (shutil.move if mover else shutil.copy2)(origen, destino)
    return destino


def _escribir_leeme(carpeta, nombre, estado, doc):
    lineas = ['DOCUMENTO: %s' % nombre, 'ESTADO: %s' % {
        'listo': 'LISTO para importar en m4PRO (sin avisos que requieran revisión)',
        'revisar': 'REVISAR antes de importar (hay avisos marcados como REVISAR)'}[estado], '',
        'Total calculado: %.2f €' % doc.importe]
    if doc.total_declarado is not None:
        lineas.append('Total que declara el documento: %.2f €' % doc.total_declarado)
    lineas += ['', 'AVISOS:']
    orden = {'revisar': 0, 'aviso': 1, 'info': 2}
    for a in sorted(doc.avisos, key=lambda a: orden[a.nivel]):
        lineas.append('  [%s] %s' % (a.nivel.upper(), a.texto))
    lineas += ['', 'Ficheros: %s.bc3 (para importar en m4PRO) y %s_revision.xlsx (para mirar a mano).' % (
        os.path.splitext(nombre)[0], os.path.splitext(nombre)[0])]
    with open(os.path.join(carpeta, 'LEEME.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lineas) + '\n')


def procesar_fichero(ruta, cfg, mover=True, conexion=None):
    """Devuelve un diccionario con el resultado. Nunca lanza excepciones por un documento malo."""
    c = conexion or db.conectar(cfg['_db'])
    nombre = os.path.basename(ruta)
    sello = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    car = cfg['carpetas']
    try:
        lector, motivo = detectar(ruta)
        if lector is None:
            destino = _archivar(ruta, car['pendientes'], sello, mover)
            with open(destino + '.motivo.txt', 'w', encoding='utf-8') as f:
                f.write(motivo + '\n')
            did = db.registrar(c, nombre, 'pendiente', avisos=[motivo])
            db.evento(c, 'pendiente', motivo, did)
            return {'archivo': nombre, 'estado': 'pendiente', 'motivo': motivo}
        doc = lector.leer(ruta)
        base = os.path.splitext(_nombre_seguro(nombre))[0]
        salida = os.path.join(car['salida'], '%s_%s' % (sello, base))
        os.makedirs(salida, exist_ok=True)
        exp_bc3.escribir(doc, os.path.join(salida, base + '.bc3'),
                         nombre=doc.nombre or base, propietario=cfg['bc3']['propietario'])
        revision.escribir(doc, os.path.join(salida, base + '_revision.xlsx'))
        estado = 'revisar' if any(a.nivel == 'revisar' for a in doc.avisos) else 'listo'
        _escribir_leeme(salida, nombre, estado, doc)
        avisos = [{'nivel': a.nivel, 'texto': a.texto} for a in doc.avisos]
        with open(os.path.join(salida, 'resumen.json'), 'w', encoding='utf-8') as f:
            json.dump({'archivo': nombre, 'lector': lector.__name__.split('.')[-1], 'estado': estado,
                       'total_calculado': doc.importe, 'total_declarado': doc.total_declarado, 'avisos': avisos},
                      f, ensure_ascii=False, indent=1)
        _archivar(ruta, car['procesados'], sello, mover)
        did = db.registrar(c, nombre, estado, lector.__name__.split('.')[-1], doc, avisos, salida)
        db.evento(c, 'procesado', '%s -> %s' % (nombre, estado), did)
        return {'archivo': nombre, 'estado': estado, 'lector': lector.__name__.split('.')[-1],
                'total_calculado': doc.importe, 'total_declarado': doc.total_declarado,
                'avisos': avisos, 'salida': salida, 'documento': doc}
    except Exception:
        detalle = traceback.format_exc()
        try:
            destino = _archivar(ruta, car['errores'], sello, mover)
            with open(destino + '.error.txt', 'w', encoding='utf-8') as f:
                f.write(detalle)
        except Exception:
            pass
        did = db.registrar(c, nombre, 'error', avisos=[detalle.splitlines()[-1]])
        db.evento(c, 'error', detalle, did)
        return {'archivo': nombre, 'estado': 'error', 'motivo': detalle.splitlines()[-1]}


def _estable(ruta, espera=1.0):
    """Evita leer un fichero que aún se está copiando: su tamaño debe quedar quieto."""
    import time
    a = os.path.getsize(ruta)
    time.sleep(espera)
    return a == os.path.getsize(ruta)


def procesar_entrada(cfg):
    resultados = []
    for nombre in sorted(os.listdir(cfg['carpetas']['entrada'])):
        ruta = os.path.join(cfg['carpetas']['entrada'], nombre)
        if not os.path.isfile(ruta) or nombre.startswith(('~$', '.')):
            continue
        if not _estable(ruta, 0.5):
            continue
        resultados.append(procesar_fichero(ruta, cfg))
    return resultados
