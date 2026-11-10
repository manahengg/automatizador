"""Una OBRA: el presupuesto del cliente + las ofertas de los proveedores que se van añadiendo + las correcciones.

Carpeta de cada obra (dentro de <datos>/obras/<nombre>/):
    cliente/<fichero>                  presupuesto o mediciones del cliente (BC3, PDF o Excel)
    proveedores/<Proveedor>/<fichero>  ofertas (PDF con texto o escaneado, Excel)
    estado.json                        qué hay cargado y las correcciones manuales de emparejamiento
    cache/<huella>.pkl                 lectura ya hecha de cada documento (el OCR solo se hace una vez)
    comparativa_<obra>.xlsx            el Excel generado

Se pueden añadir proveedores en cualquier momento: cada análisis se rehace con todo lo que haya.
"""
import datetime
import hashlib
import json
import os
import pickle
import re
import shutil

from . import bbdd as B
from . import emparejar as M
from .lectores import bc3, pdf_oferta, pdf_presupuesto

VERSION_CACHE = 4


def carpeta_datos():
    d = os.environ.get('AUTOMATIZADOR_DATOS') or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                               'automatizador_datos')
    os.makedirs(d, exist_ok=True)
    return d


def ruta_bbdd():
    return os.path.join(carpeta_datos(), 'precios.db')


def nombre_seguro(n):
    n = re.sub(r'[^\w\-. ]+', '_', n.strip(), flags=re.U).strip(' ._')
    return n[:60] or 'sin_nombre'


def huella(ruta):
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for trozo in iter(lambda: f.read(1 << 20), b''):
            h.update(trozo)
    return h.hexdigest()[:20]


# ------------------------------------------------------------------------------------------------ lectura
def leer_cliente(ruta, progreso=None):
    ext = os.path.splitext(ruta)[1].lower()
    if ext == '.bc3':
        return bc3.leer(ruta)
    if ext == '.pdf':
        return pdf_presupuesto.leer(ruta, progreso)
    if ext in ('.xlsx', '.xlsm'):
        from .lectores import excel_obra, excel_generico
        for lector in (excel_obra, excel_generico):
            try:
                if lector.reconoce(ruta):
                    return lector.leer(ruta)
            except Exception:
                continue
    raise ValueError('No sé leer el presupuesto del cliente "%s" (se admiten BC3, PDF y Excel).' % os.path.basename(ruta))


def leer_oferta(ruta, progreso=None):
    ext = os.path.splitext(ruta)[1].lower()
    if ext == '.pdf':
        return pdf_oferta.leer(ruta, progreso)
    if ext in ('.xlsx', '.xlsm'):
        from .lectores import excel_erp, excel_generico
        for lector in (excel_erp, excel_generico):
            try:
                if lector.reconoce(ruta):
                    return lector.leer(ruta)
            except Exception:
                continue
    if ext == '.bc3':
        return bc3.leer(ruta)
    raise ValueError('No sé leer la oferta "%s" (se admiten PDF, Excel y BC3).' % os.path.basename(ruta))


