"""Petición de oferta para proveedores: las partidas del cliente (de los capítulos elegidos) SIN precios.

Una fila por material a comprar (la cantidad real interpretada: 4x35 x 27,5 m -> 110 m de 1x35), con la descripción
completa de la partida, y celdas amarillas para que el proveedor ponga marca/modelo, su referencia, precio y descuento.
La columna "Código" identifica cada material: cuando el proveedor devuelve este Excel relleno y se sube como oferta, la
app lo casa directamente por ese código (lectores/excel_peticion.py), sin depender de leer un PDF.
No lleva el nombre del cliente (no se le enseña al proveedor) ni el logo.
"""
import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, Protection
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation

MARCA = 'automatizador-peticion v1'
FUENTE = 'Arial'
F_TIT = Font(name=FUENTE, size=14, bold=True, color='1F4E78')
F_N = Font(name=FUENTE, size=9)
F_B = Font(name=FUENTE, size=9, bold=True)
F_CAB = Font(name=FUENTE, size=9, bold=True, color='FFFFFF')
F_GRIS = Font(name=FUENTE, size=9, italic=True, color='595959')
F_CAP = Font(name=FUENTE, size=10, bold=True, color='1F4E78')
R_CAB = PatternFill('solid', fgColor='1F4E78')
R_CAP = PatternFill('solid', fgColor='DDEBF7')
R_SUB = PatternFill('solid', fgColor='F2F2F2')
R_TOT = PatternFill('solid', fgColor='BDD7EE')
R_IN = PatternFill('solid', fgColor='FFF2CC')
FINO = Side(style='thin', color='BFBFBF')
BORDE = Border(left=FINO, right=FINO, top=FINO, bottom=FINO)
EUR = '#,##0.00 €;-#,##0.00 €;""'
EUR4 = '#,##0.0000 €;-#,##0.0000 €;""'
CANT = '#,##0.##'
ARRIBA = Alignment(vertical='top', wrap_text=True)

COLUMNAS = [('Nº', 6), ('Código', 13), ('Ud', 5), ('Descripción de la partida', 58), ('Material a ofertar', 34),
            ('Cantidad', 10), ('Marca / modelo ofertado', 24), ('Ref. proveedor', 14), ('Precio unitario', 12),
            ('Dto. %', 7), ('Precio neto', 12), ('Importe', 13), ('Observaciones', 30)]
C_COD, C_CANT, C_MARCA, C_REF, C_PRECIO, C_DTO, C_NETO, C_IMP, C_OBS = 2, 6, 7, 8, 9, 10, 11, 12, 13
F_CABECERA = 8


