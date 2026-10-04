#!/usr/bin/env python3
"""Seleccion en negativo + persistente + redactor sin bordes encimados. Chrome via CDP_PORT, API en 9421 (datos x2)."""
import sys, json
sys.path.insert(0, __import__('os').path.dirname(__file__))
from cdp import Page
API = "http://127.0.0.1:9421/"
C = []
def check(label, ok, det=""):
    C.append(bool(ok)); print(("  ✔ " if ok else "  ✘ ") + label + ((" — " + str(det)) if (det and not ok) else ""))
pg = Page(API, 1600, 1000); ev = pg.ev
pg.sleep(2); ev("openProject('prueba-x2')", await_promise=True); pg.sleep(3)
LUM = """(c,bg)=>{const p=s=>{const m=s.match(/[\\d.]+/g).map(Number);return {r:m[0],g:m[1],b:m[2],a:m.length>3?m[3]:1}};
 const L=o=>{const f=x=>{x/=255;return x<=.03928?x/12.92:Math.pow((x+.055)/1.055,2.4)};return .2126*f(o.r)+.7152*f(o.g)+.0722*f(o.b)};
 let a=p(c),b=p(bg); if(a.a<1){a={r:a.r*a.a+b.r*(1-a.a),g:a.g*a.a+b.g*(1-a.a),b:a.b*a.a+b.b*(1-a.a),a:1}}
 const l1=L(a),l2=L(b);return (Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05)}"""
def sel_info():
    return ev("(()=>{const e=document.querySelector('#list .item.sel'); if(!e) return null; const cs=getComputedStyle(e); return {id:e.dataset.id,bg:cs.backgroundColor,n:document.querySelectorAll('#list .item.sel').length,kind:e.classList.contains('change')?'cambio':'nota'}})()")
def contraste_ok():
    return ev("(()=>{const e=document.querySelector('#list .item.sel'); const bg=getComputedStyle(e).backgroundColor; const f=%s; const mal=[]; e.querySelectorAll('p,.item-who strong,.item-who small,.status,.text-btn,.time-link,.now,.link-chip').forEach(x=>{ if(getComputedStyle(x).display==='none'||!x.textContent.trim()) return; let b=bg; const xb=getComputedStyle(x).backgroundColor; if(!/rgba\\(.*, 0\\)|transparent/.test(xb)){ const q=xb.match(/[\\d.]+/g).map(Number); if(q.length>3&&q[3]<1){const w=bg.match(/[\\d.]+/g).map(Number); b=\x27rgb(\x27+[0,1,2].map(i=>Math.round(q[i]*q[3]+w[i]*(1-q[3]))).join(\x27,\x27)+\x27)\x27} else b=xb } const c=f(getComputedStyle(x).color,b); if(c<4.5) mal.push(x.className+':'+c.toFixed(1))}); return mal})()" % LUM)
def recargar():
    ev("location.reload()"); pg.sleep(5)
def en_vista():
    return ev("(()=>{const e=document.querySelector('#list .item.sel'); if(!e) return false; const a=e.getBoundingClientRect(),b=document.querySelector('#list').getBoundingClientRect(); return a.top>=b.top-2&&a.bottom<=b.bottom+2})()")
for tipo in ("change", "note"):
    nom = "cambio" if tipo == "change" else "nota"
    cid = ev("document.querySelector('#list .item.%s').dataset.id" % tipo)
    ev("document.querySelector('#list .item.%s .item-top').click()" % tipo); pg.sleep(1)
    s = sel_info()
    check("%s seleccionado: una sola tarjeta marcada" % nom, s and s["n"] == 1 and s["id"] == cid, s)
    check("%s seleccionado: fondo oscuro (negativo)" % nom, s and s["bg"] == "rgb(23, 23, 23)", s)
    mal = contraste_ok(); check("%s seleccionado: todo el texto con contraste >= 4.5:1" % nom, mal == [], mal)
    check("%s seleccionado: queda guardado" % nom, ev("JSON.parse(localStorage.getItem(LAST_KEY)).sel") == cid)
    f0 = ev("Math.round(v.currentTime*24)")
    recargar()
    s2 = sel_info()
    check("%s: tras recargar sigue seleccionado y oscuro" % nom, s2 and s2["id"] == cid and s2["bg"] == "rgb(23, 23, 23)", s2)
    check("%s: tras recargar la tarjeta esta a la vista" % nom, en_vista() is True)
    f1 = ev("Math.round(v.currentTime*24)")
    check("%s: tras recargar el video vuelve a su fotograma" % nom, abs(f1 - f0) <= 1, (f0, f1, ev("st.notas.find(n=>n.id===st.selId).frame")))
# seleccion inexistente guardada: no rompe y no marca nada
ev("localStorage.setItem(LAST_KEY, JSON.stringify({slug:st.slug, vid:st.vid, sel:'n_no_existe'}))"); recargar()
check("seleccion guardada que ya no existe: sin tarjeta marcada", sel_info() is None)
check("seleccion guardada que ya no existe: el proyecto abre igual", ev("!!st.slug && document.querySelectorAll('#list .item').length>0"))
# redactor en «pedir ajuste» con foco
cid = ev("document.querySelector('#list .item.change').dataset.id")
ev("x2PedirAjuste('%s')" % cid); pg.sleep(.5); ev("document.querySelector('#ta').focus()"); pg.sleep(.3)
r = ev("""(()=>{const ta=document.querySelector('#ta'),ed=document.querySelector('.editor'),lb=document.querySelector('#edLbl');
 const a=getComputedStyle(ta),b=getComputedStyle(ed),c=getComputedStyle(lb);
 return {taOutline:a.outlineStyle,taBorder:a.borderTopWidth,edBorderStyle:b.borderTopStyle,lbShadow:c.boxShadow,lbBg:c.backgroundColor,lbBorder:c.borderTopWidth,btn:document.querySelector('#bSaveTxt').textContent}})()""")
check("redactor: el textarea no pinta aro propio al enfocar", r["taOutline"] == "none" and r["taBorder"] == "0px", r)
check("redactor: la etiqueta no lleva recuadro ni relleno", r["lbShadow"] == "none" and r["lbBorder"] == "0px" and r["lbBg"] in ("rgba(0, 0, 0, 0)", "transparent"), r)
check("redactor: pedir ajuste conserva el borde discontinuo (un solo trazo)", r["edBorderStyle"] == "dashed", r)
check("redactor: el boton dice «Pedir ajuste»", r["btn"] == "Pedir ajuste", r)
check("sin excepciones de JS", pg.errors == [], pg.errors[:3])
print("%d/%d checks" % (sum(C), len(C))); sys.exit(0 if all(C) else 1)
