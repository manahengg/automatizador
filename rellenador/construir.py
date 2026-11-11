"""Genera Rellenar_precios.html: UN solo fichero con la página, el núcleo y las librerías dentro (funciona sin
internet; solo el OCR de PDF escaneados descarga Tesseract la primera vez).

    python rellenador/construir.py
"""
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(os.path.dirname(AQUI), 'Rellenar_precios.html')


def leer(*ruta):
    with open(os.path.join(AQUI, *ruta), encoding='utf-8') as f:
        return f.read()


def seguro(js):
    return js.replace('</script', '<\\/script')        # que el código no cierre la etiqueta <script> antes de tiempo


def main():
    html = leer('plantilla.html')
    for marca, js in (('/*PDFJS*/', leer('vendor', 'pdf.min.js')), ('/*JSZIP*/', leer('vendor', 'jszip.min.js')),
                      ('/*NUCLEO*/', leer('nucleo.js')), ('/*PDFWORKER*/', leer('vendor', 'pdf.worker.min.js'))):
        assert marca in html, marca
        html = html.replace(marca, seguro(js), 1)
    with open(SALIDA, 'w', encoding='utf-8') as f:
        f.write(html)
    print('Generado', SALIDA, '(%d KB)' % (os.path.getsize(SALIDA) // 1024))


if __name__ == '__main__':
    main()
