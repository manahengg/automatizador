/* Rellenador de precios — núcleo (sin interfaz). Funciona en el navegador (window.Rellenador) y en Node (pruebas).

   1) PDF del proveedor -> líneas (por posición) -> artículos: una línea es un artículo si tiene
      cantidad x precio x (1 - dto%) = importe (así se reconocen las columnas sin plantillas por proveedor;
      también los números que el PDF dibuja partidos: "7" + "70,80" = 770,80).
   2) Excel del ERP ("Petición de oferta"): fila de cabeceras con CÓDIGO / DESCRIPCIÓN / CANTIDAD / SU PRECIO.
   3) Emparejar: alineación en orden (las ofertas siguen el orden de la petición) por parecido de texto y cantidad,
      y después lo que quede suelto por mejor parecido.
   4) Escribir: SOLO las celdas de la columna de precio, sustituyendo la celda existente por la misma celda con su
      valor y el mismo estilo (s="..."). Nada más del fichero cambia.
*/
(function (raiz, fabrica) {
  if (typeof module === 'object' && module.exports) module.exports = fabrica();
  else raiz.Rellenador = fabrica();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ------------------------------------------------------------------------------------------ texto y números
  function sinTildes(s) { return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, ''); }
  function norm(s) { return sinTildes(String(s || '')).toLowerCase(); }

  function numero(t) {
    // '3.023,28' '969,0000' '4,00' '36' '70,80€' '1.950' -> número;  si no es un número -> null
    let s = String(t || '').replace(/[€\s]/g, '').replace(/^\((.*)\)$/, '-$1');
    if (!/^-?[\d.,]+%?$/.test(s) || !/\d/.test(s)) return null;
    s = s.replace(/%$/, '');
    if (s.includes(',')) s = s.replace(/\./g, '').replace(',', '.');
    else if (/^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, '');
    else if ((s.match(/\./g) || []).length > 1) return null;
    const v = parseFloat(s);
    return isFinite(v) ? v : null;
  }

  // ------------------------------------------------------------------------------------------ PDF -> líneas
  // items: [{str, x, y, w, h, pagina}] con y creciendo hacia ABAJO
  function lineas(items) {
    const porPag = {};
    for (const it of items) {
      if (!it.str || !it.str.trim()) continue;
      (porPag[it.pagina] = porPag[it.pagina] || []).push(it);
    }
    const out = [];
    for (const p of Object.keys(porPag).map(Number).sort((a, b) => a - b)) {
      const its = porPag[p].sort((a, b) => a.y - b.y || a.x - b.x);
      const alturas = its.map(i => i.h || 8).sort((a, b) => a - b);
      const hMed = alturas[Math.floor(alturas.length / 2)] || 8;
      let actual = null;
      for (const it of its) {
        if (!actual || Math.abs(it.y - actual.y) > hMed * 0.5) {
          actual = { pagina: p, y: it.y, h: hMed, partes: [] };
          out.push(actual);
        }
        actual.partes.push(it);
      }
    }
    for (const l of out) {
      l.partes.sort((a, b) => a.x - b.x);
      l.palabras = [];
      for (const it of l.partes) {                         // cada trozo -> palabras con x aproximada
        const ws = it.str.split(/\s+/).filter(Boolean);
        const total = it.str.length || 1;
        let pos = 0;
        for (const w of ws) {
          const i = it.str.indexOf(w, pos);
          pos = i + w.length;
          l.palabras.push({ t: w, x: it.x + (it.w || 0) * i / total, x1: it.x + (it.w || 0) * pos / total });
        }
      }
      l.texto = l.palabras.map(w => w.t).join(' ');
    }
    return out;
  }

  // ------------------------------------------------------------------------------------------ líneas -> artículos
  const FIN = /^(p[aá]gina\s*\d|suma y sigue|total|base imponible|i\.?v\.?a|precios?:|validez|forma de pago|observaciones|importe total)/i;

  function candidatosNumero(palabras) {
    // números de la línea; también dos trozos seguidos que forman un número partido ("7" + "70,80")
    const nums = [];
    for (let i = 0; i < palabras.length; i++) {
      const v = numero(palabras[i].t);
      if (v === null) continue;
      nums.push({ v, i, j: i, t: palabras[i].t });
      // OCR que pierde la coma: '44999' puede ser 4,4999 / 44,999...  (se prueba solo si hace cuadrar la cuenta)
      if (/^\d{4,7}$/.test(palabras[i].t))
        for (let k = 1; k <= 4; k++) nums.push({ v: v / Math.pow(10, k), i, j: i, t: palabras[i].t, sincoma: true });
      if (i + 1 < palabras.length && /^\d{1,3}$/.test(palabras[i].t)) {
        const sig = palabras[i + 1].t.replace(/€/g, '');
        if (/^\d[\d.]*,\d+$/.test(sig)) {
          const w = numero(palabras[i].t + sig);
          if (w !== null) nums.push({ v: w, i, j: i + 1, t: palabras[i].t + sig, pegado: true });
        }
      }
    }
    return nums;
  }

  function articuloDeLinea(l, tolerancia) {
    tolerancia = tolerancia || 0;                       // 0 = la cuenta debe cuadrar; >0 = escaneos (se marca)
    if (/\b(raee|ecopila|ecotasa|canon)\b/i.test(l.texto)) return null;    // cánones: no son artículos
    const ns = candidatosNumero(l.palabras);
    if (ns.length < 3) return null;
    const ultimos = ns.filter(n => n.j >= ns[ns.length - 1].j - 1);       // el importe es de los últimos
    let mejor = null;
    for (const imp of ultimos) {
      if (imp.v <= 0) continue;
      for (const q of ns) {
        if (q.j >= imp.i || q.v <= 0 || q.v > 1e6) continue;
        for (const p of ns) {
          if (p.i <= q.j || p.j >= imp.i || p.v <= 0) continue;
          const dtos = [null].concat(ns.filter(d => d.i > p.j && d.j < imp.i && d.v > 0 && d.v < 100));
          for (const d of dtos) {
            const calc = q.v * p.v * (1 - (d ? d.v : 0) / 100);
            const err = Math.abs(calc - imp.v);
            if (err <= Math.max(0.03, imp.v * Math.max(0.004, tolerancia))) {
              const c = { q, p, d, imp, err: err / imp.v, aprox: err > Math.max(0.03, imp.v * 0.004),
                          pegados: [q, p, d, imp].filter(x => x && (x.pegado || x.sincoma)).length + (q.sincoma || imp.sincoma ? 5 : 0) };
              // preferir: sin trozos pegados innecesarios, con la cantidad más a la izquierda posible (descripción antes)
              if (!mejor || c.aprox < mejor.aprox || (c.aprox === mejor.aprox && (c.pegados < mejor.pegados ||
                  (c.pegados === mejor.pegados && c.err < mejor.err - 1e-9))))
                mejor = c;
            }
          }
        }
      }
    }
    if (!mejor) return null;
    const usados = new Set();
    for (const x of [mejor.q, mejor.p, mejor.d, mejor.imp]) if (x) for (let k = x.i; k <= x.j; k++) usados.add(k);
    const antes = l.palabras.filter((w, k) => k < mejor.q.i && !usados.has(k)).map(w => w.t);
    const despues = l.palabras.filter((w, k) => k > mejor.imp.j && !usados.has(k)).map(w => w.t)
      .filter(t => numero(t) === null && t !== '€');
    return {
      cantidad: mejor.q.v, precioLista: mejor.p.v, dto: mejor.d ? mejor.d.v : 0, importe: mejor.imp.v,
      precio: Math.round(mejor.imp.v / mejor.q.v * 10000) / 10000,
      revisar: mejor.aprox ? 'la cuenta no cuadra del todo (lectura dudosa del escaneo): precio = importe / cantidad' :
        (mejor.p.sincoma ? 'el escaneo no leyó la coma del precio: se ha deducido de la cuenta' : ''),
      texto: antes.join(' ').replace(/\s*€\s*/g, ' ').trim(), extra: despues.join(' ')
    };
  }

  const CABECERA = /\b(codigo|concepto|cantidad|precio|dto|parcial|importe|descripcion|referencia|articulo|unidades|neto|total)\b/g;
  function esCabecera(t) { return (norm(t).match(CABECERA) || []).length >= 3; }

  function articulos(lins, escaneado) {
    lins = lins.filter(l => !esCabecera(l.texto));
    const arts = [];
    lins.forEach((l, k) => {
      const a = articuloDeLinea(l) || (escaneado ? articuloDeLinea(l, 0.4) : null);
      if (a) { a.linea = k; a.pagina = l.pagina; a.y = l.y; a.h = l.h; a.arriba = []; a.abajo = []; arts.push(a); }
    });
    // líneas con descripción y solo una cantidad al final ("BOTONERA ... 2,00"): ofertadas SIN precio
    lins.forEach((l, k) => {
      if (arts.some(a => a.linea === k) || FIN.test(l.texto.trim())) return;
      const ps = l.palabras, ult = ps.length ? ps[ps.length - 1].t : '';
      const letras = ps.filter(w => /[a-záéíóúñ]{3,}/i.test(w.t)).length;
      if (letras >= 3 && /^\d{1,5}(,\d{1,3})?$/.test(ult) && !ps.slice(0, -1).some(w => /^\d[\d.]*,\d+$/.test(w.t))) {
        arts.push({ linea: k, pagina: l.pagina, y: l.y, h: l.h, arriba: [], abajo: [], cantidad: numero(ult), precioLista: null,
                    dto: 0, importe: 0, precio: null, sinPrecio: true, revisar: '',
                    texto: ps.slice(0, -1).map(w => w.t).join(' '), extra: '' });
      }
    });
    arts.sort((a, b) => a.linea - b.linea);
    // líneas sin números: a la descripción del artículo más cercano en la misma página (arriba o abajo)
    lins.forEach((l, k) => {
      if (arts.some(a => a.linea === k) || FIN.test(l.texto.trim()) || l.texto.length < 2) return;
      let mejor = null, dist = Infinity;
      for (const a of arts) {
        if (a.pagina !== l.pagina) continue;
        const dd = Math.abs(a.y - l.y);
        if (dd < dist || (dd === dist && a.y > l.y)) { dist = dd; mejor = a; }
      }
      if (mejor && dist <= mejor.h * 2.6) (l.y < mejor.y ? mejor.arriba : mejor.abajo).push(l.texto);
    });
    return arts.map((a, i) => ({
      n: i + 1, pagina: a.pagina, cantidad: a.cantidad, precioLista: a.precioLista, dto: a.dto, importe: a.importe,
      sinPrecio: !!a.sinPrecio,
      precio: a.precio, revisar: a.revisar || '', descripcion: [...a.arriba, a.texto, ...a.abajo, a.extra].filter(Boolean).join(' ')
        .replace(/\s+/g, ' ').trim()
    }));
  }

  // ------------------------------------------------------------------------------------------ Excel del ERP
  function xmlTexto(s) {
    return s.replace(/<rPh\b[\s\S]*?<\/rPh>/g, '').replace(/<[^>]+>/g, '')
      .replace(/&#x([0-9a-f]+);/gi, (m, h) => String.fromCodePoint(parseInt(h, 16)))
      .replace(/&#(\d+);/g, (m, d) => String.fromCodePoint(+d))
      .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&');
  }
  function colNum(c) { let n = 0; for (const ch of c) n = n * 26 + ch.charCodeAt(0) - 64; return n; }

  async function rutaHoja(zip) {
    const wb = await zip.file('xl/workbook.xml').async('string');
    const rels = await zip.file('xl/_rels/workbook.xml.rels').async('string');
    const m = /<sheet\b[^>]*?r:id="([^"]+)"/.exec(wb);
    const rel = new RegExp('<Relationship\\b[^>]*Id="' + m[1] + '"[^>]*Target="([^"]+)"').exec(rels) ||
      new RegExp('<Relationship\\b[^>]*Target="([^"]+)"[^>]*Id="' + m[1] + '"').exec(rels);
    let t = rel[1].replace(/^\//, '');
    return t.startsWith('xl/') ? t : 'xl/' + t;
  }

  async function leerExcel(zip) {
    const hoja = await rutaHoja(zip);
    const xml = await zip.file(hoja).async('string');
    const ss = zip.file('xl/sharedStrings.xml') ? await zip.file('xl/sharedStrings.xml').async('string') : '';
    const compartidos = [];
    for (const m of ss.matchAll(/<si>([\s\S]*?)<\/si>/g)) compartidos.push(xmlTexto(m[1]));
    const celdas = {};                       // 'B29' -> valor
    for (const m of xml.matchAll(/<c r="([A-Z]+)(\d+)"([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
      const [, col, fila, attrs, cuerpo] = m;
      if (!cuerpo) continue;
      const v = /<v>([\s\S]*?)<\/v>/.exec(cuerpo);
      const is = /<is>([\s\S]*?)<\/is>/.exec(cuerpo);
      let val = null;
      if (/t="s"/.test(attrs) && v) val = compartidos[+v[1]];
      else if (is) val = xmlTexto(is[1]);
      else if (v) val = /t="str"/.test(attrs) ? xmlTexto(v[1]) : +v[1];
      if (val !== null && val !== '') celdas[col + fila] = { col, fila: +fila, val };
    }
    // cabeceras: la fila que tiene PRECIO y CANTIDAD
    const filasCab = {};
    for (const c of Object.values(celdas)) {
      const t = norm(c.val);
      if (typeof c.val === 'string' && /precio|cantidad|codigo|descripcion|^ud\.?$/.test(t))
        (filasCab[c.fila] = filasCab[c.fila] || []).push(c);
    }
    let cab = null;
    for (const f of Object.keys(filasCab).map(Number).sort((a, b) => a - b)) {
      const cs = filasCab[f], tiene = r => cs.find(c => r.test(norm(c.val)));
      if (tiene(/precio/) && tiene(/cantidad/)) {
        cab = { fila: f, precio: tiene(/precio/).col, cantidad: tiene(/cantidad/).col,
                codigo: (tiene(/codigo/) || {}).col, desc: (tiene(/descripcion|concepto|designacion/) || {}).col,
                ud: (tiene(/^ud\.?$|^unidad/) || {}).col };
        break;
      }
    }
    if (!cab) throw new Error('No encuentro en el Excel la fila de cabeceras con "CANTIDAD" y "PRECIO".');
    const porFila = {};
    for (const c of Object.values(celdas)) if (c.fila > cab.fila) (porFila[c.fila] = porFila[c.fila] || {})[c.col] = c.val;
    if (!cab.desc) {                                 // sin cabecera de descripción: la columna con los textos más largos
      const largo = {};
      for (const r of Object.values(porFila)) for (const [col, v] of Object.entries(r))
        if (typeof v === 'string') largo[col] = (largo[col] || 0) + v.length;
      cab.desc = Object.keys(largo).sort((a, b) => largo[b] - largo[a])[0];
    }
    const filas = [];
    for (const f of Object.keys(porFila).map(Number).sort((a, b) => a - b)) {
      const r = porFila[f];
      const desc = cab.desc ? String(r[cab.desc] || '') : '';
      const cant = numero(String(r[cab.cantidad] ?? '').trim()) ?? (typeof r[cab.cantidad] === 'number' ? r[cab.cantidad] : null);
      if (!desc.trim() || cant === null) continue;
      filas.push({ fila: f, codigo: cab.codigo ? String(r[cab.codigo] || '').trim() : '', ud: cab.ud ? String(r[cab.ud] || '').trim() : '',
                   titulo: desc.split('\n')[0].trim(), descripcion: desc.trim(), cantidad: cant,
                   precioActual: r[cab.precio] ?? null });
    }
    return { hoja, cab, filas, xml };
  }

  // ------------------------------------------------------------------------------------------ emparejar
  const VACIAS = new Set(['de', 'la', 'el', 'los', 'las', 'en', 'con', 'para', 'por', 'y', 'o', 'a', 'del', 'al', 'un',
    'una', 'equivalente', 'incluyendo', 'instalada', 'instalado', 'marcado', 'ce', 'segun', 'reglamento', 'ue',
    'replanteo', 'accesorios', 'anclaje', 'cable', 'conexionado', 'totalmente', 'suministro', 'colocacion', 'ud', 'm',
    'erco', 'mm', 'incluso', 'medios', 'auxiliares']);
  function fichas(s) {
    return norm(s).replace(/(\d),(\d)/g, '$1.$2').split(/[^a-z0-9.=]+/).map(w => w.replace(/^[.=]+|[.=]+$/g, ''))
      .filter(w => w && (w.length > 1 || /\d/.test(w)) && !VACIAS.has(w));
  }
  function casa(a, b) { return a === b || (a.length >= 3 && b.length >= 3 && (a.startsWith(b) || b.startsWith(a))); }
  function cobertura(xs, ys) {
    // los números de modelo (100, 1500, 2240...) pesan el doble que las palabras
    if (!xs.length) return 0;
    const peso = x => /^\d{3,}$/.test(x) ? 2 : 1;
    const total = xs.reduce((s, x) => s + peso(x), 0);
    return xs.filter(x => ys.some(y => casa(x, y) || (/^\d{3,}$/.test(x) && y.includes(x)))).reduce((s, x) => s + peso(x), 0) / total;
  }
  function parecido(fila, art) {
    const ft = fichas(fila.titulo), fd = fichas(fila.descripcion.slice(0, 260)), fa = fichas(art.descripcion);
    const texto = 0.55 * cobertura(ft, fa) + 0.45 * cobertura(fa, fd.concat(ft));
    const cod = fila.codigo && norm(art.descripcion).includes(norm(fila.codigo).replace(/\s/g, '')) ? 0.3 : 0;
    const q = fila.cantidad && art.cantidad ? (Math.abs(fila.cantidad - art.cantidad) < 1e-6 ? 1 :
      (Math.abs(fila.cantidad / art.cantidad - 1) < 0.05 ? 0.6 : 0)) : 0;
    return { total: 0.65 * texto + 0.35 * q + cod, texto, cantidad: q };
  }

  function emparejar(filas, arts) {
    const n = filas.length, m = arts.length;
    const S = filas.map(f => arts.map(a => parecido(f, a)));
    // cantidad idéntica: basta menos parecido de texto (proveedores que abrevian: 'DOWNL.KOMBIC 100 RED.1500')
    const ok = (i, j) => (S[i][j].total >= 0.42 && S[i][j].texto >= 0.3) || (S[i][j].cantidad === 1 && S[i][j].texto >= 0.18);
    // alineación en orden (como la petición): máxima suma de parecidos
    const D = Array.from({ length: n + 1 }, () => new Float64Array(m + 1));
    const B = Array.from({ length: n + 1 }, () => new Int8Array(m + 1));
    for (let i = 1; i <= n; i++) for (let j = 1; j <= m; j++) {
      let v = D[i - 1][j], b = 1;
      if (D[i][j - 1] > v) { v = D[i][j - 1]; b = 2; }
      if (ok(i - 1, j - 1) && D[i - 1][j - 1] + S[i - 1][j - 1].total > v) { v = D[i - 1][j - 1] + S[i - 1][j - 1].total; b = 3; }
      D[i][j] = v; B[i][j] = b;
    }
    const res = filas.map(() => null);
    const usados = new Set();
    for (let i = n, j = m; i > 0 && j > 0;) {
      if (B[i][j] === 3) { res[i - 1] = { art: j - 1, ...S[i - 1][j - 1], como: 'orden' }; usados.add(j - 1); i--; j--; }
      else if (B[i][j] === 1) i--; else j--;
    }
    // lo que quede: mejor pareja libre (ofertas con otro orden)
    const libres = [];
    filas.forEach((f, i) => { if (!res[i]) arts.forEach((a, j) => { if (!usados.has(j) && ok(i, j) && S[i][j].total >= 0.5) libres.push([S[i][j].total, i, j]); }); });
    libres.sort((a, b) => b[0] - a[0]);
    for (const [, i, j] of libres) if (!res[i] && !usados.has(j)) { res[i] = { art: j, ...S[i][j], como: 'parecido' }; usados.add(j); }
    return res.map((r, i) => r && Object.assign(r, precioPara(filas[i], arts[r.art]),
      { seguridad: r.texto >= 0.6 && r.cantidad === 1 ? 'alta' : (r.total >= 0.6 ? 'media' : 'baja') }));
  }

  function precioPara(fila, art) {
    // partida en metros y el proveedor vende piezas/rollos de N m ('5MX10', 'L=2M', 'SUPF.2M'): precio por metro
    if (!art || art.precio == null) return { precio: null, nota: '' };
    if (/^\s*m(l|\.)?\s*$/i.test(fila.ud || '')) {
      const m = /(?:^|[^\d.,])(\d{1,2}(?:[.,]\d)?)\s*m(?![m\d])/i.exec(art.descripcion.replace(/l\s*=\s*/gi, ' '));
      const n = m ? parseFloat(m[1].replace(',', '.')) : null;
      if (n && n > 1 && Math.abs(art.cantidad / fila.cantidad - 1) > 0.1) {
        return { precio: Math.round(art.precio / n * 10000) / 10000,
                 nota: 'vendido en piezas de ' + String(n).replace('.', ',') + ' m: ' + art.precio + ' € / ' + n + ' m = precio por metro (' +
                       art.cantidad + ' piezas = ' + (art.cantidad * n) + ' m; se piden ' + fila.cantidad + ')' };
      }
    }
    return { precio: art.precio, nota: '' };
  }

  // ------------------------------------------------------------------------------------------ escribir
  function escribirPrecios(xml, colPrecio, precios) {
    // precios: {fila: número | null}. Cambia SOLO la celda <c r="I29" .../> de cada fila; conserva su estilo s="".
    let n = 0;
    for (const [fila, valor] of Object.entries(precios)) {
      const ref = colPrecio + fila;
      const filaRe = new RegExp('(<row\\b[^>]*\\br="' + fila + '"[^>]*>)([\\s\\S]*?)(</row>)');
      const mf = filaRe.exec(xml);
      if (!mf) continue;
      let cuerpo = mf[2];
      const celdaRe = new RegExp('<c r="' + ref + '"([^>]*?)(?:/>|>[\\s\\S]*?</c>)');
      const mc = celdaRe.exec(cuerpo);
      const estilo = mc ? (/\bs="(\d+)"/.exec(mc[1]) || [])[1] : null;
      const nueva = valor === null || valor === undefined || valor === ''
        ? '<c r="' + ref + '"' + (estilo ? ' s="' + estilo + '"' : '') + '/>'
        : '<c r="' + ref + '"' + (estilo ? ' s="' + estilo + '"' : '') + '><v>' + (+(+valor).toFixed(4)) + '</v></c>';
      if (mc) cuerpo = cuerpo.replace(celdaRe, nueva);
      else {                                         // la celda no existe: se inserta en su sitio
        const cn = colNum(colPrecio);
        let puesto = false;
        cuerpo = cuerpo.replace(/<c r="([A-Z]+)\d+"/g, (all, c) => {
          if (!puesto && colNum(c) > cn) { puesto = true; return nueva + all; }
          return all;
        });
        if (!puesto) cuerpo += nueva;
      }
      xml = xml.replace(filaRe, mf[1] + cuerpo + mf[3]);
      n++;
    }
    return { xml, n };
  }

  return { numero, lineas, articuloDeLinea, articulos, leerExcel, emparejar, parecido, precioPara, escribirPrecios, norm };
});
