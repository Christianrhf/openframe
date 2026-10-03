#!/usr/bin/env python3
"""Servidor de PRUEBA para la interfaz de invitados (tarea U). NO es la puerta real.

Simula, delante de un server.py local (--api), dos cosas que hace S:
  * la puerta de invitados `guest.py`      -> puerto --invitado (por defecto 9384)
  * los endpoints de administración          -> puerto --admin    (por defecto 9385)
    (/invitar, /api/invitados/estado) sobre un proxy transparente al server.py

Y añade mandos de prueba bajo /__mock/* (solo aquí, jamás en producción):
  POST /__mock/config  {"slug","video","nombre","ve_otras","caducado","expira","sin_endpoints","publicada"}
  POST /__mock/enlaces [ ...lista de enlaces tal cual los devolvería GET /invitar... ]
  GET  /__mock/estado

Uso:  python3 tools/mock-inv.py --api 9383 --invitado 9384 --admin 9385 --slug zz-port --video v_xxx
Solo stdlib (Python 3.9+).
"""
import argparse
import json
import re
import secrets
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
STATE = {
    "api": "http://127.0.0.1:9383",
    "slug": None, "video": None,
    "nombre": None,            # cookie ofn simulada
    "enlace_id": "ab12cd34",   # el enlace del invitado que mira la página
    "ve_otras": False,
    "caducado": False,         # True -> la puerta responde 404 a todo
    "expira": None,            # ISO; None -> ahora + 7 días
    "sin_endpoints": False,    # True -> /invitar y /estado devuelven 404 (server.py viejo)
    "publicada": True,         # lo que devuelve publicar.sh (simulado)
    "enlaces": [],             # lista administrada (GET /invitar)
}
JSON = "application/json"
NOMBRE_MAX = 40
ETQ_MAX = 60
CUERPO_MAX = 1024 * 1024


def ahora():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def expira_por_defecto():
    return STATE["expira"] or iso(ahora() + timedelta(days=7))


