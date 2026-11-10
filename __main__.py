"""Línea de comandos:  python -m automatizador <orden>

  app [--puerto N] [--no-abrir]
        Abre la APP WEB local (lo normal): obras, ofertas, comparativa, correcciones, Excel y base de datos de precios.

  comparar CLIENTE OFERTA [OFERTA ...] [--obra NOMBRE] [-o salida.xlsx]
        Todo de una vez sin abrir la app: crea/actualiza la obra, añade las ofertas, guarda los precios en la base de
        datos y genera el Excel comparativo.

  bbdd TEXTO
        Busca un material en la base de datos de precios (p. ej.:  bbdd "1x35 rz1-k").

Los datos (obras y base de datos precios.db) se guardan en la carpeta indicada por la variable AUTOMATIZADOR_DATOS o,
si no existe, en "automatizador_datos" junto a la carpeta del programa.
"""
import argparse
import os
import sys


def main(argv=None):
    p = argparse.ArgumentParser(prog='automatizador', description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument('orden', choices=['app', 'comparar', 'bbdd'])
    p.add_argument('rutas', nargs='*')
    p.add_argument('--obra', help='nombre de la obra (por defecto, el nombre del fichero del cliente)')
    p.add_argument('-o', '--salida', help='ruta del Excel a generar')
    p.add_argument('--puerto', type=int, default=8765)
    p.add_argument('--no-abrir', action='store_true', help='con la orden app: no abrir el navegador')
    a = p.parse_args(argv)

    if a.orden == 'app':
        from .app_web import servir
        servir(a.puerto, abrir=not a.no_abrir)
        return 0

    from .bbdd import BBDD
    from .obra import Obra, ruta_bbdd
    db = BBDD(ruta_bbdd())
    if a.orden == 'bbdd':
        filas = db.buscar(' '.join(a.rutas))
        for f in filas:
            print('%-28s %-16s %10.4f €  %-10s %-20s %s' % ((f['clave_material'] or '')[:28], f['proveedor'][:16],
                                                           f['precio_neto'], f['fecha'] or '', f['obra'][:20],
                                                           f['descripcion'][:60]))
        if not filas:
            print('Sin resultados.', db.resumen())
        return 0

    if len(a.rutas) < 2:
        p.error('uso: comparar CLIENTE OFERTA [OFERTA ...]')
    from .exportadores import excel_comparativa
    cliente, ofertas = a.rutas[0], a.rutas[1:]
    try:
        o = Obra.crear(a.obra or os.path.splitext(os.path.basename(cliente))[0])
        o.poner_cliente(cliente, progreso=print)
        for f in ofertas:
            prov, d = o.anadir_proveedor(f, progreso=print)
            print('Oferta de %s: %d líneas' % (prov, sum(1 for _ in d.partidas())))
        r = o.analizar(db, progreso=print)
        salida = a.salida or os.path.join(o.carpeta, 'comparativa_%s.xlsx' % o.ident)
        excel_comparativa.escribir(r, salida)
    except (ValueError, OSError) as e:
        print('ERROR:', e)
        return 1
    for pv in r.proveedores:
        print('%-16s %3d líneas · %3d casadas · %3d materiales cubiertos de %d' % (
            pv['nombre'], len(pv['lineas']), len(pv['lineas']) - len(pv['sin']), len(pv['ofertas']), len(r.materiales)))
    print('Excel:', salida)
    return 0


if __name__ == '__main__':
    sys.exit(main())
