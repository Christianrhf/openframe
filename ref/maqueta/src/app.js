'use strict';
const $=id=>document.getElementById(id);
const FPS=24,TOTAL=1440,SECS=60;
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const ico=(n,c)=>'<svg class="ico '+(c||'')+'" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="#i-'+n+'"/></svg>';
let frame=300,playing=false,speed=1,last=0,carry=0,filterResolved=false,replyTarget=null;
let drawing=false,tool='pen',shape=null,start=null,strokeWidth=5,drawBefore='';
let selId=null,zoom=1,viewStart=0,notePage=0,notePageCount=1;

function tc(f){const s=Math.floor(f/FPS);return '00:'+String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0')+':'+String(f%FPS).padStart(2,'0');}
const cards=()=>[...document.querySelectorAll('.item')];
const byId=id=>document.querySelector('.item[data-item="'+id+'"]');
let toastTimer;function toast(m){$('toast').textContent=m;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3500);}

/* ── Historial: Ctrl+Z deshace el ÚLTIMO cambio, sea el que sea ───
   Trazo, borrar dibujos, nota nueva, respuesta, resolver/reabrir, marcar revisado.
   Cada cambio registra cómo se deshace y cómo se rehace; un cambio nuevo vacía el «rehacer». */
const hist=[],future=[];
function syncHist(){$('undoDrawing').disabled=!hist.length;$('redoDrawing').disabled=!future.length;}
function commit(label,undo,redo){hist.push({label,undo,redo});future.length=0;syncHist();}
function afterChange(){refreshNotes();update();}
function undoLast(){const a=hist.pop();if(!a){toast('No hay nada que deshacer.');return;}a.undo();future.push(a);afterChange();syncHist();toast('Deshecho: '+a.label+'. Ctrl+Mayús+Z lo rehace.');}
function redoLast(){const a=future.pop();if(!a){toast('No hay nada que rehacer.');return;}a.redo();hist.push(a);afterChange();syncHist();toast('Rehecho: '+a.label+'.');}
const cardName=c=>c.dataset.label.split(' · ')[0];

/* ── Reproducción ───────────────────────────────────────────── */
function setPlaying(v){
  playing=v;last=0;carry=0;
  $('videoPlayIcon').setAttribute('href',v?'#i-pause':'#i-play');
  $('bandPlayIcon').setAttribute('href',v?'#i-pause':'#i-play');
  $('video').classList.toggle('playing',v);
  const hint=(v?'Pausar':'Reproducir')+' (Espacio · K pausa · L reproduce)';
  [$('videoPlay'),$('bandPlay')].forEach(b=>{b.title=hint;b.setAttribute('aria-label',hint);});
}
function togglePlay(){if(frame>=TOTAL)seek(0);setPlaying(!playing);}
$('videoPlay').onclick=e=>{e.stopPropagation();togglePlay();};
$('bandPlay').onclick=e=>{e.stopPropagation();togglePlay();};
$('video').onclick=e=>{if(drawing)return;if(e.target.closest('#videoPlay,.vpill'))return;togglePlay();};
function tick(now){if(playing){if(last){carry+=(now-last)/1000*FPS*speed;const w=Math.floor(carry);carry-=w;if(w){frame=Math.min(TOTAL,frame+w);ensureVisible();update();if(frame>=TOTAL)setPlaying(false);}}last=now;}requestAnimationFrame(tick);}
requestAnimationFrame(tick);
function seek(sec){frame=clamp(Math.round(sec*FPS),0,TOTAL);ensureVisible();update();}
$('previous').onclick=()=>{setPlaying(false);frame=Math.max(0,frame-1);ensureVisible();update();};
$('next').onclick=()=>{setPlaying(false);frame=Math.min(TOTAL,frame+1);ensureVisible();update();};
$('backSecond').onclick=()=>{setPlaying(false);seek(frame/FPS-1);};
$('forwardSecond').onclick=()=>{setPlaying(false);seek(frame/FPS+1);};
$('scrubber').oninput=e=>{frame=Number(e.target.value);update();};
const speedSteps=[[1,'normal'],[1.5,'rápido'],[2,'muy rápido']];
$('speed').onclick=()=>{
  const [v,w]=speedSteps[(speedSteps.findIndex(s=>s[0]===speed)+1)%speedSteps.length];speed=v;
  const label=String(v).replace('.',',')+'×',chip=$('speed');
  chip.querySelector('b').textContent=label;chip.querySelector('small').textContent=w;chip.classList.toggle('fast',v!==1);
  const h='Velocidad de reproducción: '+w+' ('+label+'). Pulsar para cambiar';chip.title=h;chip.setAttribute('aria-label',h);
};

/* ── Línea de tiempo: ventana visible y zoom ─────────────────── */
const span=()=>SECS/zoom;
function ensureVisible(){const t=frame/FPS,s=span();if(t<viewStart||t>viewStart+s)viewStart=clamp(t-s*.25,0,SECS-s);}
function renderTimeline(){
  const s=span();viewStart=clamp(viewStart,0,SECS-s);
  const sc=$('scrubber');sc.min=Math.round(viewStart*FPS);sc.max=Math.round((viewStart+s)*FPS);sc.value=frame;sc.setAttribute('aria-valuetext',tc(frame));
  document.querySelectorAll('#ruler span').forEach((e,i)=>{
    e.style.left=(i/6*100)+'%';
    const f=Math.round((viewStart+s*i/6)*FPS);e.textContent=s<20?tc(f).slice(3):tc(f).slice(3,8);
  });
  renderMarkers();
  const p=(frame/FPS-viewStart)/s*100;
  $('playhead').style.left=clamp(p,0,100)+'%';
  $('playhead').style.visibility=(p<0||p>100)?'hidden':'visible';
  $('played').style.width=clamp(p,0,100)+'%';
  $('zoomOut').disabled=zoom<=1;$('zoomFit').disabled=zoom<=1;$('zoomIn').disabled=zoom>=8;
  renderRanges();
}
/* HOOK · dueño: agente B (densidad). Coloca los marcadores de los dos carriles según la ventana visible,
   y agrupa los que quedarían solapados en un .cluster-marker (ver B1/B2 en docs/TASK-B.md). */
function renderMarkers(){
  const s=span();
  document.querySelectorAll('.cluster-marker').forEach(c=>c.remove());
  document.querySelectorAll('.marker').forEach(m=>{
    const x=(Number(m.dataset.frame)/FPS-viewStart)/s*100;
    m.style.left=x+'%';m.hidden=x<-1||x>101;delete m.dataset.clustered;m.removeAttribute('title');
  });
  /* Lecturas (getBoundingClientRect) de los dos carriles antes de escribir nada: un solo reflow. */
  const plans=['laneNotes','laneChanges'].map(id=>planClusters($(id)));
  plans.forEach(apply=>apply());
  updateLaneTotals();
}
/* selId se actualiza en syncSel(), que corre DESPUES de renderTimeline() dentro de update():
   aqui no podemos fiarnos de selId (va un render por detras) y recalculamos la seleccion viva.
   H · misma cadena que syncSel() (exacto > seleccionada ya en su tramo > primera en su tramo),
   SIN llamar a syncSel() (muta selId y correría fuera de orden). */
function liveSelId(){
  const cur=selId&&byId(selId);
  if(cur&&!cur.hidden&&Number(cur.dataset.frame)===frame)return selId;
  const exact=cards().find(c=>!c.hidden&&Number(c.dataset.frame)===frame);
  if(exact)return exact.dataset.item;
  if(cur&&!cur.hidden&&aInRange(cur))return selId;
  const inRange=cards().find(c=>!c.hidden&&aInRange(c));
  return inRange?inRange.dataset.item:null;
}
/* H · el seleccionado participa del agrupado como cualquier otro: si acabaría solapado con un grupo o con
   otro marcador suelto, se absorbe en ese grupo (.has-sel) en vez de quedar suelto encima tapándolo.
   Para medir el solape real se le aplica .sel un instante (si no la tenía) ANTES de leer getBoundingClientRect:
   syncSel() se la pondrá de verdad más tarde, así que hay que agrupar según el tamaño que tendrá, no el que tiene ahora. */
function planClusters(lane){
  const live=liveSelId();
  const liveEl=live&&lane.querySelector(':scope > .marker[data-item="'+live+'"]');
  const hadSel=!!(liveEl&&liveEl.classList.contains('sel'));
  if(liveEl&&!hadSel)liveEl.classList.add('sel');
  const real=[...lane.querySelectorAll(':scope > .marker')].filter(m=>!m.hidden);
  const items=real.map(m=>({m,r:m.getBoundingClientRect(),live:m.dataset.item===live})).sort((a,b)=>a.r.left-b.r.left);
  if(liveEl&&!hadSel)liveEl.classList.remove('sel');
  if(items.length<2)return ()=>{};
  const groups=[];let cur=[items[0]];
  for(let i=1;i<items.length;i++){
    const prev=cur[cur.length-1],it=items[i];
    if(it.r.left-prev.r.right<4)cur.push(it);else{groups.push(cur);cur=[it];}
  }
  groups.push(cur);
  const multi=groups.filter(g=>g.length>1);
  if(!multi.length)return ()=>{};
  return ()=>multi.forEach(g=>{
    const hasSel=g.some(it=>it.live);
    const members=g.map(it=>it.m);
    if(hasSel)members.sort((a,b)=>(a.dataset.item===live?-1:b.dataset.item===live?1:0));   /* el absorbido va primero en la vista previa */
    members.forEach(m=>{m.hidden=true;m.dataset.clustered='true';});
    lane.appendChild(buildClusterMarker(members,hasSel?live:null));
  });
}
/* HOOK · dueño: agente A (anotaciones). Dibuja las barras de las notas con tramo (entrada→salida).
   Una barra por nota con data-out, recortada a la ventana visible; el marcador circular sigue en la entrada, por encima. */
