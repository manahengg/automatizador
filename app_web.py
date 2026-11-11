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
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import compartido as C
from . import emparejar as M
from .app_html import PAGINA
from .bbdd import BBDD
from .obra import Obra, clave_mat, leer_cliente, ruta_bbdd
from .exportadores import excel_comparativa, excel_peticion, excel_pedido
from . import decisiones as D

MAX_SUBIDA = 300 * 1024 * 1024
BLOQUEO = threading.RLock()        # una operación pesada cada vez (OCR, análisis, escritura)
_CACHE = {}                         # id obra -> (marca, Resultado)
_DB = None


_LOGO = None


def _logo_datos():
    """Logo de la empresa incrustado en la página (data URI): funciona igual en el .exe y sin internet."""
    global _LOGO
    if _LOGO is None:
        import base64
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recursos', 'logo_64.png')
        try:
            with open(ruta, 'rb') as f:
                _LOGO = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()
        except OSError:
            _LOGO = ''
    return _LOGO


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


VERSION = {'n': 0, 'cambios': [], 'conocimiento': 0}   # contador de cambios que ven los navegadores


def _avisar_cambio(obra, texto, usuario=None):
    VERSION['n'] += 1
    VERSION['cambios'].append({'v': VERSION['n'], 'obra': obra, 'texto': texto, 'usuario': usuario})
    del VERSION['cambios'][:-200]


def _marca(o):
    return (o.marca(), VERSION['conocimiento'], _marca_bases())


def _marca_bases():
    """Cambia cuando alguien añade o quita una base de precios global (en cualquier PC)."""
    from . import bases
    d = bases.dir_compartida()
    try:
        return tuple(sorted(os.listdir(d))) if os.path.isdir(d) else ()
    except OSError:
        return ()


def analisis(o, forzar=False, progreso=None):
    with BLOQUEO:
        o.recargar()
        m = _marca(o)
        c = _CACHE.get(o.ident)
        if c and c[0] == m and not forzar:
            return c[1]
        r = o.analizar(db(), progreso=progreso)
        _CACHE[o.ident] = (m, r)
        return r


def _n(x, d=2):
    return None if x is None else round(x, d)


def llevar_obras_locales():
    """Copia a la carpeta compartida las obras creadas antes en este PC (sin borrar las locales)."""
    base_local = os.path.join(C.carpeta_local(), 'obras')
    if not C.compartida_activa() or not os.path.isdir(base_local):
        return 0
    n = 0
    for d in os.listdir(base_local):
        origen = os.path.join(base_local, d)
        destino = os.path.join(Obra.base(), d)
        if not os.path.isdir(origen) or os.path.exists(destino):
            continue
        shutil.copytree(origen, destino, ignore=shutil.ignore_patterns('cache', '*.xlsx', '~$*'))
        Obra(destino)                                  # migra estado.json a eventos si hace falta
        n += 1
    return n


