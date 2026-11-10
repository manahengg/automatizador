# Comparador de ofertas de material eléctrico

Le das el **presupuesto / licitación del cliente** (BC3 o PDF) y las **ofertas de los proveedores** (PDF con texto,
PDF escaneado o Excel) —al principio o en cualquier momento— y la app:

1. Pasa a Excel todas las partidas y capítulos del cliente y **casa cada artículo del proveedor con su partida**.
2. Genera la comparativa con: Capítulo · Nº licit. · Código cliente · Descripción · **Material a comprar** (cantidad
   real interpretada de la descripción) · por proveedor: Código · Cantidad ofertada · Diferencia de cantidad ·
   Precio · Importe · Diferencia con el cliente · y al final: Más bajo · P.U. más barato · P.U. más barato × cantidad ·
   Mejor precio de la BBDD · Alertas. El precio e importe más baratos se ponen en **verde**. Subtotales por capítulo.
3. Guarda **todos los precios en una base de datos** y avisa si un proveedor (aunque no esté en esta obra) tiene
   registrado un material más barato.
4. **Detecta irregularidades**: textos del cliente sin sentido, productos distintos a lo pedido, cantidades que no
   cuadran, potencias insuficientes…
5. **Aprende**: las correcciones de emparejamiento y los "casos" que anotas se recuerdan para obras futuras.

## Instalar en Windows (sin instalar Python)

1. En GitHub: pestaña **Actions** → flujo **"Instalador Windows"** → última ejecución en verde → sección
   **Artifacts** → descarga `ComparadorOfertas_Setup` (zip con `ComparadorOfertas_Setup_x.y.z.exe`).
2. Ejecuta el instalador (no pide permisos de administrador). Crea el acceso directo **"Comparador de ofertas"**.
3. Al abrirlo aparece una ventana negra (es el servidor; no la cierres mientras uses la app) y se abre el navegador.

Los datos (obras y `precios.db`) se guardan en `%LOCALAPPDATA%\ComparadorOfertas` y **no se borran** al desinstalar
o actualizar. Para compartir la base de datos entre equipos basta con copiar esa carpeta.

## Usar desde Python (cualquier sistema)

```bash
pip install -r requirements.txt
```

```bash
python -m automatizador app
```

Desde la carpeta que contiene `automatizador/`. Otras órdenes:

```bash
python -m automatizador comparar CLIENTE.pdf OFERTA1.pdf OFERTA2.pdf --obra "Nombre" -o comparativa.xlsx
```

```bash
python -m automatizador bbdd "1x35 rz1-k"
```

## Cómo funciona (por dentro)

| Paso | Módulo | Qué hace |
|---|---|---|
| Leer PDF | `pdfpalabras.py` | Palabras con su posición. Si la página es un escaneo, **OCR con RapidOCR** (incluido, sin programas externos). Une números que el PDF dibuja partidos ("7" + "70,80" → 770,80). |
| Oferta de proveedor | `lectores/pdf_oferta.py` | **Lector genérico por columnas** (no hay plantillas por proveedor): localiza la cabecera CÓDIGO/DESCRIPCIÓN/CANTIDAD/PRECIO/DTO/IMPORTE, asigna cada número a su columna y comprueba cantidad × precio × (1−dto) = importe. Detecta secciones (plantas), cánones RAEE, líneas OPCIONALES y el total del documento para verificar que cuadra. |
| Presupuesto del cliente | `lectores/pdf_presupuesto.py`, `lectores/bc3.py` | Capítulos, subcapítulos, partidas, descripción larga, cantidad, precio e importe (formato Presto/Arquímedes/m4PRO o BC3). |
| Conocimiento eléctrico | `electrico.py` | Familia del producto y características (sección, tipo de cable RZ1-K/H07Z1-K/RV-K/XZ1, Cu/Al, Ø, W, lm, K, IP, polos, A, mA, fases, kWp, óptica, longitud…). **Convierte la partida en materiales con cantidad real**: 4x35+1x16 unipolar × 27,5 m → 110 m de 1x35 + 27,5 m de 1x16; 3(1x150)+1x95 → 3×Q + Q; "2 TUBOS" → 2×Q; puesto de trabajo con 3 RJ45 → 3×Q conectores; sistema FV de 21 paneles → módulos + inversor. Revisa incoherencias (IP547 no existe, título y descripción con potencias distintas, "conexión a red" frente a "sin conexión a red", secciones no normalizadas, H07Z1-K a 0,6/1 kV…) y compara pedido/ofertado. |
| Emparejar | `emparejar.py` | Puntúa cada pareja línea↔material por código, familia, características, texto, cantidad y planta; asignación global + mejora local por bloques; los accesorios (tapas, placas, bases, protecciones…) se suman a su partida como complementos. Potencia FV: calcula cuántos módulos **del proveedor** hacen falta para los kWp pedidos y avisa si la oferta se queda corta o se pasa. |
| Base de datos | `bbdd.py` | SQLite: proveedores, obras, ofertas, **cada línea con su precio**, equivalencias aprendidas y casos anotados. Reconoce "el mismo material" por código, por clave técnica (`cable|1x35|RZ1-K`) o por la partida a la que se casó en otra obra. Optimizador FV con todos los módulos registrados. |
| Obra | `obra.py` | Carpeta por obra con los documentos, correcciones y caché de lecturas (el OCR se hace una sola vez). |
| Excel | `exportadores/excel_comparativa.py` | Hojas Comparativa, Resumen, Alertas, Líneas proveedores y BBDD precios. Todo con fórmulas; el verde es formato condicional. |
| App | `app_web.py`, `app_html.py` | Servidor local (solo 127.0.0.1, los ficheros no salen del ordenador). |
| Windows | `windows/`, `.github/workflows/windows.yml` | PyInstaller + Inno Setup construidos en GitHub Actions. |

### Cómo aprende

- **Correcciones de emparejamiento**: en "Líneas de proveedores" cambias a qué partida va una línea; se guarda en la
  obra y como equivalencia en la BBDD (ese código de ese proveedor = ese material), y se aplica en las próximas ofertas.
- **Casos**: botón "📝 Anotar caso" en cualquier fila de la comparativa (p. ej. *"Debería ser 10 módulos de 630 W:
  21 × 460 W está sobredimensionado"*). Se guarda con las características técnicas del material y aparece como aviso
  en cualquier obra futura con un material parecido. Se consultan y olvidan en la pestaña de la base de datos.
- **Precios**: cada oferta alimenta la BBDD, así que cada obra nueva compara también con lo ya visto.

## Ejemplos

`obras/` contiene dos casos reales usados para probar: Alburquerque (cliente en PDF; Electrofil en PDF y Sonepar
escaneado) y Museo de Mérida (cliente en BC3; Electromercantil y Electrofil).
