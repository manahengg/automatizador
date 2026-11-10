"""Base de datos de PRECIOS (SQLite, un único fichero: datos/precios.db).

Guarda cada línea de cada oferta de proveedor que pasa por la app, para poder decir en obras futuras:
    "este proveedor, para este material, lo tiene a este precio"  y  "ojo: el proveedor X (que no está en esta obra)
    tiene registrado este material más barato".

Cómo se reconoce "el mismo material" entre ofertas/obras distintas (de más a menos fiable):
  1. mismo proveedor y mismo código de artículo;
  2. misma CLAVE TÉCNICA (electrico.clave_material: 'cable|1x35|RZ1-K', 'tubo|20|corrugado', 'downlight|20W'...);
  3. misma descripción de material del cliente a la que se casó en otra obra.
"""
import datetime
import os
import re
import sqlite3

from . import electrico as E

ESQUEMA = """
CREATE TABLE IF NOT EXISTS proveedor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS obra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    creada TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS oferta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id INTEGER NOT NULL REFERENCES obra(id),
    proveedor_id INTEGER NOT NULL REFERENCES proveedor(id),
    archivo TEXT NOT NULL,
    huella TEXT NOT NULL,
    fecha_doc TEXT,
    validez TEXT,
    importada TEXT NOT NULL,
    total_doc REAL,
    UNIQUE (obra_id, proveedor_id, huella)
);
CREATE TABLE IF NOT EXISTS precio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oferta_id INTEGER NOT NULL REFERENCES oferta(id) ON DELETE CASCADE,
    proveedor_id INTEGER NOT NULL REFERENCES proveedor(id),
    obra_id INTEGER NOT NULL REFERENCES obra(id),
    linea INTEGER,
    codigo TEXT,
    codigo_norm TEXT,
    descripcion TEXT NOT NULL,
    desc_norm TEXT,
    familia TEXT,
    clave_material TEXT,
    cantidad REAL,
    precio_lista REAL,
    dto REAL,
    precio_neto REAL,
    opcional INTEGER DEFAULT 0,
    fecha TEXT,
    asignado_codigo TEXT,          -- código de la partida del cliente a la que se casó
    asignado_desc TEXT             -- descripción normalizada del material del cliente
);
CREATE INDEX IF NOT EXISTS ix_precio_clave ON precio(clave_material);
CREATE INDEX IF NOT EXISTS ix_precio_cod ON precio(proveedor_id, codigo_norm);
CREATE INDEX IF NOT EXISTS ix_precio_asig ON precio(asignado_desc);
CREATE TABLE IF NOT EXISTS caso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creado TEXT NOT NULL,
    obra TEXT,
    proveedor TEXT,                 -- vacío = aplica a cualquier proveedor
    familia TEXT,
    clave_material TEXT,
    atributos TEXT,                 -- JSON con las características del material (kwp, sección, W...)
    texto_material TEXT,            -- descripción normalizada del material del cliente
    oferta TEXT,                    -- lo que ofertó el proveedor (descripción)
    observacion TEXT NOT NULL,      -- la corrección/criterio de la persona
    cantidad_correcta REAL,
    activo INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS equivalencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id INTEGER NOT NULL REFERENCES proveedor(id),
    clave_linea TEXT NOT NULL,      -- código normalizado o inicio de la descripción de la línea del proveedor
    destino TEXT NOT NULL,          -- clave de material, 'cli:<código cliente>' o 'desc:<descripción cliente>'
    creada TEXT NOT NULL,
    UNIQUE (proveedor_id, clave_linea, destino)
);
"""


def ahora():
    return datetime.datetime.now().isoformat(timespec='seconds')


def cod(x):
    return re.sub(r'[^A-Z0-9]', '', str(x or '').upper())


def dnorm(x):
    return E.norm(x)[:60]


def clave_asignado(m):
    """Identifica el material del cliente al que se casó una línea (sirve entre obras distintas)."""
    return dnorm(m.descripcion if m.n_mats > 1 else (m.partida.resumen or m.descripcion))


