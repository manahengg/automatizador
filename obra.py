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

VERSION_CACHE = 8


def carpeta_datos():
    return C.carpeta_local()


def ruta_bbdd():
    return os.path.join(C.carpeta_local(), 'precios.db')


PREFIJO_PETICION = 'PET:'      # código que lleva cada fila de una petición de oferta (exportadores/excel_peticion.py)


def clave_mat(m):
    """Identificador del material que no depende de la numeración: código de partida + sufijo (a, b...)."""
    return '%s%s' % ((m.codigo or '').strip(), m.id[len(str(m.n)):])


def _n_linea(linea):
    """Número de línea legible (1, 2...) de un identificador 'huella:nº' o de un número de versiones anteriores."""
    t = str(linea if linea is not None else 0).split(':')[-1]
    return int(t) + 1 if t.isdigit() else t


def _describir(tipo, d):
    return {'crear': 'creó la obra', 'cliente': 'subió el presupuesto del cliente %s' % d.get('archivo', '').split('/')[-1],
            'proveedor': '%s la oferta %s de %s' % ('añadió' if d.get('modo') == 'anadir' else 'subió (sustituyendo)',
                                                    d.get('archivo', '').split('/')[-1], d.get('nombre')), 'quitar': 'quitó la oferta de %s' % d.get('nombre'),
            'fijar': 'casó la línea %s de %s con %s' % (_n_linea(d.get('linea')), d.get('proveedor'),
                                                        d.get('material') or '(sin casar)'),
            'deshacer': 'deshizo la corrección de la línea %s de %s' % (_n_linea(d.get('linea')), d.get('proveedor')),
            'capitulos': 'eligió los capítulos que hacemos (%d)' % len(d.get('incluidos') or []),
            'cliente_anadir': 'añadió al presupuesto del cliente %s' % ', '.join(
                x['archivo'].split('/')[-1] for x in d.get('archivos') or []),
            'cliente_quitar': 'quitó del presupuesto del cliente %s' % d.get('archivo', '').split('/')[-1],
            'quitar_oferta': 'quitó la oferta %s de %s' % (d.get('archivo', '').split('/')[-1], d.get('nombre')),
            'datos': 'puso los datos de la obra (código %s, cliente %s)' % (d.get('cod') or '-', d.get('cliente') or '-')
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
        from .lectores import excel_proyecto, excel_obra, excel_generico
        for lector in (excel_proyecto, excel_obra, excel_generico):
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
        from .lectores import excel_erp, excel_generico, base_precios, excel_peticion
        for lector in (base_precios, excel_peticion, excel_erp, excel_generico):
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
             'manuales': {}, 'historial': [], 'capitulos': None,      # capitulos None = aún sin elegir
             'ofertas': [], 'capitulos_previos': None, 'capitulos_conocidos': [],
             'datos': {'cod': '', 'cliente': '', 'descripcion': ''}}       # para nombrar los Excel
        for ev in C.leer_eventos(self.dir_eventos):
            d, t = ev.get('datos') or {}, ev.get('tipo')
            quien = ev.get('usuario')
            if t == 'crear':
                e['nombre'] = d.get('nombre') or e['nombre']
                e['creada'] = e['creada'] or ev.get('cuando')
            elif t in ('cliente', 'cliente_anadir'):
                nuevos = d.get('archivos') or [{'archivo': d['archivo'], 'huella': d['huella']}]
                if t == 'cliente' or not e['cliente']:
                    e['cliente'] = {'archivos': [], 'usuario': quien, 'cuando': ev['cuando']}
                    e['manuales'] = {}                  # las correcciones dependían del presupuesto anterior
                    e['capitulos_previos'] = None
                else:
                    e['capitulos_previos'] = e['capitulos']     # se vuelve a preguntar, con lo elegido ya marcado
                for x in nuevos:
                    if all(y['huella'] != x['huella'] for y in e['cliente']['archivos']):
                        e['cliente']['archivos'].append({'archivo': x['archivo'], 'huella': x['huella']})
                e['cliente']['archivo'] = e['cliente']['archivos'][0]['archivo']
                e['capitulos'] = None
            elif t == 'cliente_quitar':
                if e['cliente']:
                    e['cliente']['archivos'] = [x for x in e['cliente']['archivos'] if x['huella'] != d['huella']]
                    if not e['cliente']['archivos']:
                        e['cliente'] = None
                    else:
                        e['cliente']['archivo'] = e['cliente']['archivos'][0]['archivo']
            elif t == 'proveedor':
                nom = d['nombre']
                if d.get('modo', 'sustituir') == 'sustituir':   # (las ofertas de versiones anteriores sustituían)
                    e['ofertas'] = [o for o in e['ofertas'] if o['proveedor'].lower() != nom.lower()]
                    e['manuales'].pop(nom, None)
                if all(o['huella'] != d['huella'] or o['proveedor'].lower() != nom.lower() for o in e['ofertas']):
                    e['ofertas'].append({'proveedor': nom, 'archivo': d['archivo'], 'huella': d['huella'],
                                         'anadida': ev['cuando'], 'usuario': quien})
            elif t == 'quitar':
                e['ofertas'] = [o for o in e['ofertas'] if o['proveedor'] != d['nombre']]
                e['manuales'].pop(d['nombre'], None)
            elif t == 'quitar_oferta':
                e['ofertas'] = [o for o in e['ofertas'] if o['huella'] != d['huella']]
            elif t == 'datos':
                e['datos'] = {k: (d.get(k) or '').strip() for k in ('cod', 'cliente', 'descripcion')}
            elif t == 'capitulos':
                e['capitulos'] = list(d.get('incluidos') or [])
                e['capitulos_conocidos'] = list(d.get('conocidos') or [])
            elif t == 'fijar':
                e['manuales'].setdefault(d['proveedor'], {})[str(d['linea'])] = {
                    'id': d.get('material'), 'cod': d.get('material_cod')} if d.get('material') else None
            elif t == 'deshacer':
                e['manuales'].get(d['proveedor'], {}).pop(str(d['linea']), None)
            e['historial'].append({'cuando': ev.get('cuando'), 'usuario': quien, 'tipo': t,
                                   'detalle': _describir(t, d)})
        # proveedores = nombres con al menos una oferta (cada uno puede tener varias)
        provs = {}
        for o in e['ofertas']:
            p = provs.setdefault(o['proveedor'].lower(), {'nombre': o['proveedor'], 'ofertas': [], 'anadida': o['anadida'],
                                                          'usuario': o['usuario']})
            p['ofertas'].append(o)
            p['archivo'], p['huella'] = o['archivo'], o['huella']
        e['proveedores'] = list(provs.values())
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
    def crear(cls, nombre, cod='', cliente=''):
        nombre = nombre.strip()
        if not nombre:
            raise ValueError('La obra necesita un nombre.')
        carpeta = os.path.join(cls.base(), nombre_seguro(nombre))
        existe = os.path.isdir(os.path.join(carpeta, 'eventos')) or os.path.exists(os.path.join(carpeta, 'estado.json'))
        os.makedirs(carpeta, exist_ok=True)
        if not existe:
            C.escribir_evento(os.path.join(carpeta, 'eventos'), 'crear', {'nombre': nombre})
            if cod or cliente:
                C.escribir_evento(os.path.join(carpeta, 'eventos'), 'datos',
                                  {'cod': cod, 'cliente': cliente, 'descripcion': nombre})
        return cls(carpeta)

    def poner_datos(self, cod, cliente, descripcion):
        self._evento('datos', {'cod': cod, 'cliente': cliente, 'descripcion': descripcion})

    def nombre_excel(self, tipo, fecha=None):
        """'Cod_Obra.Cliente.descripcion_breve.tipo_documento.DD-MM-YYYY.xlsx' (p. ej.
        'E0123.CONSTRUCTORA.EDIFICIO_EJEMPLO.Comparativa.11-11-2026.xlsx'). Los puntos separan los campos, así que
        dentro de cada campo los puntos y espacios pasan a '_'."""
        d = self.estado.get('datos') or {}

        def campo(x):
            import unicodedata
            x = ''.join(c for c in unicodedata.normalize('NFKD', x or '') if not unicodedata.combining(c))
            x = re.sub(r'[\\/:*?"<>|.\s]+', '_', (x or '').strip()).strip('_')
            return x or 'SIN'
        fecha = fecha or datetime.date.today()
        return '%s.%s.%s.%s.%s.xlsx' % (campo(d.get('cod')), campo(d.get('cliente')).upper(),
                                        campo(d.get('descripcion') or self.nombre).upper(), campo(tipo),
                                        fecha.strftime('%d-%m-%Y'))

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

    def poner_cliente(self, ruta_origen, nombre_fichero=None, progreso=None, anadir=False, mas=None):
        """Sube el presupuesto del cliente. `mas`: otros ficheros del mismo proyecto [(ruta, nombre)].
        anadir=True: se añade al presupuesto que ya hay (proyecto en varios ficheros) en vez de sustituirlo."""
        archivos, doc = [], None
        for ruta, nom in [(ruta_origen, nombre_fichero or os.path.basename(ruta_origen))] + list(mas or []):
            doc = self._leer(ruta, leer_cliente, progreso)            # falla aquí si no se puede leer
            destino, h = self._copiar(ruta, 'cliente', nom)
            archivos.append({'archivo': os.path.relpath(destino, self.carpeta).replace(os.sep, '/'), 'huella': h})
        tipo = 'cliente_anadir' if anadir and self.estado.get('cliente') else 'cliente'
        self._evento(tipo, {'archivos': archivos})
        return self.documento_cliente(progreso) if len(archivos) > 1 or tipo == 'cliente_anadir' else doc

    def quitar_cliente(self, huella_doc):
        x = next((a for a in (self.estado.get('cliente') or {}).get('archivos', []) if a['huella'] == huella_doc), None)
        if x:
            self._evento('cliente_quitar', {'huella': huella_doc, 'archivo': x['archivo']})

    def anadir_proveedor(self, ruta_origen, proveedor=None, nombre_fichero=None, progreso=None, sustituir=False):
        nombre_fichero = nombre_fichero or os.path.basename(ruta_origen)
        doc = self._leer(ruta_origen, leer_oferta, progreso)
        proveedor = (proveedor or pdf_oferta.proveedor_por_carpeta(ruta_origen) or doc.proveedor or 'Proveedor').strip()
        destino, h = self._copiar(ruta_origen, os.path.join('proveedores', nombre_seguro(proveedor)), nombre_fichero)
        # un proveedor puede tener varias ofertas (p. ej. una por capítulo); sustituir=True reemplaza las anteriores
        self._evento('proveedor', {'nombre': proveedor, 'huella': h, 'modo': 'sustituir' if sustituir else 'anadir',
                                   'archivo': os.path.relpath(destino, self.carpeta).replace(os.sep, '/')})
        return proveedor, doc

    def quitar_proveedor(self, proveedor, bbdd=None):
        self._evento('quitar', {'nombre': proveedor})
        if bbdd:
            bbdd.quitar_oferta(self.nombre, proveedor)

    def quitar_oferta(self, huella_doc, bbdd=None):
        """Quita UNA oferta (documento) de un proveedor; sus otras ofertas se mantienen."""
        o = next((x for x in self.estado['ofertas'] if x['huella'] == huella_doc), None)
        if o:
            self._evento('quitar_oferta', {'huella': huella_doc, 'nombre': o['proveedor'], 'archivo': o['archivo']})

    def fijar(self, proveedor, linea, material_id, material_cod=None):
        """Corrección manual: la línea `linea` (identificador 'huella:nº' dentro de su documento) del proveedor va a
        `material_id` ('' o None = no casar). Se guarda también el código de la partida (material_cod), para que la
        corrección siga siendo válida aunque cambie la numeración al añadir ficheros al proyecto."""
        self._evento('fijar', {'proveedor': proveedor, 'linea': str(linea), 'material': material_id or None,
                               'material_cod': material_cod})

    def elegir_capitulos(self, incluidos, conocidos=None):
        """Capítulos del presupuesto del cliente que hacemos nosotros (claves de emparejar.arbol_capitulos).
        conocidos: todos los capítulos que había al elegir (para marcar como nuevos los que aparezcan después)."""
        if not incluidos:
            raise ValueError('Elige al menos un capítulo.')
        self._evento('capitulos', {'incluidos': list(incluidos), 'conocidos': list(conocidos or incluidos)})

    @property
    def pendiente_capitulos(self):
        return bool(self.estado.get('cliente')) and self.estado.get('capitulos') is None

    def documento_cliente(self, progreso=None):
        """El presupuesto del cliente; si viene en varios ficheros, unido en uno solo."""
        docs = [self._leer(os.path.join(self.carpeta, a['archivo']), leer_cliente, progreso)
                for a in self.estado['cliente']['archivos']]
        from .lectores.excel_proyecto import combinar_documentos
        return combinar_documentos(docs, self.nombre)

    def deshacer(self, proveedor, linea):
        self._evento('deshacer', {'proveedor': proveedor, 'linea': str(linea)})

    # -------------------------------------------------------------------------------------- caché de lecturas
    def _leer(self, ruta, lector, progreso=None):
        """Lee un documento con caché COMPARTIDA (JSON, por huella): un escaneo se pasa por OCR una vez para todos."""
        h = huella(ruta)
        dir_cache = os.path.join(C.carpeta_compartida(), 'cache')
        cache = os.path.join(dir_cache, '%s_%s_v%d.json' % (lector.__name__, h, VERSION_CACHE))
        if os.path.exists(cache):
            try:
                with open(cache, encoding='utf-8') as f:
                    doc = doc_de_dict(json.load(f))
                if progreso:
                    progreso('Documento ya leído: se reutiliza su lectura (sin repetir el OCR)', 1.0)
                return doc
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
        avisar = progreso or (lambda t, f=None: None)
        if not self.estado.get('cliente'):
            raise ValueError('Falta el presupuesto del cliente.')
        avisar('Leyendo el presupuesto del cliente…')
        cli = self.documento_cliente(progreso)
        materiales = M.materiales_cliente(cli)
        self.total_materiales = len(materiales)
        if self.estado.get('capitulos') is not None:           # solo los capítulos que hacemos nosotros
            incl = set(self.estado['capitulos'])
            materiales = [m for m in materiales if M.clave_material_cap(m) in incl]
        por_cod = {}
        for m in materiales:
            por_cod.setdefault(clave_mat(m), m.id)
        conocidas = bbdd.conocidas() if bbdd else {}
        provs = []
        proveedores = list(self.estado['proveedores'])
        # bases de precios globales (Junta...): proveedor de referencia presente en TODAS las obras
        from . import bases as BASES
        en_obra = {o['huella'] for p in proveedores for o in p['ofertas']}
        for b in BASES.listar():
            if b['huella'] in en_obra:
                continue                                    # ya subida a mano en esta obra
            try:
                from .lectores import base_precios
                doc_b = self._leer(b['ruta'], base_precios.leer, progreso)
            except Exception as e:                          # una base rota no impide analizar la obra
                avisar('No se pudo leer la base de precios %s: %s' % (b['archivo'], e))
                continue
            nombre_b = doc_b.proveedor or os.path.splitext(b['archivo'])[0]
            if any(p['nombre'].lower() == nombre_b.lower() for p in proveedores):
                continue
            proveedores.append({'nombre': nombre_b, 'global': True, 'ofertas': [
                {'proveedor': nombre_b, 'archivo': b['ruta'], 'huella': b['huella'], 'anadida': None,
                 'usuario': 'base de precios (todas las obras)'}]})
        for p in proveedores:
            avisar('Casando la oferta de %s con el presupuesto…' % p['nombre'])
            docs, lineas = [], []
            for of in p['ofertas']:
                doc = self._leer(os.path.join(self.carpeta, of['archivo']), leer_oferta, progreso)
                varias = len(p['ofertas']) > 1
                for k, l in enumerate(M.lineas_oferta(doc, p['nombre'])):
                    l.i = len(lineas)
                    l.uid = '%s:%d' % (of['huella'][:10], k)
                    l.huella = of['huella']
                    if varias:
                        l.seccion = '%s · %s' % (os.path.splitext(os.path.basename(of['archivo']))[0][:24], l.seccion)
                    lineas.append(l)
                docs.append({'doc': doc, 'archivo': of['archivo'], 'huella': of['huella'], 'anadida': of['anadida'],
                             'usuario': of['usuario']})
            manuales = {}
            uid_a_i = {l.uid: l.i for l in lineas}
            for k, v in self.estado['manuales'].get(p['nombre'], {}).items():
                li = uid_a_i.get(k)
                if li is None and k.isdigit() and int(k) < len(lineas):    # correcciones de versiones anteriores
                    li = int(k)
                if li is None:
                    continue
                if v is None:
                    manuales[li] = None
                else:
                    mid = por_cod.get(v.get('cod')) if v.get('cod') else None
                    manuales[li] = mid or v.get('id')
            # petición de oferta devuelta rellena: cada fila lleva el código de su material -> casado seguro
            for l in lineas:
                cod = (l.partida.codigo or '')
                if cod.startswith(PREFIJO_PETICION) and l.i not in manuales:
                    mid = por_cod.get(cod[len(PREFIJO_PETICION):])
                    if mid:
                        manuales[l.i] = mid
            catalogo = all(d['doc'].tipo == 'base_precios' for d in docs)
            if catalogo:
                asign, sin, puntos = M.emparejar_catalogo(materiales, lineas, manuales, conocidas)
            else:
                asign, sin, puntos = M.emparejar(materiales, lineas, manuales, conocidas)
            ofertas = M.construir_ofertas(materiales, asign)
            provs.append({'nombre': p['nombre'], 'doc': docs[0]['doc'], 'docs': docs, 'lineas': lineas, 'asign': asign,
                          'sin': sin, 'ofertas': ofertas, 'puntos': puntos, 'archivo': docs[0]['archivo'],
                          'huella': docs[0]['huella'], 'catalogo': catalogo, 'global': bool(p.get('global')),
                          'referencia': all((d['doc'].condiciones or {}).get('referencia') for d in docs)})
        res = Resultado(self, cli, materiales, provs)
        res.comparar_referencias()
        if bbdd:
            avisar('Guardando precios en la base de datos y buscando precios históricos…')
            por_id = {m.id: m for m in materiales}
            bbdd.sincronizar_obra(self.nombre, [p['nombre'] for p in provs if not p['global']],
                                  {d['huella'] for p in provs if not p['global'] for d in p['docs']})
            for pv in provs:
                if pv['global']:                            # una sola vez en la BBDD, no en cada obra
                    for d in pv['docs']:
                        if not bbdd.tiene_oferta(BASES.OBRA_BBDD, pv['nombre'], d['huella']):
                            bbdd.registrar_oferta(BASES.OBRA_BBDD, pv['nombre'], os.path.basename(d['archivo']),
                                                  d['huella'], d['doc'], [l for l in pv['lineas']
                                                                          if l.huella == d['huella']], {})
                    continue
                asignado = {a.linea.i: por_id[a.material_id] for a in pv['asign'] if a.tipo == 'principal'}
                for d in pv['docs']:
                    bbdd.registrar_oferta(self.nombre, pv['nombre'], os.path.basename(d['archivo']), d['huella'], d['doc'],
                                          [l for l in pv['lineas'] if l.huella == d['huella']], asignado)
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
        self.avisos_referencia = {}   # material_id -> [texto]  base de precios más barata que los distribuidores

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

    @property
    def distribuidores(self):
        """Proveedores a los que se puede comprar (sin las bases de precios de referencia, p. ej. la de la Junta)."""
        return [pv for pv in self.proveedores if not pv.get('referencia')]

    def comparar_referencias(self):
        """Base de precios (Junta...) MÁS BARATA que todos los distribuidores, o con precio para algo que nadie oferta:
        se avisa como cuando la BBDD tiene registrado un precio mejor."""
        self.avisos_referencia = {}
        for ref in [pv for pv in self.proveedores if pv.get('referencia')]:
            for mid, o in ref['ofertas'].items():
                m = next((x for x in self.materiales if x.id == mid), None)
                if not m or not o.precio:
                    continue
                nom, mejor = self.mas_barato(m)
                if mejor is None:
                    t = ('%s tiene este material a %.2f € ("%s"); en esta obra ningún distribuidor lo ha ofertado.'
                         % (ref['nombre'], o.precio, o.principal.partida.descripcion[:60]))
                elif o.precio < mejor * 0.995:
                    t = ('%s tiene este material a %.2f € ("%s"): MÁS BARATO que el mejor precio de los distribuidores '
                         '(%s, %.2f €, un %.0f%% más caro).' % (ref['nombre'], o.precio, o.principal.partida.descripcion[:60],
                                                                 nom, mejor, (mejor / o.precio - 1) * 100))
                else:
                    continue
                o.alertas.append(('media', t))
                self.avisos_referencia.setdefault(mid, []).append(t)

    def adjudicacion(self):
        """{distribuidor: [material_id...]}: cada material al distribuidor con el unitario más bajo (empate: el primero)."""
        out = {pv['nombre']: [] for pv in self.distribuidores}
        for m in self.materiales:
            mejores = [(pv['ofertas'][m.id].precio, k, pv['nombre']) for k, pv in enumerate(self.distribuidores)
                       if m.id in pv['ofertas'] and pv['ofertas'][m.id].precio]
            if mejores:
                out[min(mejores)[2]].append(m.id)
        return out

    def totales_proveedores(self):
        """Total de cada distribuidor comprándole TODO lo que oferta (con las cantidades del proyecto, para comparar
        igual a todos). El 'más barato en total' es el de menor total entre los que ofertan más materiales: si no, uno que
        oferta la mitad de las partidas parecería siempre el más barato.
        -> [{proveedor, total, materiales, total_documento, ganador}] ordenado por total"""
        filas = []
        for pv in self.distribuidores:
            con = [o for o in pv['ofertas'].values() if o.precio is not None]
            filas.append({'proveedor': pv['nombre'], 'materiales': len(con),
                          'total': round(sum(o.importe or 0 for o in con), 2),
                          'total_documento': round(sum(d['doc'].total_declarado or 0 for d in pv['docs']), 2) or None,
                          'ganador': False})
        if filas:
            maximo = max(f['materiales'] for f in filas)
            completos = [f for f in filas if f['materiales'] == maximo and f['total'] > 0]
            if completos:
                min(completos, key=lambda f: f['total'])['ganador'] = True
        return sorted(filas, key=lambda f: (not f['ganador'], f['total']))

    def reparto(self):
        """Comprando cada material al distribuidor más barato: cuánto se le adjudica a cada uno.
        -> (filas [{proveedor, materiales, importe, pct, total_propio, ofertados}], total, sin_oferta)"""
        por = {pv['nombre']: {'proveedor': pv['nombre'], 'materiales': 0, 'importe': 0.0,
                              'ofertados': sum(1 for o in pv['ofertas'].values() if o.precio is not None),
                              'total_propio': round(sum(o.importe or 0 for o in pv['ofertas'].values()), 2)}
               for pv in self.distribuidores}
        adj = self.adjudicacion()
        mats = {m.id: m for m in self.materiales}
        for pv in self.distribuidores:
            for mid in adj[pv['nombre']]:
                o = pv['ofertas'][mid]
                por[pv['nombre']]['materiales'] += 1
                por[pv['nombre']]['importe'] += o.importe if o.importe is not None else o.precio * (mats[mid].cantidad or 0)
        sin = len(self.materiales) - sum(len(v) for v in adj.values())
        total = round(sum(x['importe'] for x in por.values()), 2)
        filas = sorted(por.values(), key=lambda x: -x['importe'])
        for x in filas:
            x['importe'] = round(x['importe'], 2)
            x['pct'] = x['importe'] / total if total else 0.0
        return filas, total, sin

    def mas_barato(self, m, solo_principal=False):
        """(proveedor, precio) más barato entre las ofertas de esta obra para el material m.
        solo_principal: precio de la línea principal (sin accesorios ni cánones), para comparar con la BBDD."""
        def precio(o):
            return o.principal.partida.precio if solo_principal else o.precio
        mejores = [(precio(pv['ofertas'][m.id]), pv['nombre']) for pv in self.distribuidores
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
            refs = {pv['nombre'].lower() for pv in self.proveedores if pv.get('referencia')}
            # las bases de precios de la obra ya tienen su columna y su aviso: no se repiten como "histórico"
            filas = [f for f in filas if f['proveedor'].lower() not in refs]
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
