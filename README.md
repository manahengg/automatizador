# Rellenar precios de oferta en el Excel del ERP

**Abre `Rellenar_precios.html`** (doble clic; Chrome o Edge). No hay que instalar nada.

1. Arrastra el **Excel de petición de oferta del ERP** (el de ese proveedor y esa obra).
2. Arrastra el **PDF del presupuesto del proveedor** (uno o varios; también escaneados).
3. Revisa la tabla y pulsa **⬇ Descargar Excel con precios**.

Se descarga el mismo Excel (`<nombre>_precios.xlsx`) con **solo la columna "SU PRECIO UD" rellena**: el resto del
fichero queda idéntico, byte a byte (formatos, anchos, cabecera...). Todo ocurre en el ordenador: ningún fichero sale de él.

## Qué hace con cada proveedor

No hay plantillas por proveedor: sirve para Electrofil, Electromercantil, Sonepar o cualquier otro.

- **Lee las líneas del PDF** y reconoce cada artículo porque cumple *cantidad × precio × (1 − dto) = importe*. Así
  encuentra las columnas en cualquier formato, y también los números que el PDF dibuja partidos ("7" + "70,80").
- **PDF escaneados** (sin texto): se leen con OCR (Tesseract) en la propia página. **La primera vez necesita internet**
  para descargar el OCR; los PDF con texto funcionan sin internet. Si el escaneo pierde una coma o un dígito, la cuenta
  lo corrige y la línea se marca en amarillo para revisarla.
- **Precio que se escribe:** el **neto por unidad**, con su descuento (importe ÷ cantidad).
- **Partidas en metros y el proveedor vende piezas o rollos de N m:** se pasa a €/m y se marca para revisar.
- **Empareja** cada fila del Excel con su línea del PDF siguiendo el orden, la descripción (los números de modelo
  pesan más) y la cantidad.
- **Colores de la tabla:**
  - verde: seguro;
  - amarillo: revisar;
  - rojo: no está en el PDF;
  - gris: el proveedor la incluye sin precio.

  En cualquier fila se puede elegir otra línea del PDF o escribir el precio a mano.

Probado con los presupuestos reales del Museo de Mérida:
- **Electrofil:** 85 de 85 líneas, suma 862.434,23 €.
- **Electromercantil:** 85 de 85.
- **Sonepar escaneado (Mormones):** 19 de 21 correctas; el resto, en rojo para elegirlas a mano.

## Para quien lo mantenga

- `rellenador/nucleo.js`: lectura del PDF, artículos, lectura del Excel, emparejamiento y escritura de precios (sin
  interfaz; se puede probar con Node).
- `rellenador/plantilla.html`: la página.
- `rellenador/vendor/`: pdf.js (Apache 2.0) y JSZip (MIT).
- `python rellenador/construir.py`: vuelve a generar `Rellenar_precios.html`, un solo fichero con todo dentro.
- `node rellenador/pruebas.js`: pruebas rápidas del núcleo, con datos inventados.

## La app completa anterior

La app de comparativas (comparador, base de datos de precios, aprendizaje, pedidos...) **no se ha borrado**: está en
`archivo/app_completa/`, sin usar, por si se quiere retomar (ver `archivo/LEEME.md`).