def datos_obra(o):
    e = o.estado
    base = {'id': o.ident, 'nombre': o.nombre, 'cliente': e.get('cliente'), 'version': VERSION['n'],
            'proveedores': [{'nombre': p['nombre'], 'archivo': os.path.basename(p['archivo']), 'anadida': p.get('anadida'),
                             'usuario': p.get('usuario'), 'n_ofertas': len(p['ofertas'])} for p in e['proveedores']],
            'cliente_archivos': [{'archivo': os.path.basename(a['archivo']), 'huella': a['huella']}
                                 for a in (e.get('cliente') or {}).get('archivos', [])],
            'historial': e['historial'][-40:][::-1], 'capitulos': e.get('capitulos'), 'datos': e.get('datos') or {}}
    if o.pendiente_capitulos:
        base['pendiente_capitulos'] = True          # primero hay que elegir qué capítulos hacemos
        return base
    if not e.get('cliente'):
        return base
    r = analisis(o)
    provs = r.proveedores
    for pv in provs:
        if pv.get('global'):              # bases de precios presentes en todas las obras
            base['proveedores'].append({'nombre': pv['nombre'], 'archivo': os.path.basename(pv['archivo']),
                                        'anadida': None, 'usuario': 'todas las obras', 'n_ofertas': 1, 'global': True})
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
                    'confianza': _n(of.confianza, 3), 'aprendido': of.aprendido, 'origen': of.origen,
                    'dcant': M.comparacion_cantidad(of.cant_prov, m.cantidad)}
        fila['aprendido'] = r.avisos_aprendidos(m)
        fila['riesgo'] = (r.fichas.get(m.id) or {}).get('riesgo')
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
        manual = {k for k in e['manuales'].get(pv['nombre'], {})}
        out = []
        for l in pv['lineas']:
            a = por.get(l.i)
            if pv.get('catalogo') and not a:
                continue                   # base de precios: solo los artículos usados (son miles)
            cands = [{'id': mid, 'p': _n(sc)} for sc, mid in (pv['puntos'].get(l.i) or [])[:5]]
            out.append({'i': l.i, 'uid': l.uid, 'seccion': l.seccion, 'codigo': l.referencia, 'desc': l.partida.descripcion[:200],
                        'cant': l.partida.cantidad, 'precio': _n(l.partida.precio, 4), 'dto': l.partida.dto_pct,
                        'importe': _n(l.partida.importe_exacto), 'mat': a.material_id if a else None,
                        'tipo': a.tipo if a else None, 'punt': _n(a.puntuacion) if a else None,
                        'manual': l.uid in manual or str(l.i) in manual, 'cands': cands, 'notas': l.partida.notas})
        docs = []
        for x in pv['docs']:
            d = x['doc']
            docs.append({'archivo': os.path.basename(x['archivo']), 'huella': x['huella'], 'fecha': d.fecha,
                         'validez': d.validez, 'total_doc': d.total_declarado, 'usuario': x.get('usuario'),
                         'anadida': x.get('anadida'), 'lineas': sum(1 for _ in d.partidas()),
                         'suma': round(sum(p.importe_exacto for p in d.partidas() if p.precio is not None), 2),
                         'avisos': [a.texto for a in d.avisos if a.nivel != 'info'][:12]})
        lineas[pv['nombre']] = {'lineas': out, 'docs': docs, 'referencia': bool(pv.get('referencia')),
                                'global': bool(pv.get('global')),
                                'catalogo': bool(pv.get('catalogo'))}
    total_cli = round(sum(m.partida.importe for m in r.materiales if m.primero), 2)
    totales = {pv['nombre']: {'importe': round(sum(o.importe or 0 for o in pv['ofertas'].values()), 2),
                              'cubiertos': len(pv['ofertas']), 'sin': len(pv['sin'])} for pv in provs}
    filas_rep, total_rep, sin_rep = r.reparto()
    for pv in provs:
        totales[pv['nombre']]['referencia'] = bool(pv.get('referencia'))
    from . import analisis_partida as AP
    base.update(reparto={'filas': filas_rep, 'total': total_rep, 'sin': sin_rep}, totales_prov=r.totales_proveedores(),
                revisar=[{k: f[k] for k in ('id', 'n', 'codigo', 'resumen', 'riesgo', 'motivos')}
                         for f in AP.a_revisar(r.fichas)])
    base.update(materiales=mats, lineas=lineas, total_cliente=total_cli, totales=totales,
                cliente_nombre=r.cliente.nombre, avisos_cliente=[a.texto for a in r.cliente.avisos if a.nivel != 'info'])
    return base


def _aprendido():
    """Una decisión nueva cambia lo aprendido: hay que rehacer el análisis de TODAS las obras."""
    VERSION['conocimiento'] += 1


def _decision_fijar(o, r, pv, l, mat):
    """Casar (mat) o descasar (mat None) a mano la línea l: se registra con lo que la app había propuesto."""
    mats = {m.id: m for m in r.materiales}
    a_antes = next((a for a in pv['asign'] if a.linea.uid == l.uid), None)
    antes = mats.get(a_antes.material_id) if a_antes else None
    if mat is not None:
        cands = sorted(((x, sc) for x in pv['lineas'] for sc, mid in (pv['puntos'].get(x.i) or []) if mid == mat.id),
                       key=lambda t: -t[1])
        sc = next((s for x, s in cands if x.uid == l.uid), None)
        D.registrar(db(), 'casar', o.nombre, pv['nombre'],
                    [D.item(mat, l, cands, antes, sc, muestras=D.muestras(r, pv, l, mat))])
    elif antes is not None:
        D.registrar(db(), 'descasar', o.nombre, pv['nombre'],
                    [D.item(antes, l, puntuacion=a_antes.puntuacion, muestras=D.muestras(r, pv, l, antes, False))])
    _aprendido()


def _decision_pedido(o, r, prov, ids):
    """Lo que se pide a un proveedor cuenta como emparejamiento aceptado."""
    pv = next(p for p in r.proveedores if p['nombre'] == prov)
    items = [D.item(m, pv['ofertas'][m.id].principal, puntuacion=pv['ofertas'][m.id].puntuacion,
                    muestras=D.muestras(r, pv, pv['ofertas'][m.id].principal, m))
             for m in r.materiales if m.id in pv['ofertas'] and (ids is None or m.id in ids)
             and pv['ofertas'][m.id].precio is not None]
    if items:
        D.registrar(db(), 'pedido', o.nombre, prov, items)
        _aprendido()


