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

## Novedades de uso

- **Capítulos que hacemos**: al subir el presupuesto del cliente la app pregunta qué capítulos hacemos nosotros; solo
  esos se comparan, se casan y salen en el Excel (la numeración Nº licit. se mantiene). Se cambia cuando se quiera con
  el botón "📂 Capítulos que hacemos".
- **Proyecto en varios ficheros**: el presupuesto del cliente puede ser un BC3, un PDF o **varios Excel** (formato
  "Orden · Designación · Cantidad · Precio"); se unen por código y los capítulos se deducen del código (08.02.22 → 08 >
  08.02). Se pueden añadir ficheros más tarde ("Añadir al proyecto actual").
- **Varias ofertas por proveedor**: p. ej. una por capítulo, o una sola para todo; se casan todas juntas. Al subir se
  elige si se añade o si sustituye a las anteriores de ese proveedor.
- Columnas del proveedor: **unitario** y **total**.
- **Datos de la obra y nombre de los Excel**: al crear la obra se piden el **código de obra** y el **cliente** (se
  cambian con "✏ Datos de la obra"). Todo Excel que genera la app se llama
  `Cod_Obra.Cliente.descripcion_breve.tipo_documento.DD-MM-YYYY.xlsx`, p. ej.
  `E0123.CONSTRUCTORA.EDIFICIO_EJEMPLO.Comparativa.11-11-2026.xlsx`. Los Excel ya no llevan el logo.
- **Petición de oferta** ("📤 Petición de oferta"): Excel con las partidas de los capítulos elegidos **sin precios**
  para mandarlo a los proveedores (cantidad real de material, descripción completa, celdas amarillas para marca,
  referencia, precio y descuento; sin el nombre del cliente). Cuando el proveedor lo devuelve relleno se sube como
  oferta y **se casa solo por el código** de cada fila.
- **Bases de precios** (p. ej. la de la Junta de Extremadura en Excel): se suben como un proveedor más y entran como
  **referencia**: se comparan sus precios de material, pero no cuentan para el "más barato" ni para el reparto, y avisan
  si los distribuidores están por encima. En Documentos, "⬇ Desglose" saca un Excel con cada partida separada en mano
  de obra / materiales / maquinaria / %, los materiales con su precio y las incoherencias de la propia base.
- **Reparto entre distribuidores**: comprando cada material al más barato, cuánto se le adjudica a cada distribuidor
  (en la pantalla y en la hoja Resumen del Excel).
- **Halógenos**: antes de avisar se deduce si lo ofertado lleva halógenos (designación Z1 = libre, V = PVC; AS/LSZH/LH;
  CPR a1; marcas; PVC en tubos). Solo hay alerta grave si se confirma que los lleva.

## Instalar en Windows (sin instalar Python)

1. En GitHub: pestaña **Actions** → flujo **"Instalador Windows"** → última ejecución en verde → sección
   **Artifacts** → descarga `ComparadorOfertas_Windows` (un ZIP).
2. **Antes de descomprimir**: clic derecho en el ZIP → Propiedades → marca **Desbloquear** → Aceptar. Descomprímelo.
3. Doble clic en **`Instalar.bat`**. Copia la app a `%LOCALAPPDATA%\Programs\ComparadorOfertas`, crea el acceso
   directo **"Comparador de ofertas"** (escritorio y menú Inicio) y la abre. Si Windows muestra "Windows protegió su
   PC": *Más información* → *Ejecutar de todas formas*.
4. Al abrirla aparece una ventana negra (es el servidor; no la cierres mientras uses la app) y se abre el navegador.

**Actualizaciones automáticas:** el ZIP solo hay que instalarlo una vez. Después, cada vez que se abre, la app mira si
hay una versión nueva en GitHub (de la misma rama con la que se construyó el ZIP; se puede cambiar en ⚙ Configuración →
Actualizaciones) y se actualiza sola: descarga solo el código (unos cientos de KB) y lo deja también en la carpeta
compartida para los demás PCs (`actualizaciones/`). Si una versión necesita librerías nuevas, la app avisa de que hay que
instalar el ZIP completo; si una versión nueva no arranca, vuelve sola a la anterior (`actualizar.py`). Si el
repositorio vuelve a ser privado, basta con poner un token de GitHub de solo lectura en un PC.

**Por qué no hay un .exe ni un instalador .exe:** Windows 11 (Smart App Control / Control de aplicaciones) bloquea
los ejecutables sin firma digital (error *"código 4551"*), también el instalador de Inno Setup, que se extrae y
ejecuta desde la carpeta temporal. El ZIP lleva el **Python embebido oficial de python.org, firmado**, las librerías
tal cual se publican en PyPI y el código de la app en ficheros `.py`; `Instalar.bat` (los .bat no los controla
Smart App Control) usa ese `python.exe` para instalar (`windows/instalar.py`) y el acceso directo abre ese mismo
`python.exe` con la app. Si al abrirla la ventana negra avisa de que no se pudo cargar una librería, Windows ha
bloqueado una DLL de esa librería. La solución definitiva es **firmar** con un certificado de firma de código de la
empresa (p. ej. Azure Trusted Signing); entonces se puede volver al instalador `windows/instalador.iss`.

Los datos (obras y `precios.db`) se guardan en `%LOCALAPPDATA%\ComparadorOfertas` y **no se borran** al desinstalar
o actualizar.

## Trabajo en equipo con SharePoint (compartido y en tiempo real)

1. En SharePoint crea una carpeta para la app (p. ej. "Comparador de ofertas") y pulsa **Sincronizar** o
   **Agregar acceso directo a Mis archivos**: aparecerá en el Explorador de Windows de cada PC.