function renderRanges(){
  const s=span(),lane=$('laneNotes'),live=new Set();
  cards().forEach(c=>{
    if(c.dataset.kind==='change'||!c.dataset.out)return;
    const id=c.dataset.item;live.add(id);
    let bar=lane.querySelector('.a-rangebar[data-item="'+id+'"]');
    if(!bar){
      bar=document.createElement('button');bar.type='button';bar.className='a-rangebar';bar.dataset.item=id;bar.innerHTML='<i></i>';
      lane.insertBefore(bar,lane.firstChild);   /* antes que los marcadores: el círculo se pinta encima de la barra */
    }
    const i=Number(c.dataset.frame),o=Number(c.dataset.out);
    const L=(i/FPS-viewStart)/s*100,R=(o/FPS-viewStart)/s*100,l=clamp(L,0,100),r=clamp(R,0,100);
    bar.hidden=!!c.hidden||R<0||L>100;
    bar.style.left=l+'%';bar.style.width=(r-l)+'%';
    const t='Tramo de '+c.dataset.label+' · '+tc(i)+' → '+tc(o);
    bar.title=t;bar.setAttribute('aria-label',t);
  });
  lane.querySelectorAll('.a-rangebar').forEach(b=>{if(!live.has(b.dataset.item))b.remove();});
}
function buildClusterMarker(members,selId){
  const kind=members[0].classList.contains('note')?'note':'change';
  const avg=members.reduce((sum,m)=>sum+parseFloat(m.style.left),0)/members.length;
  const frames=members.map(m=>Number(m.dataset.frame)).sort((a,b)=>a-b);
  const ids=members.map(m=>m.dataset.item);
  const cm=document.createElement('button');
  cm.type='button';cm.className='cluster-marker '+kind+(selId?' has-sel':'');cm.style.left=avg+'%';
  cm.dataset.ids=ids.join(',');cm.dataset.kind=kind;
  if(selId)cm.dataset.selId=selId;
  cm.innerHTML=kind==='change'?'<b>'+members.length+'</b>':String(members.length);
  const lbl=(kind==='note'?'Grupo de '+members.length+' notas, ':'Grupo de '+members.length+' cambios, ')+tc(frames[0])+' a '+tc(frames[frames.length-1])+(selId?'. Incluye la seleccionada':'')+'. Pulsar para acercar';
  cm.title='';cm.setAttribute('aria-label',lbl);
  cm.onclick=e=>{e.stopPropagation();zoomToCluster(members.slice());};
  return cm;
}
function stillGroupedAs(ids){
  return [...document.querySelectorAll('.cluster-marker')].some(cm=>{
    const cids=cm.dataset.ids.split(',');return ids.every(id=>cids.includes(id));
  });
}
/* B1 · clic en un grupo: acerca centrando el grupo hasta separar los miembros (máx. x8); si sigue junto, lista. */
function zoomToCluster(members){
  const frames=members.map(m=>Number(m.dataset.frame)).sort((a,b)=>a-b);
  const centerSec=(frames[0]+frames[frames.length-1])/2/FPS;
  const ids=members.map(m=>m.dataset.item);
  while(zoom<8){
    zoom=clamp(zoom*2,1,8);viewStart=clamp(centerSec-span()/2,0,SECS-span());renderTimeline();
    if(!stillGroupedAs(ids))return;
  }
  viewStart=clamp(centerSec-span()/2,0,SECS-span());renderTimeline();
  if(stillGroupedAs(ids))openClusterPop(members);
}
function laneTotalEls(){
  return [...document.querySelectorAll('.lane-label')].map(lbl=>{
    let t=lbl.querySelector('.lane-total');
    if(!t){t=document.createElement('span');t.className='lane-total';lbl.insertBefore(t,lbl.querySelector('.nav'));}
    return t;
  });
}
function updateLaneTotals(){
  const [tNotes,tChanges]=laneTotalEls();
  if(tNotes)tNotes.textContent=document.querySelectorAll('#laneNotes > .marker').length;
  if(tChanges)tChanges.textContent=document.querySelectorAll('#laneChanges > .marker').length;
}
function miniGlyph(card){
  if(card.dataset.kind==='change')return '<span class="mk mini change"><b>'+(card.querySelector('.mk b')?card.querySelector('.mk b').textContent:'')+'</b></span>';
  return '<span class="mk mini note">'+(card.querySelector('.mk')?card.querySelector('.mk').textContent.trim():'')+'</span>';
}
/* B1 · popover de lista cuando a x8 los miembros del grupo siguen juntos (fotograma a fotograma). */
let clusterPop=null;
function closeClusterPop(){if(clusterPop){clusterPop.remove();clusterPop=null;document.removeEventListener('pointerdown',clusterPopOutside,true);}}
function clusterPopOutside(e){if(clusterPop&&!clusterPop.contains(e.target))closeClusterPop();}
function openClusterPop(members){
  closeClusterPop();hidePreview();
  const ids=members.map(m=>m.dataset.item);
  const anchor=[...document.querySelectorAll('.cluster-marker')].find(cm=>stillGroupedAs(ids)&&ids.every(id=>cm.dataset.ids.split(',').includes(id)))||members[0];
  clusterPop=document.createElement('div');clusterPop.className='cluster-pop';clusterPop.setAttribute('role','listbox');clusterPop.setAttribute('aria-label','Marcadores agrupados');
  const live=liveSelId();
  members.forEach(m=>{
    const c=byId(m.dataset.item);if(!c)return;
    const who=c.querySelector('.item-who strong').textContent,txt=(c.querySelector('p')?c.querySelector('p').textContent:'').slice(0,40),sel=m.dataset.item===live;
    const b=document.createElement('button');b.type='button';b.setAttribute('role','option');b.setAttribute('aria-selected',String(sel));
    if(sel)b.classList.add('cp-sel');
    b.innerHTML=miniGlyph(c)+'<span class="cp-who">'+who+'</span><span class="cp-time">'+tc(Number(c.dataset.frame))+'</span><span class="cp-text">'+txt+'</span>'+(sel?'<span class="cp-sel-flag" title="Es la seleccionada" aria-label="Es la seleccionada">'+ico('eye','xs')+'</span>':'');
    b.onclick=ev=>{ev.stopPropagation();closeClusterPop();selectItem(m.dataset.item);};
    clusterPop.appendChild(b);
  });
  document.body.appendChild(clusterPop);
  const r=anchor.getBoundingClientRect();
  let left=r.left+r.width/2-clusterPop.offsetWidth/2,top=r.top-clusterPop.offsetHeight-8;
  if(top<8)top=r.bottom+8;
  left=clamp(left,8,innerWidth-8-clusterPop.offsetWidth);top=clamp(top,8,innerHeight-8-clusterPop.offsetHeight);
  clusterPop.style.left=left+'px';clusterPop.style.top=top+'px';
  setTimeout(()=>document.addEventListener('pointerdown',clusterPopOutside,true),0);
}
/* B2 · vista previa al pasar el ratón / foco por un marcador o un grupo ───────────────────────── */
let previewTimer=null,previewEl=null,scrubDragging=false;
function hidePreview(){
  clearTimeout(previewTimer);
  if(previewEl){previewEl.remove();previewEl=null;}
  document.querySelectorAll('[aria-describedby="mkPreview"]').forEach(e=>e.removeAttribute('aria-describedby'));
}
function previewRowsForGroup(ids,kind,selId){
  const shown=ids.slice(0,4).map(id=>{
    const c=byId(id);if(!c)return '';
    const who=c.querySelector('.item-who strong').textContent,txt=(c.querySelector('p')?c.querySelector('p').textContent:'').slice(0,40);
    const sel=id===selId;
    return '<div class="mp-row'+(sel?' mp-row-sel':'')+'">'+miniGlyph(c)+'<span>'+who+'</span><span class="mp-time">'+tc(Number(c.dataset.frame))+'</span>'+(sel?'<span class="mp-sel-flag" title="Es la seleccionada" aria-label="Es la seleccionada">'+ico('eye','xs')+'</span>':'')+'</div>';
  }).join('');
  const more=ids.length>4?'<div class="mp-more">+'+(ids.length-4)+' más</div>':'';
  return '<div class="mp-head">Grupo de '+ids.length+' '+(kind==='note'?'notas':'cambios')+'</div>'+shown+more;
}
function showPreviewFor(target){
  if(scrubDragging||drawing)return;
  hidePreview();
  const isCluster=target.classList.contains('cluster-marker');
  previewEl=document.createElement('div');previewEl.className='mk-preview';previewEl.id='mkPreview';previewEl.setAttribute('role','tooltip');
  if(isCluster){
    previewEl.innerHTML=previewRowsForGroup(target.dataset.ids.split(','),target.dataset.kind,target.dataset.selId||null);
  }else{
    const c=byId(target.dataset.item);if(!c){previewEl=null;return;}
    const who=c.querySelector('.item-who strong').textContent,type=c.dataset.kind==='change'?'Cambio':'Nota';
    const f=Number(c.dataset.frame),out=c.dataset.out?(' → '+tc(Number(c.dataset.out))):'';
    const txt=(c.querySelector('p')?c.querySelector('p').textContent:'').slice(0,110);
    previewEl.innerHTML='<div class="mp-head">'+miniGlyph(c)+'<span>'+who+' · '+type+'</span></div><div class="mp-time">'+tc(f)+out+'</div><div class="mp-text">'+txt+'</div>';
  }
  document.body.appendChild(previewEl);
  target.setAttribute('aria-describedby','mkPreview');
  positionPreview(previewEl,target);
}
function positionPreview(el,target){
  const r=target.getBoundingClientRect();
  let top=r.top-el.offsetHeight-8,left=r.left+r.width/2-el.offsetWidth/2;
  if(top<8)top=r.bottom+8;
  left=clamp(left,8,innerWidth-8-el.offsetWidth);top=clamp(top,8,innerHeight-8-el.offsetHeight);
  el.style.left=left+'px';el.style.top=top+'px';
}
document.addEventListener('mouseover',e=>{
  const t=e.target.closest&&e.target.closest('.marker,.cluster-marker');if(!t||t.hidden)return;
  clearTimeout(previewTimer);previewTimer=setTimeout(()=>showPreviewFor(t),120);
});
document.addEventListener('mouseout',e=>{
  const t=e.target.closest&&e.target.closest('.marker,.cluster-marker');if(!t)return;
  clearTimeout(previewTimer);hidePreview();
});
document.addEventListener('focusin',e=>{
  const t=e.target.closest&&e.target.closest('.marker,.cluster-marker');if(!t)return;
  clearTimeout(previewTimer);showPreviewFor(t);
});
document.addEventListener('focusout',e=>{
  const t=e.target.closest&&e.target.closest('.marker,.cluster-marker');if(!t)return;
  hidePreview();
});
$('scrubber').addEventListener('pointerdown',()=>{scrubDragging=true;hidePreview();});
addEventListener('pointerup',()=>{scrubDragging=false;});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeClusterPop();hidePreview();}});
function setZoom(z){zoom=clamp(z,1,8);viewStart=clamp(frame/FPS-span()/2,0,SECS-span());renderTimeline();}
$('zoomIn').onclick=()=>setZoom(zoom*2);$('zoomOut').onclick=()=>setZoom(zoom/2);$('zoomFit').onclick=()=>setZoom(1);

