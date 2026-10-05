#!/usr/bin/env python3
"""Revocar enlaces a mano desde «Compartir»: lista de otros videos, revocar uno, revocar todos. API 9421 (datos x2), guest 9427."""
import json, os, subprocess, sys, time, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page
API = "http://127.0.0.1:9421"
C = []
def check(l, ok, d=""):
    C.append(bool(ok)); print(("  ✔ " if ok else "  ✘ ") + l + ((" — " + str(d)) if (d and not ok) else ""))
def http(m, path, body=None, raw=None, h=None, base=API):
    req = urllib.request.Request(base + path, method=m, data=(json.dumps(body).encode() if body is not None else raw),
                                 headers=dict({"Content-Type": "application/json"} if body is not None else {}, **(h or {})))
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"{}")
        except Exception: return e.code, {}
slug = "prueba-x2"
_, d = http("GET", "/api/proyectos/" + slug)
v1 = d["videos"][0]["id"]
# segundo video (mismo clip) para tener «otro video»
clip = open(os.path.join(ROOT, "clip.mp4"), "rb").read()
st, r = http("POST", "/api/proyectos/%s/videos" % slug, raw=clip, h={"X-Filename": "otro.mp4", "Content-Type": "application/octet-stream"})
_, d = http("GET", "/api/proyectos/" + slug)
v2 = [v["id"] for v in d["videos"] if v["id"] != v1][0]
mk = lambda vid, et: http("POST", "/api/proyectos/%s/videos/%s/invitar" % (slug, vid), {"dias": 7, "etiqueta": et, "ve_otras": False})[1]
a = mk(v1, "A en el video actual"); b = mk(v2, "B en otro video")
st, act = http("GET", "/api/invitados/activos")
check("API: /api/invitados/activos lista los 2 enlaces vivos con proyecto y video", st == 200 and len(act.get("enlaces", [])) == 2
      and all(e.get("proyecto") and e.get("video") and e.get("slug") == slug for e in act["enlaces"]), act)
# la puerta de invitados y las cabeceras de proxy NO ven esta ruta
gp = subprocess.Popen([sys.executable, os.path.join(ROOT, "guest.py"), "--puerto", "9427", "--api", API], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
try:
    check("seguridad: la puerta de invitados responde 404 a /api/invitados/activos", http("GET", "/api/invitados/activos", base="http://127.0.0.1:9427")[0] == 404)
finally:
    gp.terminate()
check("seguridad: con cabeceras de tunel (Cf-Ray) el 8477 responde 404", http("GET", "/api/invitados/activos", h={"Cf-Ray": "x"})[0] == 404)
pg = Page(API + "/", 1600, 1000); ev = pg.ev
pg.sleep(2); ev("openProject('%s')" % slug, await_promise=True); pg.sleep(2.5)
ev("openVideo('%s')" % v1, await_promise=True); pg.sleep(1.5)
ev("document.querySelector('#bShare').click()"); pg.sleep(1.8)
filas = ev("[...document.querySelectorAll('#shList .shlink')].map(r=>({otro:!!r.dataset.otro,txt:r.textContent.replace(/\\s+/g,' ').slice(0,120)}))")
check("popover: el enlace del video actual y el de otro video aparecen", len(filas) == 2 and sum(1 for f in filas if f["otro"]) == 1, filas)
check("popover: la fila de otro video nombra la etiqueta y el video", any(f["otro"] and "B en otro video" in f["txt"] and "otro.mp4" in f["txt"].lower() for f in filas), filas)
check("popover: hay «En otros videos» y «Revocar todos (2)»", ev("!!document.querySelector('#shList .shsec')") and ev("(document.querySelector('#shRevTodos')||{}).textContent") == "Revocar todos (2)")
# revocar el de otro video: primer clic arma, segundo revoca
ev("document.querySelector('#shList .shlink[data-otro] button[data-rev]').click()"); pg.sleep(.4)
check("revocar: el primer clic solo pide confirmación («¿Revocar?»)", ev("document.querySelector('#shList .shlink[data-otro] button[data-rev]').textContent") == "¿Revocar?"
      and len(http("GET", "/api/invitados/activos")[1]["enlaces"]) == 2)
ev("document.querySelector('#shList .shlink[data-otro] button[data-rev]').click()"); pg.sleep(1.5)
act = http("GET", "/api/invitados/activos")[1]["enlaces"]
check("revocar: el segundo clic revoca en el servidor (queda 1 vivo)", len(act) == 1 and act[0]["id"] == a["id"], act)
check("revocar: la fila de otro video desaparece del popover", ev("document.querySelectorAll('#shList .shlink[data-otro]').length") == 0)
check("revocar: «Revocar todos» ya no se ofrece con un solo enlace", ev("!document.querySelector('#shRevTodos')"))
# dos vivos de nuevo -> revocar todos
mk(v2, "C"); mk(v2, "D"); pg.sleep(.3)
ev("document.querySelector('#bShare').click()"); pg.sleep(.5); ev("document.querySelector('#bShare').click()"); pg.sleep(1.5)
check("revocar todos: se ofrece con 3 vivos", ev("(document.querySelector('#shRevTodos')||{}).textContent") == "Revocar todos (3)", ev("(document.querySelector('#shRevTodos')||{}).textContent"))
ev("document.querySelector('#shRevTodos').click()"); pg.sleep(.4)
check("revocar todos: el primer clic solo pide confirmación", ev("document.querySelector('#shRevTodos').textContent") == "¿Revocar los 3?" and len(http("GET", "/api/invitados/activos")[1]["enlaces"]) == 3)
ev("document.querySelector('#shRevTodos').click()"); pg.sleep(2)
check("revocar todos: no queda ningún enlace vivo", http("GET", "/api/invitados/activos")[1]["enlaces"] == [])
check("revocar todos: el popover queda sin filas vivas ni «Revocar todos»", ev("document.querySelectorAll('#shList .shlink:not(.muerto)').length") == 0 and ev("!document.querySelector('#shRevTodos')"))
pg.shot("enlaces-popover.png")
check("sin excepciones de JS", pg.errors == [], pg.errors[:3])
print("%d/%d checks" % (sum(C), len(C))); sys.exit(0 if all(C) else 1)
