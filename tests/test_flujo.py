"""Prueba de extremo a extremo de la app, a través de su API HTTP (lo mismo que hace la pantalla).

Ejecutar desde la carpeta que CONTIENE el paquete:   python -m automatizador.tests.test_flujo
Sale con código 1 si algo falla. La usa también el flujo de GitHub antes de construir el instalador.
"""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(AQUI)
# documentos INVENTADOS (tests/ejemplos.py): el repositorio es público y no lleva documentos reales de obras
JUNTA = os.path.join(REPO, 'obras', 'bases_precios', 'BASE_DE_DATOS_PRECIOS_JUNTA_EXTREM.xlsx')
PUERTO = 8791
BASE = 'http://127.0.0.1:%d' % PUERTO


def pedir(ruta, datos=None, ficheros=None, campos=None):
    if ficheros:
        limite = uuid.uuid4().hex
        cuerpo = b''
        for k, v in (campos or {}).items():
            cuerpo += ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (limite, k, v)).encode()
        for f in ficheros:
            with open(f, 'rb') as fh:
                contenido = fh.read()
            cuerpo += ('--%s\r\nContent-Disposition: form-data; name="fichero"; filename="%s"\r\n'
                       'Content-Type: application/octet-stream\r\n\r\n' % (limite, os.path.basename(f))).encode()
            cuerpo += contenido + b'\r\n'
        cuerpo += ('--%s--\r\n' % limite).encode()
        req = urllib.request.Request(BASE + ruta, data=cuerpo,
                                     headers={'Content-Type': 'multipart/form-data; boundary=' + limite})
    elif datos is not None:
        req = urllib.request.Request(BASE + ruta, data=json.dumps(datos).encode(),
                                     headers={'Content-Type': 'application/json'})
    else:
        req = urllib.request.Request(BASE + ruta)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            cuerpo = r.read()
            return json.loads(cuerpo) if r.headers.get_content_type() == 'application/json' else cuerpo
    except urllib.error.HTTPError as e:
        raise AssertionError('%s -> HTTP %s: %s' % (ruta, e.code, e.read().decode('utf-8', 'replace')))


def nombre_descarga(ruta):
    with urllib.request.urlopen(BASE + ruta, timeout=600) as r:
        cd = r.headers.get('Content-Disposition') or ''
        datos = r.read()
    from urllib.parse import unquote as uq
    nom = cd.split("filename*=UTF-8''")[-1] if "filename*=" in cd else ''
    return uq(nom), datos


def subir(ruta, ficheros, campos=None):
    t = pedir(ruta, ficheros=ficheros, campos=campos)['trabajo']
    while True:
        j = pedir('/api/trabajo/' + t)
        if j['estado'] != 'trabajando':
            assert j['estado'] == 'listo', 'Subida fallida: %s' % j['mensaje']
            return j
        time.sleep(0.5)


def comprobar(condicion, texto):
    print(('  OK   ' if condicion else '  FALLO ') + texto)
    if not condicion:
        raise AssertionError(texto)