class Obra:
    def __init__(self, carpeta):
        self.carpeta = carpeta
        with open(os.path.join(carpeta, 'estado.json'), encoding='utf-8') as f:
            self.estado = json.load(f)
        self.estado.setdefault('proveedores', [])
        self.estado.setdefault('manuales', {})

    # -------------------------------------------------------------------------------------- gestión
    @classmethod
    def crear(cls, nombre):
        nombre = nombre.strip()
        if not nombre:
            raise ValueError('La obra necesita un nombre.')
        carpeta = os.path.join(carpeta_datos(), 'obras', nombre_seguro(nombre))
        if os.path.exists(os.path.join(carpeta, 'estado.json')):
            return cls(carpeta)
        os.makedirs(carpeta, exist_ok=True)
        with open(os.path.join(carpeta, 'estado.json'), 'w', encoding='utf-8') as f:
            json.dump({'nombre': nombre, 'creada': B.ahora(), 'cliente': None, 'proveedores': [], 'manuales': {}},
                      f, ensure_ascii=False, indent=1)
        return cls(carpeta)

    @staticmethod
    def listar():
        base = os.path.join(carpeta_datos(), 'obras')
        if not os.path.isdir(base):
            return []
        out = []
        for d in sorted(os.listdir(base)):
            if os.path.exists(os.path.join(base, d, 'estado.json')):
                out.append(Obra(os.path.join(base, d)))
        return out

    @staticmethod
    def abrir(ident):
        c = os.path.join(carpeta_datos(), 'obras', nombre_seguro(ident))
        if not os.path.exists(os.path.join(c, 'estado.json')):
            raise ValueError('No existe la obra "%s".' % ident)
        return Obra(c)

    @property
    def nombre(self):
        return self.estado['nombre']

    @property
    def ident(self):
        return os.path.basename(self.carpeta)

    def guardar(self):
        tmp = os.path.join(self.carpeta, 'estado.json.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.estado, f, ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(self.carpeta, 'estado.json'))

    def poner_cliente(self, ruta_origen, nombre_fichero=None, progreso=None):
        destino_dir = os.path.join(self.carpeta, 'cliente')
        shutil.rmtree(destino_dir, ignore_errors=True)
        os.makedirs(destino_dir)
        destino = os.path.join(destino_dir, nombre_fichero or os.path.basename(ruta_origen))
        shutil.copy2(ruta_origen, destino)
        doc = self._leer(destino, leer_cliente, progreso)          # falla aquí si no se puede leer
        self.estado['cliente'] = {'archivo': os.path.relpath(destino, self.carpeta), 'huella': huella(destino)}
        self.estado['manuales'] = {}                                # las correcciones dependían del presupuesto anterior
        self.guardar()
        return doc

    def anadir_proveedor(self, ruta_origen, proveedor=None, nombre_fichero=None, progreso=None):
        nombre_fichero = nombre_fichero or os.path.basename(ruta_origen)
        tmp = os.path.join(self.carpeta, 'tmp_' + nombre_seguro(nombre_fichero))
        shutil.copy2(ruta_origen, tmp)
        try:
            doc = self._leer(tmp, leer_oferta, progreso)
        except Exception:
            os.remove(tmp)
            raise
        proveedor = (proveedor or pdf_oferta.proveedor_por_carpeta(ruta_origen) or doc.proveedor or 'Proveedor').strip()
        destino_dir = os.path.join(self.carpeta, 'proveedores', nombre_seguro(proveedor))
        os.makedirs(destino_dir, exist_ok=True)
        destino = os.path.join(destino_dir, nombre_seguro(nombre_fichero))
        shutil.move(tmp, destino)
        h = huella(destino)
        # un proveedor = una oferta vigente por obra: la nueva sustituye a la anterior del mismo proveedor
        anteriores = [p for p in self.estado['proveedores'] if p['nombre'].lower() == proveedor.lower()]
        for p in anteriores:
            if p['archivo'] != os.path.relpath(destino, self.carpeta):
                try:
                    os.remove(os.path.join(self.carpeta, p['archivo']))
                except OSError:
                    pass
        self.estado['proveedores'] = [p for p in self.estado['proveedores'] if p['nombre'].lower() != proveedor.lower()]
        self.estado['proveedores'].append({'nombre': proveedor, 'archivo': os.path.relpath(destino, self.carpeta),
                                           'huella': h, 'anadida': B.ahora()})
        self.estado['manuales'].pop(proveedor, None)
        self.guardar()
        return proveedor, doc

    def quitar_proveedor(self, proveedor, bbdd=None):
        for p in self.estado['proveedores']:
            if p['nombre'] == proveedor:
                try:
                    os.remove(os.path.join(self.carpeta, p['archivo']))
                except OSError:
                    pass
        self.estado['proveedores'] = [p for p in self.estado['proveedores'] if p['nombre'] != proveedor]
        self.estado['manuales'].pop(proveedor, None)
        self.guardar()
        if bbdd:
            bbdd.quitar_oferta(self.nombre, proveedor)

    def fijar(self, proveedor, linea, material_id):
        """Corrección manual: la línea nº `linea` del proveedor va a `material_id` ('' o None = no casar)."""
        self.estado['manuales'].setdefault(proveedor, {})[str(linea)] = material_id or None
        self.guardar()

    def deshacer(self, proveedor, linea):
        self.estado['manuales'].get(proveedor, {}).pop(str(linea), None)
        self.guardar()

    # -------------------------------------------------------------------------------------- caché de lecturas
    def _leer(self, ruta, lector, progreso=None):
        h = huella(ruta)
        cache = os.path.join(self.carpeta, 'cache', '%s_%s_v%d.pkl' % (lector.__name__, h, VERSION_CACHE))
        if os.path.exists(cache):
            try:
                with open(cache, 'rb') as f:
                    return pickle.load(f)
            except Exception:
                pass
        doc = lector(ruta, progreso)
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, 'wb') as f:
            pickle.dump(doc, f)
        return doc

    # -------------------------------------------------------------------------------------- análisis
    def analizar(self, bbdd=None, progreso=None):
        """Lee todo, empareja cada proveedor, consulta y alimenta la base de datos de precios."""
        avisar = progreso or (lambda t: None)
        if not self.estado.get('cliente'):
            raise ValueError('Falta el presupuesto del cliente.')
        avisar('Leyendo el presupuesto del cliente…')
        cli = self._leer(os.path.join(self.carpeta, self.estado['cliente']['archivo']), leer_cliente, progreso)
        materiales = M.materiales_cliente(cli)
        conocidas = bbdd.conocidas() if bbdd else {}
        provs = []
        for p in self.estado['proveedores']:
            avisar('Leyendo y casando la oferta de %s…' % p['nombre'])
            doc = self._leer(os.path.join(self.carpeta, p['archivo']), leer_oferta, progreso)
            lineas = M.lineas_oferta(doc, p['nombre'])
            manuales = {int(k): v for k, v in self.estado['manuales'].get(p['nombre'], {}).items()}
            asign, sin, puntos = M.emparejar(materiales, lineas, manuales, conocidas)
            ofertas = M.construir_ofertas(materiales, asign)
            provs.append({'nombre': p['nombre'], 'doc': doc, 'lineas': lineas, 'asign': asign, 'sin': sin,
                          'ofertas': ofertas, 'puntos': puntos, 'archivo': p['archivo'], 'huella': p['huella']})
        res = Resultado(self, cli, materiales, provs)
        if bbdd:
            avisar('Guardando precios en la base de datos y buscando precios históricos…')
            por_id = {m.id: m for m in materiales}
            for pv in provs:
                asignado = {a.linea.i: por_id[a.material_id] for a in pv['asign'] if a.tipo == 'principal'}
                bbdd.registrar_oferta(self.nombre, pv['nombre'], os.path.basename(pv['archivo']), pv['huella'],
                                      pv['doc'], pv['lineas'], asignado)
            res.consultar_historico(bbdd)
        return res


