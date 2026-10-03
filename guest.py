#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Puerta publica, deliberadamente pequena, para un solo video por enlace."""
import argparse
import base64
import binascii
import collections
import fcntl
import hashlib
import hmac
import http.cookies
import json
import math
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
THUMBS = os.path.join(BASE, "thumbs")
LOGS = os.path.join(BASE, "logs")
BODY_MAX = 1024 * 1024
THUMB_MAX = 600 * 1024
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
SLUG_RE = r"[A-Za-z0-9][A-Za-z0-9.-]{0,63}"
VID_RE = r"v_[0-9a-f]{8}"
NOTE_RE = r"[A-Za-z0-9_-]{1,80}"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
NOT_FOUND = ("<!doctype html><meta charset=utf-8><title>No disponible</title>"
             "<p>Este enlace ya no está disponible</p>").encode("utf-8")


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def parse_iso(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (AttributeError, TypeError, ValueError):
        return None


def active(link):
    expiry = parse_iso(link.get("expira"))
    return bool(expiry and not link.get("revocado") and expiry > datetime.now(timezone.utc))


def atomic_links(path, mutate):
    """Actualiza usos sin perder una revocacion concurrente de server.py."""
    lock_path = path + ".lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with os.fdopen(fd, "r+") as lockf:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
            links = read_json(path, [])
            if not isinstance(links, list):
                return None
            result = mutate(links)
            if result is None:
                return None
            tmp = path + ".tmp-%d-%s" % (os.getpid(), uuid.uuid4().hex[:8])
            outfd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(outfd, "w", encoding="utf-8") as f:
                    json.dump(links, f, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
                os.chmod(path, 0o600)
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            return result
    finally:
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass


class InvitationStore(object):
    def __init__(self):
        self.lock = threading.RLock()
        self.files = {}

    def _paths(self):
        paths = []
        try:
            slugs = os.listdir(DATA)
        except OSError:
            return paths
        for slug in slugs:
            videos = os.path.join(DATA, slug, "videos")
            try:
                vids = os.listdir(videos)
            except OSError:
                continue
            for vid in vids:
                path = os.path.join(videos, vid, "invitados.json")
                if os.path.isfile(path):
                    paths.append((slug, vid, path))
        return paths

    def refresh(self):
        with self.lock:
            present = set()
            for slug, vid, path in self._paths():
                present.add(path)
                try:
                    stamp = os.stat(path).st_mtime_ns
                except OSError:
                    continue
                old = self.files.get(path)
                if old is None or old[0] != stamp:
                    links = read_json(path, [])
                    self.files[path] = (stamp, slug, vid,
                                        links if isinstance(links, list) else [])
            for path in list(self.files):
                if path not in present:
                    del self.files[path]

    def by_token(self, token):
        if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
            return None
        self.refresh()
        with self.lock:
            for path, (_stamp, slug, vid, links) in self.files.items():
                for link in links:
                    candidate = link.get("token", "") if isinstance(link, dict) else ""
                    if (len(candidate) == len(token) and
                            secrets.compare_digest(candidate, token) and active(link)):
                        return slug, vid, dict(link), path
        return None

    def record_use(self, found):
        slug, vid, link, path = found
        enlace_id = link.get("id")

        def change(links):
            for current in links:
                if current.get("id") == enlace_id and active(current):
                    current["usos"] = int(current.get("usos") or 0) + 1
                    current["ultimo_uso"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    return dict(current)
            return None

        updated = atomic_links(path, change)
        self.refresh()
        return (slug, vid, updated, path) if updated is not None else None


class RateLimiter(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.events = {}

    def allow(self, enlace_id):
        now = time.monotonic()
        with self.lock:
            q = self.events.setdefault(enlace_id, collections.deque())
            while q and q[0] <= now - 3600:
                q.popleft()
            recent = sum(1 for stamp in q if stamp > now - 60)
            if recent >= 60 or len(q) >= 300:
                return False
            q.append(now)
            return True


STORE = InvitationStore()
LIMITER = RateLimiter()
LOG_LOCK = threading.Lock()


def secret_value():
    path = os.path.join(DATA, ".guest_secret")
    try:
        with open(path, "rb") as f:
            value = f.read()
        if len(value) != 32:
            raise ValueError("secreto invalido")
        os.chmod(path, 0o600)
        return value
    except Exception:
        raise RuntimeError("falta data/.guest_secret valido; arranca server.py primero")


def safe_script_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def log_event(enlace_id, method, status):
    os.makedirs(LOGS, exist_ok=True)
    line = "%s id=%s method=%s status=%d\n" % (
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        enlace_id if re.fullmatch(r"[0-9a-f]{8}", enlace_id or "") else "-",
        method if method in ("GET", "HEAD", "POST", "PATCH") else "OTRO", status)
    with LOG_LOCK:
        with open(os.path.join(LOGS, "guest.log"), "a", encoding="utf-8") as f:
            f.write(line)


class LimitedServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 40

    def __init__(self, address, handler):
        self.slots = threading.BoundedSemaphore(40)
        super().__init__(address, handler)

    def get_request(self):
        sock, addr = super().get_request()
        sock.settimeout(20)
        return sock, addr

    def process_request(self, request, client_address):
        self.slots.acquire()
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def shutdown_request(self, request):
        try:
            super().shutdown_request(request)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenFrameGuest/1.0"
    protocol_version = "HTTP/1.1"
    api = "http://127.0.0.1:8477"
    gate_secret = b""

    def log_message(self, fmt, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        # BaseHTTPRequestHandler usa 501 para verbos sin do_*; la puerta no revela
        # esa diferencia: todo verbo fuera de la lista blanca es el mismo 404.
        if code == 501:
            return self._404()
        return super().send_error(code, message, explain)

    def _headers(self, ctype, length, extra=None):
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or []):
            self.send_header(key, value)

    def _send(self, status, body=b"", ctype="application/json; charset=utf-8", extra=None,
              enlace_id=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self._headers(ctype, len(body), extra)
        self.end_headers()
        if self.command != "HEAD" and body:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        log_event(enlace_id, self.command, status)

    def _json(self, value, status=200, extra=None, enlace_id=None):
        return self._send(status, json.dumps(value, ensure_ascii=False),
                          "application/json; charset=utf-8", extra, enlace_id)

    def _404(self, enlace_id=None):
        return self._send(404, NOT_FOUND, "text/html; charset=utf-8", enlace_id=enlace_id)

    def _cookie_values(self):
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return {}
        return {key: morsel.value for key, morsel in jar.items()}

    def _session(self):
        token = self._cookie_values().get("ofg")
        return STORE.by_token(token)

    def _request_path(self):
        """Conserva la distincion de targets ambiguos que http.server normaliza."""
        parts = self.requestline.split(" ")
        if len(parts) < 2:
            return None
        target = parts[1]
        if target.startswith("//") or target.startswith("http://") or target.startswith("https://"):
            return None
        try:
            return urlsplit(target).path
        except ValueError:
            return None

    def _max_age(self, link):
        expiry = parse_iso(link.get("expira"))
        if expiry is None:
            return 0
        return max(0, int((expiry - datetime.now(timezone.utc)).total_seconds()))

    def _cookie(self, key, value, link):
        return "%s=%s; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=%d" % (
            key, value, self._max_age(link))

    def _signed_name(self, name, enlace_id):
        payload = base64.urlsafe_b64encode(name.encode("utf-8")).rstrip(b"=").decode("ascii")
        mac = hmac.new(self.gate_secret, (enlace_id + "\0" + payload).encode("ascii"),
                       hashlib.sha256).hexdigest()
        return payload + "." + mac

    def _name(self, link):
        raw = self._cookie_values().get("ofn", "")
        try:
            payload, supplied = raw.split(".", 1)
            expected = hmac.new(
                self.gate_secret, (link["id"] + "\0" + payload).encode("ascii"),
                hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, supplied):
                return None
            padded = payload + "=" * ((4 - len(payload) % 4) % 4)
            name = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
            if not self._valid_name(name):
                return None
            return name
        except (ValueError, UnicodeError, binascii.Error, KeyError):
            return None

    @staticmethod
    def _valid_name(name):
        return (isinstance(name, str) and 1 <= len(name) <= 40 and
                not any(ord(ch) < 32 or ord(ch) == 127 for ch in name))

    def _body(self):
        if self.headers.get("Transfer-Encoding"):
            return None, 413
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None, 413
        if size < 0 or size > BODY_MAX:
            self.close_connection = True
            return None, 413
        raw = self.rfile.read(size) if size else b""
        try:
            value = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeError, ValueError):
            return None, 400
        if not isinstance(value, dict):
            return None, 400
        return value, None

    def _upstream(self, method, path, payload=None, gate=False):
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if gate:
            headers["X-Guest-Gate"] = self.gate_secret.hex()
        req = Request(self.api + path, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=20) as resp:
                raw = resp.read(BODY_MAX + 1)
                if len(raw) > BODY_MAX:
                    return 502, {"error": "respuesta demasiado grande"}
                return resp.status, json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            try:
                body = json.loads(exc.read(BODY_MAX + 1).decode("utf-8"))
            except Exception:
                body = {"error": "no disponible"}
            return exc.code, body
        except (URLError, OSError, ValueError):
            return 502, {"error": "no disponible"}

    def _project(self, slug):
        return self._upstream("GET", "/api/proyectos/" + slug)

    def _visible(self, session):
        slug, vid, link, _path = session
        status, data = self._upstream("GET", "/api/notas/" + slug)
        if status != 200 or not isinstance(data, dict):
            return None
        shared = [n for n in data.get("notas", [])
                  if isinstance(n, dict) and n.get("video") == vid]
        if link.get("ve_otras"):
            return shared
        own_ids = {n.get("id") for n in shared if n.get("enlace_id") == link.get("id")}
        return [n for n in shared
                if n.get("enlace_id") == link.get("id") or n.get("parent") in own_ids]

    @staticmethod
    def _drawing(value):
        if value is None:
            return None
        if not isinstance(value, dict) or not isinstance(value.get("strokes"), list):
            raise ValueError("dibujo invalido")
        total = 0
        if len(value["strokes"]) > 100:
            raise ValueError("dibujo demasiado grande")
        for stroke in value["strokes"]:
            if not isinstance(stroke, dict) or not isinstance(stroke.get("pts"), list):
                raise ValueError("dibujo invalido")
            total += len(stroke["pts"])
            if total > 400:
                raise ValueError("dibujo demasiado grande")
            for point in stroke["pts"]:
                if not isinstance(point, dict):
                    raise ValueError("dibujo invalido")
                x, y = point.get("x"), point.get("y")
                if (isinstance(x, bool) or isinstance(y, bool) or
                        not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or
                        not math.isfinite(x) or not math.isfinite(y) or
                        not 0 <= x <= 1 or not 0 <= y <= 1):
                    raise ValueError("dibujo invalido")
        return value

    @staticmethod
    def _thumb(value):
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise ValueError("miniatura invalida")
        raw = value.split(",", 1)[-1]
        try:
            decoded = base64.b64decode(raw.encode("ascii"), validate=True)
        except (UnicodeError, binascii.Error):
            raise ValueError("miniatura invalida")
        if len(decoded) > THUMB_MAX:
            raise ValueError("miniatura demasiado grande")
        return value

    def _write_allowed(self, link):
        if LIMITER.allow(link.get("id")):
            return True
        self._json({"error": "demasiadas solicitudes"}, 429, enlace_id=link.get("id"))
        return False

    def do_GET(self):
        path = self._request_path()
        if path is None:
            return self._404()
        if path == "/api/ping":
            return self._json({"ok": True})
        match = re.fullmatch(r"/r/([A-Za-z0-9_-]{43})", path)
        if match:
            found = STORE.by_token(match.group(1))
            if found is None:
                return self._404()
            found = STORE.record_use(found)
            if found is None:
                return self._404()
            _slug, _vid, link, _file = found
            return self._send(302, b"", "text/html; charset=utf-8",
                              [("Location", "/"),
                               ("Set-Cookie", self._cookie("ofg", match.group(1), link))],
                              link.get("id"))
        session = self._session()
        if session is None:
            return self._404()
        slug, vid, link, _file = session
        enlace_id = link.get("id")
        if path == "/":
            status, pdata = self._project(slug)
            if status != 200:
                return self._404(enlace_id)
            video = next((v for v in pdata.get("videos", []) if v.get("id") == vid), None)
            if video is None:
                return self._404(enlace_id)
            config = {
                "slug": slug, "video": vid, "nombre": self._name(link),
                "expira": link.get("expira"), "ve_otras": bool(link.get("ve_otras")),
                "proyecto": {"nombre": pdata.get("proyecto", {}).get("nombre", slug),
                             "cliente": pdata.get("proyecto", {}).get("cliente", "")},
                "version": {key: video.get(key) for key in
                            ("nombre", "fps", "duracion", "ancho", "alto")},
            }
            try:
                with open(os.path.join(BASE, "visor.html"), "r", encoding="utf-8") as f:
                    html = f.read()
            except OSError:
                return self._404(enlace_id)
            marker = html.find("<script>")
            if marker < 0:
                return self._404(enlace_id)
            injected = "<script>window.__INVITADO=%s</script>" % safe_script_json(config)
            body = (html[:marker] + injected + html[marker:]).encode("utf-8")
            return self._send(200, body, "text/html; charset=utf-8", enlace_id=enlace_id)
        if re.fullmatch(r"/api/proyectos/" + re.escape(slug), path):
            status, pdata = self._project(slug)
            if status != 200:
                return self._404(enlace_id)
            visible = self._visible(session)
            if visible is None:
                return self._404(enlace_id)
            pdata["videos"] = [v for v in pdata.get("videos", []) if v.get("id") == vid]
            pdata["notas"] = visible
            return self._json(pdata, enlace_id=enlace_id)
        if re.fullmatch(r"/api/notas/" + re.escape(slug), path):
            visible = self._visible(session)
            if visible is None:
                return self._404(enlace_id)
            return self._json({"notas": visible}, enlace_id=enlace_id)
        media = re.fullmatch(r"/media/(" + SLUG_RE + r")/(" + VID_RE +
                             r")/([A-Za-z0-9][A-Za-z0-9._-]{0,127})", path)
        if media:
            if media.group(1) != slug or media.group(2) != vid:
                return self._404(enlace_id)
            return self._media(session, media.group(3), head=False)
        thumb = re.fullmatch(r"/thumbs/(" + SLUG_RE + r")/(" + NOTE_RE + r")\.jpg", path)
        if thumb:
            if thumb.group(1) != slug:
                return self._404(enlace_id)
            return self._thumb_file(session, thumb.group(2), head=False)
        return self._404(enlace_id)

    def do_HEAD(self):
        path = self._request_path()
        if path is None:
            return self._404()
        session = self._session()
        if session is None:
            return self._404()
        slug, vid, link, _file = session
        media = re.fullmatch(r"/media/(" + SLUG_RE + r")/(" + VID_RE +
                             r")/([A-Za-z0-9][A-Za-z0-9._-]{0,127})", path)
        if media and media.group(1) == slug and media.group(2) == vid:
            return self._media(session, media.group(3), head=True)
        return self._404(link.get("id"))

    def do_POST(self):
        path = self._request_path()
        if path is None:
            return self._404()
        session = self._session()
        if session is None:
            return self._404()
        slug, vid, link, _file = session
        enlace_id = link.get("id")
        name_route = path == "/api/invitado/nombre"
        note_route = re.fullmatch(r"/api/proyectos/" + re.escape(slug) + r"/notas", path)
        if not name_route and not note_route:
            return self._404(enlace_id)
        body, error = self._body()
        if error:
            return self._json({"error": "cuerpo invalido"}, error, enlace_id=enlace_id)
        if not self._write_allowed(link):
            return
        if name_route:
            name = body.get("nombre")
            if not self._valid_name(name):
                return self._json({"error": "nombre invalido"}, 400, enlace_id=enlace_id)
            cookie = self._cookie("ofn", self._signed_name(name, enlace_id), link)
            return self._json({"ok": True, "nombre": name}, extra=[("Set-Cookie", cookie)],
                              enlace_id=enlace_id)
        name = self._name(link)
        if name is None:
            return self._json({"error": "nombre"}, 403, enlace_id=enlace_id)
        text = body.get("text", "")
        if not isinstance(text, str) or len(text) > 4000:
            return self._json({"error": "texto invalido"}, 400, enlace_id=enlace_id)
        frame = body.get("frame", 0)
        end_frame = body.get("end_frame")
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return self._json({"error": "fotograma invalido"}, 400, enlace_id=enlace_id)
        if (end_frame not in (None, "", 0) and
                (isinstance(end_frame, bool) or not isinstance(end_frame, int) or end_frame < frame)):
            return self._json({"error": "tramo invalido"}, 400, enlace_id=enlace_id)
        try:
            drawing = self._drawing(body.get("drawing"))
            thumb = self._thumb(body.get("thumb"))
        except ValueError as exc:
            return self._json({"error": str(exc)}, 400, enlace_id=enlace_id)
        parent = body.get("parent")
        if parent is not None:
            visible = self._visible(session)
            if (not isinstance(parent, str) or
                    not any(n.get("id") == parent for n in (visible or []))):
                return self._404(enlace_id)
        forced = {
            "video": vid, "fps": self._video_fps(slug, vid), "kind": "nota",
            "author": "invitado", "autor_nombre": name, "enlace_id": enlace_id,
            "text": text, "frame": frame, "end_frame": end_frame,
            "drawing": drawing, "thumb": thumb, "parent": parent,
        }
        status, data = self._upstream("POST", "/api/proyectos/%s/notas" % slug,
                                      forced, gate=True)
        if status == 404:
            return self._404(enlace_id)
        return self._json(data, status, enlace_id=enlace_id)

    def _video_fps(self, slug, vid):
        status, pdata = self._project(slug)
        if status == 200:
            video = next((v for v in pdata.get("videos", []) if v.get("id") == vid), None)
            if video:
                try:
                    fps = float(video.get("fps") or 24)
                    if math.isfinite(fps) and 12 <= fps <= 240:
                        return fps
                except (TypeError, ValueError):
                    pass
        return 24.0

    def do_PATCH(self):
        path = self._request_path()
        if path is None:
            return self._404()
        session = self._session()
        if session is None:
            return self._404()
        slug, _vid, link, _file = session
        enlace_id = link.get("id")
        match = re.fullmatch(r"/api/notas/" + re.escape(slug) + r"/(" + NOTE_RE + r")", path)
        if not match:
            return self._404(enlace_id)
        body, error = self._body()
        if error:
            return self._json({"error": "cuerpo invalido"}, error, enlace_id=enlace_id)
        if not self._write_allowed(link):
            return
        if not body or any(key not in ("text", "drawing") for key in body):
            return self._404(enlace_id)
        visible = self._visible(session)
        note = next((n for n in (visible or []) if n.get("id") == match.group(1)), None)
        if note is None or note.get("enlace_id") != enlace_id:
            return self._404(enlace_id)
        clean = {}
        if "text" in body:
            if not isinstance(body["text"], str) or len(body["text"]) > 4000:
                return self._json({"error": "texto invalido"}, 400, enlace_id=enlace_id)
            clean["text"] = body["text"]
        if "drawing" in body:
            try:
                clean["drawing"] = self._drawing(body["drawing"])
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400, enlace_id=enlace_id)
        status, data = self._upstream("PATCH", "/api/notas/%s/%s" % (slug, match.group(1)), clean)
        if status == 404:
            return self._404(enlace_id)
        return self._json(data, status, enlace_id=enlace_id)

    def _media(self, session, requested, head=False):
        slug, vid, link, _file = session
        enlace_id = link.get("id")
        meta_path = os.path.join(DATA, slug, "videos", vid, "meta.json")
        meta = read_json(meta_path, {})
        declared = meta.get("archivo")
        if (requested not in (declared, "proxy-720.mp4") or
                os.path.splitext(requested)[1].lower() not in VIDEO_EXT):
            return self._404(enlace_id)
        video_dir = os.path.realpath(os.path.join(DATA, slug, "videos", vid))
        actual = requested
        if requested == declared and requested.startswith("media."):
            proxy = os.path.join(video_dir, "proxy-720.mp4")
            if os.path.isfile(proxy):
                actual = "proxy-720.mp4"
        path = os.path.realpath(os.path.join(video_dir, actual))
        if not path.startswith(video_dir + os.sep) or not os.path.isfile(path):
            return self._404(enlace_id)
        size = os.path.getsize(path)
        start, end, status = 0, size - 1, 200
        range_value = self.headers.get("Range")
        if range_value:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_value.strip())
            valid = bool(match and size > 0 and (match.group(1) or match.group(2)))
            if valid:
                if match.group(1):
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else size - 1
                else:
                    suffix = int(match.group(2))
                    valid = suffix > 0
                    start = max(0, size - suffix)
                    end = size - 1
                valid = valid and start < size and start <= end
                end = min(end, size - 1)
            if not valid:
                return self._send(416, b"", "application/json; charset=utf-8",
                                  [("Content-Range", "bytes */%d" % size)], enlace_id)
            status = 206
        length = max(0, end - start + 1)
        ctype = "video/mp4" if path.lower().endswith((".mp4", ".m4v")) else "video/quicktime"
        extra = [("Accept-Ranges", "bytes")]
        if status == 206:
            extra.append(("Content-Range", "bytes %d-%d/%d" % (start, end, size)))
        self.send_response(status)
        self._headers(ctype, length, extra)
        self.end_headers()
        if not head:
            try:
                with open(path, "rb") as f:
                    f.seek(start)
                    left = length
                    while left:
                        chunk = f.read(min(65536, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
        log_event(enlace_id, self.command, status)

    def _thumb_file(self, session, note_id, head=False):
        slug, _vid, link, _file = session
        visible = self._visible(session)
        if not any(n.get("id") == note_id and n.get("thumb") == note_id + ".jpg"
                   for n in (visible or [])):
            return self._404(link.get("id"))
        root = os.path.realpath(os.path.join(THUMBS, slug))
        path = os.path.realpath(os.path.join(root, note_id + ".jpg"))
        if not path.startswith(root + os.sep) or not os.path.isfile(path):
            return self._404(link.get("id"))
        size = os.path.getsize(path)
        self.send_response(200)
        self._headers("image/jpeg", size)
        self.end_headers()
        if not head:
            try:
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
        log_event(link.get("id"), self.command, 200)

    def _unknown(self):
        session = self._session()
        return self._404(session[2].get("id") if session else None)

    do_DELETE = _unknown
    do_PUT = _unknown
    do_OPTIONS = _unknown
    do_TRACE = _unknown
    do_CONNECT = _unknown


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--puerto", type=int, default=8478)
    parser.add_argument("--api", default="http://127.0.0.1:8477")
    args = parser.parse_args()
    if not re.fullmatch(r"http://127\.0\.0\.1:\d{1,5}", args.api.rstrip("/")):
        raise SystemExit("--api debe apuntar a http://127.0.0.1:<puerto>")
    Handler.api = args.api.rstrip("/")
    Handler.gate_secret = secret_value()
    server = LimitedServer(("127.0.0.1", args.puerto), Handler)
    print("Puerta de invitados en http://127.0.0.1:%d" % args.puerto)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nparado")


if __name__ == "__main__":
    main()
