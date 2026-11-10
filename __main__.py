"""Línea de comandos:  python -m automatizador <orden>

  procesar        procesa una vez todo lo que haya en la carpeta de entrada
  vigilar         se queda mirando la carpeta de entrada y procesa lo que llegue (Ctrl+C para parar)
  uno RUTA        procesa un solo fichero SIN moverlo (útil para probar)
  estado          muestra los últimos documentos procesados
  comparar LICITACION OFERTA   empareja la oferta de un proveedor con la licitación y genera el BC3 de comparación
  comparativa LICITACION OFERTA [OFERTA ...]   UNA orden: BC3 por proveedor + comparativa.xlsx con todos
  aplicar CARPETA              regenera el BC3 tras corregir a mano emparejamiento.xlsx
  anadir CARPETA OFERTA [OFERTA…]   añade presupuestos nuevos a una comparativa ya hecha
  app [--puerto N] [--no-abrir]   abre la APP WEB local: subes licitación + ofertas, revisas en pantalla y descargas el .zip
"""
import argparse
import os
import sys
import time

from . import db
from .procesar import cargar_config, procesar_fichero, procesar_entrada


def _imprimir(r):
    marca = {'listo': 'LISTO   ', 'revisar': 'REVISAR ', 'pendiente': 'PENDIENTE', 'error': 'ERROR   '}[r['estado']]
    linea = '%s %s' % (marca, r['archivo'])
    if 'total_calculado' in r:
        linea += '  |  total %.2f €' % r['total_calculado']
        if r.get('total_declarado') is not None:
            linea += ' (documento: %.2f €)' % r['total_declarado']
    print(linea)
    if r['estado'] in ('pendiente', 'error'):
        print('     ', r['motivo'])
    for a in r.get('avisos', []):
        if a['nivel'] != 'info':
            print('      [%s] %s' % (a['nivel'].upper(), a['texto']))
    if r.get('salida'):
        print('      ->', r['salida'])


def main(argv=None):
    p = argparse.ArgumentParser(prog='automatizador', description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument('orden', choices=['procesar', 'vigilar', 'uno', 'estado', 'comparar', 'comparativa', 'aplicar', 'anadir', 'app'])
    p.add_argument('ruta', nargs='?')
    p.add_argument('oferta', nargs='*')
    p.add_argument('--config', default='config.yaml')
    p.add_argument('--puerto', type=int, default=8765)
    p.add_argument('--no-abrir', action='store_true', help='con la orden app: no abrir el navegador solo')
    a = p.parse_args(argv)
    cfg = cargar_config(a.config)
    if a.orden == 'procesar':
        if cfg.get('pausa'):
            print('El programa está en pausa (pausa: true en config.yaml).')
            return 0
        res = procesar_entrada(cfg)
        for r in res:
            _imprimir(r)
        if not res:
            print('No hay nada en', cfg['carpetas']['entrada'])
    elif a.orden == 'vigilar':
        print('Vigilando', cfg['carpetas']['entrada'], '(Ctrl+C para parar)')
        try:
            while True:
                cfg = cargar_config(a.config)       # se relee para que el interruptor de pausa surta efecto al momento
                if not cfg.get('pausa'):
                    for r in procesar_entrada(cfg):
                        _imprimir(r)
                time.sleep(cfg['intervalo_segundos'])
        except KeyboardInterrupt:
            print('Parado.')
    elif a.orden == 'uno':
        if not a.ruta:
            p.error('falta la ruta del fichero')
        _imprimir(procesar_fichero(a.ruta, cfg, mover=False))
    elif a.orden == 'comparar':
        if not (a.ruta and len(a.oferta) == 1):
            p.error('uso: comparar LICITACION OFERTA')
        from .flujo_comparar import comparar_ficheros
        try:
            r = comparar_ficheros(a.ruta, a.oferta[0], cfg)
        except (ValueError, OSError) as e:
            print('ERROR:', e)
            return 1
        res, n = r['resumen'], {e: sum(x.estado == e for x in r['parejas']) for e in ('seguro', 'revisar', 'sin pareja')}
        print('Oferta de %s: %d líneas -> %d seguras, %d a revisar, %d sin pareja' % (res['proveedor'], len(r['parejas']), n['seguro'], n['revisar'], n['sin pareja']))
        print('Licitación %.2f €  |  %s %.2f €  (%+.2f %%)' % (res['importe_licitacion'], res['proveedor'], res['importe_proveedor'], res['diferencia_pct'] or 0))
        print('Siguiente paso: revisa emparejamiento.xlsx y ejecuta  python -m automatizador aplicar "%s"' % r['carpeta'])
        print('->', r['carpeta'])
    elif a.orden == 'comparativa':
        if not (a.ruta and a.oferta):
            p.error('uso: comparativa LICITACION OFERTA [OFERTA ...]')
        from .flujo_comparar import comparativa
        try:
            r = comparativa(a.ruta, a.oferta, cfg)
        except (ValueError, OSError) as e:
            print('ERROR:', e)
            return 1
        for x in r['resultados']:
            res, n = x['resumen'], {e: sum(q.estado == e for q in x['parejas']) for e in ('seguro', 'revisar', 'sin pareja')}
            print('%-18s %d líneas: %d seguras, %d a revisar, %d sin pareja | licitación %.2f €, oferta %.2f € (%+.2f %%)' % (
                res['proveedor'], len(x['parejas']), n['seguro'], n['revisar'], n['sin pareja'],
                res['importe_licitacion'], res['importe_proveedor'], res['diferencia_pct'] or 0))
        print('Comparativa en:', r['carpeta'])
    elif a.orden == 'aplicar':
        if not a.ruta:
            p.error('uso: aplicar CARPETA')
        from .flujo_comparar import aplicar
        try:
            r = aplicar(a.ruta, cfg)
        except ValueError as e:
            print('ERROR:', e)
            return 1
        res = r['resumen']
        print('Generado %s con %d partidas: licitación %.2f €, %s %.2f € (%+.2f %%)' % (r['bc3'], res['partidas'], res['importe_licitacion'], res['proveedor'], res['importe_proveedor'], res['diferencia_pct'] or 0))
        print('Líneas de la oferta que NO se han incluido:', r['sin_incluir'])
        print('->', r['carpeta'])
    elif a.orden == 'anadir':
        if not (a.ruta and a.oferta):
            p.error('uso: anadir CARPETA OFERTA [OFERTA ...]')
        from .flujo_comparar import anadir_ofertas
        try:
            r = anadir_ofertas(a.ruta, a.oferta, cfg, progreso=print)
        except (ValueError, OSError) as e:
            print('ERROR:', e)
            return 1
        print('Comparativa actualizada con %d proveedores en: %s' % (len(r['resultados']), r['carpeta']))
    elif a.orden == 'app':
        from .app_web import servir
        try:
            c = db.conectar(cfg['_db'])
            c.close()

            servir(cfg, puerto=a.puerto, abrir=not a.no_abrir)
        except OSError as e:
            print('ERROR:', e)
            return 1
    elif a.orden == 'estado':
        c = db.conectar(cfg['_db'])
        for f in db.ultimos(c):
            print('%s  %-9s %-34s %s' % (f['creado'], f['estado'], f['archivo'][:34], f['carpeta_salida'] or ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
