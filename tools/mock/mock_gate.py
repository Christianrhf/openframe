#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract-shaped guest gate plus deliberate mutants.

Set OFG_MUTANT to one of:
trust_author, traversal, invite_file, no_expiry, prefix_slug, no_size_limit
"""
from __future__ import print_function

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse
from urllib.request import Request, build_opener


DATA = None
API = None
MUTANT = None
LOG = None
LOCK = threading.RLock()
WRITES = {}
ACTIVE = 0
MAX_CONN = 40


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value):
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return datetime.fromtimestamp(0, timezone.utc)


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, value, mode=None):
    tmp = path + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    if mode:
        try:
            os.chmod(path, mode)
        except OSError:
            pass


def pdir(slug):
    return os.path.join(DATA, slug)


def vdir(slug, vid):
    return os.path.join(pdir(slug), "videos", vid)


def invites_path(slug, vid):
    return os.path.join(vdir(slug, vid), "invitados.json")


def notes_path(slug):
    return os.path.join(pdir(slug), "notes.json")


def secret():
    path = os.path.join(DATA, ".guest_secret")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(os.urandom(32))
        os.chmod(path, 0o600)
    with open(path, "rb") as f:
        return f.read()


def sign_name(name):
    raw = name.encode("utf-8")
    sig = hmac.new(secret(), raw, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") + "." + sig


def verify_name(value):
    if not value or "." not in value or len(value) > 300:
        return None
    b64, sig = value.rsplit(".", 1)
    try:
        raw = base64.urlsafe_b64decode((b64 + "===")[:len(b64) + (-len(b64) % 4)])
    except Exception:
        return None
    good = hmac.new(secret(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    try:
        name = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if valid_name(name):
        return name
    return None


def valid_name(name):
    if not isinstance(name, str) or not (1 <= len(name) <= 40):
        return False
    for ch in name:
        if ord(ch) < 32 or ord(ch) == 127:
            return False
    return True


def find_token(token):
    if not token:
        return None
    for slug in os.listdir(DATA):
        videos = os.path.join(pdir(slug), "videos")
        if not os.path.isdir(videos):
            continue
        for vid in os.listdir(videos):
            path = invites_path(slug, vid)
            invites = read_json(path, [])
            for inv in invites:
                if inv.get("token") == token:
                    meta = read_json(os.path.join(vdir(slug, vid), "meta.json"), {})
                    proj = read_json(os.path.join(pdir(slug), "meta.json"), {})
                    return {
                        "slug": slug,
                        "vid": vid,
                        "path": path,
                        "invite": inv,
                        "invites": invites,
                        "project": proj,
                        "video": dict(meta, id=vid),
                    }
    return None


def is_active(info):
    inv = info["invite"] if info else {}
    if not info:
        return False
    if MUTANT == "no_expiry":
        return True
    if inv.get("revocado"):
        return False
    return parse_iso(inv.get("expira") or "") > datetime.now(timezone.utc)


def visible_notes(info):
    notes = read_json(notes_path(info["slug"]), [])
    own = set()
    visible = []
    for note in notes:
        if note.get("video") != info["vid"]:
            continue
        if info["invite"].get("ve_otras") or note.get("enlace_id") == info["invite"].get("id"):
            visible.append(note)
            own.add(note.get("id"))
    for note in notes:
        if note.get("video") == info["vid"] and note.get("parent") in own and note not in visible:
            visible.append(note)
    return visible


def api_json(method, path, data=None):
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(API + path, data=body, headers=headers, method=method)
    opener = build_opener()
    resp = opener.open(req, timeout=10)
    raw = resp.read()
    return resp.getcode(), json.loads(raw.decode("utf-8") or "{}")


def cookie_value(header, name):
    c = SimpleCookie()
    try:
        c.load(header or "")
    except Exception:
        return None
    if name in c:
        return c[name].value
    return None


def safe_join(root, *parts):
    path = os.path.realpath(os.path.join(root, *parts))
    root = os.path.realpath(root)
    if path == root or path.startswith(root + os.sep):
        return path
    return None


def log_line(info, status, path):
    if not LOG:
        return
    try:
        lid = info["invite"].get("id") if info else "-"
        clean = path.split("?", 1)[0]
        if clean.startswith("/r/"):
            clean = "/r/<token>"
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s id=%s status=%s path=%s\n" % (now_iso(), lid, status, clean))
    except Exception:
        pass


class GateServer(ThreadingHTTPServer):
    daemon_threads = True

    def get_request(self):
        global ACTIVE
        request, client = ThreadingHTTPServer.get_request(self)
        with LOCK:
            ACTIVE += 1
            over = ACTIVE > MAX_CONN
        if over:
            try:
                request.close()
            except Exception:
                pass
        request.settimeout(20)
        return request, client

    def close_request(self, request):
        global ACTIVE
        try:
            ThreadingHTTPServer.close_request(self, request)
        finally:
            with LOCK:
                ACTIVE = max(0, ACTIVE - 1)


class Handler(BaseHTTPRequestHandler):
    server_version = "MockOpenFrameGuest/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def send_body(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None, info=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass
        log_line(info, code, self.path)

    def send_json(self, code, value, info=None):
        self.send_body(code, json.dumps(value, ensure_ascii=False), info=info)

    def not_found(self, info=None):
        self.send_body(404, "Este enlace ya no esta disponible", "text/plain; charset=utf-8", info=info)

    def current_info(self):
        token = cookie_value(self.headers.get("Cookie"), "ofg")
        info = find_token(token)
        return info if is_active(info) else None

    def body(self, limit=True):
        cls = self.headers.get_all("Content-Length") or []
        if len(cls) > 1:
            raise ValueError("duplicate content-length")
        if self.headers.get("Transfer-Encoding") and cls:
            raise ValueError("te plus cl")
        n = int(cls[0]) if cls else 0
        if limit and MUTANT != "no_size_limit" and n > 1024 * 1024:
            raise OverflowError("too large")
        return self.rfile.read(n) if n else b""

    def jbody(self, limit=True):
        raw = self.body(limit=limit)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def rate_ok(self, info):
        key = info["invite"].get("id")
        now = time.time()
        with LOCK:
            rows = [t for t in WRITES.get(key, []) if now - t < 3600]
            minute = len([t for t in rows if now - t < 60])
            if minute >= 60 or len(rows) >= 300:
                WRITES[key] = rows
                return False
            rows.append(now)
            WRITES[key] = rows
            return True

    def handle_one_request(self):
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        except socket.timeout:
            try:
                self.close_connection = True
            except Exception:
                pass

    def do_GET(self):
        p = urlparse(self.path).path
        if p.startswith("/r/"):
            token = p.split("/", 2)[2]
            info = find_token(token)
            if not is_active(info):
                return self.not_found(info)
            with LOCK:
                info["invite"]["usos"] = int(info["invite"].get("usos") or 0) + 1
                info["invite"]["ultimo_uso"] = now_iso()
                write_json(info["path"], info["invites"], 0o600)
            max_age = max(1, int((parse_iso(info["invite"]["expira"]) - datetime.now(timezone.utc)).total_seconds()))
            cookie = "ofg=%s; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=%d" % (token, max_age)
            return self.send_body(302, b"", extra={"Location": "/", "Set-Cookie": cookie}, info=info)
        info = self.current_info()
        if not info:
            return self.not_found()
        if p in ("/", "/index.html"):
            name = verify_name(cookie_value(self.headers.get("Cookie"), "ofn"))
            payload = {
                "slug": info["slug"],
                "video": info["vid"],
                "nombre": name,
                "expira": info["invite"].get("expira"),
                "ve_otras": bool(info["invite"].get("ve_otras")),
                "proyecto": {"nombre": info["project"].get("nombre"), "cliente": info["project"].get("cliente")},
                "version": {
                    "nombre": info["video"].get("nombre"),
                    "fps": info["video"].get("fps"),
                    "duracion": info["video"].get("duracion"),
                    "ancho": info["video"].get("ancho"),
                    "alto": info["video"].get("alto"),
                },
            }
            boot = json.dumps(payload).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            html = "<!doctype html><script>window.__INVITADO=%s</script><script></script>" % boot
            return self.send_body(200, html, "text/html; charset=utf-8", info=info)
        if p == "/api/ping":
            return self.send_json(200, {"ok": True}, info=info)
        m = re.match(r"^/api/proyectos/([^/]+)$", p)
        if m:
            asked = m.group(1)
            allowed = asked.startswith(info["slug"]) if MUTANT == "prefix_slug" else asked == info["slug"]
            if not allowed:
                return self.not_found(info)
            meta = read_json(os.path.join(pdir(asked), "meta.json"), {})
            video = read_json(os.path.join(vdir(asked, info["vid"]), "meta.json"), None)
            if not video:
                return self.not_found(info)
            video = dict(video, id=info["vid"])
            return self.send_json(200, {"proyecto": meta, "videos": [video], "notas": visible_notes(info)}, info=info)
        m = re.match(r"^/api/notas/([^/]+)$", p)
        if m:
            asked = m.group(1)
            allowed = asked.startswith(info["slug"]) if MUTANT == "prefix_slug" else asked == info["slug"]
            if not allowed:
                return self.not_found(info)
            return self.send_json(200, {"notas": visible_notes(info)}, info=info)
        m = re.match(r"^/media/([^/]+)/([^/]+)/(.+)$", p)
        if m:
            return self.media(info, m.group(1), m.group(2), m.group(3))
        m = re.match(r"^/thumbs/([^/]+)/([^/]+)\.jpg$", p)
        if m:
            slug, nid = m.group(1), m.group(2)
            if slug != info["slug"] or not any(n.get("id") == nid or n.get("thumb") == nid + ".jpg" for n in visible_notes(info)):
                return self.not_found(info)
            path = safe_join(os.path.join(DATA, "thumbs", slug), nid + ".jpg")
            if not path or not os.path.exists(path):
                return self.not_found(info)
            with open(path, "rb") as f:
                return self.send_body(200, f.read(), "image/jpeg", info=info)
        return self.not_found(info)

    def do_HEAD(self):
        p = urlparse(self.path).path
        info = self.current_info()
        if not info:
            return self.not_found()
        m = re.match(r"^/media/([^/]+)/([^/]+)/(.+)$", p)
        if m:
            return self.media(info, m.group(1), m.group(2), m.group(3))
        return self.not_found(info)

    def media(self, info, slug, vid, name):
        name = unquote(name)
        if slug != info["slug"] or vid != info["vid"]:
            return self.not_found(info)
        root = vdir(slug, vid)
        if MUTANT == "invite_file" and name == "invitados.json":
            path = invites_path(slug, vid)
        elif MUTANT == "traversal":
            path = os.path.realpath(os.path.join(root, name))
        else:
            if not os.path.basename(name).startswith("media"):
                return self.not_found(info)
            if "/" in name or "\\" in name or "\x00" in name:
                return self.not_found(info)
            path = safe_join(root, name)
        if not path or not os.path.isfile(path):
            return self.not_found(info)
        if os.path.basename(path).startswith("media") and os.path.exists(os.path.join(root, "proxy-720.mp4")):
            path = os.path.join(root, "proxy-720.mp4")
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        start, end, code = 0, size - 1, 200
        extra = {"Accept-Ranges": "bytes"}
        if rng:
            m = re.match(r"^bytes=(\d+)-(\d*)$", rng)
            if not m:
                return self.send_body(416, b"", extra=extra, info=info)
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
            if start >= size or end < start:
                return self.send_body(416, b"", extra=extra, info=info)
            end = min(end, size - 1)
            code = 206
            extra["Content-Range"] = "bytes %d-%d/%d" % (start, end, size)
        with open(path, "rb") as f:
            f.seek(start)
            data = f.read(end - start + 1)
        return self.send_body(code, data, "video/mp4", extra=extra, info=info)

    def do_POST(self):
        p = urlparse(self.path).path
        info = self.current_info()
        if not info:
            return self.not_found()
        try:
            if p == "/api/invitado/nombre":
                data = self.jbody()
                name = data.get("nombre")
                if not valid_name(name):
                    return self.send_json(400, {"error": "nombre"}, info=info)
                return self.send_json(200, {"ok": True, "nombre": name}, info=info, extra_cookie=sign_name(name))
        except OverflowError:
            return self.send_json(413, {"error": "grande"}, info=info)
        except ValueError:
            return self.send_json(400, {"error": "bad framing"}, info=info)
        except Exception as exc:
            return self.send_json(400, {"error": str(exc)}, info=info)
        if p == "/api/invitado/nombre":
            return
        try:
            if re.match(r"^/api/proyectos/[^/]+/notas$", p):
                if not self.rate_ok(info):
                    return self.send_json(429, {"error": "limite"}, info=info)
                slug = p.split("/")[3]
                if slug != info["slug"]:
                    return self.not_found(info)
                name = verify_name(cookie_value(self.headers.get("Cookie"), "ofn"))
                if not name:
                    return self.send_json(403, {"error": "nombre"}, info=info)
                incoming = self.jbody(limit=True)
                allowed_parent = incoming.get("parent")
                if allowed_parent and not any(n.get("id") == allowed_parent for n in visible_notes(info)):
                    return self.not_found(info)
                drawing = incoming.get("drawing")
                if drawing and count_points(drawing) > 400:
                    return self.send_json(413, {"error": "drawing"}, info=info)
                thumb = incoming.get("thumb")
                if thumb and len(thumb.encode("utf-8")) > 600 * 1024:
                    return self.send_json(413, {"error": "thumb"}, info=info)
                if MUTANT == "trust_author":
                    out = dict(incoming)
                    out.setdefault("video", info["vid"])
                    out.setdefault("fps", info["video"].get("fps") or 24.0)
                    out.setdefault("kind", "nota")
                    out.setdefault("author", "invitado")
                    out.setdefault("autor_nombre", name)
                    out.setdefault("enlace_id", info["invite"].get("id"))
                else:
                    out = {
                        "text": (incoming.get("text") or "")[:4000],
                        "frame": incoming.get("frame") or 0,
                        "end_frame": incoming.get("end_frame"),
                        "drawing": drawing,
                        "thumb": thumb,
                        "parent": allowed_parent,
                    }
                    out.update({
                        "video": info["vid"],
                        "fps": info["video"].get("fps") or 24.0,
                        "kind": "nota",
                        "author": "invitado",
                        "autor_nombre": name,
                        "enlace_id": info["invite"].get("id"),
                    })
                    for key in ("resolved", "resuelve", "visto", "decision"):
                        out.pop(key, None)
                code, data = api_json("POST", "/api/proyectos/%s/notas" % info["slug"], out)
                return self.send_json(code, data, info=info)
        except OverflowError:
            return self.send_json(413, {"error": "grande"}, info=info)
        except ValueError:
            return self.send_json(400, {"error": "bad framing"}, info=info)
        except Exception as exc:
            return self.send_json(400, {"error": str(exc)}, info=info)
        return self.not_found(info)

    def send_json(self, code, value, info=None, extra_cookie=None):
        extra = {}
        if extra_cookie:
            extra["Set-Cookie"] = "ofn=%s; HttpOnly; Secure; SameSite=Lax; Path=/" % extra_cookie
        self.send_body(code, json.dumps(value, ensure_ascii=False), info=info, extra=extra)

    def do_PATCH(self):
        p = urlparse(self.path).path
        info = self.current_info()
        if not info:
            return self.not_found()
        m = re.match(r"^/api/notas/([^/]+)/([^/]+)$", p)
        if not m or m.group(1) != info["slug"]:
            return self.not_found(info)
        try:
            data = self.jbody()
        except Exception:
            return self.send_json(400, {"error": "bad"}, info=info)
        nid = m.group(2)
        own = None
        for note in visible_notes(info):
            if note.get("id") == nid and note.get("enlace_id") == info["invite"].get("id"):
                own = note
                break
        if not own:
            return self.not_found(info)
        patch = {}
        if "text" in data:
            patch["text"] = data["text"]
        if "drawing" in data:
            patch["drawing"] = data["drawing"]
        code, result = api_json("PATCH", "/api/notas/%s/%s" % (info["slug"], nid), patch)
        return self.send_json(code, result, info=info)

    def do_DELETE(self):
        return self.not_found(self.current_info())

    def do_PUT(self):
        return self.not_found(self.current_info())

    def do_OPTIONS(self):
        return self.not_found(self.current_info())

    def do_TRACE(self):
        return self.not_found(self.current_info())

    def do_CONNECT(self):
        return self.not_found(self.current_info())

    def do_PROPFIND(self):
        return self.not_found(self.current_info())


def count_points(drawing):
    total = 0
    if isinstance(drawing, dict):
        strokes = drawing.get("strokes") or []
    elif isinstance(drawing, list):
        strokes = drawing
    else:
        return 0
    for stroke in strokes:
        pts = stroke.get("points") if isinstance(stroke, dict) else stroke
        if isinstance(pts, list):
            total += len(pts)
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--puerto", type=int, default=9398)
    parser.add_argument("--api", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--log")
    args = parser.parse_args()
    global DATA, API, MUTANT, LOG
    DATA = os.path.abspath(args.data)
    API = args.api.rstrip("/")
    MUTANT = os.environ.get("OFG_MUTANT") or ""
    LOG = args.log
    srv = GateServer(("127.0.0.1", args.puerto), Handler)
    print("mock gate http://127.0.0.1:%d mutant=%s" % (args.puerto, MUTANT or "correct"), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
