"""Páginas de la app web (HTML + CSS + JavaScript sin dependencias externas: funciona sin internet)."""

CSS = r'''
:root{--navy:#17324d;--azul:#2f6690;--claro:#eaf1f8;--gris:#f4f5f7;--borde:#d0d5dd;--txt:#1d2939;--suave:#667085;
--verde:#12b76a;--verde-bg:#d1fadf;--verde-tx:#05603a;--ambar:#f79009;--ambar-bg:#fef0c7;--ambar-tx:#93370d;
--rojo:#f04438;--rojo-bg:#fee4e2;--rojo-tx:#b42318;--azul-bg:#d1e9ff;--azul-tx:#175cd3;--fondo:#f6f8fb;--tarjeta:#fff}
@media (prefers-color-scheme:dark){:root{--navy:#0b1b2b;--azul:#5b9bd5;--claro:#1b2a3a;--gris:#1f2933;--borde:#344054;--txt:#e4e7ec;--suave:#98a2b3;
--verde-bg:#12372a;--verde-tx:#75e0a7;--ambar-bg:#3d2f0a;--ambar-tx:#fec84b;--rojo-bg:#3d1613;--rojo-tx:#fda29b;--azul-bg:#102a56;--azul-tx:#84caff;--fondo:#101828;--tarjeta:#182230}}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 "Segoe UI",Calibri,system-ui,sans-serif;color:var(--txt);background:var(--fondo)}
.wrap{max-width:1240px;margin:0 auto;padding:0 20px}
header.top{background:var(--navy);color:#fff;padding:18px 0}
header.top .wrap{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
header.top h1{margin:0;font-size:22px;font-weight:700}
header.top .sub{color:#c9d6e4;font-size:13px}
header.top .espacio{flex:1}
a{color:var(--azul)}
.btn{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--borde);background:var(--tarjeta);color:var(--txt);border-radius:8px;padding:9px 16px;font:inherit;font-weight:600;cursor:pointer;text-decoration:none}
.btn:hover{border-color:var(--azul)}
.btn.primario{background:var(--azul);border-color:var(--azul);color:#fff}
.btn.primario:hover{filter:brightness(1.1)}
.btn[disabled]{opacity:.45;cursor:not-allowed}
.btn.claro{background:transparent;color:#fff;border-color:#ffffff66}
main{padding:32px 0 110px}
h2{font-size:18px;margin:28px 0 12px;color:var(--navy)}
@media (prefers-color-scheme:dark){h2{color:#cfe3f7}}
.card{background:var(--tarjeta);border:1px solid var(--borde);border-radius:12px;padding:20px}
.explica{color:var(--suave);font-size:14px;margin:0 0 14px}
.drop{border:2px dashed var(--borde);border-radius:12px;padding:26px 16px;text-align:center;color:var(--suave);cursor:pointer;transition:.15s;background:var(--gris)}
.drop:hover,.drop.sobre{border-color:var(--azul);background:var(--claro);color:var(--txt)}
.drop b{display:block;color:var(--txt);font-size:16px;margin-bottom:4px}
.fichero{display:flex;align-items:center;gap:10px;margin-top:8px;padding:8px 12px;border:1px solid var(--borde);border-radius:8px;background:var(--tarjeta)}
.fichero .n{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.fichero .t{color:var(--suave);font-size:13px}
.fichero button{border:0;background:none;color:var(--rojo-tx);cursor:pointer;font-size:18px;line-height:1}
.pasos{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:18px}
.num{display:inline-flex;width:26px;height:26px;border-radius:50%;background:var(--azul);color:#fff;font-weight:700;align-items:center;justify-content:center;margin-right:8px;font-size:14px}
.error{background:var(--rojo-bg);color:var(--rojo-tx);border-left:5px solid var(--rojo);padding:12px 16px;border-radius:8px;margin:14px 0;white-space:pre-wrap}
.aviso{background:var(--ambar-bg);color:var(--ambar-tx);border-left:5px solid var(--ambar);padding:10px 14px;border-radius:8px;margin:6px 0;font-size:14px}
.info{background:var(--claro);border-left:5px solid var(--azul);padding:10px 14px;border-radius:8px;margin:6px 0;font-size:14px}
.ok{background:var(--verde-bg);color:var(--verde-tx);border-left:5px solid var(--verde);padding:10px 14px;border-radius:8px;margin:6px 0}
.progreso{display:none;text-align:center;padding:40px 20px}
.rueda{width:44px;height:44px;border:5px solid var(--claro);border-top-color:var(--azul);border-radius:50%;margin:0 auto 14px;animation:g 1s linear infinite}
@keyframes g{to{transform:rotate(360deg)}}
.previos a{display:flex;justify-content:space-between;gap:12px;padding:10px 14px;border:1px solid var(--borde);border-radius:8px;margin-bottom:8px;background:var(--tarjeta);text-decoration:none;color:var(--txt)}
.previos a:hover{border-color:var(--azul)}
.previos small{color:var(--suave)}
/* tarjetas KPI */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.kpi{background:var(--claro);border-radius:10px;padding:14px 16px;border-top:5px solid var(--azul)}
.kpi.mejor{border-top-color:var(--verde)}
.kpi .et{font-size:12px;font-weight:700;color:var(--suave);text-transform:uppercase;letter-spacing:.03em}
.kpi .valor{font-size:26px;font-weight:700;margin:2px 0}
.kpi .nota{font-size:13px;color:var(--suave)}
.chip{display:inline-block;border-radius:999px;padding:1px 10px;font-size:12px;font-weight:700;white-space:nowrap}
.chip.seguro{background:var(--verde-bg);color:var(--verde-tx)}
.chip.revisar{background:var(--ambar-bg);color:var(--ambar-tx)}
.chip.sinpareja,.chip.mal{background:var(--rojo-bg);color:var(--rojo-tx)}
.chip.mano{background:var(--azul-bg);color:var(--azul-tx)}
.chip.neutro{background:var(--gris);color:var(--suave)}
/* revisión */
.tabs{display:flex;gap:6px;flex-wrap:wrap;border-bottom:2px solid var(--borde);margin-bottom:12px}
.tab{padding:9px 16px;border:0;background:none;font:inherit;font-weight:600;color:var(--suave);cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-2px}
.tab.act{color:var(--azul);border-bottom-color:var(--azul)}
.filtros{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.pill{border:1px solid var(--borde);background:var(--tarjeta);border-radius:999px;padding:5px 14px;font:inherit;font-size:13px;cursor:pointer;color:var(--txt)}
.pill.act{background:var(--azul);border-color:var(--azul);color:#fff}
.fila{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;padding:14px;border:1px solid var(--borde);border-radius:10px;margin-bottom:10px;background:var(--tarjeta);border-left:6px solid var(--verde)}
.fila.revisar{border-left-color:var(--ambar)}.fila.sinpareja{border-left-color:var(--rojo)}.fila.mano{border-left-color:var(--azul)}
.fila.dup{background:var(--rojo-bg)}
@media (max-width:820px){.fila{grid-template-columns:1fr}}
.fila .d{font-weight:600}
.fila .meta{font-size:13px;color:var(--suave);margin-top:2px}
.fila .motivo{font-size:13px;color:var(--ambar-tx);margin-top:6px}
select,input.otra{width:100%;padding:8px 10px;border:1px solid var(--borde);border-radius:8px;font:inherit;background:var(--tarjeta);color:var(--txt)}
input.otra{margin-top:6px}
.det{font-size:13px;color:var(--suave);margin-top:6px}
.det .mal{color:var(--rojo-tx);font-weight:700}
.barra{position:fixed;left:0;right:0;bottom:0;background:var(--tarjeta);border-top:1px solid var(--borde);box-shadow:0 -4px 16px #0002;padding:12px 0;z-index:5}
.barra .wrap{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.barra .esp{flex:1;font-size:14px}
table.ficheros{width:100%;border-collapse:collapse;font-size:14px}
table.ficheros td{padding:6px 10px;border-bottom:1px solid var(--borde)}
table.ficheros td.t{text-align:right;color:var(--suave);white-space:nowrap}
.toast{position:fixed;top:16px;right:16px;background:var(--verde);color:#fff;padding:12px 18px;border-radius:10px;font-weight:600;z-index:9;box-shadow:0 6px 20px #0004}
'''

