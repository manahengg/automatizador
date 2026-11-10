"""Palabras con coordenadas de cada página de un PDF, venga con texto o sea un escaneo.

Todos los lectores PDF trabajan sobre esto, así que da igual de dónde salga el texto:

  * PDF con texto  -> pdfplumber (rápido y exacto).
  * PDF escaneado  -> OCR con RapidOCR (se instala con pip, sin programas externos; funciona en Windows).
                      Si no está, se intenta con Tesseract (pytesseract) si existe en el equipo.

Cada palabra es un dict {'text', 'x0', 'x1', 'top', 'bottom'} en PUNTOS de la página (como pdfplumber),
también las del OCR (se convierten de píxeles a puntos), para que los lectores no tengan que distinguir.
"""
import re

import pdfplumber

from .texto import reparar_mojibake

ESCALA_OCR = 2.5          # 2.5 x 72 ppp = 180 ppp: suficiente para facturas y presupuestos escaneados
_MOTOR = None


class SinOCR(RuntimeError):
    pass


def _motor_ocr():
    global _MOTOR
    if _MOTOR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _MOTOR = ('rapidocr', RapidOCR())
        except ImportError:
            try:
                import pytesseract  # noqa: F401
                _MOTOR = ('tesseract', None)
            except ImportError:
                raise SinOCR('El PDF es un escaneo (no tiene texto) y no hay motor de OCR instalado. '
                             'Instala RapidOCR con:  pip install rapidocr_onnxruntime')
    return _MOTOR


def _ocr_pagina(ruta, indice):
    import numpy as np
    import pypdfium2
    pdf = pypdfium2.PdfDocument(ruta)
    try:
        pagina = pdf[indice]
        imagen = pagina.render(scale=ESCALA_OCR).to_pil().convert('RGB')
    finally:
        pdf.close()
    nombre, motor = _motor_ocr()
    k = 1.0 / ESCALA_OCR
    palabras = []
    if nombre == 'rapidocr':
        resultado, _ = motor(np.array(imagen))
        for caja, texto, confianza in resultado or []:
            xs = [p[0] for p in caja]
            ys = [p[1] for p in caja]
            palabras.extend(_trocear(texto, min(xs) * k, max(xs) * k, min(ys) * k, max(ys) * k, float(confianza)))
    else:
        import pytesseract
        d = pytesseract.image_to_data(imagen, lang='spa', output_type=pytesseract.Output.DICT)
        for i, t in enumerate(d['text']):
            if t.strip():
                palabras.append({'text': t, 'x0': d['left'][i] * k, 'x1': (d['left'][i] + d['width'][i]) * k,
                                 'top': d['top'][i] * k, 'bottom': (d['top'][i] + d['height'][i]) * k,
                                 'conf': float(d['conf'][i]) / 100})
    return palabras


def _trocear(texto, x0, x1, top, bottom, conf):
    """RapidOCR devuelve frases enteras; se reparten en palabras con x proporcional al nº de caracteres."""
    trozos = texto.split()
    if not trozos:
        return []
    total = max(1, len(texto))
    ancho = (x1 - x0) / total
    out, pos = [], 0
    for t in trozos:
        i = texto.index(t, pos)
        out.append({'text': t, 'x0': x0 + i * ancho, 'x1': x0 + (i + len(t)) * ancho, 'top': top, 'bottom': bottom,
                    'conf': conf})
        pos = i + len(t)
    return out


def paginas(ruta, progreso=None):
    """Lista de páginas; cada una: {'ancho', 'alto', 'palabras': [...], 'ocr': bool}."""
    out = []
    with pdfplumber.open(ruta) as pdf:
        n = len(pdf.pages)
        for i, pag in enumerate(pdf.pages):
            palabras = pag.extract_words(x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False, use_text_flow=False)
            for w in palabras:
                w['text'] = reparar_mojibake(w['text'])
            palabras = [w for w in palabras if w['text']]
            ocr = False
            if len(palabras) < 5:                     # página sin texto: es una imagen escaneada
                if progreso:
                    progreso('OCR de la página %d de %d (PDF escaneado)…' % (i + 1, n))
                palabras = _ocr_pagina(ruta, i)
                ocr = True
            out.append({'ancho': float(pag.width), 'alto': float(pag.height), 'palabras': palabras, 'ocr': ocr})
    return out


