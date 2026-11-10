"""App web LOCAL:  python -m automatizador app      (se abre en http://127.0.0.1:8765)

Flujo:
  1. Crear una obra.
  2. Subir el presupuesto del cliente (BC3, PDF o Excel).
  3. Añadir ofertas de proveedores al principio o en cualquier momento (PDF con texto o escaneado, Excel).
  4. Revisar la comparativa, las alertas y corregir a mano los emparejamientos dudosos (se aprenden para el futuro).
  5. Descargar el Excel.
  Pestaña "Base de datos": buscar cualquier material y ver a qué precio lo tiene cada proveedor.

Solo usa la librería estándar de Python. Escucha ÚNICAMENTE en 127.0.0.1: nadie de la red puede entrar y los ficheros no
salen del ordenador.
"""
import email
import email.policy
import json
import os
import re
import shutil
import tempfile
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import emparejar as M
from .app_html import PAGINA
from .bbdd import BBDD
from .obra import Obra, ruta_bbdd
from .exportadores import excel_comparativa

MAX_SUBIDA = 300 * 1024 * 1024
BLOQUEO = threading.RLock()        # una operación pesada cada vez (OCR, análisis, escritura)
_CACHE = {}                         # id obra -> (marca, Resultado)
_DB = None


def db():
    global _DB
    if _DB is None:
        _DB = BBDD(ruta_bbdd())
    return _DB


def parsear_multipart(content_type, cuerpo):
    """[(campo, nombre_fichero|None, bytes)] de un formulario multipart (sin el módulo cgi, retirado de Python)."""
    msg = email.message_from_bytes(b'Content-Type: ' + content_type.encode('latin-1') + b'\r\n\r\n' + cuerpo,
                                   policy=email.policy.HTTP)
    if not msg.is_multipart():
        raise ValueError('El formulario no es multipart.')
    return [(p.get_param('name', header='content-disposition'), p.get_filename(), p.get_payload(decode=True) or b'')
            for p in msg.iter_parts()]


def _marca(o):
    ficheros = [os.path.join(o.carpeta, 'estado.json')]
    return tuple(os.path.getmtime(f) for f in ficheros if os.path.exists(f))


def analisis(o, forzar=False):
    with BLOQUEO:
        m = _marca(o)
        c = _CACHE.get(o.ident)
        if c and c[0] == m and not forzar:
            return c[1]
        r = o.analizar(db())
        _CACHE[o.ident] = (m, r)
        return r


def _n(x, d=2):
    return None if x is None else round(x, d)


def datos_obra(o):
    e = o.estado
    base = {'id': o.ident, 'nombre': o.nombre, 'cliente': e.get('cliente'),
            'proveedores': [{'nombre': p['nombre'], 'archivo': os.path.basename(p['archivo']), 'anadida': p.get('anadida')}
                            for p in e['proveedores']]}
    if not e.get('cliente'):
        return base
    r = analisis(o)
    provs = r.proveedores
    mats = []
    for m in r.materiales:
        fila = {'id': m.id, 'n': m.n, 'codigo': m.codigo, 'cap': m.ruta[-1] if m.ruta else '', 'primero': m.primero,
                'resumen': (m.partida.resumen or m.partida.descripcion)[:160], 'material': m.descripcion, 'nota': m.nota,
                'ud': m.unidad, 'cant_partida': m.partida.cantidad, 'cant': _n(m.cantidad, 3), 'precio_cli': m.partida.precio,
                'alertas_cli': m.alertas_cliente, 'prov': {}}
        for pv in provs:
            of = pv['ofertas'].get(m.id)
            if of:
                fila['prov'][pv['nombre']] = {
                    'codigos': of.codigos, 'desc': of.descripcion[:300], 'cant': of.cant_prov, 'precio': _n(of.precio, 4),
                    'importe': _n(of.importe), 'estado': of.estado, 'punt': _n(of.puntuacion),
                    'alertas': [{'g': g, 't': t} for g, t in of.alertas],
                    'dcant': M.comparacion_cantidad(of.cant_prov, m.cantidad)}
        fila['aprendido'] = r.avisos_aprendidos(m)
        nom, pr = r.mas_barato(m)
        fila['mejor'] = {'prov': nom, 'precio': _n(pr, 4), 'importe': _n(pr * m.cantidad if pr else None)}
        h = r.historico.get(m.id)
        if h:
            fila['bbdd'] = {'aviso': h['aviso'], 'ultimos': [
                {'prov': x['proveedor'], 'precio': _n(x['precio_neto'], 4), 'fecha': x['fecha'], 'obra': x['obra'],
                 'desc': x['descripcion'][:90], 'motivo': x['motivo']} for x in h['ultimos'][:8]]}
        mats.append(fila)
    lineas = {}
    for pv in provs:
        por = {a.linea.i: a for a in pv['asign']}
        manual = {int(k): v for k, v in e['manuales'].get(pv['nombre'], {}).items()}
        out = []
        for l in pv['lineas']:
            a = por.get(l.i)
            cands = [{'id': mid, 'p': _n(sc)} for sc, mid in (pv['puntos'].get(l.i) or [])[:5]]
            out.append({'i': l.i, 'seccion': l.seccion, 'codigo': l.referencia, 'desc': l.partida.descripcion[:200],
                        'cant': l.partida.cantidad, 'precio': _n(l.partida.precio, 4), 'dto': l.partida.dto_pct,
                        'importe': _n(l.partida.importe_exacto), 'mat': a.material_id if a else None,
                        'tipo': a.tipo if a else None, 'punt': _n(a.puntuacion) if a else None,
                        'manual': l.i in manual, 'cands': cands, 'notas': l.partida.notas})
        d = pv['doc']
        suma = round(sum(p.importe_exacto for p in d.partidas() if p.precio is not None), 2)
        lineas[pv['nombre']] = {'lineas': out, 'fecha': d.fecha, 'validez': d.validez, 'total_doc': d.total_declarado,
                                'suma': suma, 'avisos': [a.texto for a in d.avisos if a.nivel != 'info'][:12]}
    total_cli = round(sum(m.partida.importe for m in r.materiales if m.primero), 2)
    totales = {pv['nombre']: {'importe': round(sum(o.importe or 0 for o in pv['ofertas'].values()), 2),
                              'cubiertos': len(pv['ofertas']), 'sin': len(pv['sin'])} for pv in provs}
    base.update(materiales=mats, lineas=lineas, total_cliente=total_cli, totales=totales,
                cliente_nombre=r.cliente.nombre, avisos_cliente=[a.texto for a in r.cliente.avisos if a.nivel != 'info'])
    return base


