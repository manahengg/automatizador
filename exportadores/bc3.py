"""Exportador a BC3 (FIEBDC-3) con el mismo estilo que el que escribe m4PRO.

VALIDADO: el BC3 generado desde la certificación de Cintra se importó en la base PRUEBA de m4PRO con los
importes, cantidades, tildes y textos correctos. Hay un test de regresión que exige que este exportador
reproduzca ese fichero byte a byte (tests/test_real.py).

Estructura: raíz P01## -> capítulos C01# -> subcapítulos C0101# -> partidas (código "<nº capítulo>.<código origen>").
La cantidad de cada partida va como rendimiento en ~D y como medición en ~M. El texto largo va en ~T.
"""
import datetime
from ..modelo import Capitulo, r2


def limpia(s):
    """Los separadores del formato no pueden aparecer dentro de un texto."""
    return str(s).replace('|', '/').replace('~', '-').replace('\\', '/').replace('\r', ' ').replace('\n', ' ').strip()


def num(v, dec=2):
    return ('%.' + str(dec) + 'f') % v


def _texto_partida(p):
    t = limpia(p.descripcion)
    if p.precio is None:
        t += ' [SIN PRECIO EN LA OFERTA: cantidad incluida en otra partida o pendiente de confirmar]'
    elif p.precio_lista is not None and p.dto_pct is not None:
        t += ' [Precio lista %.2f, dto %.2f %%]' % (p.precio_lista, p.dto_pct)
    return t


def _clave(p):
    return (limpia(p.unidad) or 'ud', limpia(p.descripcion)[:50].strip(),
            r2(p.precio) if p.precio is not None else 0.0, _texto_partida(p))


def _capitulo(cap, cod, ci, ruta_pos, cuerpo, fecha, reg):
    hijos, items, total = [], [], 0.0
    for pos, h in enumerate(cap.hijos, 1):
        if isinstance(h, Capitulo):
            cod_sub = cod[:-1] + '%02d#' % pos
            t_sub, items_sub = _capitulo(h, cod_sub, ci, ruta_pos + [pos], cuerpo, fecha, reg)
            hijos.append((cod_sub, 1.0))
            total += t_sub
            items.extend(items_sub)
        else:
            base, k, clave = '%02d.%s' % (ci, h.codigo or '%03d' % pos), 2, _clave(h)
            cod_p = base
            while cod_p in reg and reg[cod_p] != clave:      # mismo código con otro precio/texto: se desambigua
                cod_p, k = '%s_%d' % (base, k), k + 1
            nuevo = cod_p not in reg                         # un concepto repetido se define una sola vez
            reg[cod_p] = clave
            hijos.append((cod_p, h.cantidad))
            total += h.importe
            items.append((cod_p, h, '%02d' % ci + ''.join('\\%03d' % x for x in ruta_pos + [pos]), nuevo))
    total = round(total, 2)
    cuerpo.append('~C|%s||%s|%s|%s|0|' % (cod, limpia(cap.titulo), num(total), fecha))
    cuerpo.append('~D|%s|%s|' % (cod, ''.join('%s\\1\\%s\\' % (c, num(q, 3)) for c, q in hijos)))
    return total, items


def generar(doc, nombre=None, fecha=None, propietario='TRITON ENERGIA S.L.'):
    """Devuelve (texto del BC3, total). El texto usa saltos CRLF como el BC3 real de m4PRO."""
    fecha = fecha or datetime.date.today().strftime('%d%m%y')
    nombre = nombre or doc.nombre or 'Presupuesto importado'
    cabecera = ['~V|%s\\%s|FIEBDC 3.0/95|m4PRO ERP - Ver. 6.0.16 - https://solinat.com||ANSI|' % (propietario, fecha),
                '~K|2\\2\\3\\3\\2\\2\\2\\2|0|']
    cuerpo, raiz_hijos, total_raiz, reg = [], [], 0.0, {}
    for ci, cap in enumerate(doc.capitulos, 1):
        cod_cap = 'C%02d#' % ci
        total_cap, items = _capitulo(cap, cod_cap, ci, [], cuerpo, fecha, reg)
        for cod, p, ruta, nuevo in items:
            if nuevo:
                cuerpo.append('~C|%s|%s|%s|%s|%s|0|' % (cod, limpia(p.unidad) or 'ud', limpia(p.descripcion)[:50].strip(),
                                                        num(r2(p.precio)) if p.precio is not None else num(0), fecha))
                cuerpo.append('~T|%s|%s|' % (cod, _texto_partida(p)))
            cuerpo.append('~M|%s|%s|%s|\\\\%s\\0.00\\0.00\\0.00\\|' % (cod, ruta, num(p.cantidad, 3), num(p.cantidad)))
        raiz_hijos.append(cod_cap)
        total_raiz += total_cap
    total_raiz = round(total_raiz, 2)
    cabecera.append('~C|P01##||%s|%s|%s|0|' % (limpia(nombre), num(total_raiz), fecha))
    cabecera.append('~D|P01##|%s|' % ''.join('%s\\1\\1\\' % c for c in raiz_hijos))
    return '\r\n'.join(cabecera + cuerpo) + '\r\n', total_raiz


def escribir(doc, ruta, **kw):
    """Escribe el BC3 en Windows-1252 (la codificación que declara su cabecera). Devuelve el total."""
    texto, total = generar(doc, **kw)
    with open(ruta, 'wb') as f:
        f.write(texto.encode('cp1252', errors='replace'))
    return total
