// Pruebas rápidas del núcleo con datos inventados:  node rellenador/pruebas.js
'use strict';
const R = require('./nucleo.js');
let fallos = 0;
function ok(cond, txt) { console.log((cond ? '  OK   ' : '  FALLO ') + txt); if (!cond) fallos++; }
const linea = (texto, y, pagina = 1) => {
  let x = 10; return texto.split(' ').map(w => { const it = {str: w, x, y, w: w.length * 5, h: 8, pagina}; x += w.length * 5 + 4; return it; });
};

ok(R.numero('3.023,28') === 3023.28 && R.numero('969,0000') === 969 && R.numero('1.950') === 1950 && R.numero('70,80€') === 70.8,
   'números en formato español');
// estilo Electrofil: descripción + cantidad, precio, % dto, importe; continuación en la línea siguiente
let items = [].concat(linea('PROYECTOR LIGHTSCAN GRAFITO LED 6,1W 3000K - WIDE 4,00 969,0000 22,00 3.023,28', 100),
                      linea('FLOOD - BLUETOOTH', 110),
                      linea('BOTONERA BLUETOOTH PARA 4 ESCENAS EN COLOR NEGRO 2,00', 130));
let a = R.articulos(R.lineas(items));
ok(a.length === 2 && a[0].precio === 755.82 && /FLOOD - BLUETOOTH/.test(a[0].descripcion), 'Electrofil: precio neto 755,82 y descripción completa');
ok(a[1].sinPrecio && a[1].cantidad === 2, 'línea con solo cantidad = ofertada sin precio');
// estilo Electromercantil: descripción arriba y abajo, precio partido "7" + "70,80 €"
items = [].concat(linea('Proyector Lightscan grafito, LED 6, 1 w', 95), linea('ERCO 35558 4 7 70,80 € 3.083,18 €', 103),
                  linea('3000K, wide flood, Dali-Bluetooth', 111));
a = R.articulos(R.lineas(items));
ok(a.length === 1 && Math.abs(a[0].precio - 770.795) < 1e-6 && /Proyector.*wide flood/.test(a[0].descripcion),
   'Electromercantil: número partido 7 + 70,80 y descripción arriba y abajo');
// escaneo que pierde la coma del precio
a = R.articulos(R.lineas(linea('85 21606 UNEX BANDEJA 66 Cubierta 100 gris 51,00 44999 NETO 229,49', 50)), true);
ok(a.length === 1 && Math.abs(a[0].precio - 4.4998) < 1e-3 && /coma/.test(a[0].revisar), 'escaneo sin coma: se deduce y se marca');
ok(R.articulos(R.lineas(linea('COSTE RAEE (R.D208/2005) 2,00 0,0800 0,16', 60))).length === 0, 'los cánones RAEE no son artículos');
// emparejar en orden con cantidades y piezas en metros
const filas = [{fila: 29, codigo: '1', ud: 'ud', titulo: 'PROYECTOR LIGHTSCAN GRAFITO W. F.', descripcion: 'Proyector Lightscan grafito LED 6,1w 3000k wide flood', cantidad: 4},
               {fila: 30, codigo: '2', ud: 'ml', titulo: 'TIRA FINE LED G2 IP20', descripcion: 'Tira fine led 24V', cantidad: 16},
               {fila: 31, codigo: '3', ud: 'ud', titulo: 'LUMINARIA EMERGENCIA 200 LM', descripcion: 'Emergencia', cantidad: 9}];
const arts = [{descripcion: 'PROYECTOR LIGHTSCAN GRAFITO LED 6,1W 3000K WIDE FLOOD', cantidad: 4, precio: 755.82},
              {descripcion: 'FINE LED G2 IP20 24V 48W 830 5MX10 LAMP', cantidad: 4, precio: 59.83}];
const em = R.emparejar(filas, arts);
ok(em[0] && em[0].art === 0 && em[0].precio === 755.82, 'emparejado por descripción y cantidad');
ok(em[1] && em[1].precio === 11.966 && /piezas de 5 m/.test(em[1].nota), 'rollos de 5 m -> precio por metro, marcado');
ok(em[2] === null, 'lo que no está en el PDF queda sin casar');
// escribir: solo cambia la celda de precio y conserva su estilo
const xml = '<row r="29" spans="2:9"><c r="H29" s="38"><v>4</v></c><c r="I29" s="39"/></row><row r="30"><c r="H30" s="38"><v>16</v></c></row>';
const w = R.escribirPrecios(xml, 'I', {29: 755.82, 30: 11.966});
ok(w.xml === '<row r="29" spans="2:9"><c r="H29" s="38"><v>4</v></c><c r="I29" s="39"><v>755.82</v></c></row>' +
              '<row r="30"><c r="H30" s="38"><v>16</v></c><c r="I30"><v>11.966</v></c></row>', 'solo se escriben las celdas de precio, con su estilo');
console.log(fallos ? 'HAY ' + fallos + ' FALLOS' : 'TODO CORRECTO');
process.exit(fallos ? 1 : 0);
