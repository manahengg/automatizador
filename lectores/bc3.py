"""Lector de BC3 (FIEBDC-3). Probado con un BC3 real exportado por m4PRO (708 conceptos).

Se queda en el nivel de capítulos y partidas (la descomposición interna de cada partida no se expande):
cantidad = factor * rendimiento de la relación ~D con su capítulo, precio = precio del concepto ~C.
"""
import collections
from ..modelo import Documento, Capitulo, Partida


def decodificar(datos):
    """m4PRO declara ANSI en la cabecera pero escribe UTF-8: se prueba UTF-8, luego cp1252."""
    for cod in ('utf-8', 'cp1252', 'latin-1'):
        try:
            return datos.decode(cod), cod
        except UnicodeDecodeError:
            continue


def reconoce(ruta):
    if not str(ruta).lower().endswith('.bc3'):
        return False
    with open(ruta, 'rb') as f:
        return f.read(200).lstrip().startswith(b'~V')


def leer(ruta):
    with open(ruta, 'rb') as _f:
        texto, cod = decodificar(_f.read())
    conceptos, hijos, textos = {}, collections.defaultdict(list), {}
    for reg in texto.replace('\r\n', '\n').split('~'):
        if not reg.strip():
            continue
        tipo, campos = reg[0], reg[1:].rstrip('\n').lstrip('|').split('|')
        if tipo == 'C':
            conceptos[campos[0].split('\\')[0]] = {'unidad': campos[1], 'resumen': campos[2],
                                                   'precio': float(campos[3] or 0)}
        elif tipo == 'D':
            partes = campos[1].split('\\')
            for i in range(0, len(partes) - 2, 3):
                if partes[i]:
                    hijos[campos[0]].append((partes[i], float(partes[i + 1] or 1), float(partes[i + 2] or 1)))
        elif tipo == 'T':
            textos[campos[0]] = campos[1]
    raices = [c for c in conceptos if c.endswith('##')]
    if not raices:
        raise ValueError('El BC3 no tiene concepto raíz (código acabado en ##)')
    raiz = raices[0]
    doc = Documento(tipo='presupuesto', origen=str(ruta), nombre=conceptos[raiz]['resumen'],
                    total_declarado=conceptos[raiz]['precio'])

    def nodo(codigo, factor, rend):
        c = conceptos[codigo]
        if codigo.endswith('#'):
            cap = Capitulo(titulo=c['resumen'], codigo=codigo)
            for h, f, r in hijos.get(codigo, []):
                if h in conceptos:
                    cap.hijos.append(nodo(h, f, r))
            return cap
        return Partida(descripcion=textos.get(codigo) or c['resumen'], cantidad=round(factor * rend, 3),
                       precio=c['precio'], unidad=c['unidad'] or 'ud', codigo=codigo)

    sueltas = []
    for h, f, r in hijos.get(raiz, []):
        if h not in conceptos:
            continue
        n = nodo(h, f, r)
        if isinstance(n, Capitulo):
            doc.capitulos.append(n)
        else:
            sueltas.append(n)
    if sueltas:
        doc.capitulos.append(Capitulo(titulo='SIN CAPÍTULO', hijos=sueltas))
    doc.avisar('info', 'Codificación detectada: %s. Se leen capítulos y partidas; la descomposición interna de cada '
                       'partida (mano de obra, materiales) no se expande.' % cod)
    doc.validar()
    return doc
