"""Normalización conservadora de texto extraído de PDF/Excel.

Repara mojibake UTF-8/Latin-1 habitual sin alterar texto correcto. No sustituye OCR:
si el PDF contiene glifos mal codificados en su fuente, el lector debe recurrir a OCR.
"""
from __future__ import annotations
import re
import unicodedata

_MOJIBAKE = ("Ã", "Â", "â€", "ðŸ", "ï¿½", " ")


def reparar_mojibake(valor):
    if valor is None:
        return valor
    s = str(valor)
    # Hasta dos pasadas: algunos PDF han sufrido doble conversión.
    for _ in range(2):
        if not any(m in s for m in _MOJIBAKE):
            break
        try:
            candidato = s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                candidato = s.encode("cp1252").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                break
        # Solo aceptar si reduce las señales de corrupción.
        antes = sum(s.count(x) for x in _MOJIBAKE)
        despues = sum(candidato.count(x) for x in _MOJIBAKE)
        if despues >= antes:
            break
        s = candidato
    s = s.replace("\ufffd", " ")
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[\t\r\f]+", " ", s)
    s = re.sub(r" {2,}", " ", s)
    return s.strip()


def normalizar_busqueda(valor):
    s = reparar_mojibake(valor) or ""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("0,6/1 kv", "06 1kv").replace("0,6/1kv", "06 1kv")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()
