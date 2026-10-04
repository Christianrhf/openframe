#!/usr/bin/env python3
"""Regresión CDP de P4 (Fase 4: densidad de marcadores) contra el proyecto
sintético ``prueba-p4``.

Requiere server.py en 9441 y Chrome CDP en 9443:

    rm -rf data logs; mkdir -p logs
    python3 server.py --puerto 9441 > logs/server.out 2>&1 &
    tools/chrome.sh start 9443
    curl -s -X POST http://127.0.0.1:9441/api/proyectos \\
      -H 'Content-Type: application/json' -d '{"nombre":"prueba-p4"}'
    curl -s -X POST http://127.0.0.1:9441/api/proyectos/prueba-p4/videos \\
      --data-binary @clip.mp4 -H 'X-Filename: clip.mp4' \\
      -H 'Content-Type: application/octet-stream'
    CDP_PORT=9443 /tmp/o8/venv/bin/python tools/test-p4.py

No usa ni crea datos reales. Las notas de la prueba de densidad se inyectan
directamente en ``st.notas`` (misma sesión del navegador, sin red) con un LCG
con semilla: cero aleatoriedad real, siempre reproducible.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page  # noqa: E402

API = os.environ.get("P4_API", "http://127.0.0.1:9441").rstrip("/")
SLUG = "prueba-p4"

checks = []


def check(name, value, detail=""):
    ok = bool(value)
    checks.append(ok)
    print(("✔ " if ok else "✘ ") + name + ((" — " + str(detail)[:200]) if detail and not ok else ""))
    return ok


# ── LCG determinista (Numerical Recipes): misma semilla -> misma secuencia,
#    siempre; nada de random.random() ni de time.time() en el generador. ──
def lcg_stream(seed):
    state = seed & 0xFFFFFFFF
    while True:
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        yield state


def notas_sinteticas(seed, n, total_frames):
    gen = lcg_stream(seed)
    defs = []
    for i in range(n):
        frame = next(gen) % max(1, total_frames)
        kind = "cambio" if (next(gen) % 5) == 0 else "nota"
        author = "claude" if kind == "cambio" else ("invitado" if (next(gen) % 11) == 0 else "cristian")
        defs.append({"frame": frame, "kind": kind, "author": author})
    return defs


def inyectar_notas(pg, defs):
    js = ("(function(){const defs=" + json.dumps(defs) + ";"
          "st.notas = defs.map((d,i)=>({id:'p4_'+i, video:st.vid, frame:d.frame, kind:d.kind,"
          "author:d.author, resolved:false, text:'t'+i, autor_nombre:'Invitado P4',"
          "timecode: tc(null, d.frame)}));"
          "st.selId = defs.length ? 'p4_' + (defs.length>>1) : null;"
          "return st.notas.length;})()")
    return pg.ev(js)


def fijar_zoom(pg, zoom):
    js = ("(function(z){const dur=tlDur(); const span=dur/z;"
          "tlSetView(z, Math.max(0,(dur-span)/2)); tlPaint();"
          "return JSON.stringify(tlSeg());})(%r)" % (zoom,))
    return pg.ev(js)


def medir_rects(pg):
    js = ("JSON.stringify([...document.querySelectorAll("
          "'#scrub .mark:not([hidden]),#scrub .cluster-marker')]"
          ".map(e=>{const r=e.getBoundingClientRect();"
          "return [r.left,r.top,r.right,r.bottom];}))")
    raw = pg.ev(js)
    if isinstance(raw, str) and raw.startswith(("EXC:", "JSERR")):
        return None
    return json.loads(raw)


def solapes(rects):
    n = len(rects)
    pares = 0
    for i in range(n):
        ax0, ay0, ax1, ay1 = rects[i]
        for j in range(i + 1, n):
            bx0, by0, bx1, by1 = rects[j]
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                pares += 1
    return pares


def total_frames(pg):
    return pg.ev("Math.round(tlDur() * fps)")


SEEDS = list(range(1, 41))          # 40 semillas, deterministas
ZOOMS = [1, 2, 4, 8]


def matriz_densidad(pg, n_notas):
    tf = total_frames(pg)
    fallos = 0
    probados = 0
    for seed in SEEDS:
        defs = notas_sinteticas(seed, n_notas, tf)
        got = inyectar_notas(pg, defs)
        if got != n_notas:
            check("inyeccion de %d notas (semilla %d)" % (n_notas, seed), False, got)
            fallos += 1
            continue
        for zoom in ZOOMS:
            fijar_zoom(pg, zoom)
            rects = medir_rects(pg)
            probados += 1
            if rects is None:
                fallos += 1
                continue
            s = solapes(rects)
            if s != 0:
                fallos += 1
                print("  ✘ solape: n=%d semilla=%d zoom=%d -> %d pares, %d cajas" %
                      (n_notas, seed, zoom, s, len(rects)))
    check("0 solapes con %d notas (40 semillas x 4 zooms = %d combinaciones)" % (n_notas, probados),
          fallos == 0, "%d fallos" % fallos)


def main():
    pg = Page(API + "/", 1280, 800)
    pg.ev("[...document.querySelectorAll('.pitem')].find(e=>e.textContent.includes('%s'))?.click()" % SLUG)
    time.sleep(1.2)
    check("proyecto de prueba cargado", pg.ev("st.vid != null"), pg.ev("st.vid"))
    check("video real detectado (duracion y fps)", pg.ev("vmeta() && vmeta().duracion > 0 && vmeta().fps > 0"),
          pg.ev("JSON.stringify(vmeta())"))

    # ── matriz dura: 0 solapes, 40 semillas x 4 zooms, con 5 y con 60 notas ──
    matriz_densidad(pg, 5)
    matriz_densidad(pg, 60)

    # ── (a) dos carriles: notas y cambios en filas distintas ──
    tf = total_frames(pg)
    inyectar_notas(pg, [{"frame": 20, "kind": "nota", "author": "cristian"},
                         {"frame": 20, "kind": "cambio", "author": "claude"}])
    fijar_zoom(pg, 1)
    filas = json.loads(pg.ev("JSON.stringify([...document.querySelectorAll('#scrub .mark')]"
                              ".map(e=>getComputedStyle(e).getPropertyValue('--fila').trim()))"))
    check("carril de notas = 0", "0" in filas, filas)
    check("carril de cambios = 1", "1" in filas, filas)
    r = json.loads(pg.ev("JSON.stringify([...document.querySelectorAll('#scrub .mark')]"
                          ".map(e=>e.getBoundingClientRect().top))"))
    check("las dos filas quedan a alturas distintas (misma hora, sin solape vertical)",
          len(set(r)) == 2, r)

    # ── forma: notas = circulo, cambios = rombo (rotado 45deg) ──
    forma = json.loads(pg.ev("JSON.stringify((()=>{const ms=[...document.querySelectorAll('#scrub .mark')];"
                              "const n=ms.find(e=>!e.classList.contains('cambio'));"
                              "const c=ms.find(e=>e.classList.contains('cambio'));"
                              "return {notaRadius:getComputedStyle(n).borderRadius, "
                              "cambioRot:getComputedStyle(c).transform};})())"))
    check("nota = circulo (border-radius 50%)", "50%" in forma.get("notaRadius", ""), forma)
    check("cambio = rombo (transform rotate)", forma.get("cambioRot", "none") != "none", forma)

    # ── objetivo tactil >= 28px (medido con getComputedStyle del ::before, no estimado) ──
    tactil = json.loads(pg.ev("""JSON.stringify((()=>{
      const m = document.querySelector('#scrub .mark');
      const b = m.getBoundingClientRect();
      const cs = getComputedStyle(m, '::before');
      const ins = parseFloat(cs.left);
      return {mark: b.width + Math.abs(ins)*2};
    })())"""))
    check("objetivo tactil del marcador >= 28px", tactil["mark"] >= 28, tactil)

    # ── (b) agrupar + insignia + vista previa ──
    defs60 = notas_sinteticas(7, 12, tf)
    # fuerza que TODAS caigan juntas (mismo fotograma +/- 1) para un grupo grande
    base = tf // 2
    defs_apretadas = [{"frame": base + (i % 3), "kind": "nota", "author": "cristian"} for i in range(8)]
    inyectar_notas(pg, defs_apretadas)
    fijar_zoom(pg, 1)
    info = json.loads(pg.ev("""JSON.stringify((()=>{
      const c = document.querySelector('#scrub .cluster-marker');
      if(!c) return null;
      return {n: c.querySelector('span').textContent, aria: c.getAttribute('aria-label'),
        tip: c.dataset.tip, real: document.querySelectorAll('#scrub .mark').length,
        ocultos: document.querySelectorAll('#scrub .mark[hidden]').length};
    })())"""))
    check("grupo creado con insignia de cuenta", info is not None and info["n"] == "8", info)
    check("insignia aria-label trae hora y conteo", info and "Grupo de 8" in info["aria"], info)
    check("vista previa (data-tip) trae primeras entradas y hora", info and "·" in info["tip"], info)
    check("los .mark reales agrupados quedan ocultos en el DOM (hidden)",
          info and info["ocultos"] == info["real"] == 8, info)

    # ── clic en el grupo = zoom (c no se prueba aqui con popover: no lo pide P4) ──
    z0 = pg.ev("st.tl.zoom")
    pg.click("#scrub .cluster-marker")
    time.sleep(.15)
    z1 = pg.ev("st.tl.zoom")
    check("clic en el grupo sube el zoom", z1 > z0, (z0, z1))

    # ── (c) el seleccionado se absorbe en el grupo (has-sel), no lo tapa ──
    inyectar_notas(pg, defs_apretadas)
    fijar_zoom(pg, 1)
    pg.ev("st.selId = 'p4_3'")
    pg.ev("tlPaint()")
    hassel = json.loads(pg.ev("""JSON.stringify((()=>{
      const c = document.querySelector('#scrub .cluster-marker');
      const m = document.querySelector('.mark[data-nid=p4_3]');
      return {hasSel: c ? c.classList.contains('has-sel') : null,
        markHidden: m ? m.hidden : null};
    })())"""))
    check("el grupo con el seleccionado lleva has-sel", hassel.get("hasSel") is True, hassel)
    check("el marcador real seleccionado queda oculto (absorbido, no tapa al grupo)",
          hassel.get("markHidden") is True, hassel)

    # ── (d) a11y: <button> real, aria-label, activable con Espacio (Enter es
    #     nativo del <button> y no se puede sintetizar de forma fiable con
    #     Input.dispatchKeyEvent en Chrome headless — verificado aparte, ver REPORT) ──
    inyectar_notas(pg, [{"frame": 10 + i * 25, "kind": "nota", "author": "cristian"} for i in range(3)])
    fijar_zoom(pg, 1)
    tag = pg.ev("document.querySelector('#scrub .mark').tagName")
    check("el marcador es un <button> real (role=button y tabindex nativos)", tag == "BUTTON", tag)
    check("tabindex accesible por teclado (tabIndex 0)", pg.ev("document.querySelector('#scrub .mark').tabIndex") == 0)
    aria = pg.ev("document.querySelector('#scrub .mark').getAttribute('aria-label')")
    check("aria-label trae hora/autor/estado", aria and "·" in aria, aria)
    pg.ev("document.querySelectorAll('#scrub .mark')[1].focus()")
    pend0 = pg.ev("st.pend")
    paused0 = pg.ev("v.paused")
    pg.key(" ")
    time.sleep(.15)
    pend1 = pg.ev("JSON.stringify(st.pend)")
    paused1 = pg.ev("v.paused")
    check("Espacio con el foco en un marcador lo activa (no pausa/reproduce el video)",
          pend1 and pend1 != "null" and paused0 == paused1, (pend0, pend1, paused0, paused1))

    # ── (e) invitados: siguen respetando ve_otras (filtrado YA en el servidor;
    #     aqui solo se confirma que el marcador .mark.inv se sigue pintando) ──
    inyectar_notas(pg, [{"frame": 15, "kind": "nota", "author": "invitado"}])
    fijar_zoom(pg, 1)
    check("marcador de invitado sigue distinguible (.mark.inv)",
          pg.ev("!!document.querySelector('#scrub .mark.inv')"))

    # ── 0 excepciones de pagina en toda la sesion ──
    check("cero excepciones de pagina", not pg.errors, pg.errors)

    # ── sin scroll ni controles recortados en los cuatro tamaños de entrega ──
    for w, h in ((1280, 800), (1440, 900), (1600, 1000), (1920, 1080)):
        pg.viewport(w, h, clear_storage=False)
        pg.ev("[...document.querySelectorAll('.pitem')].find(e=>e.textContent.includes('%s'))?.click()" % SLUG)
        time.sleep(.4)
        m = json.loads(pg.ev("JSON.stringify({page:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],"
                              "view:[innerWidth,innerHeight]})"))
        check("sin scroll de pagina %dx%d" % (w, h), m["page"] == m["view"], m)
        recortes = json.loads(pg.ev("""JSON.stringify((()=>{
          const grupos = [['.tp-row','.tp-row > *:not(.spacer)'],['#tools','#tools > *:not(.spacer)']];
          const mal=[];
          for(const [padreSel,hijosSel] of grupos){
            const p=document.querySelector(padreSel), pr=p&&p.getBoundingClientRect();
            if(!pr) continue;
            for(const e of document.querySelectorAll(hijosSel)){
              if(getComputedStyle(e).display==='none') continue;
              const r=e.getBoundingClientRect();
              if(r.left < pr.left-1 || r.right > pr.right+1 || r.top < pr.top-1 || r.bottom > pr.bottom+1)
                mal.push({padre:padreSel,el:e.id||e.className,caja:[r.left,r.top,r.right,r.bottom],limite:[pr.left,pr.top,pr.right,pr.bottom]});
            }
          }
          return mal;
        })())"""))
        check("sin controles recortados %dx%d" % (w, h), not recortes, recortes)
        pg.shot("p4-%dx%d.png" % (w, h))

    check("cero excepciones de pagina (tras cambios de viewport)", not pg.errors, pg.errors)

    print("\n%d/%d checks" % (sum(checks), len(checks)))
    raise SystemExit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
