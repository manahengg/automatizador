"""Actualización automática del código de la app instalada (sin volver a descargar el ZIP completo).

Cómo llega una versión nueva a cada PC:
  1. Un PC con permiso de lectura de GitHub (token en ⚙ Configuración; el repositorio es privado) descarga el código de
     la rama elegida (por defecto "main") y lo deja también en la carpeta compartida:
         <carpeta compartida>/actualizaciones/<fecha>_<sha>.zip   (+ .json)   (solo se crean ficheros, nunca se modifican)
  2. Los demás PCs, al abrir la app, ven en la carpeta compartida que hay una versión más reciente y se la copian.
Solo se cambia la carpeta app\\automatizador (ficheros .py: Smart App Control no los bloquea). Python y las librerías no
se tocan: si una versión nueva necesita librerías distintas (cambia requirements.txt) hay que instalar el ZIP completo
una vez, y la app lo dice. Si la versión nueva no arranca, el lanzador vuelve sola a la anterior.
"""
import datetime
import hashlib
import io
import json
import os
import py_compile
import shutil
import tempfile
import urllib.request
import zipfile

from . import compartido as C

REPO = 'manahengg/automatizador'
PAQUETE = os.path.dirname(os.path.abspath(__file__))           # ...\app\automatizador
EXCLUIR = {'obras', 'tests', '__pycache__', '.git', '.github', 'build', 'dist', 'paquete', 'venv', '.venv',
           'automatizador_datos'}
_ULTIMA = {'cuando': None, 'resultado': None}


def instalado():
    """True en la app instalada (python\\ y app\\automatizador); False al ejecutar desde el código fuente (git)."""
    raiz = os.path.dirname(os.path.dirname(PAQUETE))
    return os.path.exists(os.path.join(raiz, 'python', 'python.exe')) and not os.path.isdir(os.path.join(PAQUETE, '.git'))


