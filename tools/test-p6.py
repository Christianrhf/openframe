#!/usr/bin/env python3
"""Suite de la fase 6 (atajos, chuleta y accesibilidad). Sin aleatoriedad.

Tres partes, todas en primer plano:
  A) Estatica sobre visor.html y visor.sh (sin navegador).
  B) UI real del ANFITRION por CDP: atajos nuevos, chuleta, foco, ARIA, a11y medida.
  C) UI real del INVITADO por la puerta: la chuleta solo trae lo que aplica a su flujo.

Uso:  tools/chrome.sh start 9473
      CDP_PORT=9473 /tmp/o8/venv/bin/python tools/test-p6.py
Puertos: server 9471, guest 9472, Chrome 9473.
No toca ~/visornotas: crea su propio proyecto `Prueba P6`.
"""
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SERVER_PORT = 9471
GUEST_PORT = 9472
SERVER = ("127.0.0.1", SERVER_PORT)
GUEST = ("127.0.0.1", GUEST_PORT)
CDP_PORT = int(os.environ.get("CDP_PORT", "9473"))
API = "http://127.0.0.1:%d" % SERVER_PORT
PROCS = []
CHECKS = []


def check(label, value, detail=""):
    ok = bool(value)
    CHECKS.append((ok, label))
    print(("OK  " if ok else "FAIL") + "  " + label + ((" — " + str(detail)[:300]) if detail and not ok else ""))
    return ok


# ── utilidades HTTP ────────────────────────────────────────────
def request(target, method, path, body=None, headers=None, timeout=25):
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


def limpiar():
    base = os.path.join(ROOT, "data")
    if not os.path.isdir(base):
        return
    for name in sorted(os.listdir(base)):
        if name == "prueba-p6" or name.startswith("prueba-p6-"):
            shutil.rmtree(os.path.join(base, name), ignore_errors=True)


DIBUJO = {"strokes": [{"tool": "pen", "color": "#ff4d4d", "size": 5,
                       "pts": [{"x": 0.2, "y": 0.2}, {"x": 0.6, "y": 0.5}]}]}


def preparar():
    st, d, _ = request(SERVER, "POST", "/api/proyectos", {"nombre": "Prueba P6", "cliente": "QA"})
    slug = d["slug"]
    with open(os.path.join(ROOT, "clip.mp4"), "rb") as f:
        raw = f.read()
    st, d, _ = request(SERVER, "POST", "/api/proyectos/%s/videos" % slug, raw,
                       {"X-Filename": "p6.mp4", "Content-Type": "application/octet-stream"})
    vid = d["video"]["id"]

    def nota(frame, text, **ex):
        b = {"video": vid, "frame": frame, "text": text, "author": "cristian"}
        b.update(ex)
        s_, dd, _ = request(SERVER, "POST", "/api/proyectos/%s/notas" % slug, b)
        assert s_ == 201, (s_, dd)
        return dd["nota"]

    n1 = nota(10, "el logo entra tarde y se queda corto en pantalla")
    n2 = nota(40, "este plano se alarga demasiado", drawing=DIBUJO)
    n3 = nota(70, "falta el rotulo final")
    nota(12, "logo movido 3 fotogramas", author="claude", kind="cambio", resuelve=n1["id"])
    nota(42, "plano recortado", author="claude", kind="cambio", resuelve=n2["id"])
    nota(10, "gracias, lo veo", parent=n1["id"])
    return slug, vid, [n1, n2, n3]


