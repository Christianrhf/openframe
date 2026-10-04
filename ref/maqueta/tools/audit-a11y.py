"""Auditoria de accesibilidad y acabado (tarea E).
Uso:  CDP_PORT=9356 uv run --quiet --with websocket-client python3 tools/audit-a11y.py

Mide en Chrome real, en 2 tamanos x 2 estados (chat inicial / con una nota seleccionada):
  (a) CONTRASTE  de todo texto visible contra su fondo efectivo (composicion alfa de los
      fondos de los ancestros). Umbral WCAG: 4.5:1; 3:1 solo si el texto es "grande"
      (>=24px, o >=18.66px con peso >=700).
  (b) TAMANO     de letra minimo 11px. Unica excepcion: los numerales dentro de un
      marcador (.mk / .cluster-marker), donde se admite >=9px.
  (c) HIT AREA   de todo `button, select, input, [role=slider], .item` visible:
      >=28x28, o >=24x24 si esta en una fila con >=8px de separacion a su vecino.
  (d) NOMBRE     accesible en todo boton/control (texto, aria-label, title o aria-labelledby).
Se ignora lo que esta recortado por un ancestro con overflow hidden/clip (p. ej. las
paginas del chat que no se ven) y lo que tiene display:none / visibility:hidden / opacity 0.

Imprime, por familia, la lista de fallos con selector, valor medido y ejemplo de texto.
Al final, la AUDITORIA DE ACABADO (recuento estatico sobre src/): degradados, sombras con
blur, radios, colores y tamanos de letra distintos.
Sale con codigo 1 si hay algun fallo en (a)-(d).
"""
import sys, os, re, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MIN_PX = 11.0
MK_MIN_PX = 9.0
HIT = 28.0
HIT_SMALL = 24.0
GAP_OK = 8.0

