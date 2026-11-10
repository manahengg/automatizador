"""Estilo común de los Excel: paleta, formatos de celda y piezas reutilizables (banner, tarjetas, impresión).

Todos los libros se escriben con xlsxwriter (formatos, formato condicional, gráficos y validación de datos
que openpyxl no ofrece con esta calidad). Los números se escriben como NÚMEROS (no texto) con su formato de
celda, y los totales como fórmulas con su valor ya calculado, para que se vean igual en cualquier visor.
"""
import math

import xlsxwriter  # noqa: F401  (se importa aquí para fallar pronto y con un mensaje claro si falta)

NAVY, AZUL, CLARO, GRIS, BORDE, TXT = '#17324D', '#2F6690', '#EAF1F8', '#F4F5F7', '#D0D5DD', '#1D2939'
VERDE_BG, VERDE_TX, VERDE = '#D1FADF', '#05603A', '#12B76A'
AMBAR_BG, AMBAR_TX, AMBAR = '#FEF0C7', '#93370D', '#F79009'
ROJO_BG, ROJO_TX, ROJO = '#FEE4E2', '#B42318', '#F04438'
AZUL_BG, AZUL_TX = '#D1E9FF', '#175CD3'

EUR = '#,##0.00 "€"'
NUM = '#,##0.00'
PCT = '0.0%'
DPCT = '+0.0%;-0.0%;0.0%'
DEUR = '+#,##0.00 "€";-#,##0.00 "€";0.00 "€"'


class Estilos:
    """Fábrica de formatos con caché: E(bold=True, bg_color=...) devuelve siempre el mismo objeto para las mismas propiedades."""

    def __init__(self, wb):
        self.wb, self._c = wb, {}

    def __call__(self, **kw):
        k = tuple(sorted(kw.items()))
        if k not in self._c:
            base = {'font_name': 'Calibri', 'font_size': 10, 'font_color': TXT, 'valign': 'vcenter'}
            base.update(kw)
            self._c[k] = self.wb.add_format(base)
        return self._c[k]

    # formatos habituales
    def cab(self, **kw):
        base = dict(bold=True, font_color='#FFFFFF', bg_color=AZUL, text_wrap=True, align='center', border=1,
                    border_color=BORDE)
        base.update(kw)
        return self(**base)

    def celda(self, **kw):
        base = {'border': 1, 'border_color': BORDE}
        base.update(kw)
        return self(**base)


def nuevo_libro(ruta):
    wb = xlsxwriter.Workbook(ruta, {'strings_to_numbers': False, 'strings_to_formulas': False,
                                    'strings_to_urls': False})
    wb.set_properties({'author': 'Automatizador de ofertas', 'comments': 'Generado automáticamente'})
    return wb, Estilos(wb)


def _m(ws, r1, c1, r2, c2, valor, fmt):
    if (r1, c1) == (r2, c2):
        ws.write(r1, c1, valor, fmt)
    else:
        ws.merge_range(r1, c1, r2, c2, valor, fmt)


def banner(ws, E, titulo, subtitulo, ncols):
    ws.hide_gridlines(2)
    ws.set_row(0, 36)
    ws.set_row(1, 20)
    _m(ws, 0, 0, 0, ncols - 1, titulo, E(bold=True, font_size=18, font_color='#FFFFFF', bg_color=NAVY, indent=1))
    _m(ws, 1, 0, 1, ncols - 1, subtitulo, E(italic=True, font_color='#C9D6E4', bg_color=NAVY, indent=1))


def tarjeta(ws, E, fila, col, etiqueta, valor, fmt_num=None, ancho=2, color=AZUL, nota=''):
    """Tarjeta KPI de 3 filas: etiqueta pequeña, valor grande, nota. Ocupa `ancho` columnas."""
    c2 = col + ancho - 1
    borde = {'top': 5, 'top_color': color}
    _m(ws, fila, col, fila, c2, etiqueta, E(font_size=9, bold=True, font_color='#667085', bg_color=CLARO, indent=1, **borde))
    kw = {'num_format': fmt_num} if fmt_num else {}
    _m(ws, fila + 1, col, fila + 1, c2, valor, E(font_size=18, bold=True, font_color=color if color != AMBAR else AMBAR_TX,
                                                bg_color=CLARO, indent=1, align='left', **kw))
    _m(ws, fila + 2, col, fila + 2, c2, nota, E(font_size=9, font_color='#667085', bg_color=CLARO, indent=1))
    ws.set_row(fila + 1, 30)


def seccion(ws, E, fila, texto, ncols, color=AZUL):
    ws.set_row(fila, 22)
    _m(ws, fila, 0, fila, ncols - 1, texto, E(bold=True, font_size=12, font_color=color, bottom=2, bottom_color=color))


def caja(ws, E, fila, ncols, texto, tipo='info', chars_por_linea=150):
    """Párrafo en un recuadro de color que ocupa todo el ancho (ajusta el alto al texto)."""
    bg, tx, bd = {'info': (CLARO, TXT, AZUL), 'aviso': (AMBAR_BG, AMBAR_TX, AMBAR),
                  'error': (ROJO_BG, ROJO_TX, ROJO), 'ok': (VERDE_BG, VERDE_TX, VERDE)}[tipo]
    lineas = max(1, math.ceil(len(texto) / float(chars_por_linea)))
    ws.set_row(fila, 15 * lineas + 5)
    _m(ws, fila, 0, fila, ncols - 1, texto, E(text_wrap=True, valign='top', font_color=tx, bg_color=bg, left=5,
                                              left_color=bd, indent=1))


def imprimir(ws, repetir=None, horizontal=True, una_pagina=False):
    if horizontal:
        ws.set_landscape()
    ws.set_paper(9)                       # A4
    ws.fit_to_pages(1, 1 if una_pagina else 0)   # todo el ancho en una página; el alto, las que hagan falta
    ws.set_margins(0.4, 0.4, 0.6, 0.6)
    ws.set_footer('&L&8&F — &A&C&8Página &P de &N&R&8&D')
    if repetir is not None:
        ws.repeat_rows(*repetir)


def corto(s, n):
    s = ' '.join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + '…'