def upstream(method, path, body=None, headers=None):
    """Llama al server.py real. Devuelve (status, headers_dict, bytes)."""
    req = urllib.request.Request(STATE["api"] + path, data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def upstream_json(method, path, obj=None):
    body = json.dumps(obj).encode("utf-8") if obj is not None else None
    st, hd, raw = upstream(method, path, body, {"Content-Type": JSON} if body else None)
    try:
        return st, json.loads(raw.decode("utf-8") or "null")
    except Exception:
        return st, None


def notas_upstream(slug):
    st, d = upstream_json("GET", "/api/notas/%s" % slug)
    return (d or {}).get("notas", []) if st == 200 else []


class Base(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body=b"", ctype=JSON, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > CUERPO_MAX:
            self._send(413, b"")
            return None
        return self.rfile.read(n) if n else b""

    def _jbody(self):
        raw = self._body()
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    def _404(self):
        # idéntico para todo lo desconocido: sin eco de la ruta
        self._send(404, "<!doctype html><title>No disponible</title><p>Este enlace ya no está disponible.",
                   "text/html; charset=utf-8")

    # ── mandos de prueba (compartidos por los dos puertos) ──
    def _mock(self):
        p = self.path.split("?")[0]
        if p == "/__mock/estado" and self.command == "GET":
            with LOCK:
                self._json({k: v for k, v in STATE.items()})
            return True
        if p == "/__mock/config" and self.command == "POST":
            d = self._jbody() or {}
            with LOCK:
                for k in ("slug", "video", "nombre", "ve_otras", "caducado", "expira",
                          "sin_endpoints", "publicada", "enlace_id"):
                    if k in d:
                        STATE[k] = d[k]
            self._json({"ok": True})
            return True
        if p == "/__mock/enlaces" and self.command == "POST":
            d = self._jbody()
            with LOCK:
                STATE["enlaces"] = d if isinstance(d, list) else []
            self._json({"ok": True, "n": len(STATE["enlaces"])})
            return True
        return False


# ═══════════════════════════ PUERTA DE INVITADOS (simula guest.py) ═══════════════════════════
class Invitado(Base):
    def _visible(self, n, todas):
        if n.get("video") != STATE["video"]:
            return False
        if STATE["ve_otras"]:
            return True
        mio = STATE["enlace_id"]
        if n.get("enlace_id") == mio:
            return True
        if n.get("parent"):
            padre = next((x for x in todas if x.get("id") == n["parent"]), None)
            return bool(padre and padre.get("enlace_id") == mio)
        return False

    def _filtrar(self, notas):
        return [n for n in notas if self._visible(n, notas)]

    def _muerta(self):
        if STATE["caducado"]:
            return True
        try:
            t = datetime.strptime(expira_por_defecto(), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            return t <= ahora()
        except Exception:
            return False

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if self._mock():
            return
        p = self.path.split("?")[0]
        if p == "/":
            return self._index()
        if self._muerta():
            return self._404()
        if p == "/api/ping":
            return self._json({"ok": True})
        slug, vid = STATE["slug"], STATE["video"]
        m = re.match(r"^/api/proyectos/([\w.-]+)$", p)
        if m and m.group(1) == slug:
            st, d = upstream_json("GET", p)
            if st != 200 or not d:
                return self._404()
            d["videos"] = [x for x in d.get("videos", []) if x.get("id") == vid]
            d["notas"] = self._filtrar(d.get("notas", []))
            return self._json(d)
        m = re.match(r"^/api/notas/([\w.-]+)$", p)
        if m and m.group(1) == slug:
            st, d = upstream_json("GET", p)
            if st != 200 or not d:
                return self._404()
            d["notas"] = self._filtrar(d.get("notas", []))
            return self._json(d)
        m = re.match(r"^/media/([\w.-]+)/([\w.-]+)/([\w.-]+)$", p)
        if m and m.group(1) == slug and m.group(2) == vid:
            hd = {}
            if self.headers.get("Range"):
                hd["Range"] = self.headers["Range"]
            st, h2, raw = upstream("GET", p, None, hd)
            extra = {k: v for k, v in h2.items() if k.lower() in ("content-range", "accept-ranges")}
            return self._send(st, raw, h2.get("Content-Type", "video/mp4"), extra)
        m = re.match(r"^/thumbs/([\w.-]+)/([\w.-]+\.jpg)$", p)
        if m and m.group(1) == slug:
            nid = m.group(2)[:-4]
            todas = notas_upstream(slug)
            n = next((x for x in todas if x.get("id") == nid), None)
            if not n or not self._visible(n, todas):
                return self._404()
            st, h2, raw = upstream("GET", p)
            return self._send(st, raw, "image/jpeg")
        return self._404()

    def _index(self):
        st, h2, raw = upstream("GET", "/")
        if st != 200:
            return self._404()
        html = raw.decode("utf-8", "replace")
        inv = {
            "slug": STATE["slug"], "video": STATE["video"],
            "nombre": STATE["nombre"], "expira": expira_por_defecto(),
            "ve_otras": bool(STATE["ve_otras"]),
            "enlace_id": STATE["enlace_id"],
            "proyecto": {"nombre": "zz-port", "cliente": "Cliente Demo"},
            "version": {"nombre": "clip.mp4", "fps": 21.533, "duracion": 6.0, "ancho": 0, "alto": 0},
        }
        # detalle real del proyecto para nombre/cliente/version
        st2, d = upstream_json("GET", "/api/proyectos/%s" % STATE["slug"])
        if st2 == 200 and d:
            pr = d.get("proyecto") or {}
            inv["proyecto"] = {"nombre": pr.get("nombre") or STATE["slug"], "cliente": pr.get("cliente") or ""}
            vm = next((x for x in d.get("videos", []) if x.get("id") == STATE["video"]), None)
            if vm:
                inv["version"] = {"nombre": vm.get("nombre"), "fps": vm.get("fps"), "duracion": vm.get("duracion"),
                                  "ancho": vm.get("ancho"), "alto": vm.get("alto")}
        tag = "<script>window.__INVITADO=" + json.dumps(inv, ensure_ascii=False).replace("</", "<\\/") + "</script>\n"
        i = html.find("<script")
        html = html[:i] + tag + html[i:] if i >= 0 else html + tag
        self._send(200, html, "text/html; charset=utf-8", {
            "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff"})

    def do_POST(self):
        if self._mock():
            return
        p = self.path.split("?")[0]
        if self._muerta():
            self._body()
            return self._404()
        if p == "/api/invitado/nombre":
            d = self._jbody()
            if d is None:
                return
            nombre = str((d or {}).get("nombre", ""))
            if re.search(r"[\x00-\x1f\x7f]", nombre) or not nombre.strip() or len(nombre.strip()) > NOMBRE_MAX:
                return self._json({"error": "nombre"}, 400)
            with LOCK:
                STATE["nombre"] = nombre.strip()
            return self._json({"ok": True, "nombre": STATE["nombre"]})
        m = re.match(r"^/api/proyectos/([\w.-]+)/notas$", p)
        if m and m.group(1) == STATE["slug"]:
            d = self._jbody()
            if d is None:
                return
            if not STATE["nombre"]:
                return self._json({"error": "nombre"}, 403)
            d = d or {}
            texto = str(d.get("text", ""))[:4000]
            cuerpo = {"video": STATE["video"], "kind": "nota", "author": "invitado",
                      "autor_nombre": STATE["nombre"], "enlace_id": STATE["enlace_id"], "text": texto}
            for k in ("frame", "end_frame", "drawing", "thumb", "fps"):
                if k in d:
                    cuerpo[k] = d[k]
            if d.get("parent"):
                todas = notas_upstream(STATE["slug"])
                padre = next((x for x in todas if x.get("id") == d["parent"]), None)
                if not padre or not self._visible(padre, todas):
                    return self._404()
                cuerpo["parent"] = d["parent"]
            # server.py (base) no conoce autor_nombre/enlace_id como parámetros de add_note:
            # se crean y luego se completan los campos con un PATCH directo en notes.json
            st, r = upstream_json("POST", p, cuerpo)
            if st not in (200, 201) or not r or not r.get("nota"):
                return self._json(r or {"error": "upstream"}, st if st >= 400 else 500)
            n = self._completar(r["nota"])
            # un PATCH neutro hace que server.py suba `rev`: el poll de la UI ve los campos nuevos
            st2, r2 = upstream_json("PATCH", "/api/notas/%s/%s" % (STATE["slug"], n["id"]), {"text": n.get("text", "")})
            if st2 == 200 and r2 and r2.get("nota"):
                n = r2["nota"]
            return self._json({"nota": n}, 201)
        return self._404()

    def _completar(self, n):
        """server.py de la base ignora autor_nombre/enlace_id: se escriben a mano en notes.json."""
        import os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "data", STATE["slug"], "notes.json")
        try:
            with LOCK:
                notas = json.load(open(path, encoding="utf-8"))
                for x in notas:
                    if x.get("id") == n["id"]:
                        x["author"] = "invitado"
                        x["autor_nombre"] = STATE["nombre"]
                        x["enlace_id"] = STATE["enlace_id"]
                        n = dict(n, **{"author": "invitado", "autor_nombre": STATE["nombre"],
                                       "enlace_id": STATE["enlace_id"]})
                json.dump(notas, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as e:  # noqa
            n["mock_error"] = str(e)
        return n

    def do_PATCH(self):
        p = self.path.split("?")[0]
        if self._muerta():
            self._body()
            return self._404()
        m = re.match(r"^/api/notas/([\w.-]+)/([\w.-]+)$", p)
        if not (m and m.group(1) == STATE["slug"]):
            self._body()
            return self._404()
        d = self._jbody()
        if d is None:
            return
        todas = notas_upstream(STATE["slug"])
        n = next((x for x in todas if x.get("id") == m.group(2)), None)
        if not n or n.get("enlace_id") != STATE["enlace_id"]:
            return self._404()
        patch = {k: d[k] for k in ("text", "drawing") if k in (d or {})}
        if "text" in patch:
            patch["text"] = str(patch["text"])[:4000]
        st, r = upstream_json("PATCH", p, patch)
        return self._json(r or {}, st)

    def do_DELETE(self):
        self._body()
        return self._404()

    def do_PUT(self):
        self._body()
        return self._404()


# ═══════════════════════════ ADMINISTRACIÓN (simula lo nuevo de server.py) ═══════════════════════════
class Admin(Base):
    RE_INV = re.compile(r"^/api/proyectos/([\w.-]+)/videos/([\w.-]+)/invitar(?:/([\w-]+))?$")

    def _proxy(self):
        raw = self._body()
        if raw is None:
            return
        hd = {}
        for k in ("Content-Type", "Range", "X-Filename"):
            if self.headers.get(k):
                hd[k] = self.headers[k]
        st, h2, body = upstream(self.command, self.path, raw or None, hd)
        extra = {k: v for k, v in h2.items() if k.lower() in ("content-range", "accept-ranges", "x-build")}
        self._send(st, body, h2.get("Content-Type", JSON), extra)

    def _invitar(self, m):
        slug, vid, eid = m.group(1), m.group(2), m.group(3)
        if STATE["sin_endpoints"]:
            return self._json({"error": "no encontrado: " + self.path}, 404)
        if self.command == "POST" and not eid:
            d = self._jbody() or {}
            dias = d.get("dias", 7)
            try:
                dias = int(dias)
            except Exception:
                return self._json({"error": "dias"}, 400)
            if not 1 <= dias <= 90:
                return self._json({"error": "dias fuera de rango (1-90)"}, 400)
            e = {"id": secrets.token_hex(4), "token": secrets.token_urlsafe(32),
                 "creado": iso(ahora()), "expira": iso(ahora() + timedelta(days=dias)),
                 "revocado": False, "etiqueta": str(d.get("etiqueta", ""))[:ETQ_MAX],
                 "ve_otras": bool(d.get("ve_otras", False)), "usos": 0, "ultimo_uso": None,
                 "slug": slug, "vid": vid}
            e["url"] = "https://openframe.inspiredink.space/r/" + e["token"]
            with LOCK:
                STATE["enlaces"].append(e)
            return self._json({"id": e["id"], "token": e["token"], "url": e["url"], "expira": e["expira"],
                               "etiqueta": e["etiqueta"], "ve_otras": e["ve_otras"],
                               "publicada": bool(STATE["publicada"]),
                               "aviso": "" if STATE["publicada"] else "publicar.sh on falló (simulado)"}, 201)
        if self.command == "GET" and not eid:
            notas = notas_upstream(slug)
            out = []
            with LOCK:
                for e in STATE["enlaces"]:
                    if e.get("slug", slug) != slug or e.get("vid", vid) != vid:
                        continue
                    o = {k: e.get(k) for k in ("id", "url", "creado", "expira", "revocado", "etiqueta",
                                               "ve_otras", "usos", "ultimo_uso")}
                    o["notas"] = sum(1 for n in notas if n.get("enlace_id") == e.get("id"))
                    out.append(o)
            return self._json({"enlaces": out})
        if self.command == "DELETE" and eid:
            with LOCK:
                e = next((x for x in STATE["enlaces"] if x.get("id") == eid), None)
                if not e:
                    return self._json({"error": "enlace no existe"}, 404)
                e["revocado"] = True
            return self._json({"ok": True})
        return self._json({"error": "no encontrado: " + self.path}, 404)

    def _ruta(self):
        if self._mock():
            return
        p = self.path.split("?")[0]
        m = self.RE_INV.match(p)
        if m:
            return self._invitar(m)
        if p == "/api/invitados/estado" and self.command == "GET":
            if STATE["sin_endpoints"]:
                return self._json({"error": "no encontrado: " + p}, 404)
            with LOCK:
                act = sum(1 for e in STATE["enlaces"] if not e.get("revocado")
                          and str(e.get("expira", "")) > iso(ahora()))
            return self._json({"publicada": bool(STATE["publicada"]) and act > 0, "enlaces_activos": act})
        return self._proxy()

    do_GET = do_POST = do_PATCH = do_DELETE = do_HEAD = _ruta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", type=int, default=9383)
    ap.add_argument("--invitado", type=int, default=9384)
    ap.add_argument("--admin", type=int, default=9385)
    ap.add_argument("--slug", default="zz-port")
    ap.add_argument("--video", default=None)
    a = ap.parse_args()
    STATE["api"] = "http://127.0.0.1:%d" % a.api
    STATE["slug"] = a.slug
    if a.video:
        STATE["video"] = a.video
    else:
        st, d = upstream_json("GET", "/api/proyectos/%s" % a.slug)
        vids = (d or {}).get("videos", []) if st == 200 else []
        STATE["video"] = vids[0]["id"] if vids else None
    s1 = ThreadingHTTPServer(("127.0.0.1", a.invitado), Invitado)
    s2 = ThreadingHTTPServer(("127.0.0.1", a.admin), Admin)
    for s in (s1, s2):
        s.daemon_threads = True
        threading.Thread(target=s.serve_forever, daemon=True).start()
    print("mock invitado  http://127.0.0.1:%d  (slug=%s video=%s)" % (a.invitado, STATE["slug"], STATE["video"]))
    print("mock admin     http://127.0.0.1:%d  -> api %s" % (a.admin, STATE["api"]))
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
