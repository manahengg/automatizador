# Archivo: app completa de comparativas (no se usa)

El enfoque cambió: el ERP de la empresa ya hace casi todo, y ahora solo se usa `Rellenar_precios.html` (en la raíz).

`app_completa/` es la app anterior, entera y tal como estaba (comparativa de ofertas, base de datos de precios, bases
de la Junta, petición de oferta, pedidos, reparto, aprendizaje con IA local...). Su documentación está en
`app_completa/README.md`, y su flujo de GitHub para generar el instalador de Windows en
`app_completa/github_workflows/` (desactivado: GitHub solo ejecuta los flujos de `.github/workflows/`).

## Para retomarla

1. Copia la carpeta `app_completa` a otro sitio con el nombre `automatizador`.
2. Desde la carpeta que la contiene, ejecuta:

   ```bash
   pip install -r automatizador/requirements.txt
   ```

   ```bash
   python -m automatizador app
   ```

3. Para volver a generar el instalador de Windows, devuelve `github_workflows/windows.yml` a `.github/workflows/`.

El historial completo de la app está en git: el último commit con la app en la raíz es
"Aprendizaje fase 4: modelo de lenguaje local".
