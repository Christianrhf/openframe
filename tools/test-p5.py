#!/usr/bin/env python3
"""Suite de la fase 5 (cierre de ronda y estado del corte). Sin aleatoriedad.

Dos mitades, ambas en primer plano:
  A) API + CLI + puerta de invitados (stdlib): server.py en 9451, guest.py en 9452.
  B) UI real por CDP: Chrome en CDP_PORT (9453 por defecto) contra el mismo server.

Uso:  tools/chrome.sh start 9453
      CDP_PORT=9453 /tmp/o8/venv/bin/python tools/test-p5.py
No toca ~/visornotas ni ningun proyecto real: crea su propio `Prueba P5`.
"""
import http.client
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SERVER_PORT = 9451
GUEST_PORT = 9452
SERVER = ("127.0.0.1", SERVER_PORT)
GUEST = ("127.0.0.1", GUEST_PORT)
CDP_PORT = int(os.environ.get("CDP_PORT", "9453"))
API = "http://127.0.0.1:%d" % SERVER_PORT
PROCS = []
CHECKS = []


def check(label, value, detail=""):
    ok = bool(value)
    CHECKS.append((ok, label))
    print(("✔ " if ok else "✘ ") + label + ((" — " + str(detail)) if detail and not ok else ""))
    return ok


def request(target, method, path, body=None, headers=None, timeout=20):
    headers = dict(headers or {})
    if isinstance(body, (dict, list)):
        body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    conn = http.client.HTTPConnection(target[0], target[1], timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = None
        return resp.status, data, raw
    finally:
        conn.close()


def ping(target):
    try:
        return request(target, "GET", "/api/ping", timeout=1)[0] == 200
    except Exception:
        return False


def wait_for(target, name):
    for _ in range(100):
        if ping(target):
            return
        time.sleep(0.1)
    raise RuntimeError("no arranco %s en %d" % (name, target[1]))


def start_servers():
    env = dict(os.environ)
    env["OPENFRAME_NO_PUBLICAR"] = "1"
    if not ping(SERVER):
        PROCS.append(subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "server.py"), "--puerto", str(SERVER_PORT)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        wait_for(SERVER, "server.py")
    if not ping(GUEST):
        PROCS.append(subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "guest.py"), "--puerto", str(GUEST_PORT),
             "--api", API], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        wait_for(GUEST, "guest.py")


def stop_servers():
    for proc in reversed(PROCS):
        proc.terminate()
    for proc in reversed(PROCS):
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()


