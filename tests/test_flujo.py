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
JUNTA = os.path.join(REPO, 'recursos', 'bases_precios', 'BASE_DE_DATOS_PRECIOS_JUNTA_EXTREMADURA_2026.xlsx')
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


from urllib.parse import quote


def main():
    os.environ['AUTOMATIZADOR_DATOS'] = tempfile.mkdtemp(prefix='prueba_app_')
    # los modelos de IA se descargan una vez y se reutilizan entre pruebas
    os.environ.setdefault('AUTOMATIZADOR_MODELOS', os.path.join(tempfile.gettempdir(), 'automatizador_modelos'))
    from automatizador import app_web
    threading.Thread(target=app_web.servir, kwargs={'puerto': PUERTO, 'abrir': False}, daemon=True).start()
    from automatizador.tests import ejemplos
    docs_prueba = ejemplos.generar(tempfile.mkdtemp(prefix='ejemplos_'))
    CLIENTE, OFERTA1, OFERTA2 = docs_prueba['cliente'], docs_prueba['oferta1'], docs_prueba['oferta2']
    time.sleep(2)
    t0 = time.time()
    while time.time() - t0 < 600:                   # el modelo de comprensión del texto se descarga solo al arrancar
        ms = pedir('/api/modelos')
        e5 = next(m for m in ms['modelos'] if m['nombre'] == 'e5-small')
        if e5['disponible'] or (e5['descarga'] or {}).get('estado') == 'error':
            break
        time.sleep(2)
    comprobar(e5['disponible'], 'el modelo de comprensión del texto se descarga solo (%s)' % (e5['descarga'] or {}).get('texto'))
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
    ds = pedir('/api/decisiones')
    comprobar(len(ds) == 1 and ds[0]['accion'] == 'casar' and ds[0]['proveedor'] == 'Electrofil',
              'la decisión se registra con su contexto (fase 0)')
    # 2) deshacer
    pedir(O + '/deshacer', {'proveedor': 'Electrofil', 'linea': libre['uid']})
    l3 = next(l for l in pedir(O)['lineas']['Electrofil']['lineas'] if l['uid'] == libre['uid'])
    comprobar(not l3['manual'], 'deshacer la corrección')
    comprobar(not pedir('/api/decisiones'), 'deshacer olvida también la decisión')
    # 3) "no casar" una línea casada
    casada = next(l for l in lineas if l['mat'])
    pedir(O + '/fijar', {'proveedor': 'Electrofil', 'linea': casada['uid'], 'material': ''})
    l4 = next(l for l in pedir(O)['lineas']['Electrofil']['lineas'] if l['uid'] == casada['uid'])
    comprobar(l4['mat'] is None and l4['manual'], 'marcar una línea como "no casar"')
    comprobar([x['accion'] for x in pedir('/api/decisiones')] == ['descasar'], 'se registra el "no casar"')
    con_of = next(m['id'] for m in pedir(O)['materiales'] if 'Electrofil' in m['prov'])
    r_ac = pedir(O + '/aceptar', {'material': con_of})
    comprobar(r_ac['ok'] and any(x['accion'] == 'aceptar' for x in pedir('/api/decisiones')), '✔ Aceptar: %s' % r_ac['mensaje'])
    u = next(x['uid'] for x in pedir('/api/decisiones') if x['accion'] == 'aceptar')
    pedir('/api/decisiones/olvidar', {'uid': u})
    comprobar(all(x['accion'] != 'aceptar' for x in pedir('/api/decisiones')), 'olvidar una decisión')
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
    # fase 1: búsqueda por significado (otras palabras, mismo material)
    sem = pedir('/api/bbdd?modo=sem&q=' + quote('conductor de cobre libre de halógenos de 2,5'))
    comprobar(sem.get('semantica') and sem['filas'] and '2,5' in sem['filas'][0]['descripcion'],
              'búsqueda por significado: "%s"' % (sem['filas'][0]['descripcion'] if sem['filas'] else '-'))
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
    # 9) base de precios de la Junta: presente en TODAS las obras sin subirla, como referencia
    d = pedir(O)
    J = 'Junta Extremadura 2026'
    j = d['lineas'].get(J)
    comprobar(j is not None and j['global'] and j['referencia'] and 0 < len(j['lineas']) <= ejemplos.MATERIALES,
              'la base de la Junta está en la obra sin subirla (%d artículos usados)' % (len(j['lineas']) if j else 0))
    comprobar(any(p['nombre'] == J for p in d['proveedores']), 'la Junta sale como columna de proveedor')
    comprobar(all(m['mejor']['prov'] != J for m in d['materiales']), 'la Junta no es "más barato" (no recibe pedidos)')
    avisos_j = [a['t'] for m in d['materiales'] for a in (m['prov'].get(J) or {}).get('alertas', [])
                if 'MÁS BARATO' in a['t'] or 'ningún distribuidor' in a['t']]
    comprobar(avisos_j, 'aviso cuando la Junta es más barata o nadie más lo oferta (%d): %s'
              % (len(avisos_j), avisos_j[0][:90] if avisos_j else ''))
    pedir('/api/obras', {'nombre': 'Otra_obra', 'cod': 'E0002', 'cliente': 'X'})
    subir('/api/obra/Otra_obra/cliente', [CLIENTE])
    pedir('/api/obra/Otra_obra/capitulos', {'incluidos': todos})
    comprobar(J in pedir('/api/obra/Otra_obra')['lineas'], 'y también en una obra nueva sin ofertas')
    bs = pedir('/api/bases')
    hj = next(b['huella'] for b in bs if b['origen'] == 'app')
    pedir('/api/bases/quitar', {'huella': hj})
    comprobar(J not in pedir(O)['lineas'], 'quitar la base de todas las obras')
    subir_base = pedir('/api/bases', ficheros=[JUNTA])
    comprobar(subir_base['ok'] and J in pedir(O)['lineas'], 'volver a activarla subiéndola')
    reparto_filas = pedir(O)['reparto']['filas']
    comprobar(reparto_filas and all(x['proveedor'] != J for x in reparto_filas),
              'reparto entre distribuidores: %s' % ', '.join('%s %.2f' % (x['proveedor'], x['importe'])
                                                              for x in reparto_filas))
    d = pedir(O)
    # 10) pedidos: al más barato en total (toda su oferta) y uno por distribuidor con sus materiales más baratos
    ganador = next(x for x in d['totales_prov'] if x['ganador'])
    comprobar(all(x['proveedor'] != 'Junta Extremadura' for x in d['totales_prov']), 'la Junta no recibe pedidos')
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
    n_ped = sum(1 for x in pedir('/api/decisiones') if x['accion'] == 'pedido')
    comprobar(n_ped >= len(ejemplos.PARTIDAS) // 2, 'lo pedido cuenta como aceptado (%d decisiones)' % n_ped)
    comprobar(abs(total_zip - d['reparto']['total']) < 1.0, 'los pedidos del reparto suman lo mismo que el reparto '
                                                             '(%.2f / %.2f)' % (total_zip, d['reparto']['total']))
    nom, xlsx = nombre_descarga('/api/base/%s/desglose' % hj)
    comprobar('Desglose' in nom and xlsx[:2] == b'PK', 'desglose de la base de precios: %s' % nom)
    # 11) fase 2: lo aprendido en una obra se aplica en otra
    O2 = '/api/obra/Otra_obra'
    subir(O2 + '/proveedor', [OFERTA1], {'proveedor': 'Electrofil', 'sustituir': '0'})
    d2 = pedir(O2)
    l_desc = next(l for l in d2['lineas']['Electrofil']['lineas'] if l['desc'] == casada['desc'])
    comprobar(l_desc['mat'] != casada['mat'],
              'lo que se DESCASÓ en otra obra no se vuelve a casar solo (%s)' % casada['desc'][:40])
    portes = next(l for l in d2['lineas']['Electrofil']['lineas'] if l['desc'].startswith('PORTES'))
    comprobar(not portes['mat'], 'antes de aprender: "PORTES" sin casar en la obra nueva')
    det = next(m['id'] for m in pedir(O)['materiales'] if 'DETECTOR' in m['resumen'].upper())
    lp = next(l for l in pedir(O)['lineas']['Electrofil']['lineas'] if l['desc'].startswith('PORTES'))
    pedir(O + '/fijar', {'proveedor': 'Electrofil', 'linea': lp['uid'], 'material': det})
    d2 = pedir(O2)
    portes = next(l for l in d2['lineas']['Electrofil']['lineas'] if l['desc'].startswith('PORTES'))
    m_det = next(m for m in d2['materiales'] if m['id'] == det)
    of = m_det['prov'].get('Electrofil') or {}
    comprobar(portes['mat'] == det and of.get('aprendido') and 'Aplicado por lo aprendido' in of['aprendido'],
              'lo que se CASÓ a mano en una obra se aplica solo en otra, explicado: %s' % (of.get('aprendido') or '-')[:110])
    ea = pedir('/api/aprendizaje')
    comprobar(ea['muestras'] > 0 and ea['decisiones'] > 0,
              'modelo de confianza: %d decisiones, %d muestras (%d aciertos / %d errores), entrenado: %s %s'
              % (ea['decisiones'], ea['muestras'], ea['aciertos'], ea['errores'], ea['entrenado'], ea['pesos'] or ''))
    print('TODO CORRECTO')


if __name__ == '__main__':
    try:
        main()
    except AssertionError as e:
        print('ERROR:', e)
        sys.exit(1)
    os._exit(0)
