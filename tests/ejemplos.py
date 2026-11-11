"""Documentos de prueba INVENTADOS (sin datos de clientes ni proveedores reales) para las pruebas automáticas.

    presupuesto_cliente(ruta)        Excel "Orden · Designación · Cantidad · Precio" (como una petición de ofertas)
    oferta(ruta, n, escaneada=False) PDF de oferta de proveedor con columnas CÓDIGO/DESCRIPCIÓN/CANTIDAD/PRECIO/DTO/IMPORTE;
                                     escaneada=True la convierte en imagen (sin texto) para probar el OCR
Los documentos reales de las obras no se guardan en el repositorio (es público): ver .gitignore.
"""
import io
import os

CAPITULOS = {'01.01': 'CABLEADO', '01.02': 'ILUMINACION', '01.03': 'MECANISMOS'}

# código, unidad, designación, cantidad, precio cliente
PARTIDAS = [
    ('01.01.01', 'm', 'LÍNEA GENERAL RZ1-K (AS) 4x35+1x16 mm2. Línea de alimentación formada por conductores unipolares de '
                      'cobre RZ1-K (AS) 0,6/1 kV de 4x35+1x16 mm2, bajo tubo, totalmente instalada.', 27.5, 61.20),
    ('01.01.02', 'm', 'CABLE H07Z1-K (AS) 1x2,5 mm2. Conductor unipolar de cobre libre de halógenos, instalado.', 600, 1.10),
    ('01.01.03', 'm', 'CABLE H07Z1-K (AS) 1x1,5 mm2. Conductor unipolar de cobre libre de halógenos, instalado.', 450, 0.80),
    ('01.01.04', 'm', 'TUBO CORRUGADO D=20 mm LIBRE DE HALÓGENOS, empotrado, con guía.', 300, 0.95),
    ('01.02.01', 'ud', 'DOWNLIGHT LED EMPOTRABLE 20 W 4000K IP44 Ø200 mm, driver incluido, totalmente instalado.', 40, 48.00),
    ('01.02.02', 'ud', 'PANTALLA ESTANCA LED 36 W 4000K IP65 1200 mm, totalmente instalada.', 12, 39.50),
    ('01.02.03', 'ud', 'BLOQUE AUTÓNOMO DE EMERGENCIA 200 lm, 1 h de autonomía, totalmente instalado.', 15, 52.00),
    ('01.03.01', 'ud', 'INTERRUPTOR UNIPOLAR 10 A empotrado, con tecla y marco blanco, totalmente instalado.', 25, 14.00),
    ('01.03.02', 'ud', 'BASE ENCHUFE SCHUKO 16 A 2P+TT empotrada, con tapa y marco blanco, totalmente instalada.', 60, 13.50),
    ('01.03.03', 'ud', 'DETECTOR DE MOVIMIENTO 360º DE TECHO 1000 W, totalmente instalado.', 8, 55.00),
]
MATERIALES = len(PARTIDAS) + 1        # la línea 4x35+1x16 se desglosa en 1x35 y 1x16

# líneas de las ofertas: (código, descripción, cantidad, precio, dto)
OFERTA_1 = [   # cableado y mecanismos
    ('RZ1K135', 'CABLE RZ1-K (AS) 0,6/1KV 1X35 MM2 CU', 110, 4.85, 30),
    ('RZ1K116', 'CABLE RZ1-K (AS) 0,6/1KV 1X16 MM2 CU', 27.5, 2.30, 30),
    ('H07Z25', 'CABLE H07Z1-K (AS) 1X2,5 MM2 ROLLO 100M', 600, 0.62, 35),
    ('H07Z15', 'CABLE H07Z1-K (AS) 1X1,5 MM2 ROLLO 100M', 450, 0.41, 35),
    ('TC20LH', 'TUBO CORRUGADO LIBRE HALOGENOS D20 CON GUIA', 300, 0.52, 20),
    ('INT10A', 'INTERRUPTOR UNIPOLAR 10A BLANCO', 25, 4.10, 25),
    ('SCH16', 'BASE ENCHUFE SCHUKO 16A 2P+TT BLANCO', 60, 3.95, 25),
    ('PORTES', 'PORTES Y EMBALAJE', 1, 35.00, 0),
]
OFERTA_2 = [   # iluminación y detección
    ('DL20W', 'DOWNLIGHT LED EMPOTRABLE 20W 4000K IP44 D200', 40, 21.40, 15),
    ('EST36', 'PANTALLA ESTANCA LED 36W 4000K IP65 1200MM', 12, 18.90, 15),
    ('EME200', 'BLOQUE AUTONOMO EMERGENCIA 200 LM 1H', 15, 24.60, 15),
    ('DET360', 'DETECTOR MOVIMIENTO 360 TECHO 1000W', 8, 27.80, 15),
]
OFERTAS = {1: OFERTA_1, 2: OFERTA_2}


