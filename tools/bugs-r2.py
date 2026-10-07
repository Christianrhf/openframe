#!/usr/bin/env python3
"""R2 · Caza de errores exploratoria del porte fusionado — una prueba por hallazgo (`docs/historial/rondas/BUGS-R2.md`).

Arranca sus propios procesos (nunca los de otro agente):
    server.py --puerto 9481
    guest.py  --puerto 9482 --api http://127.0.0.1:9481
    Chrome CDP en 9483 (tools/chrome.sh)

Uso:
    tools/chrome.sh start 9483
    OPENFRAME_NO_PUBLICAR=1 /tmp/o8/venv/bin/python3 tools/bugs-r2.py

Solo LEE el comportamiento del visor/servidor actuales: no los toca. Cada check
PASA si el hallazgo NO se reproduce y FALLA si se reproduce (así la suite debe
dar 0/4 — o menos — hoy, mientras los bugs sigan sin arreglar). Sin aleatoriedad:
mismos datos cada vez. No usa ~/visornotas ni datos reales.
"""
import http.client
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SERVER_PORT = 9481
GUEST_PORT = 9482
CDP_PORT = int(os.environ.get("CDP_PORT", "9483"))
SERVER = ("127.0.0.1", SERVER_PORT)
GUEST = ("127.0.0.1", GUEST_PORT)
API = "http://127.0.0.1:%d" % SERVER_PORT
PROCS = []
CHECKS = []
SLUG = "bugs-r2"


def check(hallazgo, severidad, ok, detalle=""):
    # ok=True  -> el hallazgo NO se reprodujo hoy (bien)
    # ok=False -> el hallazgo SE reprodujo (mal; esto es lo esperado hasta que se arregle)
    CHECKS.append((ok, hallazgo))
    marca = "✔ no se reproduce" if ok else "✘ SE REPRODUCE"
    print("[%s] %s — %s%s" % (severidad, hallazgo, marca, (" — " + str(detalle)) if detalle else ""))
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


def nota(slug, vid, frame, text, **extra):
    body = {"video": vid, "frame": frame, "text": text, "author": "cristian"}
    body.update(extra)
    st, d, raw = request(SERVER, "POST", "/api/proyectos/%s/notas" % slug, body)
    assert st == 201, (st, d, raw)
    return d["nota"]


def preparar():
    """Proyecto sintetico fijo con 2 videos (para poder Comparar)."""
    st, d, _ = request(SERVER, "POST", "/api/proyectos", {"nombre": "Prueba R2 bugs", "cliente": "QA"})
    assert st == 200, d
    slug = d["slug"]
    with open(os.path.join(ROOT, "clip.mp4"), "rb") as f:
        raw = f.read()
    st, d, _ = request(SERVER, "POST", "/api/proyectos/%s/videos" % slug, raw,
                       {"X-Filename": "v01.mp4", "Content-Type": "application/octet-stream"})
    assert st == 200, d
    v1 = d["video"]["id"]
    st, d, _ = request(SERVER, "POST", "/api/proyectos/%s/videos" % slug, raw,
                       {"X-Filename": "v02.mp4", "Content-Type": "application/octet-stream"})
    assert st == 200, d
    v2 = d["video"]["id"]
    return slug, v1, v2


DIBUJO = {"strokes": [{"tool": "pen", "color": "#ff4d4d", "size": 5,
                       "pts": [{"x": 0.2, "y": 0.2}, {"x": 0.6, "y": 0.5}]}]}


