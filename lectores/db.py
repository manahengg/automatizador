# app/automatizador/db.py
import os
import sqlite3
from pathlib import Path

def get_app_dir():
    # Ruta segura en AppData\Local\AutomatizadorOfertas
    app_data = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    app_dir = Path(app_data) / "AutomatizadorOfertas"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir

def get_log_path():
    return get_app_dir() / "registro.txt"

def log_message(mensaje: str):
    try:
        log_file = get_log_path()
        with open(log_file, "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}\n")
    except Exception as e:
        print(f"Error al escribir en registro: {e}")

def init_db():
    db_path = get_app_dir() / "datos.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            proyecto TEXT,
            estado TEXT
        )
    ''')
    conn.commit()
    conn.close()