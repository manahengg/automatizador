"""Trabajo en equipo a través de una carpeta compartida (SharePoint / OneDrive sincronizado, o una unidad de red).

Regla de oro: en la carpeta compartida NUNCA se modifica un fichero; solo se crean ficheros nuevos.
Así OneDrive/SharePoint no pueden generar conflictos ("fichero-PC-JUAN.json") ni perder cambios.

Estructura de la carpeta compartida:
    obras/<obra>/cliente/...                documentos del cliente (no se modifican)
    obras/<obra>/proveedores/<prov>/...     ofertas (no se modifican)
    obras/<obra>/eventos/<fecha>_<usuario>_<id>.json     lo que ha hecho cada persona en la obra
    conocimiento/<fecha>_<usuario>_<id>.json             equivalencias aprendidas y casos anotados
    cache/<lector>_<huella>_v<N>.json        lecturas ya hechas (el OCR de un escaneo se hace una vez para todos)

Carpeta LOCAL de cada PC (%LOCALAPPDATA%\\ComparadorOfertas o AUTOMATIZADOR_DATOS):
    config.json      carpeta compartida y nombre de usuario
    precios.db       base de datos local (se rehace sola a partir de lo compartido)
"""
import datetime
import getpass
import json
import os
import re
import uuid


# --------------------------------------------------------------------------------------------- configuración
def carpeta_local():
    d = os.environ.get('AUTOMATIZADOR_DATOS') or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'automatizador_datos')
    os.makedirs(d, exist_ok=True)
    return d


def _ruta_config():
    return os.path.join(carpeta_local(), 'config.json')


def config():
    try:
        with open(_ruta_config(), encoding='utf-8') as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    c.setdefault('carpeta_compartida', '')
    c.setdefault('usuario', _usuario_sistema())
    return c


def guardar_config(carpeta=None, usuario=None):
    c = config()
    if carpeta is not None:
        carpeta = carpeta.strip().strip('"')
        if carpeta:
            if not os.path.isdir(carpeta):
                raise ValueError('La carpeta "%s" no existe (¿está sincronizada con OneDrive en este PC?).' % carpeta)
            prueba = os.path.join(carpeta, '.prueba_escritura_%s' % uuid.uuid4().hex[:6])
            try:
                with open(prueba, 'w') as f:
                    f.write('ok')
                os.remove(prueba)
            except OSError as e:
                raise ValueError('No se puede escribir en "%s": %s' % (carpeta, e))
        c['carpeta_compartida'] = carpeta
    if usuario is not None and usuario.strip():
        c['usuario'] = usuario.strip()[:40]
    with open(_ruta_config(), 'w', encoding='utf-8') as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    return c


def _usuario_sistema():
    try:
        return getpass.getuser()
    except Exception:
        return 'usuario'


def usuario():
    return config()['usuario']


def carpeta_compartida():
    """Donde viven obras, conocimiento y caché. Sin carpeta compartida configurada: la local (uso individual)."""
    c = config()['carpeta_compartida']
    base = c if c and os.path.isdir(c) else carpeta_local()
    return base


def compartida_activa():
    c = config()['carpeta_compartida']
    return bool(c and os.path.isdir(c))


def sugerencias_carpeta():
    """Carpetas de OneDrive / SharePoint sincronizadas en este PC (para proponerlas en la configuración)."""
    out = []
    raices = [os.environ.get(k) for k in ('OneDriveCommercial', 'OneDrive', 'OneDriveConsumer')]
    perfil = os.path.expanduser('~')
    try:
        raices += [os.path.join(perfil, d) for d in os.listdir(perfil) if os.path.isdir(os.path.join(perfil, d))]
    except OSError:
        pass
    vistos = set()
    for r in raices:
        if not r or r in vistos or not os.path.isdir(r):
            continue
        vistos.add(r)
        nombre = os.path.basename(r)
        if 'onedrive' in nombre.lower() or ' - ' in nombre:      # "Empresa" de SharePoint: "Sitio - Documentos"
            out.append(r)
            try:
                for d in os.listdir(r):
                    p = os.path.join(r, d)
                    if os.path.isdir(p) and ('compar' in d.lower() or 'oferta' in d.lower() or ' - ' in d):
                        out.append(p)
            except OSError:
                pass
    return out[:20]


# --------------------------------------------------------------------------------------------- eventos
def _sello():
    return datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')


def _seguro(t):
    return re.sub(r'[^\w-]+', '_', t, flags=re.U)[:30] or 'x'


def escribir_evento(carpeta, tipo, datos):
    """Crea un fichero de evento NUEVO (nunca se reescribe uno existente). Devuelve el evento."""
    os.makedirs(carpeta, exist_ok=True)
    ev = {'id': uuid.uuid4().hex, 'tipo': tipo, 'cuando': datetime.datetime.now().isoformat(timespec='seconds'),
          'usuario': usuario(), 'datos': datos}
    nombre = '%s_%s_%s.json' % (_sello(), _seguro(ev['usuario']), ev['id'][:8])
    tmp = os.path.join(carpeta, '~$' + nombre + '.tmp')          # OneDrive no sincroniza ficheros "~$…"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(ev, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(carpeta, nombre))
    return ev


def leer_eventos(carpeta):
    """Eventos de una carpeta, en orden. Los ficheros a medio sincronizar o dañados se ignoran (se leerán luego)."""
    if not os.path.isdir(carpeta):
        return []
    out = []
    for n in sorted(os.listdir(carpeta)):
        if not n.endswith('.json') or n.startswith('~$'):
            continue
        try:
            with open(os.path.join(carpeta, n), encoding='utf-8') as f:
                ev = json.load(f)
            ev['_fichero'] = n
            out.append(ev)
        except (OSError, ValueError):
            continue
    return out


def marca_carpeta(*carpetas):
    """Huella barata de 'algo ha cambiado' en unas carpetas (nº de ficheros y última modificación)."""
    n, ultima = 0, 0.0
    for c in carpetas:
        if not os.path.isdir(c):
            continue
        for raiz, _, ficheros in os.walk(c):
            for f in ficheros:
                if f.startswith('~$'):
                    continue
                n += 1
                try:
                    ultima = max(ultima, os.path.getmtime(os.path.join(raiz, f)))
                except OSError:
                    pass
    return (n, ultima)