AUDIT_JS = r"""
(()=>{
const MIN_PX=%(MIN_PX)s, MK_MIN_PX=%(MK_MIN_PX)s, HIT=%(HIT)s, HIT_SMALL=%(HIT_SMALL)s, GAP_OK=%(GAP_OK)s;

const parseC=s=>{const m=(s||'').match(/[\d.]+/g);if(!m||m.length<3)return null;
  return {r:+m[0],g:+m[1],b:+m[2],a:m.length>3?+m[3]:1};};
const over=(fg,bg)=>({r:fg.r*fg.a+bg.r*(1-fg.a),g:fg.g*fg.a+bg.g*(1-fg.a),b:fg.b*fg.a+bg.b*(1-fg.a),a:1});
const lum=c=>{const f=v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)};
  return .2126*f(c.r)+.7152*f(c.g)+.0722*f(c.b);};
const ratio=(a,b)=>{const l1=lum(a),l2=lum(b);return (Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);};
const hex=c=>'#'+[c.r,c.g,c.b].map(v=>Math.round(v).toString(16).padStart(2,'0')).join('');

/* fondo efectivo: apila los fondos de los ancestros hasta el primero opaco y compone */
function effBg(el){
  const layers=[];let e=el;
  while(e){const s=getComputedStyle(e);const c=parseC(s.backgroundColor);
    if(c&&c.a>0){layers.push(c);if(c.a>=1)break;}
    e=e.parentElement;}
  let base={r:255,g:255,b:255,a:1};
  for(let i=layers.length-1;i>=0;i--)base=over(layers[i],base);
  return base;
}
function sel(el){
  let s=el.tagName.toLowerCase();
  if(el.id)s+='#'+el.id;
  const cl=(el.className&&el.className.baseVal!==undefined?el.className.baseVal:el.className)||'';
  if(typeof cl==='string'&&cl.trim())s+='.'+cl.trim().split(/\s+/).join('.');
  return s;
}
/* visible de verdad: con caja, no oculto, y no recortado por un ancestro overflow hidden/clip */
function visible(el){
  const r=el.getBoundingClientRect();
  if(r.width<.5||r.height<.5)return false;
  if(r.right<=0||r.bottom<=0||r.left>=innerWidth||r.top>=innerHeight)return false;
  let e=el;
  while(e&&e!==document.documentElement){
    const s=getComputedStyle(e);
    if(s.display==='none'||s.visibility==='hidden'||parseFloat(s.opacity)===0)return false;
    if(e!==el&&/hidden|clip/.test(s.overflowX+' '+s.overflowY)){
      const b=e.getBoundingClientRect();
      if(r.right<=b.left+.5||r.left>=b.right-.5||r.bottom<=b.top+.5||r.top>=b.bottom-.5)return false;
    }
    e=e.parentElement;
  }
  return true;
}
const inMarker=el=>!!(el.closest&&el.closest('.mk,.cluster-marker,.marker'));

/* ── (a) contraste + (b) tamano: un registro por elemento con texto propio ── */
const texts=[];
[...document.querySelectorAll('body *')].forEach(el=>{
  if(/^(script|style|svg|use|symbol|defs|path|circle|rect|line|polyline|ellipse|g)$/i.test(el.tagName))return;
  const own=[...el.childNodes].filter(n=>n.nodeType===3&&n.textContent.trim()).map(n=>n.textContent.trim()).join(' ');
  if(!own)return;
  if(!visible(el))return;
  const s=getComputedStyle(el);
  const size=parseFloat(s.fontSize),weight=parseInt(s.fontWeight)||400;
  const fg0=parseC(s.color);if(!fg0)return;
  const bg=effBg(el),fg=fg0.a<1?over(fg0,bg):fg0;
  const large=size>=24||(size>=18.66&&weight>=700);
  const need=large?3:4.5;
  const cr=ratio(fg,bg);
  texts.push({sel:sel(el),size:Math.round(size*100)/100,weight,fg:hex(fg),bg:hex(bg),
    cr:Math.round(cr*100)/100,need,mk:inMarker(el),txt:own.slice(0,38)});
});

/* ── (c) hit areas ──
   El area real incluye los ::before/::after absolutos que algunos controles usan para
   ampliarse sin engordar el dibujo, y en una casilla de verificacion es la del <label>
   que la envuelve (pulsar la etiqueta activa la casilla). */
function pseudoBox(el,which){
  const s=getComputedStyle(el,which);
  if(!s||!s.content||s.content==='none'||s.display==='none')return null;
  if(s.position!=='absolute'&&s.position!=='fixed')return null;
  const w=parseFloat(s.width),h=parseFloat(s.height),L=parseFloat(s.left),T=parseFloat(s.top);
  if(!(w>0&&h>0)||isNaN(L)||isNaN(T))return null;
  const r=el.getBoundingClientRect(),cs=getComputedStyle(el);
  const bx=r.left+(parseFloat(cs.borderLeftWidth)||0),by=r.top+(parseFloat(cs.borderTopWidth)||0);
  return {left:bx+L,top:by+T,right:bx+L+w,bottom:by+T+h};
}
function hitRect(el){
  const r=el.getBoundingClientRect();
  const o={left:r.left,top:r.top,right:r.right,bottom:r.bottom};
  ['::before','::after'].forEach(p=>{const b=pseudoBox(el,p);if(!b)return;
    o.left=Math.min(o.left,b.left);o.top=Math.min(o.top,b.top);
    o.right=Math.max(o.right,b.right);o.bottom=Math.max(o.bottom,b.bottom);});
  o.width=o.right-o.left;o.height=o.bottom-o.top;return o;
}
const hitTarget=el=>{
  if(el.tagName==='INPUT'&&/^(checkbox|radio)$/.test(el.type)){const l=el.closest('label');if(l)return l;}
  return el;
};
const CTRL='button, select, input, [role=slider], .item';
const ctrls=[...document.querySelectorAll(CTRL)].filter(visible)
  .filter(el=>!(el.tagName==='INPUT'&&el.type==='range'&&el.id==='scrubber'))  /* el scrubber ocupa el carril entero */
  .map(el=>({el,r:hitRect(hitTarget(el))}));
const hits=ctrls.map(({el,r})=>{
  let gap=1e9;
  ctrls.forEach(o=>{
    if(o.el===el||o.el.contains(el)||el.contains(o.el))return;
    const dx=Math.max(o.r.left-r.right,r.left-o.r.right);
    const dy=Math.max(o.r.top-r.bottom,r.top-o.r.bottom);
    const d=(dx<0&&dy<0)?0:Math.max(dx,dy,0);
    if(d<gap)gap=d;
  });
  const w=Math.round(r.width*10)/10,h=Math.round(r.height*10)/10;
  const ok=(w>=HIT&&h>=HIT)||(w>=HIT_SMALL&&h>=HIT_SMALL&&gap>=GAP_OK);
  return {sel:sel(el),w,h,gap:gap>1e8?-1:Math.round(gap*10)/10,ok,
    txt:(el.getAttribute('aria-label')||el.textContent||'').trim().slice(0,32)};
});

/* ── (d) nombre accesible ── */
const named=el=>{
  const lb=el.getAttribute('aria-labelledby');
  if(lb&&lb.split(/\s+/).some(id=>document.getElementById(id)&&document.getElementById(id).textContent.trim()))return true;
  return !!((el.getAttribute('aria-label')||'').trim()||(el.getAttribute('title')||'').trim()
    ||el.textContent.trim()||(el.tagName==='INPUT'&&(el.getAttribute('placeholder')||'').trim()));
};
const unnamed=[...document.querySelectorAll('button, select, input, [role=slider]')].filter(visible)
  .filter(el=>!named(el)).map(el=>({sel:sel(el)}));

/* censo de tamanos de letra realmente usados en texto visible */
const sizeSet={};texts.forEach(t=>{sizeSet[t.size]=(sizeSet[t.size]||0)+1;});
return {texts,hits,unnamed,sizeSet};
})()
""" % dict(MIN_PX=MIN_PX, MK_MIN_PX=MK_MIN_PX, HIT=HIT, HIT_SMALL=HIT_SMALL, GAP_OK=GAP_OK)


