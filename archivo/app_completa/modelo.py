"""Formato interno único. Todo documento (PDF, Excel, BC3) se convierte a esto antes de hacer nada más.

Regla de importes (la misma que aplica m4PRO): el precio se redondea a 2 decimales y
importe = round(cantidad * round(precio, 2), 2).
"""
from dataclasses import dataclass, field
from typing import List, Optional, Union
import datetime
from decimal import Decimal, ROUND_HALF_UP
from .texto import reparar_mojibake


def r2(x):
    """Redondeo a 2 decimales 'medio hacia arriba' (770,795 -> 770,80), como en una factura."""
    return float(Decimal(repr(float(x))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


@dataclass
class Partida:
    descripcion: str
    cantidad: float
    precio: Optional[float]            # precio unitario NETO (ya con descuento); None = la oferta no trae precio
    unidad: str = 'ud'
    codigo: Optional[str] = None       # código del origen, si lo tiene
    precio_lista: Optional[float] = None
    dto_pct: Optional[float] = None
    importe_declarado: Optional[float] = None   # lo que imprime el documento, para contrastar
    notas: List[str] = field(default_factory=list)
    referencia: Optional[str] = None   # referencia/código de producto del proveedor, si la trae (ayuda a emparejar)
    resumen: str = ''                  # título corto de la partida (presupuestos de cliente)
    marca: Optional[str] = None        # fabricante, si la oferta lo indica en columna aparte
    opcional: bool = False             # línea marcada OPCIONAL: se registra el precio pero no suma
    canon_de: Optional['Partida'] = field(default=None, repr=False, compare=False)   # canon RAEE: línea a la que acompaña

    def __post_init__(self):
        self.descripcion = reparar_mojibake(self.descripcion) or ''
        self.unidad = reparar_mojibake(self.unidad) or 'ud'
        self.codigo = reparar_mojibake(self.codigo) if self.codigo else self.codigo
        self.referencia = reparar_mojibake(self.referencia) if self.referencia else self.referencia
        self.resumen = reparar_mojibake(self.resumen) or ''
        self.notas = [reparar_mojibake(x) for x in (self.notas or [])]

    @property
    def importe(self) -> float:
        if self.precio is None:
            return 0.0
        return round(self.cantidad * r2(self.precio), 2)

    @property
    def importe_exacto(self) -> float:
        """Importe sin redondear el precio: lo que el proveedor realmente cobra."""
        if self.precio is None:
            return 0.0
        return round(self.cantidad * self.precio, 2)


@dataclass
class Capitulo:
    titulo: str
    codigo: Optional[str] = None
    hijos: List[Union['Capitulo', Partida]] = field(default_factory=list)   # en el orden del origen

    def __post_init__(self):
        self.titulo = reparar_mojibake(self.titulo) or ''
        self.codigo = reparar_mojibake(self.codigo) if self.codigo else self.codigo

    @property
    def importe(self) -> float:
        return round(sum(h.importe for h in self.hijos), 2)

    def partidas(self):
        for h in self.hijos:
            if isinstance(h, Capitulo):
                yield from h.partidas()
            else:
                yield h


@dataclass
class Aviso:
    nivel: str      # 'info' | 'aviso' | 'revisar'  ('revisar' = una persona debe mirarlo antes de seguir)
    texto: str


@dataclass
class Documento:
    tipo: str                           # 'oferta_proveedor' | 'obra' | 'certificacion' | 'presupuesto'
    origen: str
    nombre: str = ''
    proveedor: Optional[str] = None
    referencia: Optional[str] = None
    fecha: Optional[str] = None
    validez: Optional[str] = None
    condiciones: dict = field(default_factory=dict)
    capitulos: List[Capitulo] = field(default_factory=list)
    total_declarado: Optional[float] = None
    avisos: List[Aviso] = field(default_factory=list)

    def __post_init__(self):
        self.nombre = reparar_mojibake(self.nombre) or ''
        self.proveedor = reparar_mojibake(self.proveedor) if self.proveedor else self.proveedor
        self.referencia = reparar_mojibake(self.referencia) if self.referencia else self.referencia

    @property
    def importe(self) -> float:
        return round(sum(c.importe for c in self.capitulos), 2)

    def partidas(self):
        for c in self.capitulos:
            yield from c.partidas()

    def avisar(self, nivel, texto):
        self.avisos.append(Aviso(nivel, texto))

    def validar(self, hoy: Optional[datetime.date] = None):
        """Comprobaciones comunes a todos los formatos."""
        hoy = hoy or datetime.date.today()
        sin_precio = [p for p in self.partidas() if p.precio is None]
        if sin_precio:
            self.avisar('revisar', '%d líneas sin precio en el documento (se importan a 0,00 €): %s' % (
                len(sin_precio), '; '.join(sorted({p.descripcion[:40] for p in sin_precio}))))
        if self.total_declarado is not None:
            dif = round(self.importe - self.total_declarado, 2)
            exacto = round(sum(p.importe_exacto for p in self.partidas()), 2)
            if abs(dif) <= 0.01:
                self.avisar('info', 'La suma de líneas coincide con el total del documento (%.2f €).' % self.total_declarado)
            elif abs(exacto - self.total_declarado) <= 0.05:
                self.avisar('aviso', 'Diferencia de %.2f € solo por el redondeo de precios a 2 decimales '
                                     '(sin redondear coincide con el documento).' % dif)
            else:
                self.avisar('revisar', 'La suma de líneas (%.2f €; %.2f € sin redondear precios) NO coincide con el total '
                                       'del documento (%.2f €): diferencia de %.2f €.' % (
                                           self.importe, exacto, self.total_declarado, round(exacto - self.total_declarado, 2)))
        for p in self.partidas():
            if p.importe_declarado is not None and abs(round(p.importe_exacto - p.importe_declarado, 2)) > 0.011:
                self.avisar('revisar', 'El importe calculado de "%s" (%.2f €) no coincide con el impreso (%.2f €).' % (
                    p.descripcion[:40], p.importe_exacto, p.importe_declarado))
        if self.validez:
            try:
                v = datetime.datetime.strptime(self.validez, '%d/%m/%Y').date()
                if v < hoy:
                    self.avisar('revisar', 'La oferta caducó el %s: pedir al proveedor que la renueve.' % self.validez)
            except ValueError:
                pass


# ------------------------------------------------------------------------------------- JSON (caché compartida)
_CAMPOS_PARTIDA = ('descripcion', 'cantidad', 'precio', 'unidad', 'codigo', 'precio_lista', 'dto_pct',
                   'importe_declarado', 'notas', 'referencia', 'resumen', 'marca', 'opcional')


def doc_a_dict(doc):
    """Documento -> dict serializable en JSON (sin pickle: seguro para una carpeta compartida)."""
    indices = {}

    def cap(c):
        hijos = []
        for h in c.hijos:
            if isinstance(h, Capitulo):
                hijos.append({'cap': cap(h)})
            else:
                d = {k: getattr(h, k) for k in _CAMPOS_PARTIDA}
                d['_n'] = indices.setdefault(id(h), len(indices))
                d['_canon'] = indices.get(id(h.canon_de)) if h.canon_de is not None else None
                hijos.append({'p': d})
        return {'titulo': c.titulo, 'codigo': c.codigo, 'hijos': hijos}
    return {'tipo': doc.tipo, 'origen': doc.origen, 'nombre': doc.nombre, 'proveedor': doc.proveedor,
            'referencia': doc.referencia, 'fecha': doc.fecha, 'validez': doc.validez, 'condiciones': doc.condiciones,
            'total_declarado': doc.total_declarado, 'avisos': [[a.nivel, a.texto] for a in doc.avisos],
            'capitulos': [cap(c) for c in doc.capitulos]}


def doc_de_dict(d):
    por_n, canones = {}, []

    def cap(x):
        c = Capitulo(titulo=x['titulo'], codigo=x['codigo'])
        for h in x['hijos']:
            if 'cap' in h:
                c.hijos.append(cap(h['cap']))
            else:
                p = h['p']
                part = Partida(**{k: p.get(k) for k in _CAMPOS_PARTIDA if k in p})
                part.opcional = bool(p.get('opcional'))
                part.notas = list(p.get('notas') or [])
                por_n[p['_n']] = part
                if p.get('_canon') is not None:
                    canones.append((part, p['_canon']))
                c.hijos.append(part)
        return c
    doc = Documento(tipo=d['tipo'], origen=d['origen'], nombre=d.get('nombre') or '', proveedor=d.get('proveedor'),
                    referencia=d.get('referencia'), fecha=d.get('fecha'), validez=d.get('validez'),
                    condiciones=d.get('condiciones') or {}, total_declarado=d.get('total_declarado'))
    doc.avisos = [Aviso(n, t) for n, t in d.get('avisos') or []]
    doc.capitulos = [cap(c) for c in d['capitulos']]
    for part, n in canones:
        part.canon_de = por_n.get(n)
    return doc