/* ── Selección: lo que se ve en pantalla es lo que se marca ───
   Una entrada está «en pantalla» cuando el fotograma mostrado ES el suyo.
   Si se mueve el fotograma, deja de estarlo y la marca se quita sola. */
function syncSel(){
  renderRanges();
  const cur=selId&&byId(selId);
  if(!(cur&&!cur.hidden&&Number(cur.dataset.frame)===frame)){
    /* A · el fotograma exacto gana; si no hay, vale la nota cuyo tramo contiene el fotograma (la ya seleccionada primero) */
    const m=cards().find(c=>!c.hidden&&Number(c.dataset.frame)===frame)
          ||(cur&&!cur.hidden&&aInRange(cur)?cur:null)
          ||cards().find(c=>!c.hidden&&aInRange(c));
    selId=m?m.dataset.item:null;
  }
  document.querySelectorAll('[data-item]').forEach(e=>{
    const on=e.dataset.item===selId;e.classList.toggle('sel',on);
    if(e.classList.contains('marker'))e.setAttribute('aria-pressed',String(on));
    else e.setAttribute('aria-current',String(on));
  });
  const pill=$('selPill');
  if(selId){pill.hidden=false;$('selPillText').textContent='Viendo: '+byId(selId).dataset.label;}else pill.hidden=true;
}
function selectItem(id){
  const el=byId(id);if(!el)return;
  if(el.hidden){
    if(el.dataset.resolved==='true')filterResolved=true;
    typeFilter='all';personFilter='all';drawingFilter=false;hideReviewed=false;searchQ='';
    $('searchInput').value='';syncFilterControlsUI();
    refreshNotes();
  }
  setPlaying(false);selId=id;frame=Number(el.dataset.frame);ensureVisible();update();goToPage(el);
}
function update(){
  const t=tc(frame);$('bandClock').textContent=t;$('noteTime').textContent=t;
  renderTimeline();syncSel();aSyncAnno();
}
document.addEventListener('click',e=>{
  const mk=e.target.closest&&e.target.closest('.marker');if(mk){selectItem(mk.dataset.item);return;}
  const go=e.target.closest&&e.target.closest('[data-goto]');if(go){e.stopPropagation();selectItem(go.dataset.goto);return;}
  const card=e.target.closest&&e.target.closest('.item');
  if(card&&!e.target.closest('.item-actions,.reply'))selectItem(card.dataset.item);
});
document.addEventListener('keydown',e=>{
  const c=e.target&&e.target.closest?e.target.closest('.item'):null;
  if(c&&e.target===c&&(e.key==='Enter'||e.key===' ')){e.preventDefault();selectItem(c.dataset.item);}
});
function jump(sel,dir){
  const fr=[...document.querySelectorAll(sel)].map(m=>Number(m.dataset.frame)).sort((a,b)=>a-b);
  const next=dir>0?fr.find(f=>f>frame):[...fr].reverse().find(f=>f<frame);
  const f=next!==undefined?next:(dir>0?fr[0]:fr[fr.length-1]);
  const mk=[...document.querySelectorAll(sel)].find(m=>Number(m.dataset.frame)===f);
  if(mk)selectItem(mk.dataset.item);
}
$('prevNote').onclick=()=>jump('.marker.note',-1);$('nextNote').onclick=()=>jump('.marker.note',1);
$('prevChange').onclick=()=>jump('.marker.change',-1);$('nextChange').onclick=()=>jump('.marker.change',1);

/* ── Conversación ───────────────────────────────────────────── */
function setBtn(btn,icon,text){btn.querySelector('use').setAttribute('href','#i-'+icon);btn.querySelector('span').textContent=text;}
/* HOOK · dueño: agente C (chat a escala). ¿Se muestra esta tarjeta en la vista actual? Pestaña + tipo + persona + dibujo + revisados + búsqueda. */
function cardVisible(c){return matchesFilters(c);}
function refreshNotes(){
  let open=0,done=0;
  cards().forEach(c=>{
    if(c.dataset.kind!=='change'){c.dataset.resolved==='true'?done++:open++;}
    c.hidden=!cardVisible(c);
  });
  document.querySelectorAll('.marker').forEach(m=>{
    const c=byId(m.dataset.item);
    m.classList.toggle('done',c.dataset.kind==='change'?c.dataset.reviewed==='true':c.dataset.resolved==='true');
    m.classList.toggle('filtered-out',c.hidden);
  });
  $('openCount').textContent=open;$('resolvedCount').textContent=done;
  const visible=cards().filter(c=>!c.hidden).length,scope=totalForScope();
  $('resultCount').textContent=visible+' de '+scope;
  $('countAll').textContent=cards().filter(c=>matchesFilters(c,'all')).length;
  $('countNotes').textContent=cards().filter(c=>matchesFilters(c,'note')).length;
  $('countChanges').textContent=cards().filter(c=>matchesFilters(c,'change')).length;
  const noResults=visible===0,active=hasActiveFilters();
  $('emptyNotes').hidden=!noResults;
  $('emptyNotesText').textContent=noResults?(active?'Ningún resultado':'No hay nada en esta vista.'):'';
  $('clearFiltersBtn').hidden=!(noResults&&active);
  syncFiltersDot();
  $('openTab').setAttribute('aria-selected',String(!filterResolved));$('resolvedTab').setAttribute('aria-selected',String(filterResolved));
  $('feed').setAttribute('aria-labelledby',filterResolved?'resolvedTab':'openTab');
  updateRoundPill();
  paginate();syncSel();
}
$('openTab').onclick=()=>{filterResolved=false;notePage=0;refreshNotes();};
$('resolvedTab').onclick=()=>{filterResolved=true;notePage=0;refreshNotes();};

function setReply(card){
  replyTarget=card;
  const who=card?card.querySelector('.item-who strong').textContent+' · '+(card.dataset.kind==='change'?'Cambio '+card.querySelector('.mk b').textContent:'Nota '+card.querySelector('.mk').textContent):null;
  $('composerLabel').textContent=card?'Responder a '+who:'Nueva nota';
  $('noteInput').placeholder=card?'Escribe tu respuesta en este hilo…':'Escribe una nota para el equipo…';
  $('noteForm').classList.toggle('replying',!!card);
  if(card)$('noteInput').focus();
}
$('cancelReply').onclick=()=>setReply(null);
$('noteInput').addEventListener('focus',()=>setPlaying(false));   /* la nota se ancla al fotograma visible: que no se mueva mientras escribes */
function setResolved(card,v){card.dataset.resolved=String(v);const b=card.querySelector('.resolve-btn');if(b)setBtn(b,v?'rotate-ccw':'circle-check',v?'Reabrir':'Resolver');}
function setReviewed(card,v){dSetDecision(card,v?'approved':null);}   /* compat: «revisado» = hay decisión (D) */
function wire(card){
  if(card.dataset.kind==='change')dWireChange(card);
  const rs=card.querySelector('.resolve-btn');
  if(rs)rs.onclick=e=>{e.stopPropagation();const prev=card.dataset.resolved==='true',v=!prev;setResolved(card,v);
    commit(cardName(card)+(v?' resuelta':' reabierta'),()=>setResolved(card,prev),()=>setResolved(card,v));refreshNotes();};
  card.querySelector('.reply-btn').onclick=e=>{e.stopPropagation();setReply(card);};
}
cards().forEach(wire);