TRABAJOS = {}          # id -> Trabajo (subidas en curso, para la barra de progreso)


class Trabajo:
    """Una subida que se procesa en segundo plano y va contando por dónde va."""

    def __init__(self, titulo):
        self.id = uuid.uuid4().hex
        self.titulo = titulo
        self.inicio = time.time()
        self.estado = 'trabajando'           # trabajando | listo | error
        self.texto = 'Preparando…'
        self.fraccion = 0.0
        self.pasos = []                       # [{'texto', 'seg'}] pasos terminados
        self._t_paso = time.time()
        self.mensaje = ''
        TRABAJOS[self.id] = self
        for k in [k for k, t in TRABAJOS.items() if time.time() - t.inicio > 3600]:
            TRABAJOS.pop(k, None)

    def paso(self, texto, fraccion=None):
        if texto != self.texto:
            if self.texto and not self.texto.startswith('Preparando'):
                self.pasos.append({'texto': self.texto, 'seg': round(time.time() - self._t_paso, 1)})
                del self.pasos[:-40]
            self.texto, self._t_paso = texto, time.time()
        if fraccion is not None:
            self.fraccion = max(self.fraccion, min(1.0, fraccion))

    def tramo(self, desde, hasta, prefijo=''):
        """Callback de progreso de un documento que ocupa [desde, hasta] de la barra total."""
        def cb(texto, frac=None):
            self.paso(prefijo + texto, None if frac is None else desde + (hasta - desde) * frac)
        return cb

    def json(self):
        return {'id': self.id, 'titulo': self.titulo, 'estado': self.estado, 'texto': self.texto,
                'fraccion': round(self.fraccion, 3), 'pasos': self.pasos, 'mensaje': self.mensaje,
                'segundos': round(time.time() - self.inicio), 'seg_paso': round(time.time() - self._t_paso)}


def procesar_subida(trabajo, o, accion, ficheros, campos, carpeta_tmp):
    """Lee los documentos subidos, analiza la obra y deja el resultado en el trabajo (hilo aparte)."""
    hechos = []
    n = len(ficheros)
    try:
        with BLOQUEO:
            if accion == 'cliente':
                # el proyecto del cliente puede venir en varios ficheros: se leen todos y se unen
                cb = trabajo.tramo(0, 0.85)
                for k, (nombre_f, ruta_tmp) in enumerate(ficheros):
                    cbk = trabajo.tramo(0.85 * k / n, 0.85 * (k + 1) / n, '%s · ' % nombre_f if n > 1 else '')
                    cbk('Abriendo el documento…', 0)
                    o._leer(ruta_tmp, leer_cliente, cbk)                         # lee (y deja en caché) cada fichero
                d = o.poner_cliente(ficheros[0][1], ficheros[0][0], progreso=None, anadir=campos.get('modo') == 'anadir',
                                    mas=[(r, nf) for nf, r in ficheros[1:]])
                hechos.append('Presupuesto del cliente%s: %d partidas, %s €. Elige ahora los capítulos que hacemos' % (
                    ' (%d ficheros)' % len(o.estado['cliente']['archivos']) if len(o.estado['cliente']['archivos']) > 1 else '',
                    sum(1 for _ in d.partidas()), ('%.2f' % d.importe).replace('.', ',')))
                cb('Leído: ' + hechos[-1], 1.0)
            else:
                nombre_prov = (campos.get('proveedor') or '').strip()
                sustituir = campos.get('sustituir') == '1'
                for k, (nombre_f, ruta_tmp) in enumerate(ficheros):
                    cb = trabajo.tramo(0.85 * k / n, 0.85 * (k + 1) / n, '%s · ' % nombre_f if n > 1 else '')
                    cb('Abriendo el documento…', 0)
                    prov, d = o.anadir_proveedor(ruta_tmp, nombre_prov or None, nombre_f, progreso=cb,
                                                 sustituir=sustituir and k == 0)
                    hechos.append('%s: %d líneas leídas (%s)' % (prov, sum(1 for _ in d.partidas()), nombre_f))
                    cb('Leído: ' + hechos[-1], 1.0)
            if o.estado.get('cliente') and not o.pendiente_capitulos:
                cb = trabajo.tramo(0.85, 1.0)
                cb('Casando ofertas con el presupuesto y consultando la base de datos de precios…', 0.1)
                analisis(o, progreso=lambda t, f=None: cb(t, 0.5))
        trabajo.paso('Terminado', 1.0)
        trabajo.mensaje = ' · '.join(hechos)
        trabajo.estado = 'listo'
    except (ValueError, OSError) as e:
        trabajo.estado, trabajo.mensaje = 'error', str(e)
    except Exception as e:
        traceback.print_exc()
        trabajo.estado, trabajo.mensaje = 'error', 'Fallo inesperado (%s: %s).' % (type(e).__name__, e)
    finally:
        shutil.rmtree(carpeta_tmp, ignore_errors=True)