def fecha_iso(f):
    """'26/06/2025' -> '2025-06-26' (para ordenar). Si no se entiende, se deja tal cual."""
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', f or '')
    return '%s-%02d-%02d' % (m.group(3), int(m.group(2)), int(m.group(1))) if m else (f or None)


class BBDD:
    def __init__(self, ruta):
        os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        self.ruta = ruta
        self.c = sqlite3.connect(ruta, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.c.execute('PRAGMA foreign_keys = ON')
        self.c.create_function('REGEXP', 2, lambda patron, valor: bool(valor and re.search(patron, valor)))
        self.c.executescript(ESQUEMA)

    def cerrar(self):
        self.c.close()

    # ------------------------------------------------------------------------------------------ altas
    def _id(self, tabla, nombre, extra=None):
        r = self.c.execute('SELECT id FROM %s WHERE nombre = ?' % tabla, (nombre,)).fetchone()
        if r:
            return r['id']
        if tabla == 'obra':
            cur = self.c.execute('INSERT INTO obra (nombre, creada) VALUES (?, ?)', (nombre, ahora()))
        else:
            cur = self.c.execute('INSERT INTO proveedor (nombre) VALUES (?)', (nombre,))
        return cur.lastrowid

    def proveedor_id(self, nombre):
        return self._id('proveedor', nombre.strip())

    def registrar_oferta(self, obra, proveedor, archivo, huella, doc, lineas, asignado=None):
        """Guarda (o sustituye) todas las líneas de una oferta.

        lineas: [emparejar.Linea]; asignado: {nº línea: Material} para recordar a qué se casó cada línea."""
        asignado = asignado or {}
        obra_id = self._id('obra', obra)
        prov_id = self.proveedor_id(proveedor)
        self.c.execute('DELETE FROM oferta WHERE obra_id=? AND proveedor_id=? AND huella=?', (obra_id, prov_id, huella))
        cur = self.c.execute(
            'INSERT INTO oferta (obra_id, proveedor_id, archivo, huella, fecha_doc, validez, importada, total_doc) '
            'VALUES (?,?,?,?,?,?,?,?)', (obra_id, prov_id, archivo, huella, doc.fecha, doc.validez, ahora(),
                                         doc.total_declarado))
        of_id = cur.lastrowid
        fecha = fecha_iso(doc.fecha) or ahora()[:10]
        filas = []
        for l in lineas:
            p = l.partida
            if p.precio is None or l.es_canon:
                continue
            m = asignado.get(l.i)
            filas.append((of_id, prov_id, obra_id, l.i, p.referencia, cod(p.referencia), p.descripcion,
                          dnorm(p.descripcion), l.atributos.get('familia'), E.clave_material(l.atributos),
                          p.cantidad, p.precio_lista, p.dto_pct, round(p.precio, 4), int(bool(p.opcional)), fecha,
                          m.codigo if m else None, clave_asignado(m) if m else None))
        self.c.executemany(
            'INSERT INTO precio (oferta_id, proveedor_id, obra_id, linea, codigo, codigo_norm, descripcion, desc_norm, '
            'familia, clave_material, cantidad, precio_lista, dto, precio_neto, opcional, fecha, asignado_codigo, '
            'asignado_desc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', filas)
        self.c.commit()
        return len(filas)

    def quitar_oferta(self, obra, proveedor):
        r = self.c.execute('SELECT o.id FROM oferta o JOIN obra b ON b.id=o.obra_id JOIN proveedor p ON p.id=o.proveedor_id '
                           'WHERE b.nombre=? AND p.nombre=?', (obra, proveedor)).fetchall()
        for x in r:
            self.c.execute('DELETE FROM precio WHERE oferta_id=?', (x['id'],))
            self.c.execute('DELETE FROM oferta WHERE id=?', (x['id'],))
        self.c.commit()

    # ------------------------------------------------------------------------------------------ aprendizaje
    def aprender(self, proveedor, linea, material):
        """La persona ha casado a mano `linea` con `material`: se recuerda para las próximas ofertas."""
        prov_id = self.proveedor_id(proveedor)
        clave = cod(linea.referencia) or dnorm(linea.partida.descripcion)
        destinos = ['desc:' + dnorm(material.partida.resumen or material.descripcion)]
        if material.codigo:
            destinos.append('cli:' + cod(material.codigo))
        if material.clave:
            destinos.append(material.clave)
        for d in destinos:
            self.c.execute('INSERT OR IGNORE INTO equivalencia (proveedor_id, clave_linea, destino, creada) VALUES (?,?,?,?)',
                           (prov_id, clave, d, ahora()))
        self.c.commit()

    def conocidas(self):
        """{(proveedor en minúsculas, clave de línea): destino} para emparejar.puntuar."""
        out = {}
        for r in self.c.execute('SELECT p.nombre, e.clave_linea, e.destino FROM equivalencia e '
                                'JOIN proveedor p ON p.id=e.proveedor_id ORDER BY e.id'):
            out[(r['nombre'].lower(), r['clave_linea'])] = r['destino']
        return out

    # ------------------------------------------------------------------------------------------ consultas
    _SELECT = ('SELECT pr.*, p.nombre AS proveedor, b.nombre AS obra FROM precio pr '
               'JOIN proveedor p ON p.id = pr.proveedor_id JOIN obra b ON b.id = pr.obra_id ')

    def precios_material(self, material, codigos_lineas=(), excluir_obra=None):
        """Todos los precios registrados de un material del cliente (de cualquier proveedor y obra).

        Devuelve lista de dict ordenada por precio, con 'motivo' (por qué se considera el mismo material)."""
        res = {}

        def add(rows, motivo):
            for r in rows:
                if excluir_obra and r['obra'] == excluir_obra:
                    continue
                if r['opcional']:
                    continue
                d = dict(r)
                d['motivo'] = motivo
                res.setdefault(d['id'], d)
        clave = material.clave
        if clave and len(clave.split('|')) >= 2:
            add(self.c.execute(self._SELECT + 'WHERE pr.clave_material = ?', (clave,)).fetchall(),
                'misma característica técnica (%s)' % clave)
        ad = clave_asignado(material)
        if ad:
            add(self.c.execute(self._SELECT + 'WHERE pr.asignado_desc = ?', (ad,)).fetchall(),
                'casado con la misma partida en otra obra')
        if material.codigo and len(cod(material.codigo)) >= 5 and material.n_mats == 1:
            add(self.c.execute(self._SELECT + 'WHERE pr.codigo_norm = ?', (cod(material.codigo),)).fetchall(),
                'mismo código de artículo')
        for pid, cn in codigos_lineas:
            if cn and len(cn) >= 4:
                add(self.c.execute(self._SELECT + 'WHERE pr.proveedor_id = ? AND pr.codigo_norm = ?',
                                   (pid, cn)).fetchall(), 'mismo código de artículo del proveedor')
        return sorted(res.values(), key=lambda d: (d['precio_neto'], d['fecha'] or ''))

    def mejor_por_proveedor(self, filas):
        """De una lista de precios, el último precio registrado de cada proveedor (el más reciente; a igual
        fecha el más barato)."""
        out = {}
        for f in sorted(filas, key=lambda d: (d['fecha'] or '', -d['precio_neto'])):
            out[f['proveedor']] = f
        return sorted(out.values(), key=lambda d: d['precio_neto'])

    def buscar(self, texto, limite=300):
        """Búsqueda libre (para la pantalla de la BBDD): todas las palabras deben aparecer."""
        palabras = [w for w in E.norm(texto).split() if w]
        if not palabras:
            return []
        conds, args = [], []
        for w in palabras:
            if re.fullmatch(r'[\d.,x]+', w):        # números como palabra completa: '20' no encuentra '2000'
                pat = r'(^|[^\d.,])%s([^\d.,]|$)' % re.escape(w)
                conds.append('(pr.desc_norm REGEXP ? OR pr.clave_material REGEXP ?)')
                args += [pat, pat]
            else:
                conds.append('(pr.desc_norm LIKE ? OR pr.codigo_norm LIKE ? OR pr.clave_material LIKE ?)')
                args += ['%' + w + '%', '%' + cod(w) + '%', '%' + w + '%']
        cond = ' AND '.join(conds)
        rows = self.c.execute(self._SELECT + 'WHERE ' + cond + ' ORDER BY pr.clave_material, pr.precio_neto LIMIT ?',
                              args + [limite]).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------------------------------ casos aprendidos
    def anotar_caso(self, obra, material, observacion, proveedor=None, oferta=None, cantidad_correcta=None):
        """Guarda una corrección/criterio de la persona para aplicarlo en casos parecidos del futuro."""
        import json
        at = {k: (sorted(v) if isinstance(v, set) else v) for k, v in material.atributos.items()
              if k in ('familia', 'seccion', 'kwp', 'wp', 'potencia_w', 'lumenes', 'diametro', 'tipo_cable', 'fases',
                       'amperios', 'optica', 'temp_color')}
        self.c.execute('INSERT INTO caso (creado, obra, proveedor, familia, clave_material, atributos, texto_material, '
                       'oferta, observacion, cantidad_correcta) VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (ahora(), obra, proveedor or None, material.atributos.get('familia'), material.clave,
                        json.dumps(at, ensure_ascii=False), E.norm(material.partida.resumen or material.descripcion),
                        oferta, observacion.strip(), cantidad_correcta))
        self.c.commit()

    def casos(self):
        return [dict(r) for r in self.c.execute('SELECT * FROM caso WHERE activo=1 ORDER BY id DESC')]

    def borrar_caso(self, ident):
        self.c.execute('UPDATE caso SET activo=0 WHERE id=?', (ident,))
        self.c.commit()

    def casos_parecidos(self, material, todos=None):
        """Casos anteriores que se parecen a este material. Devuelve [(parecido 0..1, caso)]."""
        import json
        todos = self.casos() if todos is None else todos
        at = material.atributos
        fam = at.get('familia')
        tm = set(E.norm(material.partida.resumen or material.descripcion).split())
        out = []
        for c in todos:
            if not fam or c['familia'] != fam:
                continue
            ca = json.loads(c['atributos'] or '{}')
            p = 0.4
            if c['clave_material'] and c['clave_material'] == material.clave:
                p += 0.3
            for k in ('kwp', 'seccion', 'diametro', 'wp'):
                x, y = at.get(k), ca.get(k)
                if x and y:
                    p += 0.25 if abs(x - y) <= 0.25 * max(x, y) else -0.3
            tc = set((c['texto_material'] or '').split())
            if tm and tc:
                p += 0.3 * len(tm & tc) / max(1, len(tm | tc))
            if p >= 0.55:
                out.append((min(1.0, p), c))
        return sorted(out, key=lambda t: -t[0])

    def modulos_fv(self):
        """Módulos fotovoltaicos con precio registrado (último precio de cada proveedor y potencia)."""
        out = {}
        for r in self.c.execute(self._SELECT + "WHERE pr.familia = 'modulo_fv' ORDER BY pr.fecha"):
            m = re.search(r'(\d{3})\s*w', E.norm(r['descripcion']))
            if not m:
                continue
            wp = int(m.group(1))
            if 200 <= wp <= 900:
                out[(r['proveedor'], wp)] = dict(r, wp=wp)
        return list(out.values())

    def resumen(self):
        return {
            'proveedores': self.c.execute('SELECT COUNT(*) FROM proveedor').fetchone()[0],
            'obras': self.c.execute('SELECT COUNT(*) FROM obra').fetchone()[0],
            'precios': self.c.execute('SELECT COUNT(*) FROM precio').fetchone()[0],
            'equivalencias': self.c.execute('SELECT COUNT(*) FROM equivalencia').fetchone()[0],
            'casos': self.c.execute('SELECT COUNT(*) FROM caso WHERE activo=1').fetchone()[0],
        }