# ── R2-1 · tramo invertido (end_frame <= frame) deja el dibujo invisible para siempre ──
def r2_1_tramo_invertido(slug, vid, pg):
    n = nota(slug, vid, 10, "tramo valido con dibujo", end_frame=30, drawing=DIBUJO)
    nid = n["id"]
    # mover la nota MAS ALLA de su propio end_frame (lo que hace arrastrar el
    # marcador en la barra, o "Mover a otro momento"): el servidor lo acepta.
    st, d, _ = request(SERVER, "PATCH", "/api/notas/%s/%s" % (slug, nid), {"frame": 50})
    aceptado_roto = (st == 200 and d["nota"]["end_frame"] is not None
                     and d["nota"]["end_frame"] <= d["nota"]["frame"])
    # confirmar en el visor real: el dibujo no se ve en NINGUN fotograma (ni el
    # propio, ni el del viejo tramo, ni el 0): notaVisibleEnElFrameActual() nunca
    # lo devuelve porque f>=50 && f<=30 no se cumple jamas.
    visible_en_algun_frame = False
    for f in (0, 10, 20, 30, 50):
        pg.ev("seek(%d/fps)" % f)
        time.sleep(0.12)
        vis = pg.ev("(()=>{const n=notaVisibleEnElFrameActual();return n?n.id:null})()")
        if vis == nid:
            visible_en_algun_frame = True
    bug = aceptado_roto and not visible_en_algun_frame
    return check(
        "R2-1 tramo invertido (end_frame<=frame) tras mover la nota: dibujo invisible para siempre",
        "ALTA", not bug,
        {"patch_status": st, "end_frame": d["nota"].get("end_frame"), "frame": d["nota"].get("frame"),
         "visible_en_algun_frame": visible_en_algun_frame})


# ── R2-2 · frame fuera del video se acepta al CREAR la nota (aunque PATCH si lo limita) ──
def r2_2_frame_fuera_de_rango(slug, vid):
    st, d, _ = request(SERVER, "POST", "/api/proyectos/%s/notas" % slug,
                       {"video": vid, "frame": 999999, "text": "fuera de rango", "author": "cristian"})
    creado_fuera_de_rango = (st == 201 and d["nota"]["frame"] == 999999)
    # el video de prueba dura ~6s a ~21.5fps (unos 129 fotogramas reales).
    # PATCH SI limita contra la duracion real del video (ver server.py ~1430):
    if creado_fuera_de_rango:
        nid = d["nota"]["id"]
        st2, d2, _ = request(SERVER, "PATCH", "/api/notas/%s/%s" % (slug, nid), {"frame": 999999})
        patch_rechaza = (st2 == 400)
    else:
        patch_rechaza = None
    bug = creado_fuera_de_rango and patch_rechaza
    return check(
        "R2-2 POST crea una nota con fotograma fuera del video (PATCH si lo rechaza: asimetria)",
        "ALTA", not bug,
        {"post_status": st, "frame_guardado": d.get("nota", {}).get("frame"), "patch_rechaza": patch_rechaza})


# ── R2-3 · Comparar queda "vivo" tras archivar el unico proyecto abierto ──
def r2_3_comparar_tras_archivar(slug, v1, v2, pg):
    pg.reload()
    pg.ev("window.confirm = () => true")
    time.sleep(0.4)
    pg.ev("[...document.querySelectorAll('.pitem')].find(e=>e.textContent.includes('Prueba R2 bugs'))?.click()")
    time.sleep(0.6)
    pg.ev("openVideo(%s)" % json.dumps(v1), await_promise=True)
    time.sleep(0.3)
    entro = pg.ev("cmpEntrar()")
    time.sleep(0.4)
    pg.ev("archivarProyecto(%s, true)" % json.dumps(slug), await_promise=True)
    time.sleep(0.5)
    slug_tras = pg.ev("st.slug")
    cmp_on_tras = pg.ev("CMP.on")
    v2src_tras = pg.ev("document.getElementById('v2').getAttribute('src')")
    # desarchivar siempre, para dejar el proyecto limpio para el resto de la suite
    request(SERVER, "POST", "/api/proyectos/%s/archivar" % slug, {"archivado": False})
    bug = (entro is True) and (slug_tras is None) and (cmp_on_tras is True) and bool(v2src_tras)
    return check(
        "R2-3 Comparar sigue activo (CMP.on, #v2 con media vieja) tras archivar el unico proyecto abierto",
        "MEDIA", not bug,
        {"entro": entro, "slug_tras_archivar": slug_tras, "CMP.on": cmp_on_tras, "v2_src": v2src_tras})