def lineas(palabras, tolerancia=None):
    """Agrupa palabras en líneas (por altura). Devuelve [{'top','bottom','palabras'(ordenadas por x),'texto'}]."""
    if not palabras:
        return []
    alturas = sorted(w['bottom'] - w['top'] for w in palabras)
    h = alturas[len(alturas) // 2] or 6
    tol = tolerancia if tolerancia is not None else max(1.5, h * 0.45)
    ordenadas = sorted(palabras, key=lambda w: ((w['top'] + w['bottom']) / 2, w['x0']))
    grupos = []
    for w in ordenadas:
        c = (w['top'] + w['bottom']) / 2
        if grupos and abs(c - grupos[-1]['c']) <= tol:
            g = grupos[-1]
            g['palabras'].append(w)
            g['c'] = sum((p['top'] + p['bottom']) / 2 for p in g['palabras']) / len(g['palabras'])
        else:
            grupos.append({'c': c, 'palabras': [w]})
    out = []
    for g in grupos:
        ps = _unir_pegadas(sorted(g['palabras'], key=lambda w: w['x0']))
        out.append({'top': min(p['top'] for p in ps), 'bottom': max(p['bottom'] for p in ps), 'palabras': ps,
                    'texto': ' '.join(p['text'] for p in ps), 'altura': h})
    return out


_NUMERICO = re.compile(r'^[\d.,]+$')


def _unir_pegadas(ps):
    """Une trozos de número que el PDF dibuja pegados ('7' + '70,80' -> '770,80'): hueco casi nulo entre ambos."""
    out = []
    for w in ps:
        if out and _NUMERICO.match(out[-1]['text']) and _NUMERICO.match(w['text']) and w['x0'] - out[-1]['x1'] < 0.8:
            p = dict(out[-1])
            p['text'] += w['text']
            p['x1'] = w['x1']
            out[-1] = p
        else:
            out.append(w)
    return out


# ------------------------------------------------------------------------------------------- números
RE_NUM = re.compile(r'^-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?$|^-?\d+\.\d{1,4}$|^-?,\d+$')


def es_numero(t):
    return bool(RE_NUM.match(t.replace('€', '').strip()))


def numero(t):
    """'1.234,56' -> 1234.56 · '3,0500' -> 3.05 · '4' -> 4 · ',80' -> 0.8 · '12.5' -> 12.5 (punto decimal)."""
    s = t.replace('€', '').replace(' ', '').strip()
    if not s:
        return None
    neg = s.startswith('-')
    s = s.lstrip('-')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(?:\.\d{3})+', s):
        s = s.replace('.', '')
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def ocr_zona(ruta, indice, x0, top, x1, bottom, escala=4.0):
    """OCR de un recorte de página (en puntos). Se usa para recuperar texto que el OCR de página completa omitió."""
    import numpy as np
    import pypdfium2
    nombre, motor = _motor_ocr()
    pdf = pypdfium2.PdfDocument(ruta)
    try:
        img = pdf[indice].render(scale=escala).to_pil().convert('RGB')
    finally:
        pdf.close()
    caja = (max(0, int(x0 * escala)), max(0, int(top * escala)), int(x1 * escala), int(bottom * escala))
    rec = img.crop(caja)
    if nombre == 'rapidocr':
        res, _ = motor(np.array(rec))
        trozos = sorted(res or [], key=lambda r: (round(r[0][0][1] / 15), r[0][0][0]))
        return ' '.join(t for _, t, _ in trozos)
    import pytesseract
    return pytesseract.image_to_string(rec, lang='spa').replace('\n', ' ').strip()
