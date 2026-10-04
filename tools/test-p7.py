#!/usr/bin/env python3
"""P7 · Comparar v01 · v02 en el visor real, medido por CDP en Chrome.

Requiere (puertos propios de P7, nunca compartidos con otra suite):
    OPENFRAME_NO_PUBLICAR=1 python3 server.py --puerto 9461
    OPENFRAME_NO_PUBLICAR=1 python3 guest.py --puerto 9462 --api http://127.0.0.1:9461
    tools/chrome.sh start 9463
    CDP_PORT=9463 /tmp/o8/venv/bin/python tools/test-p7.py

Crea un proyecto «Prueba P7» con clip.mp4 subido DOS veces (corte-v01 / corte-v02),
entra al modo Comparar como anfitrion (lado a lado y cortina), mide la deriva entre
los dos <video>, el tirador, el teclado, la restauracion del estado al salir, los
tres tamanos de ventana, y comprueba que el invitado no tiene ni boton ni ruta.
Sin aleatoriedad: los 20 saltos usan random.Random(7). Sale 1 si falla algun check.
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page as _Page  # noqa: E402


class Page(_Page):
    """Como cdp.Page, pero el 404 de un recurso guarda tambien su URL (para saber de que es)."""

    def send(self, method, **params):
        self._id += 1
        self.ws.send(json.dumps({'id': self._id, 'method': method, 'params': params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get('method') == 'Runtime.exceptionThrown':
                d = m['params']['exceptionDetails']
                self.errors.append((d.get('exception') or {}).get('description') or d.get('text'))
            elif m.get('method') == 'Log.entryAdded' and m['params']['entry'].get('level') == 'error':
                e = m['params']['entry']
                self.errors.append('LOG ' + e.get('text', '') + ' @ ' + str(e.get('url')))
            if m.get('id') == self._id:
                return m.get('result', {})

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "http://127.0.0.1:%s" % os.environ.get("P7_SERVER_PORT", "9461")
GATE = "http://127.0.0.1:%s" % os.environ.get("P7_GATE_PORT", "9462")
CLIP = os.path.join(ROOT, "clip.mp4")
RES = []


def check(nombre, ok, detalle=""):
    # una expresion que lanza en la pagina devuelve 'EXC: ...' (string, truthy): es un FALLO
    if isinstance(ok, str) and ok.startswith(("EXC", "JSERR")):
        detalle = ok; ok = False
    RES.append((nombre, bool(ok)))
    print(("  OK  " if ok else "  FALLA ") + nombre + (("  -- " + str(detalle)[:400]) if (detalle and not ok) else ""))
    return bool(ok)


class SinRedirigir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


ABRIR = urllib.request.build_opener(SinRedirigir)


def http(method, url, obj=None, raw=None, headers=None, seguir=True):
    body = raw if raw is not None else (json.dumps(obj).encode("utf-8") if obj is not None else None)
    req = urllib.request.Request(url, data=body, method=method)
    if raw is None and obj is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    abrir = urllib.request.urlopen if seguir else ABRIR.open
    try:
        with abrir(req, timeout=20) as r:
            txt = r.read()
            try:
                return r.status, json.loads(txt.decode("utf-8")), dict(r.headers)
            except Exception:
                return r.status, txt, dict(r.headers)
    except urllib.error.HTTPError as e:
        txt = e.read()
        try:
            return e.code, json.loads(txt.decode("utf-8")), dict(e.headers)
        except Exception:
            return e.code, txt, dict(e.headers)


def subir(slug, nombre):
    with open(CLIP, "rb") as f:
        raw = f.read()
    st, d, _ = http("POST", "%s/api/proyectos/%s/videos" % (API, slug), raw=raw,
                    headers={"X-Filename": nombre, "Content-Type": "application/octet-stream"})
    assert st == 200 and d.get("video"), (st, d)
    return d["video"]


def esperar(pg, expr, seg=6.0, paso=0.1):
    fin = time.time() + seg
    while time.time() < fin:
        if pg.ev(expr) is True:
            return True
        time.sleep(paso)
    return False


def J(pg, expr):
    return json.loads(pg.ev("JSON.stringify(" + expr + ")"))


def metric(pg):
    return J(pg, "{page:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],"
                 "view:[innerWidth,innerHeight],"
                 "stage:[document.querySelector('.stage').clientWidth,document.querySelector('.stage').scrollWidth,"
                 "document.querySelector('.stage').clientHeight,document.querySelector('.stage').scrollHeight],"
                 "screen:[screen_.clientWidth,screen_.scrollWidth,screen_.clientHeight,screen_.scrollHeight]}"
                 .replace("screen_", "document.getElementById('screen')"))


def sin_scroll(m):
    return (m["page"] == m["view"] and m["stage"][0] == m["stage"][1] and m["stage"][2] == m["stage"][3]
            and m["screen"][0] == m["screen"][1] and m["screen"][2] == m["screen"][3])


def rects(pg):
    return J(pg, "(()=>{const r=s=>{const e=document.querySelector(s);const b=e.getBoundingClientRect();"
                 "return {x:b.left,y:b.top,w:b.width,h:b.height,r:b.right,b:b.bottom}};"
                 "return {fw:r('#fw'),w2:r('#cmpWrap'),sc:r('#screen'),h:r('#cmpHandle'),cu:r('#cmpCurtain')}})()")


def deriva(pg):
    """|t1 - t2| en fotogramas del corte actual."""
    return float(pg.ev("Math.abs(v.currentTime - v2.currentTime) * fps"))


def sc_alias(pg):
    # `screen` a secas es window.screen: la escena se nombra SC en las expresiones
    pg.ev("window.SC = document.getElementById('screen')")


def abrir_proyecto(pg, slug, vid=None):
    sc_alias(pg)
    pg.ev("openProject(%s, {vid:%s})" % (json.dumps(slug), json.dumps(vid)), await_promise=True)
    esperar(pg, "vdur > 0 && st.vid !== null", 8)


def main():
    # ── proyecto de prueba: un corte primero (para ver el boton desactivado) ──
    st, d, _ = http("POST", API + "/api/proyectos", {"nombre": "Prueba P7"})
    assert st == 200, (st, d)
    slug = d["slug"]
    v1 = subir(slug, "corte-v01.mp4")
    time.sleep(1.1)                                    # created distinto (orden por created)

    pg = Page(API + "/", 1280, 800)
    abrir_proyecto(pg, slug)
    check("proyecto de prueba abierto con el primer corte", pg.ev("st.slug===%s && st.vid===%s" % (json.dumps(slug), json.dumps(v1["id"]))))
    check("con UN corte: «Comparar» desactivado y title que lo explica",
          pg.ev("bCmp.disabled===true && /otro corte/.test(bCmp.title) && bCmp.getAttribute('aria-disabled')==='true'"),
          pg.ev("[bCmp.disabled, bCmp.title]"))
    check("sin entrar: #v2 no tiene src (no se descarga nada)", pg.ev("!v2.getAttribute('src') && v2.readyState===0"))

    # ── segundo corte: el mismo clip con otro nombre y fps distinto en la meta ──
    v2 = subir(slug, "corte-v02.mp4")
    http("POST", "%s/api/proyectos/%s/videos/%s/meta" % (API, slug, v1["id"]), {"fps": 24})
    abrir_proyecto(pg, slug, v2["id"])
    check("abierto el corte nuevo (v02) con el fps del archivo",
          pg.ev("st.vid===%s && Math.abs(fps-21.53)<0.05" % json.dumps(v2["id"])), pg.ev("[st.vid, fps]"))
    check("con DOS cortes: «Comparar» activo", pg.ev("bCmp.disabled===false && !bCmp.hidden"))
    check("lista de candidatos = el otro corte", pg.ev("cmpCandidatos().length===1 && cmpCandidatos()[0].id===%s" % json.dumps(v1["id"])))

    # estado previo que debe volver EXACTO al salir
    pg.ev("tlSetView(2, 1.0); tlPaint(); seek(1.5); v.playbackRate=1.25; st.selId=null;")
    esperar(pg, "!v.seeking", 3)
    antes = J(pg, "{t:v.currentTime, zoom:st.tl.zoom, off:st.tl.off, rate:v.playbackRate, paused:v.paused}")

    # ── entrar: por defecto contra el anterior por created, lado a lado ──
    pg.click("#bCmp")
    check("entra en Comparar contra el corte anterior por created",
          pg.ev("CMP.on===true && CMP.otro===%s && cmpSel.value===%s && cmpSel.options.length===1" % (json.dumps(v1["id"]), json.dumps(v1["id"]))),
          pg.ev("[CMP.on, CMP.otro, cmpSel.value]"))
    check("#v2 carga el OTRO corte solo al entrar", pg.ev("(v2.getAttribute('src')||'').includes(%s)" % json.dumps("/" + v1["id"] + "/")), pg.ev("v2.getAttribute('src')"))
    check("al entrar el video se pausa y la seleccion no cambia", pg.ev("v.paused && st.selId===null"))
    check("controles del modo visibles: selector, Lado a lado, Cortina, salir; «Comparar» oculto",
          pg.ev("!cmpSel.hidden && !cmpSide.hidden && !cmpCurt.hidden && !cmpExit.hidden && bCmp.hidden"))
    esperar(pg, "v2.readyState>=1 && v2.videoWidth>0", 8)
    time.sleep(0.4)
    r = rects(pg)
    same_h = abs(r["fw"]["h"] - r["w2"]["h"]) <= 1
    apart = r["w2"]["r"] <= r["fw"]["x"] + 0.5 and r["w2"]["w"] > 100 and r["fw"]["w"] > 100
    inside = (r["w2"]["x"] >= r["sc"]["x"] - 0.5 and r["fw"]["r"] <= r["sc"]["r"] + 0.5
              and r["fw"]["y"] >= r["sc"]["y"] - 0.5 and r["fw"]["b"] <= r["sc"]["b"] + 0.5)
    check("lado a lado: dos cajas de la misma altura, el otro corte a la izquierda, sin solaparse, dentro de la escena",
          pg.ev("SC.classList.contains('cmp-side')") and same_h and apart and inside, r)
    check("lado a lado: el canvas de notas sigue sobre el corte actual (mismo rectangulo que #v)",
          pg.ev("(()=>{const a=v.getBoundingClientRect(),b=cv.getBoundingClientRect();return Math.abs(a.width-b.width)<1.5&&Math.abs(a.height-b.height)<1.5&&Math.abs(a.left-b.left)<1.5})()"))
    check("rotulos de cada corte y pill «Comparando … con …» con el aviso de fps distintos",
          pg.ev("!cmpPill.hidden && cmpPill.textContent.includes('Comparando') && cmpPill.textContent.includes('corte-v02') && "
                "cmpPill.textContent.includes('corte-v01') && cmpPill.textContent.includes('fps 21.533 / 24') && "
                "!cmpLblCur.hidden && cmpLblCur.textContent==='corte-v02.mp4' && cmpLblOtro.textContent==='corte-v01.mp4'"),
          pg.ev("cmpPill.textContent"))
    m = metric(pg)
    check("lado a lado 1280x800: sin scroll (pagina, stage, escena)", sin_scroll(m), m)
    pg.shot("p7-side-1280x800.png")

    # ── cortina ──
    pg.click("#cmpCurt")
    time.sleep(0.3)
    r = rects(pg)
    solapa = all(abs(r["w2"][k] - r["fw"][k]) <= 1 for k in ("x", "y", "w", "h"))
    check("cortina: #cmpWrap ocupa EXACTAMENTE el rectangulo del corte actual (±1 px)",
          pg.ev("SC.classList.contains('cmp-curtain') && cmpSide.getAttribute('aria-pressed')==='false' && cmpCurt.getAttribute('aria-pressed')==='true'") and solapa, r)
    check("cortina al 50 %: clip-path inset(0 50% 0 0), role=slider y aria-valuenow=50",
          pg.ev("cmpWrap.style.clipPath.replace(/0px/g,'0')==='inset(0 50% 0 0)' && cmpHandle.getAttribute('role')==='slider' && cmpHandle.getAttribute('aria-valuenow')==='50'"),
          pg.ev("[cmpWrap.style.clipPath, cmpHandle.getAttribute('aria-valuenow')]"))
    hc = r["h"]["x"] + r["h"]["w"] / 2
    check("tirador centrado en el 50 % del video (±1 px)", abs(hc - (r["fw"]["x"] + r["fw"]["w"] / 2)) <= 1, (hc, r["fw"]))
    # y=0.65 (antes 0.3): la réplica literal (R3) puso el segmentado v02|otro|Dividir
    # y el grupo chico «Lado a lado» arriba del video (como la maqueta); a 0.3 el punto
    # de muestra caía ENCIMA de ese grupo en vez de sobre el video. Mismo chequeo
    # (que capa gana a cada lado del divisor), mas abajo para no tocar esa chrome real.
    check("elementFromPoint: a la izquierda del divisor se ve el otro corte, a la derecha el actual",
          pg.ev("(()=>{const f=fw.getBoundingClientRect();const y=f.top+f.height*0.65;"
                "const a=document.elementFromPoint(f.left+f.width*0.25,y), b=document.elementFromPoint(f.left+f.width*0.75,y);"
                "return a===v2 && (b===cv||b===v)})()"))
    # arrastre real del tirador: 25 % y 75 %
    for pct in (25, 75):
        r = rects(pg)
        hx, hy = r["h"]["x"] + r["h"]["w"] / 2, r["h"]["y"] + r["h"]["h"] / 2
        pg.drag(hx, hy, r["fw"]["x"] + r["fw"]["w"] * pct / 100, hy, steps=10)
        time.sleep(0.15)
        r2 = rects(pg)
        hc = r2["h"]["x"] + r2["h"]["w"] / 2
        check("arrastre del tirador al %d %%: posicion medida ±1 px y clip-path" % pct,
              abs(hc - (r2["fw"]["x"] + r2["fw"]["w"] * pct / 100)) <= 1 and abs(float(pg.ev("CMP.pct")) - pct) <= 0.6
              and pg.ev("cmpWrap.style.clipPath.replace(/0px/g,'0')") == "inset(0 %d%% 0 0)" % (100 - pct),
              (hc, pg.ev("[CMP.pct, cmpWrap.style.clipPath]")))
    check("arrastrar el tirador no cambia reproducir/pausar ni el fotograma", pg.ev("v.paused && Math.abs(v.currentTime-1.5)<0.05"))
    # teclado
    pg.ev("cmpSetPct(75); cmpHandle.focus()")
    t0 = pg.ev("v.currentTime")
    pg.key("ArrowLeft")
    pg.key("ArrowLeft", shift=True)
    pg.key("ArrowRight")
    check("teclado: ← 1 %, Shift+← 10 %, → 1 % (75 → 65) y el fotograma NO se mueve",
          pg.ev("CMP.pct===65 && cmpHandle.getAttribute('aria-valuenow')==='65'") and abs(float(pg.ev("v.currentTime")) - float(t0)) < 1e-6,
          pg.ev("[CMP.pct, v.currentTime]"))
    pg.ev("cmpSetPct(50)")
    pg.shot("p7-curtain-1280x800.png")
    pg.ev("cmpSel.focus()")
    pg.key("Escape")
    check("Esc con el selector enfocado NO sale del modo (cierra el desplegable)", pg.ev("CMP.on===true"))
    pg.ev("cmpSel.blur()")

    # ── sincronizacion: reproducir 10 s a 0.5x (el clip dura 6 s), pausar, pasos, saltos ──
    pg.ev("seek(0); v.playbackRate = 0.5;")
    esperar(pg, "!v.seeking && !v2.seeking", 3)
    check("velocidad replicada en #v2 (ratechange)", abs(float(pg.ev("v2.playbackRate")) - 0.5) < 0.01)
    pg.ev("play()")
    muestras = []
    t_ini = time.time()
    for k in range(10):
        time.sleep(1.0)
        muestras.append(deriva(pg))
    dur = time.time() - t_ini
    check("tras %.1f s reproduciendo: #v2 reproduce y la deriva es < 1 fotograma (max %.3f f)" % (dur, max(muestras)),
          pg.ev("!v.paused && !v2.paused && v.currentTime>4") and max(muestras) < 1.0, (muestras, pg.ev("[v.currentTime, v2.currentTime, v.paused, v2.paused]")))
    pg.ev("pause()")
    time.sleep(0.3)
    check("pausar el principal pausa #v2 y los dos quedan en el mismo instante", pg.ev("v.paused && v2.paused") and deriva(pg) < 1.0, deriva(pg))
    pg.ev("stepF(1)")
    esperar(pg, "!v.seeking && !v2.seeking", 3)
    check("paso de fotograma: #v2 salta al mismo tiempo", deriva(pg) < 0.5, deriva(pg))
    rng = random.Random(7)
    peor = 0.0
    for k in range(20):
        t = round(rng.uniform(0, 5.9), 3)
        pg.ev("seek(%s)" % t)
        esperar(pg, "!v.seeking && !v2.seeking && v2.readyState>=2", 3)
        time.sleep(0.05)
        peor = max(peor, deriva(pg))
    check("20 saltos aleatorios (semilla 7): deriva maxima %.3f f < 1" % peor, peor < 1.0, peor)
    check("cero excepciones de pagina hasta aqui", not pg.errors, pg.errors)

    # ── cambiar de corte con el selector (vuelve al mismo, es el unico) y salir con Esc ──
    pg.ev("v.playbackRate=0.75; tlReset(); seek(3.2);")
    esperar(pg, "!v.seeking", 3)
    pg.ev("document.body.focus(); cmpHandle.blur()")
    pg.key("Escape")
    time.sleep(0.4)
    despues = J(pg, "{t:v.currentTime, zoom:st.tl.zoom, off:st.tl.off, rate:v.playbackRate, paused:v.paused}")
    check("Esc sale del modo: clases fuera, capa y tirador ocultos, «Comparar» de vuelta",
          pg.ev("!CMP.on && !SC.classList.contains('cmp-on') && !SC.classList.contains('cmp-curtain') && "
                "getComputedStyle(cmpWrap).display==='none' && getComputedStyle(cmpCurtain).display==='none' && "
                "cmpPill.hidden && cmpLblCur.hidden && !bCmp.hidden && !bCmp.disabled && cmpSel.hidden"))
    check("al salir se libera el segundo video (sin src, readyState 0)", pg.ev("!v2.getAttribute('src') && v2.readyState===0"), pg.ev("[v2.getAttribute('src'), v2.readyState]"))
    check("al salir vuelve el estado exacto: posicion, pausa, velocidad, zoom y desplazamiento",
          abs(despues["t"] - antes["t"]) < 0.03 and despues["paused"] == antes["paused"] and abs(despues["rate"] - antes["rate"]) < 1e-6
          and abs(despues["zoom"] - antes["zoom"]) < 1e-6 and abs(despues["off"] - antes["off"]) < 1e-6, (antes, despues))
    check("#fw recupera su geometria CSS (sin tamano en px)", pg.ev("fw.style.cssText===''"))
    check("comparar no entra en la pila de deshacer", pg.ev("st.undo.length===0 && st.uPos===-1"))

    # ── tres tamanos de ventana, los dos modos ──
    for w, h in ((1440, 900), (1600, 1000), (1280, 800)):
        pg.viewport(w, h, clear_storage=False)
        abrir_proyecto(pg, slug, v2["id"])
        pg.ev("cmpEntrar()")
        esperar(pg, "v2.readyState>=1", 8)
        time.sleep(0.4)
        m1 = metric(pg)
        r = rects(pg)
        ok1 = (sin_scroll(m1) and abs(r["fw"]["h"] - r["w2"]["h"]) <= 1 and r["w2"]["r"] <= r["fw"]["x"] + 0.5
               and r["fw"]["b"] <= r["sc"]["b"] + 0.5 and r["fw"]["y"] >= r["sc"]["y"] - 0.5)
        pg.shot("p7-side-%dx%d.png" % (w, h))
        pg.ev("cmpSetModo('curtain')")
        time.sleep(0.3)
        m2 = metric(pg)
        r2 = rects(pg)
        ok2 = sin_scroll(m2) and all(abs(r2["w2"][k] - r2["fw"][k]) <= 1 for k in ("x", "y", "w", "h"))
        pg.shot("p7-curtain-%dx%d.png" % (w, h))
        check("%dx%d: sin scroll en lado a lado y en cortina; cajas bien colocadas (video %dx%d)" % (w, h, r["fw"]["w"], r["fw"]["h"]),
              ok1 and ok2, (m1, m2, r, r2))
        pg.ev("cmpSalir(true)")

    # ── pantalla completa apunta a la escena entera mientras se compara ──
    check("bMax con el modo activo apunta a #screen (y a #v sin el modo)",
          pg.ev("(()=>{let tgt=null;const o=HTMLElement.prototype.requestFullscreen;"
                "HTMLElement.prototype.requestFullscreen=function(){tgt=this;return Promise.resolve()};"
                "cmpEntrar(); bMax.click(); const a=tgt; cmpSalir(true); bMax.click(); const b=tgt;"
                "HTMLElement.prototype.requestFullscreen=o; return a===SC && b===v})()"))

    # ── invitado: ni boton ni ruta ──
    st, d, _ = http("POST", "%s/api/proyectos/%s/videos/%s/invitar" % (API, slug, v2["id"]), {"dias": 1, "etiqueta": "p7"})
    token = (d.get("url") or "").rsplit("/", 1)[-1]
    check("enlace de invitado creado para el corte actual (201)", st == 201 and len(token) == 43, (st, d))
    st, _, hd = http("GET", GATE + "/r/" + token, seguir=False)
    cookie = (hd.get("Set-Cookie") or "").split(";")[0]
    check("la puerta acepta el enlace (302 + cookie)", st == 302 and cookie.startswith("ofg="), (st, hd))
    st_ok, _, _ = http("GET", "%s/media/%s/%s/%s" % (GATE, slug, v2["id"], v2["archivo"]), headers={"Cookie": cookie, "Range": "bytes=0-99"})
    st_no, _, _ = http("GET", "%s/media/%s/%s/%s" % (GATE, slug, v1["id"], v1["archivo"]), headers={"Cookie": cookie, "Range": "bytes=0-99"})
    check("puerta: el video del enlace se sirve (%d) y el OTRO corte es 404 (%d): no hay ruta para comparar" % (st_ok, st_no),
          st_ok in (200, 206) and st_no == 404)
    st_api, _, _ = http("GET", "%s/api/proyectos/%s" % (GATE, slug), headers={"Cookie": cookie})
    lista = http("GET", "%s/api/proyectos/%s" % (GATE, slug), headers={"Cookie": cookie})[1]
    check("puerta: el proyecto del invitado solo trae SU video (no sabe que existe otro corte)",
          st_api == 200 and [x["id"] for x in lista.get("videos", [])] == [v2["id"]], lista.get("videos"))
    gp = Page(GATE + "/r/" + token, 1280, 800)
    time.sleep(0.8)
    sc_alias(gp)
    check("pagina de invitado: window.__INVITADO presente y el control de comparar NO se ve",
          gp.ev("!!window.__INVITADO && getComputedStyle(cmpCtl).display==='none' && getComputedStyle(cmpWrap).display==='none'"))
    check("pagina de invitado: cmpEntrar() no hace nada (false, sin src en #v2, sin clase)",
          gp.ev("cmpEntrar()===false && !v2.getAttribute('src') && !CMP.on && !SC.classList.contains('cmp-on')"))
    check("pagina de invitado: cero excepciones", not gp.errors, gp.errors)

    # ── proyectos reales (solo notes/meta): abren sin excepciones con el codigo nuevo ──
    lp = http("GET", API + "/api/proyectos")[1]
    reales = [p for p in (lp.get("proyectos", []) + lp.get("archivados", [])) if not p["slug"].startswith("prueba-p7")]
    if reales:
        for p in reales:
            pg.errors.clear()
            abrir_proyecto(pg, p["slug"])
            time.sleep(0.3)
            n = int(pg.ev("(st.videos||[]).length"))
            # la copia de datos reales no trae los videos: el 404 del media es esperado y NO es una excepcion
            exc = [e for e in pg.errors if not e.startswith("LOG Failed to load resource")]
            nn = int(pg.ev("(st.notas||[]).length"))
            # un proyecto ARCHIVADO no abre video (vmeta() es null: pro() solo mira los activos;
            # comportamiento previo a P7), asi que ahi «Comparar» queda desactivado
            abre = pg.ev("!!vmeta()") is True
            esperado = "false" if (abre and n > 1) else "true"
            check("proyecto real «%s» (%d cortes, %d notas%s): abre sin excepciones; «Comparar» %s" % (
                      p["slug"], n, nn, "" if abre else ", archivado", "activo" if esperado == "false" else "desactivado"),
                  not exc and pg.ev("bCmp.disabled===%s" % esperado), (exc, pg.ev("[bCmp.disabled, bCmp.title]")))
    else:
        print("  (sin proyectos reales en data/: copia /tmp/o10/datos-reales para esa comprobacion)")

    ok = sum(1 for _, o in RES if o)
    print("\n%d/%d checks" % (ok, len(RES)))
    raise SystemExit(0 if ok == len(RES) else 1)


if __name__ == "__main__":
    main()
