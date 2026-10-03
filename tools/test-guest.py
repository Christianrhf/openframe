#!/usr/bin/env python3
"""Suite adversaria autocontenida para guest.py (stdlib, puertos S3 9381/9382)."""
import base64
import concurrent.futures
import datetime
import http.client
import json
import os
import random
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.parse
import uuid


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PORT = 9381
GUEST_PORT = 9382
SERVER = ("127.0.0.1", SERVER_PORT)
GUEST = ("127.0.0.1", GUEST_PORT)
PROCS = []
CHECKS = 0
FAILS = []
GUEST_BODIES = []


def check(condition, label):
    global CHECKS
    CHECKS += 1
    if not condition:
        FAILS.append(label)
        print("FAIL %03d %s" % (CHECKS, label))


def request(target, method, path, body=None, headers=None, guest=False, timeout=15):
    host, port = target
    headers = dict(headers or {})
    if isinstance(body, (dict, list)):
        body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    elif isinstance(body, str):
        body = body.encode("utf-8")
    if body is not None:
        headers.setdefault("Content-Length", str(len(body)))
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        result = (resp.status, dict(resp.getheaders()), raw)
        if guest:
            GUEST_BODIES.append(raw)
        return result
    finally:
        conn.close()


def raw_status(payload):
    """Peticion cruda por socket: sirve para cabeceras que http.client no deja
    construir (dos Content-Length, Transfer-Encoding a mano)."""
    try:
        sock = socket.create_connection(GUEST, timeout=6)
    except OSError:
        return 0
    try:
        sock.settimeout(6)
        sock.sendall(payload.encode("utf-8"))
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    except OSError:
        return 0
    finally:
        sock.close()
    head = data.split(b"\r\n", 1)[0].split(b" ")
    return int(head[1]) if len(head) > 1 and head[1].isdigit() else 0


def jrequest(target, method, path, value=None, headers=None, guest=False):
    status, hs, raw = request(target, method, path, value, headers, guest)
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = None
    return status, hs, data, raw


def declared_large(path, cookie):
    conn = http.client.HTTPConnection(GUEST[0], GUEST[1], timeout=15)
    try:
        conn.putrequest("POST", path)
        conn.putheader("Cookie", cookie)
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(1024 * 1024 + 1))
        conn.endheaders()
        resp = conn.getresponse()
        raw = resp.read()
        GUEST_BODIES.append(raw)
        return resp.status, dict(resp.getheaders()), raw
    finally:
        conn.close()


def ping(target):
    try:
        return request(target, "GET", "/api/ping", timeout=1)[0] == 200
    except Exception:
        return False


def wait_for(target):
    for _ in range(80):
        if ping(target):
            return
        time.sleep(0.1)
    raise RuntimeError("no arranco %s:%d" % target)


def start_servers():
    env = dict(os.environ)
    env["OPENFRAME_NO_PUBLICAR"] = "1"
    if not ping(SERVER):
        PROCS.append(subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "server.py"), "--puerto", str(SERVER_PORT)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        wait_for(SERVER)
    if not ping(GUEST):
        PROCS.append(subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "guest.py"), "--puerto", str(GUEST_PORT),
             "--api", "http://127.0.0.1:%d" % SERVER_PORT],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        wait_for(GUEST)


def stop_servers():
    for proc in reversed(PROCS):
        proc.terminate()
    for proc in reversed(PROCS):
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()


def cookie_value(header, key):
    if not header:
        return None
    first = header.split(";", 1)[0]
    if not first.startswith(key + "="):
        return None
    return first


def create_project(name, client):
    status, _hs, data, _raw = jrequest(
        SERVER, "POST", "/api/proyectos", {"nombre": name, "cliente": client})
    check(status == 200 and data and data.get("slug"), "crear proyecto " + name)
    return data["slug"]


def upload(slug, filename):
    with open(os.path.join(ROOT, "clip.mp4"), "rb") as f:
        raw = f.read()
    status, _hs, data, _body = jrequest(
        SERVER, "POST", "/api/proyectos/%s/videos" % slug, raw,
        {"X-Filename": filename, "Content-Type": "application/octet-stream"})
    check(status == 200 and data and data.get("video", {}).get("id"), "subir " + filename)
    return data["video"]


def invite(slug, vid, label="QA", other=False):
    status, _hs, data, _raw = jrequest(
        SERVER, "POST", "/api/proyectos/%s/videos/%s/invitar" % (slug, vid),
        {"dias": 7, "etiqueta": label, "ve_otras": other})
    check(status == 201 and data and data.get("token"), "crear enlace " + label)
    return data