class Resultado:
    """Todo lo que necesitan el Excel y la pantalla."""

    def __init__(self, obra, cliente, materiales, proveedores):
        self.obra = obra
        self.cliente = cliente
        self.materiales = materiales
        self.proveedores = proveedores
        self.historico = {}
        self.casos = {}          # material_id -> [(parecido, caso)]  correcciones aprendidas en casos parecidos
        self.optimo_fv = {}      # material_id -> [(coste, nº módulos, precio BBDD)]  mejor forma de llegar a los kWp

    def avisos_aprendidos(self, m):
        """Textos de lo aprendido para el material m (casos anteriores y optimización por potencia)."""
        out = []
        for p, c in self.casos.get(m.id, []):
            t = 'Caso aprendido (%s, obra "%s"%s): %s' % ((c['creado'] or '')[:10], c['obra'] or '',
                                                          ', proveedor %s' % c['proveedor'] if c['proveedor'] else '',
                                                          c['observacion'])
            if c['cantidad_correcta']:
                t += ' [cantidad correcta indicada: %s]' % ('%g' % c['cantidad_correcta'])
            if c['oferta']:
                t += ' — se había ofertado: %s' % c['oferta'][:80]
            out.append(t)
        ops = self.optimo_fv.get(m.id)
        if ops:
            coste, n, x = ops[0]
            kwp = m.atributos['kwp']
            t = ('Óptimo con los módulos de la BBDD para %s kWp: %d módulos de %d Wp (%s, %.2f €/ud) = %.2f € · %.2f kWp'
                 % (('%g' % kwp).replace('.', ','), n, x['wp'], x['proveedor'], x['precio_neto'], coste, n * x['wp'] / 1000))
            otros = ['%d×%dW %s %.0f €' % (nn, xx['wp'], xx['proveedor'], cc) for cc, nn, xx in ops[1:4]]
            if otros:
                t += '. Otras opciones: ' + '; '.join(otros)
            out.append(t)
        return out

    def oferta(self, prov, mid):
        return prov['ofertas'].get(mid)

    def mas_barato(self, m, solo_principal=False):
        """(proveedor, precio) más barato entre las ofertas de esta obra para el material m.
        solo_principal: precio de la línea principal (sin accesorios ni cánones), para comparar con la BBDD."""
        def precio(o):
            return o.principal.partida.precio if solo_principal else o.precio
        mejores = [(precio(pv['ofertas'][m.id]), pv['nombre']) for pv in self.proveedores
                   if m.id in pv['ofertas'] and precio(pv['ofertas'][m.id])]
        if not mejores:
            return None, None
        p, n = min(mejores)
        return n, p

    def consultar_historico(self, bbdd):
        self.casos = {}
        self.optimo_fv = {}
        todos = bbdd.casos()
        modulos = None
        for m in self.materiales:
            parecidos = bbdd.casos_parecidos(m, todos)
            if parecidos:
                self.casos[m.id] = parecidos[:3]
            kwp = m.atributos.get('kwp')
            if kwp and m.atributos.get('familia') == 'modulo_fv':
                modulos = bbdd.modulos_fv() if modulos is None else modulos
                opciones = []
                for x in modulos:
                    n = int(-(-kwp * 1000 // x['wp']))
                    opciones.append((n * x['precio_neto'], n, x))
                opciones.sort(key=lambda t: (t[0], t[1]))
                if opciones:
                    self.optimo_fv[m.id] = opciones[:5]
        en_obra = {pv['nombre'].lower() for pv in self.proveedores}
        for m in self.materiales:
            codigos = []
            for pv in self.proveedores:
                o = pv['ofertas'].get(m.id)
                if o and o.principal.referencia:
                    codigos.append((bbdd.proveedor_id(pv['nombre']), B.cod(o.principal.referencia)))
            filas = bbdd.precios_material(m, codigos, excluir_obra=self.obra.nombre)
            if not filas:
                continue
            ultimos = bbdd.mejor_por_proveedor(filas)
            mejor = ultimos[0]
            _, actual = self.mas_barato(m, solo_principal=True)
            aviso = None
            if actual is None or mejor['precio_neto'] < actual * 0.995:
                fuera = mejor['proveedor'].lower() not in en_obra
                aviso = '%s tiene registrado este material a %.4f € (%s, obra "%s")%s%s' % (
                    mejor['proveedor'], mejor['precio_neto'], mejor['fecha'] or '', mejor['obra'],
                    ' — NO está en esta obra' if fuera else '',
                    (' — más barato que el mejor precio actual (%.4f €)' % actual) if actual else
                    ' — en esta obra nadie lo ha ofertado')
            self.historico[m.id] = {'filas': filas, 'ultimos': ultimos, 'mejor': mejor, 'aviso': aviso}
