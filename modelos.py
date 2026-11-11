"""Modelos de IA locales (se descargan UNA vez; luego todo funciona sin internet).

    e5-small   comprensión del texto (fase 1): ~135 MB, se descarga sola al abrir la app
    llm        modelo de lenguaje que redacta (fase 4): ~2,5-3 GB, se descarga cuando alguien lo pide (Aprendizaje)

Dónde se guardan:
    <carpeta local>/modelos/<nombre>/          el que usa este PC
    <carpeta compartida>/modelos/<nombre>/     copia para los demás PCs (la toman de ahí en vez de internet)
Un modelo está completo cuando su carpeta tiene 'completo.json' (se escribe al final: una descarga cortada no cuenta).
Los ficheros de modelo son datos (no programas): Smart App Control no los bloquea.
"""
import json
import os
import shutil
import threading
import time
import urllib.request

from . import compartido as C

HF = 'https://huggingface.co/%s/resolve/main/%s'
MODELOS = {
    'e5-small': {'repo': 'Xenova/multilingual-e5-small', 'titulo': 'Comprensión del texto (multilingual-e5-small)',
                 'ficheros': {'onnx/model_quantized.onnx': 'model_quantized.onnx', 'tokenizer.json': 'tokenizer.json',
                              'config.json': 'config.json'}, 'mb': 135},
}
_DESCARGAS = {}                 # nombre -> {'estado', 'fraccion', 'texto', 'error'}
_LOCK = threading.Lock()


def registrar(nombre, info):
    MODELOS[nombre] = info


def _dir_local(nombre):
    base = os.environ.get('AUTOMATIZADOR_MODELOS') or os.path.join(C.carpeta_local(), 'modelos')
    return os.path.join(base, nombre)


def _dir_compartido(nombre):
    if not C.compartida_activa():
        return None
    return os.path.join(C.carpeta_compartida(), 'modelos', nombre)


def _completo(d):
    return bool(d) and os.path.exists(os.path.join(d, 'completo.json'))


def ruta(nombre):
    """Carpeta del modelo si está disponible en este PC (si solo está en la carpeta compartida, se copia)."""
    d = _dir_local(nombre)
    if _completo(d):
        return d
    dc = _dir_compartido(nombre)
    if _completo(dc):
        try:
            _copiar(dc, d)
            return d
        except OSError:
            return dc                               # se usa directamente desde la carpeta compartida
    return None


def _copiar(origen, destino):
    tmp = destino + '.copiando'
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(origen, tmp)
    shutil.rmtree(destino, ignore_errors=True)
    os.replace(tmp, destino)


def estado(nombre):
    info = MODELOS[nombre]
    return {'nombre': nombre, 'titulo': info['titulo'], 'mb': info['mb'], 'disponible': bool(ruta(nombre)),
            'descarga': _DESCARGAS.get(nombre)}


def descargar(nombre, segundo_plano=True):
    """Descarga el modelo de Hugging Face (público, sin cuenta). Devuelve el estado de la descarga."""
    with _LOCK:
        d = _DESCARGAS.get(nombre)
        if d and d['estado'] == 'descargando':
            return d
        if ruta(nombre):
            return {'estado': 'listo', 'fraccion': 1.0, 'texto': 'Ya descargado', 'error': None}
        _DESCARGAS[nombre] = d = {'estado': 'descargando', 'fraccion': 0.0, 'texto': 'Empezando…', 'error': None}
    if segundo_plano:
        threading.Thread(target=_descargar, args=(nombre,), daemon=True).start()
    else:
        _descargar(nombre)
    return d


def _descargar(nombre):
    info = MODELOS[nombre]
    est = _DESCARGAS[nombre]
    destino = _dir_local(nombre)
    tmp = destino + '.descargando'
    try:
        os.makedirs(tmp, exist_ok=True)
        total_mb = float(info['mb'])
        hecho = 0
        for remoto, local in info['ficheros'].items():
            url = HF % (info['repo'], remoto)
            final = os.path.join(tmp, local)
            os.makedirs(os.path.dirname(final), exist_ok=True)
            if os.path.exists(final) and os.path.getsize(final) > 0:
                hecho += os.path.getsize(final)
                continue
            req = urllib.request.Request(url, headers={'User-Agent': 'comparador-ofertas'})
            with urllib.request.urlopen(req, timeout=60) as r, open(final + '.part', 'wb') as f:
                t0 = time.time()
                while True:
                    trozo = r.read(1 << 20)
                    if not trozo:
                        break
                    f.write(trozo)
                    hecho += len(trozo)
                    est['fraccion'] = min(0.99, hecho / (total_mb * 1048576))
                    est['texto'] = 'Descargando %s: %d de ~%d MB' % (local, hecho // 1048576, total_mb)
                    if time.time() - t0 > 7200:
                        raise TimeoutError('la descarga tarda demasiado')
            os.replace(final + '.part', final)
        with open(os.path.join(tmp, 'completo.json'), 'w', encoding='utf-8') as f:
            json.dump({'repo': info['repo'], 'cuando': time.strftime('%Y-%m-%dT%H:%M:%S')}, f)
        shutil.rmtree(destino, ignore_errors=True)
        os.replace(tmp, destino)
        est.update(estado='listo', fraccion=1.0, texto='Descargado')
        dc = _dir_compartido(nombre)                 # copia para los demás PCs
        if dc and not _completo(dc):
            est['texto'] = 'Descargado. Copiando a la carpeta compartida para los demás PCs…'
            try:
                _copiar(destino, dc)
                est['texto'] = 'Descargado y compartido con los demás PCs'
            except OSError as e:
                est['texto'] = 'Descargado (no se pudo copiar a la carpeta compartida: %s)' % e
    except Exception as e:
        est.update(estado='error', error=str(e), texto='Error en la descarga: %s' % e)
