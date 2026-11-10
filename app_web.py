"""App web LOCAL:  python -m automatizador app

Se abre en tu navegador (http://127.0.0.1:8765). Subes la licitación y los presupuestos de los proveedores, revisas en
pantalla lo dudoso y descargas un .zip con los mismos ficheros de siempre (BC3 por proveedor, emparejamiento.xlsx,
diferencias.xlsx, comparativa.xlsx, LEEME y originales).

Solo usa la librería estándar de Python. Escucha ÚNICAMENTE en 127.0.0.1: nadie de tu red puede entrar y los ficheros
no salen de tu ordenador.
"""
import email
import email.policy
import io
import json
import mimetypes
import os
import re
import shutil
import threading
import time
import traceback
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from . import flujo_comparar as flujo
from .procesar import _nombre_seguro, nombre_corto
from .app_html import PAGINA_INICIO, PAGINA_TRABAJO

MAX_SUBIDA = 300 * 1024 * 1024
ID_TRABAJO = re.compile(r'^\d{8}-\d{6}_comparativa$')
EXTENSIONES = ('.bc3', '.pdf', '.xlsx', '.xlsm')

BLOQUEO = threading.Lock()          # una tarea pesada cada vez (leer PDFs, emparejar, escribir ficheros)
TRABAJOS = {}                        # token -> {'estado': 'trabajando'|'listo'|'error', 'msg': str, 'id': str}


def parsear_multipart(content_type, cuerpo):
    """Separa un formulario multipart/form-data. Devuelve [(campo, nombre_fichero|None, bytes)].

    Usa el módulo 'email' porque 'cgi' ya no existe en las versiones nuevas de Python."""
    msg = email.message_from_bytes(b'Content-Type: ' + content_type.encode('latin-1') + b'\r\n\r\n' + cuerpo,
                                   policy=email.policy.HTTP)
    if not msg.is_multipart():
        raise ValueError('El formulario no es multipart.')
    out = []
    for parte in msg.iter_parts():
        out.append((parte.get_param('name', header='content-disposition'), parte.get_filename(),
                    parte.get_payload(decode=True) or b''))
    return out


