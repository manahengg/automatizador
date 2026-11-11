"""Comprensión del texto (fase 1 del aprendizaje): cada partida / línea se convierte en un vector de "significado".

Modelo: multilingual-e5-small (Microsoft/intfloat), versión ONNX cuantizada (~118 MB), ejecutado con onnxruntime (el
mismo motor que el OCR, firmado por Microsoft). Funciona en el procesador de un PC normal: milisegundos por texto.
El tokenizador (trocear el texto como lo espera el modelo) está escrito aquí en Python para no añadir más librerías.

Textos que dicen lo mismo con otras palabras ("Derivación individual 4x35+TT16" / "Línea RZ1-K 4x35+1x16 bajo tubo")
quedan cerca: su parecido (coseno) es alto. Si el modelo no está descargado, todo sigue funcionando sin esta parte.
"""
import hashlib
import json
import math
import os
import re
import threading
import unicodedata

import numpy as np

from . import modelos

MODELO = 'e5-small'
MAX_TOKENS = 128
_LOCK = threading.Lock()
_EST = {'tok': None, 'sesion': None, 'error': None}
_CACHE = {}                 # (prefijo+texto) -> vector


# ------------------------------------------------------------------------------------------- tokenizador
class Unigram:
    """Tokenizador SentencePiece-Unigram (el de XLM-R / e5) a partir de tokenizer.json."""

    def __init__(self, ruta):
        with open(ruta, encoding='utf-8') as f:
            t = json.load(f)
        vocab = t['model']['vocab']
        self.piezas = {p: (i, s) for i, (p, s) in enumerate(vocab)}
        self.unk = t['model'].get('unk_id', 3)
        self.unk_score = min(s for _, s in vocab) - 10.0
        self.max_len = max(len(p) for p, _ in vocab if len(p) < 40)
        self.bos, self.eos = 0, 2

    @staticmethod
    def normalizar(texto):
        texto = unicodedata.normalize('NFKC', texto or '')
        return re.sub(r'\s+', ' ', texto).strip()

    def _viterbi(self, palabra):
        n = len(palabra)
        mejor = [(-math.inf, None, None)] * (n + 1)      # (puntuación, inicio, id)
        mejor[0] = (0.0, None, None)
        for fin in range(1, n + 1):
            for ini in range(max(0, fin - self.max_len), fin):
                if mejor[ini][0] == -math.inf:
                    continue
                p = self.piezas.get(palabra[ini:fin])
                if p is not None:
                    sc = mejor[ini][0] + p[1]
                    if sc > mejor[fin][0]:
                        mejor[fin] = (sc, ini, p[0])
            if mejor[fin][0] == -math.inf:                  # carácter desconocido
                mejor[fin] = (mejor[fin - 1][0] + self.unk_score, fin - 1, self.unk)
        ids, fin = [], n
        while fin > 0:
            _, ini, i = mejor[fin]
            ids.append(i)
            fin = ini
        ids.reverse()
        out = []
        for i in ids:                                       # unk seguidos se funden en uno
            if not (i == self.unk and out and out[-1] == self.unk):
                out.append(i)
        return out

    def codificar(self, texto, max_tokens=MAX_TOKENS):
        ids = []
        for palabra in self.normalizar(texto).split(' '):
            if palabra:
                ids.extend(self._viterbi('▁' + palabra))
            if len(ids) >= max_tokens - 2:
                break
        return [self.bos] + ids[:max_tokens - 2] + [self.eos]


# ------------------------------------------------------------------------------------------- modelo
def _cargar():
    if _EST['sesion'] is not None or _EST['error']:
        return _EST['sesion'] is not None
    d = modelos.ruta(MODELO)
    if not d:
        return False
    try:
        import onnxruntime as ort
        op = ort.SessionOptions()
        op.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2)))
        _EST['tok'] = Unigram(os.path.join(d, 'tokenizer.json'))
        _EST['sesion'] = ort.InferenceSession(os.path.join(d, 'model_quantized.onnx'), op,
                                              providers=['CPUExecutionProvider'])
        _EST['entradas'] = {i.name for i in _EST['sesion'].get_inputs()}
        return True
    except Exception as e:
        _EST['error'] = str(e)
        return False


