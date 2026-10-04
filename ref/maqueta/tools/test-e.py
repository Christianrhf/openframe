"""Pruebas de la tarea E: atajos (SHORTCUTS), chuleta, foco, movimiento reducido y orden de Tab.
Uso:  CDP_PORT=9356 uv run --quiet --with websocket-client python3 tools/test-e.py
Capturas en shots/e-*.png (hay que MIRARLAS; un check verde no prueba que se vea bien)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page

res = []
def check(name, cond, detail=''):
    res.append((bool(cond), name, detail))

pg = Page()
ev = pg.ev
blur = lambda: ev("document.activeElement&&document.activeElement.blur&&document.activeElement.blur()")

# ── 1. Chuleta de atajos ────────────────────────────────────────────────────────────────────
pg.viewport(1280, 800)
n_short = ev("SHORTCUTS.length")
blur(); pg.key('?'); pg.sleep(.3)
K = ev("""({open:!document.getElementById('keysPop').hidden,
            exp:document.getElementById('keysBtn').getAttribute('aria-expanded'),
            rows:document.querySelectorAll('#keysPop .keys-row').length,
            groups:[...document.querySelectorAll('#keysPop .keys-group h3')].map(h=>h.textContent),
            role:document.getElementById('keysPop').getAttribute('role')})""")
check('chuleta: "?" la abre (dialog visible, aria-expanded=true)',
      isinstance(K, dict) and K['open'] and K['exp'] == 'true' and K['role'] == 'dialog', str(K))
check(f'chuleta: una fila por atajo de SHORTCUTS ({n_short})',
      isinstance(K, dict) and K['rows'] == n_short, f"filas={K.get('rows')} SHORTCUTS={n_short}")
check('chuleta: los 5 grupos pedidos, en orden',
      isinstance(K, dict) and K['groups'] == ['Reproducción', 'Navegación', 'Notas', 'Dibujo', 'General'], str(K.get('groups')))
fit = ev("""(()=>{const p=document.getElementById('keysPop'),r=p.getBoundingClientRect();
  return {x:r.left,y:r.top,r:r.right,b:r.bottom,w:r.width,h:r.height,
          sy:p.scrollHeight-p.clientHeight,sx:p.scrollWidth-p.clientWidth,
          pageSy:document.documentElement.scrollHeight-document.documentElement.clientHeight}})()""")
check('chuleta: cabe en la ventana a 1280x800, sin scroll propio ni de pagina',
      isinstance(fit, dict) and fit['x'] >= 0 and fit['y'] >= 0 and fit['r'] <= 1280 and fit['b'] <= 800
      and fit['sy'] <= 0 and fit['sx'] <= 0 and fit['pageSy'] == 0, str(fit))
pg.shot('e-02-chuleta-1280.png')
pg.key('Escape'); pg.sleep(.3)
check('chuleta: Esc la cierra y el foco vuelve al boton',
      ev("document.getElementById('keysPop').hidden") is True
      and ev("document.activeElement.id") == 'keysBtn'
      and ev("document.getElementById('keysBtn').getAttribute('aria-expanded')") == 'false')
ev("document.getElementById('keysBtn').click()"); pg.sleep(.3)
op = ev("!document.getElementById('keysPop').hidden")
ev("document.getElementById('keysBtn').click()"); pg.sleep(.2)
check('chuleta: el boton del cabecero la abre y la cierra',
      op is True and ev("document.getElementById('keysPop').hidden") is True)

# ── 2. Atajos nuevos, uno por uno ───────────────────────────────────────────────────────────
blur(); ev("seek(12.5);setPlaying(true)"); pg.sleep(.2)
pg.key('k'); pg.sleep(.2)
check('K: pausa', ev("playing") is False)
f0 = ev("frame")
pg.key('l'); pg.sleep(.2)
play1 = ev("playing")
pg.key('l'); pg.sleep(.2)
sp = ev("speed")
ev("setPlaying(false)")
check('L: reproduce y, pulsada otra vez, pasa a la velocidad siguiente',
      play1 is True and sp == 1.5, f'playing={play1} speed={sp}')

ev("speed=1;seek(12.5);setPlaying(false)"); pg.sleep(.2)
f0 = ev("frame"); pg.key('j'); pg.sleep(.25)
check('J: un segundo atras (24 fotogramas)', ev("frame") == f0 - 24, f'{f0} -> {ev("frame")}')

ev("seek(12.5)"); pg.sleep(.2); f0 = ev("frame")
pg.key('.'); pg.sleep(.2); f1 = ev("frame")
pg.key(','); pg.sleep(.2); f2 = ev("frame")
check('. y , : un fotograma adelante y atras', f1 == f0 + 1 and f2 == f0, f'{f0} -> {f1} -> {f2}')

ev("selectItem('n1')"); pg.sleep(.3)
pg.key(']'); pg.sleep(.35); s1 = ev("selId")
pg.key('['); pg.sleep(.35); s2 = ev("selId")
check('] y [ : nota siguiente y anterior', s1 == 'n2' and s2 == 'n1', f'{s1} / {s2}')

ev("seek(500/FPS)"); pg.sleep(.2)   # 500 cae entre los dos cambios (331 y 677)
pg.key('}'); pg.sleep(.35); c1 = ev("selId")
pg.key('{'); pg.sleep(.35); c2 = ev("selId")
check('} y { : cambio siguiente y anterior', c1 == 'a2' and c2 == 'a1', f'{c1} / {c2}')

blur(); pg.key('/'); pg.sleep(.25)
check('/ : enfoca la busqueda', ev("document.activeElement.id") == 'searchInput')
blur()

ev("setPlaying(true)"); pg.sleep(.2); pg.key('n'); pg.sleep(.3)
check('N: pausa y enfoca el composer en el fotograma actual',
      ev("playing") is False and ev("document.activeElement.id") == 'noteInput'
      and ev("document.getElementById('noteTime').textContent") == ev("tc(aNoteFrame())"))
blur()

pg.key('c'); pg.sleep(.3); m1 = ev("dCmpMode")
pg.key('c'); pg.sleep(.3); m2 = ev("dCmpMode")
check('C: activa y desactiva comparar v01 · v02', m1 == 'split' and m2 == 'v02', f'{m1} / {m2}')

n0 = ev("cards().length")
ev("document.getElementById('noteInput').focus();document.getElementById('noteInput').value='nota por Ctrl+Enter'")
pg.key('Enter', ctrl=True); pg.sleep(.5)
check('Ctrl+Enter: envia desde el textarea (unico atajo que funciona dentro del texto)',
      ev("cards().length") == n0 + 1, f'{n0} -> {ev("cards().length")}')
blur(); pg.key('z', ctrl=True); pg.sleep(.3)

# ── 3. Los atajos NO se disparan escribiendo ────────────────────────────────────────────────
# enfocar el textarea pausa (comportamiento base): se enfoca ANTES de arrancar la reproduccion
ev("seek(12.5);document.getElementById('noteInput').focus()"); pg.sleep(.2)
ev("setPlaying(true)"); pg.sleep(.2); before = ev("({f:frame,p:playing})")
for k in ('j', 'k', 'l', 'n', 'c', '[', '/'):
    pg.key(k)
pg.sleep(.3)
after = ev("({f:frame,p:playing,v:document.getElementById('noteInput').value,ae:document.activeElement.id})")
check('escribiendo en el textarea los atajos no se disparan (sigue reproduciendo y el texto se escribe)',
      isinstance(after, dict) and after['p'] is True and after['ae'] == 'noteInput' and 'jkl' in after['v'],
      str(after))
pg.key('?'); pg.sleep(.2)
check('"?" dentro del textarea no abre la chuleta', ev("document.getElementById('keysPop').hidden") is True)
ev("document.getElementById('noteInput').value='';setPlaying(false)"); blur()

# ── 4. title + aria-keyshortcuts en cada boton con atajo ────────────────────────────────────
hints = ev("""(()=>{const bad=[];
 SHORTCUTS.forEach(s=>(s.btn||[]).forEach(([sel,combo,ks])=>{
   document.querySelectorAll(sel).forEach(b=>{
     const t=(b.getAttribute('title')||'').replace(/\\s+/g,'');
     const k=(b.getAttribute('aria-keyshortcuts')||'').split(' ');
     if(k.indexOf(ks)<0)bad.push(sel+' aria-keyshortcuts sin '+ks);
     if(t.indexOf(combo.replace(/\\s+/g,''))<0)bad.push(sel+' title sin '+combo);
   });
 }));
 return {bad,n:document.querySelectorAll('[aria-keyshortcuts]').length}})()""")
check('cada boton con atajo lleva el atajo en title y en aria-keyshortcuts',
      isinstance(hints, dict) and not hints['bad'] and hints['n'] >= 16, str(hints)[:300])

# ── 5. Foco: un solo anillo de 2 px, y vuelve a su disparador ───────────────────────────────
ring = ev("""(()=>{const b=document.getElementById('next');b.focus();
 const s=getComputedStyle(b);
 return {w:s.outlineWidth,st:s.outlineStyle,off:s.outlineOffset,sh:s.boxShadow}})()""")
check('foco: anillo de 2 px, un solo trazo (sin sombra/halo)',
      isinstance(ring, dict) and ring['w'] == '2px' and ring['st'] == 'solid'
      and ring['off'] == '2px' and ring['sh'] == 'none', str(ring))
card = ev("""(()=>{const c=document.querySelector('.item[data-item=a1]');c.focus();
 const s=getComputedStyle(c);return {ol:s.outlineStyle,sh:s.boxShadow,bw:s.borderTopWidth}})()""")
check('foco en una tarjeta: un solo trazo (borde + 1 px, sin outline doble)',
      isinstance(card, dict) and card['ol'] == 'none' and card['sh'].count('rgb') == 1, str(card))
blur()

# ── 6. Movimiento reducido y aria-live ──────────────────────────────────────────────────────
pg.send('Emulation.setEmulatedMedia', features=[{'name': 'prefers-reduced-motion', 'value': 'reduce'}])
pg.sleep(.2)
rm = ev("""(()=>{const a=getComputedStyle(document.querySelector('.video-play')).transitionDuration,
 b=getComputedStyle(document.querySelector('.item')).transitionDuration,
 c=getComputedStyle(document.querySelector('.marker')).transitionDuration;
 return [a,b,c]})()""")
check('prefers-reduced-motion: reduce apaga las transiciones',
      isinstance(rm, list) and all(x.replace('0s', '').replace(',', '').strip() == '' for x in rm), str(rm))
pg.send('Emulation.setEmulatedMedia', features=[])
pg.sleep(.2)
live = ev("""({rc:document.getElementById('resultCount').getAttribute('aria-live'),
               to:document.getElementById('toast').getAttribute('aria-live'),
               ps:document.getElementById('pageStatus').getAttribute('aria-live')})""")
check('aria-live="polite" en el contador de resultados y en el toast',
      isinstance(live, dict) and live['rc'] == 'polite' and live['to'] == 'polite', str(live))

# ── 7. Orden de Tab: video -> linea de tiempo -> barra de anotar -> chat -> composer ────────
order = ev("""(()=>{
 const FOC='a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]';
 const zone=el=>el.closest('#noteForm')?5:el.closest('.sidebar')?4:el.closest('.dock')?3
   :el.closest('.timeline-panel')?2:el.closest('.video')?1:el.closest('header')?0:-1;
 const els=[...document.querySelectorAll(FOC)].filter(e=>{
   const r=e.getBoundingClientRect();
   return r.width>0&&r.height>0&&e.tabIndex>=0&&zone(e)>=0&&getComputedStyle(e).visibility!=='hidden';});
 const zs=els.map(zone),pos=[];
 let desc=0;for(let i=1;i<zs.length;i++)if(zs[i]<zs[i-1])desc++;
 return {zonas:[...new Set(zs)],desordenes:desc,positivos:els.filter(e=>e.tabIndex>0).length,n:els.length}})()""")
check('orden de Tab: zonas en orden video -> tiempo -> anotar -> chat -> composer, sin tabindex positivos',
      isinstance(order, dict) and order['desordenes'] == 0 and order['positivos'] == 0
      and order['zonas'] == sorted(order['zonas']), str(order))

# ── 8. Capturas ─────────────────────────────────────────────────────────────────────────────
ev("selectItem('a1')"); pg.sleep(.4)
pg.shot('e-01-pantalla-1280.png')
r = pg.rect('.item[data-item=a1]')
if isinstance(r, dict):
    pg.shot('e-04-acciones-28px.png', clip=(r['x'] - 8, r['y'] - 8, r['w'] + 16, r['h'] + 16))
rs = pg.rect('.sidebar')
if isinstance(rs, dict):
    pg.shot('e-05-chat-contraste.png', clip=(rs['x'], rs['y'], rs['w'], min(rs['h'], 430)))
pg.viewport(1600, 1000); pg.sleep(.3)
blur(); pg.key('?'); pg.sleep(.35)
pg.shot('e-03-chuleta-1600.png')
fit2 = ev("""(()=>{const p=document.getElementById('keysPop'),r=p.getBoundingClientRect();
  return {ok:r.left>=0&&r.top>=0&&r.right<=1600&&r.bottom<=1000,sy:p.scrollHeight-p.clientHeight}})()""")
check('chuleta: cabe tambien a 1600x1000 sin scroll', isinstance(fit2, dict) and fit2['ok'] and fit2['sy'] <= 0, str(fit2))
pg.key('Escape'); pg.sleep(.2)

check('consola: cero excepciones de la pagina', not pg.errors, str(pg.errors[:3]))

fails = [r for r in res if not r[0]]
for ok, name, d in res:
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok or not d else '   -> ' + d))
print(f'\n{len(res) - len(fails)}/{len(res)} checks OK' + ('' if not fails else f'  ·  {len(fails)} FALLAN'))
sys.exit(1 if fails else 0)