def _tarea(token, tmp, trabajo):
    """Ejecuta en segundo plano un trabajo pesado. `trabajo(progreso)` devuelve la carpeta de la comparativa."""
    estado = TRABAJOS[token]
    try:
        with BLOQUEO:
            carpeta = trabajo(lambda t: estado.update(msg=t))
        estado.update(estado='listo', id=os.path.basename(carpeta), msg='Listo')
    except (ValueError, OSError) as e:
        pista = ''
        if isinstance(e, OSError) and getattr(e, 'winerror', None) in (3, 206):
            pista = ('\n\nLa ruta de la carpeta es demasiado larga para Windows. Copia la carpeta del programa a algo corto, '
                     'por ejemplo C:\\automatizador, y ábrelo desde ahí.')
        estado.update(estado='error', msg=str(e) + pista)
    except Exception as e:                                           # fallo inesperado: se cuenta y se deja rastro en consola
        traceback.print_exc()
        estado.update(estado='error', msg='Fallo inesperado (%s: %s). Mira la ventana negra del programa para el detalle.' % (
            type(e).__name__, e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def hacer_manejador(cfg):
    base_salida = os.path.realpath(cfg['carpetas']['salida'])

    def carpeta_trabajo(idt):
        if not ID_TRABAJO.match(idt or ''):
            return None
        c = os.path.join(base_salida, idt)
        return c if os.path.isdir(c) and os.path.exists(os.path.join(c, 'comparativa.xlsx')) else None

    def ficheros(carpeta):
        out = []
        for raiz, _, nombres in os.walk(carpeta):
            for n in sorted(nombres):
                rel = os.path.relpath(os.path.join(raiz, n), carpeta).replace(os.sep, '/')
                out.append({'ruta': rel, 'tam': os.path.getsize(os.path.join(raiz, n))})
        out.sort(key=lambda f: (f['ruta'].count('/'), f['ruta']))
        return out

    class Manejador(BaseHTTPRequestHandler):
        server_version = 'Automatizador'

        def log_message(self, fmt, *args):                          # sin ruido en la consola
            pass

        # ------------------------------------------------------------------ utilidades de respuesta
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
            self._enviar(codigo, json.dumps(obj, ensure_ascii=False), 'application/json; charset=utf-8')

        def _error(self, codigo, texto):
            self._json({'error': texto}, codigo)

        # ------------------------------------------------------------------ GET
        def do_GET(self):
            ruta = unquote(urlparse(self.path).path)
            if ruta == '/':
                return self._enviar(200, PAGINA_INICIO, 'text/html; charset=utf-8')
            if ruta == '/trabajos.json':
                return self._json(self._lista_trabajos())
            m = re.fullmatch(r'/estado/([0-9a-f]{32})', ruta)
            if m:
                e = TRABAJOS.get(m.group(1))
                return self._json(e) if e else self._error(404, 'Trabajo desconocido.')
            m = re.fullmatch(r'/trabajo/([^/]+)', ruta)
            if m:
                return (self._enviar(200, PAGINA_TRABAJO, 'text/html; charset=utf-8')
                        if carpeta_trabajo(m.group(1)) else self._error(404, 'No existe ese trabajo.'))
            m = re.fullmatch(r'/trabajo/([^/]+)/datos\.json', ruta)
            if m:
                return self._datos(m.group(1))
            m = re.fullmatch(r'/trabajo/([^/]+)/descargar\.zip', ruta)
            if m:
                return self._zip(m.group(1))
            m = re.fullmatch(r'/trabajo/([^/]+)/f/(.+)', ruta)
            if m:
                return self._fichero(m.group(1), m.group(2))
            if ruta == '/favicon.ico':
                return self._enviar(204, b'', 'image/x-icon')
            self._error(404, 'No encontrado.')

        def _lista_trabajos(self):
            out = []
            for d in sorted(os.listdir(base_salida), reverse=True):
                if carpeta_trabajo(d):
                    sello = d[:15]
                    out.append({'id': d, 'fecha': '%s/%s/%s %s:%s' % (sello[6:8], sello[4:6], sello[0:4], sello[9:11], sello[11:13]),
                                'proveedores': sorted(x for x in os.listdir(os.path.join(base_salida, d))
                                                      if os.path.exists(os.path.join(base_salida, d, x, 'emparejamiento.json')))})
            return out[:15]

        def _datos(self, idt):
            c = carpeta_trabajo(idt)
            if not c:
                return self._error(404, 'No existe ese trabajo.')
            try:
                with BLOQUEO:
                    d = flujo.datos_revision(c)
            except (ValueError, OSError) as e:
                return self._error(400, str(e))
            d.update(id=idt, carpeta=c, ficheros=ficheros(c))
            self._json(d)

        def _zip(self, idt):
            c = carpeta_trabajo(idt)
            if not c:
                return self._error(404, 'No existe ese trabajo.')
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                for f in ficheros(c):
                    z.write(os.path.join(c, f['ruta']), '%s/%s' % (idt, f['ruta']))
            self._enviar(200, buf.getvalue(), 'application/zip',
                         {'Content-Disposition': 'attachment; filename="%s.zip"' % idt})

        def _fichero(self, idt, rel):
            c = carpeta_trabajo(idt)
            if not c:
                return self._error(404, 'No existe ese trabajo.')
            real = os.path.realpath(os.path.join(c, rel))
            if not real.startswith(os.path.realpath(c) + os.sep) or not os.path.isfile(real):     # impide salir de la carpeta (../)
                return self._error(404, 'No existe ese fichero.')
            with open(real, 'rb') as f:
                datos = f.read()
            tipo = mimetypes.guess_type(real)[0] or 'application/octet-stream'
            self._enviar(200, datos, tipo, {'Content-Disposition': 'attachment; filename="%s"' % os.path.basename(real).replace('"', '_')})

        # ------------------------------------------------------------------ POST
        def _cuerpo(self):
            n = int(self.headers.get('Content-Length') or 0)
            if n > MAX_SUBIDA:
                raise ValueError('Subida demasiado grande (máximo %d MB).' % (MAX_SUBIDA // 1048576))
            return self.rfile.read(n)

        def do_POST(self):
            ruta = unquote(urlparse(self.path).path)
            try:
                if ruta == '/crear':
                    return self._crear()
                m = re.fullmatch(r'/trabajo/([^/]+)/aplicar', ruta)
                if m:
                    return self._aplicar(m.group(1))
                m = re.fullmatch(r'/trabajo/([^/]+)/anadir', ruta)
                if m:
                    return self._anadir(m.group(1))
                m = re.fullmatch(r'/trabajo/([^/]+)/quitar', ruta)
                if m:
                    return self._quitar(m.group(1))
            except ValueError as e:
                return self._error(400, str(e))
            except Exception as e:
                traceback.print_exc()
                return self._error(500, 'Fallo inesperado: %s: %s' % (type(e).__name__, e))
            self._error(404, 'No encontrado.')

        def _guardar_subidas(self, tmp, grupos):
            """Guarda en `tmp` los ficheros subidos [(carpeta, nombre, bytes)] con nombres cortos y seguros. Devuelve rutas."""
            usados, rutas = set(), []
            for prefijo, nombre, datos in grupos:
                limpio = nombre_corto(_nombre_seguro(os.path.basename(nombre.replace('\\', '/'))) or 'fichero', 40)
                if not limpio.lower().endswith(EXTENSIONES):
                    raise ValueError('"%s": formato no admitido (usa %s).' % (nombre, ', '.join(EXTENSIONES)))
                base, ext = os.path.splitext(limpio)
                k, cand = 1, limpio
                while cand.lower() in usados:
                    k += 1
                    cand = '%s_%d%s' % (base, k, ext)
                usados.add(cand.lower())
                dest = os.path.join(tmp, prefijo, cand)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, 'wb') as f:
                    f.write(datos)
                rutas.append(dest)
            return rutas

        def _lanzar(self, tmp, trabajo, msg):
            token = uuid.uuid4().hex
            TRABAJOS[token] = {'estado': 'trabajando', 'msg': msg, 'id': ''}
            threading.Thread(target=_tarea, args=(token, tmp, trabajo), daemon=True).start()
            self._json({'token': token})

        def _crear(self):
            partes = parsear_multipart(self.headers.get('Content-Type', ''), self._cuerpo())
            lic = [(n, d) for campo, n, d in partes if campo == 'licitacion' and n and d]
            ofs = [(n, d) for campo, n, d in partes if campo == 'ofertas' and n and d]
            if len(lic) != 1:
                raise ValueError('Falta la licitación (un único fichero).')
            if not ofs:
                raise ValueError('Añade al menos un presupuesto de proveedor.')
            tmp = os.path.join(base_salida, '_subidas', uuid.uuid4().hex[:8])
            os.makedirs(tmp)
            try:
                rutas = self._guardar_subidas(tmp, [('licitacion', lic[0][0], lic[0][1])] + [('ofertas', n, d) for n, d in ofs])
            except ValueError:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            self._lanzar(tmp, lambda prog: flujo.comparativa(rutas[0], rutas[1:], cfg, progreso=prog, app=True)['carpeta'],
                         'Leyendo la licitación…')

        def _anadir(self, idt):
            c = carpeta_trabajo(idt)
            if not c:
                return self._error(404, 'No existe ese trabajo.')
            partes = parsear_multipart(self.headers.get('Content-Type', ''), self._cuerpo())
            ofs = [(n, d) for campo, n, d in partes if campo == 'ofertas' and n and d]
            if not ofs:
                raise ValueError('Elige al menos un presupuesto.')
            tmp = os.path.join(base_salida, '_subidas', uuid.uuid4().hex[:8])
            os.makedirs(tmp)
            try:
                rutas = self._guardar_subidas(tmp, [('ofertas', n, d) for n, d in ofs])
            except ValueError:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            self._lanzar(tmp, lambda prog: flujo.anadir_ofertas(c, rutas, cfg, progreso=prog)['carpeta'], 'Preparando…')

        def _quitar(self, idt):
            c = carpeta_trabajo(idt)
            if not c:
                return self._error(404, 'No existe ese trabajo.')
            try:
                sub = json.loads(self._cuerpo().decode('utf-8'))['proveedor']
                if not re.fullmatch(r'[\w.\-]+', sub):
                    raise ValueError('Proveedor no válido.')
            except (KeyError, TypeError, json.JSONDecodeError):
                raise ValueError('Petición mal formada.')
            with BLOQUEO:
                flujo.quitar_oferta(c, sub, cfg)
            self._json({'ok': True})

        def _aplicar(self, idt):
            c = carpeta_trabajo(idt)
            if not c:
                return self._error(404, 'No existe ese trabajo.')
            try:
                cuerpo = json.loads(self._cuerpo().decode('utf-8'))
                elecciones = {}
                for prov, el in cuerpo['elecciones'].items():
                    if not re.fullmatch(r'[\w.\-]+', prov):
                        raise ValueError('Proveedor no válido.')
                    elecciones[prov] = {int(o): int(l) for o, l in el.items() if l not in (None, '')}
            except (KeyError, TypeError, json.JSONDecodeError):
                raise ValueError('Petición mal formada.')
            with BLOQUEO:
                flujo.regenerar(c, elecciones, cfg)
            self._json({'ok': True})

    return Manejador


def servir(cfg, puerto=8765, abrir=True):
    srv = None
    for p in range(puerto, puerto + 20):                # si el puerto está ocupado, prueba el siguiente
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', p), hacer_manejador(cfg))
            puerto = p
            break
        except OSError:
            continue
    if srv is None:
        raise OSError('No hay ningún puerto libre entre %d y %d.' % (puerto, puerto + 19))
    url = 'http://127.0.0.1:%d/' % puerto
    print('App en marcha:', url)
    print('Cierra esta ventana (o pulsa Ctrl+C) para parar el programa.')
    if abrir:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('Parado.')
    finally:
        srv.server_close()
