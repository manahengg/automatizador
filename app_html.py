"""Página única de la app web (HTML + CSS + JS sin dependencias externas: funciona sin internet)."""

PAGINA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comparador de ofertas</title><link rel="icon" type="image/png" href="__LOGO__">
<style>
:root{--azul:#1f4e78;--azul2:#2e75b6;--verde:#c6efce;--verdeT:#006100;--amar:#fff2cc;--nar:#f8cbad;--gris:#f3f4f6;--borde:#d9dde3;--txt:#1d232b;--rojo:#c00000}
*{box-sizing:border-box}body{margin:0;font:13px/1.4 Arial,Helvetica,sans-serif;color:var(--txt);background:#fff}
header{background:var(--azul);color:#fff;padding:10px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header h1{font-size:17px;margin:0;flex:1}header button{background:#fff2;color:#fff;border:1px solid #fff6}
button{font:inherit;padding:6px 12px;border-radius:5px;border:1px solid var(--borde);background:#fff;cursor:pointer}
button.prim{background:var(--azul2);color:#fff;border-color:var(--azul2)}button:disabled{opacity:.5;cursor:default}
main{padding:14px 16px}input[type=text],select{font:inherit;padding:5px 8px;border:1px solid var(--borde);border-radius:5px}
.tarjetas{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.tarjeta{border:1px solid var(--borde);border-radius:8px;padding:12px;cursor:pointer}.tarjeta:hover{border-color:var(--azul2)}
.tarjeta h3{margin:0 0 6px;font-size:15px}.peq{font-size:11px;color:#666}
.pestanas{display:flex;gap:4px;border-bottom:2px solid var(--azul);margin:12px 0}
.pestanas button{border-radius:6px 6px 0 0;border-bottom:none}.pestanas button.act{background:var(--azul);color:#fff}
table{border-collapse:collapse;width:100%}th,td{border:1px solid var(--borde);padding:4px 6px;vertical-align:top}
th{background:var(--azul);color:#fff;position:sticky;top:0;font-weight:600;font-size:12px;z-index:1}
.tabla{overflow:auto;max-height:calc(100vh - 230px);border:1px solid var(--borde)}
td.num{text-align:right;white-space:nowrap}tr.cap td{background:#d9e1f2;font-weight:bold}
.verde{background:var(--verde);color:var(--verdeT);font-weight:bold}.revisar{background:var(--amar)}.alta{background:var(--nar)}
.alerta{color:var(--rojo);font-size:11px}.chip{display:inline-block;padding:1px 6px;border-radius:9px;font-size:11px;background:var(--gris)}
.chip.seguro{background:var(--verde)}.chip.revisar{background:var(--amar)}.chip.manual{background:#ddebf7}.chip.sin{background:var(--nar)}
.caja{border:1px dashed var(--azul2);border-radius:8px;padding:14px;margin:8px 0;background:#f7fbff}
.fila{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.ocultar{display:none}
#msg{position:fixed;bottom:14px;right:14px;max-width:520px;padding:10px 14px;border-radius:8px;background:var(--azul);color:#fff;display:none;z-index:9;white-space:pre-wrap}
#msg.error{background:var(--rojo)}#cargando{position:fixed;inset:0;background:#fff8;display:none;align-items:center;justify-content:center;z-index:8;font-size:16px}
.mat{font-size:11px;color:#444}
#progreso{position:fixed;inset:0;background:#0006;display:none;align-items:center;justify-content:center;z-index:10}
#progreso .panel{background:#fff;border-radius:10px;padding:18px 22px;width:min(640px,92vw);box-shadow:0 8px 30px #0004}
#progreso h3{margin:0 0 4px;font-size:15px}.barra{height:14px;background:#e8edf3;border-radius:7px;overflow:hidden;margin:10px 0 6px}
.barra div{height:100%;background:linear-gradient(90deg,#2e75b6,#5b9bd5);width:0;transition:width .4s}
#progAhora{font-weight:bold;margin:6px 0}#progPasos{max-height:190px;overflow:auto;font-size:12px;color:#555;border-top:1px solid #eee;margin-top:8px;padding-top:6px}
#progPasos div:before{content:'✔ ';color:#548235}.gira{display:inline-block;animation:g 1s linear infinite}@keyframes g{to{transform:rotate(360deg)}}.resumen td{font-size:13px}
</style></head><body>
<header><img src="__LOGO__" alt="" style="height:38px;width:38px;background:#fff;border-radius:50%;padding:2px"><h1 id="titulo">Comparador de ofertas de material eléctrico</h1>
<span id="compartido" class="peq" style="color:#fff"></span><button onclick="irInicio()">Obras</button><button onclick="irBBDD()">Base de datos de precios</button><button onclick="irConfig()">⚙ Configuración</button></header>
<main id="app"></main><div id="msg"></div><div id="cargando"><div id="cargandoTxt">Trabajando…</div></div>
<div id="progreso"><div class="panel"><h3 id="progTitulo">Procesando</h3><div class="peq" id="progFich"></div>
<div class="barra"><div id="progBarra"></div></div><div class="fila" style="justify-content:space-between"><span id="progPct">0 %</span><span class="peq" id="progTiempo"></span></div>
<div id="progAhora"><span class="gira">⏳</span> <span id="progTexto">Preparando…</span></div><div id="progPasos"></div>
<div class="peq" style="margin-top:8px">Los PDF escaneados tardan unos segundos por página (reconocimiento de texto). Puedes dejar esta ventana abierta; si otra persona ya leyó el mismo documento, se aprovecha su lectura.</div></div></div>
<script>
const $=s=>document.querySelector(s);let OBRA=null,DATOS=null,PEST='comp';
const eur=(v,d=2)=>v==null?'':v.toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d})+' €';
const num=v=>v==null?'':v.toLocaleString('es-ES',{maximumFractionDigits:3});
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function aviso(t,err){const m=$('#msg');m.textContent=t;m.className=err?'error':'';m.style.display='block';clearTimeout(m._t);m._t=setTimeout(()=>m.style.display='none',err?12000:5000)}
function cargando(on,t){$('#cargando').style.display=on?'flex':'none';$('#cargandoTxt').textContent=t||'Trabajando…'}
async function api(url,opt){const r=await fetch(url,opt);const j=await r.json().catch(()=>({error:'Respuesta no válida'}));if(!r.ok||j.error)throw new Error(j.error||r.status);return j}
async function irInicio(){OBRA=null;$('#titulo').textContent='Comparador de ofertas de material eléctrico';
 const obras=await api('/api/obras');
 $('#app').innerHTML=`<div class="caja fila"><b>Nueva obra:</b><input type="text" id="nuevaObra" placeholder="Nombre de la obra" size="40"><button class="prim" onclick="crearObra()">Crear</button></div>
 <div class="tarjetas">${obras.map(o=>`<div class="tarjeta" onclick="abrirObra('${esc(o.id)}')"><h3>${esc(o.nombre)}</h3>
 <div>${o.cliente?'✔ Presupuesto del cliente':'✖ Falta el presupuesto del cliente'}</div><div class="peq">Proveedores: ${o.proveedores.map(esc).join(', ')||'ninguno'}</div></div>`).join('')||'<p>No hay obras todavía.</p>'}</div>`}
async function crearObra(){const n=$('#nuevaObra').value.trim();if(!n)return aviso('Escribe un nombre',1);try{const j=await api('/api/obras',{method:'POST',body:JSON.stringify({nombre:n})});abrirObra(j.id)}catch(e){aviso(e.message,1)}}
async function abrirObra(id){OBRA=id;cargando(true,'Analizando la obra (la primera vez puede tardar si hay PDFs escaneados)…');
 try{DATOS=await api('/api/obra/'+encodeURIComponent(id))}catch(e){cargando(false);return aviso(e.message,1)}cargando(false);pintarObra()}
function pintarObra(){const d=DATOS;$('#titulo').textContent='Obra: '+d.nombre;
 if(d.pendiente_capitulos)return elegirCapitulos(true);
 const pest=[['comp','Comparativa'],['alert','Alertas'],['lineas','Líneas de proveedores'],['docs','Documentos']];
 let h=`<div class="fila"><div class="caja" style="flex:1">${docsCabecera(d)}</div></div>
 <div class="pestanas">${pest.map(([k,t])=>`<button class="${PEST==k?'act':''}" onclick="PEST='${k}';pintarObra()">${t}</button>`).join('')}
 <span style="flex:1"></span>${d.materiales?`<button class="prim" onclick="location.href='/api/obra/${encodeURIComponent(d.id)}/excel'">⬇ Descargar Excel</button>`:''}</div><div id="cuerpo"></div>`;
 $('#app').innerHTML=h;if(!d.materiales&&PEST!='docs'){PEST='docs'}
 ({comp:pintarComp,alert:pintarAlertas,lineas:pintarLineas,docs:pintarDocs})[PEST]()}
function docsCabecera(d){const nf=(d.cliente_archivos||[]).length;let t=`<b>Cliente:</b> ${d.cliente?(nf>1?nf+' ficheros':esc(d.cliente.archivo.split('/').pop())):'<span class="alerta">falta</span>'}`;
 if(d.total_cliente!=null)t+=` · ${new Set(d.materiales.map(m=>m.n)).size} partidas · ${eur(d.total_cliente)}`;
 t+=' &nbsp; <b>Proveedores:</b> '+(d.proveedores.map(p=>{const x=d.totales&&d.totales[p.nombre];return `${esc(p.nombre)}${p.n_ofertas>1?' ['+p.n_ofertas+' ofertas]':''}${x?` (${x.cubiertos} materiales · ${eur(x.importe)})`:''}`}).join(' · ')||'ninguno');
 if(d.cliente)t+=` &nbsp; <button onclick="elegirCapitulos(false)" title="Elegir qué capítulos del presupuesto hacemos nosotros">📂 Capítulos que hacemos${d.capitulos?' ('+d.capitulos.length+')':''}</button>`;
 return t+` &nbsp; <button onclick="PEST='docs';pintarObra()">+ Añadir oferta</button>`}
let ARBOL=null;
async function elegirCapitulos(primeraVez){cargando(true,'Leyendo los capítulos del presupuesto…');let j;try{j=await api(`/api/obra/${encodeURIComponent(OBRA)}/capitulos`)}catch(e){cargando(false);return aviso(e.message,1)}cargando(false);
 ARBOL=j;OCUPADO=true;const sel=new Set(j.incluidos||[]);const todos=j.incluidos===null;
 const fila=n=>`<div class="capfila" data-nivel="${n.nivel}" style="padding-left:${n.nivel*22}px"><label><input type="checkbox" class="capchk" data-clave="${esc(n.clave)}" ${todos||sel.has(n.clave)?'checked':''} onchange="marcarCap(this)">
  <b>${esc(n.codigo)}</b> ${esc(n.titulo)}</label> <span class="peq">${n.partidas} partidas${j.total?' · '+eur(n.importe):''}</span></div>${n.hijos.map(fila).join('')}`;
 $('#titulo').textContent='Obra: '+(DATOS?DATOS.nombre:OBRA);
 $('#app').innerHTML=`<div class="caja"><h3 style="margin-top:0">${primeraVez?'Antes de procesar: ':''}¿Qué capítulos del presupuesto hacemos nosotros?</h3>
 <p class="peq">Solo se compararán con las ofertas, se casarán y saldrán en el Excel las partidas de los capítulos marcados. Puedes cambiarlo cuando quieras con el botón "📂 Capítulos que hacemos" (añadir o quitar capítulos rehace la comparativa). Al marcar o desmarcar un capítulo se marcan o desmarcan sus subcapítulos.</p>
 <div class="fila"><button onclick="todosCap(true)">Marcar todos</button><button onclick="todosCap(false)">Desmarcar todos</button><span id="capResumen" style="font-weight:bold"></span></div>
 <div style="margin:10px 0;max-height:calc(100vh - 330px);overflow:auto;border:1px solid var(--borde);border-radius:6px;padding:8px">${j.arbol.map(fila).join('')}</div>
 <div class="fila"><button class="prim" onclick="guardarCap()">✔ Guardar y procesar</button>${primeraVez?'':'<button onclick="OCUPADO=false;abrirObra(OBRA)">Cancelar</button>'}</div></div>`;resumenCap()}
function marcarCap(chk){const f=chk.closest('.capfila');const nivel=+f.dataset.nivel;let el=f.nextElementSibling;
 while(el&&+el.dataset.nivel>nivel){el.querySelector('.capchk').checked=chk.checked;el=el.nextElementSibling}resumenCap()}
function todosCap(v){document.querySelectorAll('.capchk').forEach(c=>c.checked=v);resumenCap()}
function resumenCap(){let n=0,imp=0;const rec=ns=>ns.forEach(x=>{const c=document.querySelector(`.capchk[data-clave="${CSS.escape(x.clave)}"]`);if(c&&c.checked){n+=x.propias;imp+=x.importe-x.hijos.reduce((a,h)=>a+h.importe,0)}rec(x.hijos)});rec(ARBOL.arbol);
 $('#capResumen').textContent=`Seleccionado: ${n} partidas`+(ARBOL.total?` · ${eur(Math.round(imp*100)/100)} de ${eur(ARBOL.total)}`:' (el proyecto no trae precios)')}
async function guardarCap(){const inc=[...document.querySelectorAll('.capchk')].filter(c=>c.checked).map(c=>c.dataset.clave);if(!inc.length)return aviso('Marca al menos un capítulo',1);
 cargando(true,'Guardando y casando las ofertas con los capítulos elegidos…');try{await api(`/api/obra/${encodeURIComponent(OBRA)}/capitulos`,{method:'POST',body:JSON.stringify({incluidos:inc})});OCUPADO=false;PEST='comp';await abrirObra(OBRA)}catch(e){cargando(false);aviso(e.message,1)}}
function pintarDocs(){const d=DATOS;const L=d.lineas||{};
 const filasOf=[];for(const p of d.proveedores){const docs=(L[p.nombre]||{}).docs||[];for(const x of docs)filasOf.push([p.nombre,x])}
 $('#cuerpo').innerHTML=`
 <div class="caja"><h3 style="margin-top:0">1. Presupuesto / proyecto del cliente</h3>
 ${(d.cliente_archivos||[]).length?`<table style="width:auto;margin-bottom:8px"><tr><th>Fichero del proyecto</th><th></th></tr>${d.cliente_archivos.map(a=>`<tr><td>${esc(a.archivo)}</td><td>${d.cliente_archivos.length>1?`<button onclick="quitarCli('${a.huella}','${esc(a.archivo)}')">Quitar</button>`:''}</td></tr>`).join('')}</table>`:''}
 <div class="fila"><input type="file" id="fCli" multiple accept=".bc3,.pdf,.xlsx,.xlsm">
 ${d.cliente?`<label><input type="radio" name="modoCli" value="anadir" checked> Añadir al proyecto actual (proyecto en varios ficheros)</label><label><input type="radio" name="modoCli" value="sustituir"> Sustituir todo el presupuesto</label>`:''}
 <button class="prim" onclick="subir('cliente')">Subir</button></div>
 <div class="peq">BC3, PDF de "Presupuesto y mediciones" o Excel (también varios Excel de un mismo proyecto: se unen por código). Después se elige qué capítulos hacemos. Sustituir todo borra las correcciones manuales.</div>${(d.avisos_cliente||[]).map(a=>`<div class="alerta">${esc(a)}</div>`).join('')}</div>
 <div class="caja"><h3 style="margin-top:0">2. Ofertas de proveedores (se pueden añadir en cualquier momento)</h3>
 <div class="fila"><input type="file" id="fProv" multiple accept=".pdf,.xlsx,.xlsm,.bc3"><input type="text" id="nProv" placeholder="Proveedor (opcional)" list="listaProv"><datalist id="listaProv">${d.proveedores.map(p=>`<option value="${esc(p.nombre)}">`).join('')}</datalist>
 <label title="Si no se marca, la oferta se AÑADE a las que ya hay de ese proveedor (p. ej. una oferta por capítulo)"><input type="checkbox" id="sustProv"> Sustituir las ofertas anteriores de este proveedor</label><button class="prim" onclick="subir('proveedor')">Añadir</button></div>
 <div class="peq">Un proveedor puede tener <b>varias ofertas</b> (por ejemplo una por capítulo) o una sola para todo: se casan todas juntas con el presupuesto. Si escribes el nombre del proveedor se aplica a todos los ficheros seleccionados; si no, se deduce de cada documento. Los PDF escaneados se leen con OCR.</div>
 <table style="margin-top:8px"><tr><th>Proveedor</th><th>Fichero</th><th>Añadida por</th><th>Fecha oferta</th><th>Validez</th><th>Líneas</th><th>Total documento</th><th>Suma leída</th><th>Avisos</th><th></th></tr>
 ${filasOf.map(([p,x])=>`<tr><td>${esc(p)}</td><td>${esc(x.archivo)}</td><td class="peq">${esc(x.usuario||'')}<br>${esc((x.anadida||'').replace('T',' ').slice(0,16))}</td><td>${esc(x.fecha)}</td><td>${esc(x.validez)}</td><td class="num">${x.lineas}</td><td class="num">${eur(x.total_doc)}</td><td class="num ${x.total_doc!=null&&Math.abs(x.total_doc-x.suma)>0.05?'revisar':''}">${eur(x.suma)}</td><td class="alerta">${(x.avisos||[]).map(esc).join('<br>')}</td><td><button onclick="quitarOferta('${x.huella}','${esc(x.archivo)}')">Quitar</button></td></tr>`).join('')}</table>
 ${d.proveedores.length&&!filasOf.length?'<p class="peq">Las ofertas se muestran aquí después de elegir los capítulos.</p>':''}</div>
 <div class="caja"><h3 style="margin-top:0">Historial (quién ha hecho qué)</h3>${(d.historial||[]).map(h=>`<div class="peq">${esc((h.cuando||'').replace('T',' '))} · <b>${esc(h.usuario||'')}</b> ${esc(h.detalle)}</div>`).join('')}</div>`}
async function quitarOferta(h,nom){OCUPADO=true;const ok=confirm('¿Quitar la oferta '+nom+'?');OCUPADO=false;if(!ok)return;try{await api(`/api/obra/${encodeURIComponent(OBRA)}/quitar_oferta`,{method:'POST',body:JSON.stringify({huella:h})});abrirObra(OBRA)}catch(e){aviso(e.message,1)}}
async function quitarCli(h,nom){OCUPADO=true;const ok=confirm('¿Quitar '+nom+' del proyecto del cliente?');OCUPADO=false;if(!ok)return;try{await api(`/api/obra/${encodeURIComponent(OBRA)}/quitar_cliente`,{method:'POST',body:JSON.stringify({huella:h})});abrirObra(OBRA)}catch(e){aviso(e.message,1)}}
function verProgreso(on,titulo,fich){$('#progreso').style.display=on?'flex':'none';if(on){$('#progTitulo').textContent=titulo;$('#progFich').textContent=fich||'';
 $('#progPasos').innerHTML='';$('#progBarra').style.width='0';$('#progPct').textContent='0 %';$('#progTexto').textContent='Preparando…';$('#progTiempo').textContent=''}}
function pintarProgreso(j){const pct=Math.round(j.fraccion*100);$('#progBarra').style.width=pct+'%';$('#progPct').textContent=pct+' %';
 $('#progTexto').textContent=j.texto+(j.seg_paso>=3?` (${j.seg_paso} s)`:'');$('#progTiempo').textContent='Tiempo: '+(j.segundos>=60?Math.floor(j.segundos/60)+' min '+j.segundos%60+' s':j.segundos+' s');
 $('#progPasos').innerHTML=j.pasos.map(p=>`<div>${esc(p.texto)} <span class="peq">${p.seg>=1?'('+p.seg+' s)':''}</span></div>`).join('');$('#progPasos').scrollTop=1e6}
function enviar(url,fd,onSubida){return new Promise((ok,mal)=>{const x=new XMLHttpRequest();x.open('POST',url);
 x.upload.onprogress=e=>{if(e.lengthComputable)onSubida(e.loaded/e.total)};
 x.onload=()=>{let j;try{j=JSON.parse(x.responseText)}catch(e){return mal(new Error('Respuesta no válida'))}if(x.status>=400||j.error)mal(new Error(j.error||x.status));else ok(j)};
 x.onerror=()=>mal(new Error('No se pudo enviar el fichero'));x.send(fd)})}
async function subir(tipo){const inp=tipo=='cliente'?$('#fCli'):$('#fProv');if(!inp.files.length)return aviso('Elige un fichero',1);
 const fs=[...inp.files];const fd=new FormData();for(const f of fs)fd.append('fichero',f,f.name);
 if(tipo=='proveedor'){fd.append('proveedor',$('#nProv').value);fd.append('sustituir',$('#sustProv').checked?'1':'0')}
 else{const m=document.querySelector('input[name=modoCli]:checked');fd.append('modo',m?m.value:'sustituir');
  if(m&&m.value=='sustituir'){OCUPADO=true;const ok=confirm('Se sustituirá TODO el presupuesto del cliente y se borrarán las correcciones manuales. ¿Seguir?');OCUPADO=false;if(!ok)return}}
 const mb=fs.reduce((a,f)=>a+f.size,0)/1048576;OCUPADO=true;
 verProgreso(true,tipo=='cliente'?'Leyendo el presupuesto del cliente':'Leyendo '+(fs.length>1?fs.length+' ofertas':'la oferta'),fs.map(f=>f.name).join(' · ')+` (${mb.toFixed(1)} MB)`);
 try{const r=await enviar(`/api/obra/${encodeURIComponent(OBRA)}/${tipo}`,fd,f=>{$('#progBarra').style.width=Math.round(f*5)+'%';$('#progTexto').textContent=`Subiendo ${Math.round(f*100)} %…`});
  let j;do{await new Promise(z=>setTimeout(z,600));j=await api('/api/trabajo/'+r.trabajo);pintarProgreso(j)}while(j.estado=='trabajando');
  if(j.estado=='error')throw new Error(j.mensaje);
  await new Promise(z=>setTimeout(z,500));verProgreso(false);aviso(j.mensaje);PEST='comp';await abrirObra(OBRA)}
 catch(e){verProgreso(false);aviso(e.message,1)}finally{OCUPADO=false}}
async function quitar(p){OCUPADO=true;const ok=confirm('¿Quitar la oferta de '+p+'?');OCUPADO=false;if(!ok)return;try{await api(`/api/obra/${encodeURIComponent(OBRA)}/quitar`,{method:'POST',body:JSON.stringify({proveedor:p})});abrirObra(OBRA)}catch(e){aviso(e.message,1)}}
let SOLO_OF=null;
function pintarComp(){const d=DATOS,P=d.proveedores.map(p=>p.nombre);
 const conOf=d.materiales.filter(m=>Object.keys(m.prov).length).length,total=d.materiales.length;
 const soloOf=SOLO_OF===null?(P.length>0&&conOf<total/2):SOLO_OF;
 const caps=[...new Set(d.materiales.filter(m=>Object.keys(m.prov).length).map(m=>m.cap))];
 const resumenOf=P.length?`<div class="caja" style="margin:0 0 6px;padding:8px 12px"><b>${conOf} de ${total}</b> materiales tienen oferta de algún proveedor${conOf<total?` (capítulos ofertados: ${caps.slice(0,8).map(esc).join(', ')}${caps.length>8?'…':''}). El resto de partidas del cliente no las ha ofertado nadie${soloOf?' y están ocultas: desmarca "solo partidas con oferta" para verlas':''}.`:'.'}</div>`:'';
 let h=`${resumenOf}<div class="fila" style="margin-bottom:6px"><input type="text" id="filtro" placeholder="Filtrar por texto, código o capítulo" size="40" oninput="filtrar()">
 <label title="Oculta las partidas que ningún proveedor ha ofertado"><input type="checkbox" id="soloOf" onchange="SOLO_OF=this.checked;filtrar()" ${soloOf?'checked':''}> solo partidas con oferta</label>
 <label><input type="checkbox" id="soloAl" onchange="filtrar()"> solo con alertas</label><span class="peq">Verde = más barato · amarillo = casamiento a revisar · naranja = ofertan algo distinto. Pasa el ratón por encima para ver detalles.</span></div>
 <div class="tabla"><table id="tcomp"><thead><tr><th>Nº</th><th>Código</th><th>Partida del cliente</th><th>Material a comprar</th><th>Ud</th><th>Cant.</th><th>Precio cliente</th>
 ${P.map(p=>`<th>${esc(p)}<br>código</th><th>${esc(p)}<br>cant. ofertada</th><th>${esc(p)}<br>unitario</th><th>${esc(p)}<br>total</th>`).join('')}<th>Más bajo</th><th>P.U. más barato</th><th>× cantidad</th><th>BBDD</th><th>Alertas</th></tr></thead><tbody>`;
 let cap=null;for(const m of d.materiales){if(m.cap!==cap){cap=m.cap;h+=`<tr class="cap"><td colspan="${12+P.length*4}">${esc(cap)}</td></tr>`}
  const al=[...m.alertas_cli.map(a=>'CLIENTE: '+a),...(m.aprendido||[]).map(a=>'🧠 '+a)];let celdas='';
  const min=m.mejor.precio;
  for(const p of P){const o=m.prov[p];if(!o){celdas+='<td></td><td></td><td></td><td></td>';continue}
   o.alertas.forEach(a=>al.push(p+': '+a.t));const grave=o.alertas.some(a=>a.g=='alta');const cl=grave?'alta':(o.estado=='revisar'?'revisar':'');
   const ver=o.precio!=null&&min!=null&&Math.abs(o.precio-min)<1e-9?'verde':'';
   celdas+=`<td class="${cl}" title="${esc(o.desc)}\nPuntuación ${o.punt} · ${o.estado}">${esc(o.codigos)}</td><td class="num" title="${esc(o.dcant)}">${num(o.cant)}${o.dcant&&o.dcant!='='?`<div class="peq">${esc(o.dcant)}</div>`:''}</td><td class="num ${ver}">${eur(o.precio,4)}</td><td class="num ${ver}">${eur(o.importe)}</td>`}
  let bb='';if(m.bbdd){bb=`<span title="${esc(m.bbdd.ultimos.map(x=>`${x.prov}: ${x.precio} € (${x.fecha}, ${x.obra}) ${x.desc}`).join('\n'))}">${esc(m.bbdd.ultimos[0].prov)} ${eur(m.bbdd.ultimos[0].precio,4)}</span>`;if(m.bbdd.aviso){al.push('BBDD: '+m.bbdd.aviso);bb='<span class="verde">'+bb+'</span>'}}
  h+=`<tr data-of="${Object.keys(m.prov).length?1:0}" data-al="${al.length?1:0}" data-txt="${esc((m.codigo+' '+m.resumen+' '+m.material+' '+cap).toLowerCase())}"><td>${esc(m.id)}</td><td>${esc(m.codigo)}</td><td>${m.primero?esc(m.resumen):''}</td><td class="mat">${esc(m.material)}${m.nota?`<div class="peq">${esc(m.nota)}</div>`:''}</td><td>${esc(m.ud)}</td><td class="num">${num(m.cant)}</td><td class="num">${m.primero?eur(m.precio_cli):''}</td>${celdas}
  <td>${esc(m.mejor.prov||'')}</td><td class="num">${eur(m.mejor.precio,4)}</td><td class="num">${eur(m.mejor.importe)}</td><td>${bb}</td><td class="alerta">${al.map(esc).join('<br>')}<div><button class="peq" onclick="anotar('${esc(m.id)}')" title="Enseñar a la app: anota una corrección o criterio para este material; se recordará en obras futuras">📝 Anotar caso</button></div></td></tr>`}
 h+='</tbody></table></div>';$('#cuerpo').innerHTML=h;filtrar()}
function filtrar(){const t=$('#filtro').value.toLowerCase(),s=$('#soloAl').checked,o=$('#soloOf').checked;let cap=null,visibles=0;
 const cierra=()=>{if(cap)cap.classList.toggle('ocultar',visibles==0)};
 document.querySelectorAll('#tcomp tbody tr').forEach(tr=>{if(tr.classList.contains('cap')){cierra();cap=tr;visibles=0;return}
  const ocul=(t&&!tr.dataset.txt.includes(t))||(s&&tr.dataset.al!='1')||(o&&tr.dataset.of!='1');tr.classList.toggle('ocultar',ocul);if(!ocul)visibles++});cierra()}
function pintarAlertas(){const d=DATOS;const filas=[];
 for(const m of d.materiales){m.alertas_cli.forEach(a=>filas.push(['media',m.id,m.codigo,'Cliente',a]));
  for(const [p,o] of Object.entries(m.prov)){o.alertas.forEach(a=>filas.push([a.g,m.id,m.codigo,p,a.t]))}
  if(m.bbdd&&m.bbdd.aviso)filas.push(['media',m.id,m.codigo,'BBDD',m.bbdd.aviso]);
  (m.aprendido||[]).forEach(a=>filas.push(['media',m.id,m.codigo,'Aprendido',a]))}
 for(const [p,L] of Object.entries(d.lineas||{}))L.lineas.filter(l=>!l.mat&&l.precio!=null).forEach(l=>filas.push(['baja','','',p,`Línea ${l.i+1} sin casar: ${l.desc}`]));
 const o={alta:0,media:1,baja:2};filas.sort((a,b)=>o[a[0]]-o[b[0]]);
 $('#cuerpo').innerHTML=`<div class="tabla"><table><tr><th>Gravedad</th><th>Nº</th><th>Código</th><th>Origen</th><th>Detalle</th></tr>${filas.map(f=>`<tr><td class="${f[0]=='alta'?'alta':f[0]=='media'?'revisar':''}">${f[0]}</td><td>${esc(f[1])}</td><td>${esc(f[2])}</td><td>${esc(f[3])}</td><td>${esc(f[4])}</td></tr>`).join('')}</table></div>`}
async function anotar(mid){OCUPADO=true;try{await anotar2(mid)}finally{OCUPADO=false}}
async function anotar2(mid){const d=DATOS,m=d.materiales.find(x=>x.id==mid);const P=Object.keys(m.prov);
 const obs=prompt(`Anotar caso para ${m.id} · ${m.codigo} · ${m.material}\n\nEscribe la corrección o el criterio (p. ej.: "Debería ser 10 módulos de 630 W: 21x460 W está sobredimensionado").\nSe recordará en obras futuras con materiales parecidos.`);if(!obs)return;
 let prov='';if(P.length){prov=prompt('¿A qué proveedor se refiere? ('+P.join(', ')+')\nDéjalo vacío si aplica a todos.','')||''}
 const cant=prompt('Cantidad correcta (opcional, déjalo vacío si no aplica):','')||'';
 try{await api(`/api/obra/${encodeURIComponent(OBRA)}/caso`,{method:'POST',body:JSON.stringify({material:mid,observacion:obs,proveedor:prov.trim(),cantidad:cant.trim()})});aviso('Caso guardado: la app lo tendrá en cuenta a partir de ahora.');abrirObra(OBRA)}catch(e){aviso(e.message,1)}}
let PROVSEL=null;
function pintarLineas(){const d=DATOS,P=Object.keys(d.lineas||{});if(!P.length){$('#cuerpo').innerHTML='<p>No hay ofertas cargadas.</p>';return}
 if(!P.includes(PROVSEL))PROVSEL=P[0];const L=d.lineas[PROVSEL].lineas;const mats=Object.fromEntries(d.materiales.map(m=>[m.id,m]));
 $('#cuerpo').innerHTML=`<div class="fila" style="margin-bottom:6px">Proveedor: <select onchange="PROVSEL=this.value;pintarLineas()">${P.map(p=>`<option ${p==PROVSEL?'selected':''}>${esc(p)}</option>`).join('')}</select>
 <span class="peq">Cambia el desplegable para casar una línea con otra partida (o "no casar"). La corrección se guarda y se aprende para próximas ofertas de este proveedor.</span></div>
 <div class="tabla"><table><tr><th>#</th><th>Sección</th><th>Código</th><th>Descripción del proveedor</th><th>Cant.</th><th>Precio neto</th><th>Dto</th><th>Importe</th><th>Casada con</th><th>Tipo</th><th></th></tr>
 ${L.map(l=>{const m=l.mat?mats[l.mat]:null;const cl=l.manual?'manual':(l.mat?(l.punt>=0.75?'seguro':'revisar'):'sin');
 return `<tr><td>${l.i+1}</td><td class="peq">${esc(l.seccion)}</td><td>${esc(l.codigo)}</td><td>${esc(l.desc)}${l.notas.length?`<div class="peq">${esc(l.notas.join('; '))}</div>`:''}</td><td class="num">${num(l.cant)}</td><td class="num">${eur(l.precio,4)}</td><td class="num">${l.dto??''}</td><td class="num">${eur(l.importe)}</td>
 <td><select data-i="${l.i}" onfocus="opciones(this)" onchange="fijar('${l.uid}',this.value)" style="max-width:420px"><option value="${esc(l.mat||'')}">${m?esc(m.id+' · '+m.codigo+' · '+m.material.slice(0,60)):'— sin casar —'}</option></select></td>
 <td><span class="chip ${cl}">${l.manual?'manual':(l.tipo||'sin casar')}${l.punt!=null&&!l.manual?' '+l.punt:''}</span></td><td>${l.manual?`<button onclick="deshacer('${l.uid}')" title="Volver a la propuesta automática">↺</button>`:''}</td></tr>`}).join('')}</table></div>`}
function opciones(sel){if(sel._ok)return;sel._ok=1;const d=DATOS,l=d.lineas[PROVSEL].lineas.find(x=>x.i==sel.dataset.i);const actual=sel.value;
 const c=l.cands.map(x=>x.id);const fmt=m=>`${m.id} · ${m.codigo} · ${m.material.slice(0,70)}`;
 let h=`<option value="">— no casar —</option><optgroup label="Sugeridas">${c.map(id=>{const m=d.materiales.find(x=>x.id==id);return m?`<option value="${esc(id)}" ${id==actual?'selected':''}>${esc(fmt(m))}</option>`:''}).join('')}</optgroup><optgroup label="Todas las partidas">`;
 for(const m of d.materiales)h+=`<option value="${esc(m.id)}" ${m.id==actual&&!c.includes(actual)?'selected':''}>${esc(fmt(m))}</option>`;sel.innerHTML=h+'</optgroup>'}
async function fijar(i,mat){cargando(true,'Guardando y recalculando…');try{await api(`/api/obra/${encodeURIComponent(OBRA)}/fijar`,{method:'POST',body:JSON.stringify({proveedor:PROVSEL,linea:i,material:mat})});await abrirObra(OBRA)}catch(e){cargando(false);aviso(e.message,1)}}
async function deshacer(i){cargando(true);try{await api(`/api/obra/${encodeURIComponent(OBRA)}/deshacer`,{method:'POST',body:JSON.stringify({proveedor:PROVSEL,linea:i})});await abrirObra(OBRA)}catch(e){cargando(false);aviso(e.message,1)}}
async function irBBDD(){OBRA=null;$('#titulo').textContent='Base de datos de precios';
 $('#app').innerHTML=`<div class="caja fila"><input type="text" id="qb" size="50" placeholder="Material, código o característica (p. ej.: 1x35 rz1-k, downlight 20w, tubo 20)" onkeydown="if(event.key=='Enter')buscarBBDD()"><button class="prim" onclick="buscarBBDD()">Buscar</button><span id="resb" class="peq"></span></div><div id="tb"></div><h3>Casos aprendidos</h3><div id="tc"></div>`;buscarBBDD();pintarCasos()}
async function pintarCasos(){const cs=await api('/api/casos');$('#tc').innerHTML=cs.length?`<table><tr><th>Fecha</th><th>Obra</th><th>Proveedor</th><th>Familia</th><th>Material</th><th>Observación</th><th>Cant. correcta</th><th></th></tr>${cs.map(c=>`<tr><td>${esc((c.creado||'').slice(0,10))}</td><td>${esc(c.obra)}</td><td>${esc(c.proveedor||'todos')}</td><td>${esc(c.familia)}</td><td>${esc(c.texto_material)}</td><td>${esc(c.observacion)}</td><td class="num">${c.cantidad_correcta??''}</td><td><button onclick="borrarCaso(${c.id})">Olvidar</button></td></tr>`).join('')}</table>`:'<p class="peq">Todavía no hay casos. Usa "📝 Anotar caso" en la comparativa de una obra para enseñar a la app.</p>'}
async function borrarCaso(id){if(!confirm('¿Olvidar este caso?'))return;await api('/api/casos/borrar',{method:'POST',body:JSON.stringify({id})});pintarCasos()}
async function buscarBBDD(){const q=($('#qb')||{}).value||'';try{const j=await api('/api/bbdd?q='+encodeURIComponent(q));const r=j.resumen;$('#resb').textContent=`${r.precios} precios · ${r.proveedores} proveedores · ${r.obras} obras · ${r.equivalencias} equivalencias aprendidas · ${r.casos} casos`;
 if(!q){$('#tb').innerHTML='<p>Escribe qué buscar. Cada línea de cada oferta que pasa por la app queda registrada aquí con su precio neto, proveedor, fecha y obra.</p>';return}
 const grupos={};for(const f of j.filas){const k=f.clave_material||f.desc_norm;(grupos[k]=grupos[k]||[]).push(f)}
 let h='<div class="tabla"><table><tr><th>Material (clave técnica)</th><th>Proveedor</th><th>Precio neto</th><th>Fecha</th><th>Obra</th><th>Código</th><th>Descripción del proveedor</th><th>Cant.</th><th>Dto</th></tr>';
 for(const [k,fs] of Object.entries(grupos)){const min=Math.min(...fs.map(f=>f.precio_neto));fs.forEach((f,i)=>h+=`<tr>${i==0?`<td rowspan="${fs.length}"><b>${esc(k)}</b></td>`:''}<td>${esc(f.proveedor)}</td><td class="num ${f.precio_neto==min&&fs.length>1?'verde':''}">${eur(f.precio_neto,4)}</td><td>${esc(f.fecha)}</td><td>${esc(f.obra)}</td><td>${esc(f.codigo)}</td><td>${esc(f.descripcion)}</td><td class="num">${num(f.cantidad)}</td><td class="num">${f.dto??''}</td></tr>`)}
 $('#tb').innerHTML=h+'</table></div>'+(j.filas.length?'':'<p>Sin resultados.</p>')}catch(e){aviso(e.message,1)}}
let VER=0,OCUPADO=false;
async function sondear(){try{const j=await api('/api/cambios?v='+VER);if(VER&&j.cambios.length){
  const ajenos=j.cambios.filter(c=>c.usuario);if(ajenos.length)aviso('Actualizado: '+ajenos.map(c=>c.texto).join(' · '));
  const enPantalla=document.activeElement&&['SELECT','INPUT','TEXTAREA'].includes(document.activeElement.tagName);
  if(!OCUPADO&&!enPantalla&&$('#cargando').style.display!='flex'){
   if(OBRA&&j.cambios.some(c=>c.obra==OBRA||c.obra===null))recargarObra();else if(!OBRA&&$('#nuevaObra'))irInicio()}}
  VER=j.v}catch(e){}setTimeout(sondear,3000)}
async function recargarObra(){try{const d=await api('/api/obra/'+encodeURIComponent(OBRA));DATOS=d;const sc=$('.tabla')?$('.tabla').scrollTop:0;pintarObra();if($('.tabla'))$('.tabla').scrollTop=sc}catch(e){}}
async function estadoCompartido(){try{const c=await api('/api/config');$('#compartido').innerHTML=(c.activa?'🔗 Compartido':'💻 Solo este PC')+' · '+esc(c.usuario)}catch(e){}}
async function irConfig(){OBRA=null;$('#titulo').textContent='Configuración';const c=await api('/api/config');
 $('#app').innerHTML=`<div class="caja"><h3 style="margin-top:0">Trabajo en equipo (SharePoint / OneDrive)</h3>
 <p>1. En SharePoint crea (o elige) una carpeta para la app, p. ej. <b>"Comparador de ofertas"</b>, y pulsa <b>Sincronizar</b> (o <b>Agregar acceso directo a Mis archivos</b>) para que aparezca en el Explorador de Windows.<br>
 2. Pega aquí su ruta (en el Explorador: clic derecho en la carpeta → <i>Copiar como ruta de acceso</i>). Todos los PCs deben apuntar a la misma carpeta de SharePoint.</p>
 <div class="fila"><b>Carpeta compartida:</b><input type="text" id="cfgCarpeta" size="80" value="${esc(c.carpeta_compartida)}" placeholder="C:\\Users\\...\\Empresa\\Comparador de ofertas"></div>
 ${c.sugerencias.length?`<div class="peq" style="margin:6px 0">Carpetas de OneDrive/SharePoint encontradas en este PC (clic para usarla):<br>${c.sugerencias.map(x=>`<a href="#" onclick="$('#cfgCarpeta').value=this.textContent;return false">${esc(x)}</a>`).join('<br>')}</div>`:''}
 <div class="fila" style="margin-top:8px"><b>Tu nombre:</b><input type="text" id="cfgUsuario" value="${esc(c.usuario)}" size="30"><span class="peq">Aparece en el historial de cada obra y en los casos que anotes.</span></div>
 <div class="fila" style="margin-top:10px"><button class="prim" onclick="guardarConfig()">Guardar</button><span class="peq">Estado: ${c.activa?'<b>compartido</b> — trabajando en '+esc(c.en_uso):'solo este PC ('+esc(c.en_uso)+')'}</span></div>
 ${c.obras_locales.length?`<div class="caja" style="background:#fff8e5">Tienes ${c.obras_locales.length} obra(s) creadas antes solo en este PC (${c.obras_locales.map(esc).join(', ')}). <button onclick="llevarObras()">Copiarlas a la carpeta compartida</button></div>`:''}
 <p class="peq">Cómo funciona: en la carpeta compartida nunca se modifica un fichero, solo se crean ficheros nuevos (uno por acción), así OneDrive no genera conflictos aunque varias personas trabajen a la vez en la misma obra. Cada PC mantiene su base de datos de precios local, que se completa sola con lo de todos. Base local: ${esc(c.local)}</p></div>`}
async function guardarConfig(){cargando(true,'Guardando y sincronizando…');try{await api('/api/config',{method:'POST',body:JSON.stringify({carpeta_compartida:$('#cfgCarpeta').value,usuario:$('#cfgUsuario').value})});cargando(false);aviso('Configuración guardada');estadoCompartido();irConfig()}catch(e){cargando(false);aviso(e.message,1)}}
async function llevarObras(){cargando(true);try{const j=await api('/api/config/llevar_obras',{method:'POST',body:'{}'});cargando(false);aviso(j.mensaje);irConfig()}catch(e){cargando(false);aviso(e.message,1)}}
estadoCompartido();irInicio();sondear();
</script></body></html>
"""
