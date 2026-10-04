#!/usr/bin/env python3
"""Auditoria de accesibilidad y acabado del visor REAL (fase P6).

Portada de `ref/maqueta/tools/audit-a11y.py` al visor real: aqui no hay `src/app.css`
ni `body.html`, todo vive en `visor.html` (un `<style>` y un `<script>`), y la pagina
se sirve por HTTP desde `server.py`, no por `file://`.

Uso:  tools/chrome.sh start 9473
      CDP_PORT=9473 /tmp/o8/venv/bin/python tools/audit-a11y.py --api http://127.0.0.1:9471

Mide en Chrome real, en 3 tamanos x 3 estados (lista / nota seleccionada / chuleta de
atajos abierta):
  (a) CONTRASTE  de todo texto visible contra su fondo efectivo (composicion alfa de
      los fondos de los ancestros). Umbral WCAG AA: 4.5:1; 3:1 si el texto es "grande"
      (>=24px, o >=18.66px con peso >=700).
  (b) TAMANO     de letra minimo 11px. Unica excepcion: los numerales dentro de un
      marcador de la linea de tiempo (>=9px), que son glifos, no texto corrido.
  (c) HIT AREA   de todo `button, select, input, [role=slider]` visible: >=28x28, o
      >=24x24 si tiene >=8px de separacion a su vecino.
  (d) NOMBRE     accesible en todo boton/control (texto, aria-label, title,
      aria-labelledby o placeholder).
Se ignora lo oculto (display:none, visibility:hidden, opacity 0) y lo recortado por un
ancestro con overflow hidden/clip (p. ej. las paginas del chat que no se ven).

Sale con codigo 1 si hay algun fallo en (a)-(d).
"""
import argparse
import collections
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page                                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MIN_PX = 11.0
MK_MIN_PX = 9.0
HIT = 28.0
HIT_SMALL = 24.0
GAP_OK = 8.0

# El scrubber ocupa el carril entero de la banda de tiempo: su alto no es un objetivo
# tactil de 28px sino la pista completa, y se pulsa en cualquier punto de la banda.
EXENTOS = ("#scrub", "#cv", "#file")

AUDIT_JS = r"""
(()=>{
const MIN_PX=%(MIN_PX)s, MK_MIN_PX=%(MK_MIN_PX)s, HIT=%(HIT)s, HIT_SMALL=%(HIT_SMALL)s, GAP_OK=%(GAP_OK)s;
const EXENTOS=%(EXENTOS)s;

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
function visible(el){
  const r=el.getBoundingClientRect();
  if(r.width<.5||r.height<.5)return false;
  if(r.right<=0||r.bottom<=0||r.left>=innerWidth||r.top>=innerHeight)return false;
  let e=el;
  while(e&&e!==document.documentElement){
    const s=getComputedStyle(e);
    if(s.display==='none'||s.visibility==='hidden'||parseFloat(s.opacity)===0)return false;
    if(e.hasAttribute&&e.hasAttribute('hidden'))return false;
    if(e!==el&&/hidden|clip/.test(s.overflowX+' '+s.overflowY)){
      const b=e.getBoundingClientRect();
      if(r.right<=b.left+.5||r.left>=b.right-.5||r.bottom<=b.top+.5||r.top>=b.bottom-.5)return false;
    }
    e=e.parentElement;
  }
  return true;
}
/* glifos dentro de un marcador de la linea de tiempo: numerales, no texto corrido */
const inMarker=el=>!!(el.closest&&el.closest('.mark,.cluster-marker,.mk,.marker'));
const exento=el=>EXENTOS.some(s=>el.matches&&el.matches(s));

/* ── (a) contraste + (b) tamano ── */
const texts=[];
[...document.querySelectorAll('body *')].forEach(el=>{
  if(/^(script|style|svg|use|symbol|defs|path|circle|rect|line|polyline|ellipse|g|option)$/i.test(el.tagName))return;
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

/* ── (c) hit areas: el area real incluye los ::before/::after absolutos y, en una
   casilla de verificacion, la del <label> que la envuelve (pulsarla la activa) ── */
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
const CTRL='button, select, input, [role=slider]';
const ctrls=[...document.querySelectorAll(CTRL)].filter(visible).filter(el=>!exento(el))
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
  .filter(el=>!exento(el)).filter(el=>!named(el)).map(el=>({sel:sel(el)}));

const sizeSet={};texts.forEach(t=>{sizeSet[t.size]=(sizeSet[t.size]||0)+1;});
return {texts,hits,unnamed,sizeSet};
})()
""" % dict(MIN_PX=MIN_PX, MK_MIN_PX=MK_MIN_PX, HIT=HIT, HIT_SMALL=HIT_SMALL,
           GAP_OK=GAP_OK, EXENTOS=json.dumps(list(EXENTOS)))


def abrir_proyecto(pg, nombre):
    pg.ev("[...document.querySelectorAll('.pitem')].find(e=>e.textContent.includes(%s))?.click()"
          % json.dumps(nombre))
    pg.sleep(.8)
    pg.ev("(document.querySelector('.vitem')||{click(){}}).click()")
    pg.sleep(1.0)


