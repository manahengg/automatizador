"""Hoja de revisión en Excel: es lo que mira una persona antes de importar o de comparar.

Hoja "Resumen": datos del documento, totales y avisos (con color según gravedad).
Hoja "Líneas": una fila por partida; en amarillo lo que requiere atención.
"""
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment

ROJO = PatternFill('solid', fgColor='F8CBAD')
AMARILLO = PatternFill('solid', fgColor='FFF2CC')
VERDE = PatternFill('solid', fgColor='E2EFDA')


def escribir(doc, ruta):
    wb = openpyxl.Workbook()
    rs = wb.active
    rs.title = 'Resumen'
    filas = [
        ('Documento', doc.nombre or doc.origen), ('Tipo', doc.tipo), ('Proveedor', doc.proveedor),
        ('Referencia', doc.referencia), ('Fecha', doc.fecha), ('Validez de la oferta', doc.validez),
        ('Forma de pago', doc.condiciones.get('forma_pago')), ('Portes', doc.condiciones.get('portes')),
        ('Plazo de entrega', doc.condiciones.get('plazo_entrega')),
        ('Total calculado (precios a 2 decimales, como m4PRO)', doc.importe),
        ('Total que declara el documento', doc.total_declarado),
        ('Diferencia', None if doc.total_declarado is None else round(doc.importe - doc.total_declarado, 2)),
        ('Líneas', sum(1 for _ in doc.partidas())),
    ]
    for k, v in filas:
        if v not in (None, ''):
            rs.append([k, v])
    for c in rs['A']:
        c.font = Font(bold=True)
    rs.append([])
    rs.append(['AVISOS'])
    rs.cell(rs.max_row, 1).font = Font(bold=True)
    orden = {'revisar': 0, 'aviso': 1, 'info': 2}
    for a in sorted(doc.avisos, key=lambda a: orden[a.nivel]):
        rs.append([{'revisar': 'REVISAR', 'aviso': 'Aviso', 'info': 'Info'}[a.nivel], a.texto])
        fila = rs[rs.max_row]
        fila[0].fill = fila[1].fill = {'revisar': ROJO, 'aviso': AMARILLO, 'info': VERDE}[a.nivel]
        fila[1].alignment = Alignment(wrap_text=True, vertical='top')
    rs.column_dimensions['A'].width = 52
    rs.column_dimensions['B'].width = 110

    ws = wb.create_sheet('Líneas')
    ws.append(['Capítulo', 'Código', 'Descripción', 'Ud', 'Cantidad', 'Precio lista', 'Dto %', 'Precio neto',
               'Importe (m4PRO)', 'Importe exacto', 'Importe impreso', 'Aviso'])
    for c in ws[1]:
        c.font = Font(bold=True)

    def recorrer(caps, ruta_titulos):
        for cap in caps:
            ruta = ruta_titulos + [cap.titulo] if cap.titulo else ruta_titulos
            for h in cap.hijos:
                if hasattr(h, 'hijos'):
                    recorrer([h], ruta)
                else:
                    aviso = None
                    if h.precio is None:
                        aviso = 'Sin precio en el documento'
                    elif h.importe_declarado is not None and abs(h.importe - h.importe_declarado) > 0.005:
                        aviso = 'Redondeo a 2 decimales: %+.2f €' % (h.importe - h.importe_declarado)
                    if h.notas:
                        aviso = ((aviso + '; ') if aviso else '') + '; '.join(h.notas)
                    ws.append([' / '.join(ruta), h.codigo, h.descripcion, h.unidad, h.cantidad, h.precio_lista,
                               h.dto_pct, None if h.precio is None else round(h.precio, 4), h.importe,
                               h.importe_exacto, h.importe_declarado, aviso])
                    if aviso:
                        for c in ws[ws.max_row]:
                            c.fill = AMARILLO
    recorrer(doc.capitulos, [])
    for col, ancho in zip('ABCDEFGHIJKL', (34, 12, 70, 6, 10, 12, 8, 12, 14, 14, 14, 50)):
        ws.column_dimensions[col].width = ancho
    ws.freeze_panes = 'A2'
    wb.save(ruta)
