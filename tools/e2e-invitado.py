#!/usr/bin/env python3
"""E2E de punta a punta del modo invitado: interfaz REAL (visor.html) contra la
puerta REAL (guest.py) y el servidor REAL (server.py), en Chrome de verdad.

    tools/chrome.sh start 9366
    CDP_PORT=9366 /tmp/o8/venv/bin/python tools/e2e-invitado.py
    # (o: CDP_PORT=9366 uv run --quiet --with websocket-client python3 tools/e2e-invitado.py)

Levanta los dos procesos con datos limpios (`data/`, `logs/`), crea proyecto +
video (clip.mp4) + enlace con la API de administracion y recorre el flujo del
invitado en el navegador: nombre, nota con texto, dibujo, tramo, respuesta,
edicion, acciones prohibidas desde la consola, caducidad a mitad de sesion y
revocacion. Despues abre la app de Cristian y comprueba la insignia, el popover
«Compartir» contra los endpoints reales, responder y resolver. Mide la latencia
nota-invitado -> app-de-Cristian y el 206 del video por la puerta.

OPENFRAME_NO_PUBLICAR=1 siempre: esto no toca el tunel.
Capturas en shots/ (mirarlas con Read). Sale 1 si falla algun check.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = "/usr/bin/python3"                     # el Python 3.9 del sistema, como en produccion
SHOTS = os.path.join(ROOT, "shots")

RES = []
TIEMPOS = {}


def check(nombre, ok, detalle=""):
    RES.append((nombre, bool(ok), detalle))
    print(("  OK  " if ok else "  FALLA ") + nombre +
          (("  -- " + str(detalle)[:300]) if (detalle and not ok) else ""))
    return bool(ok)


# ─────────────────────────── HTTP sin dependencias ───────────────────────────

class SinRedirigir(urllib.request.HTTPRedirectHandler):
    """El 302 de /r/<token> es el objeto de la prueba: seguirlo oculta el Set-Cookie."""

    def redirect_request(self, *a, **kw):
        return None


ABRIR = urllib.request.build_opener(SinRedirigir)


def http(method, url, obj=None, raw=None, headers=None, timeout=20, seguir=True):
    body = raw if raw is not None else (json.dumps(obj).encode("utf-8") if obj is not None else None)
    req = urllib.request.Request(url, data=body, method=method)
    if raw is None and obj is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    abrir = urllib.request.urlopen if seguir else ABRIR.open
    try:
        with abrir(req, timeout=timeout) as r:
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
    except Exception as e:
        return 0, str(e), {}


def libre(puerto):
    s = socket.socket()
    # SO_REUSEADDR: igual que http.server, para no confundir un TIME_WAIT con ocupado
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", puerto))
        return True
    except OSError:
        return False
    finally:
        s.close()


def elegir(puerto, tomados=()):
    """El puerto asignado, o el siguiente libre si algo lo tiene ocupado."""
    for p in range(puerto, puerto + 40):
        if p not in tomados and libre(p):
            return p
    raise SystemExit("no hay puertos libres cerca de %d" % puerto)


def esperar(url, segundos=25):
    fin = time.time() + segundos
    while time.time() < fin:
        st, _, _ = http("GET", url, timeout=3)
        if st == 200:
            return True
        time.sleep(0.3)
    return False


# ─────────────────────────────── arranque ───────────────────────────────

class Entorno(object):
    def __init__(self, p_admin, p_gate):
        self.admin = "http://127.0.0.1:%d" % p_admin
        self.gate = "http://127.0.0.1:%d" % p_gate
        self.procs = []
        env = dict(os.environ, OPENFRAME_NO_PUBLICAR="1")
        subprocess.call(["rm", "-rf", os.path.join(ROOT, "data"), os.path.join(ROOT, "logs")])
        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
        for args, out in ((["--puerto", str(p_admin)], "server.out"),):
            self.procs.append(subprocess.Popen(
                [PY, "server.py"] + args, cwd=ROOT, env=env,
                stdout=open(os.path.join(ROOT, "logs", out), "w"), stderr=subprocess.STDOUT))
        if not esperar(self.admin + "/api/ping"):
            self.parar()
            raise SystemExit("server.py no arranco en %s" % self.admin)
        self.procs.append(subprocess.Popen(
            [PY, "guest.py", "--puerto", str(p_gate), "--api", self.admin], cwd=ROOT, env=env,
            stdout=open(os.path.join(ROOT, "logs", "guest.out"), "w"), stderr=subprocess.STDOUT))
        if not esperar(self.gate + "/api/ping"):
            self.parar()
            raise SystemExit("guest.py no arranco en %s" % self.gate)

    def parar(self):
        for p in self.procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in self.procs:
            try:
                p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass


def notas_servidor(admin, slug):
    st, d, _ = http("GET", admin + "/api/notas/" + slug)
    return (d or {}).get("notas", []) if st == 200 else []


def nota_por_id(admin, slug, nid):
    return next((n for n in notas_servidor(admin, slug) if n.get("id") == nid), None)


def enlaces(admin, slug, vid):
    st, d, _ = http("GET", "%s/api/proyectos/%s/videos/%s/invitar" % (admin, slug, vid))
    return (d or {}).get("enlaces", []) if st == 200 else []


def links_path(slug, vid):
    return os.path.join(ROOT, "data", slug, "videos", vid, "invitados.json")


# ─────────────────────────────── utilidades de pagina ───────────────────────────────

FETCH = """
window.__t = async (m, p, b) => {
  try{
    const r = await fetch(p, {method: m, headers: {'Content-Type':'application/json'},
                              body: b == null ? undefined : JSON.stringify(b)});
    let t = ''; try{ t = await r.text(); }catch(e){}
    return {s: r.status, t: t.slice(0, 300)};
  }catch(e){ return {s: -1, t: String(e)}; }
};
true
"""


def evp(pg, expr):
    """Evalua una promesa que usa __t (lo inyecta antes). Devuelve siempre un dict."""
    pg.ev(FETCH)
    out = pg.ev(expr, await_promise=True)
    return out if isinstance(out, dict) else {"s": -1, "t": str(out)}


def tp(pg, method, path, body=None):
    return evp(pg, "__t(%s, %s, %s)" % (json.dumps(method), json.dumps(path),
                                        "null" if body is None else json.dumps(body)))


def nav(pg, url, espera=1.4):
    pg.url = url
    pg.send("Page.navigate", url=url)
    time.sleep(espera)


def esperar_js(pg, expr, segundos=12, paso=0.3):
    fin = time.time() + segundos
    ultimo = None
    while time.time() < fin:
        ultimo = pg.ev(expr)
        if ultimo:
            return ultimo
        time.sleep(paso)
    return ultimo


def errores_reales(pg):
    """Errores de pagina que no son 404 esperados de la puerta."""
    fuera = []
    for e in pg.errors:
        s = str(e)
        if "404" in s or "Failed to load resource" in s or "net::ERR_ABORTED" in s:
            continue
        fuera.append(s)
    return fuera


# ═══════════════════════════════════ MAIN ═══════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin", type=int, default=9391)
    ap.add_argument("--gate", type=int, default=9392)
    args = ap.parse_args()

    p_admin = elegir(args.admin)
    p_gate = elegir(args.gate, tomados={p_admin})
    if (p_admin, p_gate) != (args.admin, args.gate):
        print("! puertos ocupados; uso %d (server) y %d (puerta)" % (p_admin, p_gate))
    env = Entorno(p_admin, p_gate)
    ADMIN, GATE = env.admin, env.gate
    try:
        correr(ADMIN, GATE)
    finally:
        env.parar()

    malos = [n for n, ok, _ in RES if not ok]
    print("\n%d/%d checks" % (len(RES) - len(malos), len(RES)))
    for k, v in TIEMPOS.items():
        print("  · %s: %s" % (k, v))
    if malos:
        print("FALLAN:")
        for n in malos:
            print("  - " + n)
    return 1 if malos else 0


def correr(ADMIN, GATE):  # noqa: C901  (es un recorrido lineal, se lee de arriba abajo)
    # ── 1. datos reales por la API de administracion ──
    print("\n== administracion (server.py) ==")
    check("server.py responde /api/ping", http("GET", ADMIN + "/api/ping")[1].get("ok") is True)
    check("guest.py responde /api/ping", http("GET", GATE + "/api/ping")[1].get("ok") is True)

    st, d, _ = http("POST", ADMIN + "/api/proyectos", {"nombre": "Cafe Lumen", "cliente": "Lumen SA"})
    SLUG = (d or {}).get("slug")
    check("proyecto creado", st == 200 and SLUG == "cafe-lumen", (st, d))

    with open(os.path.join(ROOT, "clip.mp4"), "rb") as f:
        clip = f.read()
    st, d, _ = http("POST", ADMIN + "/api/proyectos/%s/videos" % SLUG, raw=clip,
                    headers={"X-Filename": "clip.mp4", "Content-Type": "application/octet-stream"})
    VID = ((d or {}).get("video") or {}).get("id")
    FPS = ((d or {}).get("video") or {}).get("fps")
    check("video subido con fps real del clip", st == 200 and VID and abs((FPS or 0) - 21.533) < 0.01, (st, FPS))
    # un segundo video: el invitado NUNCA debe verlo
    st, d, _ = http("POST", ADMIN + "/api/proyectos/%s/videos" % SLUG, raw=clip,
                    headers={"X-Filename": "otro.mp4", "Content-Type": "application/octet-stream"})
    VID2 = ((d or {}).get("video") or {}).get("id")
    check("segundo video (el prohibido) creado", st == 200 and VID2 and VID2 != VID, (st, VID2))
    # otro proyecto: el invitado NUNCA debe verlo
    st, d, _ = http("POST", ADMIN + "/api/proyectos", {"nombre": "Otro Cliente", "cliente": "X"})
    SLUG2 = (d or {}).get("slug")
    check("segundo proyecto (el prohibido) creado", st == 200 and SLUG2 and SLUG2 != SLUG, (st, SLUG2))

    st, d, _ = http("POST", "%s/api/proyectos/%s/videos/%s/invitar" % (ADMIN, SLUG, VID),
                    {"dias": 7, "etiqueta": "Marta (cliente)", "ve_otras": False})
    LINK = d or {}
    TOKEN = LINK.get("token", "")
    EID = LINK.get("id", "")
    check("enlace creado 201 con token de 43 chars", st == 201 and len(TOKEN) == 43 and len(EID) == 8, (st, LINK))
    check("respuesta del POST /invitar trae publicada=false y aviso (NO_PUBLICAR)",
          LINK.get("publicada") is False and "aviso" in LINK, LINK)
    check("url del enlace usa la base publica",
          LINK.get("url", "").startswith("https://openframe.inspiredink.space/r/"), LINK.get("url"))
    # enlace de OTRO invitado al mismo video: sus notas no deben verse (ve_otras=false)
    st, d2, _ = http("POST", "%s/api/proyectos/%s/videos/%s/invitar" % (ADMIN, SLUG, VID),
                     {"dias": 7, "etiqueta": "Otro invitado", "ve_otras": False})
    EID_OTRO, TOKEN_OTRO = (d2 or {}).get("id"), (d2 or {}).get("token")
    check("segundo enlace del mismo video creado", st == 201 and EID_OTRO and EID_OTRO != EID, (st, d2))

    # ── 2. /r/<token> crudo: cabeceras y cookie ──
    st, _, h = http("GET", GATE + "/r/" + TOKEN, seguir=False)
    cookie = h.get("Set-Cookie", "")
    check("/r/<token> redirige 302 a /", st == 302 and h.get("Location") == "/", (st, h.get("Location")))
    check("cookie ofg HttpOnly+Secure+SameSite=Lax+Path=/ con Max-Age",
          cookie.startswith("ofg=" + TOKEN) and "HttpOnly" in cookie and "Secure" in cookie
          and "SameSite=Lax" in cookie and "Path=/" in cookie and "Max-Age=" in cookie, cookie)
    check("cabeceras de privacidad en la puerta",
          h.get("Cache-Control") == "no-store" and "noindex" in (h.get("X-Robots-Tag") or "")
          and h.get("Referrer-Policy") == "no-referrer"
          and h.get("X-Content-Type-Options") == "nosniff", h)
    usos_antes = next((e for e in enlaces(ADMIN, SLUG, VID) if e["id"] == EID), {}).get("usos")
    check("GET /r/<token> cuenta usos", usos_antes and usos_antes >= 1, usos_antes)

    # ── 3. el invitado en Chrome real ──
    print("\n== invitado en Chrome (puerta real) ==")
    pg = Page(url=GATE + "/r/" + TOKEN, w=1600, h=1000)
    try:
        pg.send("Browser.grantPermissions",
                origin=GATE, permissions=["clipboardReadWrite", "clipboardSanitizedWrite"])
    except Exception:
        pass
    time.sleep(1.4)
    inv = pg.ev("window.__INVITADO ? JSON.parse(JSON.stringify(window.__INVITADO)) : null")
    check("window.__INVITADO inyectado con slug/video del enlace",
          isinstance(inv, dict) and inv.get("slug") == SLUG and inv.get("video") == VID, inv)
    check("window.__INVITADO trae enlace_id (lo pedia U2 para saber que notas son suyas)",
          isinstance(inv, dict) and inv.get("enlace_id") == EID, inv)
    check("window.__INVITADO trae proyecto/version legibles y ve_otras=false",
          isinstance(inv, dict) and (inv.get("proyecto") or {}).get("nombre") == "Cafe Lumen"
          and (inv.get("version") or {}).get("nombre") == "clip.mp4" and inv.get("ve_otras") is False, inv)
    check("nombre nulo al entrar (aun no hay cookie ofn)", inv and inv.get("nombre") is None, inv)
    check("body.invitado y banner presente",
          pg.ev("document.body.classList.contains('invitado') && !!document.getElementById('invBanner')"))
    check("sin scroll de pagina a 1600x1000",
          pg.ev("document.documentElement.scrollHeight <= window.innerHeight + 2"),
          pg.ev("document.documentElement.scrollHeight + '>' + window.innerHeight"))

    dlg = esperar_js(pg, "document.getElementById('invDlg').classList.contains('on')")
    check("dialogo «¿Cómo te llamas?» abierto solo", dlg)
    pg.shot("i01-dialogo-nombre.png")

    ocultos = ["#bProj", "#bUp", "#bDel", "#bOut", "#bHer", "#bClaude", "#bShare", "#bMove",
               "#plist", "#vlist", "#sello", "#bUndoAccion", "#bRedoAccion", ".rail", ".vcol"]
    falla = pg.ev("JSON.stringify(%s.filter(s => {const e=document.querySelector(s); "
                  "return e && e.offsetParent !== null;}))" % json.dumps(ocultos))
    check("15 controles de Cristian OCULTOS (offsetParent null)", falla == "[]", falla)
    visibles = ["#invBanner", "#bPlay", "#ta", "#bSave", "#bEnd", "#bGo", "[data-tool=pen]",
                "#swBtn", "#filtersBtn", "#filterBar .seg-btn[data-type=all]", "#bErase", "#scrub"]
    falta = pg.ev("JSON.stringify(%s.filter(s => {const e=document.querySelector(s); "
                  "return !e || e.offsetParent === null;}))" % json.dumps(visibles))
    check("controles de revision DISPONIBLES", falta == "[]", falta)

    NOMBRE = "Marta Ríos"
    pg.ev("document.getElementById('invNombre').value = %s" % json.dumps(NOMBRE))
    pg.click("#invDlgOk")
    ok = esperar_js(pg, "!document.getElementById('invDlg').classList.contains('on')")
    check("POST /api/invitado/nombre cierra el dialogo", ok)
    check("banner «Revisando como <nombre> · <proyecto> · <version>»",
          all(x in (pg.ev("document.getElementById('invBanner').textContent") or "")
              for x in ("Revisando como", NOMBRE, "Cafe Lumen", "clip.mp4")),
          pg.ev("document.getElementById('invBanner').textContent"))
    pg.shot("i02-banner-sin-notas.png")

    # ── nota con texto ──
    pg.ev("v.currentTime = 1.0")
    time.sleep(0.4)
    pg.ev("document.getElementById('ta').value = 'El logo entra tarde; súbelo medio segundo.'")
    pg.ev("document.getElementById('ta').dispatchEvent(new Event('input'))")
    pg.click("#bSave")
    time.sleep(1.2)
    notas = notas_servidor(ADMIN, SLUG)
    n1 = next((n for n in notas if "logo entra tarde" in (n.get("text") or "")), None)
    check("nota con texto creada por la puerta", n1 is not None, [n.get("text") for n in notas])
    check("la puerta FUERZA author=invitado, autor_nombre y enlace_id",
          n1 and n1.get("author") == "invitado" and n1.get("autor_nombre") == NOMBRE
          and n1.get("enlace_id") == EID, n1)
    check("la puerta FUERZA el video compartido y el fps real",
          n1 and n1.get("video") == VID and abs((n1.get("fps") or 0) - 21.533) < 0.01, n1)
    check("insignia «Invitado · Nombre» en la tarjeta del invitado",
          ("Invitado · " + NOMBRE) in (pg.ev("document.getElementById('list').textContent") or ""),
          pg.ev("document.getElementById('list').textContent"))
    check("la tarjeta lleva data-who=invitado",
          pg.ev("!!document.querySelector('.item[data-who=\"invitado\"]')"))

    # ── nota con dibujo ──
    # Desde la fase 2 del porte el trazo es un BORRADOR local (`tmp_`) y texto +
    # trazos + tramo + JPEG viajan en UN SOLO POST al pulsar Guardar: el dibujo ya
    # no crea una nota vacia en el servidor a mitad del gesto.
    pg.ev("""window.__posts = [];
             const _f = window.fetch;
             window.fetch = function(u, o){ try{ if(o && o.method === 'POST' && o.body)
               window.__posts.push({u: String(u), len: o.body.length}); }catch(e){}
               return _f.apply(this, arguments); };
             true""")
    r = pg.rect("#cv")
    pg.ev("v.currentTime = 2.0")
    time.sleep(0.4)
    pg.click("[data-tool=pen]")
    if r:
        pg.drag(r["x"] + r["w"] * 0.3, r["y"] + r["h"] * 0.35,
                r["x"] + r["w"] * 0.7, r["y"] + r["h"] * 0.6, steps=10)
    time.sleep(1.2)
    borrador = pg.ev("JSON.stringify((st.notas||[]).filter(n=>String(n.id).startsWith('tmp_'))"
                     ".map(n=>({id:n.id, frame:n.frame,"
                     "pts:(n.drawing&&n.drawing.strokes||[]).reduce((a,s)=>a+(s.pts||[]).length,0)})))")
    bs = json.loads(borrador or "[]")
    check("el trazo nace como BORRADOR local (tmp_), sin nota vacia en el servidor",
          len(bs) == 1 and bs[0]["pts"] >= 3
          and not any((n.get("drawing") or {}).get("strokes") for n in notas_servidor(ADMIN, SLUG)), bs)
    check("dibujar NO manda ningun POST por la puerta (un solo POST al guardar)",
          pg.ev("window.__posts.length") == 0, pg.ev("JSON.stringify(window.__posts)"))
    check("el borrador se marca como «borrador» en la tarjeta",
          pg.ev("!!document.querySelector('.draft-badge')"),
          pg.ev("document.getElementById('list').textContent"))
    pg.click("#bSave")
    time.sleep(1.8)
    check("Guardar manda UN solo POST con el dibujo dentro",
          pg.ev("window.__posts.length") == 1
          and (pg.ev("JSON.stringify(window.__posts)") or "").find("/notas") > 0,
          pg.ev("JSON.stringify(window.__posts)"))
    dibujadas = [n for n in notas_servidor(ADMIN, SLUG)
                 if (n.get("drawing") or {}).get("strokes")]
    nd = dibujadas[0] if dibujadas else None
    pts = sum(len(s.get("pts") or []) for s in ((nd or {}).get("drawing") or {}).get("strokes", []))
    puntos_ok = all(0 <= p.get("x", -1) <= 1 and 0 <= p.get("y", -1) <= 1
                    for s in ((nd or {}).get("drawing") or {}).get("strokes", [])
                    for p in (s.get("pts") or []))
    check("nota con DIBUJO guardada por la puerta (strokes con pts normalizados)",
          nd is not None and pts >= 3 and puntos_ok, (len(dibujadas), pts, puntos_ok))
    check("el dibujo del invitado lleva su enlace_id", nd and nd.get("enlace_id") == EID, nd)
    check("el JPEG de la nota con dibujo viaja en el mismo POST y queda en disco",
          nd and nd.get("thumb") == nd["id"] + ".jpg"
          and os.path.isfile(os.path.join(ROOT, "thumbs", SLUG, nd["thumb"])), nd and nd.get("thumb"))
    check("el borrador desaparece al guardarse (ningun tmp_ huerfano)",
          pg.ev("(st.notas||[]).filter(n=>String(n.id).startsWith('tmp_')).length") == 0)
    pg.ev("document.querySelector('[data-tool=pen]').click()")   # soltar la herramienta
    pg.shot("i03-nota-y-dibujo.png")

    # ── nota con tramo (end_frame viaja en el POST) ──
    pg.ev("v.currentTime = 3.0")
    time.sleep(0.3)
    pg.ev("document.getElementById('ta').value = 'Desde aquí hasta el corte sobra música.'")
    pg.ev("document.getElementById('ta').dispatchEvent(new Event('input'))")
    pg.ev("st.pend = {frame: snap(3.0), time: 3.0}")
    pg.ev("v.currentTime = 4.5")
    time.sleep(0.3)
    pg.click("#bEnd")
    time.sleep(0.3)
    tramo = pg.ev("st.invTramo ? JSON.stringify(st.invTramo) : null")
    pg.click("#bSave")
    time.sleep(1.2)
    nt = next((n for n in notas_servidor(ADMIN, SLUG) if "sobra música" in (n.get("text") or "")), None)
    check("nota con TRAMO: end_frame > frame guardado por la puerta",
          nt and nt.get("end_frame") and nt["end_frame"] > nt["frame"], (tramo, nt))

    # ── respuesta propia ──
    pg.ev("startReply(%s)" % json.dumps(n1["id"]))
    time.sleep(0.3)
    pg.ev("document.getElementById('ta').value = 'Me refiero al primer plano.'")
    pg.ev("document.getElementById('ta').dispatchEvent(new Event('input'))")
    pg.click("#bSave")
    time.sleep(1.2)
    rep = next((n for n in notas_servidor(ADMIN, SLUG) if n.get("parent") == n1["id"]), None)
    check("respuesta del invitado con parent correcto y frame heredado",
          rep and rep.get("author") == "invitado" and rep.get("frame") == n1.get("frame"), rep)

    # ── editar SU nota ──
    pg.ev("startEdit(%s)" % json.dumps(n1["id"]))
    time.sleep(0.3)
    pg.ev("document.getElementById('ta').value = 'El logo entra tarde (editado por Marta).'")
    pg.ev("document.getElementById('ta').dispatchEvent(new Event('input'))")
    pg.click("#bSave")
    time.sleep(1.2)
    n1b = nota_por_id(ADMIN, SLUG, n1["id"])
    check("PATCH /api/notas/<slug>/<id>: el invitado edita SU texto",
          n1b and "editado por Marta" in (n1b.get("text") or ""), n1b and n1b.get("text"))

    # ── miniatura: nace en el navegador, viaja por la puerta y vuelve por /thumbs ──
    pg.ev("""window.__thumb = (() => {
      const c = document.createElement('canvas'); c.width = 96; c.height = 54;
      const g = c.getContext('2d'); g.fillStyle = '#111'; g.fillRect(0,0,96,54);
      g.fillStyle = '#fff'; g.fillRect(8,8,40,20);
      return c.toDataURL('image/jpeg', 0.7);
    })(); window.__thumb.length""")
    rt = evp(pg, "__t('POST', %s, {frame: 60, text: 'Nota con miniatura', thumb: window.__thumb})"
                 % json.dumps("/api/proyectos/%s/notas" % SLUG))
    nmini = next((n for n in notas_servidor(ADMIN, SLUG) if "miniatura" in (n.get("text") or "")), None)
    check("nota con THUMB aceptada por la puerta y guardada como <id>.jpg",
          rt.get("s") == 201 and nmini and nmini.get("thumb") == nmini["id"] + ".jpg", (rt, nmini))
    check("el jpeg existe en disco",
          nmini and os.path.isfile(os.path.join(ROOT, "thumbs", SLUG, nmini["thumb"])))
    pg.ev("setThumbs(true)")
    cargada = esperar_js(pg, "(()=>{const i=[...document.querySelectorAll('.item img.thumb')]"
                             ".find(x=>x.src.indexOf(%s)>=0); return i && i.complete && i.naturalWidth>0})()"
                         % json.dumps(nmini["thumb"] if nmini else "x"), 10)
    check("la miniatura se descarga por /thumbs de la puerta y se pinta", cargada)
    pg.ev("setThumbs(false)")
    r = tp(pg, "GET", "/thumbs/%s/%s.jpg" % (SLUG, "n_00000000"))
    check("thumb de una nota que el invitado no ve -> 404", r.get("s") == 404, r)

    # ── topes y rechazos de la puerta vistos desde el navegador ──
    r = evp(pg, """(async () => {
      const pts = []; for(let i=0;i<401;i++) pts.push({x: i/401, y: 0.5});
      return await __t('POST', %s, {frame: 70, text: 'dibujo enorme',
                                    drawing: {strokes: [{tool:'pen', color:'#ff4d4d', size:3, pts: pts}]}});
    })()""" % json.dumps("/api/proyectos/%s/notas" % SLUG))
    check("dibujo por encima del tope de puntos -> 413", r.get("s") == 413, r)
    r = tp(pg, "POST", "/api/proyectos/%s/notas" % SLUG,
           {"frame": 1, "text": "respuesta a una nota que no veo", "parent": "n_deadbeef"})
    check("responder a una nota que el invitado no ve -> 404", r.get("s") == 404, r)
    for mal, etiqueta in ((" ", "en blanco"), ("x" * 41, "de 41 caracteres"), ("a\u0007b", "con control chars")):
        r = tp(pg, "POST", "/api/invitado/nombre", {"nombre": mal})
        check("nombre %s -> 400" % etiqueta, r.get("s") == 400, (mal, r))
    nom_ok = tp(pg, "POST", "/api/invitado/nombre", {"nombre": NOMBRE})
    check("el nombre bueno se vuelve a aceptar", nom_ok.get("s") == 200, nom_ok)

    # ── XSS: el nombre y el texto viajan crudos; la interfaz los pinta literales ──
    XSS = "<img src=x onerror=window.__xss=1>"
    tp(pg, "POST", "/api/invitado/nombre", {"nombre": XSS})
    tp(pg, "POST", "/api/proyectos/%s/notas" % SLUG,
       {"frame": 80, "text": "<b>texto</b><img src=x onerror=window.__xss=2>"})
    pg.ev("pullInvitado()", await_promise=True)
    time.sleep(0.8)
    pg.ev("renderList()")
    check("nombre y texto con HTML se pintan literales (window.__xss nunca existe)",
          pg.ev("typeof window.__xss === 'undefined'") and
          pg.ev("document.getElementById('list').textContent.indexOf('<img src=x') >= 0"),
          pg.ev("document.getElementById('list').textContent").__str__()[:200])
    tp(pg, "POST", "/api/invitado/nombre", {"nombre": NOMBRE})
    pg.ev("INV.nombre = %s; invPintarBanner()" % json.dumps(NOMBRE))

    # ── notas ajenas: de Cristian, de otro enlace, de otro video, de otro proyecto ──
    st, d, _ = http("POST", ADMIN + "/api/proyectos/%s/notas" % SLUG,
                    {"video": VID, "frame": 30, "text": "Nota interna de Cristian", "author": "cristian"})
    N_CRIS = ((d or {}).get("nota") or {}).get("id")
    st, d, _ = http("POST", ADMIN + "/api/proyectos/%s/notas" % SLUG,
                    {"video": VID2, "frame": 10, "text": "Nota del OTRO video", "author": "cristian"})
    N_OTROVID = ((d or {}).get("nota") or {}).get("id")
    # nota del otro invitado, creada como lo haria su puerta (con el secreto de la puerta)
    secreto = open(os.path.join(ROOT, "data", ".guest_secret"), "rb").read()
    st, d, _ = http("POST", ADMIN + "/api/proyectos/%s/notas" % SLUG,
                    {"video": VID, "frame": 40, "text": "Nota del OTRO invitado",
                     "autor_nombre": "Otro", "enlace_id": EID_OTRO},
                    headers={"X-Guest-Gate": secreto.hex()})
    N_OTROINV = ((d or {}).get("nota") or {}).get("id")
    check("nota del otro invitado creada via X-Guest-Gate", st == 201 and N_OTROINV, (st, d))

    st, d, _ = http("GET", GATE + "/api/notas/" + SLUG,
                    headers={"Cookie": "ofg=" + TOKEN})
    vis = {n["id"] for n in (d or {}).get("notas", [])}
    check("ve_otras=false: el invitado NO ve la nota de otro enlace", N_OTROINV not in vis, sorted(vis))
    check("el invitado NUNCA ve notas de otro video", N_OTROVID not in vis, sorted(vis))
    check("el invitado SI ve sus notas", n1["id"] in vis and rep["id"] in vis, sorted(vis))

    # respuesta de Cristian a la nota del invitado: SI debe verse
    st, d, _ = http("POST", ADMIN + "/api/proyectos/%s/notas" % SLUG,
                    {"video": VID, "parent": n1["id"], "text": "Hecho, lo subo medio segundo.",
                     "author": "cristian"})
    N_RESPCRIS = ((d or {}).get("nota") or {}).get("id")
    st, d, _ = http("GET", GATE + "/api/notas/" + SLUG, headers={"Cookie": "ofg=" + TOKEN})
    vis = {n["id"] for n in (d or {}).get("notas", [])}
    check("la respuesta de Cristian a SU nota SI es visible", N_RESPCRIS in vis, sorted(vis))

    llego = esperar_js(pg, "JSON.stringify(st.notas.map(n=>n.id)).indexOf(%s) >= 0" % json.dumps(N_RESPCRIS), 12)
    check("el sondeo del invitado trae la respuesta de Cristian (rev de /api/proyectos/<slug>)", llego)
    # El hilo ya esta montado; seguir es una accion explicita de lectura.
    pg.ev("x2SeguirNota(%s); renderList()" % json.dumps(n1["id"]))
    check("la respuesta de Cristian se pinta como «Cristian», no como invitado",
          pg.ev("!!document.querySelector('.reply[data-who=\"cristian\"] .item-top strong') && document.querySelector('.reply[data-who=\"cristian\"] .item-top strong').textContent==='Cristian'"),
          (pg.ev("document.getElementById('hiloCount').textContent"),
           pg.ev("document.getElementById('list').textContent")))
    pg.shot("i04-hilo-con-cristian.png")

    # ── acciones prohibidas desde la consola del invitado ──
    print("\n== acciones prohibidas contra la puerta real ==")
    pro = [
        ("borrar su propia nota (DELETE)", "DELETE", "/api/notas/%s/%s" % (SLUG, n1["id"]), None),
        ("borrar por la ruta de proyectos", "DELETE", "/api/proyectos/%s/notas/%s" % (SLUG, n1["id"]), None),
        ("resolver un hilo (PATCH resolved)", "PATCH", "/api/notas/%s/%s" % (SLUG, n1["id"]), {"resolved": True}),
        ("marcar visto", "PATCH", "/api/notas/%s/%s" % (SLUG, n1["id"]), {"visto": True}),
        ("mover la nota de fotograma", "PATCH", "/api/notas/%s/%s" % (SLUG, n1["id"]), {"frame": 999}),
        ("editar la nota de Cristian", "PATCH", "/api/notas/%s/%s" % (SLUG, N_CRIS), {"text": "mio"}),
        ("editar la nota del otro invitado", "PATCH", "/api/notas/%s/%s" % (SLUG, N_OTROINV), {"text": "mio"}),
        ("listar TODOS los proyectos", "GET", "/api/proyectos", None),
        ("ver OTRO proyecto", "GET", "/api/proyectos/" + SLUG2, None),
        ("ver las notas de OTRO proyecto", "GET", "/api/notas/" + SLUG2, None),
        ("crear proyecto", "POST", "/api/proyectos", {"nombre": "mio"}),
        ("subir video", "POST", "/api/proyectos/%s/videos" % SLUG, {}),
        ("archivar el proyecto", "POST", "/api/proyectos/%s/archivar" % SLUG, {}),
        ("heredar hilos", "POST", "/api/proyectos/%s/heredar" % SLUG, {"desde": VID, "hacia": VID2}),
        ("ver los hilos (vista de Cristian)", "GET", "/api/proyectos/%s/hilos" % SLUG, None),
        ("listar los enlaces de invitado", "GET", "/api/proyectos/%s/videos/%s/invitar" % (SLUG, VID), None),
        ("crear otro enlace de invitado", "POST", "/api/proyectos/%s/videos/%s/invitar" % (SLUG, VID), {"dias": 90}),
        ("leer la actividad de invitados", "GET", "/api/invitados/actividad", None),
        ("ver el estado de la puerta", "GET", "/api/invitados/estado", None),
        ("descargar el video del OTRO video", "GET", "/media/%s/%s/media.mp4" % (SLUG, VID2), None),
        ("tocar la meta del video", "POST", "/api/proyectos/%s/videos/%s/meta" % (SLUG, VID), {"fps": 1}),
    ]
    for nombre, m, p, b in pro:
        r = tp(pg, m, p, b)
        check("prohibido: %s -> 404" % nombre, r.get("s") == 404, r)
    check("el 404 de la puerta no hace eco de la ruta ni del token",
          not any(x in (tp(pg, "GET", "/api/proyectos/" + SLUG2) or {}).get("t", "")
                  for x in (SLUG2, TOKEN)))
    # la nota de Cristian sigue intacta tras los intentos
    nc = nota_por_id(ADMIN, SLUG, N_CRIS)
    check("la nota de Cristian sigue intacta y sin resolver",
          nc and nc.get("text") == "Nota interna de Cristian" and not nc.get("resolved"), nc)
    nm = nota_por_id(ADMIN, SLUG, n1["id"])
    check("la nota del invitado no se pudo resolver ni mover ni borrar",
          nm and not nm.get("resolved") and nm.get("frame") == n1.get("frame"), nm)

    # ── auditoria del porte (fases 1-3) con window.__INVITADO ──
    print("\n== auditoria de las fases 1-3 en modo invitado ==")
    AJENAS = ["Nota interna de Cristian", "Nota del OTRO invitado", "Nota del OTRO video"]
    fuga = pg.ev("""(()=>{
      const malas = [], antes = st.x2Person;
      for(const p of ['all','cristian','claude','invitado']){
        st.x2Person = p; renderList();
        const t = document.getElementById('list').textContent;
        for(const s of %s) if(t.indexOf(s) >= 0) malas.push(p + ':' + s);
      }
      st.x2Person = antes; renderList();
      return JSON.stringify(malas);
    })()""" % json.dumps(AJENAS))
    check("ningun filtro de persona expone notas ajenas con ve_otras=false", fuga == "[]", fuga)
    sin_decidir = pg.ev("JSON.stringify([...document.querySelectorAll("
                        "'[data-approve],[data-adjust],[data-redecide],.approve-btn,.adjust-btn')]"
                        ".map(e=>e.outerHTML.slice(0,60)))")
    check("cero botones de decision (Aprobar / Pedir ajuste / Cambiar decision) en la pagina del invitado",
          sin_decidir == "[]", sin_decidir)
    # las funciones de decision existen en el script: llamarlas a mano no debe hacer nada
    pg.ev("x2Aprobar(%s); x2PedirAjuste(%s); x2Reconsiderar(%s); true"
          % (json.dumps(n1["id"]), json.dumps(n1["id"]), json.dumps(n1["id"])))
    time.sleep(1.0)
    nd1 = nota_por_id(ADMIN, SLUG, n1["id"])
    check("x2Aprobar/x2PedirAjuste/x2Reconsiderar desde la consola del invitado no cambian nada",
          nd1 and not nd1.get("decision") and not nd1.get("resolved")
          and not pg.ev("!!st.adjustTo"), nd1)
    # Ctrl+Z del invitado: deshace SU dibujo y NUNCA el de otra persona
    pg.ev("v.currentTime = 2.0")
    time.sleep(0.4)
    pg.click("[data-tool=pen]")
    rcv = pg.rect("#cv")        # `r` se reutiliza para respuestas HTTP mas arriba
    if rcv:
        pg.drag(rcv["x"] + rcv["w"] * 0.4, rcv["y"] + rcv["h"] * 0.5,
                rcv["x"] + rcv["w"] * 0.6, rcv["y"] + rcv["h"] * 0.7, steps=8)
    time.sleep(1.0)
    pg.ev("document.querySelector('[data-tool=pen]').click()")
    antes_z = pg.ev("(()=>{const n=st.notas.find(x=>x.id===%s);"
                    "return n && n.drawing ? (n.drawing.strokes||[]).length : -1})()" % json.dumps(nd["id"]))
    pg.ev("deshacer()", await_promise=True)
    time.sleep(0.6)
    check("Ctrl+Z del invitado deshace SU trazo (antes no deshacia nada)",
          pg.ev("(()=>{const d=st.notas.filter(n=>String(n.id).startsWith('tmp_'));"
                "return d.length===0 || (d[0].drawing.strokes||[]).length===0})()"),
          pg.ev("JSON.stringify((st.notas||[]).filter(n=>String(n.id).startsWith('tmp_'))"
                ".map(n=>(n.drawing.strokes||[]).length))"))
    # ahora con una nota AJENA seleccionada: deshacer no debe tocarla
    pg.ev("st.selId = %s; true" % json.dumps(N_CRIS))
    pg.ev("deshacer()", await_promise=True)
    pg.ev("rehacer()", await_promise=True)
    time.sleep(0.8)
    ncris2 = nota_por_id(ADMIN, SLUG, N_CRIS)
    check("deshacer/rehacer con una nota AJENA seleccionada no la toca (ni local ni en el servidor)",
          ncris2 and ncris2.get("text") == "Nota interna de Cristian"
          and not (ncris2.get("drawing") or {}).get("strokes")
          and not pg.ev("(()=>{const n=st.notas.find(x=>x.id===%s);"
                        "return !!(n && n.drawing && (n.drawing.strokes||[]).length)})()" % json.dumps(N_CRIS)),
          ncris2)
    nd_ok = nota_por_id(ADMIN, SLUG, nd["id"]) if nd else None
    check("el dibujo ya guardado del invitado sigue intacto tras deshacer/rehacer",
          nd_ok and len((nd_ok.get("drawing") or {}).get("strokes") or []) == antes_z, (antes_z, nd_ok))
    pg.ev("st.selId = null; renderList(); true")

    # Lo que escribe el invitado debe quedar dentro de su caja desplazable.
    pg.ev("v.currentTime = 5.6")
    time.sleep(0.3)
    pg.ev("document.getElementById('ta').value = 'ULTIMA-DEL-INVITADO'")
    pg.ev("document.getElementById('ta').dispatchEvent(new Event('input'))")
    pg.click("#bSave")
    time.sleep(1.6)
    check("la nota nueva del invitado queda dentro de la caja",
          pg.ev("(()=>{const n=[...list.querySelectorAll('.item')].find(n=>n.textContent.includes('ULTIMA-DEL-INVITADO'));"
                "if(!n)return false;const a=n.getBoundingClientRect(),b=list.getBoundingClientRect();"
                "return a.top>=b.top-2&&a.bottom<=b.bottom+2})()") is True)
    check("el hilo del invitado permite scroll propio",
          pg.ev("getComputedStyle(list).overflowY==='auto' && document.documentElement.scrollHeight<=innerHeight+2") is True)
    check("invitado sin controles de pagina", pg.ev("!document.querySelector('#x2Prev,#x2Next,#x2Page')") is True)
    pg.shot("i03b-invitado-auditoria.png")

    # ── video por la puerta: 206 y reproduccion ──
    print("\n== video por la puerta ==")
    t0 = time.time()
    st, body, h = http("GET", GATE + "/media/%s/%s/media.mp4" % (SLUG, VID),
                       headers={"Cookie": "ofg=" + TOKEN, "Range": "bytes=0-65535"})
    ms = (time.time() - t0) * 1000
    TIEMPOS["Range 0-65535 por la puerta"] = "%.1f ms, %s" % (ms, h.get("Content-Range"))
    check("GET /media con Range -> 206 + Content-Range + Accept-Ranges",
          st == 206 and h.get("Content-Range", "").startswith("bytes 0-65535/")
          and h.get("Accept-Ranges") == "bytes" and len(body) == 65536, (st, h))
    st, _, h = http("GET", GATE + "/media/%s/%s/media.mp4" % (SLUG, VID),
                    headers={"Cookie": "ofg=" + TOKEN, "Range": "bytes=99999999-"})
    check("Range fuera de rango -> 416", st == 416, st)
    vinfo = esperar_js(pg, "(v.readyState >= 2 && v.duration > 0) ? "
                           "JSON.stringify({rs:v.readyState, d:v.duration, src:v.currentSrc}) : ''", 15)
    check("el <video> del invitado carga por /media de la puerta (readyState>=2)",
          bool(vinfo) and "/media/" in (vinfo or ""), vinfo)
    pg.ev("v.currentTime = 0; v.play()")
    time.sleep(1.2)
    avanzo = pg.ev("v.currentTime")
    check("el video reproduce de verdad (currentTime avanza)",
          isinstance(avanzo, (int, float)) and avanzo > 0.05, avanzo)
    pg.ev("v.pause()")

    check("logs/guest.log registra el id del enlace y NUNCA el token", (lambda: (
        lambda raw: EID in raw and TOKEN not in raw)(
            open(os.path.join(ROOT, "logs", "guest.log")).read()))())

    # ── 4. la app de Cristian ──
    print("\n== app de Cristian (server.py real) ==")
    cp = Page(url=ADMIN + "/", w=1600, h=1000)
    try:
        cp.send("Browser.grantPermissions", origin=ADMIN,
                permissions=["clipboardReadWrite", "clipboardSanitizedWrite"])
    except Exception:
        pass
    time.sleep(1.0)
    cp.ev("localStorage.setItem('openframe:last', JSON.stringify({slug:%s, vid:%s}))" % (json.dumps(SLUG), json.dumps(VID)))
    nav(cp, ADMIN + "/", 2.2)
    listo = esperar_js(cp, "(st && st.slug === %s && st.vid) ? st.vid : ''" % json.dumps(SLUG), 15)
    if not listo:
        cp.ev("openProject(%s)" % json.dumps(SLUG))
        time.sleep(1.2)
        cp.ev("openVideo(%s)" % json.dumps(VID))
        time.sleep(1.2)
    check("la app de Cristian abre el proyecto sin window.__INVITADO",
          cp.ev("!window.__INVITADO && st.slug === %s" % json.dumps(SLUG)), cp.ev("st && st.slug"))
    texto = esperar_js(cp, "document.getElementById('list').textContent.indexOf('Invitado · %s') >= 0 ? 'si' : ''"
                       % NOMBRE, 12)
    check("Cristian ve la insignia «Invitado · Nombre» en las notas del invitado", texto == "si",
          (cp.ev("document.getElementById('list').textContent") or "")[:300])
    check("las notas del invitado NO se confunden con las de Cristian (data-who distinto)",
          cp.ev("!!document.querySelector('.item[data-who=\"invitado\"]') && "
                "!!document.querySelector('.item[data-who=\"cristian\"]')"))
    cp.shot("i05-cristian-insignia.png")

    # ── popover Compartir contra los endpoints reales ──
    check("el boton Compartir existe y usa el icono lucide share-2",
          cp.ev("(()=>{const b=document.getElementById('bShare');"
                "return !!b && b.offsetParent !== null && "
                "b.innerHTML.indexOf('#i-share2') >= 0})()"),
          cp.ev("document.getElementById('bShare') && document.getElementById('bShare').innerHTML"))
    cp.click("#bShare")
    time.sleep(1.4)
    filas = cp.ev("document.querySelectorAll('#shList .shlink').length")
    check("el popover lista los 2 enlaces REALES del video", filas == 2, filas)
    linea = cp.ev("document.getElementById('shEstado').textContent")
    check("linea «Puerta cerrada · N activos» con el estado real de server.py",
          "Puerta cerrada" in (linea or "") and "2 activos" in (linea or ""), linea)
    check("cada fila trae estado activo, usos y nº de notas",
          cp.ev("(()=>{const r=document.querySelector('#shList .shlink');return r && "
                "r.textContent.indexOf('activo')>=0 && /\\d+ usos?/.test(r.textContent) && "
                "/\\d+ notas?/.test(r.textContent)})()"),
          cp.ev("document.querySelector('#shList .shlink') && document.querySelector('#shList .shlink').textContent"))
    cp.shot("i06-compartir-popover.png")

    cp.ev("document.getElementById('shDias').value='30'")
    cp.ev("document.getElementById('shEtq').value='Enlace de prueba E2E'")
    cp.click("#shCrear")
    time.sleep(1.8)
    ls = enlaces(ADMIN, SLUG, VID)
    nuevo = next((e for e in ls if e.get("etiqueta") == "Enlace de prueba E2E"), None)
    check("«Crear» del popover crea el enlace REAL (30 dias, etiqueta)",
          len(ls) == 3 and nuevo is not None, [e.get("etiqueta") for e in ls])
    check("el popover avisa de que la puerta NO quedo abierta (publicada=false)",
          "NO quedó abierta" in (cp.ev("document.getElementById('shNuevo').textContent") or ""),
          cp.ev("document.getElementById('shNuevo').textContent"))
    try:
        cp.send("Page.bringToFront")
        cp.send("Emulation.setFocusEmulationEnabled", enabled=True)
    except Exception:
        pass
    cp.ev("navigator.clipboard.writeText('vacio')", await_promise=True)
    fila = "#shList .shlink[data-eid='%s']" % nuevo["id"]
    cop = cp.ev("(()=>{const r=document.querySelector(%s); if(!r) return 'sin fila';"
                "const b=[...r.querySelectorAll('button')].find(x=>x.textContent==='Copiar');"
                "if(!b) return 'sin boton'; b.click(); return true})()" % json.dumps(fila))
    time.sleep(0.8)
    copiado = cp.ev("navigator.clipboard.readText()", await_promise=True)
    check("«Copiar» de la fila deja la URL publica del enlace en el portapapeles",
          isinstance(copiado, str) and copiado == nuevo.get("url"), (cop, copiado))
    check("«Copiar» avisa con un toast",
          "copiado" in (cp.ev("document.getElementById('toast').textContent") or "").lower(),
          cp.ev("document.getElementById('toast').textContent"))
    cp.shot("i07-compartir-creado.png")

    sel = "#shList .shlink[data-eid='%s'] button[data-rev]" % nuevo["id"]
    cp.click(sel)
    time.sleep(0.4)
    armado = cp.ev("(()=>{const b=document.querySelector(%s);return b && b.textContent})()" % json.dumps(sel))
    check("«Revocar» pide confirmacion en el propio boton (sin confirm())", armado == "¿Revocar?", armado)
    cp.click(sel)
    time.sleep(1.6)
    rev = next((e for e in enlaces(ADMIN, SLUG, VID) if e["id"] == nuevo["id"]), {})
    check("el segundo clic revoca de verdad (DELETE real)", rev.get("revocado") is True, rev)
    check("el enlace revocado aparece como muerto en la lista",
          cp.ev("(()=>{const r=document.querySelector(%s);return !!r && r.dataset.estado==='revocado'})()"
                % json.dumps("#shList .shlink[data-eid='%s']" % nuevo["id"])),
          cp.ev("document.getElementById('shList').textContent"))
    st, _, _ = http("GET", GATE + "/r/" + (nuevo.get("url") or "").rsplit("/", 1)[-1], seguir=False)
    check("el enlace revocado ya no entra por la puerta (404)", st == 404, st)
    cp.ev("shCerrar()")

    # ── Cristian responde y resuelve el hilo del invitado ──
    cp.ev("startReply(%s)" % json.dumps(n1["id"]))
    time.sleep(0.3)
    cp.ev("document.getElementById('ta').value='Subido. Mira la v2.'")
    cp.ev("document.getElementById('ta').dispatchEvent(new Event('input'))")
    cp.click("#bSave")
    time.sleep(1.4)
    reps = [n for n in notas_servidor(ADMIN, SLUG) if n.get("parent") == n1["id"]]
    check("Cristian responde al hilo del invitado",
          any(n.get("author") == "cristian" and "Mira la v2" in (n.get("text") or "") for n in reps),
          [(n.get("author"), n.get("text")) for n in reps])
    cp.ev("toggleRes(%s)" % json.dumps(n1["id"]))
    time.sleep(1.4)
    nr = nota_por_id(ADMIN, SLUG, n1["id"])
    check("Cristian resuelve el hilo del invitado", nr and nr.get("resolved") is True, nr)
    cp.shot("i08-cristian-respuesta-resuelto.png")

    # ── 5. latencia: nota del invitado -> app de Cristian por sondeo ──
    print("\n== latencia por sondeo ==")
    cp.ev("window.__lat = null; st.rev = st.rev")
    # Quien lee arriba conserva su posicion y seleccion al llegar una nota remota.
    cp.ev("renderList(); list.scrollTop=0")
    lectura_antes = cp.ev("({top:list.scrollTop,sel:st.selId})")
    cp.ev("document.getElementById('toast').textContent = ''")
    pg.ev("v.currentTime = 5.0")
    time.sleep(0.3)
    pg.ev("document.getElementById('ta').value = 'MEDIDA-LATENCIA'")
    pg.ev("document.getElementById('ta').dispatchEvent(new Event('input'))")
    t0 = time.time()
    pg.click("#bSave")
    visto = None
    fin = time.time() + 20
    while time.time() < fin:
        if cp.ev("document.getElementById('list').textContent.indexOf('MEDIDA-LATENCIA') >= 0"):
            visto = time.time() - t0
            break
        time.sleep(0.12)
    TIEMPOS["nota del invitado visible en la app de Cristian"] = ("%.2f s" % visto) if visto else "no llego en 20 s"
    check("la nota del invitado aparece sola en la app de Cristian (sondeo) en < 8 s",
          visto is not None and visto < 8, TIEMPOS["nota del invitado visible en la app de Cristian"])
    check("y llega con la insignia «Invitado · Nombre»",
          cp.ev("(()=>{const n=[...document.querySelectorAll('.item')].find(x=>x.textContent.indexOf('MEDIDA-LATENCIA')>=0);"
                "return !!n && n.dataset.who==='invitado' && n.textContent.indexOf('Invitado · %s')>=0})()" % NOMBRE))
    check("el sondeo conserva la lectura y seleccion de Cristian",
          cp.ev("({top:list.scrollTop,sel:st.selId})") == lectura_antes)
    check("Cristian recibe un aviso de que llego una nota de invitado",
          "Invitado" in (cp.ev("document.getElementById('toast').textContent") or ""),
          cp.ev("document.getElementById('toast').textContent"))
    check("el hilo permite scroll y la pagina sigue fija tras la llegada",
          cp.ev("getComputedStyle(list).overflowY==='auto' && document.documentElement.scrollHeight<=innerHeight+2") is True)
    cp.shot("i08b-llegada-hilo.png")

    # ── actividad para el aviso de Telegram ──
    st, d, _ = http("GET", ADMIN + "/api/invitados/actividad?desde=2000-01-01T00:00:00Z")
    act = (d or {}).get("notas", [])
    mias = [a for a in act if a.get("etiqueta") == "Marta (cliente)"]
    check("/api/invitados/actividad lista las notas del invitado con nombre, etiqueta, proyecto y version",
          st == 200 and len(mias) >= 4 and NOMBRE in {a.get("nombre") for a in mias}
          and all(a.get("proyecto") == "Cafe Lumen" and a.get("version") == "clip.mp4"
                  and a.get("slug") == SLUG and a.get("vid") == VID and a.get("timecode")
                  for a in mias), (st, len(mias), act[:1]))
    check("/api/invitados/actividad devuelve el nombre con HTML tal cual (lo escapa quien pinta)",
          any(a.get("nombre") == XSS for a in mias), {a.get("nombre") for a in mias})
    check("/api/invitados/actividad NUNCA trae notas de Cristian ni de Claude",
          all(a.get("nombre") for a in act) and not any("Cristian" in (a.get("text") or "") for a in act),
          [a.get("text") for a in act])

    # ── 6. caducidad a mitad de sesion ──
    print("\n== caducidad y revocacion a mitad de sesion ==")
    path = links_path(SLUG, VID)
    links = json.load(open(path))
    for l in links:
        if l["id"] == EID:
            l["expira"] = "2001-01-01T00:00:00+00:00"
    with open(path, "w") as f:
        json.dump(links, f)
    cad = esperar_js(pg, "document.body.classList.contains('inv-caducado')", 20)
    check("enlace caducado a mitad de sesion: la interfaz lo detecta por el 404 del sondeo", cad)
    check("aviso claro «Este enlace caducó» y escritura apagada",
          pg.ev("(()=>{const t=document.getElementById('invBanner').textContent;"
                "return t.indexOf('caducó')>=0 && document.getElementById('ta').disabled "
                "&& document.getElementById('bSave').disabled})()"),
          pg.ev("document.getElementById('invBanner').textContent"))
    pg.shot("i09-invitado-caducado.png")
    r = tp(pg, "POST", "/api/proyectos/%s/notas" % SLUG, {"frame": 1, "text": "tras caducar"})
    check("tras caducar, la puerta rechaza escribir (404)", r.get("s") == 404, r)
    check("ninguna nota «tras caducar» llego al servidor",
          not any("tras caducar" in (n.get("text") or "") for n in notas_servidor(ADMIN, SLUG)))

    # revocar: el 404 es IDENTICO al de un token inventado
    links = json.load(open(path))
    for l in links:
        if l["id"] == EID:
            l["expira"] = "2099-01-01T00:00:00+00:00"
            l["revocado"] = True
    with open(path, "w") as f:
        json.dump(links, f)
    time.sleep(2.4)
    st_rev, body_rev, _ = http("GET", GATE + "/r/" + TOKEN, seguir=False)
    st_inv, body_inv, _ = http("GET", GATE + "/r/" + ("z" * 43), seguir=False)
    pagina = (body_rev if isinstance(body_rev, bytes) else b"").decode("utf-8", "replace")
    check("enlace revocado: 404 con la pagina minima «Este enlace ya no está disponible»",
          st_rev == 404 and "ya no está disponible" in pagina, (st_rev, pagina[:160]))
    check("el 404 del revocado es IDENTICO al de un token inventado (sin pistas)",
          st_rev == st_inv and body_rev == body_inv, (st_rev, st_inv))
    nav(pg, GATE + "/r/" + TOKEN, 1.6)
    check("el navegador del invitado revocado ve la pagina de enlace no disponible",
          "ya no está disponible" in (pg.ev("document.body.textContent") or ""),
          pg.ev("document.body.textContent"))
    pg.shot("i10-enlace-revocado.png")
    st, _, _ = http("GET", GATE + "/api/notas/" + SLUG, headers={"Cookie": "ofg=" + TOKEN})
    check("la cookie vieja ya no sirve para leer notas (404)", st == 404, st)

    # ── 7. segundo invitado con ve_otras=true: SI ve las notas del primero ──
    print("\n== segundo invitado (ve_otras=true) ==")
    # un marcador de CAMBIO de Agente (fase 1 del porte): el invitado que ve «otras»
    # lo vera en la lista, pero sin una sola accion de decision
    st, d, _ = http("POST", ADMIN + "/api/proyectos/%s/notas" % SLUG,
                    {"video": VID, "frame": 55, "text": "Cambio aplicado por el Agente",
                     "author": "claude", "kind": "cambio", "resuelve": n1["id"]})
    N_CAMBIO = ((d or {}).get("nota") or {}).get("id")
    check("marcador de cambio de Agente creado para la auditoria", st == 201 and N_CAMBIO, (st, d))
    st, d, _ = http("POST", "%s/api/proyectos/%s/videos/%s/invitar" % (ADMIN, SLUG, VID),
                    {"dias": 3, "etiqueta": "Director (ve otras)", "ve_otras": True})
    TOKEN_VE, EID_VE = (d or {}).get("token"), (d or {}).get("id")
    check("enlace con ve_otras=true creado", st == 201 and (d or {}).get("ve_otras") is True, (st, d))
    nav(pg, GATE + "/r/" + TOKEN_VE, 2.2)
    inv2 = pg.ev("window.__INVITADO ? JSON.parse(JSON.stringify(window.__INVITADO)) : null")
    check("el segundo invitado entra con su propio enlace_id y ve_otras=true",
          isinstance(inv2, dict) and inv2.get("enlace_id") == EID_VE and inv2.get("ve_otras") is True, inv2)
    pg.ev("document.getElementById('invNombre').value = 'Director'")
    pg.click("#invDlgOk")
    time.sleep(1.0)
    texto2 = esperar_js(pg, "(()=>{const t=document.getElementById('list').textContent;"
                            "return (t.indexOf('Invitado · Marta Ríos')>=0 && t.indexOf('Invitado · Otro')>=0"
                            " && t.indexOf('Nota interna de Cristian')>=0) ? 'si' : ''})()", 12)
    check("ve_otras=true: ve las notas de los OTROS invitados y las de Cristian", texto2 == "si",
          (pg.ev("document.getElementById('list').textContent") or "")[:300])
    check("pero sigue sin ver nada del otro video ni de otro proyecto",
          not any(x in (pg.ev("document.getElementById('list').textContent") or "")
                  for x in ("Nota del OTRO video",)) and tp(pg, "GET", "/api/notas/" + SLUG2).get("s") == 404)
    check("no puede editar las notas de otro invitado aunque las vea",
          tp(pg, "PATCH", "/api/notas/%s/%s" % (SLUG, n1["id"]), {"text": "mio"}).get("s") == 404)
    # fase 1 del porte vista por un invitado con ve_otras=true
    pg.ev("st.x2Type='all'; st.x2Person='all'; renderList()")
    verCambio = esperar_js(pg, "document.getElementById('list').textContent.includes('Cambio aplicado por el Agente') ? 'si' : ''", 12)
    check("ve_otras=true: el invitado ve el cambio de Agente en la conversacion", verCambio == "si",
          pg.ev("x2Filtradas().length"))
    check("pero la tarjeta de cambio llega SIN botones de decision",
          pg.ev("JSON.stringify([...document.querySelectorAll("
                "'[data-approve],[data-adjust],[data-redecide],.approve-btn,.adjust-btn')].length)") == "0",
          pg.ev("document.getElementById('list').innerHTML.length"))
    check("el invitado no ve Resolver/Mover/Borrar/Comparar y solo edita entradas propias",
          pg.ev("(()=>{const prohibidos=list.querySelectorAll('.resolve-btn,.move-btn,.del-btn,.approve-btn,.adjust-btn,.redecide-btn,.compare-btn');"
                "const entradas=[...list.querySelectorAll('.item,.reply')];"
                "return prohibidos.length===0&&entradas.every(e=>{const id=e.dataset.id||e.dataset.rid,n=st.notas.find(x=>x.id===id);"
                "return !!e.querySelector('.edit-btn')===esMia(n)})})()"),
          pg.ev("JSON.stringify([...list.querySelectorAll('.item,.reply')].map(e=>[e.dataset.id||e.dataset.rid,!!e.querySelector('.edit-btn')]))"))
    pg.ev("x2Aprobar(%s); x2PedirAjuste(%s); true" % (json.dumps(N_CAMBIO), json.dumps(N_CAMBIO)))
    time.sleep(1.0)
    ncam = nota_por_id(ADMIN, SLUG, N_CAMBIO)
    check("ni llamando a x2Aprobar/x2PedirAjuste a mano se decide el cambio de Agente",
          ncam and not ncam.get("decision"), ncam)
    pg.ev("renderList()")
    check("el rotulo del hilo dice «Agente», nunca «Claude», tambien para el invitado",
          "Claude" not in (pg.ev("document.getElementById('list').textContent") or ""),
          pg.ev("document.getElementById('list').textContent"))
    pg.shot("i11-ve-otras.png")

    # ── 8. tope de escrituras: 60/min por enlace -> 429 ──
    r = evp(pg, """(async () => {
      let ult = 0, n429 = 0;
      for(let i = 0; i < 70; i++){
        const r = await __t('POST', '/api/invitado/nombre', {nombre: 'Director'});
        ult = r.s; if(r.s === 429) n429++;
      }
      return {ult: ult, n429: n429};
    })()""")
    check("pasado el tope de escrituras por minuto la puerta responde 429",
          r.get("n429", 0) > 0 and r.get("ult") == 429, r)

    # ── 9. la puerta NUNCA es el 8477 ──
    st, _, _ = http("GET", GATE + "/api/proyectos", headers={"Cookie": "ofg=" + TOKEN_OTRO})
    check("ni con un enlace vivo se puede listar proyectos por la puerta", st == 404, st)
    errs = errores_reales(pg) + errores_reales(cp)
    check("ninguna excepcion de JavaScript inesperada en toda la sesion", not errs, errs[:4])


if __name__ == "__main__":
    sys.exit(main())