def sh(*args):
    env = dict(os.environ)
    env["VISOR_API"] = API
    r = subprocess.run([os.path.join(ROOT, "visor.sh")] + list(args), cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr


# ── A · estatica ───────────────────────────────────────────────
COMANDOS = ["proyectos", "archivar", "nuevo", "subir", "estado", "vids", "notas", "nota",
            "responder", "cambio", "cambios-lista", "ajustes", "borrar-cambio", "resolver",
            "resolver-todas", "desmarcar", "borrar-nota", "invitar", "invitados", "revocar"]

# geometria LITERAL de lucide-react `keyboard` (__iconNode), no dibujada a mano
KEYBOARD_D = ["M10 8h.01", "M12 12h.01", "M14 8h.01", "M16 12h.01", "M18 8h.01",
              "M6 8h.01", "M7 16h10", "M8 12h.01"]


def parte_estatica():
    html = open(os.path.join(ROOT, "visor.html"), encoding="utf-8").read()
    css = html.split("<style>", 1)[1].split("</style>", 1)[0]

    sprite = html.split('<svg class="sprite"', 1)[1].split("</svg>", 1)[0]
    icono = re.search(r'<g id="i-keyboard">(.*?)</g>', sprite, re.S)
    check("el sprite trae el icono `keyboard` de Lucide", bool(icono))
    if icono:
        cuerpo = icono.group(1)
        check("la geometria del icono es la de lucide-react (__iconNode), sin retocar",
              all(('d="%s"' % d) in cuerpo for d in KEYBOARD_D) and
              'width="20" height="16" x="2" y="4" rx="2"' in cuerpo, cuerpo[:200])

    chicos = [m for m in re.findall(r"font-size:\s*([\d.]+)px", css) if float(m) < 11]
    check("ninguna regla de CSS deja texto por debajo de 11px", not chicos, chicos)
    glifo = re.findall(r"font:\s*\d+\s+(\d+(?:\.\d+)?)px", css)
    check("la unica letra menor de 11px es el glifo del grupo de marcadores (9px)",
          glifo == ["9"], glifo)

    check("hay un :focus-visible global de 2px (un solo trazo)",
          ":focus-visible{outline:2px solid var(--accent)" in css, "")
    check("los campos ya no apagan el foco con outline:none incondicional",
          "input,textarea,select{font:inherit;color:inherit;background:none;border:none}" in css and
          "input:not(:focus-visible),textarea:not(:focus-visible),select:not(:focus-visible){outline:none}" in css)
    check("prefers-reduced-motion apaga transiciones y animaciones",
          "@media (prefers-reduced-motion: reduce){\n    *,*::before,*::after{transition:none !important;animation:none !important" in css)
    # Réplica literal (R1): el gris de texto ya no se declara aquí, es el --muted de la
    # maqueta (mismo #6b6b6b, mismo 4.5:1) y --fg-mute es su alias. Se comprueban los dos.
    check("el gris de texto llega a 4.5:1 (--muted #6b6b6b, --fg-mute es su alias)",
          "--muted:#6b6b6b" in css and "--fg-mute:var(--muted)" in css)
    check("el toast se anuncia (aria-live polite)",
          '<div class="toast" id="toast" role="status" aria-live="polite"' in html)
    check("la chuleta es un dialogo con nombre accesible",
          'id="keysPop" role="dialog" aria-modal="true" aria-labelledby="keysPopT"' in html)
    check("el boton que abre la chuleta se explica en title/aria-label",
          'id="keysBtn"' in html and 'aria-label="Atajos de teclado"' in html and
          'title="Atajos de teclado  ?"' in html)
    check("el circulo ya no anuncia un atajo C que nunca tuvo",
          'data-tool="ellipse" data-key="C"' not in html)
    check("la tabla de atajos es UNA sola (P6_ATAJOS) y no hay segunda copia",
          html.count("const P6_ATAJOS") == 1)
    # cero `const` reasignados en el bloque nuevo
    js = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    nuevos = re.findall(r"\bconst (P6_\w+|p6\w+)\b", js)
    reasig = [n for n in set(nuevos) if re.search(r"^\s*%s\s*=" % re.escape(n), js, re.M)]
    check("ningun const nuevo se reasigna", not reasig, reasig)

    rc, out = sh("ayuda")
    check("visor.sh ayuda sale con codigo 0", rc == 0, rc)
    faltan = [c for c in COMANDOS if ("\n  " + c + " ") not in out and ("\n  " + c + "\n") not in out]
    check("visor.sh ayuda lista los %d comandos" % len(COMANDOS), not faltan, faltan)
    sin_ej = [c for c in COMANDOS if ("visor.sh " + c + " ") not in out and ("visor.sh " + c + "\n") not in out]
    check("cada comando de la ayuda trae un ejemplo", not sin_ej, sin_ej)
    check("la ayuda documenta los comandos nuevos (estado, notas enviadas, ajustes)",
          "estado <slug> <video-id> <nuevo>" in out and "notas <slug> [todas|pendientes|enviadas]" in out
          and "ajustes <slug>" in out)
    rc2, out2 = sh("--help")
    check("visor.sh --help y visor.sh ayuda dicen lo mismo", rc2 == 0 and out2 == out)


# ── B · la UI del anfitrion ────────────────────────────────────
def chrome_vivo():
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % CDP_PORT, timeout=3).read()
        return True
    except Exception:
        return False


