"""Una OBRA: el presupuesto del cliente + las ofertas de los proveedores que se van añadiendo + las correcciones.

Carpeta de cada obra (dentro de <carpeta compartida>/obras/<nombre>/, ver compartido.py):
    cliente/<fichero>                  presupuesto o mediciones del cliente (BC3, PDF o Excel)
    proveedores/<Proveedor>/<fichero>  ofertas (PDF con texto o escaneado, Excel)
    eventos/*.json                     qué ha hecho cada persona (subir, añadir, quitar, corregir); el estado se deduce
                                       de ellos, así varias personas pueden trabajar a la vez sin pisarse

Se pueden añadir proveedores en cualquier momento: cada análisis se rehace con todo lo que haya.
"""
import datetime
import hashlib
import json
import os
import re
import shutil

from . import bbdd as B
from . import compartido as C
from .modelo import doc_a_dict, doc_de_dict
from . import emparejar as M
from .lectores import bc3, pdf_oferta, pdf_presupuesto

VERSION_CACHE = 5


def carpeta_datos():
    return C.carpeta_local()


def ruta_bbdd():
    return os.path.join(C.carpeta_local(), 'precios.db')


def _describir(tipo, d):
    return {'crear': 'creó la obra', 'cliente': 'subió el presupuesto del cliente %s' % d.get('archivo', '').split('/')[-1],
            'proveedor': 'añadió la oferta de %s' % d.get('nombre'), 'quitar': 'quitó la oferta de %s' % d.get('nombre'),
            'fijar': 'casó la línea %s de %s con %s' % ((d.get('linea') or 0) + 1, d.get('proveedor'),
                                                        d.get('material') or '(sin casar)'),
            'deshacer': 'deshizo la corrección de la línea %s de %s' % ((d.get('linea') or 0) + 1, d.get('proveedor'))
            }.get(tipo, tipo)


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
    """Estado = eventos de la carpeta eventos/ aplicados en orden (ver compartido.py)."""

    def __init__(self, carpeta):
        self.carpeta = carpeta
        self._migrar_estado_json()
        self.recargar()

    # -------------------------------------------------------------------------------------- estado por eventos
    @property
    def dir_eventos(self):
        return os.path.join(self.carpeta, 'eventos')

    def recargar(self):
        e = {'nombre': os.path.basename(self.carpeta), 'creada': None, 'cliente': None, 'proveedores': [],
             'manuales': {}, 'historial': []}
        for ev in C.leer_eventos(self.dir_eventos):
            d, t = ev.get('datos') or {}, ev.get('tipo')
            quien = ev.get('usuario')
            if t == 'crear':
                e['nombre'] = d.get('nombre') or e['nombre']
                e['creada'] = e['creada'] or ev.get('cuando')
            elif t == 'cliente':
                e['cliente'] = {'archivo': d['archivo'], 'huella': d['huella'], 'usuario': quien, 'cuando': ev['cuando']}
                e['manuales'] = {}                      # las correcciones dependían del presupuesto anterior
            elif t == 'proveedor':
                nom = d['nombre']
                e['proveedores'] = [p for p in e['proveedores'] if p['nombre'].lower() != nom.lower()]
                e['proveedores'].append({'nombre': nom, 'archivo': d['archivo'], 'huella': d['huella'],
                                         'anadida': ev['cuando'], 'usuario': quien})
                e['manuales'].pop(nom, None)
            elif t == 'quitar':
                e['proveedores'] = [p for p in e['proveedores'] if p['nombre'] != d['nombre']]
                e['manuales'].pop(d['nombre'], None)
            elif t == 'fijar':
                e['manuales'].setdefault(d['proveedor'], {})[str(d['linea'])] = d.get('material')
            elif t == 'deshacer':
                e['manuales'].get(d['proveedor'], {}).pop(str(d['linea']), None)
            e['historial'].append({'cuando': ev.get('cuando'), 'usuario': quien, 'tipo': t,
                                   'detalle': _describir(t, d)})
        self.estado = e

    def _evento(self, tipo, datos):
        C.escribir_evento(self.dir_eventos, tipo, datos)
        self.recargar()

    def marca(self):
        """Cambia cuando cualquier persona toca la obra (eventos o documentos)."""
        return C.marca_carpeta(self.dir_eventos)

    def _migrar_estado_json(self):
        """Obras creadas con la versión anterior (estado.json modificable) -> eventos."""
        viejo = os.path.join(self.carpeta, 'estado.json')
        if not os.path.exists(viejo) or os.path.isdir(self.dir_eventos):
            return
        with open(viejo, encoding='utf-8') as f:
            e = json.load(f)
        C.escribir_evento(self.dir_eventos, 'crear', {'nombre': e.get('nombre') or os.path.basename(self.carpeta)})
        if e.get('cliente'):
            C.escribir_evento(self.dir_eventos, 'cliente', e['cliente'])
        for p in e.get('proveedores', []):
            C.escribir_evento(self.dir_eventos, 'proveedor', {'nombre': p['nombre'], 'archivo': p['archivo'],
                                                              'huella': p['huella']})
        for prov, m in (e.get('manuales') or {}).items():
            for li, mat in m.items():
                C.escribir_evento(self.dir_eventos, 'fijar', {'proveedor': prov, 'linea': int(li), 'material': mat})
        os.replace(viejo, viejo + '.migrado')

    # -------------------------------------------------------------------------------------- gestión
    @staticmethod
    def base():
        return os.path.join(C.carpeta_compartida(), 'obras')

    @classmethod
    def crear(cls, nombre):
        nombre = nombre.strip()
        if not nombre:
            raise ValueError('La obra necesita un nombre.')
        carpeta = os.path.join(cls.base(), nombre_seguro(nombre))
        existe = os.path.isdir(os.path.join(carpeta, 'eventos')) or os.path.exists(os.path.join(carpeta, 'estado.json'))
        os.makedirs(carpeta, exist_ok=True)
        if not existe:
            C.escribir_evento(os.path.join(carpeta, 'eventos'), 'crear', {'nombre': nombre})
        return cls(carpeta)

    @staticmethod
    def listar():
        base = Obra.base()
        if not os.path.isdir(base):
            return []
        out = []
        for d in sorted(os.listdir(base)):
            c = os.path.join(base, d)
            if os.path.isdir(os.path.join(c, 'eventos')) or os.path.exists(os.path.join(c, 'estado.json')):
                out.append(Obra(c))
        return out

    @staticmethod
    def abrir(ident):
        c = os.path.join(Obra.base(), nombre_seguro(ident))
        if not (os.path.isdir(os.path.join(c, 'eventos')) or os.path.exists(os.path.join(c, 'estado.json'))):
            raise ValueError('No existe la obra "%s".' % ident)
        return Obra(c)

    @property
    def nombre(self):
        return self.estado['nombre']

    @property
    def ident(self):
        return os.path.basename(self.carpeta)

    def _copiar(self, origen, subcarpeta, nombre_fichero):
        """Copia un documento a la obra SIN sobrescribir nunca (si ya existe otro distinto, se le pone sufijo)."""
        destino_dir = os.path.join(self.carpeta, subcarpeta)
        os.makedirs(destino_dir, exist_ok=True)
        base, ext = os.path.splitext(nombre_seguro(nombre_fichero))
        h = huella(origen)
        destino = os.path.join(destino_dir, base + ext)
        k = 1
        while os.path.exists(destino) and huella(destino) != h:
            k += 1
            destino = os.path.join(destino_dir, '%s_%d%s' % (base, k, ext))
        if not os.path.exists(destino):
            tmp = os.path.join(destino_dir, '~$' + os.path.basename(destino) + '.tmp')
            shutil.copy2(origen, tmp)
            os.replace(tmp, destino)
        return destino, h

    def poner_cliente(self, ruta_origen, nombre_fichero=None, progreso=None):
        doc = self._leer(ruta_origen, leer_cliente, progreso)           # falla aquí si no se puede leer
        destino, h = self._copiar(ruta_origen, 'cliente', nombre_fichero or os.path.basename(ruta_origen))
        self._evento('cliente', {'archivo': os.path.relpath(destino, self.carpeta).replace(os.sep, '/'), 'huella': h})
        return doc

    def anadir_proveedor(self, ruta_origen, proveedor=None, nombre_fichero=None, progreso=None):
        nombre_fichero = nombre_fichero or os.path.basename(ruta_origen)
        doc = self._leer(ruta_origen, leer_oferta, progreso)
        proveedor = (proveedor or pdf_oferta.proveedor_por_carpeta(ruta_origen) or doc.proveedor or 'Proveedor').strip()
        destino, h = self._copiar(ruta_origen, os.path.join('proveedores', nombre_seguro(proveedor)), nombre_fichero)
        # una oferta nueva de un proveedor ya cargado sustituye a la anterior (el fichero viejo se conserva)
        self._evento('proveedor', {'nombre': proveedor, 'huella': h,
                                   'archivo': os.path.relpath(destino, self.carpeta).replace(os.sep, '/')})
        return proveedor, doc

    def quitar_proveedor(self, proveedor, bbdd=None):
        self._evento('quitar', {'nombre': proveedor})
        if bbdd:
            bbdd.quitar_oferta(self.nombre, proveedor)

    def fijar(self, proveedor, linea, material_id):
        """Corrección manual: la línea nº `linea` del proveedor va a `material_id` ('' o None = no casar)."""
        self._evento('fijar', {'proveedor': proveedor, 'linea': int(linea), 'material': material_id or None})

    def deshacer(self, proveedor, linea):
        self._evento('deshacer', {'proveedor': proveedor, 'linea': int(linea)})

    # -------------------------------------------------------------------------------------- caché de lecturas
    def _leer(self, ruta, lector, progreso=None):
        """Lee un documento con caché COMPARTIDA (JSON, por huella): un escaneo se pasa por OCR una vez para todos."""
        h = huella(ruta)
        dir_cache = os.path.join(C.carpeta_compartida(), 'cache')
        cache = os.path.join(dir_cache, '%s_%s_v%d.json' % (lector.__name__, h, VERSION_CACHE))
        if os.path.exists(cache):
            try:
                with open(cache, encoding='utf-8') as f:
                    return doc_de_dict(json.load(f))
            except (OSError, ValueError, KeyError, TypeError):
                pass
        doc = lector(ruta, progreso)
        try:
            os.makedirs(dir_cache, exist_ok=True)
            tmp = os.path.join(dir_cache, '~$%s.tmp' % os.path.basename(cache))
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(doc_a_dict(doc), f, ensure_ascii=False)
            os.replace(tmp, cache)
        except OSError:
            pass
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
            bbdd.sincronizar_obra(self.nombre, [p['nombre'] for p in provs], {p['huella'] for p in provs})
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