def run_state(pg, w, h, state):
    pg.viewport(w, h)
    if state == 'sel':
        pg.ev("selectItem('n1')"); pg.sleep(.4)
    else:
        pg.sleep(.2)
    d = pg.ev(AUDIT_JS)
    if not isinstance(d, dict):
        print('  !! la auditoria no devolvio datos:', str(d)[:400]); return None
    tag = f'{w}x{h}/{"nota seleccionada" if state=="sel" else "inicial"}'
    bad_contrast = [t for t in d['texts'] if t['cr'] < t['need'] - 0.005]
    bad_size = [t for t in d['texts']
                if t['size'] < (MK_MIN_PX if t['mk'] else MIN_PX) - 0.01]
    bad_hit = [x for x in d['hits'] if not x['ok']]
    return dict(tag=tag, n_text=len(d['texts']), n_ctrl=len(d['hits']),
                contrast=bad_contrast, size=bad_size, hit=bad_hit,
                unnamed=d['unnamed'], sizes=d['sizeSet'])


def finish_audit():
    css = open(os.path.join(ROOT, 'src', 'app.css'), encoding='utf-8').read()
    body = open(os.path.join(ROOT, 'src', 'body.html'), encoding='utf-8').read()
    js = open(os.path.join(ROOT, 'src', 'app.js'), encoding='utf-8').read()
    src = css + '\n' + body + '\n' + js
    grad = re.findall(r'(?:linear|radial|conic)-gradient', css)
    # repeating-linear-gradient de la reticula del carril: son lineas de 1px, no un degradado de color
    rep = re.findall(r'repeating-linear-gradient', css)
    blur = []
    for m in re.finditer(r'box-shadow\s*:\s*([^;}]+)', css):
        val = re.sub(r'(rgba?|hsla?)\([^)]*\)', 'COLOR', m.group(1))
        for part in val.split(','):
            toks = re.findall(r'-?\d+(?:\.\d+)?(?:px)?(?=\s|$)', part.replace('inset', ' '))
            lens = [t for t in toks if t.strip()]
            if len(lens) >= 3 and abs(float(lens[2].replace('px', ''))) > 0:
                blur.append(part.strip()[:60])
    radii = set()
    for m in re.finditer(r'border-radius\s*:\s*([^;}]+)', css):
        radii.add(m.group(1).strip())
    def norm_hex(h):                       # #fff y #ffffff son EL MISMO color: se cuentan una vez
        h = h[1:].lower()
        if len(h) in (3, 4): h = ''.join(c * 2 for c in h)
        return '#' + h
    colors = set(norm_hex(x) for x in re.findall(r'#[0-9a-fA-F]{3,8}\b', src))
    colors |= set(re.findall(r'rgba?\([^)]*\)', css))
    fsizes = set()
    for m in re.finditer(r'font-size\s*:\s*([^;}]+)', css):
        fsizes.add(m.group(1).strip())
    for m in re.finditer(r'font\s*:\s*([^;}]+)', css):
        g = re.search(r'(\d+(?:\.\d+)?px)', m.group(1))
        if g: fsizes.add(g.group(1))
    return dict(grad=grad, rep=rep, blur=blur, radii=sorted(radii),
                colors=sorted(colors), fsizes=sorted(fsizes))