# ── R2-4 · responder a un hilo cuya raiz se borra mientras se escribe: la respuesta
#          se envia en silencio como nota SUELTA, no como respuesta ──
def r2_4_respuesta_huerfana(slug, vid, pg):
    raiz = nota(slug, vid, 5, "raiz para responder R2-4")
    nid = raiz["id"]
    pg.reload()
    pg.ev("window.confirm = () => true")
    time.sleep(0.4)
    pg.ev("[...document.querySelectorAll('.pitem')].find(e=>e.textContent.includes('Prueba R2 bugs'))?.click()")
    time.sleep(0.6)
    pg.ev("openVideo(%s)" % json.dumps(vid), await_promise=True)
    time.sleep(0.3)
    pg.ev("startReply(%s)" % json.dumps(nid))
    reply_to_antes = pg.ev("st.replyTo")
    texto = "respuesta R2-4 mientras la raiz desaparece"
    pg.ev("const ta=document.getElementById('ta');ta.value=%s;"
          "ta.dispatchEvent(new Event('input',{bubbles:true}))" % json.dumps(texto))
    # concurrencia real: otra sesion (p.ej. el Agente via visor.sh borrar) borra la
    # raiz MIENTRAS el host sigue con el cuadro de respuesta abierto y sin enviar.
    st_del, _d, _ = request(SERVER, "DELETE", "/api/proyectos/%s/notas/%s" % (slug, nid))
    # un tick de sondeo (lo que pasa cada 2.2s sin que el host haga nada)
    pg.ev("pull(true)", await_promise=True)
    time.sleep(0.3)
    reply_to_despues = pg.ev("st.replyTo")
    ta_conserva_texto = pg.ev("document.getElementById('ta').value") == texto
    antes_de_enviar = pg.ev("st.notas.length")
    pg.ev("saveNote()", await_promise=True)
    time.sleep(0.4)
    creada = pg.ev("JSON.stringify(st.notas.find(n=>n.text===%s))" % json.dumps(texto))
    creada = json.loads(creada) if creada else None
    quedo_como_nota_suelta = bool(creada) and creada.get("parent") is None
    bug = (st_del == 200 and reply_to_antes == nid and reply_to_despues is None
           and ta_conserva_texto and quedo_como_nota_suelta)
    return check(
        "R2-4 respuesta a un hilo borrado entre tanto se envia SIN AVISO como nota suelta, no como respuesta",
        "MEDIA", not bug,
        {"delete_status": st_del, "replyTo_antes": reply_to_antes, "replyTo_despues": reply_to_despues,
         "ta_conserva_texto": ta_conserva_texto, "nota_creada": creada})


def main():
    from cdp import Page  # noqa: E402  (tools/cdp.py)
    start_servers()
    try:
        slug, v1, v2 = preparar()
        pg = Page("http://127.0.0.1:%d/" % SERVER_PORT, 1280, 800)
        try:
            r2_1_tramo_invertido(slug, v1, pg)
            r2_2_frame_fuera_de_rango(slug, v1)
            r2_3_comparar_tras_archivar(slug, v1, v2, pg)
            r2_4_respuesta_huerfana(slug, v1, pg)
            print("\npagina sin excepciones:", not pg.errors, pg.errors if pg.errors else "")
        finally:
            try:
                pg.ws.close()
            except Exception:
                pass
    finally:
        stop_servers()
    ok = sum(1 for o, _ in CHECKS if o)
    print("\n%d/%d sin reproducirse (de %d hallazgos probados)" % (ok, len(CHECKS), len(CHECKS)))
    # el script "falla" (exit 1) si TODOS los hallazgos siguen reproduciendose,
    # que es justo lo que se espera mientras nadie arregle visor.html/server.py.
    raise SystemExit(0 if ok == len(CHECKS) else 1)


if __name__ == "__main__":
    main()