def presupuesto_cliente(ruta):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append([None, 'OBRA DE PRUEBA (datos inventados)'])
    ws.append([])
    ws.append(['Orden', 'Designación de las Partidas', 'Cantidad', 'Precio'])
    for cod, ud, desc, cant, precio in PARTIDAS:
        ws.append([cod, '%s %s' % (ud.capitalize(), desc), cant, precio])
    wb.save(ruta)
    return ruta


def oferta(ruta, n, escaneada=False):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    lineas = OFERTAS[n]
    destino = io.BytesIO() if escaneada else ruta
    c = canvas.Canvas(destino, pagesize=A4)
    alto = A4[1]
    c.setFont('Helvetica-Bold', 14)
    c.drawString(40, alto - 50, 'DISTRIBUCIONES ELECTRICAS DE PRUEBA S.L.')
    c.setFont('Helvetica', 9)
    c.drawString(40, alto - 66, 'OFERTA Nº P-%04d   Fecha: 10/11/2026   Validez: 30 dias' % (100 + n))
    xs = [30, 95, 345, 400, 465, 495]
    y = alto - 100
    c.setFont('Helvetica-Bold', 9)
    for x, t in zip(xs, ['CÓDIGO', 'DESCRIPCIÓN', 'CANTIDAD', 'PRECIO', 'DTO', 'IMPORTE']):
        c.drawString(x, y, t)
    c.setFont('Helvetica', 10)
    total = 0.0
    for cod, desc, cant, precio, dto in lineas:
        y -= 22
        imp = round(cant * precio * (1 - dto / 100.0), 2)
        total += imp
        f = lambda v, d=2: ('%.*f' % (d, v)).replace('.', ',')   # noqa: E731
        c.drawString(xs[0], y, cod)
        c.drawString(xs[1], y, desc[:48])
        c.drawRightString(xs[2] + 40, y, f(cant))
        c.drawRightString(xs[3] + 45, y, f(precio, 3))
        c.drawRightString(xs[4] + 25, y, f(dto) if dto else '')
        c.drawRightString(xs[5] + 50, y, f(imp))
    y -= 30
    c.setFont('Helvetica-Bold', 10)
    c.drawString(xs[2], y, 'BASE IMPONIBLE')
    c.drawRightString(xs[5] + 50, y, ('%.2f' % total).replace('.', ','))
    c.save()
    if escaneada:
        import pypdfium2
        pdf = pypdfium2.PdfDocument(destino.getvalue())
        img = pdf[0].render(scale=3.5).to_pil().convert('RGB')
        pdf.close()
        img.save(ruta, 'PDF', resolution=250.0)
    return ruta


def generar(carpeta):
    os.makedirs(carpeta, exist_ok=True)
    return {'cliente': presupuesto_cliente(os.path.join(carpeta, 'presupuesto_cliente_prueba.xlsx')),
            'oferta1': oferta(os.path.join(carpeta, 'oferta_prueba_1.pdf'), 1),
            'oferta2': oferta(os.path.join(carpeta, 'oferta_prueba_2.pdf'), 2),
            'escaneada': oferta(os.path.join(carpeta, 'oferta_prueba_escaneada.pdf'), 2, escaneada=True)}


if __name__ == '__main__':
    import sys
    print(generar(sys.argv[1] if len(sys.argv) > 1 else 'ejemplos_prueba'))