def main():
    pg = Page()
    runs = []
    for (w, h) in [(1280, 800), (1600, 1000)]:
        for state in ('init', 'sel'):
            r = run_state(pg, w, h, state)
            if r: runs.append(r)

    total = 0
    for fam, key in [('(a) CONTRASTE < umbral WCAG', 'contrast'),
                     ('(b) TAMANO de letra < minimo', 'size'),
                     ('(c) HIT AREA insuficiente', 'hit'),
                     ('(d) CONTROL sin nombre accesible', 'unnamed')]:
        print('\n=== ' + fam + ' ===')
        n = 0
        for r in runs:
            fails = r[key]
            n += len(fails)
            if not fails: continue
            print(f'  [{r["tag"]}]  {len(fails)} fallos')
            seen = set()
            for f in fails:
                k = f['sel']
                if k in seen: continue
                seen.add(k)
                if key == 'contrast':
                    print(f'    {f["sel"]}  {f["cr"]}:1 (necesita {f["need"]}:1)  '
                          f'{f["fg"]} sobre {f["bg"]}  {f["size"]}px  «{f["txt"]}»')
                elif key == 'size':
                    print(f'    {f["sel"]}  {f["size"]}px  «{f["txt"]}»')
                elif key == 'hit':
                    print(f'    {f["sel"]}  {f["w"]}x{f["h"]}px  separacion={f["gap"]}px  «{f["txt"]}»')
                else:
                    print(f'    {f["sel"]}')
        total += n
        print(f'  -> {n} fallos en total ({len(runs)} pasadas)')

    sizes = collections.Counter()
    for r in runs:
        for k, v in r['sizes'].items(): sizes[float(k)] += v
    print('\n=== CENSO (texto visible, suma de las pasadas) ===')
    print('  elementos con texto: ' + ', '.join(f'{r["tag"]}={r["n_text"]}' for r in runs))
    print('  controles medidos:   ' + ', '.join(f'{r["tag"]}={r["n_ctrl"]}' for r in runs))
    print(f'  tamanos de letra distintos en pantalla: {len(sizes)} -> '
          + ', '.join(f'{k:g}px' for k in sorted(sizes)))

    f = finish_audit()
    print('\n=== ACABADO (recuento estatico sobre src/) ===')
    print(f'  degradados de color (linear/radial/conic-gradient): {len(f["grad"]) - len(f["rep"])}'
          f'   [+{len(f["rep"])} repeating-linear-gradient = reticula de lineas de 1px]')
    print(f'  box-shadow con blur > 0: {len(f["blur"])}')
    for b in f['blur']: print('    ' + b)
    print(f'  border-radius distintos: {len(f["radii"])} -> {f["radii"]}')
    print(f'  colores distintos: {len(f["colors"])} -> {f["colors"]}')
    print(f'  font-size distintos en CSS: {len(f["fsizes"])} -> {f["fsizes"]}')

    print(f'\n{"AUDITORIA OK: 0 fallos en (a)-(d)" if total == 0 else f"{total} FALLOS en (a)-(d)"}')
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
