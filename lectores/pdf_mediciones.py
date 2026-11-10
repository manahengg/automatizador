"""Lector de mediciones de proyecto en PDF (sin precios)."""
import re
import pdfplumber
from ..modelo import Documento, Capitulo, Partida
from ..texto import reparar_mojibake

NUM = r"-?\d{1,3}(?:\.\d{3})*(?:,\d+)?"

def _n(s):
    return float(s.replace('.', '').replace(',', '.'))

def reconoce(ruta):
    try:
        with pdfplumber.open(ruta) as pdf:
            t = '\n'.join(reparar_mojibake(p.extract_text() or '') for p in pdf.pages[:2]).upper()
        return 'MEDICIONES' in t and 'CANTIDAD' in t and ('CÓDIGO' in t or 'CODIGO' in t)
    except Exception:
        return False

def leer(ruta):
    doc = Documento(tipo='obra', origen=str(ruta), nombre='Mediciones de proyecto')
    capitulos, cap = [], None
    codigo = unidad = None
    descripcion = []
    cantidad = None

    def guardar():
        nonlocal codigo, unidad, descripcion, cantidad, cap
        if codigo and descripcion and cantidad is not None:
            if cap is None:
                cap = Capitulo(titulo='SIN CAPÍTULO')
                capitulos.append(cap)
            cap.hijos.append(Partida(codigo=codigo, descripcion=' '.join(descripcion).strip(),
                unidad=unidad or 'ud', cantidad=cantidad, precio=None,
                notas=['Medición original del proyecto; pendiente de precio de proveedor']))
        codigo, unidad, descripcion, cantidad = None, None, [], None

    with pdfplumber.open(ruta) as pdf:
        for page in pdf.pages:
            for raw in reparar_mojibake(page.extract_text() or '').splitlines():
                line = ' '.join(raw.split()).strip()
                if not line: continue
                m = re.match(r'^(?:CAPÍTULO|CAPITULO)\s+([0-9.]+)\s+(.+)$', line, re.I)
                if m:
                    guardar(); cap = Capitulo(titulo=m.group(2).strip(), codigo=m.group(1)); capitulos.append(cap); continue
                m = re.match(r'^(?:SUBCAPÍTULO|SUBCAPITULO|APARTADO)\s+([0-9.]+)\s+(.+)$', line, re.I)
                if m:
                    guardar(); cap = Capitulo(titulo=m.group(2).strip(), codigo=m.group(1)); capitulos.append(cap); continue
                mcode = re.match(r'^(\d{2}(?:\.\d{2}){1,4})\s+([A-Za-zÁÉÍÓÚáéíóúñÑ²³]+)\s*(.*)$', line)
                if mcode:
                    guardar(); codigo, unidad = mcode.group(1), mcode.group(2)
                    if mcode.group(3).strip(): descripcion.append(mcode.group(3).strip())
                    continue
                if re.fullmatch(r'\d{2}(?:\.\d{2}){1,4}', line):
                    guardar(); codigo = line; continue
                if codigo and unidad is None and re.fullmatch(r'[A-Za-zÁÉÍÓÚáéíóúñÑ²³]+', line):
                    unidad = line; continue
                if codigo:
                    nums = re.findall(r'(?<![\w/])' + NUM + r'(?![\w/])', line)
                    # En el PDF de muestra la cantidad total aparece en una línea aislada
                    # después del detalle de cálculo. No usar los números de las fórmulas.
                    if len(nums) == 1 and line.strip() == nums[0]:
                        cantidad = _n(nums[0]); continue
                    if not re.match(r'^(?:[a-z]\*|\d+(?:[,.]\d+)?$)', line, re.I):
                        descripcion.append(line)
    guardar()
    doc.capitulos = [c for c in capitulos if c.hijos]
    if not doc.capitulos:
        raise ValueError('No se han extraído partidas del PDF de mediciones; comprueba que el PDF contiene texto seleccionable.')
    doc.avisar('info', 'Documento de mediciones sin precios: se utiliza como base de comparación.')
    doc.validar()
    return doc
