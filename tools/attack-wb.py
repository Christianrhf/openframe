#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Suite de caja BLANCA para la puerta de invitados (TASK-R).

No repite tools/attack-guest.py (159 checks) ni tools/test-guest.py (619):
solo prueba lo que salio de LEER guest.py/server.py. Arranca sus propios
server.py/guest.py en 127.0.0.1:9393/9394 con datos de usar y tirar,
monta un proyecto+video+enlace de invitado reales, ataca, y los para.

Mismo estilo PASS/FAIL que attack-guest.py: PASS = comportamiento seguro,
FAIL = el hallazgo es real HOY contra el codigo actual.
"""
from __future__ import print_function

import json
import os
import random
import shutil
import signal
import string
import subprocess
import sys
import time
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "http://127.0.0.1:9393"
GATE = "http://127.0.0.1:9394"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client(object):
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.cookies = {}
        self.opener = build_opener(NoRedirect)

    def _store(self, headers):
        try:
            vals = headers.get_all("Set-Cookie") or []
        except AttributeError:
            v = headers.get("Set-Cookie")
            vals = [v] if v else []
        for value in vals:
            c = SimpleCookie()
            try:
                c.load(value)
            except Exception:
                continue
            for key in c:
                self.cookies[key] = c[key].value

    def raw(self, method, path, body=None, headers=None, timeout=8):
        url = path if path.startswith("http") else self.base + path
        data = None
        hdrs = dict(headers or {})
        if body is not None:
            data = json.dumps(body).encode("utf-8") if isinstance(body, (dict, list)) else body
            hdrs.setdefault("Content-Type", "application/json")
        if self.cookies and "Cookie" not in hdrs:
            hdrs["Cookie"] = "; ".join("%s=%s" % kv for kv in sorted(self.cookies.items()))
        req = Request(url, data=data, headers=hdrs, method=method)
        try:
            resp = self.opener.open(req, timeout=timeout)
            raw = resp.read()
            self._store(resp.headers)
            return resp.getcode(), raw, dict(resp.headers.items())
        except HTTPError as e:
            raw = e.read()
            self._store(e.headers)
            return e.code, raw, dict(e.headers.items())
        except Exception as e:
            return 0, str(e).encode("utf-8"), {}

    def json(self, method, path, body=None, headers=None):
        status, raw, hdrs = self.raw(method, path, body=body, headers=headers)
        try:
            return status, json.loads(raw.decode("utf-8") or "{}"), hdrs
        except Exception:
            return status, {}, hdrs


RESULTS = {"pass": 0, "fail": 0}


def check(name, ok, detail=""):
    RESULTS["pass" if ok else "fail"] += 1
    print("%s %-78s %s" % ("PASS" if ok else "FAIL", name, detail))


def wait_up(url, tries=40):
    for _ in range(tries):
        try:
            Request(url + "/api/ping")
            c = Client(url)
            status, _, _ = c.raw("GET", "/api/ping")
            if status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def free_port(port):
    """Mata cualquier proceso que siga escuchando en el puerto (restos de una
    corrida anterior interrumpida): evita 'Address already in use' flaky."""
    try:
        out = subprocess.check_output(["lsof", "-ti", "tcp:%d" % port, "-sTCP:LISTEN"])
    except Exception:
        return
    for pid in out.decode().split():
        try:
            os.kill(int(pid), signal.SIGKILL)
        except OSError:
            pass
    time.sleep(0.3)


def main():
    free_port(9393)
    free_port(9394)
    data_dir = os.path.join(BASE, "data")
    logs_dir = os.path.join(BASE, "logs")
    shutil.rmtree(data_dir, ignore_errors=True)
    shutil.rmtree(logs_dir, ignore_errors=True)
    os.makedirs(logs_dir, exist_ok=True)

    env = dict(os.environ)
    env["OPENFRAME_NO_PUBLICAR"] = "1"
    server_log = open(os.path.join(logs_dir, "wb-server.out"), "wb")
    guest_log = open(os.path.join(logs_dir, "wb-guest.out"), "wb")
    server_proc = subprocess.Popen(
        [sys.executable, "server.py", "--puerto", "9393"],
        cwd=BASE, env=env, stdout=server_log, stderr=subprocess.STDOUT)
    guest_proc = subprocess.Popen(
        [sys.executable, "guest.py", "--puerto", "9394", "--api", API],
        cwd=BASE, env=env, stdout=guest_log, stderr=subprocess.STDOUT)
    try:
        if not wait_up(API) or not wait_up(GATE):
            print("ERROR: server.py/guest.py no arrancaron (ver logs/wb-*.out)", file=sys.stderr)
            return 2
        run_checks()
    finally:
        for p in (server_proc, guest_proc):
            try:
                p.send_signal(signal.SIGTERM)
                p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                    p.wait(timeout=5)
                except Exception:
                    pass
        server_log.close()
        guest_log.close()

    print("\n%d PASS / %d FAIL" % (RESULTS["pass"], RESULTS["fail"]))
    return 0 if RESULTS["fail"] == 0 else 1


def run_checks():
    admin = Client(API)
    run = "wb" + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    clip = os.path.join(BASE, "clip.mp4")
    with open(clip, "rb") as f:
        clip_bytes = f.read()

    status, proj, _ = admin.json("POST", "/api/proyectos", {"nombre": run, "cliente": "c"})
    slug = proj.get("slug")
    status, vdata, _ = admin.json("POST", "/api/proyectos/%s/videos" % slug, clip_bytes,
                                   headers={"X-Filename": "a.mp4"})
    vid = (vdata.get("video") or {}).get("id")
    check("setup: proyecto+video creados", bool(slug and vid), "slug=%r vid=%r" % (slug, vid))

    status, link, _ = admin.json(
        "POST", "/api/proyectos/%s/videos/%s/invitar" % (slug, vid),
        {"dias": 7, "etiqueta": "wb", "ve_otras": False})
    token = link.get("token")
    check("setup: enlace de invitado creado", status == 201 and bool(token), "status=%s" % status)

    # ── R1: frame/end_frame sin tope superior -> OverflowError filtrado ──
    gate = Client(GATE)
    s, _, _ = gate.raw("GET", "/r/" + token)
    s2, _, _ = gate.json("POST", "/api/invitado/nombre", {"nombre": "Invitado WB"})
    check("setup: sesion de invitado iniciada", s == 302 and s2 == 200,
          "redirect=%s nombre=%s" % (s, s2))

    huge = 10 ** 400
    status, body, _ = gate.json(
        "POST", "/api/proyectos/%s/notas" % slug,
        {"text": "nota con frame enorme", "frame": huge})
    text = json.dumps(body)
    leaks_internal = any(tok in text for tok in
                          ("OverflowError", "Traceback", "ValueError", "TypeError",
                           "ZeroDivisionError", ".py", "Error:"))
    check("R1 guest.py limita 'frame' a un rango razonable",
          status != 500 and not leaks_internal,
          "status=%s body=%s" % (status, text[:160]))

    status_admin, body_admin, _ = admin.json(
        "POST", "/api/proyectos/%s/notas" % slug,
        {"video": vid, "frame": huge, "fps": 24, "text": "x", "author": "cristian"})
    text_admin = json.dumps(body_admin)
    check("R1b server.py no revienta con frame gigante (causa raiz)",
          status_admin != 500,
          "status=%s body=%s" % (status_admin, text_admin[:160]))

    # ── nota real de invitado, para probar R2 ──
    status, note_resp, _ = gate.json(
        "POST", "/api/proyectos/%s/notas" % slug,
        {"text": "nota normal del invitado", "frame": 5})
    note_id = (note_resp.get("nota") or {}).get("id")
    check("setup: nota de invitado creada para probar PATCH", status == 201 and bool(note_id),
          "status=%s" % status)

    # ── R2 (decision de diseno): 8477 es de CONFIANZA y solo local; Cristian y el Agente lo usan sin
    #    cabecera de puerta (resolver, borrar, visto). El peligro real que R2 describe es que alguien lo
    #    exponga por error (p. ej. apuntar el tunel de Cloudflare a este puerto). Mitigacion: server.py
    #    rechaza con 404 toda peticion con cabeceras de proxy/tunel o con un Host que no sea local. ──
    if note_id:
        cf = {"Cf-Ray": "8a1b2c3d4e5f-MIA", "Cf-Connecting-Ip": "203.0.113.9"}
        status, patched, _ = admin.json("PATCH", "/api/notas/%s/%s" % (slug, note_id),
                                        {"resolved": True, "visto": True}, headers=cf)
        check("R2 8477 rechaza PATCH que llega con cabeceras de tunel (Cf-*)", status == 404,
              "status=%s" % status)
        status, _b, _ = admin.json("PATCH", "/api/notas/%s/%s" % (slug, note_id),
                                   {"resolved": True}, headers={"X-Forwarded-For": "203.0.113.9"})
        check("R2 8477 rechaza X-Forwarded-For", status == 404, "status=%s" % status)
        status, _b, _ = admin.json("PATCH", "/api/notas/%s/%s" % (slug, note_id),
                                   {"resolved": True}, headers={"Host": "openframe.inspiredink.space"})
        check("R2 8477 rechaza un Host que no es local (DNS rebinding / proxy)", status == 404,
              "status=%s" % status)
        status_del, _b, _ = admin.json("DELETE", "/api/notas/%s/%s" % (slug, note_id), headers=cf)
        check("R2b 8477 rechaza DELETE que llega con cabeceras de tunel", status_del == 404,
              "status=%s" % status_del)
        st_get, notes_now, _ = admin.json("GET", "/api/notas/%s" % slug)
        mine = [n for n in (notes_now.get("notas") or []) if n.get("id") == note_id]
        check("R2 la nota sigue intacta tras los intentos (sin resolver, sin borrar)",
              bool(mine) and not mine[0].get("resolved"), "status=%s presentes=%d" % (st_get, len(mine)))
        st_ok, _b, _ = admin.json("GET", "/api/ping")
        check("R2 el uso local normal sigue funcionando (sin cabeceras de proxy)", st_ok == 200,
              "status=%s" % st_ok)
        # el backstop NO puede romper la puerta: guest.py no reenvia cabeceras del cliente a 8477
        status, _b, _ = gate.json("POST", "/api/proyectos/%s/notas" % slug,
                                  {"text": "con Cf-Ray del cliente", "frame": 6}, headers=cf)
        check("R2 la puerta sigue funcionando con Cf-* del cliente (no los reenvia)",
              status == 201, "status=%s" % status)

if __name__ == "__main__":
    sys.exit(main())