def version_actual(carpeta=PAQUETE):
    try:
        with open(os.path.join(carpeta, 'VERSION.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'sha': None, 'fecha': ''}


def _utc(fecha):
    """'2026-11-11T08:30:00+01:00' / '...Z' -> '2026-11-11T07:30:00Z' (para comparar fechas de git y de GitHub)."""
    try:
        d = datetime.datetime.fromisoformat((fecha or '').replace('Z', '+00:00'))
        return d.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        return fecha or ''


def _hash_requisitos(texto):
    lineas = sorted(x.strip().lower() for x in texto.splitlines() if x.strip() and not x.strip().startswith('#'))
    return hashlib.sha256('\n'.join(lineas).encode()).hexdigest()[:16]


def _requisitos_actuales():
    try:
        with open(os.path.join(PAQUETE, 'requirements.txt'), encoding='utf-8') as f:
            return _hash_requisitos(f.read())
    except OSError:
        return None


def _rama():
    """Rama de la que se actualiza: la configurada o, si no, la del ZIP instalado (y si no se sabe, main)."""
    return (C.config().get('rama_actualizaciones') or version_actual().get('rama') or 'main').strip()


def _token():
    return (C.config().get('token_github') or '').strip()


def _dir_compartido():
    if not C.compartida_activa():
        return None
    return os.path.join(C.carpeta_compartida(), 'actualizaciones')


def _github(url, token, timeout):
    """Con token si lo hay (repositorio privado); sin token funciona si el repositorio es público."""
    cab = {'User-Agent': 'comparador-ofertas', 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        cab['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ValueError('GitHub rechaza el token (caducado o sin permiso de lectura del repositorio).')
        if e.code == 404 and not token:
            raise ValueError('El repositorio es privado: hace falta un token de GitHub (⚙ Configuración) en al menos '
                             'un PC, o que el repositorio sea público.')
        if e.code == 404:
            raise ValueError('GitHub no encuentra el repositorio o la rama "%s" (¿el token tiene acceso a %s?).'
                             % (_rama(), REPO))
        raise


# ------------------------------------------------------------------------------------------------ buscar
def buscar(timeout=6):
    """Versión más reciente disponible (carpeta compartida o GitHub) que sea más nueva que la instalada, o None.
    -> {'sha', 'fecha', 'origen': 'compartida'|'github', 'zip': ruta (compartida), 'mensaje'}"""
    actual = version_actual()
    cands = []
    d = _dir_compartido()
    if d and os.path.isdir(d):
        for n in os.listdir(d):
            if n.endswith('.json') and not n.startswith('~$'):
                try:
                    with open(os.path.join(d, n), encoding='utf-8') as f:
                        j = json.load(f)
                    z = os.path.join(d, n[:-5] + '.zip')
                    if os.path.exists(z) and j.get('rama', 'main') == _rama():
                        cands.append(dict(j, origen='compartida', zip=z))
                except (OSError, ValueError):
                    continue
    tok = _token()
    try:
        j = json.loads(_github('https://api.github.com/repos/%s/commits/%s' % (REPO, _rama()), tok, timeout))
    except Exception:
        if tok or not cands:                 # sin token y con la carpeta compartida al día: no es un error
            raise
        j = None
    if j:
        cands.append({'sha': j['sha'], 'fecha': j['commit']['committer']['date'],
                      'mensaje': j['commit']['message'].split('\n')[0][:200], 'origen': 'github', 'rama': _rama()})
    for c in cands:
        c['fecha'] = _utc(c.get('fecha'))
    cands = [c for c in cands if c.get('sha') and c['sha'] != actual.get('sha') and c['fecha'] > _utc(actual.get('fecha'))]
    if not cands:
        return None
    return max(cands, key=lambda c: (c['fecha'], c['origen'] == 'compartida'))


# ------------------------------------------------------------------------------------------------ aplicar
def _codigo_de_zip(datos):
    """Del ZIP de GitHub (carpeta raíz 'propietario-repo-sha/') o del de la carpeta compartida: {ruta relativa: bytes},
    solo el código de la app."""
    z = zipfile.ZipFile(io.BytesIO(datos))
    nombres = [n for n in z.namelist() if not n.endswith('/')]
    raiz = ''
    if not any(n == 'app_web.py' for n in nombres):
        raiz = next((n[:-len('app_web.py')] for n in nombres if n.endswith('/app_web.py') and n.count('/') == 1), None)
        if raiz is None:
            raise ValueError('El paquete descargado no contiene la app.')
    out = {}
    for n in nombres:
        if not n.startswith(raiz):
            continue
        rel = n[len(raiz):]
        partes = rel.split('/')
        if any(p in EXCLUIR for p in partes) or rel.endswith('.pyc'):
            continue
        out[rel] = z.read(n)
    return out


def _zip_de_codigo(ficheros):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel, datos in sorted(ficheros.items()):
            z.writestr(rel, datos)
    return b.getvalue()


def aplicar(cand, destino=PAQUETE):
    """Sustituye el código instalado por la versión cand. Devuelve un texto para la persona."""
    if cand['origen'] == 'github':
        datos = _github('https://api.github.com/repos/%s/zipball/%s' % (REPO, cand['sha']), _token(), 120)
    else:
        with open(cand['zip'], 'rb') as f:
            datos = f.read()
    ficheros = _codigo_de_zip(datos)
    for imprescindible in ('__init__.py', 'app_web.py', 'obra.py', 'windows/lanzador.py', 'requirements.txt'):
        if imprescindible not in ficheros:
            raise ValueError('El paquete descargado está incompleto (falta %s).' % imprescindible)
    if _hash_requisitos(ficheros['requirements.txt'].decode('utf-8', 'replace')) != _requisitos_actuales():
        raise ValueError('La versión nueva necesita librerías distintas: hay que instalar una vez el ZIP completo '
                         '(GitHub → Actions → "Instalador Windows" → Artifacts). Después ya se actualizará sola.')
    nuevo, anterior = destino + '.nuevo', destino + '.anterior'
    shutil.rmtree(nuevo, ignore_errors=True)
    for rel, contenido in ficheros.items():
        ruta = os.path.join(nuevo, *rel.split('/'))
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, 'wb') as f:
            f.write(contenido)
    tmp = tempfile.mkdtemp(prefix='compilar_')
    try:
        for rel in ficheros:                       # que todo el código al menos se pueda leer antes de cambiarlo
            if rel.endswith('.py'):
                py_compile.compile(os.path.join(nuevo, *rel.split('/')), cfile=os.path.join(tmp, 'x.pyc'), doraise=True)
    except py_compile.PyCompileError as e:
        shutil.rmtree(nuevo, ignore_errors=True)
        raise ValueError('La versión nueva tiene un error y no se instala: %s' % e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    with open(os.path.join(nuevo, 'VERSION.json'), 'w', encoding='utf-8') as f:
        json.dump({'sha': cand['sha'], 'fecha': cand['fecha'], 'mensaje': cand.get('mensaje', ''),
                   'rama': cand.get('rama', _rama()), 'instalada': datetime.datetime.now().isoformat(timespec='seconds')},
                  f, ensure_ascii=False, indent=1)
    shutil.rmtree(anterior, ignore_errors=True)
    os.rename(destino, anterior)
    try:
        os.rename(nuevo, destino)
    except OSError:
        os.rename(anterior, destino)
        raise
    if cand['origen'] == 'github':
        _publicar(ficheros, cand)
    return 'Actualizado a la versión del %s (%s)%s' % (
        cand['fecha'][:16].replace('T', ' '), cand['sha'][:7], ': ' + cand['mensaje'] if cand.get('mensaje') else '')


def _publicar(ficheros, cand):
    """Deja la versión en la carpeta compartida para que los demás PCs se actualicen sin token."""
    d = _dir_compartido()
    if not d:
        return
    os.makedirs(d, exist_ok=True)
    base = '%s_%s' % (cand['fecha'].replace(':', '').replace('-', '')[:15], cand['sha'][:12])
    if os.path.exists(os.path.join(d, base + '.json')):
        return
    for ext, datos in (('.zip', _zip_de_codigo(ficheros)),
                       ('.json', json.dumps({'sha': cand['sha'], 'fecha': cand['fecha'], 'mensaje': cand.get('mensaje', ''),
                                             'rama': cand.get('rama', _rama()), 'publicada_por': C.usuario()},
                                            ensure_ascii=False).encode())):
        tmp = os.path.join(d, '~$' + base + ext)
        with open(tmp, 'wb') as f:
            f.write(datos)
        os.replace(tmp, os.path.join(d, base + ext))      # el .json va el último: indica que el .zip está completo


def revertir(destino=PAQUETE):
    """Vuelve a la versión anterior (si la nueva no arranca)."""
    anterior = destino + '.anterior'
    if not os.path.isdir(anterior):
        return False
    roto = destino + '.fallida'
    shutil.rmtree(roto, ignore_errors=True)
    os.rename(destino, roto)
    os.rename(anterior, destino)
    return True


# ------------------------------------------------------------------------------------------------ uso
def al_arrancar():
    """Lo llama el lanzador antes de cargar la app. Nunca impide arrancar: si algo falla, se sigue con lo instalado."""
    if not instalado():
        return None
    try:
        cand = buscar(timeout=5)
        if not cand:
            return None
        print('Hay una versión nueva (%s). Actualizando…' % cand['fecha'][:10])
        return aplicar(cand)
    except Exception as e:                                       # sin conexión, token caducado...
        if 'repositorio es privado' in str(e):
            return None                                          # este PC no tiene token: no es un error
        return 'No se ha podido actualizar (%s). Se abre la versión instalada.' % e


def estado(comprobar=True):
    """Para la pantalla de Configuración."""
    v = version_actual()
    out = {'instalada': instalado(), 'version': v, 'rama': _rama(), 'tiene_token': bool(_token()),
           'compartida': bool(_dir_compartido()), 'disponible': None, 'error': None}
    if comprobar and out['instalada']:
        ahora = datetime.datetime.now()
        if _ULTIMA['cuando'] and (ahora - _ULTIMA['cuando']).seconds < 600:
            out['disponible'], out['error'] = _ULTIMA['resultado']
        else:
            try:
                c = buscar(timeout=5)
                out['disponible'] = c and {k: c.get(k) for k in ('sha', 'fecha', 'mensaje', 'origen')}
            except Exception as e:
                out['error'] = str(e)
            _ULTIMA['cuando'], _ULTIMA['resultado'] = ahora, (out['disponible'], out['error'])
    return out


def actualizar_ahora():
    _ULTIMA['cuando'] = None
    cand = buscar(timeout=10)
    if not cand:
        return 'Ya tienes la última versión.'
    return aplicar(cand) + '. Cierra la ventana negra de la app y vuelve a abrirla para usarla.'