def run_state(pg, w, h, state, nombre):
    pg.viewport(w, h)
    abrir_proyecto(pg, nombre)
    if state == 'sel':
        pg.ev("(document.querySelector('.item')||{click(){}}).click()")
        pg.sleep(.5)
    elif state == 'keys':
        pg.ev("typeof p6KeysAbrir==='function' && p6KeysAbrir()")
        pg.sleep(.4)
    else:
        pg.sleep(.2)
    d = pg.ev(AUDIT_JS)
    if not isinstance(d, dict):
        print('  !! la auditoria no devolvio datos:', str(d)[:400])
        return None
    etiq = {'init': 'lista', 'sel': 'nota seleccionada', 'keys': 'chuleta'}[state]
    tag = '%dx%d/%s' % (w, h, etiq)
    bad_contrast = [t for t in d['texts'] if t['cr'] < t['need'] - 0.005]
    bad_size = [t for t in d['texts']
                if t['size'] < (MK_MIN_PX if t['mk'] else MIN_PX) - 0.01]
    bad_hit = [x for x in d['hits'] if not x['ok']]
    return dict(tag=tag, n_text=len(d['texts']), n_ctrl=len(d['hits']),
                contrast=bad_contrast, size=bad_size, hit=bad_hit,
                unnamed=d['unnamed'], sizes=d['sizeSet'])


def finish_audit():
    """Recuento estatico sobre visor.html (un solo <style> y un solo <script>)."""
    html = open(os.path.join(ROOT, 'visor.html'), encoding='utf-8').read()
    css = html.split('<style>', 1)[1].split('</style>', 1)[0]
    js = html.split('<script>', 1)[1].rsplit('</script>', 1)[0]
    body = html.split('<body>', 1)[1].split('<script>', 1)[0]
    src = css + '\n' + body + '\n' + js
    grad = re.findall(r'(?:linear|radial|conic)-gradient', css)
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

    def norm_hex(h):                    # #fff y #ffffff son EL MISMO color
        h = h[1:].lower()
        if len(h) in (3, 4):
            h = ''.join(c * 2 for c in h)
        return '#' + h
    colors = set(norm_hex(x) for x in re.findall(r'#[0-9a-fA-F]{3,8}\b', src))
    colors |= set(re.findall(r'rgba?\([^)]*\)', css))
    fsizes = set()
    for m in re.finditer(r'font-size\s*:\s*([^;}]+)', css):
        fsizes.add(m.group(1).strip())
    for m in re.finditer(r'font\s*:\s*([^;}]+)', css):
        g = re.search(r'(\d+(?:\.\d+)?px)', m.group(1))
        if g:
            fsizes.add(g.group(1))
    return dict(grad=grad, rep=rep, blur=blur, radii=sorted(radii),
                colors=sorted(colors), fsizes=sorted(fsizes))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--api', default='http://127.0.0.1:9471')
    ap.add_argument('--proyecto', default='Prueba P6')
    args = ap.parse_args()
    try:
        urllib.request.urlopen(args.api + '/api/ping', timeout=3).read()
    except Exception as e:
        sys.exit('el servidor %s no responde (%s)' % (args.api, e))

    pg = Page(args.api + '/', 1280, 800)
    runs = []
    for (w, h) in [(1280, 800), (1440, 900), (1600, 1000)]:
        for state in ('init', 'sel', 'keys'):
            r = run_state(pg, w, h, state, args.proyecto)
            if r:
                runs.append(r)

    total = 0
    for fam, key in [('(a) CONTRASTE < umbral WCAG AA', 'contrast'),
                     ('(b) TAMANO de letra < minimo', 'size'),
                     ('(c) HIT AREA insuficiente', 'hit'),
                     ('(d) CONTROL sin nombre accesible', 'unnamed')]:
        print('\n=== ' + fam + ' ===')
        n = 0
        for r in runs:
            fails = r[key]
            n += len(fails)
            if not fails:
                continue
            print('  [%s]  %d fallos' % (r['tag'], len(fails)))
            seen = set()
            for f in fails:
                k = f['sel']
                if k in seen:
                    continue
                seen.add(k)
                if key == 'contrast':
                    print('    %s  %s:1 (necesita %s:1)  %s sobre %s  %spx  «%s»'
                          % (f['sel'], f['cr'], f['need'], f['fg'], f['bg'], f['size'], f['txt']))
                elif key == 'size':
                    print('    %s  %spx  «%s»' % (f['sel'], f['size'], f['txt']))
                elif key == 'hit':
                    print('    %s  %sx%spx  separacion=%spx  «%s»'
                          % (f['sel'], f['w'], f['h'], f['gap'], f['txt']))
                else:
                    print('    ' + f['sel'])
        total += n
        print('  -> %d fallos en total (%d pasadas)' % (n, len(runs)))

    sizes = collections.Counter()
    for r in runs:
        for k, v in r['sizes'].items():
            sizes[float(k)] += v
    print('\n=== CENSO (texto visible, suma de las pasadas) ===')
    print('  elementos con texto: ' + ', '.join('%s=%d' % (r['tag'], r['n_text']) for r in runs))
    print('  controles medidos:   ' + ', '.join('%s=%d' % (r['tag'], r['n_ctrl']) for r in runs))
    print('  tamanos de letra distintos en pantalla: %d -> %s'
          % (len(sizes), ', '.join('%gpx' % k for k in sorted(sizes))))

    f = finish_audit()
    print('\n=== ACABADO (recuento estatico sobre visor.html) ===')
    print('  degradados de color: %d   [+%d repeating-linear-gradient = reticula de 1px]'
          % (len(f['grad']) - len(f['rep']), len(f['rep'])))
    print('  box-shadow con blur > 0: %d' % len(f['blur']))
    print('  border-radius distintos: %d' % len(f['radii']))
    print('  colores distintos: %d' % len(f['colors']))
    print('  font-size distintos en CSS: %d -> %s' % (len(f['fsizes']), f['fsizes']))

    print('\n' + ('AUDITORIA OK: 0 fallos en (a)-(d)' if total == 0 else '%d FALLOS en (a)-(d)' % total))
    print('cero excepciones de pagina' if not pg.errors else 'EXCEPCIONES: %s' % pg.errors)
    sys.exit(1 if (total or pg.errors) else 0)


if __name__ == '__main__':
    main()