/* HOOK · dueño: agente A (anotaciones). Construye la tarjeta y el marcador de una nota nueva. */
function makeNoteCard(n,f,text,opts){
  const id='n'+n,o=opts&&opts.out!=null?Number(opts.out):null,draw=!!(opts&&opts.drawing);
  const c=document.createElement('article');c.className='item note';c.dataset.item=id;c.dataset.kind='note';c.dataset.frame=f;c.dataset.resolved='false';c.dataset.label='Nota '+n+' · Lucía Méndez';c.tabIndex=0;
  if(o!==null)c.dataset.out=o;
  if(draw)c.dataset.drawing='true';
  c.innerHTML='<div class="item-top"><span class="mk note">'+n+'</span><div class="item-who"><strong>Lucía Méndez</strong><small>Nota</small></div><span class="ago">Ahora</span><span class="now">'+ico('eye','xs')+'En pantalla</span></div>'
    +'<div class="item-meta"><button class="time-link" title="'+(o!==null?'Ir a la entrada del tramo ('+tc(f)+' → '+tc(o)+')':'Ir a este fotograma')+'">'+ico('clock','xs')
      +(o!==null?aShort(f)+' → '+aShort(o):tc(f))+'</button>'
      +(o!==null?'<span class="a-dur">'+aDur(f,o)+'</span>':'')
      +(draw?'<span class="a-flag" title="Esta nota lleva un dibujo sobre su fotograma">'+ico('pen-line','xs')+'Dibujo</span>':'')
    +'</div><p></p>'
    +'<div class="item-actions"><button class="text-btn reply-btn">'+ico('corner-down-right','sm')+'Responder</button>'
      +(o!==null?'<button class="text-btn a-play-range" title="Reproducir solo el tramo de esta nota" aria-label="Reproducir solo el tramo de esta nota">'+ico('repeat-1','sm')+'Reproducir tramo</button>':'')
      +'<button class="text-btn resolve-btn">'+ico('circle-check','sm')+'<span>Resolver</span></button></div>';
  c.querySelector('p').textContent=text;
  const m=document.createElement('button');m.className='marker mk note';m.dataset.item=id;m.dataset.frame=f;m.textContent=n;
  if(o!==null)m.dataset.out=o;
  m.title='Nota '+n+' · Lucía Méndez · '+(o!==null?tc(f)+' → '+tc(o):tc(f));m.setAttribute('aria-label',m.title);m.setAttribute('aria-pressed','false');
  return {id,card:c,marker:m};
}
/* HOOK · dueño: agente A. Crea la nota con lo que haya en el composer (texto + dibujo del fotograma + tramo) y la registra en el historial. */
function addNote(text){
  const n=cards().filter(c=>c.dataset.kind==='note').length+1;
  const f=aNoteFrame(),out=(aIn!==null&&aOut!==null)?aOut:null,draw=drafts[f]||'';
  const {id,card:c,marker:m}=makeNoteCard(n,f,text,{out,drawing:!!draw});
  const after=cards().find(x=>Number(x.dataset.frame)>f);
  $('noteContent').insertBefore(c,after||$('emptyNotes'));wire(c);
  $('laneNotes').appendChild(m);filterResolved=false;
  const pin=aIn,pout=aOut;
  const attach=()=>{if(draw){noteDrawings[id]=draw;aSetDraft(f,'');}aIn=null;aOut=null;aSyncAnno();};
  attach();
  let nextEl=null;
  commit('Nota '+n+' añadida',
    ()=>{nextEl=c.nextElementSibling;c.remove();m.remove();if(selId===id)selId=null;
         if(draw){delete noteDrawings[id];aSetDraft(f,draw);}aIn=pin;aOut=pout;aSyncAnno();},
    ()=>{$('noteContent').insertBefore(c,nextEl&&nextEl.parentNode?nextEl:$('emptyNotes'));$('laneNotes').appendChild(m);attach();});
  setTimeout(()=>selectItem(id),0);
}
function addReply(text){
  const r=document.createElement('div');r.className='reply';
  r.innerHTML='<div class="item-top"><span class="avatar" style="width:20px;height:20px;font-size:8px">LM</span><strong>Lucía Méndez</strong><span class="ago">Ahora</span></div><p></p>';
  r.querySelector('p').textContent=text;
  const host=replyTarget;host.appendChild(r);setReply(null);
  commit('respuesta en '+cardName(host),()=>r.remove(),()=>host.appendChild(r));
}
$('noteForm').onsubmit=e=>{
  e.preventDefault();const text=$('noteInput').value.trim();
  const draw=!replyTarget&&!!drafts[aNoteFrame()];   /* A · un dibujo ya es una nota válida; sin dibujo y sin texto no se envía */
  if(!text&&!draw){toast('Escribe la nota o dibuja sobre el fotograma.');return;}
  if(replyTarget)addReply(text);else addNote(text||'(solo dibujo)');
  $('noteInput').value='';if(document.activeElement===$('noteInput'))$('noteInput').blur();   /* sin foco en el texto, Ctrl+Z deshace la nota recién añadida */
  refreshNotes();update();toast('Añadido a esta sesión. Ctrl+Z lo deshace.');
};

/* Paginación por columnas: nada se corta y no hay scroll */
function paginate(){
  const content=$('noteContent'),w=content.clientWidth,gap=32;if(!w)return;
  notePageCount=Math.max(1,Math.round((content.scrollWidth+gap)/(w+gap)));  /* round, no ceil: scrollWidth trae 1 px de redondeo y fabricaba una página vacía */
  notePage=clamp(notePage,0,notePageCount-1);
  content.style.transform='translateX('+(-notePage*(w+gap))+'px)';
  const n=cards().filter(c=>!c.hidden).length;
  $('pageStatus').textContent=notePageCount>1?'Página '+(notePage+1)+' de '+notePageCount+' · '+n+' entradas':n+' entradas · todas visibles';
  $('pageStatus').disabled=notePageCount<=1;
  $('pagePrev').disabled=notePage===0;$('pageNext').disabled=notePage===notePageCount-1;
  const vp=$('feed').getBoundingClientRect();
  content.querySelectorAll('button,.item').forEach(b=>{const r=b.getBoundingClientRect();b.tabIndex=(r.left>=vp.left-1&&r.right<=vp.right+1)?0:-1;});
}
function goToPage(el){
  const content=$('noteContent'),w=content.clientWidth,gap=32;
  notePage=Math.max(0,Math.floor((el.offsetLeft+el.offsetWidth/2)/(w+gap)));paginate();
}
$('pagePrev').onclick=()=>{notePage--;paginate();};$('pageNext').onclick=()=>{notePage++;paginate();};
new ResizeObserver(()=>{paginate();const c=selId&&byId(selId);if(c&&!c.hidden)goToPage(c);}).observe($('feed'));

/* M · salto directo de página: 34 entradas = 18 páginas a 1280x800 (9 a 1920x1080); llegar a la
   entrada 30 pasaba por ~14 clics "siguiente". Con este popover: 1 clic + número + Intro. */
let pagePopOpen=false;
function openPagePop(){
  if($('pageStatus').disabled)return;
  closeFiltersPop();closeRoundPop();
  pagePopOpen=true;$('pagePop').hidden=false;$('pageStatus').setAttribute('aria-expanded','true');
  positionPop($('pagePop'),$('pageStatus'));
  const inp=$('pageJumpInput');inp.min=1;inp.max=notePageCount;inp.value=notePage+1;inp.focus();inp.select();
}
function closePagePop(){if(!pagePopOpen)return;pagePopOpen=false;$('pagePop').hidden=true;$('pageStatus').setAttribute('aria-expanded','false');}
$('pageStatus').onclick=e=>{e.stopPropagation();pagePopOpen?closePagePop():openPagePop();};
$('pageJumpForm').onsubmit=e=>{
  e.preventDefault();
  const v=Math.round(Number($('pageJumpInput').value));
  if(!Number.isNaN(v))notePage=clamp(v-1,0,notePageCount-1);
  paginate();closePagePop();$('pageStatus').focus();
};
document.addEventListener('pointerdown',e=>{
  if(pagePopOpen&&!$('pagePop').contains(e.target)&&!$('pageStatus').contains(e.target))closePagePop();
},true);