PAGINA_INICIO = r'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Comparativa de ofertas</title><style>''' + CSS + r'''</style></head><body>
<header class="top"><div class="wrap"><div><h1>Comparativa de ofertas</h1><div class="sub">Licitación + presupuestos de proveedores → BC3 para m4PRO y Excel de comparación</div></div></div></header>
<main class="wrap">
<div id="formulario">
<p class="explica">Subes lo que tienes y el programa empareja cada línea de cada oferta con su partida de la licitación. <b>No decide por ti</b>: te enseña lo dudoso para que lo confirmes, y al final te da un .zip con los ficheros.</p>
<div class="pasos">
 <div class="card"><h2 style="margin-top:0"><span class="num">1</span>Licitación</h2>
  <p class="explica">El presupuesto original (BC3 exportado de m4PRO, o Excel con el formato conocido).</p>
  <div class="drop" id="dropLic"><b>Suelta aquí la licitación</b>o haz clic para elegirla</div>
  <input type="file" id="inLic" accept=".bc3,.xlsx,.xlsm,.pdf" hidden><div id="listaLic"></div></div>
 <div class="card"><h2 style="margin-top:0"><span class="num">2</span>Presupuestos de proveedores</h2>
  <p class="explica">Uno o varios (PDF de cada proveedor, o Excel). Puedes soltarlos todos a la vez.</p>
  <div class="drop" id="dropOf"><b>Suelta aquí los presupuestos</b>o haz clic para elegirlos</div>
  <input type="file" id="inOf" accept=".bc3,.xlsx,.xlsm,.pdf" multiple hidden><div id="listaOf"></div></div>
</div>
<div id="err"></div>
<button class="btn primario" id="go" disabled>Comparar ofertas</button>
<div class="info" style="margin-top:18px"><b>Qué obtendrás (.zip):</b> comparativa.xlsx (todos los proveedores juntos) · una carpeta por proveedor con su BC3 para importar en m4PRO, emparejamiento.xlsx y diferencias.xlsx · LEEME.txt · tus originales.</div>
<h2>Trabajos anteriores</h2><div class="previos" id="previos"><small>Cargando…</small></div>
</div>
<div class="card progreso" id="progreso"><div class="rueda"></div><div id="msg" style="font-weight:600">Empezando…</div>
<div class="explica" style="margin-top:6px">Leer los PDF y emparejar puede tardar un minuto. No cierres esta pestaña.</div></div>
</main>
<script>
const $=id=>document.getElementById(id);
let lic=null, ofs=[];
const tam=b=>b>1048576?(b/1048576).toFixed(1)+' MB':Math.max(1,Math.round(b/1024))+' KB';
function lista(el,arr,quitar){el.innerHTML='';arr.forEach((f,i)=>{const d=document.createElement('div');d.className='fichero';
 d.innerHTML='<span class="n"></span><span class="t">'+tam(f.size)+'</span><button title="Quitar">×</button>';
 d.querySelector('.n').textContent=f.name;d.querySelector('button').onclick=()=>quitar(i);el.appendChild(d)})}
function pintar(){lista($('listaLic'),lic?[lic]:[],()=>{lic=null;pintar()});lista($('listaOf'),ofs,i=>{ofs.splice(i,1);pintar()});
 $('go').disabled=!(lic&&ofs.length)}
function zona(drop,input,alAnadir){drop.onclick=()=>input.click();input.onchange=()=>{alAnadir([...input.files]);input.value='';pintar()};
 ['dragenter','dragover'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('sobre')}));
 ['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('sobre')}));
 drop.addEventListener('drop',ev=>{alAnadir([...ev.dataTransfer.files]);pintar()})}
zona($('dropLic'),$('inLic'),fs=>{if(fs.length)lic=fs[0]});
zona($('dropOf'),$('inOf'),fs=>{fs.forEach(f=>{if(!ofs.some(o=>o.name===f.name&&o.size===f.size))ofs.push(f)})});
$('go').onclick=async()=>{
 $('err').innerHTML='';const fd=new FormData();fd.append('licitacion',lic,lic.name);ofs.forEach(f=>fd.append('ofertas',f,f.name));
 $('formulario').style.display='none';$('progreso').style.display='block';
 try{const r=await fetch('/crear',{method:'POST',body:fd});const j=await r.json();if(j.error)throw new Error(j.error);
  const t=setInterval(async()=>{const e=await (await fetch('/estado/'+j.token)).json();$('msg').textContent=e.msg||'';
   if(e.estado==='listo'){clearInterval(t);location='/trabajo/'+e.id}
   if(e.estado==='error'){clearInterval(t);fallo(e.msg)}},700)}
 catch(e){fallo(e.message)}};
function fallo(m){$('progreso').style.display='none';$('formulario').style.display='block';const d=document.createElement('div');d.className='error';d.textContent=m;$('err').innerHTML='';$('err').appendChild(d)}
fetch('/trabajos.json').then(r=>r.json()).then(l=>{const p=$('previos');p.innerHTML='';if(!l.length){p.innerHTML='<small>Todavía no hay ninguno.</small>';return}
 l.forEach(t=>{const a=document.createElement('a');a.href='/trabajo/'+t.id;a.innerHTML='<span></span><small></small>';a.children[0].textContent=t.fecha+' · '+t.proveedores.join(', ');a.children[1].textContent='abrir →';p.appendChild(a)})});
pintar();
</script></body></html>'''