def abrir(pg):
    pg.ev("[...document.querySelectorAll('.pitem')].find(e=>e.textContent.includes('Prueba P6'))?.click()")
    time.sleep(.8)
    pg.ev("(document.querySelector('.vitem')||{click(){}}).click()")
    time.sleep(1.2)


def parte_ui(slug, vid, notas):
    from cdp import Page
    pg = Page(API + "/", 1280, 800)
    abrir(pg)
    check("el proyecto de pruebas abre con video", pg.ev("!!st.vid"), pg.ev("st.vid"))

    # ── la chuleta ──
    pg.ev("ta.blur(); document.body.focus()")
    pg.key("?")
    time.sleep(.4)
    check("la tecla ? abre la chuleta", pg.ev("!keysPop.hidden"))
    check("la chuleta es role=dialog con aria-modal",
          pg.ev("keysPop.getAttribute('role')==='dialog' && keysPop.getAttribute('aria-modal')==='true'"))
    check("aria-expanded del boton pasa a true", pg.ev("keysBtn.getAttribute('aria-expanded')==='true'"))
    filas = pg.ev("document.querySelectorAll('#keysBody .keysFila').length")
    total = pg.ev("P6_ATAJOS.length")
    check("la chuleta pinta una fila por atajo (%s)" % filas, filas == total, (filas, total))
    check("la chuleta agrupa los atajos por bloque",
          pg.ev("[...document.querySelectorAll('#keysBody .keysGrupo > b')].map(e=>e.textContent).join('|')")
          == "Reproducción|Navegación|Notas|Dibujo|General")
    check("el foco entra en el dialogo al abrirlo", pg.ev("keysPop.contains(document.activeElement)"),
          pg.ev("document.activeElement.id"))
    pg.key("Tab"); time.sleep(.2)
    check("Tab no saca el foco del dialogo (foco atrapado)",
          pg.ev("keysPop.contains(document.activeElement)"), pg.ev("document.activeElement.id"))
    pg.key("Tab", shift=True); time.sleep(.2)
    check("Mayus+Tab tampoco saca el foco del dialogo",
          pg.ev("keysPop.contains(document.activeElement)"), pg.ev("document.activeElement.id"))
    pg.key("Escape"); time.sleep(.3)
    check("Esc cierra la chuleta", pg.ev("keysPop.hidden"))
    check("al cerrar, aria-expanded vuelve a false", pg.ev("keysBtn.getAttribute('aria-expanded')==='false'"))
    check("al cerrar, el foco vuelve a un control de la pagina",
          pg.ev("document.activeElement !== document.body && !keysPop.contains(document.activeElement)"),
          pg.ev("document.activeElement.id || document.activeElement.tagName"))
    pg.click("#keysBtn"); time.sleep(.3)
    check("el boton del teclado tambien la abre", pg.ev("!keysPop.hidden"))
    pg.click("#keysX"); time.sleep(.3)
    check("la X la cierra", pg.ev("keysPop.hidden"))
    check("la chuleta cabe sin scroll a 1280x800",
          pg.ev("(()=>{p6KeysAbrir();const r=keysPop.getBoundingClientRect();"
                "const ok=r.top>=0&&r.bottom<=innerHeight&&keysPop.scrollHeight<=keysPop.clientHeight+1;"
                "p6KeysCerrar();return ok})()"))

    # ── ningun atajo actua escribiendo ──
    pg.ev("ta.focus(); ta.value=''")
    pg.key("?"); time.sleep(.25)
    check("? NO abre la chuleta mientras se escribe", pg.ev("keysPop.hidden"))
    # `I` SIEMPRE avisa por el toast; si no aparece el aviso, el atajo no se ejecuto.
    # (el cuadro de texto mueve st.pend por su cuenta al escribir: eso no es el atajo)
    pg.ev("seek(frameT(33)); document.getElementById('toast').textContent=''; ta.focus(); ta.value=''")
    time.sleep(.5)
    pg.key("i"); pg.key("o"); pg.key("k"); time.sleep(.5)
    check("I/O/K no se ejecutan mientras se escribe (ningun aviso del atajo)",
          "Entrada del tramo" not in (pg.ev("document.getElementById('toast').textContent") or ""),
          pg.ev("document.getElementById('toast').textContent"))
    check("lo tecleado se queda en el cuadro, no se lo come el atajo",
          pg.ev("ta.value") == "iok", pg.ev("ta.value"))
    pg.ev("v.pause(); ta.value=''; setDirty(false); ta.blur(); document.body.focus()")

    # ── el video se pausa al enfocar el cuadro ──
    pg.ev("v.play()"); time.sleep(.6)
    check("el video estaba reproduciendose", pg.ev("!v.paused"))
    pg.ev("ta.focus()"); time.sleep(.4)
    check("enfocar el cuadro de texto PAUSA el video", pg.ev("v.paused"))
    pg.ev("ta.blur(); document.body.focus()")

    # ── J / K / L ──
    pg.ev("ta.blur(); seek(2.0); document.body.focus()"); time.sleep(.4)
    antes = pg.ev("v.currentTime")
    pg.key("j"); time.sleep(.5)
    check("J retrocede un segundo", abs(pg.ev("v.currentTime") - (antes - 1)) < .2,
          (antes, pg.ev("v.currentTime")))
    pg.key("l"); time.sleep(.6)
    check("L reproduce", pg.ev("!v.paused"))
    pg.key("k"); time.sleep(.4)
    check("K pausa", pg.ev("v.paused"))

    # ── [ y ] ──
    pg.ev("ta.blur(); document.body.focus(); seek(0)"); time.sleep(.4)
    pg.key("]"); time.sleep(.6)
    f1 = pg.ev("st.pend && st.pend.frame")
    pg.key("]"); time.sleep(.6)
    f2 = pg.ev("st.pend && st.pend.frame")
    check("] salta a la nota siguiente y luego a la de despues", f1 is not None and f2 is not None and f2 > f1,
          (f1, f2))
    pg.key("["); time.sleep(.6)
    check("[ vuelve a la nota anterior", pg.ev("st.pend && st.pend.frame") == f1,
          (f1, pg.ev("st.pend && st.pend.frame")))

    # ── I / O: entrada y salida del tramo ──
    pg.ev("ta.blur(); document.body.focus(); seek(frameT(30))"); time.sleep(.5)
    pg.key("i"); time.sleep(.5)
    check("I pone la entrada del tramo en el fotograma del cursor",
          pg.ev("st.pend && st.pend.frame") == 30, pg.ev("st.pend && st.pend.frame"))
    check("I suelta la nota seleccionada (la proxima nota nace aqui)", pg.ev("st.selId") is None,
          pg.ev("st.selId"))
    # O sobre una nota existente marca su salida
    nid = notas[0]["id"]
    # se selecciona pulsando su tarjeta (selectNoteById abre el dialogo de MOVER)
    pg.ev("(document.querySelector('.note.raiz[data-id=' + JSON.stringify(%s) + ']')||{click(){}}).click()"
          % json.dumps(nid))
    time.sleep(.8)
    check("la nota queda seleccionada al pulsar su tarjeta", pg.ev("st.selId") == nid, pg.ev("st.selId"))
    pg.ev("ta.blur(); document.body.focus(); seek(frameT(25))"); time.sleep(.6)
    pg.key("o"); time.sleep(1.4)
    n = next(x for x in request(SERVER, "GET", "/api/proyectos/" + slug)[1]["notas"] if x["id"] == nid)
    check("O marca la salida del tramo de la nota seleccionada (end_frame=25)",
          n.get("end_frame") == 25, n.get("end_frame"))
    pg.key("o"); time.sleep(1.4)
    n = next(x for x in request(SERVER, "GET", "/api/proyectos/" + slug)[1]["notas"] if x["id"] == nid)
    check("O otra vez en el mismo fotograma quita el tramo", n.get("end_frame") in (None,), n.get("end_frame"))

    # ── Ctrl/Cmd+Entrar ──
    pg.ev("seek(frameT(55)); ensurePend(); ta.focus(); ta.value='nota por Ctrl+Entrar dentro'; setDirty(true)")
    time.sleep(.4)
    pg.key("Enter", ctrl=True)
    time.sleep(1.8)
    notas_srv = request(SERVER, "GET", "/api/proyectos/" + slug)[1]["notas"]
    check("Ctrl+Entrar envia la nota desde dentro del cuadro",
          any(x["text"] == "nota por Ctrl+Entrar dentro" for x in notas_srv),
          [x["text"] for x in notas_srv][-3:])
    # con el foco FUERA del cuadro solo sobrevive el texto en modo respuesta/edicion
    # (updateEditor() vacia el cuadro si no se esta escribiendo: modo chat)
    pg.ev("startReply(%s); ta.value='respuesta por Ctrl+Entrar'; setDirty(true); bSave.focus()" % json.dumps(nid))
    time.sleep(.4)
    pg.key("Enter", ctrl=True)
    time.sleep(1.8)
    notas_srv = request(SERVER, "GET", "/api/proyectos/" + slug)[1]["notas"]
    check("Ctrl+Entrar tambien envia con el foco FUERA del cuadro (respondiendo)",
          any(x["text"] == "respuesta por Ctrl+Entrar" for x in notas_srv),
          [x["text"] for x in notas_srv][-3:])

    # ── no se piso ninguna tecla que ya tenia dueño ──
    check("las teclas nuevas no pisaron a las existentes (n, N, [, ], c, e, s siguen igual)",
          pg.ev("['n','N','[',']','c','e','s'].every(k=>typeof ATAJOS[k]==='function') && "
                "!Object.keys(P6_NUEVAS).some(k=>ATAJOS[k]!==P6_NUEVAS[k] && !['i','I','o','O','j','J','k','K','l','L'].includes(k))"))
    check("la chuleta documenta 22 atajos para el anfitrion", total == 22, total)

    # ── ARIA ──
    pg.click("[data-tool=rect]"); time.sleep(.3)
    check("aria-pressed sigue a la herramienta activa",
          pg.ev("document.querySelector('[data-tool=rect]').getAttribute('aria-pressed')==='true' && "
                "document.querySelector('[data-tool=pen]').getAttribute('aria-pressed')==='false'"))
    check("los puntos de grosor tienen nombre y estado",
          pg.ev("[...document.querySelectorAll('#ws button')].every(b=>b.getAttribute('aria-label')&&b.hasAttribute('aria-pressed'))"))
    check("las asas de las columnas declaran aria-expanded",
          pg.ev("bNavFold.hasAttribute('aria-expanded')"))

    # ── foco visible: UN solo trazo ──
    foco = pg.ev("(()=>{const b=document.getElementById('bPlay');b.focus();"
                 "const s=getComputedStyle(b);return JSON.stringify({w:s.outlineWidth,st:s.outlineStyle,bs:s.boxShadow})})()")
    f = json.loads(foco)
    check("el foco pinta un contorno de 2px", f["w"] == "2px" and f["st"] == "solid", f)
    check("y NO añade un segundo aro con box-shadow", f["bs"] in ("none", ""), f)

    # ── movimiento reducido ──
    pg.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
    time.sleep(.3)
    check("con prefers-reduced-motion no quedan transiciones",
          pg.ev("[...document.querySelectorAll('.btn,.note,.toast,.pitem')]"
                ".every(e=>getComputedStyle(e).transitionDuration.split(',').every(d=>parseFloat(d)===0))"))
    pg.send("Emulation.setEmulatedMedia", features=[])
    time.sleep(.2)

    # ── a11y medida en 3 tamaños ──
    from importlib.machinery import SourceFileLoader
    aud = SourceFileLoader("auditp6", os.path.join(ROOT, "tools", "audit-a11y.py")).load_module()
    for (w, h) in [(1280, 800), (1440, 900), (1600, 1000)]:
        pg.viewport(w, h)
        abrir(pg)
        time.sleep(.4)
        d = pg.ev(aud.AUDIT_JS)
        if not isinstance(d, dict):
            check("auditoria a11y a %dx%d" % (w, h), False, str(d)[:200])
            continue
        mal_c = [t for t in d["texts"] if t["cr"] < t["need"] - 0.005]
        mal_s = [t for t in d["texts"] if t["size"] < (9.0 if t["mk"] else 11.0) - 0.01]
        mal_h = [x for x in d["hits"] if not x["ok"]]
        check("a11y %dx%d: contraste AA en los %d textos" % (w, h, len(d["texts"])),
              not mal_c, [(x["sel"], x["cr"]) for x in mal_c][:6])
        check("a11y %dx%d: ningun texto por debajo de 11px" % (w, h), not mal_s,
              [(x["sel"], x["size"]) for x in mal_s][:6])
        check("a11y %dx%d: los %d controles llegan a 28px de agarre" % (w, h, len(d["hits"])),
              not mal_h, [(x["sel"], x["w"], x["h"]) for x in mal_h][:6])
        check("a11y %dx%d: todo control tiene nombre accesible" % (w, h), not d["unnamed"],
              [x["sel"] for x in d["unnamed"]][:6])
        check("sin scroll de pagina a %dx%d" % (w, h),
              pg.ev("(()=>{const d=document.documentElement;"
                    "return d.scrollWidth<=d.clientWidth && d.scrollHeight<=d.clientHeight})()"))
        check("hilo completo sin paginador a %dx%d" % (w, h),
              pg.ev("!document.querySelector('#x2Prev,#x2Next,#x2Page') && list.querySelectorAll('.note').length===x2Filtradas().length") is True)
        pg.ev("saltarANota(x2Filtradas().at(-1).id)")
        time.sleep(.7)
        check("atajo/seleccion lleva la tarjeta a la caja a %dx%d" % (w, h),
              pg.ev("(()=>{const a=list.querySelector('.note.on').getBoundingClientRect(),b=list.getBoundingClientRect();return a.top>=b.top-2&&a.bottom<=b.bottom+2})()") is True)
        check("la chuleta cabe sin scroll a %dx%d" % (w, h),
              pg.ev("(()=>{p6KeysAbrir();const r=keysPop.getBoundingClientRect();"
                    "const ok=r.top>=-0.5&&r.bottom<=innerHeight+0.5&&r.left>=-0.5&&r.right<=innerWidth+0.5;"
                    "p6KeysCerrar();return ok})()"))
    check("cero excepciones de pagina en el anfitrion", not pg.errors, pg.errors)
    return pg