def main():
    os.environ['AUTOMATIZADOR_DATOS'] = tempfile.mkdtemp(prefix='prueba_app_')
    from automatizador import app_web
    threading.Thread(target=app_web.servir, kwargs={'puerto': PUERTO, 'abrir': False}, daemon=True).start()
    from automatizador.tests import ejemplos
    docs_prueba = ejemplos.generar(tempfile.mkdtemp(prefix='ejemplos_'))
    CLIENTE, OFERTA1, OFERTA2 = docs_prueba['cliente'], docs_prueba['oferta1'], docs_prueba['oferta2']
    time.sleep(2)
    obra = 'Prueba'
    O = '/api/obra/' + obra
    pedir('/api/obras', {'nombre': obra, 'cod': 'E0001', 'cliente': 'Cliente Prueba'})
    subir(O + '/cliente', [CLIENTE])
    d = pedir(O)
    comprobar(d.get('pendiente_capitulos'), 'tras subir el presupuesto se piden los capítulos')
    caps = pedir(O + '/capitulos')
    todos = []

    def rec(ns):
        for n in ns:
            todos.append(n['clave'])
            rec(n['hijos'])
    rec(caps['arbol'])
    pedir(O + '/capitulos', {'incluidos': todos})
    subir(O + '/proveedor', [OFERTA1], {'proveedor': 'Electrofil', 'sustituir': '0'})
    subir(O + '/proveedor', [OFERTA2], {'proveedor': 'Electrofil', 'sustituir': '0'})
    d = pedir(O)
    docs = d['lineas']['Electrofil']['docs']
    comprobar(len(docs) == 2, 'un proveedor con dos ofertas (se añaden, no se sustituyen)')
    comprobar(len(d['materiales']) == ejemplos.MATERIALES,
              'materiales del presupuesto (%d partidas, la 4x35+1x16 desglosada): %d' % (len(ejemplos.PARTIDAS),
                                                                                   len(d['materiales'])))
    con_oferta = sum(1 for m in d['materiales'] if m['prov'])
    comprobar(con_oferta == ejemplos.MATERIALES, 'todos los materiales casados con las ofertas: %d' % con_oferta)
    lineas = d['lineas']['Electrofil']['lineas']
    libre = next(l for l in lineas if not l['mat'] and l['precio'] is not None)
    destino = d['materiales'][5]['id']
    # 1) casar a mano una línea sin asignar (el fallo que se vio en la app)
    pedir(O + '/fijar', {'proveedor': 'Electrofil', 'linea': libre['uid'], 'material': destino})
    l2 = next(l for l in pedir(O)['lineas']['Electrofil']['lineas'] if l['uid'] == libre['uid'])
    comprobar(l2['mat'] == destino and l2['manual'], 'casar a mano una línea sin asignar')
    comprobar(pedir('/api/bbdd?q=x')['resumen']['equivalencias'] > 0, 'la corrección se aprende en la BBDD')
    # 2) deshacer
    pedir(O + '/deshacer', {'proveedor': 'Electrofil', 'linea': libre['uid']})
    l3 = next(l for l in pedir(O)['lineas']['Electrofil']['lineas'] if l['uid'] == libre['uid'])
    comprobar(not l3['manual'], 'deshacer la corrección')
    # 3) "no casar" una línea casada
    casada = next(l for l in lineas if l['mat'])
    pedir(O + '/fijar', {'proveedor': 'Electrofil', 'linea': casada['uid'], 'material': ''})
    l4 = next(l for l in pedir(O)['lineas']['Electrofil']['lineas'] if l['uid'] == casada['uid'])
    comprobar(l4['mat'] is None and l4['manual'], 'marcar una línea como "no casar"')
    # 4) quitar una de las dos ofertas
    pedir(O + '/quitar_oferta', {'huella': docs[1]['huella']})
    d = pedir(O)
    comprobar(len(d['lineas']['Electrofil']['docs']) == 1, 'quitar una sola oferta del proveedor')
    l5 = next(l for l in d['lineas']['Electrofil']['lineas'] if l['uid'] == casada['uid'])
    comprobar(l5['manual'], 'las correcciones de la otra oferta se conservan')
    # 5) Excel
    xlsx = pedir(O + '/excel')
    comprobar(isinstance(xlsx, bytes) and xlsx[:2] == b'PK', 'se genera el Excel')
    # 6) caso aprendido
    pedir(O + '/caso', {'material': destino, 'observacion': 'prueba', 'proveedor': '', 'cantidad': ''})
    comprobar(len(pedir('/api/casos')) == 1, 'anotar un caso')
    # 7) nombre de los Excel: Cod_Obra.Cliente.descripcion.tipo.DD-MM-YYYY
    nom, _ = nombre_descarga(O + '/excel')
    hoy = time.strftime('%d-%m-%Y')
    comprobar(nom == 'E0001.CLIENTE_PRUEBA.PRUEBA.Comparativa.%s.xlsx' % hoy, 'nombre del Excel: %s' % nom)
    pedir(O + '/datos', {'cod': 'E0123', 'cliente': 'Constructora', 'descripcion': 'Edificio Ejemplo'})
    nom, _ = nombre_descarga(O + '/excel')
    comprobar(nom.startswith('E0123.CONSTRUCTORA.EDIFICIO_EJEMPLO.Comparativa.'), 'cambiar los datos de la obra: %s' % nom)
    # 8) petición de oferta sin precios -> el proveedor la rellena -> se sube como oferta y se casa por código
    import openpyxl
    from automatizador.exportadores import excel_peticion as P
    nom, xlsx = nombre_descarga(O + '/peticion')
    comprobar('.Peticion_oferta.' in nom and xlsx[:2] == b'PK', 'se genera la petición de oferta: %s' % nom)
    tmp = tempfile.mkdtemp(prefix='peticion_')
    ruta = os.path.join(tmp, 'peticion_rellena.xlsx')
    with open(ruta, 'wb') as f:
        f.write(xlsx)
    wb = openpyxl.load_workbook(ruta)
    ws = wb.worksheets[0]
    rellenas = 0
    for r in range(P.F_CABECERA + 1, ws.max_row + 1):
        if ws.cell(r, P.C_COD).value and rellenas < 8:
            ws.cell(r, P.C_PRECIO).value = 10 + r
            ws.cell(r, P.C_DTO).value = 25
            rellenas += 1
    wb.save(ruta)
    subir(O + '/proveedor', [ruta], {'proveedor': 'Proveedor Peticion', 'sustituir': '0'})
    d = pedir(O)
    ls = d['lineas']['Proveedor Peticion']['lineas']
    comprobar(len(ls) == rellenas and all(l['mat'] for l in ls) and all(l['manual'] is False or l['mat'] for l in ls),
              'la petición rellena se casa entera por código (%d de %d)' % (sum(1 for l in ls if l['mat']), len(ls)))
    # 9) base de precios de la Junta: referencia, no cuenta para el más barato ni el reparto
    subir(O + '/proveedor', [JUNTA], {'proveedor': 'Junta Extremadura', 'sustituir': '0'})
    d = pedir(O)
    j = d['lineas']['Junta Extremadura']
    comprobar(j['referencia'] and j['catalogo'] and 0 < len(j['lineas']) <= ejemplos.MATERIALES,
              'la base de la Junta entra como referencia (%d artículos usados)' % len(j['lineas']))
    comprobar(all(m['mejor']['prov'] != 'Junta Extremadura' for m in d['materiales']), 'la Junta no es "más barato"')
    comprobar(d['reparto']['filas'] and all(x['proveedor'] != 'Junta Extremadura' for x in d['reparto']['filas']),
              'reparto entre distribuidores: %s' % ', '.join('%s %.2f' % (x['proveedor'], x['importe'])
                                                              for x in d['reparto']['filas']))
    # 10) pedidos: al más barato en total (toda su oferta) y uno por distribuidor con sus materiales más baratos
    ganador = next(x for x in d['totales_prov'] if x['ganador'])
    comprobar(all(x['proveedor'] != 'Junta Extremadura' for x in d['totales_prov']), 'la Junta no recibe pedidos')
    from urllib.parse import quote
    nom, xlsx = nombre_descarga(O + '/pedido?modo=total&prov=' + quote(ganador['proveedor']))
    comprobar('.Pedido_' in nom and xlsx[:2] == b'PK', 'pedido completo al más barato en total (%s): %s'
              % (ganador['proveedor'], nom))
    import io
    import zipfile
    nom, zdatos = nombre_descarga(O + '/pedidos_reparto')
    z = zipfile.ZipFile(io.BytesIO(zdatos))
    con_materiales = [x for x in d['reparto']['filas'] if x['materiales']]
    comprobar(len(z.namelist()) == len(con_materiales), 'un pedido por distribuidor del reparto: %s' % z.namelist())
    total_zip = 0.0
    from automatizador.exportadores import excel_pedido as XP
    for n in z.namelist():
        wb = openpyxl.load_workbook(io.BytesIO(z.read(n)))
        ws = wb.active
        for r in range(XP.F_CABECERA + 1, ws.max_row + 1):
            c, p_ = ws.cell(r, XP.C_CANT).value, ws.cell(r, XP.C_PRECIO).value
            if isinstance(c, (int, float)) and isinstance(p_, (int, float)) and ws.cell(r, 1).value:
                total_zip += c * p_
    comprobar(abs(total_zip - d['reparto']['total']) < 1.0, 'los pedidos del reparto suman lo mismo que el reparto '
                                                             '(%.2f / %.2f)' % (total_zip, d['reparto']['total']))
    nom, xlsx = nombre_descarga(O + '/desglose/' + j['docs'][0]['huella'])
    comprobar('Desglose' in nom and xlsx[:2] == b'PK', 'desglose de la base de precios: %s' % nom)
    print('TODO CORRECTO')


if __name__ == '__main__':
    try:
        main()
    except AssertionError as e:
        print('ERROR:', e)
        sys.exit(1)
    os._exit(0)
