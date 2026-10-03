#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal administration/data API for tools/attack-guest.py.

It intentionally implements only the contract surface the black-box suite needs.
"""
from __future__ import print_function

import argparse
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


LOCK = threading.RLock()
DATA = None


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(value):
    value = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return re.sub(r"-{2,}", "-", value)[:48] or "proyecto"


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, value, mode=None):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    if mode is not None:
        try:
            os.chmod(path, mode)
        except OSError:
            pass


def pdir(slug):
    return os.path.join(DATA, slug)


def vdir(slug, vid):
    return os.path.join(pdir(slug), "videos", vid)


def notes_path(slug):
    return os.path.join(pdir(slug), "notes.json")


def load_notes(slug):
    return read_json(notes_path(slug), [])


def save_notes(slug, notes):
    write_json(notes_path(slug), notes)


def invites_path(slug, vid):
    return os.path.join(vdir(slug, vid), "invitados.json")


def load_invites(slug, vid):
    return read_json(invites_path(slug, vid), [])


def save_invites(slug, vid, invites):
    write_json(invites_path(slug, vid), invites, 0o600)


def load_videos(slug):
    root = os.path.join(pdir(slug), "videos")
    out = []
    if not os.path.isdir(root):
        return out
    for vid in sorted(os.listdir(root)):
        meta = read_json(os.path.join(root, vid, "meta.json"), None)
        if meta:
            item = dict(meta)
            item["id"] = vid
            out.append(item)
    return out


def decorate(notes):
    out = []
    for n in notes:
        c = dict(n)
        c["respuestas"] = len([r for r in notes if r.get("parent") == n.get("id")])
        c["estado"] = "cerrada" if c.get("resolved") else ("respondida" if c["respuestas"] else "pendiente")
        if c.get("parent"):
            c["respuestas"] = 0
            c["estado"] = None
        out.append(c)
    return out


def timecode(frame, fps):
    fps = float(fps or 24.0)
    sec = int(frame / fps)
    return "%02d:%02d:%02d:%02d" % (sec // 3600, (sec // 60) % 60, sec % 60, int(frame % fps))


def add_note(slug, data):
    notes = load_notes(slug)
    parent = data.get("parent")
    if parent:
        root = None
        for n in notes:
            if n.get("id") == parent:
                root = n
                break
        if not root:
            raise ValueError("parent missing")
        video = root.get("video")
        frame = int(root.get("frame") or 0)
        fps = float(root.get("fps") or 24.0)
    else:
        video = data.get("video")
        if not video:
            raise ValueError("video missing")
        frame = int(data.get("frame") or 0)
        fps = float(data.get("fps") or 24.0)
    note = {
        "id": data.get("id") or "n_" + uuid.uuid4().hex[:8],
        "video": video,
        "frame": frame,
        "fps": round(fps, 3),
        "timecode": timecode(frame, fps),
        "time": round(frame / fps, 3),
        "end_frame": data.get("end_frame"),
        "text": data.get("text") or "",
        "kind": "cambio" if data.get("kind") == "cambio" else "nota",
        "resolved": bool(data.get("resolved")),
        "author": data.get("author") or "cristian",
        "autor_nombre": data.get("autor_nombre"),
        "enlace_id": data.get("enlace_id"),
        "created": data.get("created") or now_iso(),
        "parent": parent or None,
    }
    note["thread"] = parent or note["id"]
    for key in ("drawing", "thumb", "visto", "resuelve", "decision"):
        if key in data:
            note[key] = data[key]
    notes.append(note)
    save_notes(slug, notes)
    return note


def count_notes(slug, link_id):
    return len([n for n in load_notes(slug) if n.get("enlace_id") == link_id])


class Handler(BaseHTTPRequestHandler):
    server_version = "MockOpenFrameAPI/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def send_body(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, code, value):
        self.send_body(code, json.dumps(value, ensure_ascii=False))

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def jbody(self):
        raw = self.body()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/api/ping":
            return self.send_json(200, {"ok": True})
        if p == "/api/proyectos":
            proyectos = []
            for slug in sorted(os.listdir(DATA)):
                meta = read_json(os.path.join(pdir(slug), "meta.json"), None)
                if meta:
                    proyectos.append(meta)
            return self.send_json(200, {"proyectos": proyectos, "archivados": [], "todos": proyectos})
        m = re.match(r"^/api/proyectos/([\w.-]+)$", p)
        if m:
            slug = m.group(1)
            meta = read_json(os.path.join(pdir(slug), "meta.json"), None)
            if not meta:
                return self.send_json(404, {"error": "no existe"})
            return self.send_json(200, {"proyecto": meta, "videos": load_videos(slug), "notas": decorate(load_notes(slug))})
        m = re.match(r"^/api/notas/([\w.-]+)$", p)
        if m:
            return self.send_json(200, {"notas": decorate(load_notes(m.group(1)))})
        m = re.match(r"^/api/proyectos/([\w.-]+)/videos/([\w.-]+)/invitar$", p)
        if m:
            slug, vid = m.group(1), m.group(2)
            base = os.environ.get("MOCK_BASE_PUBLICA", "https://openframe.inspiredink.space")
            links = []
            for inv in load_invites(slug, vid):
                item = dict(inv)
                item["url"] = base + "/r/" + inv["token"]
                item["notas"] = count_notes(slug, inv["id"])
                links.append(item)
            return self.send_json(200, {"enlaces": links})
        m = re.match(r"^/api/invitados/actividad$", p)
        if m:
            return self.send_json(200, {"notas": []})
        return self.send_json(404, {"error": "no encontrado"})

    def do_POST(self):
        p = self.path.split("?", 1)[0]
        try:
            if p == "/api/proyectos":
                data = self.jbody()
                base = slugify(data.get("nombre") or "proyecto")
                slug = base
                i = 2
                with LOCK:
                    while os.path.exists(pdir(slug)):
                        slug = "%s-%d" % (base, i)
                        i += 1
                    os.makedirs(os.path.join(pdir(slug), "videos"), exist_ok=True)
                    meta = {
                        "slug": slug,
                        "nombre": data.get("nombre") or slug,
                        "cliente": data.get("cliente") or "",
                        "nota": data.get("nota") or "",
                        "created": now_iso(),
                    }
                    write_json(os.path.join(pdir(slug), "meta.json"), meta)
                    save_notes(slug, [])
                return self.send_json(200, {"slug": slug})
            m = re.match(r"^/api/proyectos/([\w.-]+)/videos$", p)
            if m:
                slug = m.group(1)
                if not os.path.isdir(pdir(slug)):
                    return self.send_json(404, {"error": "no existe"})
                raw = self.body()
                if not raw:
                    return self.send_json(400, {"error": "cuerpo vacio"})
                fname = self.headers.get("X-Filename", "clip.mp4")
                vid = "v_" + uuid.uuid4().hex[:8]
                os.makedirs(vdir(slug, vid), exist_ok=True)
                media = os.path.join(vdir(slug, vid), "media.mp4")
                with open(media, "wb") as f:
                    f.write(raw)
                meta = {
                    "id": vid,
                    "nombre": fname,
                    "archivo": "media.mp4",
                    "bytes": len(raw),
                    "codec": "H.264",
                    "reproducible": True,
                    "duracion": 4.0,
                    "fps": 24.0,
                    "ancho": 640,
                    "alto": 360,
                    "created": now_iso(),
                    "origen": "mock",
                }
                write_json(os.path.join(vdir(slug, vid), "meta.json"), dict((k, v) for k, v in meta.items() if k != "id"))
                return self.send_json(200, {"video": meta})
            m = re.match(r"^/api/proyectos/([\w.-]+)/notas$", p)
            if m:
                note = add_note(m.group(1), self.jbody())
                return self.send_json(201, {"nota": note})
            m = re.match(r"^/api/proyectos/([\w.-]+)/videos/([\w.-]+)/invitar$", p)
            if m:
                slug, vid = m.group(1), m.group(2)
                if not os.path.isdir(vdir(slug, vid)):
                    return self.send_json(404, {"error": "no existe"})
                data = self.jbody()
                dias = int(data.get("dias") or 7)
                dias = max(1, min(90, dias))
                inv = {
                    "id": secrets.token_hex(4),
                    "token": secrets.token_urlsafe(32),
                    "creado": now_iso(),
                    "expira": (datetime.now(timezone.utc) + timedelta(days=dias)).isoformat(timespec="seconds"),
                    "revocado": False,
                    "etiqueta": (data.get("etiqueta") or "")[:60],
                    "ve_otras": bool(data.get("ve_otras")),
                    "usos": 0,
                    "ultimo_uso": None,
                }
                with LOCK:
                    invites = load_invites(slug, vid)
                    invites.append(inv)
                    save_invites(slug, vid, invites)
                base = os.environ.get("MOCK_BASE_PUBLICA", "https://openframe.inspiredink.space")
                out = dict(inv)
                out["url"] = base + "/r/" + inv["token"]
                out["publicada"] = True
                return self.send_json(201, out)
        except Exception as exc:
            return self.send_json(500, {"error": "%s: %s" % (type(exc).__name__, exc)})
        return self.send_json(404, {"error": "no encontrado"})

    def do_PATCH(self):
        p = self.path.split("?", 1)[0]
        m = re.match(r"^/api/notas/([\w.-]+)/([\w.-]+)$", p)
        if not m:
            return self.send_json(404, {"error": "no encontrado"})
        slug, nid = m.group(1), m.group(2)
        data = self.jbody()
        notes = load_notes(slug)
        for note in notes:
            if note.get("id") == nid:
                for key in ("text", "drawing", "resolved", "kind", "visto", "resuelve"):
                    if key in data:
                        note[key] = data[key]
                save_notes(slug, notes)
                return self.send_json(200, {"ok": True, "nota": note})
        return self.send_json(404, {"error": "nota no encontrada"})

    def do_DELETE(self):
        p = self.path.split("?", 1)[0]
        m = re.match(r"^/api/proyectos/([\w.-]+)/videos/([\w.-]+)/invitar/([\w.-]+)$", p)
        if m:
            slug, vid, link_id = m.group(1), m.group(2), m.group(3)
            invites = load_invites(slug, vid)
            changed = False
            for inv in invites:
                if inv.get("id") == link_id:
                    inv["revocado"] = True
                    changed = True
            save_invites(slug, vid, invites)
            return self.send_json(200 if changed else 404, {"ok": changed})
        return self.send_json(404, {"error": "no encontrado"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--puerto", type=int, default=9397)
    parser.add_argument("--data", required=True)
    args = parser.parse_args()
    global DATA
    DATA = os.path.abspath(args.data)
    if os.path.exists(DATA):
        shutil.rmtree(DATA)
    os.makedirs(DATA, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", args.puerto), Handler)
    srv.daemon_threads = True
    print("mock api http://127.0.0.1:%d data=%s" % (args.puerto, DATA), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
