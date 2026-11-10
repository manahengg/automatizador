"""Decide qué lector sirve para un fichero. El orden importa: de lo más específico a lo más genérico."""
import os
from .lectores import (bc3, pdf_mediciones, pdf_electrofil, pdf_electromercantil, pdf_sonepar, excel_erp, excel_obra, excel_generico)

# Para añadir un proveedor nuevo en PDF: crear su lector en lectores/ y añadirlo aquí (antes de los genéricos).
LECTORES = [bc3, pdf_mediciones, pdf_electrofil, pdf_electromercantil, pdf_sonepar, excel_erp, excel_obra, excel_generico]

EXTENSIONES = {'.pdf', '.xlsx', '.xlsm', '.bc3'}


def detectar(ruta):
    """Devuelve (lector, motivo). Si no hay lector, lector es None y motivo explica por qué."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext not in EXTENSIONES:
        return None, 'Extensión %s no admitida (se aceptan: %s).' % (ext or '(ninguna)', ', '.join(sorted(EXTENSIONES)))
    
    # NUEVO: Detección directa por nombre de archivo para evitar falsos rechazos en PDFs conocidos
    nombre_archivo = os.path.basename(ruta).upper()
    if 'SONEPAR' in nombre_archivo:
        return pdf_sonepar, 'Reconocido como pdf_sonepar (por nombre de archivo)'
    if 'OFE_' in nombre_archivo:
        return pdf_electrofil, 'Reconocido como pdf_electrofil (por nombre de archivo)'
    if 'MEDICIONE' in nombre_archivo:
        return pdf_mediciones, 'Reconocido como pdf_mediciones (por nombre de archivo)'

    for lector in LECTORES:
        try:
            if lector.reconoce(ruta):
                return lector, 'Reconocido como %s' % lector.__name__.split('.')[-1]
        except Exception:
            continue
            
    if ext == '.pdf':
        return None, ('PDF con una maqueta que no conozco todavía (¿proveedor nuevo?). '
                     'Hay que añadir un lector para esa maqueta; mientras tanto, pedir la oferta en Excel o BC3.')
    if ext == '.bc3':
        return None, 'BC3 sin cabecera ~V o ilegible.'
    return None, 'Excel sin cabecera reconocible (hacen falta al menos columnas de descripción, cantidad y precio).'