def sh(*args):
    """visor.sh contra el server de pruebas. Devuelve (rc, salida+error)."""
    env = dict(os.environ)
    env["VISOR_API"] = API
    r = subprocess.run([os.path.join(ROOT, "visor.sh")] + list(args), cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr


def nota(slug, vid, frame, text, **extra):
    body = {"video": vid, "frame": frame, "text": text, "author": "cristian"}
    body.update(extra)
    st, d, _ = request(SERVER, "POST", "/api/proyectos/%s/notas" % slug, body)
    assert st == 201, (st, d)
    return d["nota"]


def proyecto(slug):
    return request(SERVER, "GET", "/api/proyectos/" + slug)[1]


def video_de(slug, vid):
    return next(v for v in proyecto(slug)["videos"] if v["id"] == vid)


DIBUJO = {"strokes": [{"tool": "pen", "color": "#ff4d4d", "size": 5,
                       "pts": [{"x": 0.2, "y": 0.2}, {"x": 0.6, "y": 0.5}]}]}


def preparar():
    """Proyecto sintetico fijo: 3 notas (1 con dibujo) + 2 cambios."""
    st, d, _ = request(SERVER, "POST", "/api/proyectos",
                       {"nombre": "Prueba P5", "cliente": "QA"})
    slug = d["slug"]
    with open(os.path.join(ROOT, "clip.mp4"), "rb") as f:
        raw = f.read()
    st, d, _ = request(SERVER, "POST", "/api/proyectos/%s/videos" % slug, raw,
                       {"X-Filename": "p5.mp4", "Content-Type": "application/octet-stream"})
    vid = d["video"]["id"]
    n1 = nota(slug, vid, 10, "el logo entra tarde")
    n2 = nota(slug, vid, 40, "este plano se alarga", drawing=DIBUJO)
    n3 = nota(slug, vid, 70, "falta el rotulo final")
    c1 = nota(slug, vid, 12, "logo movido 3 fotogramas", author="claude",
              kind="cambio", resuelve=n1["id"])
    c2 = nota(slug, vid, 42, "plano recortado", author="claude", kind="cambio",
              resuelve=n2["id"])
    return slug, vid, [n1, n2, n3], [c1, c2]


# ── A · API, CLI y puerta ──────────────────────────────────────
def parte_api(slug, vid, notas, cambios):
    v = video_de(slug, vid)
    meta_cru = json.load(open(os.path.join(ROOT, "data", slug, "videos", vid, "meta.json")))
    check("meta.json nace SIN campo revision", "revision" not in meta_cru, list(meta_cru))
    check("sin el campo, el estado derivado es revision",
          v.get("revision", {}).get("estado") == "revision", v.get("revision"))

    st, d, _ = request(SERVER, "PATCH", "/api/proyectos/%s/videos/%s" % (slug, vid),
                       {"estado": "con_agente"})
    check("PATCH del video pasa a con_agente",
          st == 200 and d["revision"]["estado"] == "con_agente", (st, d))
    check("el cambio de estado trae `desde`", bool(d["revision"].get("desde")), d)
    check("GET del proyecto expone con_agente",
          video_de(slug, vid)["revision"]["estado"] == "con_agente")
    lista = request(SERVER, "GET", "/api/proyectos")[1]
    p = next(x for x in lista["proyectos"] if x["slug"] == slug)
    check("la lista de proyectos expone el estado del corte actual",
          p.get("revision", {}).get("estado") == "con_agente", p.get("revision"))

    st, d, _ = request(SERVER, "PATCH", "/api/proyectos/%s/videos/%s" % (slug, vid),
                       {"estado": "listo-ya"})
    check("estado invalido -> 400", st == 400, (st, d))
    st, _d, _ = request(SERVER, "PATCH", "/api/proyectos/%s/videos/%s" % (slug, vid), {})
    check("PATCH del video sin estado -> 400", st == 400, st)
    st, _d, _ = request(SERVER, "PATCH", "/api/proyectos/%s/videos/v_00000000" % slug,
                        {"estado": "aprobado"})
    check("PATCH de un video que no existe -> 404", st == 404, st)
    request(SERVER, "PATCH", "/api/proyectos/%s/videos/%s" % (slug, vid), {"estado": "revision"})
    check("vuelve a revision", video_de(slug, vid)["revision"]["estado"] == "revision")

    # ── enviada_el ──
    cuando = "2026-10-03T12:00:00+00:00"
    st, d, _ = request(SERVER, "PATCH", "/api/notas/%s/%s" % (slug, notas[0]["id"]),
                       {"enviada_el": cuando})
    check("PATCH de nota acepta enviada_el",
          st == 200 and d["nota"].get("enviada_el") == cuando, (st, d))
    st, _d, _ = request(SERVER, "PATCH", "/api/notas/%s/%s" % (slug, notas[1]["id"]),
                        {"enviada_el": "ayer por la tarde"})
    check("enviada_el que no es fecha -> 400", st == 400, st)
    st, d, _ = request(SERVER, "PATCH", "/api/notas/%s/%s" % (slug, notas[0]["id"]),
                       {"enviada_el": None})
    check("enviada_el = null lo quita (asi deshace Ctrl+Z)",
          st == 200 and "enviada_el" not in d["nota"], (st, d))
    request(SERVER, "PATCH", "/api/notas/%s/%s" % (slug, notas[0]["id"]),
            {"enviada_el": cuando})
    env = [n for n in proyecto(slug)["notas"] if n.get("enviada_el")]
    check("solo 1 nota queda marcada como enviada", len(env) == 1, len(env))

    # ── CLI ──
    rc, out = sh("notas", slug, "enviadas")
    check("visor.sh notas <slug> enviadas lista solo la enviada",
          rc == 0 and notas[0]["id"] in out and notas[2]["id"] not in out, out)
    check("notas enviadas marca [enviada ...]", "[enviada" in out, out)
    rc, out = sh("notas", slug, "todas")
    check("visor.sh notas muestra el estado del corte", "corte: revision" in out, out)
    rc, out = sh("notas", slug, "inventado")
    check("modo de notas invalido -> error", rc != 0 and "modo invalido" in out, (rc, out))
    rc, out = sh("estado", slug, vid)
    check("visor.sh estado <slug> <video> lee el estado",
          rc == 0 and "estado: revision" in out, out)
    rc, out = sh("estado", slug, vid, "con_agente")
    check("visor.sh estado <slug> <video> con_agente lo cambia",
          rc == 0 and "con_agente" in out and
          video_de(slug, vid)["revision"]["estado"] == "con_agente", out)
    rc, out = sh("estado", slug, vid, "mandado")
    check("visor.sh estado con un estado invalido -> error",
          rc != 0 and "estado invalido" in out, (rc, out))
    rc, out = sh("estado", slug)
    check("visor.sh estado <slug> sigue siendo el resumen del proyecto",
          rc == 0 and "PROYECTO:" in out and "corte: con_agente" in out, out)

    # los comandos del Agente NO cambian el estado por si solos
    rc, _out = sh("cambio", slug, vid, "60", "rotulo final anadido")
    check("visor.sh cambio no cambia el estado del corte",
          rc == 0 and video_de(slug, vid)["revision"]["estado"] == "con_agente")
    rc, _out = sh("responder", slug, notas[2]["id"], "hecho")
    check("visor.sh responder no cambia el estado del corte",
          rc == 0 and video_de(slug, vid)["revision"]["estado"] == "con_agente")
    rc, _out = sh("resolver", slug, notas[2]["id"])
    check("visor.sh resolver no cambia el estado del corte",
          rc == 0 and video_de(slug, vid)["revision"]["estado"] == "con_agente")
    request(SERVER, "PATCH", "/api/proyectos/%s/videos/%s" % (slug, vid), {"estado": "revision"})
    request(SERVER, "PATCH", "/api/notas/%s/%s" % (slug, notas[2]["id"]), {"resolved": False})
    request(SERVER, "PATCH", "/api/notas/%s/%s" % (slug, notas[0]["id"]), {"enviada_el": None})
    return cambios


# ── A2 · la puerta de invitados ────────────────────────────────
def parte_invitado(slug, vid):
    st, d, _ = request(SERVER, "POST", "/api/proyectos/%s/videos/%s/invitar" % (slug, vid),
                       {"dias": 7, "etiqueta": "QA P5", "ve_otras": True})
    if not check("enlace de invitado creado", st == 201 and d and d.get("token"), (st, d)):
        return
    token = d["token"]
    cookie = None
    conn = http.client.HTTPConnection(GUEST[0], GUEST[1], timeout=10)
    try:
        conn.request("GET", "/r/" + token)
        resp = conn.getresponse()
        resp.read()
        sc = resp.getheader("Set-Cookie") or ""
        cookie = sc.split(";", 1)[0] if sc.startswith("ofg=") else None
    finally:
        conn.close()
    if not check("cookie de sesion de invitado", bool(cookie), cookie):
        return
    hdr = {"Cookie": cookie}
    st, d, _ = request(GUEST, "GET", "/api/proyectos/" + slug, None, hdr)
    check("el invitado lee su proyecto por la puerta", st == 200 and d, st)
    vids = (d or {}).get("videos", [])
    check("la puerta NO deja salir el estado del corte",
          bool(vids) and all("revision" not in v for v in vids), vids)
    check("la puerta NO deja salir enviada_el",
          all("enviada_el" not in n for n in (d or {}).get("notas", [])),
          [n.get("id") for n in (d or {}).get("notas", []) if n.get("enviada_el")])
    st, _d, _ = request(GUEST, "PATCH", "/api/proyectos/%s/videos/%s" % (slug, vid),
                        {"estado": "aprobado"}, hdr)
    check("PATCH del estado por la puerta -> 404", st == 404, st)
    st, _d, _ = request(GUEST, "PATCH", "/api/notas/%s/%s" % (slug, "n_00000000"),
                        {"enviada_el": "2026-10-03T12:00:00+00:00"}, hdr)
    check("PATCH de enviada_el por la puerta -> 404", st == 404, st)
    html = request(GUEST, "GET", "/", None, hdr)[2].decode("utf-8", "replace")
    check("el HTML del invitado no trae el estado del corte",
          '"revision"' not in html.split("<script>", 2)[1][:4000], "config con revision")


# ── B · la UI real por CDP ─────────────────────────────────────
def chrome_vivo():
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % CDP_PORT, timeout=3).read()
        return True
    except Exception:
        return False


