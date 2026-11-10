"""Registro de todo lo que hace el programa (SQLite local, un solo fichero: datos/automatizador.db)."""
import json
import os
import sqlite3
import datetime

ESQUEMA = """
CREATE TABLE IF NOT EXISTS documento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creado TEXT NOT NULL,
    archivo TEXT NOT NULL,
    lector TEXT,
    tipo TEXT,
    proveedor TEXT,
    referencia TEXT,
    estado TEXT NOT NULL,            -- listo | revisar | pendiente | error
    total_calculado REAL,
    total_declarado REAL,
    avisos TEXT,                     -- JSON
    carpeta_salida TEXT
);
CREATE TABLE IF NOT EXISTS evento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cuando TEXT NOT NULL,
    documento_id INTEGER,
    que TEXT NOT NULL,
    detalle TEXT
);
"""


def conectar(ruta_db):
    os.makedirs(os.path.dirname(os.path.abspath(ruta_db)), exist_ok=True)
    c = sqlite3.connect(ruta_db)
    c.row_factory = sqlite3.Row
    c.executescript(ESQUEMA)
    return c


def ahora():
    return datetime.datetime.now().isoformat(timespec='seconds')


def registrar(c, archivo, estado, lector=None, doc=None, avisos=None, carpeta_salida=None):
    cur = c.execute(
        'INSERT INTO documento (creado, archivo, lector, tipo, proveedor, referencia, estado, total_calculado, '
        'total_declarado, avisos, carpeta_salida) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (ahora(), archivo, lector, getattr(doc, 'tipo', None), getattr(doc, 'proveedor', None),
         getattr(doc, 'referencia', None), estado, getattr(doc, 'importe', None),
         getattr(doc, 'total_declarado', None), json.dumps(avisos or [], ensure_ascii=False), carpeta_salida))
    c.commit()
    return cur.lastrowid


def evento(c, que, detalle=None, documento_id=None):
    c.execute('INSERT INTO evento (cuando, documento_id, que, detalle) VALUES (?,?,?,?)',
              (ahora(), documento_id, que, detalle))
    c.commit()


def ultimos(c, n=20):
    return c.execute('SELECT * FROM documento ORDER BY id DESC LIMIT ?', (n,)).fetchall()