/* ── Dibujo ─────────────────────────────────────────────────── */
const layer=$('drawLayer');layer.setAttribute('viewBox','0 0 1000 562.5');
const toolNames={pen:'Lápiz',arrow:'Flecha',rect:'Rectángulo',ellipse:'Círculo'};
function toggleDrawing(v){
  drawing=v;$('video').classList.toggle('drawing',v);
  $('toolPill').hidden=!v;if(v)$('toolPillText').textContent='Dibujando: '+toolNames[tool];
  document.querySelectorAll('.tool').forEach(b=>{const on=v&&b.dataset.tool===tool;b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));});
}
document.querySelectorAll('.tool').forEach(b=>b.onclick=()=>{
  if(shape)layer.onpointerup();   /* confirma el trazo en curso con SU herramienta antes de cambiar */
  if(drawing&&tool===b.dataset.tool){toggleDrawing(false);return;}
  tool=b.dataset.tool;setPlaying(false);toggleDrawing(true);
});
$('toolExit').onclick=e=>{e.stopPropagation();toggleDrawing(false);};
function point(e){const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(layer.getScreenCTM().inverse());return{x:p.x,y:p.y};}
layer.onpointerdown=e=>{
  if(!drawing)return;layer.setPointerCapture(e.pointerId);drawBefore=drafts[frame]||'';aDrawFrame=frame;start=point(e);
  shape=document.createElementNS('http://www.w3.org/2000/svg',tool==='rect'?'rect':tool==='ellipse'?'ellipse':'polyline');
  shape.setAttribute('fill','none');shape.setAttribute('stroke',$('inkColor').value);shape.setAttribute('stroke-width',strokeWidth);
  shape.setAttribute('stroke-linecap','round');shape.setAttribute('stroke-linejoin','round');
  if(tool==='pen')shape.setAttribute('points',start.x+','+start.y+' '+start.x+','+start.y);
  $('dlDraft').append(shape);   /* el trazo va al borrador del fotograma, nunca al dibujo ya adjunto a una nota */
};
layer.onpointermove=e=>{
  if(!shape)return;const p=point(e);
  if(tool==='pen')shape.setAttribute('points',shape.getAttribute('points')+' '+p.x+','+p.y);
  else if(tool==='arrow'){const a=Math.atan2(p.y-start.y,p.x-start.x),L=18;
    shape.setAttribute('points',start.x+','+start.y+' '+p.x+','+p.y+' '+(p.x-L*Math.cos(a-.5))+','+(p.y-L*Math.sin(a-.5))+' '+p.x+','+p.y+' '+(p.x-L*Math.cos(a+.5))+','+(p.y-L*Math.sin(a+.5)));}
  else if(tool==='ellipse'){shape.setAttribute('cx',(start.x+p.x)/2);shape.setAttribute('cy',(start.y+p.y)/2);shape.setAttribute('rx',Math.abs(p.x-start.x)/2);shape.setAttribute('ry',Math.abs(p.y-start.y)/2);}
  else{shape.setAttribute('x',Math.min(start.x,p.x));shape.setAttribute('y',Math.min(start.y,p.y));shape.setAttribute('width',Math.abs(p.x-start.x));shape.setAttribute('height',Math.abs(p.y-start.y));}
};
layer.onpointerup=layer.onpointercancel=()=>{
  if(shape){const f=aDrawFrame,before=drawBefore,after=$('dlDraft').innerHTML;shape=null;
    drafts[f]=after;aSyncAnno();
    commit('trazo',()=>aSetDraft(f,before),()=>aSetDraft(f,after));}
  shape=null;
};
$('undoDrawing').onclick=undoLast;$('redoDrawing').onclick=redoLast;
$('clearDrawing').onclick=()=>{
  const f=frame,before=drafts[f];
  if(!before){toast('Este fotograma no tiene dibujo.');return;}
  aSetDraft(f,'');commit('dibujo de este fotograma borrado',()=>aSetDraft(f,before),()=>aSetDraft(f,''));
};
document.querySelectorAll('[data-width]').forEach(b=>b.onclick=()=>{
  strokeWidth=+b.dataset.width;
  document.querySelectorAll('[data-width]').forEach(x=>{x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',String(x===b));});
});

/* Paleta del trazo: aquí el color SÍ es la función. Se elige por nombre, no se cicla. */
const inkColors=[['#111111','Negro'],['#ffffff','Blanco'],['#e5322d','Rojo'],['#f08a00','Naranja'],['#f2c400','Amarillo'],['#1f9d55','Verde'],['#2563eb','Azul']];
let inkPop=null;
function closeInk(){if(inkPop){inkPop.remove();inkPop=null;document.removeEventListener('pointerdown',inkOutside,true);}}
function inkOutside(e){if(inkPop&&!inkPop.contains(e.target)&&!$('inkColor').contains(e.target))closeInk();}
function setInk(color,name){
  const b=$('inkColor');b.value=color;b.querySelector('.sw').style.color=color;b.querySelector('.ink-name').textContent=name;
  b.title='Color del trazo: '+name.toLowerCase()+'. Pulsar para elegir';b.setAttribute('aria-label',b.title);
}
$('inkColor').onclick=e=>{
  e.stopPropagation();if(inkPop){closeInk();return;}
  inkPop=document.createElement('div');inkPop.className='ink-pop';inkPop.setAttribute('role','listbox');inkPop.setAttribute('aria-label','Elige el color del trazo');
  inkColors.forEach(([c,n])=>{
    const b=document.createElement('button');b.type='button';b.className='ink-swatch'+(c===$('inkColor').value?' on':'');b.setAttribute('role','option');b.setAttribute('aria-label',n);
    b.innerHTML='<i style="background:'+c+'"></i><span>'+n+'</span>';
    b.onclick=ev=>{ev.stopPropagation();setInk(c,n);closeInk();};inkPop.appendChild(b);
  });
  document.body.appendChild(inkPop);
  const r=$('inkColor').getBoundingClientRect();inkPop.style.left=Math.round(r.left)+'px';inkPop.style.bottom=Math.round(innerHeight-r.top+8)+'px';
  document.addEventListener('pointerdown',inkOutside,true);   /* el clic que la abre ya paso (pointerdown < click): no hace falta esperar */
};

/* ── Teclado, pantalla completa, cabecera ───────────────────── */
document.addEventListener('keydown',e=>{
  const tt=e.target&&e.target.closest?e.target:null;
  if((e.ctrlKey||e.metaKey)&&!e.altKey&&/^[zy]$/i.test(e.key)&&!(tt&&tt.closest('input,textarea,select,[contenteditable]'))){
    e.preventDefault();if(shape)return;   /* trazo en curso: no se deshace nada hasta soltar */
    (e.key.toLowerCase()==='y'||e.shiftKey)?redoLast():undoLast();return;
  }
  if(e.key==='Escape'){closeInk();closeFiltersPop();closeRoundPop();closePagePop();if(drawing)toggleDrawing(false);if(replyTarget)setReply(null);return;}
  const t=e.target&&e.target.closest?e.target:null;
  if(t&&t.closest('input,textarea,select,button,[contenteditable],.item')||e.ctrlKey||e.metaKey||e.altKey)return;
  if(e.code==='Space'){e.preventDefault();togglePlay();}
  else if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();$(e.key==='ArrowLeft'?(e.shiftKey?'backSecond':'previous'):(e.shiftKey?'forwardSecond':'next')).click();}
});
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('video').requestFullscreen();}catch(err){toast('La pantalla completa no está disponible en este navegador.');}};
$('share').onclick=()=>toast('Vista de ejemplo: compartir estará disponible en el proyecto conectado.');
$('version').onclick=()=>toast('Corte v02 seleccionado · v01 es la referencia de los dos cambios.');

/* ── Reordenar los grupos de la barra de anotar (arrastrar y soltar nativo) ─── */
(function(){
  const KEY='openframe:dock',dock=$('dock');let drag=null;
  const groups=()=>[...dock.querySelectorAll(':scope > [data-drag]')];
  const order=()=>groups().map(g=>g.dataset.drag);
  function apply(ids){const by={};groups().forEach(g=>by[g.dataset.drag]=g);const anchor=dock.querySelector('.spacer');ids.forEach(id=>{if(by[id])dock.insertBefore(by[id],anchor);});}
  groups().forEach(g=>g.setAttribute('draggable','true'));
  dock.addEventListener('dragstart',e=>{const g=e.target.closest&&e.target.closest('[data-drag]');if(!g)return;drag=g;g.classList.add('dragging');e.dataTransfer.effectAllowed='move';try{e.dataTransfer.setData('text/plain',g.dataset.drag);}catch(_){}});
  dock.addEventListener('dragover',e=>{
    if(!drag)return;e.preventDefault();e.dataTransfer.dropEffect='move';
    const g=e.target.closest&&e.target.closest('[data-drag]');dock.querySelectorAll('.drop-before').forEach(x=>x.classList.remove('drop-before'));
    if(!g||g===drag)return;const r=g.getBoundingClientRect();const after=e.clientX>r.left+r.width/2;
    g.parentNode.insertBefore(drag,after?g.nextSibling:g);
  });
  dock.addEventListener('drop',e=>e.preventDefault());
  dock.addEventListener('dragend',()=>{if(drag)drag.classList.remove('dragging');drag=null;try{localStorage.setItem(KEY,JSON.stringify(order()));}catch(_){}});
  try{const s=JSON.parse(localStorage.getItem(KEY)||'null');if(Array.isArray(s)&&s.length)apply(s);}catch(_){}
})();

/* ── C · chat a escala: filtros, búsqueda y cierre de ronda ──── */
let typeFilter='all',personFilter='all',drawingFilter=false,hideReviewed=true,searchQ='';
const norm=s=>(s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'');
const cardAuthor=c=>{const el=c.querySelector('.item-who strong');return el?el.textContent.trim():'';};
function itemLabel(c){const n=c.dataset.item.replace(/\D/g,'');return c.dataset.kind==='change'?'a'+n:'nota '+n;}
function itemText(c){
  const paras=[...c.querySelectorAll(':scope>p,.reply p')].map(p=>p.textContent).join(' ');
  return norm(cardAuthor(c)+' '+paras+' '+tc(Number(c.dataset.frame))+' '+itemLabel(c));
}
/* pestaña + tipo + persona + dibujo + revisados + búsqueda; typeOverride permite contar por segmento sin mutar el filtro activo */
function matchesFilters(c,typeOverride){
  const kind=c.dataset.kind;
  if(kind==='change'){if(filterResolved)return false;if(hideReviewed&&c.dataset.reviewed==='true')return false;}
  else{if((c.dataset.resolved==='true')!==filterResolved)return false;}
  const t=typeOverride!==undefined?typeOverride:typeFilter;
  if(t!=='all'&&kind!==t)return false;
  if(personFilter!=='all'&&cardAuthor(c)!==personFilter)return false;
  if(drawingFilter&&c.dataset.drawing!=='true')return false;
  if(searchQ&&!itemText(c).includes(searchQ))return false;
  return true;
}
function totalForScope(){
  return cards().filter(c=>{
    const kind=c.dataset.kind;
    if(kind==='change'){if(filterResolved)return false;}else{if((c.dataset.resolved==='true')!==filterResolved)return false;}
    return typeFilter==='all'||kind===typeFilter;
  }).length;
}
function hasActiveFilters(){return typeFilter!=='all'||personFilter!=='all'||drawingFilter||!hideReviewed||!!searchQ;}
function syncFiltersDot(){
  const active=personFilter!=='all'||drawingFilter||!hideReviewed;
  $('filtersDot').hidden=!active;$('filtersBtn').classList.toggle('active',active);
}
function syncFilterControlsUI(){
  document.querySelectorAll('.seg-btn').forEach(b=>{const on=b.dataset.type===typeFilter;b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));});
  $('searchInput').value=searchQ?$('searchInput').value:'';$('searchClear').hidden=!$('searchInput').value;
  $('chkDrawing').checked=drawingFilter;$('chkReviewed').checked=!hideReviewed;
  buildPersonOptions();
}
function buildPersonOptions(){
  const names=[...new Set(cards().map(cardAuthor))].sort((a,b)=>a.localeCompare(b,'es'));
  const box=$('personOptions');box.innerHTML='';
  const mk=(val,label)=>{
    const b=document.createElement('button');b.type='button';b.className='person-opt'+(personFilter===val?' on':'');b.setAttribute('role','option');b.textContent=label;
    b.onclick=()=>{personFilter=val;notePage=0;buildPersonOptions();refreshNotes();};box.appendChild(b);
  };
  mk('all','Todas');names.forEach(n=>mk(n,n));
}
function clearAllFilters(){
  typeFilter='all';personFilter='all';drawingFilter=false;hideReviewed=true;searchQ='';
  $('searchInput').value='';notePage=0;syncFilterControlsUI();refreshNotes();closeFiltersPop();
}
document.querySelectorAll('.seg-btn').forEach(b=>b.onclick=()=>{
  typeFilter=b.dataset.type;notePage=0;
  document.querySelectorAll('.seg-btn').forEach(x=>{const on=x===b;x.classList.toggle('on',on);x.setAttribute('aria-pressed',String(on));});
  refreshNotes();
});
$('searchInput').oninput=()=>{searchQ=norm($('searchInput').value.trim());$('searchClear').hidden=!$('searchInput').value;notePage=0;refreshNotes();};
$('searchClear').onclick=()=>{$('searchInput').value='';searchQ='';$('searchClear').hidden=true;notePage=0;refreshNotes();$('searchInput').focus();};
$('chkDrawing').onchange=e=>{drawingFilter=e.target.checked;notePage=0;refreshNotes();};
$('chkReviewed').onchange=e=>{hideReviewed=!e.target.checked;notePage=0;refreshNotes();};
$('clearFiltersLink').onclick=clearAllFilters;
$('clearFiltersBtn').onclick=clearAllFilters;