class Sincronizador(threading.Thread):
    """Vigila la carpeta compartida: conocimiento nuevo de los compañeros y obras que han cambiado.
    Lo que cambia se vuelve a analizar (y sus precios entran en la BBDD local) y se avisa a los navegadores."""
    INTERVALO = 3.0

    def __init__(self):
        super().__init__(daemon=True)
        self.marcas = {}
        self.parar = threading.Event()

    def run(self):
        while not self.parar.is_set():
            try:
                self.vuelta()
            except Exception:
                traceback.print_exc()
            self.parar.wait(self.INTERVALO)

    def vuelta(self):
        yo = C.usuario()
        with BLOQUEO:
            nuevos = db().importar_conocimiento()
        if nuevos:
            VERSION['conocimiento'] += 1
            for ev in nuevos:
                if ev.get('usuario') != yo:
                    _avisar_cambio(None, '%s %s' % (ev.get('usuario'), 'anotó un caso' if ev['tipo'] == 'caso' else
                                                     'enseñó una equivalencia' if ev['tipo'] == 'equivalencia' else
                                                     'olvidó un caso'), ev.get('usuario'))
        mb = _marca_bases()
        if self.marcas.get('__bases__', mb) != mb:
            _avisar_cambio(None, 'Bases de precios actualizadas')
        self.marcas['__bases__'] = mb
        for o in Obra.listar():
            m = o.marca()
            anterior = self.marcas.get(o.ident)
            if anterior == m:
                continue
            self.marcas[o.ident] = m
            if not o.estado.get('cliente') or o.pendiente_capitulos:
                if anterior is not None:
                    _avisar_cambio(o.ident, 'Cambios en %s' % o.nombre)
                continue
            try:
                analisis(o)                               # lee (caché compartida), empareja y alimenta la BBDD local
            except Exception as e:
                print('No se pudo analizar la obra %s: %s' % (o.nombre, e))
                continue
            if anterior is not None:
                ult = o.estado['historial'][-1] if o.estado['historial'] else {}
                quien = ult.get('usuario')
                _avisar_cambio(o.ident, '%s: %s %s' % (o.nombre, quien or '', ult.get('detalle') or 'cambios'),
                               quien if quien != yo else None)


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
                return self._enviar(200, PAGINA.replace('__LOGO__', _logo_datos()), 'text/html; charset=utf-8')
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
            m = re.fullmatch(r'/api/obra/([^/]+)/capitulos', ruta)
            if m:
                def caps():
                    o = Obra.abrir(m.group(1))
                    if not o.estado.get('cliente'):
                        raise ValueError('Primero sube el presupuesto del cliente.')
                    with BLOQUEO:
                        doc = o.documento_cliente()
                    arbol = M.arbol_capitulos(doc)
                    incl = o.estado.get('capitulos')
                    if incl is None and o.estado.get('capitulos_previos') is not None:
                        # al añadir ficheros al proyecto: lo elegido antes + los capítulos nuevos marcados
                        conocidos = set(o.estado.get('capitulos_conocidos') or [])
                        nuevos = []

                        def rec(ns):
                            for n in ns:
                                if n['clave'] not in conocidos:
                                    nuevos.append(n['clave'])
                                rec(n['hijos'])
                        rec(arbol)
                        incl = list(o.estado['capitulos_previos']) + nuevos
                    self._json({'arbol': arbol, 'incluidos': incl, 'total': round(doc.importe, 2)})
                return self._proteger(caps)
            m = re.fullmatch(r'/api/obra/([^/]+)/excel', ruta)
            if m:
                return self._proteger(lambda: self._excel(Obra.abrir(m.group(1))))
            m = re.fullmatch(r'/api/obra/([^/]+)/ficha/([^/]+)', ruta)
            if m:
                def ficha():
                    r = analisis(Obra.abrir(m.group(1)))
                    f = r.fichas.get(m.group(2))
                    if not f:
                        raise ValueError('No existe esa partida.')
                    self._json(f)
                return self._proteger(ficha)
            m = re.fullmatch(r'/api/obra/([^/]+)/pedido', ruta)
            if m:
                prov = (q.get('prov') or [''])[0]
                modo = (q.get('modo') or ['total'])[0]
                return self._proteger(lambda: self._pedido(Obra.abrir(m.group(1)), prov, modo))
            m = re.fullmatch(r'/api/obra/([^/]+)/pedidos_reparto', ruta)
            if m:
                return self._proteger(lambda: self._pedidos_reparto(Obra.abrir(m.group(1))))
            m = re.fullmatch(r'/api/obra/([^/]+)/peticion', ruta)
            if m:
                caps = [c for c in (q.get('caps') or [''])[0].split('|') if c] or None
                return self._proteger(lambda: self._peticion(Obra.abrir(m.group(1)), caps))
            m = re.fullmatch(r'/api/obra/([^/]+)/desglose/([0-9a-f]{6,64})', ruta)
            if m:
                return self._proteger(lambda: self._desglose(Obra.abrir(m.group(1)), m.group(2)))
            m = re.fullmatch(r'/api/trabajo/([0-9a-f]{32})', ruta)
            if m:
                t = TRABAJOS.get(m.group(1))
                return self._json(t.json()) if t else self._error(404, 'Trabajo desconocido.')
            if ruta == '/api/cambios':
                desde = int((q.get('v') or ['0'])[0] or 0)
                return self._json({'v': VERSION['n'], 'cambios': [c for c in VERSION['cambios'] if c['v'] > desde],
                                   'usuario': C.usuario()})
            if ruta == '/api/config':
                c = C.config()
                return self._json({'carpeta_compartida': c['carpeta_compartida'], 'usuario': c['usuario'],
                                   'activa': C.compartida_activa(), 'en_uso': C.carpeta_compartida(),
                                   'local': C.carpeta_local(), 'sugerencias': C.sugerencias_carpeta(),
                                   'obras_locales': self._obras_locales()})
            if ruta == '/api/bases':
                from . import bases
                return self._proteger(lambda: self._json([{k: b[k] for k in ('archivo', 'huella', 'origen', 'activa')}
                                                          for b in bases.listar(todas=True)]))
            m = re.fullmatch(r'/api/base/([0-9a-f]{20})/desglose', ruta)
            if m:
                return self._proteger(lambda: self._desglose_global(m.group(1)))
            if ruta == '/api/aprendizaje':
                def est():
                    from . import aprendizaje as A
                    A.cargar(db())
                    self._json(A.estado())
                return self._proteger(est)
            if ruta == '/api/decisiones':
                texto = (q.get('q') or [''])[0]
                return self._proteger(lambda: self._json(db().decisiones(texto)))
            if ruta == '/api/version':
                from . import actualizar
                return self._proteger(lambda: self._json(actualizar.estado()))
            if ruta == '/api/casos':
                return self._proteger(lambda: self._json(db().casos()))
            if ruta == '/api/bbdd':
                texto = (q.get('q') or [''])[0]
                if (q.get('modo') or [''])[0] == 'sem':
                    return self._proteger(lambda: self._json({'resumen': db().resumen(), 'filas': db().buscar_semantica(texto),
                                                              'semantica': True}))
                return self._proteger(lambda: self._json({'resumen': db().resumen(), 'filas': db().buscar(texto)}))
            if ruta == '/api/modelos':
                from . import modelos, semantica
                return self._proteger(lambda: self._json({'modelos': [modelos.estado(n) for n in modelos.MODELOS],
                                                          'semantica': semantica.estado()}))
            self._error(404, 'No encontrado.')

        def _obras_locales(self):
            base = os.path.join(C.carpeta_local(), 'obras')
            if not C.compartida_activa() or not os.path.isdir(base):
                return []
            return sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))

        def _excel(self, o):
            with BLOQUEO:
                r = analisis(o)
                fd, tmp = tempfile.mkstemp(suffix='.xlsx')
                os.close(fd)
                try:
                    excel_comparativa.escribir(r, tmp)
                    with open(tmp, 'rb') as f:
                        datos = f.read()
                finally:
                    os.remove(tmp)
            self._descargar(datos, o.nombre_excel('Comparativa'))

        def _descargar(self, datos, nombre):
            from urllib.parse import quote
            ascii_ = re.sub(r'[^\w.-]+', '_', nombre.encode('ascii', 'ignore').decode()) or 'fichero.xlsx'
            self._enviar(200, datos, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         {'Content-Disposition': 'attachment; filename="%s"; filename*=UTF-8\'\'%s'
                                                 % (ascii_, quote(nombre))})

        def _generar(self, escribir):
            fd, tmp = tempfile.mkstemp(suffix='.xlsx')
            os.close(fd)
            try:
                escribir(tmp)
                with open(tmp, 'rb') as f:
                    return f.read()
            finally:
                os.remove(tmp)

        def _peticion(self, o, caps=None):
            """Petición de oferta sin precios de los capítulos elegidos (por defecto, los que hacemos)."""
            if not o.estado.get('cliente'):
                raise ValueError('Primero sube el presupuesto del cliente.')
            with BLOQUEO:
                doc = o.documento_cliente()
            mats = M.materiales_cliente(doc)
            incl = set(caps) if caps else (set(o.estado['capitulos']) if o.estado.get('capitulos') is not None else None)
            if incl is not None:
                mats = [x for x in mats if M.clave_material_cap(x) in incl]
            if not mats:
                raise ValueError('No hay partidas en los capítulos elegidos.')
            titulos = []
            for x in mats:
                t = ' '.join(y for y in [(x.ruta_codigos[-1] if x.ruta_codigos else '') or '', x.ruta[-1] if x.ruta else '']
                             if y).strip()
                if t and t not in titulos:
                    titulos.append(t)
            d = o.estado.get('datos') or {}
            datos = self._generar(lambda ruta: excel_peticion.escribir(
                mats, ruta, obra=d.get('descripcion') or o.nombre, cod_obra=d.get('cod') or '',
                capitulos_txt='; '.join(titulos)[:400]))
            self._descargar(datos, o.nombre_excel('Peticion_oferta'))

        def _pedido(self, o, prov, modo):
            """modo 'total': todo lo que oferta el proveedor; 'reparto': solo los materiales en los que es el más barato."""
            with BLOQUEO:
                r = analisis(o)
            if not any(pv['nombre'] == prov for pv in r.distribuidores):
                raise ValueError('"%s" no es un distribuidor de esta obra.' % prov)
            if modo == 'reparto':
                ids = set(r.adjudicacion()[prov])
                if not ids:
                    raise ValueError('%s no es el más barato en ningún material.' % prov)
                motivo = 'Pedido de los materiales en los que su oferta es la más económica.'
                tipo = 'Pedido_%s' % prov
            else:
                ids, motivo, tipo = None, 'Pedido según su oferta completa.', 'Pedido_%s' % prov
            datos = self._generar(lambda ruta: excel_pedido.escribir(r, prov, ruta, ids, o.estado.get('datos') or {}, motivo))
            _decision_pedido(o, r, prov, ids)
            self._descargar(datos, o.nombre_excel(tipo))

        def _pedidos_reparto(self, o):
            """ZIP con un pedido por distribuidor con sus materiales más baratos."""
            import io
            import zipfile
            with BLOQUEO:
                r = analisis(o)
            adj = r.adjudicacion()
            b = io.BytesIO()
            with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
                for prov, ids in adj.items():
                    if ids:
                        z.writestr(o.nombre_excel('Pedido_%s' % prov), self._generar(lambda ruta: excel_pedido.escribir(
                            r, prov, ruta, set(ids), o.estado.get('datos') or {},
                            'Pedido de los materiales en los que su oferta es la más económica.')))
            if not any(adj.values()):
                raise ValueError('No hay ofertas de distribuidores con precio.')
            for prov, ids in adj.items():
                if ids:
                    _decision_pedido(o, r, prov, set(ids))
            from urllib.parse import quote
            nombre = o.nombre_excel('Pedidos_reparto')[:-5] + '.zip'
            self._enviar(200, b.getvalue(), 'application/zip',
                         {'Content-Disposition': "attachment; filename=\"pedidos.zip\"; filename*=UTF-8''%s" % quote(nombre)})

        def _desglose_global(self, h):
            from . import bases
            from .exportadores import excel_base_precios
            b = next((x for x in bases.listar(todas=True) if x['huella'] == h), None)
            if not b:
                raise ValueError('No existe esa base de precios.')
            datos = self._generar(lambda tmp: excel_base_precios.escribir(b['ruta'], tmp))
            self._descargar(datos, 'Desglose.%s.%s.xlsx' % (os.path.splitext(b['archivo'])[0],
                                                             time.strftime('%d-%m-%Y')))

        def _desglose(self, o, huella_doc):
            of = next((x for x in o.estado['ofertas'] if x['huella'].startswith(huella_doc)), None)
            if not of:
                raise ValueError('No encuentro ese documento en la obra.')
            ruta = os.path.join(o.carpeta, of['archivo'])
            from .lectores import base_precios
            if not base_precios.reconoce(ruta):
                raise ValueError('Ese documento no es una base de precios.')
            from .exportadores import excel_base_precios
            datos = self._generar(lambda tmp: excel_base_precios.escribir(ruta, tmp))
            self._descargar(datos, o.nombre_excel('Desglose_' + of['proveedor']))

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
            if ruta == '/api/config':
                def cfg():
                    d = self._json_cuerpo()
                    if set(d) <= {'token_github', 'rama_actualizaciones'}:      # solo opciones de actualización
                        C.guardar_config(token_github=d.get('token_github'), rama_actualizaciones=d.get('rama_actualizaciones'))
                        from . import actualizar
                        actualizar._ULTIMA['cuando'] = None
                        return self._json({'ok': True})
                    with BLOQUEO:
                        C.guardar_config(d.get('carpeta_compartida'), d.get('usuario'))
                        _CACHE.clear()
                        VERSION['conocimiento'] += 1
                        db().importar_conocimiento()
                    _avisar_cambio(None, 'Configuración cambiada')
                    self._json({'ok': True})
                return self._proteger(cfg)
            if ruta == '/api/modelos/descargar':
                def desc():
                    from . import modelos
                    self._json(modelos.descargar(self._json_cuerpo()['nombre']))
                return self._proteger(desc)
            if ruta == '/api/decisiones/olvidar':
                def olv():
                    D.olvidar(db(), self._json_cuerpo()['uid'])
                    _aprendido()
                    self._json({'ok': True})
                return self._proteger(olv)
            if ruta == '/api/actualizar':
                def act():
                    from . import actualizar
                    if not actualizar.instalado():
                        raise ValueError('Solo se actualiza la app instalada (ahora se ejecuta desde el código fuente).')
                    self._json({'ok': True, 'mensaje': actualizar.actualizar_ahora()})
                return self._proteger(act)
            if ruta in ('/api/bases', '/api/bases/quitar'):
                def bas():
                    from . import bases
                    if ruta == '/api/bases/quitar':
                        bases.quitar(self._json_cuerpo()['huella'])
                        msg = 'Base de precios quitada de todas las obras'
                    else:
                        partes = parsear_multipart(self.headers.get('Content-Type', ''), self._cuerpo())
                        fich = [(f, v) for k, f, v in partes if f and v]
                        if not fich:
                            raise ValueError('No se ha recibido ningún fichero.')
                        tmp = tempfile.mkdtemp(prefix='base_')
                        try:
                            for nombre_f, datos in fich:
                                ruta_tmp = os.path.join(tmp, os.path.basename(nombre_f.replace('\\', '/')))
                                with open(ruta_tmp, 'wb') as fh:
                                    fh.write(datos)
                                bases.anadir(ruta_tmp, os.path.basename(ruta_tmp))
                        finally:
                            shutil.rmtree(tmp, ignore_errors=True)
                        msg = 'Base de precios añadida: aparece en todas las obras'
                    with BLOQUEO:
                        _CACHE.clear()
                    _avisar_cambio(None, msg)
                    self._json({'ok': True, 'mensaje': msg})
                return self._proteger(bas)
            if ruta == '/api/config/llevar_obras':
                def llevar():
                    with BLOQUEO:
                        n = llevar_obras_locales()
                    _avisar_cambio(None, 'Obras locales copiadas a la carpeta compartida')
                    self._json({'ok': True, 'mensaje': '%d obras copiadas a la carpeta compartida' % n})
                return self._proteger(llevar)
            if ruta == '/api/casos/borrar':
                def borrar():
                    db().borrar_caso(int(self._json_cuerpo()['id']))
                    _CACHE.clear()
                    self._json({'ok': True})
                return self._proteger(borrar)
            if ruta == '/api/obras':
                def crear():
                    d = self._json_cuerpo()
                    o = Obra.crear(d.get('nombre', ''), (d.get('cod') or '').strip(), (d.get('cliente') or '').strip())
                    self._json({'id': o.ident})
                return self._proteger(crear)
            m = re.fullmatch(r'/api/obra/([^/]+)/(cliente|proveedor|quitar|quitar_oferta|quitar_cliente|fijar|deshacer|reanalizar|caso|capitulos|datos|aceptar)', ruta)
            if not m:
                return self._error(404, 'No encontrado.')
            accion = m.group(2)

            def hacer():
                o = Obra.abrir(m.group(1))
                if accion in ('cliente', 'proveedor'):
                    partes = parsear_multipart(self.headers.get('Content-Type', ''), self._cuerpo())
                    campos = {k: v.decode('utf-8', 'replace') for k, f, v in partes if not f}
                    recibidos = [(f, v) for k, f, v in partes if f and v]
                    if not recibidos:
                        raise ValueError('No se ha recibido ningún fichero.')
                    tmp = tempfile.mkdtemp(prefix='subida_')
                    ficheros = []
                    for nombre_f, datos in recibidos:
                        nombre_f = os.path.basename(nombre_f.replace('\\', '/'))
                        ruta_tmp = os.path.join(tmp, nombre_f)
                        with open(ruta_tmp, 'wb') as fh:
                            fh.write(datos)
                        ficheros.append((nombre_f, ruta_tmp))
                    t = Trabajo(', '.join(f for f, _ in ficheros))
                    threading.Thread(target=procesar_subida, args=(t, o, accion, ficheros, campos, tmp),
                                     daemon=True).start()
                    return self._json({'ok': True, 'trabajo': t.id})
                datos = self._json_cuerpo()
                with BLOQUEO:
                    if accion == 'quitar':
                        o.quitar_proveedor(datos['proveedor'], db())
                    elif accion == 'fijar':
                        r = analisis(o)
                        mat = next((x for x in r.materiales if x.id == datos.get('material')), None)
                        o.fijar(datos['proveedor'], datos['linea'], datos.get('material') or None,
                                clave_mat(mat) if mat else None)
                        pv = next(p for p in r.proveedores if p['nombre'] == datos['proveedor'])
                        l = next(x for x in pv['lineas'] if x.uid == str(datos['linea']))
                        _decision_fijar(o, r, pv, l, mat)
                        if mat:
                            db().aprender(datos['proveedor'], l, mat)
                    elif accion == 'deshacer':
                        r = analisis(o)
                        pv = next((p for p in r.proveedores if p['nombre'] == datos['proveedor']), None)
                        l = pv and next((x for x in pv['lineas'] if x.uid == str(datos['linea'])), None)
                        o.deshacer(datos['proveedor'], datos['linea'])
                        if l is not None:
                            db().olvidar_equivalencia(datos['proveedor'], l)
                        for u in db().c.execute("SELECT uid, datos FROM decision WHERE obra=? AND proveedor=? AND activo=1 "
                                                "AND accion IN ('casar','descasar')", (o.nombre, datos['proveedor'])).fetchall():
                            if ((json.loads(u['datos']).get('linea') or {}).get('uid')) == str(datos['linea']):
                                D.olvidar(db(), u['uid'])
                        _aprendido()
                    elif accion == 'aceptar':
                        r = analisis(o)
                        n = 0
                        for pv in r.distribuidores:
                            if datos.get('proveedor') and pv['nombre'] != datos['proveedor']:
                                continue
                            ids = [datos['material']] if datos.get('material') else list(pv['ofertas'])
                            items = [D.item(m, pv['ofertas'][m.id].principal, puntuacion=pv['ofertas'][m.id].puntuacion,
                                            muestras=D.muestras(r, pv, pv['ofertas'][m.id].principal, m))
                                     for m in r.materiales if m.id in ids and m.id in pv['ofertas']]
                            if items:
                                D.registrar(db(), 'aceptar', o.nombre, pv['nombre'], items)
                                n += len(items)
                        _aprendido()
                        return self._json({'ok': True, 'mensaje': '%d casamiento(s) aceptado(s): la app aprende de ellos' % n})
                    elif accion == 'quitar_oferta':
                        o.quitar_oferta(datos['huella'])
                    elif accion == 'quitar_cliente':
                        o.quitar_cliente(datos['huella'])
                    elif accion == 'capitulos':
                        todos = []

                        def rec(ns):
                            for n in ns:
                                todos.append(n['clave'])
                                rec(n['hijos'])
                        rec(M.arbol_capitulos(o.documento_cliente()))
                        o.elegir_capitulos(datos.get('incluidos') or [], todos)
                        analisis(o, forzar=True)
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
                    elif accion == 'datos':
                        o.poner_datos((datos.get('cod') or '').strip(), (datos.get('cliente') or '').strip(),
                                      (datos.get('descripcion') or '').strip())
                    elif accion == 'reanalizar':
                        analisis(o, forzar=True)
                self._json({'ok': True})
            self._proteger(hacer)

    sinc = Sincronizador()
    sinc.start()
    if not os.environ.get('AUTOMATIZADOR_SIN_DESCARGAS'):
        from . import modelos
        if not modelos.ruta('e5-small'):            # comprensión del texto: se descarga sola (~135 MB, una vez)
            modelos.descargar('e5-small')
    srv = ThreadingHTTPServer(('127.0.0.1', puerto), Manejador)
    url = 'http://127.0.0.1:%d/' % puerto
    print('App abierta en %s  (Ctrl+C para cerrar)' % url)
    print('Base de datos local en:', os.path.dirname(ruta_bbdd()))
    print('Carpeta de trabajo (obras):', C.carpeta_compartida(),
          '(COMPARTIDA)' if C.compartida_activa() else '(solo este PC: configura una carpeta compartida en la app)')
    print('Usuario:', C.usuario())
    if abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('Cerrado.')
    finally:
        srv.server_close()