def disponible():
    with _LOCK:
        return _cargar()


def estado():
    return {'modelo': MODELO, 'descargado': bool(modelos.ruta(MODELO)), 'cargado': _EST['sesion'] is not None,
            'error': _EST['error']}


def _limpiar(texto):
    t = re.sub(r'\s+', ' ', str(texto or '')).strip()
    return t[:400]


_DISCO = {}


def _disco():
    """Caché en disco de vectores ya calculados (carpeta local): no se recalculan al reiniciar la app."""
    if 'c' not in _DISCO:
        import sqlite3
        from . import compartido as C
        c = sqlite3.connect(os.path.join(C.carpeta_local(), 'vectores_%s.db' % MODELO), check_same_thread=False)
        c.execute('CREATE TABLE IF NOT EXISTS v (k TEXT PRIMARY KEY, v BLOB)')
        _DISCO['c'] = c
    return _DISCO['c']


def vectores(textos, tipo='query', lote=32):
    """Matriz (n, 384) normalizada. tipo: 'query' (lo que se busca) o 'passage' (en lo que se busca); para comparar
    partidas con partidas se usa 'query' en los dos lados (simétrico). None si el modelo no está disponible."""
    with _LOCK:
        if not _cargar():
            return None
        out = [None] * len(textos)
        pend = []
        for i, t in enumerate(textos):
            k = tipo + ': ' + _limpiar(t)
            if k in _CACHE:
                out[i] = _CACHE[k]
            else:
                pend.append((i, k))
        if pend:
            try:                                                        # lo ya calculado otras veces, del disco
                db = _disco()
                faltan = []
                for i, k in pend:
                    h = hashlib.sha1(k.encode('utf-8')).hexdigest()
                    r = db.execute('SELECT v FROM v WHERE k=?', (h,)).fetchone()
                    if r:
                        vec = np.frombuffer(r[0], dtype=np.float16).astype(np.float32)
                        _CACHE[k] = out[i] = vec
                    else:
                        faltan.append((i, k))
                pend = faltan
            except Exception:
                db = None
        nuevos = []
        s, tok = _EST['sesion'], _EST['tok']
        for a in range(0, len(pend), lote):
            trozo = pend[a:a + lote]
            ids = [tok.codificar(k) for _, k in trozo]
            largo = max(len(x) for x in ids)
            m_ids = np.ones((len(ids), largo), dtype=np.int64)            # 1 = <pad>
            m_att = np.zeros((len(ids), largo), dtype=np.int64)
            for j, x in enumerate(ids):
                m_ids[j, :len(x)] = x
                m_att[j, :len(x)] = 1
            entradas = {'input_ids': m_ids, 'attention_mask': m_att}
            if 'token_type_ids' in _EST['entradas']:
                entradas['token_type_ids'] = np.zeros_like(m_ids)
            h = s.run(None, entradas)[0]                                     # (n, largo, 384)
            mask = m_att[:, :, None].astype(np.float32)
            v = (h * mask).sum(1) / np.maximum(mask.sum(1), 1)
            v = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
            for (i, k), vec in zip(trozo, v.astype(np.float32)):
                _CACHE[k] = vec
                out[i] = vec
                nuevos.append((hashlib.sha1(k.encode('utf-8')).hexdigest(), vec.astype(np.float16).tobytes()))
        if nuevos:
            try:
                _disco().executemany('INSERT OR REPLACE INTO v (k, v) VALUES (?,?)', nuevos)
                _disco().commit()
            except Exception:
                pass
        if len(_CACHE) > 200000:
            _CACHE.clear()
        return np.stack(out) if out else np.zeros((0, 384), dtype=np.float32)


def texto_material(m):
    """Lo que representa una partida del cliente para compararla (título + material interpretado + inicio del texto)."""
    p = m.partida
    return ' '.join(x for x in [p.resumen or '', m.descripcion or '', (p.descripcion or '')[:160]] if x)


def texto_linea(l):
    return l.partida.descripcion or ''


def huella_texto(t):
    return hashlib.sha1(_limpiar(t).encode('utf-8')).hexdigest()[:16]