# ── C · la UI del invitado ─────────────────────────────────────
def parte_invitado(slug, vid):
    from cdp import Page
    st, d, _ = request(SERVER, "POST", "/api/proyectos/%s/videos/%s/invitar" % (slug, vid),
                       {"dias": 7, "etiqueta": "QA P6", "ve_otras": True})
    if not check("enlace de invitado creado", st == 201 and d and d.get("token"), (st, d)):
        return
    token = d["token"]
    pg = Page("http://127.0.0.1:%d/r/%s" % (GUEST_PORT, token), 1280, 800)
    time.sleep(2.0)
    pg.ev("invNombre.value='Ana'; invNombre.dispatchEvent(new Event('input'))")
    pg.ev("[...document.querySelectorAll('#invDlg button')].find(b=>/entrar|aceptar|continuar|guardar|ok/i.test(b.textContent))?.click()")
    time.sleep(1.6)
    check("el visor arranca en modo invitado", pg.ev("document.body.classList.contains('invitado')"))
    check("el invitado conserva el boton de la chuleta",
          pg.ev("(()=>{const b=document.getElementById('keysBtn');return !!b&&getComputedStyle(b).display!=='none'})()"))
    # el invitado arranca con el cuadro de texto enfocado: ahi NINGUN atajo actua
    pg.ev("ta.blur(); document.body.focus()"); time.sleep(.2)
    check("el foco sale del cuadro de texto", pg.ev("document.activeElement.id") != "ta",
          pg.ev("document.activeElement.id"))
    pg.key("?")
    time.sleep(.4)
    check("? abre la chuleta tambien para el invitado", pg.ev("!keysPop.hidden"))
    filas = pg.ev("document.querySelectorAll('#keysBody .keysFila').length")
    check("la chuleta del invitado solo trae lo que aplica a su flujo (%s de 22)" % filas,
          filas == 21, filas)
    check("no le ofrece los cambios del Agente",
          "Cambio del Agente" not in (pg.ev("keysBody.textContent") or ""))
    pg.key("Escape"); time.sleep(.3)
    check("Esc cierra la chuleta del invitado", pg.ev("keysPop.hidden"))

    pg.ev("ta.blur(); document.body.focus(); seek(frameT(20))"); time.sleep(.5)
    pg.key("i"); time.sleep(.4)
    check("I del invitado pone la entrada del tramo", pg.ev("st.pend && st.pend.frame") == 20,
          pg.ev("st.pend && st.pend.frame"))
    pg.ev("ta.blur(); document.body.focus(); seek(frameT(45))"); time.sleep(.5)
    pg.key("o"); time.sleep(.5)
    tramo = pg.ev("JSON.stringify(st.invTramo)")
    check("O del invitado cierra el tramo sin tocar la puerta (viaja en el POST)",
          tramo and json.loads(tramo) == {"ini": 20, "fin": 45}, tramo)
    check("el invitado NO ve el cierre de ronda ni el estado del corte",
          pg.ev("(()=>{const r=document.getElementById('roundStatus');"
                "return !r||getComputedStyle(r).display==='none'})()"))
    check("cero excepciones de pagina en el invitado", not pg.errors, pg.errors)


def main():
    limpiar()
    start_servers()
    pg = None
    try:
        parte_estatica()
        slug, vid, notas = preparar()
        print("proyecto de pruebas: %s / %s" % (slug, vid))
        if chrome_vivo():
            pg = parte_ui(slug, vid, notas)
            parte_invitado(slug, vid)
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