def escribir(materiales, ruta, obra='', cod_obra='', capitulos_txt='', clave=None):
    """materiales: emparejar.Material (ya filtrados por capítulos). clave(m) -> código único del material."""
    from ..obra import clave_mat
    clave = clave or clave_mat
    wb = Workbook()
    ws = wb.active
    ws.title = 'Petición de oferta'
    ws['A1'] = 'PETICIÓN DE OFERTA'
    ws['A1'].font = F_TIT
    datos = [('Obra', obra), ('Código de obra', cod_obra), ('Fecha', datetime.date.today().strftime('%d/%m/%Y')),
             ('Capítulos', capitulos_txt)]
    for k, (t, v) in enumerate(datos, 2):
        ws.cell(k, 1, t + ':').font = F_B
        ws.merge_cells(start_row=k, start_column=1, end_row=k, end_column=2)
        ws.cell(k, 3, v).font = F_N
        ws.merge_cells(start_row=k, start_column=3, end_row=k, end_column=5)
    for k, t in enumerate(['Empresa ofertante', 'Persona de contacto', 'Validez de la oferta', 'Plazo de entrega'], 2):
        ws.cell(k, 7, t + ':').font = F_B
        c = ws.cell(k, 8)
        c.fill, c.border, c.protection = R_IN, BORDE, Protection(locked=False)
        ws.merge_cells(start_row=k, start_column=8, end_row=k, end_column=10)
    ws.cell(6, 1, 'Rellenen las celdas AMARILLAS: marca/modelo, su referencia, precio unitario y, si lo hay, descuento '
                  '(el precio neto y el importe se calculan solos). Si ofertan otra cantidad o un artículo equivalente, '
                  'indíquenlo en Observaciones. Por favor, no cambien la columna "Código": permite importar su oferta.'
            ).font = F_GRIS
    ws.merge_cells(start_row=6, start_column=1, end_row=6, end_column=len(COLUMNAS))
    ws.row_dimensions[6].height = 26
    ws.cell(6, 1).alignment = ARRIBA
    for i, (t, a) in enumerate(COLUMNAS, 1):
        c = ws.cell(F_CABECERA, i, t)
        c.font, c.fill, c.border = F_CAB, R_CAB, BORDE
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[L(i)].width = a
    ws.row_dimensions[F_CABECERA].height = 28

    dv = DataValidation(type='decimal', operator='greaterThanOrEqual', formula1='0', allow_blank=True,
                        showErrorMessage=True, errorTitle='Precio', error='Escriba un número (sin el símbolo €).')
    dv_dto = DataValidation(type='decimal', operator='between', formula1='0', formula2='100', allow_blank=True,
                            showErrorMessage=True, errorTitle='Descuento', error='Descuento en % (de 0 a 100).')
    ws.add_data_validation(dv)
    ws.add_data_validation(dv_dto)

    r = F_CABECERA + 1
    subtotales = []
    cap_actual, ini = None, r
    por_partida = {}
    for m in materiales:
        por_partida.setdefault(m.n, []).append(m)

    def cerrar(fin):
        nonlocal r
        if cap_actual is None or fin < ini:
            return
        ws.cell(r, 4, 'Total %s' % cap_actual).font = F_B
        c = ws.cell(r, C_IMP, '=SUBTOTAL(9,%s%d:%s%d)' % (L(C_IMP), ini, L(C_IMP), fin))
        c.font, c.number_format = F_B, EUR
        for i in range(1, len(COLUMNAS) + 1):
            ws.cell(r, i).fill, ws.cell(r, i).border = R_SUB, BORDE
        subtotales.append(r)
        r += 1

    vistos = set()
    for m in materiales:
        if m.n in vistos:
            continue
        vistos.add(m.n)
        cod_cap = ((m.ruta_codigos[-1] if m.ruta_codigos else '') or '').rstrip('#')
        tit_cap = m.ruta[-1] if m.ruta else 'SIN CAPÍTULO'
        cap = tit_cap if not cod_cap or tit_cap.startswith(cod_cap) else '%s  %s' % (cod_cap, tit_cap)
        if cap != cap_actual:
            cerrar(r - 1)
            cap_actual = cap
            c = ws.cell(r, 1, cap)
            c.font = F_CAP
            for i in range(1, len(COLUMNAS) + 1):
                ws.cell(r, i).fill = R_CAP
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(COLUMNAS))
            r += 1
            ini = r
        grupo = por_partida[m.n]
        p = m.partida
        f0 = r
        for k, mm in enumerate(grupo):
            ws.cell(r, 1, '%d%s' % (mm.n, mm.id[len(str(mm.n)):]))
            ws.cell(r, C_COD, clave(mm))
            ws.cell(r, 3, mm.unidad or p.unidad)
            if k == 0:
                titulo = (p.resumen or '').strip()
                desc = (p.descripcion or '').strip()
                ws.cell(r, 4, (titulo + '\n' + desc if titulo and titulo not in desc[:len(titulo) + 5] else desc)[:1200])
            ws.cell(r, 5, mm.descripcion + (' (%s)' % mm.nota if mm.nota else ''))
            ws.cell(r, C_CANT, mm.cantidad)
            ws.cell(r, C_NETO, '=IF({p}{r}="","",{p}{r}*(1-N({d}{r})/100))'.format(p=L(C_PRECIO), d=L(C_DTO), r=r))
            ws.cell(r, C_IMP, '=IF({n}{r}="","",{n}{r}*{c}{r})'.format(n=L(C_NETO), c=L(C_CANT), r=r))
            for i in range(1, len(COLUMNAS) + 1):
                c = ws.cell(r, i)
                c.font, c.border, c.alignment = F_N, BORDE, ARRIBA
            for i in (C_MARCA, C_REF, C_PRECIO, C_DTO, C_OBS):
                ws.cell(r, i).fill = R_IN
                ws.cell(r, i).protection = Protection(locked=False)
            ws.cell(r, C_CANT).number_format = CANT
            ws.cell(r, C_PRECIO).number_format = EUR4
            ws.cell(r, C_NETO).number_format = EUR4
            ws.cell(r, C_IMP).number_format = EUR
            dv.add('%s%d' % (L(C_PRECIO), r))
            dv_dto.add('%s%d' % (L(C_DTO), r))
            r += 1
        if r - 1 > f0:
            ws.merge_cells(start_row=f0, start_column=4, end_row=r - 1, end_column=4)
        # alto de fila para que se lea la descripción entera (≈ 72 caracteres por línea en la columna D)
        texto = ws.cell(f0, 4).value or ''
        lineas = sum(max(1, -(-len(t) // 72)) for t in texto.split('\n'))
        alto = min(400, 12 * lineas + 4)
        filas = r - f0
        for k in range(f0, r):
            ws.row_dimensions[k].height = max(24, alto / filas)
    cerrar(r - 1)
    ws.cell(r, 4, 'TOTAL OFERTA').font = F_B
    c = ws.cell(r, C_IMP, '=SUBTOTAL(9,%s%d:%s%d)' % (L(C_IMP), F_CABECERA + 1, L(C_IMP), r - 1))
    c.font, c.number_format = F_B, EUR
    for i in range(1, len(COLUMNAS) + 1):
        ws.cell(r, i).fill, ws.cell(r, i).border = R_TOT, BORDE
    ws.freeze_panes = 'E%d' % (F_CABECERA + 1)
    ws.auto_filter.ref = 'A%d:%s%d' % (F_CABECERA, L(len(COLUMNAS)), r - 1)
    ws.print_title_rows = '%d:%d' % (F_CABECERA, F_CABECERA)
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.center.text = 'Página &P de &N'
    # marca para reconocer el fichero al importarlo de vuelta
    d = wb.create_sheet('_datos')
    d['A1'], d['A2'], d['A3'] = MARCA, obra, cod_obra
    d.sheet_state = 'hidden'
    wb.save(ruta)
    return ruta