def abrir(pg):
    pg.ev("[...document.querySelectorAll('.pitem')].find(e=>e.textContent.includes('Prueba P5'))?.click()")
    time.sleep(.6)


def parte_ui(slug, vid, notas):
    from cdp import Page
    pg = Page("http://127.0.0.1:%d/" % SERVER_PORT, 1280, 800)
    abrir(pg)
    check("tarjeta del proyecto con el estado por texto+forma",
          pg.ev("(()=>{const e=[...document.querySelectorAll('.pitem')]"
                ".find(e=>e.textContent.includes('Prueba P5'))?.querySelector('.pest');"
                "return !!e && e.textContent.includes('En revisi') && !!e.querySelector('use')})()"))
    check("la cabecera de Notas muestra los pendientes",
          "pendiente" in (pg.ev("roundTxt.textContent") or ""), pg.ev("roundTxt.textContent"))
    pg.click("#roundStatus")
    time.sleep(.2)
    res = pg.ev("JSON.stringify({ab:!p5Pop.hidden,nuevas:p5Nuevas.textContent,"
                "dib:p5Dibujo.textContent,sin:p5SinRev.textContent,ap:p5Aprob.textContent,"
                "aj:p5Ajuste.textContent,send:p5Send.disabled,appr:p5Approve.disabled})")
    r = json.loads(res)
    check("el popover de ronda se abre", r["ab"], r)
    check("resumen: 3 notas nuevas, 1 con dibujo",
          r["nuevas"] == "3" and r["dib"] == "1", r)
    check("resumen: 3 cambios sin revisar, 0 aprobados, 0 con ajuste",
          r["sin"] == "3" and r["ap"] == "0" and r["aj"] == "0", r)
    check("«Aprobar corte» desactivado con pendientes", r["appr"] is True, r)
    check("«Enviar al Agente» activo con notas nuevas", r["send"] is False, r)

    pg.click("#p5Send")
    time.sleep(1.4)
    env = [n for n in proyecto(slug)["notas"] if n.get("enviada_el")]
    check("«Enviar al Agente» marca enviada_el en las 3 notas pendientes",
          len(env) == 3, [n["id"] for n in env])
    check("el corte pasa a con_agente en el servidor",
          video_de(slug, vid)["revision"]["estado"] == "con_agente")
    check("la cabecera dice «Con el Agente»",
          pg.ev("roundTxt.textContent") == "Con el Agente", pg.ev("roundTxt.textContent"))
    check("las notas enviadas llevan insignia",
          pg.ev("document.querySelectorAll('.sent-badge').length") >= 1,
          pg.ev("document.querySelectorAll('.sent-badge').length"))

    pg.key("z", ctrl=True)
    time.sleep(1.6)
    check("Ctrl+Z deshace el envio: ninguna nota queda enviada",
          len([n for n in proyecto(slug)["notas"] if n.get("enviada_el")]) == 0,
          [n["id"] for n in proyecto(slug)["notas"] if n.get("enviada_el")])
    check("Ctrl+Z devuelve el corte a revision",
          video_de(slug, vid)["revision"]["estado"] == "revision")
    pg.key("z", ctrl=True, shift=True)
    time.sleep(1.6)
    check("Ctrl+Mayus+Z repone el envio y el estado",
          len([n for n in proyecto(slug)["notas"] if n.get("enviada_el")]) == 3 and
          video_de(slug, vid)["revision"]["estado"] == "con_agente")

    # «Con el Agente» no se mueve solo aunque no queden pendientes ni cambios abiertos
    for n in notas:
        request(SERVER, "PATCH", "/api/notas/%s/%s" % (slug, n["id"]), {"resolved": True})
    for c in [x for x in proyecto(slug)["notas"] if x.get("kind") == "cambio"]:
        request(SERVER, "PATCH", "/api/notas/%s/%s" % (slug, c["id"]), {"decision": "approved"})
    time.sleep(3.0)
    check("sin pendientes el corte SIGUE «Con el Agente» hasta aprobar",
          video_de(slug, vid)["revision"]["estado"] == "con_agente" and
          pg.ev("roundTxt.textContent") == "Con el Agente", pg.ev("roundTxt.textContent"))
    pg.click("#roundStatus")
    time.sleep(.3)
    check("ahora «Aprobar corte» esta activo", pg.ev("p5Approve.disabled") is False)
    pg.click("#p5Approve")
    time.sleep(1.4)
    check("«Aprobar corte» pasa el corte a aprobado",
          video_de(slug, vid)["revision"]["estado"] == "aprobado")
    check("la cabecera dice «Corte aprobado»",
          pg.ev("roundTxt.textContent") == "Corte aprobado", pg.ev("roundTxt.textContent"))
    pg.key("z", ctrl=True)
    time.sleep(1.6)
    check("Ctrl+Z deshace la aprobacion",
          video_de(slug, vid)["revision"]["estado"] == "con_agente")

    # un ajuste abierto bloquea la aprobacion
    c1 = [x for x in proyecto(slug)["notas"] if x.get("kind") == "cambio"][0]
    request(SERVER, "PATCH", "/api/notas/%s/%s" % (slug, c1["id"]), {"decision": "adjust"})
    time.sleep(3.0)
    pg.ev("p5PopAbierto||roundStatus.click()")
    time.sleep(.3)
    check("con un ajuste abierto «Aprobar corte» se desactiva",
          pg.ev("p5Approve.disabled") is True and pg.ev("p5Ajuste.textContent") == "1",
          pg.ev("p5Ajuste.textContent"))
    pg.key("Escape")
    time.sleep(.2)
    check("Escape cierra el popover de ronda", pg.ev("p5Pop.hidden") is True)

    for w, h in ((1280, 800), (1440, 900), (1600, 1000)):
        pg.viewport(w, h, clear_storage=False)
        abrir(pg)
        # Réplica literal (R1): la barra de proyectos arranca PLEGADA (clientWidth 0), así que
        # medir su scroll plegada no dice nada. Se despliega para comprobar lo que el check
        # busca de verdad: que nada desborde a lo ancho.
        pg.ev("plegarNav(false)")
        time.sleep(.4)
        m = json.loads(pg.ev(
            "JSON.stringify({page:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],"
            "view:[innerWidth,innerHeight],"
            "side:[document.querySelector('.sidebar').clientWidth,document.querySelector('.sidebar').scrollWidth],"
            "head:[document.querySelector('.side-head').clientWidth,document.querySelector('.side-head').scrollWidth],"
            "rail:[document.querySelector('.rail').clientWidth,document.querySelector('.rail').scrollWidth],"
            "round:roundStatus.getBoundingClientRect().height})"))
        check("sin scroll con el estado del corte %dx%d" % (w, h),
              m["page"] == m["view"] and m["side"][0] == m["side"][1] and
              m["head"][0] == m["head"][1] and m["rail"][0] == m["rail"][1], m)
        pg.click("#roundStatus")
        time.sleep(.25)
        b = json.loads(pg.ev("JSON.stringify((()=>{const r=p5Pop.getBoundingClientRect();"
                             "return {x:r.left,y:r.top,r:r.right,b:r.bottom,w:innerWidth,h:innerHeight}})())"))
        check("el popover cabe en pantalla %dx%d" % (w, h),
              b["x"] >= 0 and b["y"] >= 0 and b["r"] <= b["w"] and b["b"] <= b["h"], b)
        pg.shot("p5-%dx%d.png" % (w, h))
        pg.key("Escape")
    check("cero excepciones de pagina", not pg.errors, pg.errors)


def limpiar():
    """Borra SOLO los proyectos de esta suite (data/prueba-p5*). Nada mas."""
    base = os.path.join(ROOT, "data")
    if not os.path.isdir(base):
        return
    import shutil
    for name in sorted(os.listdir(base)):
        if name == "prueba-p5" or name.startswith("prueba-p5-"):
            shutil.rmtree(os.path.join(base, name), ignore_errors=True)


def main():
    limpiar()
    start_servers()
    try:
        slug, vid, notas, cambios = preparar()
        print("proyecto de pruebas: %s / %s" % (slug, vid))
        parte_api(slug, vid, notas, cambios)
        parte_invitado(slug, vid)
        if chrome_vivo():
            parte_ui(slug, vid, notas)
        else:
            check("Chrome CDP en %d disponible" % CDP_PORT, False,
                  "arranca tools/chrome.sh start %d" % CDP_PORT)
    finally:
        stop_servers()
    ok = sum(1 for c, _ in CHECKS if c)
    print("\n%d/%d checks" % (ok, len(CHECKS)))
    for c, label in CHECKS:
        if not c:
            print("  FALLA: " + label)
    raise SystemExit(0 if ok == len(CHECKS) else 1)


if __name__ == "__main__":
    main()
