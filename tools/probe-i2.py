#!/usr/bin/env python3
"""Sonda de diagnostico de I2 (no es una suite): mide el POST del borrador con
dibujo del invitado y la llegada de una nota nueva a la app de Cristian.

    CDP_PORT=9433 /tmp/o8/venv/bin/python tools/probe-i2.py --admin 9431 --gate 9432
"""
import argparse
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
spec = importlib.util.spec_from_file_location("e2e_inv", os.path.join(HERE, "e2e-invitado.py"))
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)
from cdp import Page  # noqa: E402

ROOT = E.ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin", type=int, default=9431)
    ap.add_argument("--gate", type=int, default=9432)
    args = ap.parse_args()
    p_admin = E.elegir(args.admin)
    p_gate = E.elegir(args.gate, tomados={p_admin})
    env = E.Entorno(p_admin, p_gate)
    ADMIN, GATE = env.admin, env.gate
    try:
        sonda(ADMIN, GATE)
    finally:
        env.parar()


def sonda(ADMIN, GATE):
    http, SLUG = E.http, "cafe-lumen"
    http("POST", ADMIN + "/api/proyectos", {"nombre": "Cafe Lumen", "cliente": "Lumen SA"})
    with open(os.path.join(ROOT, "clip.mp4"), "rb") as f:
        clip = f.read()
    st, d, _ = http("POST", ADMIN + "/api/proyectos/%s/videos" % SLUG, raw=clip,
                    headers={"X-Filename": "clip.mp4", "Content-Type": "application/octet-stream"})
    VID = ((d or {}).get("video") or {}).get("id")
    st, d, _ = http("POST", "%s/api/proyectos/%s/videos/%s/invitar" % (ADMIN, SLUG, VID),
                    {"dias": 7, "etiqueta": "Marta (cliente)", "ve_otras": False})
    TOKEN, EID = d["token"], d["id"]

    pg = Page(url=GATE + "/r/" + TOKEN, w=1600, h=1000)
    time.sleep(1.6)
    pg.ev("document.getElementById('invNombre').value = 'Marta Ríos'")
    pg.click("#invDlgOk")
    time.sleep(1.0)

    # ── A. dibujar: que queda en st.notas y que viaja en el POST ──
    pg.ev("""window.__posts = [];
             const _f = window.fetch;
             window.fetch = function(u, o){ try{ if(o && o.method === 'POST' && o.body)
               window.__posts.push({u: String(u), len: o.body.length, body: o.body.slice(0, 400)}); }catch(e){}
               return _f.apply(this, arguments); };
             true""")
    r = pg.rect("#cv")
    pg.ev("v.currentTime = 2.0")
    time.sleep(0.5)
    pg.click("[data-tool=pen]")
    pg.drag(r["x"] + r["w"] * 0.3, r["y"] + r["h"] * 0.35,
            r["x"] + r["w"] * 0.7, r["y"] + r["h"] * 0.6, steps=10)
    time.sleep(1.2)
    print("A1 borrador local tras dibujar:",
          pg.ev("JSON.stringify((st.notas||[]).filter(n=>String(n.id).startsWith('tmp_'))"
                ".map(n=>({id:n.id, frame:n.frame, strokes:(n.drawing&&n.drawing.strokes||[]).length,"
                "pts:(n.drawing&&n.drawing.strokes||[]).reduce((a,s)=>a+(s.pts||[]).length,0)})))"))
    print("A2 POSTs salidos mientras dibujaba:", pg.ev("JSON.stringify(window.__posts.map(p=>[p.u,p.len]))"))
    print("A3 selId:", pg.ev("String(st.selId)"), "| bSave disabled:", pg.ev("document.getElementById('bSave').disabled"))
    print("A4 tamano del thumb del borrador:",
          pg.ev("(()=>{const d=(st.notas||[]).find(n=>String(n.id).startsWith('tmp_'));"
                "if(!d) return 'sin borrador'; const t=x2Thumb(d); return t ? t.length : 'null'})()"))

    # Guardar el borrador (flujo real: un solo POST)
    pg.click("#bSave")
    time.sleep(1.8)
    print("A5 POSTs tras Guardar:", pg.ev("JSON.stringify(window.__posts.map(p=>[p.u,p.len]))"))
    print("A6 toast:", json.dumps(pg.ev("document.getElementById('toast').textContent")))
    notas = E.notas_servidor(ADMIN, SLUG)
    dib = [n for n in notas if (n.get("drawing") or {}).get("strokes")]
    print("A7 notas con dibujo en el servidor:",
          json.dumps([{"id": n["id"], "enlace_id": n.get("enlace_id"), "author": n.get("author"),
                       "thumb": n.get("thumb"),
                       "pts": sum(len(s.get("pts") or []) for s in n["drawing"]["strokes"])} for n in dib]))

    # ── B. la app de Cristian: pagina de la lista y llegada por sondeo ──
    cp = Page(url=ADMIN + "/", w=1600, h=1000)
    time.sleep(1.0)
    cp.ev("localStorage.setItem('openframe:last', JSON.stringify({slug:%s, vid:%s}))"
          % (json.dumps(SLUG), json.dumps(VID)))
    E.nav(cp, ADMIN + "/", 2.4)
    E.esperar_js(cp, "(st && st.slug === %s && st.vid) ? st.vid : ''" % json.dumps(SLUG), 15)
    # llenar de notas para forzar varias paginas
    for i in range(8):
        http("POST", ADMIN + "/api/proyectos/%s/notas" % SLUG,
             {"video": VID, "frame": 5 + i, "text": "relleno %d" % i, "author": "cristian"})
    time.sleep(3.0)
    print("B1 pager:", json.dumps(cp.ev("document.getElementById('x2Page').textContent")),
          "| x2Page:", cp.ev("st.x2Page"), "| cards:", cp.ev("document.querySelectorAll('#list .note').length"))

    pg.ev("v.currentTime = 5.0")
    time.sleep(0.4)
    pg.ev("document.getElementById('ta').value = 'MEDIDA-LATENCIA'")
    pg.ev("document.getElementById('ta').dispatchEvent(new Event('input'))")
    t0 = time.time()
    pg.click("#bSave")
    time.sleep(2.0)
    enserv = any("MEDIDA-LATENCIA" in (n.get("text") or "") for n in E.notas_servidor(ADMIN, SLUG))
    print("B2 la nota llego al SERVIDOR:", enserv, "| toast invitado:",
          json.dumps(pg.ev("document.getElementById('toast').textContent")))
    visto = None
    fin = time.time() + 14
    while time.time() < fin:
        if cp.ev("document.getElementById('list').textContent.indexOf('MEDIDA-LATENCIA') >= 0"):
            visto = time.time() - t0
            break
        time.sleep(0.15)
    print("B3 visible en el DOM de Cristian:", ("%.2f s" % visto) if visto else "NO en 14 s")
    print("B4 esta en st.notas de Cristian:",
          cp.ev("JSON.stringify((st.notas||[]).filter(n=>(n.text||'').indexOf('MEDIDA-LATENCIA')>=0)"
                ".map(n=>({id:n.id,frame:n.frame,who:n.author})))"))
    print("B5 pager ahora:", json.dumps(cp.ev("document.getElementById('x2Page').textContent")),
          "| x2Page:", cp.ev("st.x2Page"))
    print("B6 orden de la lista filtrada (frames):",
          cp.ev("JSON.stringify(x2Filtradas().map(n=>n.frame))"))


if __name__ == "__main__":
    main()
