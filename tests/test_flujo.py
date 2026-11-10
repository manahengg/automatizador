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
ALB = os.path.join(REPO, 'obras', 'alburquerque')
CLIENTE = os.path.join(ALB, 'cliente', 'DOC20250604121822Pliego de prescripciones tecnicas.PDF.pdf')
ELECTROFIL = os.path.join(ALB, 'proveedores', 'electrofil', 'OFE_160_70922.pdf')
MERIDA_ELECTROFIL = os.path.join(REPO, 'obras', 'mueso merida', 'proveedores', 'electrofil',
                                 'OFERTA_ELECTROFIL_160_79996.pdf')
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
    time.sleep(2)
    obra = 'Prueba'
    O = '/api/obra/' + obra
    pedir('/api/obras', {'nombre': obra})
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
    subir(O + '/proveedor', [ELECTROFIL], {'proveedor': 'Electrofil', 'sustituir': '0'})
    subir(O + '/proveedor', [MERIDA_ELECTROFIL], {'proveedor': 'Electrofil', 'sustituir': '0'})
    d = pedir(O)
    docs = d['lineas']['Electrofil']['docs']
    comprobar(len(docs) == 2, 'un proveedor con dos ofertas (se añaden, no se sustituyen)')
    comprobar(len(d['materiales']) == 45, 'materiales del presupuesto: %d' % len(d['materiales']))
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
    print('TODO CORRECTO')


if __name__ == '__main__':
    try:
        main()
    except AssertionError as e:
        print('ERROR:', e)
        sys.exit(1)
    os._exit(0)