let filtersPopOpen=false,roundPopOpen=false;
function positionPop(el,anchor){const r=anchor.getBoundingClientRect();el.style.top=Math.round(r.bottom+6)+'px';el.style.right=Math.round(innerWidth-r.right)+'px';}
function openFiltersPop(){closeRoundPop();closePagePop();filtersPopOpen=true;$('filtersPop').hidden=false;$('filtersBtn').setAttribute('aria-expanded','true');positionPop($('filtersPop'),$('filtersBtn'));buildPersonOptions();}
function closeFiltersPop(){if(!filtersPopOpen)return;filtersPopOpen=false;$('filtersPop').hidden=true;$('filtersBtn').setAttribute('aria-expanded','false');}
$('filtersBtn').onclick=e=>{e.stopPropagation();filtersPopOpen?closeFiltersPop():openFiltersPop();};

function pendingCounts(){
  const openNotes=cards().filter(c=>c.dataset.kind!=='change'&&c.dataset.resolved!=='true').length;
  const unrevChanges=cards().filter(c=>c.dataset.kind==='change'&&c.dataset.reviewed!=='true').length;
  return {openNotes,unrevChanges,total:openNotes+unrevChanges};
}
let roundState='reviewing';
function updateRoundPill(){
  const {openNotes,unrevChanges,total}=pendingCounts(),btn=$('pendingBtn');
  btn.classList.toggle('state-sent',roundState==='sent');btn.classList.toggle('state-approved',roundState==='approved');
  if(roundState==='approved')btn.innerHTML=ico('badge-check','sm')+'<span>Corte v02 aprobado</span>';
  else if(roundState==='sent')btn.innerHTML=ico('send','sm')+'<span>Con el Agente</span>';
  else btn.innerHTML=total===0?(ico('check','sm')+'<span>Todo al día</span>'):('<span>'+total+' pendiente'+(total===1?'':'s')+'</span>');
  $('roundOpenN').textContent=openNotes;$('roundUnrevN').textContent=unrevChanges;
  $('approveBtn').disabled=total!==0||roundState==='approved';
  $('sendAgentBtn').disabled=openNotes===0||roundState==='approved';
}
function openRoundPop(){closeFiltersPop();closePagePop();roundPopOpen=true;$('roundPop').hidden=false;$('pendingBtn').setAttribute('aria-expanded','true');positionPop($('roundPop'),$('pendingBtn'));updateRoundPill();}
function closeRoundPop(){if(!roundPopOpen)return;roundPopOpen=false;$('roundPop').hidden=true;$('pendingBtn').setAttribute('aria-expanded','false');}
$('pendingBtn').onclick=e=>{e.stopPropagation();roundPopOpen?closeRoundPop():openRoundPop();};
document.addEventListener('pointerdown',e=>{
  if(filtersPopOpen&&!$('filtersPop').contains(e.target)&&!$('filtersBtn').contains(e.target))closeFiltersPop();
  if(roundPopOpen&&!$('roundPop').contains(e.target)&&!$('pendingBtn').contains(e.target))closeRoundPop();
},true);
function verFilter(kind){
  closeRoundPop();filterResolved=false;typeFilter=kind;personFilter='all';drawingFilter=false;hideReviewed=true;searchQ='';
  $('searchInput').value='';notePage=0;syncFilterControlsUI();refreshNotes();
}
$('verNotesBtn').onclick=()=>verFilter('note');
$('verChangesBtn').onclick=()=>verFilter('change');
function setSentBadge(card,v){
  if(v){card.dataset.sent='true';if(!card.querySelector('.sent-badge')){const b=document.createElement('span');b.className='sent-badge';b.title='Enviada al Agente';b.setAttribute('aria-label','Enviada al Agente');b.innerHTML=ico('send','xs');card.querySelector('.item-top').appendChild(b);}}
  else{delete card.dataset.sent;const b=card.querySelector('.sent-badge');if(b)b.remove();}
}
$('sendAgentBtn').onclick=()=>{
  const targets=cards().filter(c=>c.dataset.kind!=='change'&&c.dataset.resolved!=='true'&&c.dataset.sent!=='true');
  if(!targets.length)return;
  const prev=roundState;targets.forEach(c=>setSentBadge(c,true));roundState='sent';
  commit('Notas enviadas al Agente',
    ()=>{targets.forEach(c=>setSentBadge(c,false));roundState=prev;updateRoundPill();},
    ()=>{targets.forEach(c=>setSentBadge(c,true));roundState='sent';updateRoundPill();});
  updateRoundPill();closeRoundPop();
  toast(targets.length+' nota'+(targets.length===1?'':'s')+' enviada'+(targets.length===1?'':'s')+' al Agente.');
};
$('approveBtn').onclick=()=>{
  if(pendingCounts().total!==0||roundState==='approved')return;
  const prev=roundState;roundState='approved';
  commit('Corte v02 aprobado',()=>{roundState=prev;updateRoundPill();},()=>{roundState='approved';updateRoundPill();});
  updateRoundPill();closeRoundPop();toast('Corte v02 aprobado.');
};

/* ── D · Cambios del Agente: decidir (aprobar / pedir ajuste) y comparar v01·v02 ──
   Contrato: data-resolves="n1" en la .item.change · data-decision="approved|adjust" (ausente = sin decidir)
   · data-reviewed="true" ⇔ hay decisión. El marcador homónimo recibe el mismo data-decision. */