def servir(puerto=8765, abrir=True):
    class Manejador(BaseHTTPRequestHandler):
        server_version = 'Automatizador'

        def log_message(self, fmt, *args):
            pass

        def _enviar(self, codigo, cuerpo, tipo, extra=None):
            if isinstance(cuerpo, str):
                cuerpo = cuerpo.encode('utf-8')
            self.send_response(codigo)
            self.send_header('Content-Type', tipo)
            self.send_header('Content-Length', str(len(cuerpo)))
            self.send_header('Cache-Control', 'no-store')
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(cuerpo)

        def _json(self, obj, codigo=200):
            self._enviar(codigo, json.dumps(obj, ensure_ascii=False, default=str), 'application/json; charset=utf-8')

        def _error(self, codigo, texto):
            self._json({'error': texto}, codigo)

        def _proteger(self, fn):
            try:
                fn()
            except (ValueError, OSError) as e:
                self._error(400, str(e))
            except Exception as e:                         # fallo inesperado: se cuenta y queda rastro en la consola
                traceback.print_exc()
                self._error(500, 'Fallo inesperado (%s: %s). Mira la ventana del programa.' % (type(e).__name__, e))

        # ------------------------------------------------------------------------------ GET
        def do_GET(self):
            u = urlparse(self.path)
            ruta = unquote(u.path)
            q = parse_qs(u.query)
            if ruta == '/':
                return self._enviar(200, PAGINA, 'text/html; charset=utf-8')
            if ruta == '/favicon.ico':
                return self._enviar(204, b'', 'image/x-icon')
            if ruta == '/api/obras':
                return self._proteger(lambda: self._json([{'id': o.ident, 'nombre': o.nombre,
                                                           'cliente': bool(o.estado.get('cliente')),
                                                           'proveedores': [p['nombre'] for p in o.estado['proveedores']]}
                                                          for o in Obra.listar()]))
            m = re.fullmatch(r'/api/obra/([^/]+)', ruta)
            if m:
                return self._proteger(lambda: self._json(datos_obra(Obra.abrir(m.group(1)))))
            m = re.fullmatch(r'/api/obra/([^/]+)/excel', ruta)
            if m:
                return self._proteger(lambda: self._excel(Obra.abrir(m.group(1))))
            if ruta == '/api/casos':
                return self._proteger(lambda: self._json(db().casos()))
            if ruta == '/api/bbdd':
                texto = (q.get('q') or [''])[0]
                return self._proteger(lambda: self._json({'resumen': db().resumen(), 'filas': db().buscar(texto)}))
            self._error(404, 'No encontrado.')

        def _excel(self, o):
            with BLOQUEO:
                r = analisis(o)
                fd, tmp = tempfile.mkstemp(suffix='.xlsx')
                os.close(fd)
                try:
                    excel_comparativa.escribir(r, tmp)
                    with open(tmp, 'rb') as f:
                        datos = f.read()
                    shutil.copy2(tmp, os.path.join(o.carpeta, 'comparativa_%s.xlsx' % o.ident))
                finally:
                    os.remove(tmp)
            nombre = 'comparativa_%s.xlsx' % re.sub(r'[^\w.-]+', '_', o.ident)
            self._enviar(200, datos, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         {'Content-Disposition': 'attachment; filename="%s"' % nombre})

        # ------------------------------------------------------------------------------ POST
        def _cuerpo(self):
            n = int(self.headers.get('Content-Length') or 0)
            if n > MAX_SUBIDA:
                raise ValueError('Subida demasiado grande (máximo %d MB).' % (MAX_SUBIDA // 1048576))
            return self.rfile.read(n)

        def _json_cuerpo(self):
            return json.loads(self._cuerpo() or b'{}')

        def do_POST(self):
            ruta = unquote(urlparse(self.path).path)
            if ruta == '/api/casos/borrar':
                def borrar():
                    db().borrar_caso(int(self._json_cuerpo()['id']))
                    _CACHE.clear()
                    self._json({'ok': True})
                return self._proteger(borrar)
            if ruta == '/api/obras':
                def crear():
                    o = Obra.crear(self._json_cuerpo().get('nombre', ''))
                    self._json({'id': o.ident})
                return self._proteger(crear)
            m = re.fullmatch(r'/api/obra/([^/]+)/(cliente|proveedor|quitar|fijar|deshacer|reanalizar|caso)', ruta)
            if not m:
                return self._error(404, 'No encontrado.')
            accion = m.group(2)

            def hacer():
                o = Obra.abrir(m.group(1))
                if accion in ('cliente', 'proveedor'):
                    partes = parsear_multipart(self.headers.get('Content-Type', ''), self._cuerpo())
                    campos = {k: v.decode('utf-8', 'replace') for k, f, v in partes if not f}
                    ficheros = [(f, v) for k, f, v in partes if f and v]
                    if not ficheros:
                        raise ValueError('No se ha recibido ningún fichero.')
                    hechos = []
                    with BLOQUEO, tempfile.TemporaryDirectory() as tmp:
                        for nombre_f, datos in ficheros:
                            nombre_f = os.path.basename(nombre_f.replace('\\', '/'))
                            ruta_tmp = os.path.join(tmp, nombre_f)
                            with open(ruta_tmp, 'wb') as fh:
                                fh.write(datos)
                            if accion == 'cliente':
                                d = o.poner_cliente(ruta_tmp, nombre_f)
                                hechos.append('Presupuesto del cliente: %d partidas, %.2f €' % (
                                    sum(1 for _ in d.partidas()), d.importe))
                            else:
                                nombre_prov = (campos.get('proveedor') or '').strip() if len(ficheros) == 1 else ''
                                prov, d = o.anadir_proveedor(ruta_tmp, nombre_prov or None, nombre_f)
                                hechos.append('%s: %d líneas leídas' % (prov, sum(1 for _ in d.partidas())))
                    return self._json({'ok': True, 'mensaje': ' · '.join(hechos)})
                datos = self._json_cuerpo()
                with BLOQUEO:
                    if accion == 'quitar':
                        o.quitar_proveedor(datos['proveedor'], db())
                    elif accion == 'fijar':
                        o.fijar(datos['proveedor'], int(datos['linea']), datos.get('material') or None)
                        if datos.get('material'):
                            r = analisis(o, forzar=True)
                            pv = next(p for p in r.proveedores if p['nombre'] == datos['proveedor'])
                            l = next(x for x in pv['lineas'] if x.i == int(datos['linea']))
                            mat = next(x for x in r.materiales if x.id == datos['material'])
                            db().aprender(datos['proveedor'], l, mat)
                    elif accion == 'deshacer':
                        o.deshacer(datos['proveedor'], int(datos['linea']))
                    elif accion == 'caso':
                        r = analisis(o)
                        mat = next(x for x in r.materiales if x.id == datos['material'])
                        prov = datos.get('proveedor') or None
                        oferta = None
                        if prov:
                            pv = next((p for p in r.proveedores if p['nombre'] == prov), None)
                            of = pv and pv['ofertas'].get(mat.id)
                            oferta = of and ('%s x %s' % (of.cant_prov, of.principal.partida.descripcion))
                        cant = datos.get('cantidad')
                        db().anotar_caso(o.nombre, mat, datos['observacion'], prov, oferta,
                                         float(str(cant).replace(',', '.')) if cant not in (None, '') else None)
                        _CACHE.clear()
                    elif accion == 'reanalizar':
                        analisis(o, forzar=True)
                self._json({'ok': True})
            self._proteger(hacer)

    srv = ThreadingHTTPServer(('127.0.0.1', puerto), Manejador)
    url = 'http://127.0.0.1:%d/' % puerto
    print('App abierta en %s  (Ctrl+C para cerrar)' % url)
    print('Datos y base de datos de precios en:', os.path.dirname(ruta_bbdd()))
    if abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('Cerrado.')
    finally:
        srv.server_close()
