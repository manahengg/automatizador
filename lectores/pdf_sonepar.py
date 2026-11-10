"""Lector OCR estructurado para presupuestos Sonepar."""

import os
import re
import collections

import pdfplumber

from ..modelo import Documento, Capitulo, Partida
from ..texto import reparar_mojibake


# Formato europeo: 1.234,56 / 1234,56 / 1,5922
PATRON_NUMERO = re.compile(
    r"(?<![\w/])(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2,4}(?!\d)"
)

PATRON_FILA = re.compile(
    r"^\s*(\d{1,4})\s+(.+?)\s*$"
)

LINEAS_IGNORAR = (
    "SUMA Y SIGUE",
    "VENDEDOR:",
    "FECHA VALIDEZ:",
    "SONEPAR SPAIN",
    "INSCRITA EN EL REGISTRO",
    "PRESUPUESTO",
    "ARTICULO DESCRIPCION",
    "ITEM ARTICULO",
    "PAG.:",
    "PAG.:",
)


def _configurar_tesseract():
    import pytesseract

    cmd = os.environ.get("TESSERACT_CMD")

    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd

    return pytesseract


def _num(s):
    s = str(s).replace("€", "").replace(" ", "").strip()

    if not re.fullmatch(
        r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2,4}",
        s
    ):
        return None

    return float(s.replace(".", "").replace(",", "."))


def _lineas_ocr_detalle(ruta):
    """
    Extrae líneas OCR conservando la posición horizontal de cada palabra.
    Agrupa por línea real de Tesseract, no solamente por proximidad vertical.
    """

    from pytesseract import Output

    pytesseract = _configurar_tesseract()

    resultado = []

    with pdfplumber.open(ruta) as pdf:

        total = len(pdf.pages)

        for numero_pagina, page in enumerate(pdf.pages, 1):

            print(
                f"[SONEPAR OCR] Procesando página "
                f"{numero_pagina}/{total}",
                flush=True
            )

            imagen = page.to_image(
                resolution=300
            ).original.convert("RGB")

            datos = pytesseract.image_to_data(
                imagen,
                lang="spa+eng",
                output_type=Output.DICT,
                config="--psm 6"
            )

            grupos = collections.defaultdict(list)

            for i, palabra in enumerate(datos["text"]):

                palabra = palabra.strip()

                if not palabra:
                    continue

                try:
                    confianza = float(datos["conf"][i])
                except (ValueError, TypeError):
                    confianza = 0

                if confianza < 20:
                    continue

                clave = (
                    datos["block_num"][i],
                    datos["par_num"][i],
                    datos["line_num"][i]
                )

                grupos[clave].append({
                    "x": int(datos["left"][i]),
                    "texto": palabra,
                    "confianza": confianza
                })

            lineas_pagina = []

            for palabras in grupos.values():

                palabras.sort(key=lambda p: p["x"])

                texto = " ".join(
                    p["texto"] for p in palabras
                )

                lineas_pagina.append({
                    "pagina": numero_pagina,
                    "texto": texto,
                    "palabras": palabras
                })

            # Orden vertical y horizontal de las líneas.
            lineas_pagina.sort(
                key=lambda l: (
                    min(
                        int(datos["top"][i])
                        for i in range(len(datos["text"]))
                        if datos["text"][i].strip()
                        and datos["block_num"][i] == l["palabras"][0].get("block", -999)
                    ) if False else l["palabras"][0]["x"]
                )
            ) if False else None

            # Se conserva el orden de aparición de los grupos de Tesseract.
            for linea in lineas_pagina:
                resultado.append(linea)

    return resultado


def _lineas_ocr(ruta):
    """Compatibilidad con pruebas y módulos anteriores."""
    return [
        linea["texto"]
        for linea in _lineas_ocr_detalle(ruta)
    ]


def reconoce(ruta):
    """
    Reconoce Sonepar mediante texto digital u OCR.
    """

    try:
        pytesseract = _configurar_tesseract()

        with pdfplumber.open(ruta) as pdf:

            if not pdf.pages:
                return False

            texto = (
                reparar_mojibake(pdf.pages[0].extract_text() or "")
            ).upper()

            if "SONEPAR" in texto and "PRESUPUESTO" in texto:
                return True

            imagen = pdf.pages[0].to_image(
                resolution=250
            ).original.convert("RGB")

            texto_ocr = pytesseract.image_to_string(
                imagen,
                lang="spa+eng",
                config="--psm 6"
            ).upper()

            return (
                "SONEPAR" in texto_ocr
                and "PRESUPUESTO" in texto_ocr
            )

    except Exception as e:
        print(
            "[SONEPAR] Error de reconocimiento:",
            str(e),
            flush=True
        )
        return False