let dAdjustTarget=null,dCmpMode='v02',dSplitPos=50;
const dLinked=card=>card.dataset.resolves?byId(card.dataset.resolves):null;
function dSetDecision(card,dec){
  if(dec){card.dataset.decision=dec;card.dataset.reviewed='true';}else{delete card.dataset.decision;card.dataset.reviewed='false';}
  document.querySelectorAll('.marker[data-item="'+card.dataset.item+'"]').forEach(m=>{if(dec)m.dataset.decision=dec;else delete m.dataset.decision;});
}
/* Instantánea de (decisión, estado de la nota enlazada) para que undo/redo repongan EXACTAMENTE lo anterior */
function dSnapshot(card){const note=dLinked(card);return {dec:card.dataset.decision||null,res:note?note.dataset.resolved==='true':null};}
function dRestore(card,s){dSetDecision(card,s.dec);const note=dLinked(card);if(note&&s.res!==null)setResolved(note,s.res);}
function dApprove(card){
  const prev=dSnapshot(card),note=dLinked(card);
  const apply=()=>{dSetDecision(card,'approved');if(note)setResolved(note,true);};
  apply();commit(cardName(card)+' aprobado',()=>dRestore(card,prev),apply);refreshNotes();
  toast(cardName(card)+' aprobado'+(note?' · '+cardName(note)+' resuelta':'')+'. Ctrl+Z lo deshace.');
}
function dRedecide(card){
  const prev=dSnapshot(card),note=dLinked(card);
  const apply=()=>{dSetDecision(card,null);if(note)setResolved(note,false);};
  apply();commit(cardName(card)+' devuelto a sin revisar',()=>dRestore(card,prev),apply);refreshNotes();
}
/* Pedir otro ajuste: modo visible en el composer; nada cambia hasta enviar */
function dStartAdjust(card){
  setReply(card);dAdjustTarget=card;
  $('composerLabel').textContent='Ajuste sobre cambio '+card.querySelector('.mk b').textContent;
  $('noteInput').placeholder='Qué ajuste le pides al Agente sobre este cambio…';
  $('noteForm').classList.add('adjusting');
}
function dEndAdjust(){dAdjustTarget=null;$('noteForm').classList.remove('adjusting');}
function dSubmitAdjust(text){
  const card=dAdjustTarget,prev=dSnapshot(card),note=dLinked(card);
  const r=document.createElement('div');r.className='reply';
  r.innerHTML='<div class="item-top"><span class="avatar" style="width:20px;height:20px;font-size:8px">LM</span><strong>Lucía Méndez</strong><span class="ago">Ahora</span></div><p></p>';
  r.querySelector('p').textContent=text;
  const apply=()=>{card.appendChild(r);dSetDecision(card,'adjust');if(note)setResolved(note,false);};
  apply();commit(cardName(card)+': ajuste pedido',()=>{r.remove();dRestore(card,prev);},apply);
  dEndAdjust();setReply(null);
}
$('noteForm').addEventListener('submit',e=>{
  if(!dAdjustTarget||replyTarget!==dAdjustTarget)return;
  e.preventDefault();e.stopImmediatePropagation();
  const text=$('noteInput').value.trim();if(!text)return;
  dSubmitAdjust(text);
  $('noteInput').value='';if(document.activeElement===$('noteInput'))$('noteInput').blur();
  refreshNotes();update();toast('Ajuste pedido al Agente. Ctrl+Z lo deshace.');
},true);
document.addEventListener('click',e=>{if(e.target.closest&&e.target.closest('.reply-btn,#cancelReply'))dEndAdjust();},true);
function dWireChange(card){
  const on=(sel,fn)=>{const b=card.querySelector(sel);if(b)b.onclick=e=>{e.stopPropagation();fn();};};
  on('.approve-btn',()=>dApprove(card));
  on('.adjust-btn',()=>dStartAdjust(card));
  on('.redecide-btn',()=>dRedecide(card));
  on('.compare-btn',()=>{selectItem(card.dataset.item);dSetSplit(50);dSetCompare('split');});
}
/* Comparar v01 · v02: estado de vista (no va al historial). v01 = la escena clonada con el caballo entrando. */
function dBuildV01(){
  const src=$('video').querySelector('.scene');if(!src)return null;
  const c=src.cloneNode(true);c.classList.add('scene-v01');c.setAttribute('aria-hidden','true');c.removeAttribute('role');c.removeAttribute('aria-label');
  const d=c.querySelector('defs');if(d)d.remove();   /* los url(#…) resuelven contra la escena original */
  const horse=c.querySelector('g[fill="#262626"]');if(horse)horse.setAttribute('transform','translate(1130 338)');
  c.hidden=true;src.after(c);return c;
}
const dSceneV01=dBuildV01();
function dSetSplit(p){
  dSplitPos=clamp(Math.round(p*10)/10,0,100);
  $('cmpLine').style.left=dSplitPos+'%';
  if(dSceneV01)dSceneV01.style.clipPath=dCmpMode==='split'?'inset(0 '+(100-dSplitPos)+'% 0 0)':'';
  const h=$('cmpHandle');h.setAttribute('aria-valuenow',String(Math.round(dSplitPos)));h.setAttribute('aria-valuetext',Math.round(dSplitPos)+' %');
}
function dSetCompare(mode){
  dCmpMode=mode;const v=$('video');
  v.classList.toggle('cmp-v01',mode==='v01');v.classList.toggle('cmp-split',mode==='split');
  if(dSceneV01)dSceneV01.hidden=mode==='v02';
  $('cmpCurtain').hidden=mode==='v02';$('cmpPill').hidden=mode==='v02';
  document.querySelectorAll('.vseg-btn').forEach(b=>{const on=b.dataset.cmp===mode;b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));});
  dSetSplit(dSplitPos);
}
document.querySelectorAll('.vseg-btn').forEach(b=>b.onclick=e=>{e.stopPropagation();dSetCompare(b.dataset.cmp);});
$('cmpExit').onclick=e=>{e.stopPropagation();dSetCompare('v02');};
/* Con la comparación activa, un clic en el video no reproduce/pausa (se envuelve el handler base sin tocarlo) */
const dVideoClick=$('video').onclick;
$('video').onclick=e=>{if(dCmpMode!=='v02')return;if(dVideoClick)dVideoClick(e);};
/* Cortina: arrastre con pointer events sobre la línea entera (100 % del alto) y teclado en el tirador */
(function(){
  const line=$('cmpLine'),h=$('cmpHandle');let dragging=false;
  const toPos=x=>{const r=$('video').getBoundingClientRect();return (x-r.left)/r.width*100;};
  line.onpointerdown=e=>{e.stopPropagation();dragging=true;line.setPointerCapture(e.pointerId);dSetSplit(toPos(e.clientX));};
  line.onpointermove=e=>{if(dragging)dSetSplit(toPos(e.clientX));};
  line.onpointerup=line.onpointercancel=e=>{dragging=false;try{line.releasePointerCapture(e.pointerId);}catch(_){}};
  line.onclick=e=>e.stopPropagation();
  h.onkeydown=e=>{
    if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;
    e.preventDefault();e.stopPropagation();const step=e.shiftKey?10:2;dSetSplit(dSplitPos+(e.key==='ArrowLeft'?-step:step));
  };
})();
document.addEventListener('keydown',e=>{if(e.key==='Escape'){dEndAdjust();if(dCmpMode!=='v02')dSetCompare('v02');}},true);

/* ══ A · Anotaciones: el dibujo pertenece a su fotograma + notas con tramo ═══════════════════
   icons: pen-line, move-horizontal, repeat-1, arrow-right-to-line, arrow-left-to-line
   drafts[f]        = trazos sin enviar del fotograma f (innerHTML de #dlDraft). Se ven SOLO en f.
   noteDrawings[id] = trazos ya adjuntos a una nota; se ven solo si la nota está seleccionada y frame === su entrada.
   Tramo: aIn/aOut son el tramo que llevará la PRÓXIMA nota; la nota ya creada lo lleva en data-out. */
const drafts=Object.create(null),noteDrawings=Object.create(null);
let aIn=null,aOut=null,aPlayTo=null,aDrawFrame=0,aLayerKey=null;
const aCount=h=>h?(h.match(/<(?:polyline|rect|ellipse)\b/g)||[]).length:0;
const aNoteFrame=()=>aIn!==null?aIn:frame;
const aShort=f=>tc(f).slice(3);
const aDur=(i,o)=>((o-i)/FPS).toFixed(1).replace('.',',')+' s';
const aInRange=c=>!!c.dataset.out&&Number(c.dataset.frame)<=frame&&frame<=Number(c.dataset.out);

/* Dibujo de ejemplo de la nota 1: flecha + círculo sobre el caballo (espacio 1000×562.5) */
noteDrawings.n1='<polyline fill="none" stroke="#ffffff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" points="868,166 740,295 744.7,277.6 740,295 757.1,289.5"/>'
  +'<ellipse fill="none" stroke="#ffffff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" cx="627" cy="354" rx="96" ry="83"/>';

function aSetDraft(f,html){
  if(html)drafts[f]=html;else delete drafts[f];
  aLayerKey=null;aSyncAnno();
}
/* Única fuente de verdad de la capa de dibujo y del composer: se recalcula en cada update() */
function aSyncAnno(){
  if(!shape){
    const d=drafts[frame]||'',sc=selId&&byId(selId);
    const nd=sc&&noteDrawings[selId]&&Number(sc.dataset.frame)===frame?noteDrawings[selId]:'';
    const key=frame+'\u0001'+selId+'\u0001'+d+'\u0001'+nd;
    if(key!==aLayerKey){$('dlDraft').innerHTML=d;$('dlNote').innerHTML=nd;aLayerKey=key;}
  }
  const nf=aNoteFrame(),d=drafts[nf]||'',n=aCount(d),hasIn=aIn!==null,hasOut=aOut!==null;
  $('aDrawChip').hidden=!n;
  if(n)$('aDrawChipText').textContent='Dibujo · '+n+(n===1?' trazo':' trazos');
  $('aRangeChip').hidden=!hasIn;
  if(hasIn)$('aRangeChipText').textContent=hasOut?aShort(aIn)+' → '+aShort(aOut)+' · '+aDur(aIn,aOut):aShort(aIn)+' → salida sin fijar';
  $('aChips').hidden=!n&&!hasIn;
  $('noteTime').textContent=hasIn?(hasOut?aShort(aIn)+' → '+aShort(aOut):aShort(aIn)+' → salida sin fijar'):tc(frame);
  [[$('aSetIn'),hasIn],[$('aSetOut'),hasOut]].forEach(([b,on])=>{b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));});
  const cd=$('clearDrawing');cd.disabled=!drafts[frame];
  const ct='Borrar el dibujo de este fotograma'+(cd.disabled?' · este fotograma no tiene dibujo':'');
  cd.title=ct;cd.setAttribute('aria-label',ct);
}

/* Tramo: entrada / salida del composer. Todo pasa por commit (Ctrl+Z). */
function aApplyRange(i,o,label){
  if(i===aIn&&o===aOut)return;
  const pi=aIn,po=aOut;aIn=i;aOut=o;aSyncAnno();
  commit(label,()=>{aIn=pi;aOut=po;aSyncAnno();},()=>{aIn=i;aOut=o;aSyncAnno();});
}
function aSetInAt(){
  const f=frame,keep=aOut!==null&&aOut>f;
  if(aOut!==null&&!keep)toast('Entrada en '+aShort(f)+'. La salida quedaba antes y se quitó.');
  aApplyRange(f,keep?aOut:null,'Entrada del tramo fijada');
}
function aSetOutAt(){
  const f=frame;
  if(aIn===null){toast('Fija primero la entrada del tramo.');return;}
  if(f<=aIn){toast('La salida tiene que ir después de la entrada ('+aShort(aIn)+').');return;}
  aApplyRange(aIn,f,'Salida del tramo fijada');
}
function aClearRange(){if(aIn!==null||aOut!==null)aApplyRange(null,null,'Tramo quitado');}
$('aSetIn').onclick=aSetInAt;$('aSetOut').onclick=aSetOutAt;$('aRangeChipClear').onclick=aClearRange;
$('aDrawChipClear').onclick=()=>{
  const f=aNoteFrame(),before=drafts[f];if(!before)return;
  aSetDraft(f,'');commit('dibujo de la nota quitado',()=>aSetDraft(f,before),()=>aSetDraft(f,''));
};

/* Reproducir el tramo de una nota: de la entrada a la salida, y pausa en la salida. */
function aPlayRange(c){
  if(!c||!c.dataset.out)return;
  selectItem(c.dataset.item);aPlayTo=Number(c.dataset.out);setPlaying(true);
}
function aWatchRange(){
  if(aPlayTo!==null){
    if(!playing)aPlayTo=null;
    else if(frame>=aPlayTo){frame=aPlayTo;setPlaying(false);aPlayTo=null;update();}
  }
  requestAnimationFrame(aWatchRange);
}
requestAnimationFrame(aWatchRange);