2. En la app: **⚙ Configuración** → pega la ruta de esa carpeta (clic derecho → *Copiar como ruta de acceso*; la app
   también propone las carpetas de OneDrive/SharePoint que encuentra) y escribe tu nombre.
3. Si ya tenías obras en tu PC, el botón **"Copiarlas a la carpeta compartida"** las sube.

Se comparte **todo**: obras, documentos, ofertas, correcciones de emparejamiento, casos anotados y precios. Cada
pantalla abierta se actualiza sola en unos segundos cuando un compañero cambia algo (con el aviso "Actualizado: …"), y
cada obra tiene un **historial** de quién hizo qué.

Cómo se evita que OneDrive genere conflictos: en la carpeta compartida **nunca se modifica un fichero, solo se crean
ficheros nuevos** (un "evento" por acción: `obras/<obra>/eventos/*.json`, `conocimiento/*.json`). El estado de una obra
es la suma de sus eventos en orden; si dos personas tocan la misma línea a la vez, queda la última. Las lecturas de los
PDF (también el OCR) se guardan en `cache/` y se reutilizan en todos los PCs. Cada PC mantiene su base de datos de
precios local, que se completa sola con lo de todos (funciona sin conexión y se pone al día al volver).

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
| Base de precios | `lectores/base_precios.py`, `exportadores/excel_base_precios.py` | Base oficial en Excel FIEBDC aplanado (padre · tipo · código · precio · descomposición): capítulos, partidas con su descomposición, materiales; incoherencias (título frente a descomposición, sumas que no cuadran). Se casa en "modo catálogo" (`emparejar_catalogo`: un artículo puede servir a varias partidas, filtros estrictos de material/tipo/tensión/medidas). |
| Petición de oferta | `exportadores/excel_peticion.py`, `lectores/excel_peticion.py` | Excel sin precios para proveedores y lectura del mismo devuelto relleno (casado por código). |
| Presupuesto del cliente | `lectores/pdf_presupuesto.py`, `lectores/bc3.py` | Capítulos, subcapítulos, partidas, descripción larga, cantidad, precio e importe (formato Presto/Arquímedes/m4PRO o BC3). |
| Conocimiento eléctrico | `electrico.py` | Familia del producto y características (sección, tipo de cable RZ1-K/H07Z1-K/RV-K/XZ1, Cu/Al, Ø, W, lm, K, IP, polos, A, mA, fases, kWp, óptica, longitud…). **Convierte la partida en materiales con cantidad real**: 4x35+1x16 unipolar × 27,5 m → 110 m de 1x35 + 27,5 m de 1x16; 3(1x150)+1x95 → 3×Q + Q; "2 TUBOS" → 2×Q; puesto de trabajo con 3 RJ45 → 3×Q conectores; sistema FV de 21 paneles → módulos + inversor. Revisa incoherencias (IP547 no existe, título y descripción con potencias distintas, "conexión a red" frente a "sin conexión a red", secciones no normalizadas, H07Z1-K a 0,6/1 kV…) y compara pedido/ofertado. |
| Emparejar | `emparejar.py` | Puntúa cada pareja línea↔material por código, familia, características, texto, cantidad y planta; asignación global + mejora local por bloques; los accesorios (tapas, placas, bases, protecciones…) se suman a su partida como complementos. Potencia FV: calcula cuántos módulos **del proveedor** hacen falta para los kWp pedidos y avisa si la oferta se queda corta o se pasa. |
| Base de datos | `bbdd.py` | SQLite: proveedores, obras, ofertas, **cada línea con su precio**, equivalencias aprendidas y casos anotados. Reconoce "el mismo material" por código, por clave técnica (`cable|1x35|RZ1-K`) o por la partida a la que se casó en otra obra. Optimizador FV con todos los módulos registrados. |
| Obra | `obra.py` | Carpeta por obra con los documentos; el estado se deduce de sus eventos. Caché de lecturas compartida en JSON. |
| Equipo | `compartido.py` | Configuración (carpeta compartida, usuario) y eventos: escribir sin modificar nunca un fichero, leer en orden. La app vigila la carpeta cada 3 s y avisa a los navegadores. |
| Excel | `exportadores/excel_comparativa.py` | Hojas Comparativa, Resumen, Alertas, Líneas proveedores y BBDD precios. Todo con fórmulas; el verde es formato condicional. |
| App | `app_web.py`, `app_html.py` | Servidor local (solo 127.0.0.1, los ficheros no salen del ordenador). |
| Windows | `windows/`, `.github/workflows/windows.yml` | Python embebido oficial + `Instalar.bat`/`instalar.py` (sin .exe propios), construido y probado en GitHub Actions. |

### Cómo aprende

- **Correcciones de emparejamiento**: en "Líneas de proveedores" cambias a qué partida va una línea; se guarda en la
  obra y como equivalencia en la BBDD (ese código de ese proveedor = ese material), y se aplica en las próximas ofertas.
- **Casos**: botón "📝 Anotar caso" en cualquier fila de la comparativa (p. ej. *"Debería ser 10 módulos de 630 W:
  21 × 460 W está sobredimensionado"*). Se guarda con las características técnicas del material y aparece como aviso
  en cualquier obra futura con un material parecido. Se consultan y olvidan en la pestaña de la base de datos.
- **Precios**: cada oferta alimenta la BBDD, así que cada obra nueva compara también con lo ya visto.

## Ejemplos

Los documentos reales de las obras (presupuestos de clientes y ofertas de proveedores) **no se guardan en el
repositorio**, que es público: `obras/` está en `.gitignore` salvo `obras/bases_precios/` (base de precios pública de la
Junta de Extremadura 2026). Las pruebas automáticas usan documentos inventados que genera `tests/ejemplos.py`
(un presupuesto en Excel y ofertas en PDF, una de ellas escaneada para probar el OCR).