PAGINA_TRABAJO = r'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Comparativa de ofertas</title><style>''' + CSS + r'''</style></head><body>
<header class="top"><div class="wrap"><div><h1 id="titulo">Comparativa de ofertas</h1><div class="sub" id="sub"></div></div><div class="espacio"></div>
<button class="btn claro" id="anadir" title="Ha llegado otro presupuesto: se suma a esta comparativa sin repetir lo anterior">+ Añadir presupuesto</button><input type="file" id="inAnadir" accept=".bc3,.xlsx,.xlsm,.pdf" multiple hidden><a class="btn claro" href="/">Nueva comparativa</a><a class="btn primario" id="zip" href="#">⬇ Descargar .zip</a></div></header>
<main class="wrap"><div id="contenido"><div class="card progreso" style="display:block"><div class="rueda"></div>Cargando…</div></div></main>
<div class="card progreso" id="overlay" style="position:fixed;inset:0;z-index:20;border-radius:0;align-items:center;justify-content:center;flex-direction:column;background:var(--fondo)"><div class="rueda"></div><div id="ovMsg" style="font-weight:600">Trabajando…</div><div class="explica" style="margin-top:6px">No cierres esta pestaña.</div></div>
<div class="barra" id="barra" style="display:none"><div class="wrap"><div class="esp" id="barraTxt"></div>
<button class="btn" id="descartar">Descartar cambios</button><button class="btn primario" id="aplicar">Aplicar y regenerar ficheros</button></div></div>
<script>
const ID=location.pathname.split('/')[2];
const eur=v=>v==null?'—':new Intl.NumberFormat('es-ES',{style:'currency',currency:'EUR'}).format(v);
const nm=v=>v==null?'—':new Intl.NumberFormat('es-ES',{maximumFractionDigits:3}).format(v);
const pc=v=>(v>=0?'+':'−')+Math.abs(v).toFixed(1).replace('.',',')+' %';
function h(t,p,...k){const e=document.createElement(t);for(const[a,v]of Object.entries(p||{})){if(a==='class')e.className=v;else if(a.startsWith('on'))e[a]=v;else if(v!==false&&v!=null)e.setAttribute(a,v)}
 k.flat().forEach(x=>{if(x==null||x===false)return;e.append(x.nodeType?x:document.createTextNode(x))});return e}
let D=null,SEL={},ORIG={},act=0,filtro='dudosas',LP={};
async function cargar(){
 const r=await fetch('/trabajo/'+ID+'/datos.json');D=await r.json();
 if(D.error){document.getElementById('contenido').replaceChildren(h('div',{class:'error'},D.error));return}
 LP={};D.lic_partidas.forEach(l=>LP[l.n]=l);SEL={};ORIG={};
 D.proveedores.forEach(p=>{SEL[p.id]={};ORIG[p.id]={};p.filas.forEach(f=>{SEL[p.id][f.n]=f.elegida;ORIG[p.id][f.n]=f.elegida})});
 if(act>=D.proveedores.length)act=0;pintar()}
document.getElementById('anadir').onclick=()=>{
 if(nCambios()&&!confirm('Tienes cambios sin aplicar. Si añades un presupuesto ahora se perderán.\n\n¿Continuar?'))return;
 document.getElementById('inAnadir').click()};
document.getElementById('inAnadir').onchange=async e=>{
 const fs=[...e.target.files];e.target.value='';if(!fs.length)return;
 const fd=new FormData();fs.forEach(f=>fd.append('ofertas',f,f.name));
 await tarea('/trabajo/'+ID+'/anadir',fd,'Presupuesto añadido: la comparativa incluye ya todos los proveedores')};
function esperar(token){return new Promise((ok,ko)=>{const t=setInterval(async()=>{
 const e=await(await fetch('/estado/'+token)).json();document.getElementById('ovMsg').textContent=e.msg||'';
 if(e.estado==='listo'){clearInterval(t);ok()}if(e.estado==='error'){clearInterval(t);ko(new Error(e.msg))}},700)})}
async function tarea(url,cuerpo,mensaje){
 const ov=document.getElementById('overlay');ov.style.display='flex';document.getElementById('ovMsg').textContent='Subiendo…';
 try{const r=await fetch(url,{method:'POST',body:cuerpo});const j=await r.json();if(j.error)throw new Error(j.error);
  await esperar(j.token);await cargar();toast(mensaje)}
 catch(e){await cargar();document.getElementById('contenido').prepend(h('div',{class:'error'},'No se ha podido: '+e.message))}
 finally{ov.style.display='none'}}
async function quitar(p){
 if(nCambios()&&!confirm('Tienes cambios sin aplicar que se perderán.\n\n¿Continuar?'))return;
 if(!confirm('¿Quitar el presupuesto de '+p.nombre+' de la comparativa? Se borra su carpeta (el original que subiste, no).'))return;
 const ov=document.getElementById('overlay');ov.style.display='flex';document.getElementById('ovMsg').textContent='Rehaciendo la comparativa…';
 try{const r=await fetch('/trabajo/'+ID+'/quitar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({proveedor:p.id})});
  const j=await r.json();if(j.error)throw new Error(j.error);act=0;await cargar();toast('Presupuesto quitado')}
 catch(e){document.getElementById('contenido').prepend(h('div',{class:'error'},'No se ha podido quitar: '+e.message))}
 finally{ov.style.display='none'}}
const cambiado=(pid,n)=>SEL[pid][n]!==ORIG[pid][n];
function duplicados(pid){const m={};Object.entries(SEL[pid]).forEach(([on,ln])=>{if(ln!=null)(m[ln]=m[ln]||[]).push(+on)});
 const d={};Object.entries(m).forEach(([ln,l])=>{if(l.length>1)l.forEach(o=>d[o]=ln)});return d}
const nCambios=()=>D.proveedores.reduce((s,p)=>s+p.filas.filter(f=>cambiado(p.id,f.n)).length,0);
const nDup=()=>D.proveedores.reduce((s,p)=>s+Object.keys(duplicados(p.id)).length,0);
function pintar(){
 document.getElementById('titulo').textContent='Comparativa de ofertas';
 document.getElementById('sub').textContent=(D.licitacion||'Licitación')+' · '+D.proveedores.length+' proveedor'+(D.proveedores.length==1?'':'es');
 document.getElementById('zip').href='/trabajo/'+ID+'/descargar.zip';
 const c=document.getElementById('contenido');c.replaceChildren();
 // --- tarjetas
 const imp=D.proveedores.map(p=>p.resumen.importe_proveedor),minimo=Math.min(...imp);
 c.append(h('h2',{style:'margin-top:0'},'Resumen'));
 c.append(h('div',{class:'kpis'},[h('div',{class:'kpi',style:'border-top-color:#667085'},h('div',{class:'et'},'Cliente (licitación)'),h('div',{class:'valor'},eur(D.cliente_total)),h('div',{class:'nota'},'Precio máximo de las '+D.n_comparadas+' partidas comparadas.',h('br'),'Es la referencia: cada oferta se compara con ella.'))].concat(D.proveedores.map((p,i)=>{
  const r=p.resumen,n={seguro:0,revisar:0,'sin pareja':0};p.filas.forEach(f=>n[f.estado]++);
  return h('div',{class:'kpi'+(imp[i]===minimo&&imp.length>1?' mejor':'')},
   h('div',{class:'et'},p.nombre+(imp[i]===minimo&&imp.length>1?'  ·  importe más bajo':'')),
   h('div',{class:'valor'},eur(r.importe_proveedor)),
   h('div',{class:'nota'},(r.diferencia_pct!=null?pc(r.diferencia_pct)+' frente al Cliente ('+eur(r.importe_licitacion)+')':''),h('br'),
    r.partidas+' partidas · '+n.seguro+' seguras · '+n.revisar+' a revisar · '+n['sin pareja']+' sin pareja'),
   h('div',{style:'margin-top:8px;display:flex;gap:6px;flex-wrap:wrap'},
    p.caducada?h('span',{class:'chip mal'},'Oferta CADUCADA ('+p.validez+')'):null,
    p.cuadra===false?h('span',{class:'chip mal'},'Total impreso no cuadra'):(p.cuadra?h('span',{class:'chip seguro'},'Total cuadra'):null)),
   h('div',{class:'nota',style:'margin-top:6px'},p.condiciones))}))));
 // --- avisos
 const av=D.proveedores.flatMap(p=>p.avisos.map(a=>[p.nombre,a]));
 c.append(h('h2',{},'A tener en cuenta antes de elegir'));
 c.append(...(av.length?av.map(([n,a])=>h('div',{class:'aviso'},h('b',{},n+' — '+a.nivel.toUpperCase()+': '),a.texto)):[h('div',{class:'ok'},'Sin avisos.')]));
 c.append(h('div',{class:'info'},'La elección del proveedor es tuya: el programa solo muestra importes, diferencias y avisos.'));
 // --- revisión
 c.append(h('h2',{},'Revisión del emparejamiento'));
 c.append(h('p',{class:'explica'},'Cada línea de la oferta se ha asignado a una partida de la licitación. Lo seguro ya está bien; mira lo amarillo y lo rojo, y cambia la asignación si no es la correcta. Después pulsa «Aplicar y regenerar».'));
 c.append(h('div',{class:'tabs'},D.proveedores.map((p,i)=>h('button',{class:'tab'+(i===act?' act':''),onclick:()=>{act=i;pintar()}},p.nombre)),h('span',{style:'flex:1'}),D.proveedores.length>1?h('button',{class:'pill',style:'align-self:center;margin-bottom:4px',onclick:()=>quitar(D.proveedores[act])},'Quitar este presupuesto'):null));
 const p=D.proveedores[act],dup=duplicados(p.id);
 const dudosa=f=>f.estado!=='seguro'||cambiado(p.id,f.n)||dup[f.n]!=null;
 const cuenta={dudosas:p.filas.filter(dudosa).length,todas:p.filas.length,cambiadas:p.filas.filter(f=>cambiado(p.id,f.n)).length};
 c.append(h('div',{class:'filtros'},[['dudosas','A revisar'],['todas','Todas'],['cambiadas','Cambiadas por ti']].map(([k,t])=>
  h('button',{class:'pill'+(filtro===k?' act':''),onclick:()=>{filtro=k;pintar()}},t+' ('+cuenta[k]+')'))));
 const vis=p.filas.filter(f=>filtro==='todas'||(filtro==='dudosas'&&dudosa(f))||(filtro==='cambiadas'&&cambiado(p.id,f.n)));
 if(!vis.length)c.append(h('div',{class:'ok'},filtro==='cambiadas'?'No has cambiado nada.':'Nada que revisar en este proveedor.'));
 vis.forEach(f=>c.append(fila(p,f,dup)));
 // --- ficheros
 c.append(h('h2',{},'Ficheros generados'));
 c.append(h('p',{class:'explica'},'Están en: '+D.carpeta));
 c.append(h('div',{class:'card'},h('table',{class:'ficheros'},D.ficheros.map(f=>h('tr',{},h('td',{},h('a',{href:'/trabajo/'+ID+'/f/'+f.ruta.split('/').map(encodeURIComponent).join('/')},f.ruta)),h('td',{class:'t'},(f.tam/1024).toFixed(0)+' KB'))))));
 barra()}
function fila(p,f,dup){
 const sel=SEL[p.id][f.n],mano=sel!==(f.propuesta?f.propuesta.n:null);
 const ops=[];if(f.propuesta)ops.push([f.propuesta.n,'Propuesta: '+f.propuesta.n+' · '+f.propuesta.desc.slice(0,70)]);
 f.alternativas.forEach(a=>ops.push([a.n,'Candidata '+a.n+' ('+Math.round((a.parecido||0)*100)+'%) · '+a.ruta+' · '+a.desc.slice(0,70)+' · '+(a.motivo||'revisar')]));
 if(sel!=null&&!ops.some(o=>o[0]===sel))ops.push([sel,'Elegida: '+(LP[sel]?LP[sel].etiqueta:sel)]);
 ops.push(['','— No incluir esta línea —'],['otra','Otra partida (escribir nº)…']);
 const s=h('select',{onchange:e=>{const v=e.target.value;if(v==='otra'){f._otra=true;pintarFila()}else{SEL[p.id][f.n]=v===''?null:+v;pintar()}}},
  ops.map(o=>h('option',{value:o[0],selected:(o[0]===''?sel==null&&!f._otra:o[0]===sel&&!f._otra)||(o[0]==='otra'&&f._otra)},o[1])));
 function pintarFila(){pintar()}
 const l=sel!=null?LP[sel]:null;
 const det=l?h('div',{class:'det'},'Licitación nº '+l.n+' · cant. '+nm(l.cant)+' · precio '+eur(l.precio)+'  →  oferta '+eur(f.precio)+
   (l.precio&&f.precio!=null?' ('+pc((f.precio/l.precio-1)*100)+')':''),
   f.cant!=null&&l.cant!==f.cant?h('span',{class:'mal'},'  ⚠ cantidad distinta: oferta '+nm(f.cant)):null):h('div',{class:'det'},'Esta línea no entrará en el resultado.');
 const otra=f._otra?h('input',{class:'otra',list:'lp',placeholder:'Escribe el nº o busca por texto…',
   onchange:e=>{const n=parseInt(e.target.value,10);if(LP[n]){SEL[p.id][f.n]=n;f._otra=false;pintar()}else e.target.value=''}}):null;
 const ch=cambiado(p.id,f.n)||mano?'mano':(f.estado==='sin pareja'?'sinpareja':f.estado);
 const etiqueta={seguro:'seguro',revisar:'revisar',sinpareja:'sin pareja',mano:'elegido a mano'}[ch];
 return h('div',{class:'fila '+ch+(dup[f.n]!=null?' dup':'')},
  h('div',{},h('div',{},h('span',{class:'chip '+ch},etiqueta),'  ',h('span',{class:'meta'},'Línea '+f.n+' · cant. '+nm(f.cant)+' · '+eur(f.precio))),
   h('div',{class:'d'},f.desc),h('div',{class:'meta'},f.ruta),f.motivos.map(m=>h('div',{class:'motivo'},'• '+m))),
  h('div',{},s,otra,det,dup[f.n]!=null?h('div',{class:'det mal'},'⚠ La partida '+dup[f.n]+' de la licitación está asignada a más de una línea: deja solo una.'):null))}
function barra(){
 let dl=document.getElementById('lp');if(!dl){dl=h('datalist',{id:'lp'});document.body.append(dl)}
 if(!dl.children.length)D.lic_partidas.forEach(l=>dl.append(h('option',{value:l.n+' · '+l.etiqueta.split(' · ').slice(1).join(' · ')})));
 const n=nCambios(),d=nDup(),b=document.getElementById('barra');b.style.display=(n||d)?'block':'none';
 document.getElementById('barraTxt').textContent=d?('⚠ Hay '+d+' línea(s) con partida repetida: corrígelas para poder aplicar.'):(n+' cambio'+(n==1?'':'s')+' sin aplicar. El .zip no los incluye hasta que pulses «Aplicar».');
 document.getElementById('aplicar').disabled=!!d||!n}
document.getElementById('descartar').onclick=()=>{D.proveedores.forEach(p=>{SEL[p.id]={...ORIG[p.id]}});pintar()};
document.getElementById('aplicar').onclick=async()=>{
 const b=document.getElementById('aplicar');b.disabled=true;b.textContent='Regenerando…';
 const el={};D.proveedores.forEach(p=>{el[p.id]={};Object.entries(SEL[p.id]).forEach(([on,ln])=>{if(ln!=null)el[p.id][on]=ln})});
 try{const r=await fetch('/trabajo/'+ID+'/aplicar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({elecciones:el})});
  const j=await r.json();if(j.error)throw new Error(j.error);await cargar();toast('Ficheros regenerados con tus cambios')}
 catch(e){document.getElementById('contenido').prepend(h('div',{class:'error'},'No se ha podido aplicar: '+e.message))}
 b.textContent='Aplicar y regenerar ficheros';barra()};
function toast(t){const e=h('div',{class:'toast'},t);document.body.append(e);setTimeout(()=>e.remove(),3200)}
cargar();
</script></body></html>'''