document.addEventListener('click',e=>{
  if(!e.target.closest)return;
  const bar=e.target.closest('.a-rangebar');
  if(bar){e.stopPropagation();selectItem(bar.dataset.item);return;}
  const pr=e.target.closest('.a-play-range');
  if(pr){e.stopPropagation();aPlayRange(pr.closest('.item'));}
});
document.addEventListener('keydown',e=>{
  if(e.ctrlKey||e.metaKey||e.altKey)return;
  if(e.key==='Escape'){aClearRange();return;}
  const t=e.target&&e.target.closest?e.target:null;
  if(t&&t.closest('input,textarea,select,[contenteditable]'))return;
  const k=e.key.toLowerCase();
  if(k==='i'){e.preventDefault();aSetInAt();}
  else if(k==='o'){e.preventDefault();aSetOutAt();}
});

/* ══ E · Atajos de teclado y chuleta ════════════════════════════════════════════════
   SHORTCUTS es la UNICA fuente de verdad: de aqui salen (1) el manejador de teclado,
   (2) la chuleta #keysPop y (3) el title/aria-keyshortcuts de cada boton con atajo.
   base:true  = el atajo ya existia (base o otro agente) y aqui solo se documenta: no se
                vuelve a cablear, para no dispararlo dos veces. Si choca, gana el existente.
   key        = e.key que lo dispara (letras en minuscula, se compara sin distinguir caja).
   combos     = como se escribe en la chuleta · ks = valor de aria-keyshortcuts. */
function ePlayOrFaster(){if(!playing){if(frame>=TOTAL)seek(0);setPlaying(true);}else $('speed').click();}
function eNewNote(){setPlaying(false);if(replyTarget)setReply(null);dEndAdjust();$('noteInput').focus();}
function eToggleCompare(){dSetCompare(dCmpMode==='v02'?'split':'v02');}
function eFocusSearch(){const i=$('searchInput');i.focus();i.select();}
const SHORTCUTS=[
 {g:'Reproducción',combos:['Espacio'],desc:'Reproducir o pausar',base:true,btn:[['#videoPlay','Espacio','Space'],['#bandPlay','Espacio','Space']]},
 {g:'Reproducción',combos:['K'],desc:'Pausar',key:'k',run:()=>setPlaying(false),btn:[['#bandPlay','K','K']]},
 {g:'Reproducción',combos:['L'],desc:'Reproducir · otra vez, más rápido',key:'l',run:ePlayOrFaster,btn:[['#bandPlay','L','L']]},
 {g:'Reproducción',combos:['J'],desc:'Un segundo atrás',key:'j',run:()=>$('backSecond').click(),btn:[['#backSecond','J','J']]},
 {g:'Reproducción',combos:['←','→'],desc:'Fotograma atrás o adelante',base:true,btn:[['#previous','←','ArrowLeft'],['#next','→','ArrowRight']]},
 {g:'Reproducción',combos:['Mayús+←','Mayús+→'],desc:'Un segundo atrás o adelante',base:true,btn:[['#backSecond','Mayús+←','Shift+ArrowLeft'],['#forwardSecond','Mayús+→','Shift+ArrowRight']]},
 {g:'Reproducción',combos:[',','.'],desc:'Fotograma atrás o adelante',key:',',run:()=>$('previous').click(),alt:{key:'.',run:()=>$('next').click()},btn:[['#previous',',',','],['#next','.','.']]},
 {g:'Navegación',combos:['[',']'],desc:'Nota anterior o siguiente',key:'[',run:()=>$('prevNote').click(),alt:{key:']',run:()=>$('nextNote').click()},btn:[['#prevNote','[','['],['#nextNote',']',']']]},
 {g:'Navegación',combos:['{','}'],desc:'Cambio anterior o siguiente',key:'{',run:()=>$('prevChange').click(),alt:{key:'}',run:()=>$('nextChange').click()},btn:[['#prevChange','{','{'],['#nextChange','}','}']]},
 {g:'Navegación',combos:['/'],desc:'Buscar en la conversación',key:'/',run:eFocusSearch,btn:[['#searchInput','/','/']]},
 {g:'Navegación',combos:['C'],desc:'Comparar v01 · v02',key:'c',run:eToggleCompare,btn:[['#cmpSeg [data-cmp=split]','C','C']]},
 {g:'Notas',combos:['N'],desc:'Nota nueva en este fotograma',key:'n',run:eNewNote,btn:[['#noteInput','N','N']]},
 {g:'Notas',combos:['I'],desc:'Entrada del tramo',base:true,btn:[['#aSetIn','I','I']]},
 {g:'Notas',combos:['O'],desc:'Salida del tramo',base:true,btn:[['#aSetOut','O','O']]},
 {g:'Notas',combos:['Ctrl+Entrar'],desc:'Enviar la nota o la respuesta',base:true,btn:[['#noteForm .send','Ctrl+Entrar','Control+Enter']]},
 {g:'Dibujo',combos:['Esc'],desc:'Salir del dibujo o del modo activo',base:true,btn:[['#toolExit','Esc','Escape']]},
 {g:'Dibujo',combos:['Ctrl+Z'],desc:'Deshacer el último cambio',base:true,btn:[['#undoDrawing','Ctrl+Z','Control+Z']]},
 {g:'Dibujo',combos:['Ctrl+Mayús+Z'],desc:'Rehacer',base:true,btn:[['#redoDrawing','Ctrl+Mayús+Z','Control+Shift+Z']]},
 {g:'General',combos:['?'],desc:'Esta chuleta de atajos',base:true,btn:[['#keysBtn','?','?']]}
];
/* Chuleta: se construye una sola vez desde SHORTCUTS (misma cuenta de filas que de atajos). */
const eKbd=combo=>combo.split('+').map(k=>'<kbd>'+k+'</kbd>').join('<span class="keys-sep">+</span>');
function eBuildKeys(){
  const pop=$('keysPop');if(pop.dataset.built)return;
  const groups=[];
  SHORTCUTS.forEach(s=>{let g=groups.find(x=>x.name===s.g);if(!g){g={name:s.g,rows:[]};groups.push(g);}g.rows.push(s);});
  pop.innerHTML=groups.map(g=>'<div class="keys-group"><h3>'+g.name+'</h3>'
    +g.rows.map(s=>'<div class="keys-row"><span class="keys-keys">'
      +s.combos.map(eKbd).join('<span class="keys-sep">/</span>')+'</span><span>'+s.desc+'</span></div>').join('')
    +'</div>').join('');
  pop.dataset.built='1';
}
function eOpenKeys(){
  eBuildKeys();closeInk();closeFiltersPop();closeRoundPop();closePagePop();closeClusterPop();hidePreview();
  const pop=$('keysPop'),b=$('keysBtn');pop.hidden=false;b.setAttribute('aria-expanded','true');
  const r=b.getBoundingClientRect();
  pop.style.top=Math.round(r.bottom+6)+'px';pop.style.right=Math.round(Math.max(8,innerWidth-r.right))+'px';
  const pr=pop.getBoundingClientRect();
  if(pr.bottom>innerHeight-8)pop.style.top=Math.round(Math.max(8,innerHeight-8-pr.height))+'px';
  pop.tabIndex=-1;pop.focus();
}
function eCloseKeys(){
  const pop=$('keysPop');if(pop.hidden)return;
  pop.hidden=true;$('keysBtn').setAttribute('aria-expanded','false');$('keysBtn').focus();   /* el foco vuelve a su disparador */
}
function eToggleKeys(){$('keysPop').hidden?eOpenKeys():eCloseKeys();}
$('keysBtn').onclick=e=>{e.stopPropagation();eToggleKeys();};
document.addEventListener('pointerdown',e=>{
  if(!$('keysPop').hidden&&!$('keysPop').contains(e.target)&&!$('keysBtn').contains(e.target))eCloseKeys();
},true);

const eInField=t=>!!(t&&t.closest&&t.closest('input,textarea,select,[contenteditable]'));
const eNormKey=k=>(k.length===1&&/[a-zñ]/i.test(k))?k.toLowerCase():k;
const eOwn=[];SHORTCUTS.forEach(s=>{if(s.run)eOwn.push({key:s.key,run:s.run});if(s.alt)eOwn.push(s.alt);});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){eCloseKeys();return;}
  if((e.ctrlKey||e.metaKey)&&!e.altKey&&e.key==='Enter'){        /* unico atajo que SI funciona dentro del texto */
    if(!eInField(e.target))return;
    e.preventDefault();$('noteForm').requestSubmit();return;
  }
  if(e.ctrlKey||e.metaKey||e.altKey||eInField(e.target))return;
  if(e.key==='?'){e.preventDefault();eToggleKeys();return;}
  const k=eNormKey(e.key),s=eOwn.find(x=>x.key===k);
  if(s){e.preventDefault();s.run();}
});
/* Cada control con atajo lo lleva en title y en aria-keyshortcuts (ayuda en el control, no impresa). */
const eTight=s=>(s||'').replace(/\s+/g,'');
function eWireKeyHints(){
  const map=new Map();
  SHORTCUTS.forEach(s=>(s.btn||[]).forEach(([sel,combo,ks])=>{
    document.querySelectorAll(sel).forEach(b=>{
      if(!map.has(b))map.set(b,{ks:[],cb:[]});
      const m=map.get(b);
      if(!m.ks.includes(ks))m.ks.push(ks);
      if(!m.cb.includes(combo))m.cb.push(combo);
    });
  }));
  map.forEach((m,b)=>{
    b.setAttribute('aria-keyshortcuts',m.ks.join(' '));
    const t=b.getAttribute('title')||b.getAttribute('aria-label')||'',tt=eTight(t);
    const falta=m.cb.filter(c=>tt.indexOf(eTight(c))<0);
    if(falta.length)b.setAttribute('title',(t?t+' · ':'')+falta.join(' / '));
  });
}
eWireKeyHints();

update();refreshNotes();syncHist();