def enter(token):
    status, hs, _raw = request(GUEST, "GET", "/r/" + token, guest=True)
    return status, hs, cookie_value(hs.get("Set-Cookie"), "ofg")


def set_name(ofg, name):
    status, hs, data, _raw = jrequest(
        GUEST, "POST", "/api/invitado/nombre", {"nombre": name},
        {"Cookie": ofg}, guest=True)
    return status, hs, data, cookie_value(hs.get("Set-Cookie"), "ofn")


def auth(ofg, ofn=None):
    return {"Cookie": ofg + (("; " + ofn) if ofn else "")}


def expire_link(slug, vid, link_id):
    path = os.path.join(ROOT, "data", slug, "videos", vid, "invitados.json")
    with open(path, "r", encoding="utf-8") as f:
        links = json.load(f)
    for link in links:
        if link.get("id") == link_id:
            link["expira"] = "2000-01-01T00:00:00+00:00"
    tmp = path + ".testtmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(links, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def main():
    start_servers()
    suffix = uuid.uuid4().hex[:7]
    slug = create_project("zz-guest-" + suffix, "Cliente A")
    video = upload(slug, "clip.mp4")
    other_video = upload(slug, "otro-corte.mp4")
    other_slug = create_project("zz-privado-" + suffix, "Cliente Secreto")
    secret_video = upload(other_slug, "secreto.mp4")

    main_link = invite(slug, video["id"], "Principal")
    peer_link = invite(slug, video["id"], "Otro invitado")
    other_video_link = invite(slug, other_video["id"], "Otro video")
    expired = invite(slug, video["id"], "Caducado")
    revoked = invite(slug, video["id"], "Revocado")
    expire_link(slug, video["id"], expired["id"])
    status, _hs, _data, expired_body = jrequest(
        GUEST, "GET", "/r/" + expired["token"], guest=True)
    check(status == 404, "token caducado devuelve 404")
    status, _hs, _data, _raw = jrequest(
        SERVER, "DELETE", "/api/proyectos/%s/videos/%s/invitar/%s" %
        (slug, video["id"], revoked["id"]))
    check(status == 200, "revocar por API")
    status, _hs, revoked_body = request(GUEST, "GET", "/r/" + revoked["token"], guest=True)
    check(status == 404 and revoked_body == expired_body, "revocado indistinguible de caducado")
    status, _hs, invalid_body = request(GUEST, "GET", "/r/" + "x" * 43, guest=True)
    check(status == 404 and invalid_body == expired_body, "token invalido indistinguible")
    status, _hs, short_body = request(GUEST, "GET", "/r/" + main_link["token"][:-1], guest=True)
    check(status == 404 and short_body == expired_body, "token truncado indistinguible")

    status, hs, ofg = enter(main_link["token"])
    check(status == 302 and hs.get("Location") == "/", "token valido redirige")
    flags = hs.get("Set-Cookie", "")
    check(all(x in flags for x in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=")),
          "cookie ofg tiene todas las banderas")
    check(ofg == "ofg=" + main_link["token"], "cookie ofg contiene identidad")
    status, root_headers, root_body = request(GUEST, "GET", "/", headers=auth(ofg), guest=True)
    check(status == 200 and b"window.__INVITADO" in root_body, "raiz inyecta modo invitado")
    check(main_link["token"].encode() not in root_body, "raiz no filtra token")
    check(root_headers.get("Cache-Control") == "no-store", "raiz sin cache")
    check(root_headers.get("X-Robots-Tag") == "noindex, nofollow", "raiz no indexable")
    check(root_headers.get("Referrer-Policy") == "no-referrer", "raiz sin referrer")
    check(root_headers.get("X-Content-Type-Options") == "nosniff", "raiz nosniff")

    note_path = "/api/proyectos/%s/notas" % slug
    status, _hs, data, _raw = jrequest(
        GUEST, "POST", note_path, {"frame": 2, "text": "sin nombre"}, auth(ofg), guest=True)
    check(status == 403 and data.get("error") == "nombre", "nota sin nombre devuelve 403")
    status, name_headers, data, ofn = set_name(ofg, "Ana")
    check(status == 200 and data.get("nombre") == "Ana" and ofn, "guardar nombre")
    name_flags = name_headers.get("Set-Cookie", "")
    check(all(x in name_flags for x in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/")),
          "cookie ofn protegida")
    bad_ofn = ofn[:-1] + ("0" if ofn[-1] != "0" else "1")
    status, _hs, data, _raw = jrequest(
        GUEST, "POST", note_path, {"frame": 2, "text": "firma rota"}, auth(ofg, bad_ofn), guest=True)
    check(status == 403 and data.get("error") == "nombre", "ofn manipulada rechazada")

    malicious = {
        "video": secret_video["id"], "fps": 999, "frame": 3, "end_frame": 5,
        "text": "Nota de Ana", "author": "cristian", "resolved": True,
        "kind": "cambio", "visto": True, "resuelve": "fantasma",
        "drawing": {"strokes": [{"tool": "pen", "pts": [{"x": .1, "y": .2}, {"x": .2, "y": .3}]}]},
    }
    status, _hs, data, _raw = jrequest(
        GUEST, "POST", note_path, malicious, auth(ofg, ofn), guest=True)
    own = (data or {}).get("nota", {})
    check(status == 201 and own.get("id"), "crear nota invitada")
    check(own.get("video") == video["id"], "video forzado al compartido")
    check(abs(float(own.get("fps")) - float(video["fps"])) < .001, "fps forzado al video")
    check(own.get("author") == "invitado", "author forzado")
    check(own.get("autor_nombre") == "Ana" and own.get("enlace_id") == main_link["id"],
          "identidad y enlace guardados")
    check(own.get("kind") == "nota" and not own.get("resolved"), "kind/resolved forzados")
    check(not own.get("visto") and not own.get("resuelve"), "visto/resuelve descartados")
    own_id = own["id"]

    # Un POST local normal no puede falsificar la insignia de invitado.
    status, _hs, data, _raw = jrequest(
        SERVER, "POST", note_path,
        {"video": video["id"], "frame": 4, "text": "intento local",
         "author": "invitado", "autor_nombre": "Mallory", "enlace_id": main_link["id"]})
    forged = (data or {}).get("nota", {})
    check(status == 201 and forged.get("author") == "cristian", "server bloquea author invitado falso")
    check("autor_nombre" not in forged and "enlace_id" not in forged, "server ignora campos invitados falsos")

    # Otro invitado deja una nota; el enlace principal no debe verla.
    status, _hs, peer_ofg = enter(peer_link["token"])
    check(status == 302 and peer_ofg, "entra segundo invitado")
    status, _hs, _data, peer_ofn = set_name(peer_ofg, "Beto")
    check(status == 200 and peer_ofn, "nombre segundo invitado")
    status, _hs, data, _raw = jrequest(
        GUEST, "POST", note_path, {"frame": 7, "text": "Nota de Beto"},
        auth(peer_ofg, peer_ofn), guest=True)
    peer_id = data.get("nota", {}).get("id") if data else None
    check(status == 201 and peer_id, "nota segundo invitado")
    # Cristian responde a la nota propia de Ana: esa respuesta si es visible.
    status, _hs, data, _raw = jrequest(
        SERVER, "POST", note_path, {"parent": own_id, "text": "Respuesta de Cristian"})
    reply_id = data.get("nota", {}).get("id") if data else None
    check(status == 201 and reply_id, "respuesta local a invitado")
    status, _hs, data, _raw = jrequest(
        GUEST, "GET", "/api/notas/%s" % slug, headers=auth(ofg, ofn), guest=True)
    visible_ids = {n.get("id") for n in (data or {}).get("notas", [])}
    check(status == 200 and own_id in visible_ids, "invitado ve nota propia")
    check(reply_id in visible_ids, "invitado ve respuesta a nota propia")
    check(peer_id not in visible_ids and forged.get("id") not in visible_ids, "invitado no ve notas ajenas")
    check(all(n.get("video") == video["id"] for n in data.get("notas", [])), "notas solo del video")

    status, _hs, project_data, _raw = jrequest(
        GUEST, "GET", "/api/proyectos/%s" % slug, headers=auth(ofg, ofn), guest=True)
    check(status == 200 and [v.get("id") for v in project_data.get("videos", [])] == [video["id"]],
          "proyecto filtra otros videos")
    check(peer_id not in {n.get("id") for n in project_data.get("notas", [])},
          "proyecto filtra notas ajenas")
    status, _hs, _raw = request(
        GUEST, "GET", "/api/proyectos/%s" % other_slug, headers=auth(ofg, ofn), guest=True)
    check(status == 404, "otro proyecto devuelve 404")
    status, _hs, _data, _raw = jrequest(
        GUEST, "POST", note_path, {"frame": 8, "text": "respuesta ajena", "parent": peer_id},
        auth(ofg, ofn), guest=True)
    check(status == 404, "parent invisible devuelve 404")

    status, _hs, data, _raw = jrequest(
        GUEST, "PATCH", "/api/notas/%s/%s" % (slug, own_id),
        {"text": "Texto editado"}, auth(ofg, ofn), guest=True)
    check(status == 200 and data.get("nota", {}).get("text") == "Texto editado", "PATCH texto propio")
    status, _hs, data, _raw = jrequest(
        GUEST, "PATCH", "/api/notas/%s/%s" % (slug, own_id),
        {"drawing": {"strokes": []}}, auth(ofg, ofn), guest=True)
    check(status == 200, "PATCH dibujo propio")
    status, _hs, _data, _raw = jrequest(
        GUEST, "PATCH", "/api/notas/%s/%s" % (slug, peer_id),
        {"text": "robo"}, auth(ofg, ofn), guest=True)
    check(status == 404, "PATCH nota ajena devuelve 404")
    status, _hs, _raw = request(
        GUEST, "DELETE", "/api/notas/%s/%s" % (slug, own_id),
        headers=auth(ofg, ofn), guest=True)
    check(status == 404, "DELETE incluso propia devuelve 404")
    status, _hs, _data, _raw = jrequest(
        GUEST, "PATCH", "/api/notas/%s/%s" % (slug, own_id),
        {"resolved": True}, auth(ofg, ofn), guest=True)
    check(status == 404, "PATCH campo prohibido devuelve 404")

    # S3: pasarse de un TOPE es 413, no 400 (400 queda para la forma invalida).
    too_many = {"strokes": [{"pts": [{"x": .1, "y": .2}] * 401}]}
    status, _hs, _data, _raw = jrequest(
        GUEST, "POST", note_path, {"frame": 1, "drawing": too_many}, auth(ofg, ofn), guest=True)
    check(status == 413, "mas de 400 puntos rechazados")
    status, _hs, _data, _raw = jrequest(
        GUEST, "POST", note_path,
        {"frame": 1, "drawing": {"strokes": [{"pts": [[.1, .2], [.3, .4]]}]}},
        auth(ofg, ofn), guest=True)
    check(status == 201, "dibujo con puntos [x,y] normalizado y aceptado")
    status, _hs, _data, _raw = jrequest(
        GUEST, "POST", note_path,
        {"frame": 1, "drawing": {"strokes": [{"pts": [{"x": 2, "y": 0}]}]}},
        auth(ofg, ofn), guest=True)
    check(status == 400, "punto fuera de 0..1 rechazado")
    # S3: base64 VALIDO de mas de 600 KB: antes el relleno "YQ==" repetido se
    # rechazaba por forma y el tope de tamano no se probaba de verdad.
    huge_thumb = "data:image/jpeg;base64," + base64.b64encode(b"x" * (601 * 1024)).decode("ascii")
    status, _hs, _data, _raw = jrequest(
        GUEST, "POST", note_path, {"frame": 1, "thumb": huge_thumb}, auth(ofg, ofn), guest=True)
    check(status == 413, "thumb mayor de 600 KB rechazado")
    ok_thumb = "data:image/jpeg;base64," + base64.b64encode(b"x" * 1024).decode("ascii")
    status, _hs, _data, _raw = jrequest(
        GUEST, "POST", note_path, {"frame": 1, "thumb": ok_thumb}, auth(ofg, ofn), guest=True)
    check(status == 201, "thumb pequeno aceptado")
    status, _hs, _raw = declared_large(note_path, ofg + "; " + ofn)
    check(status == 413, "cuerpo mayor de 1 MB devuelve 413")

    media_path = "/media/%s/%s/%s" % (slug, video["id"], video["archivo"])
    status, hs, raw = request(GUEST, "GET", media_path, headers=auth(ofg, ofn), guest=True)
    check(status == 200 and len(raw) == video["bytes"], "media completa")
    check(hs.get("Accept-Ranges") == "bytes", "media anuncia Range")
    status, hs, raw = request(
        GUEST, "GET", media_path, headers=dict(auth(ofg, ofn), Range="bytes=10-29"), guest=True)
    check(status == 206 and len(raw) == 20 and hs.get("Content-Range", "").startswith("bytes 10-29/"),
          "Range valido 206")
    status, hs, raw = request(
        GUEST, "GET", media_path, headers=dict(auth(ofg, ofn), Range="bytes=999999-1000000"), guest=True)
    check(status == 416 and hs.get("Content-Range", "").startswith("bytes */"), "Range invalido 416")
    status, hs, raw = request(GUEST, "HEAD", media_path, headers=auth(ofg, ofn), guest=True)
    check(status == 200 and raw == b"" and int(hs.get("Content-Length")) == video["bytes"], "HEAD media")
    status, _hs, _raw = request(
        GUEST, "GET", "/media/%s/%s/%s" % (slug, other_video["id"], other_video["archivo"]),
        headers=auth(ofg, ofn), guest=True)
    check(status == 404, "media de otro video bloqueada")
    status, _hs, other_ofg = enter(other_video_link["token"])
    check(status == 302 and other_ofg, "token de otro video abre solo su sesion")
    status, _hs, _raw = request(GUEST, "GET", media_path, headers=auth(other_ofg), guest=True)
    check(status == 404, "token de otro video no abre media principal")

    attacks = [
        "/media/%s/%s/invitados.json" % (slug, video["id"]),
        "/media/%s/%s/meta.json" % (slug, video["id"]),
        "/media/%s/%s/notes.json" % (slug, video["id"]),
        "/media/%s/%s/.guest_secret" % (slug, video["id"]),
        "/media/%s/%s/../invitados.json" % (slug, video["id"]),
        "/media/%s/%s/%%2e%%2e/notes.json" % (slug, video["id"]),
        "/media/%s/%s/%%252e%%252e%%252fnotes.json" % (slug, video["id"]),
        "/media/%s/%s/..\\notes.json" % (slug, video["id"]),
        "/media/%s/%s/%%00.mp4" % (slug, video["id"]),
        "/server.py", "/data/.guest_secret", "/data/%s/notes.json" % slug,
        "//media/%s/%s/%s" % (slug, video["id"], video["archivo"]),
    ]
    for attack in attacks:
        status, _hs, _raw = request(GUEST, "GET", attack, headers=auth(ofg, ofn), guest=True)
        check(status == 404, "bloquea fuga " + attack[:55])
    server_attacks = [
        "/media/%s/%s/invitados.json" % (slug, video["id"]),
        "/media/%s/%s/meta.json" % (slug, video["id"]),
        "/media/%s/%s/../../../../.guest_secret" % (slug, video["id"]),
        "/media/%s/%s/../../notes.json" % (slug, video["id"]),
    ]
    for attack in server_attacks:
        status, _hs, _raw = request(SERVER, "GET", attack)
        check(status != 200, "server local no sirve secreto " + attack[-30:])

    admin_paths = [
        "/api/proyectos/%s/videos/%s/invitar" % (slug, video["id"]),
        "/api/invitados/actividad?desde=2000-01-01T00:00:00Z",
        "/api/invitados/estado", "/api/proyectos", "/api/proyectos/%s/hilos" % slug,
    ]
    for path in admin_paths:
        status, _hs, _raw = request(GUEST, "GET", path, headers=auth(ofg, ofn), guest=True)
        check(status == 404, "admin no existe en guest: " + path[:45])

    matrix = [
        ("POST", "/api/ping"), ("PATCH", "/api/ping"), ("DELETE", "/api/ping"),
        ("HEAD", "/api/ping"), ("PUT", "/"), ("DELETE", "/"),
        ("GET", "/api/invitado/nombre"), ("PATCH", "/api/invitado/nombre"),
        ("DELETE", note_path), ("PUT", note_path), ("OPTIONS", note_path),
        ("POST", "/api/notas/%s" % slug), ("GET", note_path),
        ("POST", media_path), ("PATCH", media_path), ("DELETE", media_path),
        ("TRACE", "/"), ("BREW", "/cafe"),
    ]
    for method, path in matrix:
        status, _hs, _raw = request(GUEST, method, path, b"{}" if method in ("POST", "PATCH", "PUT") else None,
                                    auth(ofg, ofn), guest=True)
        check(status == 404, "%s no permitido en %s" % (method, path[:36]))

    # 30 descargas simultaneas, todas acotadas a un bloque pequeno.
    def ranged(_index):
        return request(GUEST, "GET", media_path,
                       headers=dict(auth(ofg, ofn), Range="bytes=0-1023"), guest=True)[:3:2]
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as pool:
        results = list(pool.map(ranged, range(30)))
    check(len(results) == 30, "terminan 30 solicitudes concurrentes")
    for index, (code, raw) in enumerate(results):
        check(code == 206 and len(raw) == 1024, "media concurrente %02d" % index)

    # Fuzz determinista: ninguna ruta generada pertenece a la lista blanca.
    rng = random.Random(20261003)
    methods = ["GET", "POST", "PATCH", "DELETE", "PUT", "OPTIONS", "TRACE", "BREW"]
    atoms = ["..", "%2e%2e", "%252e%252e", "\\", "%00", "admin", "invitar",
             ".guest_secret", "notes.json", "server.py", "//", "?x=1", "~"]
    bases = ["/api/", "/media/%s/%s/" % (slug, video["id"]), "/thumbs/%s/" % slug,
             "/r/", "/data/", "/api/proyectos/%s/" % slug]
    success_codes = {200, 201, 204, 206}
    for index in range(420):
        method = rng.choice(methods)
        path = rng.choice(bases) + rng.choice(atoms) + str(index) + rng.choice(atoms)
        headers = auth(ofg, ofn)
        if rng.randrange(4) == 0:
            headers["Range"] = rng.choice(["bytes=x-y", "bytes=9-2", "bytes=999999-"])
        body = b"{}" if method in ("POST", "PATCH", "PUT") else None
        status, _hs, _raw = request(GUEST, method, path, body, headers, guest=True)
        check(status not in success_codes, "fuzz %03d %s" % (index, method))

    status, _hs, activity, _raw = jrequest(
        SERVER, "GET", "/api/invitados/actividad?desde=2000-01-01T00%3A00%3A00Z")
    activity_ids = {n.get("id") for n in (activity or {}).get("notas", [])}
    check(status == 200 and own_id in activity_ids and peer_id in activity_ids, "actividad incluye notas invitadas")
    item = next(n for n in activity["notas"] if n.get("id") == own_id)
    check(item.get("nombre") == "Ana" and item.get("etiqueta") == "Principal", "actividad decora autor/etiqueta")
    check(item.get("proyecto") and item.get("version") and item.get("timecode"), "actividad tiene nombres/timecode")

    # S3: estado de la puerta para el popover «Compartir».
    status, _hs, estado, _raw = jrequest(SERVER, "GET", "/api/invitados/estado")
    check(status == 200 and estado is not None and estado.get("publicada") is False and
          isinstance(estado.get("enlaces_activos"), int) and estado["enlaces_activos"] >= 2,
          "estado de la puerta: cerrada y con enlaces activos")
    status, _hs, _data, _raw = jrequest(
        SERVER, "GET", "/api/invitados/actividad?desde=no-es-iso")
    check(status == 400, "actividad con desde invalido devuelve 400")

    list_status, _hs, listing, _raw = jrequest(
        SERVER, "GET", "/api/proyectos/%s/videos/%s/invitar" % (slug, video["id"]))
    listed = next(x for x in listing.get("enlaces", []) if x.get("id") == main_link["id"])
    check(list_status == 200 and listed.get("usos", 0) >= 1, "lista cuenta usos")
    check(listed.get("notas", 0) >= 1 and listed.get("ultimo_uso"), "lista cuenta notas y ultimo uso")
    mode = stat.S_IMODE(os.stat(os.path.join(ROOT, "data", slug, "videos", video["id"],
                                             "invitados.json")).st_mode)
    check(mode == 0o600, "invitados.json modo 600")
    check(stat.S_IMODE(os.stat(os.path.join(ROOT, "data", ".guest_secret")).st_mode) == 0o600,
          ".guest_secret modo 600")

    # CLI: crea, lista y revoca contra el puerto de prueba.
    env = dict(os.environ)
    env["VISOR_API"] = "http://127.0.0.1:%d" % SERVER_PORT
    env["OPENFRAME_NO_PUBLICAR"] = "1"
    cli = subprocess.run(
        [os.path.join(ROOT, "visor.sh"), "invitar", slug, video["id"], "--dias", "1",
         "--etiqueta", "CLI"], cwd=ROOT, env=env, text=True, capture_output=True)
    check(cli.returncode == 0 and "https://" in cli.stdout and "NO quedo abierta" in cli.stderr,
          "CLI invitar informa URL y puerta cerrada")
    status, _hs, listing, _raw = jrequest(
        SERVER, "GET", "/api/proyectos/%s/videos/%s/invitar" % (slug, video["id"]))
    cli_link = next(x for x in listing["enlaces"] if x.get("etiqueta") == "CLI")
    cli_list = subprocess.run([os.path.join(ROOT, "visor.sh"), "invitados", slug], cwd=ROOT,
                              env=env, text=True, capture_output=True)
    check(cli_list.returncode == 0 and cli_link["id"] in cli_list.stdout and "CLI" in cli_list.stdout,
          "CLI invitados lista enlace")
    cli_revoke = subprocess.run(
        [os.path.join(ROOT, "visor.sh"), "revocar", slug, video["id"], cli_link["id"]],
        cwd=ROOT, env=env, text=True, capture_output=True)
    check(cli_revoke.returncode == 0 and "REVOCADO" in cli_revoke.stdout, "CLI revocar")

    # Rate limit en un enlace dedicado para no contaminar los checks anteriores.
    rate_link = invite(slug, video["id"], "Rate")
    status, _hs, rate_ofg = enter(rate_link["token"])
    status2, _hs, _data, rate_ofn = set_name(rate_ofg, "Rita")
    status3, _hs, data, _raw = jrequest(
        GUEST, "POST", note_path, {"frame": 1, "text": "rate"}, auth(rate_ofg, rate_ofn), guest=True)
    rate_note = data.get("nota", {}).get("id") if data else None
    check(status == 302 and status2 == 200 and status3 == 201 and rate_note, "prepara enlace de rate limit")
    codes = []
    for index in range(65):
        code, _hs, _data, _raw = jrequest(
            GUEST, "PATCH", "/api/notas/%s/%s" % (slug, rate_note),
            {"text": "r%d" % index}, auth(rate_ofg, rate_ofn), guest=True)
        codes.append(code)
    check(429 in codes, "limite 60 escrituras/min devuelve 429")

    # Ningun cuerpo ni log contiene tokens (Set-Cookie es la excepcion contractual necesaria).
    all_tokens = [main_link["token"], peer_link["token"], other_video_link["token"],
                  expired["token"], revoked["token"], rate_link["token"]]
    check(all(token.encode() not in body for token in all_tokens for body in GUEST_BODIES),
          "ningun cuerpo guest contiene tokens")
    log_path = os.path.join(ROOT, "logs", "guest.log")
    with open(log_path, "rb") as f:
        log_data = f.read()
    check(all(token.encode() not in log_data for token in all_tokens), "guest.log no contiene tokens")

    # ── S3: ultima pasada de atacante ───────────────────────────────
    cookies = ofg + "; " + ofn
    # (1) SSRF hacia 8477: ninguna ruta de invitado puede convertirse en otra
    # ruta de la API de administracion por codificacion o por salto de segmento.
    ssrf_paths = [
        "/api/proyectos/%s%%2fhilos" % slug,
        "/api/proyectos/%s%%2F..%%2Finvitados%%2Factividad" % slug,
        "/api/notas/%s/..%%2f..%%2fapi%%2finvitados%%2festado" % slug,
        "/api/notas/%s/%s%%2f..%%2f..%%2fproyectos" % (slug, own_id),
        "/api/notas/%s%%00/%s" % (slug, own_id),
        "/api/proyectos/%s/notas%%3f" % slug,
    ]
    for path in ssrf_paths:
        status, _hs, _raw = request(GUEST, "GET", path, headers=auth(ofg, ofn), guest=True)
        check(status == 404, "SSRF GET %s" % path[:48])
        status, _hs, _raw = request(GUEST, "PATCH", path, b"{}", auth(ofg, ofn), guest=True)
        check(status == 404, "SSRF PATCH %s" % path[:48])
    # El Host de la API local no sirve para que la puerta se confunda de destino.
    for host in ("127.0.0.1:%d" % SERVER_PORT, "openframe.inspiredink.space.evil.test",
                 "evil.test", ""):
        status, _hs, _raw = request(GUEST, "GET", "/api/notas/" + slug,
                                    headers=dict(auth(ofg, ofn), Host=host), guest=True)
        check(status == 404, "Host ajeno rechazado %r" % host[:32])
    # X-Guest-Gate del cliente no se reenvia: la nota sigue siendo de invitado.
    status, _hs, data, _raw = jrequest(
        GUEST, "POST", note_path, {"frame": 1, "text": "gate falso", "author": "cristian"},
        dict(auth(ofg, ofn), **{"X-Guest-Gate": "0" * 64}), guest=True)
    forged = (data or {}).get("nota", {})
    check(status == 201 and forged.get("author") == "invitado" and
          forged.get("autor_nombre") == "Ana", "X-Guest-Gate del cliente no se reenvia")
    # Y el secreto real no vale como cabecera contra la puerta (no la usa).
    with open(os.path.join(ROOT, "data", ".guest_secret"), "rb") as f:
        real_gate = f.read().hex()
    status, _hs, _raw = request(GUEST, "GET", "/api/invitados/actividad",
                                headers=dict(auth(ofg, ofn), **{"X-Guest-Gate": real_gate}),
                                guest=True)
    check(status == 404, "administracion sigue ausente con el secreto real")

    # (2) Desincronizacion de longitudes.
    raw_cases = [
        ("Content-Length duplicado",
         "POST %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nCookie: %s\r\nContent-Type: application/json"
         "\r\nContent-Length: 2\r\nContent-Length: 40\r\n\r\n{}" % (note_path, GUEST_PORT, cookies)),
        ("Transfer-Encoding con Content-Length",
         "POST %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nCookie: %s\r\nTransfer-Encoding: chunked"
         "\r\nContent-Length: 4\r\n\r\n0\r\n\r\n" % (note_path, GUEST_PORT, cookies)),
        ("Transfer-Encoding a secas",
         "POST %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nCookie: %s\r\nTransfer-Encoding: chunked"
         "\r\n\r\n2\r\n{}\r\n0\r\n\r\n" % (note_path, GUEST_PORT, cookies)),
        ("Content-Length con signo",
         "POST %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nCookie: %s\r\nContent-Length: +2\r\n\r\n{}"
         % (note_path, GUEST_PORT, cookies)),
        ("Content-Length negativo",
         "POST %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nCookie: %s\r\nContent-Length: -1\r\n\r\n{}"
         % (note_path, GUEST_PORT, cookies)),
    ]
    for label, payload in raw_cases:
        status = raw_status(payload)
        check(status in (400, 404), "%s rechazado (%s)" % (label, status))

    # (3) thumb con ruta: ni al crear ni al descargar.
    for bad in ["../../data/.guest_secret", "/etc/passwd", "data:image/jpeg;base64,../x",
                "thumbs/%s/%s.jpg" % (slug, own_id)]:
        status, _hs, _data, _raw = jrequest(
            GUEST, "POST", note_path, {"frame": 1, "thumb": bad}, auth(ofg, ofn), guest=True)
        check(status == 400, "thumb con ruta rechazado %r" % bad[:28])
    for path in ["/thumbs/%s/..%%2f..%%2fdata%%2f.guest_secret.jpg" % slug,
                 "/thumbs/%s/../.guest_secret.jpg" % slug,
                 "/thumbs/%s/%s.jpg" % (other_slug, own_id),
                 "/thumbs/%s/%s%%00.jpg" % (slug, own_id)]:
        status, _hs, _raw = request(GUEST, "GET", path, headers=auth(ofg, ofn), guest=True)
        check(status == 404, "thumb ajeno 404 %s" % path[:46])

    # (4) Enlaces simbolicos dentro de la carpeta del video.
    video_dir = os.path.join(ROOT, "data", slug, "videos", video["id"])
    secret_dir = os.path.join(ROOT, "data", other_slug, "videos", secret_video["id"])
    secret_meta = json.load(open(os.path.join(secret_dir, "meta.json"), encoding="utf-8"))
    secret_file = os.path.join(secret_dir, secret_meta.get("archivo", "media.mp4"))
    proxy_link = os.path.join(video_dir, "proxy-720.mp4")
    os.symlink(secret_file, proxy_link)
    try:
        status, _hs, raw = request(GUEST, "GET", media_path,
                                   headers=dict(auth(ofg, ofn), Range="bytes=0-32"), guest=True)
        secret_head = open(secret_file, "rb").read(32)
        check(status == 404 and b"no est" in raw and secret_head not in raw,
              "proxy que es symlink a otro video da el 404 uniforme")
        other_name = os.path.join(video_dir, "secreto.mp4")
        os.symlink(secret_file, other_name)
        try:
            status, _hs, _raw = request(GUEST, "GET", "/media/%s/%s/secreto.mp4" % (slug, video["id"]),
                                        headers=auth(ofg, ofn), guest=True)
            check(status == 404, "symlink con otro nombre no se sirve")
        finally:
            os.unlink(other_name)
    finally:
        os.unlink(proxy_link)
    status, _hs, raw = request(GUEST, "GET", media_path,
                               headers=dict(auth(ofg, ofn), Range="bytes=0-31"), guest=True)
    check(status == 206 and len(raw) == 32, "el video compartido vuelve a servirse tras el symlink")

    # (5) Cache entre invitados: nada cacheable y la respuesta depende de la cookie.
    for path in ["/", "/api/notas/" + slug, "/api/proyectos/" + slug, media_path]:
        _status, hs, _raw = request(GUEST, "GET", path, headers=auth(ofg, ofn), guest=True)
        check(hs.get("Cache-Control") == "no-store", "no-store en %s" % path[:38])
        check("Cookie" in (hs.get("Vary") or ""), "Vary: Cookie en %s" % path[:38])
    _status, _hs, mine, _raw = jrequest(GUEST, "GET", "/", None, auth(ofg, ofn), guest=True)
    status_a, _hs, _data, raw_a = jrequest(GUEST, "GET", "/", None, auth(ofg, ofn), guest=True)
    status_b, _hs, _data, raw_b = jrequest(GUEST, "GET", "/", None, auth(peer_ofg, peer_ofn), guest=True)
    check(status_a == 200 and status_b == 200 and b'"nombre":"Ana"' in raw_a and
          b'"nombre":"Ana"' not in raw_b, "cada cookie recibe su propio arranque")

    print("\n%s — %d checks, %d fallos, fuzz=420, concurrencia=30" %
          ("PASS" if not FAILS else "FAIL", CHECKS, len(FAILS)))
    if FAILS:
        for label in FAILS[:20]:
            print(" - " + label)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        stop_servers()