def _limpiar_descripcion(texto):
    texto = re.sub(
        r"\bNETO\b",
        "",
        texto,
        flags=re.I
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip(" -|*()")


def _es_linea_ignorada(texto):

    mayusculas = texto.upper().strip()

    return any(
        palabra in mayusculas
        for palabra in LINEAS_IGNORAR
    )


def _extraer_datos_fila(texto):
    """
    Extrae cantidad, precio e importe.

    Prioriza la estructura:
        CANTIDAD PRECIO [NETO] IMPORTE

    No utiliza números que aparecen dentro de referencias o descripciones
    como si fueran importes.
    """

    coincidencias = list(
        PATRON_NUMERO.finditer(texto)
    )

    if len(coincidencias) < 3:
        return None

    # La etiqueta NETO identifica la posición del importe final.
    neto = re.search(
        r"\bNETO\b",
        texto,
        re.I
    )

    if neto:

        anteriores = [
            m for m in coincidencias
            if m.end() <= neto.start()
        ]

        posteriores = [
            m for m in coincidencias
            if m.start() >= neto.end()
        ]

        if len(anteriores) >= 2 and posteriores:

            cantidad = _num(anteriores[-2].group())
            precio_lista = _num(anteriores[-1].group())
            importe = _num(posteriores[0].group())

            if cantidad is not None and precio_lista is not None and importe is not None:
                return cantidad, precio_lista, importe

    # Alternativa para líneas auxiliares sin etiqueta NETO.
    ultimos = coincidencias[-3:]

    cantidad = _num(ultimos[0].group())
    precio_lista = _num(ultimos[1].group())
    importe = _num(ultimos[2].group())

    if None in (cantidad, precio_lista, importe):
        return None

    return cantidad, precio_lista, importe


def _extraer_referencia(texto):
    """
    La referencia se busca inmediatamente después del número ITEM.
    No se buscan palabras largas en toda la descripción.
    """

    m = PATRON_FILA.match(texto)

    if not m:
        return None, texto

    resto = m.group(2).strip()

    tokens = resto.split()

    if not tokens:
        return None, texto

    candidato = tokens[0].strip("()[]{}*,;:")

    # Referencias numéricas o alfanuméricas.
    if (
        len(candidato) >= 5
        and re.fullmatch(r"[A-Z0-9./-]+", candidato, re.I)
        and any(c.isdigit() for c in candidato)
    ):
        return candidato, " ".join(tokens[1:])

    return None, resto


def _limpiar_fila(texto, referencia, cantidad, precio, importe):

    texto = texto.strip()

    m = PATRON_FILA.match(texto)

    if m:
        texto = m.group(2)

    if referencia:
        texto = re.sub(
            r"^\s*" + re.escape(referencia) + r"\b",
            "",
            texto,
            count=1,
            flags=re.I
        )

    texto = PATRON_NUMERO.sub(" ", texto)

    texto = re.sub(
        r"\bNETO\b",
        " ",
        texto,
        flags=re.I
    )

    texto = re.sub(
        r"\(\s*[*%]\s*\)",
        " ",
        texto
    )

    return _limpiar_descripcion(texto)


def leer(ruta):

    print("[SONEPAR] Iniciando lectura...", flush=True)

    lineas = _lineas_ocr_detalle(ruta)

    texto_completo = "\n".join(
        l["texto"] for l in lineas
    )

    if "SONEPAR" not in texto_completo.upper():
        raise ValueError(
            "OCR no identifica Sonepar en el documento."
        )

    doc = Documento(
        tipo="oferta_proveedor",
        origen=str(ruta),
        proveedor="Sonepar",
        nombre="Oferta Sonepar"
    )

    m = re.search(
        r"PRESUPUESTO\s*(?:N[º°.]*)?\s*([A-Z0-9/-]+)",
        texto_completo,
        re.I
    )

    doc.referencia = m.group(1) if m else None

    m = re.search(
        r"\b(\d{2}/\d{2}/\d{4})\b",
        texto_completo
    )

    doc.fecha = m.group(1) if m else None

    capitulo = Capitulo(
        titulo="Oferta Sonepar"
    )

    ultima_partida = None
    lineas_detectadas = 0
    lineas_dudosas = 0

    for linea in lineas:

        texto = linea["texto"].strip()

        if not texto:
            continue

        if _es_linea_ignorada(texto):
            continue

        datos = _extraer_datos_fila(texto)

        if datos is None:

            # Una descripción puede continuar en la siguiente línea.
            # No se incorpora texto de cabeceras o pies de página.
            if ultima_partida and len(texto) > 3:

                if not re.search(
                    r"^(VENDEDOR|FECHA|TEL|EMAIL|SONEPAR|AVENIDA|CALLE)\b",
                    texto,
                    re.I
                ):
                    ultima_partida.descripcion += (
                        " " + _limpiar_descripcion(texto)
                    )

            continue

        cantidad, precio_lista, importe = datos

        if cantidad <= 0 or precio_lista < 0 or importe < 0:
            continue

        referencia, resto = _extraer_referencia(texto)

        descripcion = _limpiar_fila(
            texto,
            referencia,
            cantidad,
            precio_lista,
            importe
        )

        # Conceptos auxiliares: RAEE, ecopila, costes de gestión.
        auxiliar = bool(
            re.search(
                r"RAEE|ECOPILA|COSTE|GESTI[ÓO]N",
                texto,
                re.I
            )
        )

        if auxiliar:
            referencia = None

        if not descripcion:
            descripcion = (
                "Coste auxiliar"
                if auxiliar
                else "Artículo sin descripción"
            )
            lineas_dudosas += 1

        precio_neto = importe / cantidad

        notas = [
            "OCR Sonepar: verificar visualmente contra el PDF."
        ]

        if auxiliar:
            notas.append(
                "Concepto auxiliar RAEE/ecopila: revisar su tratamiento."
            )

        if not referencia and not auxiliar:
            notas.append(
                "Referencia no identificada con seguridad."
            )
            lineas_dudosas += 1

        if abs(
            round(cantidad * precio_lista, 2) - round(importe, 2)
        ) > 0.05:
            notas.append(
                "El importe no coincide con cantidad por precio de lista; "
                "comprobar posibles descuentos."
            )
            lineas_dudosas += 1

        partida = Partida(
            descripcion=descripcion,
            cantidad=cantidad,
            precio=precio_neto,
            referencia=referencia,
            precio_lista=precio_lista,
            importe_declarado=importe,
            notas=notas
        )

        capitulo.hijos.append(partida)

        ultima_partida = partida
        lineas_detectadas += 1

    if not capitulo.hijos:
        raise ValueError(
            "No se han reconocido partidas Sonepar."
        )

    doc.capitulos = [capitulo]

    doc.avisar(
        "revisar",
        "Oferta Sonepar extraída mediante OCR. "
        "Verificar las referencias, descripciones y precios antes "
        "de generar el BC3."
    )

    if lineas_dudosas:
        doc.avisar(
            "revisar",
            "%d partidas presentan campos dudosos o necesitan "
            "comprobación adicional." % lineas_dudosas
        )

        doc.validar()

    # DIAGNÓSTICO: comprobar que las partidas siguen dentro del documento.
    partidas_doc = list(doc.partidas())

    print("[SONEPAR DEBUG] Tipo documento:", type(doc).__name__, flush=True)
    print("[SONEPAR DEBUG] Capítulos:", len(doc.capitulos), flush=True)
    print("[SONEPAR DEBUG] Partidas mediante doc.partidas():", len(partidas_doc), flush=True)
    print("[SONEPAR DEBUG] Importe documento:", doc.importe, flush=True)

    for i, p in enumerate(partidas_doc[:3], 1):
        print(
            f"[SONEPAR DEBUG] {i}: "
            f"ref={p.referencia!r}, "
            f"descripcion={p.descripcion!r}, "
            f"cantidad={p.cantidad}, "
            f"precio={p.precio}, "
            f"importe={p.importe}",
            flush=True
        )

    print(
        f"[SONEPAR] Partidas extraídas: {lineas_detectadas}",
        flush=True
    )

    print(
        f"[SONEPAR] Partidas con incidencias: {lineas_dudosas}",
        flush=True
    )

    print(
        f"[SONEPAR] Total calculado: {doc.importe:.2f} €",
        flush=True
    )

    return doc