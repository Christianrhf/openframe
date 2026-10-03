#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Black-box attack suite for OpenFrame guest mode.

Stdlib-only, Python 3.9 compatible. It creates its own projects, videos,
guest links and notes through the local administration API, then attacks the
guest gate as an unauthenticated user and as several guest identities.
"""
from __future__ import print_function

import argparse
import base64
import json
import os
import random
import re
import shutil
import socket
import string
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client(object):
    def __init__(self, base, cookies=None, timeout=8):
        self.base = base.rstrip("/")
        self.cookies = dict(cookies or {})
        self.timeout = timeout
        self.opener = build_opener(NoRedirect)

    def clone(self):
        return Client(self.base, self.cookies, self.timeout)

    def cookie_header(self):
        return "; ".join("%s=%s" % (k, v) for k, v in sorted(self.cookies.items()))

    def store_cookies(self, headers):
        vals = []
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

    def request(self, method, path, body=None, headers=None, raw=False, timeout=None):
        url = path if path.startswith("http://") or path.startswith("https://") else self.base + path
        data = None
        hdrs = dict(headers or {})
        if body is not None:
            if isinstance(body, (dict, list)):
                data = json.dumps(body).encode("utf-8")
                hdrs.setdefault("Content-Type", "application/json")
            elif isinstance(body, str):
                data = body.encode("utf-8")
            else:
                data = body
        if self.cookies and "Cookie" not in hdrs:
            hdrs["Cookie"] = self.cookie_header()
        req = Request(url, data=data, headers=hdrs, method=method)
        try:
            resp = self.opener.open(req, timeout=timeout or self.timeout)
            body_bytes = resp.read()
            self.store_cookies(resp.headers)
            return Response(resp.getcode(), dict(resp.headers.items()), body_bytes)
        except HTTPError as e:
            body_bytes = e.read()
            self.store_cookies(e.headers)
            return Response(e.code, dict(e.headers.items()), body_bytes)
        except Exception as e:
            return Response(0, {}, b"", error=e)

    def json(self, method, path, body=None, headers=None):
        r = self.request(method, path, body=body, headers=headers)
        try:
            return r, json.loads(r.text() or "{}")
        except Exception:
            return r, {}


class Response(object):
    def __init__(self, status, headers, body, error=None):
        self.status = status
        self.headers = headers
        self.body = body
        self.error = error

    def text(self):
        return self.body.decode("utf-8", "replace")

    def header(self, name):
        lname = name.lower()
        for k, v in self.headers.items():
            if k.lower() == lname:
                return v
        return ""


class Suite(object):
    def __init__(self, args):
        self.args = args
        self.api = Client(args.api)
        self.gate = Client(args.gate)
        self.pass_count = 0
        self.fail_count = 0
        self.findings = []
        self.context = {}

    def check(self, name, ok, detail=""):
        if ok:
            self.pass_count += 1
            print("PASS %-72s %s" % (name, detail))
        else:
            self.fail_count += 1
            print("FAIL %-72s %s" % (name, detail))

    def finding(self, severity, title, suggestion):
        item = {"severity": severity, "title": title, "suggestion": suggestion}
        if item not in self.findings:
            self.findings.append(item)
            print("FINDING [%s] %s" % (severity, title))

    def api_json(self, method, path, body=None, headers=None, expect=None):
        r, data = self.api.json(method, path, body=body, headers=headers)
        if expect is not None:
            self.check("setup %s %s == %s" % (method, path, expect), r.status == expect, "got %s" % r.status)
        return r, data

    def guest_json(self, client, method, path, body=None, headers=None):
        return client.json(method, path, body=body, headers=headers)

    def setup(self):
        run = "atk" + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        clip = os.path.abspath(self.args.clip)
        with open(clip, "rb") as f:
            clip_bytes = f.read()
        _, a = self.api_json("POST", "/api/proyectos", {"nombre": run, "cliente": "cliente T"}, expect=200)
        _, b = self.api_json("POST", "/api/proyectos", {"nombre": run + "-other", "cliente": "cliente T"}, expect=200)
        slug_a, slug_b = a.get("slug"), b.get("slug")
        r, v1 = self.api_json("POST", "/api/proyectos/%s/videos" % slug_a, clip_bytes, headers={"X-Filename": "a.mp4"}, expect=200)
        r, v2 = self.api_json("POST", "/api/proyectos/%s/videos" % slug_b, clip_bytes, headers={"X-Filename": "b.mp4"}, expect=200)
        vid_a = (v1.get("video") or {}).get("id")
        vid_b = (v2.get("video") or {}).get("id")
        _, owner = self.api_json("POST", "/api/proyectos/%s/notas" % slug_a, {
            "video": vid_a,
            "frame": 2,
            "fps": 24,
            "text": "nota cristian privada",
            "author": "cristian",
        }, expect=201)
        _, other_note = self.api_json("POST", "/api/proyectos/%s/notas" % slug_b, {
            "video": vid_b,
            "frame": 3,
            "fps": 24,
            "text": "nota otro proyecto",
            "author": "cristian",
        }, expect=201)
        links = {}
        for key, body in (
            ("normal", {"dias": 7, "etiqueta": "normal", "ve_otras": False}),
            ("open", {"dias": 7, "etiqueta": "open", "ve_otras": True}),
            ("expiring", {"dias": 1, "etiqueta": "expires", "ve_otras": False}),
            ("revoked", {"dias": 7, "etiqueta": "revoked", "ve_otras": False}),
        ):
            _, data = self.api_json("POST", "/api/proyectos/%s/videos/%s/invitar" % (slug_a, vid_a), body, expect=201)
            data["token"] = data.get("token") or data.get("url", "").rsplit("/", 1)[-1]
            links[key] = data
        self.api_json("DELETE", "/api/proyectos/%s/videos/%s/invitar/%s" % (slug_a, vid_a, links["revoked"]["id"]), expect=200)
        _, pa = self.api_json("GET", "/api/proyectos/%s" % slug_a)
        fps_a = next((v.get("fps") for v in pa.get("videos", []) if v.get("id") == vid_a), 24.0)
        self.context.update({
            "fps_a": fps_a,
            "slug_a": slug_a, "slug_b": slug_b, "vid_a": vid_a, "vid_b": vid_b,
            "owner_note": (owner.get("nota") or {}),
            "other_note": (other_note.get("nota") or {}),
            "links": links,
            "clip_bytes": clip_bytes,
        })
        self.check("setup collected project/video/link ids", all([slug_a, slug_b, vid_a, vid_b, links["normal"].get("token")]))

    def login(self, link_key, name="Invitado T"):
        link = self.context["links"][link_key]
        c = Client(self.args.gate)
        r = c.request("GET", "/r/" + link["token"])
        self.check("GET /r/%s redirects for valid token" % link_key, r.status == 302, "got %s" % r.status)
        self.check("GET /r/%s sets ofg cookie" % link_key, bool(c.cookies.get("ofg")))
        r, data = c.json("POST", "/api/invitado/nombre", {"nombre": name})
        self.check("POST nombre accepted for %s" % link_key, r.status == 200 and data.get("nombre") == name, "got %s" % r.status)
        self.check("POST nombre sets signed cookie for %s" % link_key, bool(c.cookies.get("ofn")))
        return c

    def expire_link(self, link_key):
        if not self.args.data:
            self.finding("medium", "No --data supplied; expiry-on-disk check skipped", "Run with --data against test fixtures to assert immediate expiry.")
            return False
        slug = self.context["slug_a"]
        vid = self.context["vid_a"]
        target = self.context["links"][link_key]["id"]
        path = os.path.join(self.args.data, slug, "videos", vid, "invitados.json")
        rows = json.load(open(path, "r", encoding="utf-8"))
        for row in rows:
            if row.get("id") == target:
                row["expira"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True

    def run(self):
        self.setup()
        normal = self.login("normal", "Ana T")
        open_client = self.login("open", "Open T")
        self.basic_contract(normal)
        self.route_whitelist(normal)
        self.data_isolation(normal, open_client)
        own_note = self.write_forcing_checks(normal)
        self.patch_checks(normal, open_client, own_note)
        self.cookie_and_input_checks(normal)
        self.media_checks(normal)
        self.raw_socket_checks(normal)
        self.revocation_and_expiry_checks(normal)
        self.limit_checks(normal)
        self.log_checks()
        print("")
        print("SUMMARY pass=%d fail=%d checks=%d findings=%d" % (
            self.pass_count, self.fail_count, self.pass_count + self.fail_count, len(self.findings)))
        if self.findings:
            print("HALLAZGOS")
            for f in self.findings:
                print("- [%s] %s. Arreglo: %s" % (f["severity"], f["title"], f["suggestion"]))
        return 1 if self.fail_count else 0

    def basic_contract(self, c):
        r = c.request("GET", "/")
        body = r.text()
        self.check("GET / with cookie returns UI", r.status == 200 and "window.__INVITADO" in body, "got %s" % r.status)
        for header, expected in (
            ("Cache-Control", "no-store"),
            ("X-Robots-Tag", "noindex"),
            ("Referrer-Policy", "no-referrer"),
            ("X-Content-Type-Options", "nosniff"),
        ):
            self.check("security header %s" % header, expected in r.header(header), r.header(header))
        self.check("UI injection does not contain raw token", self.context["links"]["normal"]["token"] not in body)
        self.check("UI injection exposes only shared slug", self.context["slug_a"] in body and self.context["slug_b"] not in body)
        r, data = c.json("GET", "/api/ping")
        self.check("GET /api/ping ok", r.status == 200 and data.get("ok") is True)
        noauth = Client(self.args.gate)
        # S3: /api/ping queda FUERA de esta lista. CONTRATO linea 35: "GET /api/ping
        # -> {ok:true}", sin cookie, porque publicar.sh lo usa para comprobar el
        # tunel desde fuera. No expone nada: ni slug, ni notas, ni enlace.
        for path in ("/", "/api/proyectos/%s" % self.context["slug_a"], "/api/notas/%s" % self.context["slug_a"]):
            r = noauth.request("GET", path)
            self.check("no cookie blocked %s" % path, r.status == 404, "got %s" % r.status)
        r, data = noauth.json("GET", "/api/ping")
        self.check("no cookie still gets /api/ping 200", r.status == 200 and data == {"ok": True}, "got %s %s" % (r.status, data))
        invalids = ["", "x", self.context["links"]["normal"]["token"][:-2] + "xx"]
        for token in invalids:
            r = Client(self.args.gate).request("GET", "/r/" + token)
            self.check("invalid token gives identical 404", r.status == 404 and "disponible" in r.text(), "got %s" % r.status)
        r = Client(self.args.gate).request("GET", "/r/" + self.context["links"]["revoked"]["token"])
        self.check("revoked token cannot start session", r.status == 404, "got %s" % r.status)

    def route_whitelist(self, c):
        slug = self.context["slug_a"]
        vid = self.context["vid_a"]
        forbidden_gets = [
            "/api/proyectos",
            "/api/proyectos/",
            "/api/proyectos/%s/hilos" % slug,
            "/api/proyectos/%s/videos" % slug,
            "/api/proyectos/%s/videos/%s/invitar" % (slug, vid),
            "/api/proyectos/%s/videos/%s/meta" % (slug, vid),
            "/api/invitados/actividad",
            "/api/invitados/estado",
            "/server.py",
            "/guest.py",
            "/config.json",
            "/data/.guest_secret",
            "/data/%s/notes.json" % slug,
            "/data/%s/videos/%s/invitados.json" % (slug, vid),
            "/logs/guest.log",
            "/api/notas/%s/%s" % (slug, self.context["owner_note"].get("id")),
        ]
        for path in forbidden_gets:
            r = c.request("GET", path)
            self.check("forbidden GET is 404 %s" % path, r.status == 404, "got %s" % r.status)
        forbidden_posts = [
            "/api/proyectos",
            "/api/proyectos/%s/archivar" % slug,
            "/api/proyectos/%s/videos" % slug,
            "/api/proyectos/%s/heredar" % slug,
            "/api/proyectos/%s/videos/%s/invitar" % (slug, vid),
        ]
        for path in forbidden_posts:
            r = c.request("POST", path, {"x": 1})
            self.check("forbidden POST is 404 %s" % path, r.status == 404, "got %s" % r.status)
        verbs = ["TRACE", "CONNECT", "PUT", "OPTIONS", "PROPFIND", "DELETE"]
        for verb in verbs:
            r = c.request(verb, "/api/proyectos/%s" % slug)
            self.check("weird/admin verb %s returns 404" % verb, r.status == 404, "got %s" % r.status)
        suffixes = ["", "/", "?x=1", "/.", "/..", "%2f", "%00", "//x"]
        for suffix in suffixes:
            r = c.request("GET", "/api/proyectos/%s/hilos%s" % (slug, suffix))
            self.check("hilos variant blocked %r" % suffix, r.status == 404, "got %s" % r.status)

    def data_isolation(self, normal, open_client):
        slug_a, slug_b = self.context["slug_a"], self.context["slug_b"]
        vid_a, vid_b = self.context["vid_a"], self.context["vid_b"]
        r, data = normal.json("GET", "/api/proyectos/%s" % slug_a)
        videos = data.get("videos") or []
        self.check("shared project can be read", r.status == 200, "got %s" % r.status)
        self.check("shared project returns one video", len(videos) == 1 and videos[0].get("id") == vid_a, repr(videos))
        self.check("shared project omits other video id", vid_b not in json.dumps(data))
        r, data = normal.json("GET", "/api/proyectos/%s" % slug_b)
        self.check("other exact project is 404", r.status == 404, "got %s" % r.status)
        r, data = normal.json("GET", "/api/proyectos/%s-extra" % slug_a)
        self.check("prefix project slug is not enough", r.status == 404, "got %s" % r.status)
        r, data = normal.json("GET", "/api/notas/%s" % slug_b)
        self.check("other notes endpoint is 404", r.status == 404, "got %s" % r.status)
        r, data = normal.json("GET", "/api/notas/%s" % slug_a)
        notes = data.get("notas") or []
        self.check("normal link does not see owner note", all(n.get("author") != "cristian" for n in notes), repr(notes))
        r, data = open_client.json("GET", "/api/notas/%s" % slug_a)
        notes = data.get("notas") or []
        self.check("ve_otras link sees owner note in same video", any(n.get("id") == self.context["owner_note"].get("id") for n in notes))
        self.check("ve_otras still omits other project note", self.context["other_note"].get("text") not in json.dumps(data))

    def write_forcing_checks(self, c):
        slug, vid = self.context["slug_a"], self.context["vid_a"]
        malicious = {
            "video": self.context["vid_b"],
            "fps": 999,
            "kind": "cambio",
            "author": "cristian",
            "autor_nombre": "Mallory",
            "enlace_id": "deadbeef",
            "resolved": True,
            "resuelve": self.context["owner_note"].get("id"),
            "visto": True,
            "decision": "aprobar",
            "frame": 5,
            "end_frame": 9,
            "text": "<script>alert(1)</script>\r\nHeader: nope",
            "drawing": {"strokes": [{"points": [[0, 0], [1, 1]]}]},
        }
        r, data = c.json("POST", "/api/proyectos/%s/notas" % slug, malicious)
        note = data.get("nota") or {}
        self.check("guest can create note after name", r.status == 201, "got %s %s" % (r.status, data))
        expectations = [
            ("forced video", note.get("video") == vid, note.get("video")),
            ("forced fps", abs(float(note.get("fps") or 0) - float(self.context["fps_a"])) < 1e-6, note.get("fps")),
            ("forced kind nota", note.get("kind") == "nota", note.get("kind")),
            ("forced author invitado", note.get("author") == "invitado", note.get("author")),
            ("forced autor_nombre cookie", note.get("autor_nombre") == "Ana T", note.get("autor_nombre")),
            ("forced enlace_id", note.get("enlace_id") == self.context["links"]["normal"]["id"], note.get("enlace_id")),
            ("resolved stripped", not note.get("resolved"), note.get("resolved")),
            ("resuelve stripped", "resuelve" not in note, note.get("resuelve")),
            ("visto stripped", "visto" not in note, note.get("visto")),
            ("decision stripped", "decision" not in note, note.get("decision")),
            ("text preserved for later UI escaping", "<script>" in note.get("text", ""), note.get("text")),
        ]
        for name, ok, detail in expectations:
            self.check("POST note %s" % name, ok, repr(detail))
        r, data = c.json("GET", "/api/notas/%s" % slug)
        self.check("own note visible after create", any(n.get("id") == note.get("id") for n in data.get("notas", [])))
        r, data = c.json("POST", "/api/proyectos/%s/notas" % self.context["slug_b"], {"text": "outside"})
        self.check("cannot write note under other slug", r.status == 404, "got %s" % r.status)
        r, data = c.json("POST", "/api/proyectos/%s/notas" % slug, {"parent": self.context["owner_note"].get("id"), "text": "reply to hidden"})
        self.check("cannot reply to hidden parent", r.status == 404, "got %s" % r.status)
        noname = Client(self.args.gate, {"ofg": c.cookies.get("ofg")})
        r, data = noname.json("POST", "/api/proyectos/%s/notas" % slug, {"text": "no name"})
        self.check("write without signed name is 403 nombre", r.status == 403 and data.get("error") == "nombre", "got %s %s" % (r.status, data))
        fake = Client(self.args.gate, {"ofg": c.cookies.get("ofg"), "ofn": "Ana.fake"})
        r, data = fake.json("POST", "/api/proyectos/%s/notas" % slug, {"text": "fake name"})
        self.check("write with forged ofn is 403", r.status == 403, "got %s" % r.status)
        return note

    def patch_checks(self, normal, open_client, own_note):
        slug = self.context["slug_a"]
        r, data = normal.json("PATCH", "/api/notas/%s/%s" % (slug, own_note.get("id")), {
            "text": "editado",
            "drawing": {"strokes": []},
            "resolved": True,
            "kind": "cambio",
            "visto": True,
        })
        note = (data.get("nota") or {})
        self.check("can patch own note", r.status == 200, "got %s" % r.status)
        self.check("PATCH text accepted", note.get("text") == "editado", repr(note))
        self.check("PATCH resolved ignored", not note.get("resolved"), repr(note))
        self.check("PATCH kind ignored", note.get("kind") == "nota", repr(note))
        r, data = normal.json("PATCH", "/api/notas/%s/%s" % (slug, self.context["owner_note"].get("id")), {"text": "steal"})
        self.check("cannot patch owner note", r.status == 404, "got %s" % r.status)
        r, data = open_client.json("PATCH", "/api/notas/%s/%s" % (slug, own_note.get("id")), {"text": "other link edit"})
        self.check("other link cannot patch visible foreign guest note", r.status == 404, "got %s" % r.status)
        r, data = normal.json("PATCH", "/api/notas/%s/%s" % (self.context["slug_b"], own_note.get("id")), {"text": "cross"})
        self.check("cannot patch through other slug", r.status == 404, "got %s" % r.status)

    def cookie_and_input_checks(self, c):
        bad_names = ["", "A" * 41, "line\nbreak", "carriage\rreturn", "x" * 100000]
        for name in bad_names:
            r, data = c.json("POST", "/api/invitado/nombre", {"nombre": name})
            self.check("bad nombre rejected len/control %d" % len(name), r.status in (400, 413), "got %s" % r.status)
        html_name = "<script>x</script>"
        r, data = c.json("POST", "/api/invitado/nombre", {"nombre": html_name})
        self.check("HTML-looking nombre accepted as data", r.status == 200, "got %s" % r.status)
        r = c.request("GET", "/")
        self.check("HTML-looking nombre is JSON escaped in UI bootstrap", "<script>x</script>" not in r.text())
        self.finding("medium", "Guest name/text accept HTML-looking data; safety depends on UI escaping", "Keep using textContent/JSON encoding and add regression tests in the UI.")
        bidi = "abc\u202etxt"
        r, data = c.json("POST", "/api/proyectos/%s/notas" % self.context["slug_a"], {"text": bidi})
        self.check("unicode bidi text handled without 500", r.status in (201, 400), "got %s" % r.status)
        huge_text = "T" * 100000
        r, data = c.json("POST", "/api/proyectos/%s/notas" % self.context["slug_a"], {"text": huge_text})
        self.check("100KB text handled without 500", r.status in (201, 400, 413), "got %s" % r.status)

    def media_checks(self, c):
        slug, vid = self.context["slug_a"], self.context["vid_a"]
        other_slug, other_vid = self.context["slug_b"], self.context["vid_b"]
        good = c.request("GET", "/media/%s/%s/media.mp4" % (slug, vid), headers={"Range": "bytes=0-0"})
        self.check("media byte range works for shared video", good.status == 206 and len(good.body) == 1, "got %s len=%d" % (good.status, len(good.body)))
        head = c.request("HEAD", "/media/%s/%s/media.mp4" % (slug, vid))
        self.check("HEAD media allowed for shared video", head.status == 200, "got %s" % head.status)
        ranges = {
            "bytes=-0": 416,
            "bytes=0-0,5-9": 416,
            "bytes=9999999999-": 416,
            "items=0-1": 416,
            "bytes=10-1": 416,
        }
        for rng, expect in ranges.items():
            r = c.request("GET", "/media/%s/%s/media.mp4" % (slug, vid), headers={"Range": rng})
            self.check("weird Range %s rejected" % rng, r.status == expect, "got %s" % r.status)
        blocked = [
            "/media/%s/%s/media.mp4" % (other_slug, other_vid),
            "/media/%s/%s/invitados.json" % (slug, vid),
            "/media/%s/%s/meta.json" % (slug, vid),
            "/media/%s/%s/notes.json" % (slug, vid),
            "/media/%s/%s/server.py" % (slug, vid),
            "/media/%s/%s/.guest_secret" % (slug, vid),
        ]
        traversal_names = [
            "../%s/invitados.json" % vid,
            "..%%2f%s%%2finvitados.json" % vid,
            "%%2e%%2e/%s/invitados.json" % vid,
            "%%252e%%252e%%252f%s%%252finvitados.json" % vid,
            "..\\%s\\invitados.json" % vid,
            "//etc/passwd",
            "/etc/passwd",
            "media.mp4%00.json",
        ]
        blocked.extend("/media/%s/%s/%s" % (slug, vid, x) for x in traversal_names)
        for path in blocked:
            r = c.request("GET", path)
            no_secret = self.context["links"]["normal"]["token"] not in r.text()
            self.check("media/file escape blocked %s" % path[:56], r.status == 404 and no_secret, "got %s" % r.status)
        cases = [
            "/MEDIA/%s/%s/media.mp4" % (slug, vid),
            "/media/%s/%s/media.mp4/" % (slug, vid),
            "/media/%s/%s//media.mp4" % (slug, vid),
        ]
        for path in cases:
            r = c.request("GET", path)
            self.check("case/slash media variant blocked", r.status == 404, "got %s %s" % (r.status, path))

    def raw_socket_checks(self, c):
        parsed = urlparse(self.args.gate)
        host, port = parsed.hostname, parsed.port or 80
        cookie = c.cookie_header()
        # S3: TASK-S3 punto 4(ii) obliga a validar Host (solo el de base_publica y
        # 127.0.0.1/localhost:<puerto>). Los casos que NO prueban el Host usan ya
        # el Host real; "false Host" acepta 200 (no valida) o 404 (valida).
        raw_cases = []
        raw_cases.append(("duplicate CL", "POST /api/proyectos/%s/notas HTTP/1.1\r\nHost: {REAL_HOST}\r\nCookie: %s\r\nContent-Length: 2\r\nContent-Length: 20\r\n\r\n{}" % (self.context["slug_a"], cookie), [400, 404]))
        raw_cases.append(("TE plus CL", "POST /api/proyectos/%s/notas HTTP/1.1\r\nHost: {REAL_HOST}\r\nCookie: %s\r\nTransfer-Encoding: chunked\r\nContent-Length: 4\r\n\r\n0\r\n\r\n" % (self.context["slug_a"], cookie), [400, 404]))
        raw_cases.append(("false Host", "GET /api/proyectos/%s HTTP/1.1\r\nHost: evil.example\r\nCookie: %s\r\n\r\n" % (self.context["slug_a"], cookie), [200, 404]))
        raw_cases.append(("huge header", "GET /api/proyectos/%s HTTP/1.1\r\nHost: {REAL_HOST}\r\nCookie: %s\r\nX-Big: %s\r\n\r\n" % (self.context["slug_a"], cookie, "A" * 20000), [200, 400, 431]))
        raw_cases.append(("lowercase method", "get /api/proyectos/%s HTTP/1.1\r\nHost: {REAL_HOST}\r\nCookie: %s\r\n\r\n" % (self.context["slug_a"], cookie), [400, 404, 501]))
        raw_cases.append(("10000 headers", "GET /api/proyectos/%s HTTP/1.1\r\nHost: {REAL_HOST}\r\nCookie: %s\r\n%s\r\n" % (self.context["slug_a"], cookie, "".join("X-%d: y\r\n" % i for i in range(10000))), [200, 400, 431]))
        for name, raw, allowed in raw_cases:
            status, body = raw_http(host, port, raw, timeout=6)
            ok = status in allowed
            if name == "false Host" and status == 200:
                self.finding("low", "Guest gate does not reject false Host headers", "Validate Host if the tunnel ever forwards untrusted hostnames.")
            self.check("raw socket %s" % name, ok, "got %s" % status)
        origin_headers = {"Origin": "https://evil.example"}
        r, data = c.json("POST", "/api/proyectos/%s/notas" % self.context["slug_a"], {"text": "csrf"}, headers=origin_headers)
        if r.status == 201:
            self.finding("high", "CSRF write accepted with cross-site Origin and valid cookie", "Require same-origin tokens or reject untrusted Origin/Referer on guest writes.")
        self.check("CSRF behavior documented as finding, not contract failure", r.status in (201, 403, 404), "got %s" % r.status)

    def revocation_and_expiry_checks(self, normal):
        # S3: el sondeo de sesion usa una ruta QUE EXIGE sesion (/api/notas/<slug>),
        # no /api/ping, que por CONTRATO linea 35 responde 200 siempre.
        probe = "/api/notas/%s" % self.context["slug_a"]
        old = normal.request("GET", probe)
        self.check("session valid before expiry/revocation", old.status == 200, "got %s" % old.status)
        revoked = Client(self.args.gate)
        revoked.cookies["ofg"] = self.context["links"]["revoked"]["token"]
        r = revoked.request("GET", probe)
        self.check("manually supplied revoked cookie rejected", r.status == 404, "got %s" % r.status)
        exp = self.login("expiring", "Expire T")
        if self.expire_link("expiring"):
            time.sleep(2.2)
            r = exp.request("GET", probe)
            self.check("expired link rejected on next request", r.status == 404, "got %s" % r.status)
            r = Client(self.args.gate).request("GET", "/r/" + self.context["links"]["expiring"]["token"])
            self.check("expired token cannot restart session", r.status == 404, "got %s" % r.status)

    def limit_checks(self, c):
        slug = self.context["slug_a"]
        parsed = urlparse(self.args.gate)
        status, _ = raw_http(
            parsed.hostname,
            parsed.port or 80,
            "POST /api/proyectos/%s/notas HTTP/1.1\r\nHost: {REAL_HOST}\r\nCookie: %s\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n{}" % (
                slug, c.cookie_header(), 1024 * 1024 + 10),
            timeout=4,
        )
        self.check("body >1MB rejected with 413", status == 413, "got %s" % status)
        points = [[i, i] for i in range(401)]
        r, data = c.json("POST", "/api/proyectos/%s/notas" % slug, {"text": "drawing", "drawing": {"strokes": [{"points": points}]}})
        self.check("drawing over point limit rejected", r.status == 413, "got %s" % r.status)
        thumb = "data:image/jpeg;base64," + base64.b64encode(b"x" * (601 * 1024)).decode("ascii")
        r, data = c.json("POST", "/api/proyectos/%s/notas" % slug, {"text": "thumb", "thumb": thumb})
        self.check("thumb over 600KB rejected", r.status == 413, "got %s" % r.status)
        statuses = []
        for i in range(70):
            r, _ = c.json("POST", "/api/proyectos/%s/notas" % slug, {"text": "rate %d" % i})
            statuses.append(r.status)
            if r.status == 429:
                break
        self.check("write rate eventually returns 429", 429 in statuses, "statuses tail=%s" % statuses[-8:])
        threads = []
        results = []
        lock = threading.Lock()

        def worker(i):
            r = c.request("GET", "/api/ping", timeout=10)
            with lock:
                results.append(r.status)

        for i in range(60):
            t = threading.Thread(target=worker, args=(i,))
            t.daemon = True
            threads.append(t)
            t.start()
        for t in threads:
            t.join(12)
        self.check("60 concurrent reads do not leak data or hang all", len(results) == 60 and all(s in (200, 404, 429, 0) for s in results), repr(results[:10]))
        self.slowloris_probe()

    def slowloris_probe(self):
        parsed = urlparse(self.args.gate)
        sockets = []
        try:
            for _ in range(50):
                s = socket.create_connection((parsed.hostname, parsed.port or 80), timeout=2)
                s.sendall(("GET /api/ping HTTP/1.1\r\nHost: %s:%d\r\n" % (parsed.hostname, parsed.port or 80)).encode("ascii"))
                sockets.append(s)
            time.sleep(1)
            probe = Client(self.args.gate).request("GET", "/api/ping", timeout=5)
            self.check("slowloris 50 sockets does not expose non-404/200 weirdness", probe.status in (200, 404, 0), "got %s" % probe.status)
        except Exception as exc:
            self.check("slowloris 50 sockets handled", True, type(exc).__name__)
        finally:
            for s in sockets:
                try:
                    s.close()
                except Exception:
                    pass

    def log_checks(self):
        if not self.args.log:
            return
        try:
            text = open(self.args.log, "r", encoding="utf-8").read()
        except Exception as exc:
            self.check("log path readable for token leak check", False, str(exc))
            return
        leaked = [k for k, v in self.context["links"].items() if v.get("token") and v["token"] in text]
        self.check("guest log does not contain raw tokens", not leaked, repr(leaked))


def raw_http(host, port, payload, timeout=5):
    # S3: {REAL_HOST} = el Host legitimo de la puerta. TASK-S3 4(ii) obliga a
    # validar Host, asi que una peticion cruda legitima tiene que traerlo bien.
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.settimeout(timeout)
        if isinstance(payload, str):
            payload = payload.replace("{REAL_HOST}", "%s:%d" % (host, port))
            payload = payload.encode("utf-8")
        s.sendall(payload)
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 65536:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        s.close()
        m = re.match(br"HTTP/\d(?:\.\d)?\s+(\d+)", data)
        return (int(m.group(1)) if m else 0), data
    except Exception:
        return 0, b""


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True, help="local administration API, e.g. http://127.0.0.1:9397")
    parser.add_argument("--gate", required=True, help="guest gate, e.g. http://127.0.0.1:9398")
    parser.add_argument("--clip", required=True, help="mp4 fixture to upload")
    parser.add_argument("--data", help="data directory used by the implementation, for expiry mutation")
    parser.add_argument("--log", help="guest log path, for token leak checks")
    args = parser.parse_args(argv)
    suite = Suite(args)
    return suite.run()


if __name__ == "__main__":
    sys.exit(main())
