#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visor de Notas — servidor local de revision de video.
Solo stdlib. Escucha en 127.0.0.1, sin dependencias.

  python3 server.py [--puerto 8477]
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
THUMBS = os.path.join(BASE, "thumbs")
LOCK = threading.RLock()
REV = {"n": 0}          # contador de cambios (para polling barato)
STARTED = time.time()
PUBLICAR_INTERVAL = 300

for d in (DATA, THUMBS):
    os.makedirs(d, exist_ok=True)


# ── utilidades ────────────────────────────────────────────────
def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def slugify(s, fallback="proyecto"):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").strip().lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s[:48] or fallback


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    tmp = path + ".tmp-%d-%s" % (os.getpid(), uuid.uuid4().hex[:8])
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def bump():
    REV["n"] += 1


def rev():
    return REV["n"]


def pdir(slug):
    return os.path.join(DATA, slug)


def inside(root, path):
    """True solo si `path` cae realmente dentro de `root`.

    Las rutas de /media y /thumbs se extraen con [\\w.-]+, que acepta "..": sin esta
    comprobacion, /media/../../../../etc/passwd salia de la carpeta del proyecto.
    realpath resuelve tambien enlaces simbolicos.
    """
    try:
        r = os.path.realpath(root)
        p = os.path.realpath(path)
    except OSError:
        return False
    return p == r or p.startswith(r + os.sep)


def plist(slug):
    return read_json(os.path.join(pdir(slug), "meta.json"), {})


def notes_path(slug):
    return os.path.join(pdir(slug), "notes.json")


def load_notes(slug):
    return read_json(notes_path(slug), [])


def save_notes(slug, notes):
    write_json(notes_path(slug), notes)
    bump()


def vdir(slug, vid):
    return os.path.join(pdir(slug), "videos", vid)


def guest_secret_path():
    return os.path.join(DATA, ".guest_secret")


def guest_secret():
    """Secreto local compartido con guest.py; nunca sale por HTTP."""
    path = guest_secret_path()
    with LOCK:
        try:
            with open(path, "rb") as f:
                value = f.read()
            if len(value) == 32:
                os.chmod(path, 0o600)
                return value
        except OSError:
            pass
        value = secrets.token_bytes(32)
        tmp = path + ".tmp-%d-%s" % (os.getpid(), uuid.uuid4().hex[:8])
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(value)
            os.replace(tmp, path)
            os.chmod(path, 0o600)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return value


def invitados_path(slug, vid):
    return os.path.join(vdir(slug, vid), "invitados.json")


def _locked_links(slug, vid, change=None):
    """Lee/modifica enlaces con flock para coordinar server.py y guest.py."""
    path = invitados_path(slug, vid)
    if not os.path.isdir(vdir(slug, vid)):
        raise ValueError("video no existe")
    lock_path = path + ".lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with os.fdopen(fd, "r+") as lockf:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
            links = read_json(path, [])
            if not isinstance(links, list):
                links = []
            result = change(links) if change else links
            if change:
                write_json(path, links)
                os.chmod(path, 0o600)
            return result
    finally:
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass


def parse_iso(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def link_activo(link, at=None):
    at = at or datetime.now(timezone.utc)
    exp = parse_iso(link.get("expira"))
    if exp is None:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return not link.get("revocado") and exp > at


def base_publica():
    cfg = read_json(os.path.join(BASE, "config.json"), {})
    value = cfg.get("base_publica") if isinstance(cfg, dict) else None
    if not isinstance(value, str) or not value.startswith("https://"):
        value = "https://openframe.inspiredink.space"
    return value.rstrip("/")


def iter_enlaces():
    if not os.path.isdir(DATA):
        return
    for slug in sorted(os.listdir(DATA)):
        videos_root = os.path.join(pdir(slug), "videos")
        if not os.path.isdir(videos_root):
            continue
        for vid in sorted(os.listdir(videos_root)):
            path = invitados_path(slug, vid)
            if os.path.isfile(path):
                for link in read_json(path, []):
                    if isinstance(link, dict):
                        yield slug, vid, link


def enlaces_activos():
    return sum(1 for _slug, _vid, link in iter_enlaces() if link_activo(link))


def publicar(accion):
    """Opera el launchd sin heredar el request indefinidamente."""
    if os.environ.get("OPENFRAME_NO_PUBLICAR") == "1":
        return False, "publicacion desactivada por OPENFRAME_NO_PUBLICAR"
    try:
        proc = subprocess.Popen(
            [os.path.join(BASE, "publicar.sh"), accion], cwd=BASE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True)
        try:
            out, _ = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
            return False, "publicar.sh excedio 60 s"
        msg = (out or "").strip()[-300:]
        return proc.returncode == 0, msg or ("ok" if proc.returncode == 0 else "fallo")
    except Exception as exc:
        return False, "no se pudo ejecutar publicar.sh: %s" % type(exc).__name__


def puerta_estado():
    if os.environ.get("OPENFRAME_NO_PUBLICAR") == "1":
        return False
    ok, text = publicar("estado")
    return bool(ok and "tunel: abierto" in text and "puerta local: abierto" in text)


def publicar_watchdog():
    while True:
        time.sleep(PUBLICAR_INTERVAL)
        try:
            if enlaces_activos() == 0:
                publicar("off")
        except Exception:
            pass


# ── P5: estado de revision de un video ─────────────────────────
# Vive en la meta del video como `revision:{estado, desde}`. Es OPCIONAL: un
# meta.json antiguo (sin el campo) vale «revision», asi que no hay migracion.
REV_ESTADOS = ("revision", "con_agente", "aprobado")
REV_DEFECTO = "revision"


def rev_estado(meta):
    """{estado, desde} normalizado de la meta de un video. Nunca lanza."""
    r = (meta or {}).get("revision")
    if not isinstance(r, dict):
        return {"estado": REV_DEFECTO, "desde": ""}
    estado = r.get("estado")
    if estado not in REV_ESTADOS:
        estado = REV_DEFECTO
    desde = r.get("desde")
    return {"estado": estado, "desde": desde if isinstance(desde, str) else ""}


def set_rev_estado(slug, vid, estado):
    """Escribe el estado de revision del video. Devuelve {estado, desde}."""
    if estado not in REV_ESTADOS:
        raise ValueError("estado invalido: usa %s" % " | ".join(REV_ESTADOS))
    mp = os.path.join(vdir(slug, vid), "meta.json")
    with LOCK:
        cur = read_json(mp, None)
        if not cur:
            raise ValueError("video no existe")
        nuevo = {"estado": estado, "desde": now_iso()}
        cur["revision"] = nuevo
        write_json(mp, cur)
        bump()
    return nuevo


def load_videos(slug):
    root = os.path.join(pdir(slug), "videos")
    out = []
    if not os.path.isdir(root):
        return out
    for vid in sorted(os.listdir(root)):
        m = read_json(os.path.join(root, vid, "meta.json"), None)
        if m:
            m["id"] = vid
            # derivado al leer: la UI y la CLI reciben siempre el campo completo
            m["revision"] = rev_estado(m)
            out.append(m)
    out.sort(key=lambda v: v.get("created", ""))
    return out


# ── deteccion basica de codec (sin ffmpeg) ─────────────────────
CODECS = {
    b"avc1": "H.264", b"avc3": "H.264", b"hvc1": "HEVC/H.265", b"hev1": "HEVC/H.265",
    b"av01": "AV1", b"vp09": "VP9", b"vp08": "VP8",
    b"apch": "ProRes 422 HQ", b"apcn": "ProRes 422", b"apcs": "ProRes 422 LT",
    b"ap4h": "ProRes 4444", b"apco": "ProRes Proxy", b"ap4x": "ProRes 4444 XQ",
    b"dvh1": "DV", b"mjpa": "Motion JPEG", b"rle ": "Animation",
    b"mp4v": "MPEG-4 Visual", b"jpeg": "JPEG",
}
CHROME_OK = {"H.264", "VP9", "AV1", "MPEG-4 Visual"}


def sniff_codec(path):
    """Lee los atomos de tipo de muestra del MP4 para saber si Chrome podra reproducirlo."""
    found = []
    try:
        size = min(os.path.getsize(path), 3 * 1024 * 1024)
        with open(path, "rb") as f:
            buf = f.read(size)
    except Exception:
        return "desconocido"
    for code, name in CODECS.items():
        if code in buf and name not in found:
            found.append(name)
    if not found:
        return "desconocido"
    return " + ".join(found)


def playable(codec):
    parts = [p.strip() for p in (codec or "").split("+")]
    return bool(parts) and all(p in CHROME_OK for p in parts)


# ── lectura del contenedor MP4 (duracion y fps sin ffmpeg) ───
def _iter_boxes(buf, start, end):
    """Recorre los atomos de primer nivel dentro de [start, end)."""
    p = start
    while p + 8 <= end:
        size = int.from_bytes(buf[p:p + 4], "big")
        typ = buf[p + 4:p + 8]
        hdr = 8
        if size == 1:
            if p + 16 > end:
                return
            size = int.from_bytes(buf[p + 8:p + 16], "big")
            hdr = 16
        elif size == 0:
            size = end - p
        if size < hdr or p + size > end:
            return
        yield typ, p + hdr, p + size
        p += size


def _find(buf, path, start, end):
    """Busca una ruta de atomos, p.ej. [b'moov', b'trak', b'mdia', b'mdhd']."""
    for typ, s, e in _iter_boxes(buf, start, end):
        if typ == path[0]:
            if len(path) == 1:
                return s, e
            r = _find(buf, path[1:], s, e)
            if r:
                return r
    return None


def probe_mp4(path):
    """Devuelve (duracion_s, fps) leyendo mvhd/mdhd/stts. (0.0, 0.0) si no se puede."""
    dur, fps = 0.0, 0.0
    try:
        with open(path, "rb") as f:
            head = f.read(3 * 1024 * 1024)
        fsize = os.path.getsize(path)
        end = len(head)

        # moov puede estar al final (archivos finalizados en streaming).
        # Este camino estaba ROTO: hacia f.seek() con el fichero ya cerrado (el `with`
        # terminaba una linea antes), saltaba ValueError, lo tragaba el except de abajo
        # y devolvia (0.0, 0.0). O sea: TODO mp4 con el moov al final se quedaba sin
        # duracion y sin fps, y el visor caia al fps por defecto de 24.
        if _find(head, [b"moov"], 0, end) is None and fsize > end:
            with open(path, "rb") as f:
                f.seek(max(0, fsize - end))
                tail = f.read(end)
            if _find(tail, [b"moov"], 0, len(tail)):
                head, end = tail, len(tail)
            else:
                return 0.0, 0.0

        mv = _find(head, [b"moov", b"mvhd"], 0, end)
        if mv:
            s = mv[0]
            ver = head[s]
            if ver == 1:
                ts = int.from_bytes(head[s + 20:s + 24], "big")
                du = int.from_bytes(head[s + 24:s + 32], "big")
            else:
                ts = int.from_bytes(head[s + 12:s + 16], "big")
                du = int.from_bytes(head[s + 16:s + 20], "big")
            if ts > 0:
                dur = du / ts

        # fps: del time-to-sample (stts) de la pista de video
        mo = _find(head, [b"moov"], 0, end)
        if mo:
            for typ, ts_, te in _iter_boxes(head, mo[0], mo[1]):
                if typ != b"trak":
                    continue
                hd = _find(head, [b"mdia", b"mdhd"], ts_, te)
                if not hd:
                    continue
                s = hd[0]
                if head[s] == 1:
                    mts = int.from_bytes(head[s + 20:s + 24], "big")
                    mdu = int.from_bytes(head[s + 24:s + 32], "big")
                else:
                    mts = int.from_bytes(head[s + 12:s + 16], "big")
                    mdu = int.from_bytes(head[s + 16:s + 20], "big")
                if not mts:
                    continue
                tdur = mdu / mts
                if tdur <= 0:
                    continue
                st = _find(head, [b"mdia", b"minf", b"stbl", b"stts"], ts_, te)
                if not st:
                    continue
                s = st[0] + 4
                cnt = int.from_bytes(head[s:s + 4], "big")
                total, dur_sum = 0, 0
                for i in range(min(cnt, 4096)):
                    o = s + 4 + i * 8
                    if o + 8 > head.__len__():
                        break
                    c = int.from_bytes(head[o:o + 4], "big")
                    dl = int.from_bytes(head[o + 4:o + 8], "big")
                    total += c
                    dur_sum += c * dl
                if total > 0 and dur_sum > 0:
                    # segundos por muestra -> muestras por segundo
                    fps = total / (dur_sum / mts)
                    break
        if dur <= 0 and fps > 0:
            dur = 0.0
    except Exception:
        return dur, fps
    return round(dur, 3), (round(fps, 3) if fps else 0.0)


# ── timecode ──────────────────────────────────────────────────
def tc_from(frame, fps):
    fps = float(fps or 24) or 24.0
    f = int(frame)
    ff = int(f % round(fps))
    tot = int(f // round(fps))
    return "%02d:%02d:%02d:%02d" % (tot // 3600, (tot // 60) % 60, tot % 60, ff)


# ── fps: una sola fuente de verdad ────────────────────────────
# El fps es propiedad del VIDEO, no de la nota. La nota guarda el fps con el que
# se escribio (para que frame/fps == time siga siendo cierto), pero nunca decide
# el fps del video. Un fps fuera de este rango no es un fps de video: es el
# resultado de una medicion rota (en los datos reales aparecieron 3.43 y 8.0).
FPS_MIN, FPS_MAX = 12.0, 240.0
FPS_DEFAULT = 24.0


def is_fps_plausible(x):
    """True solo si x puede ser el fps de un video real."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return False
    return x == x and FPS_MIN <= x <= FPS_MAX     # x == x descarta NaN


def video_fps(slug, vid, fallback=None):
    """fps efectivo de un video: meta del video -> fallback del cliente -> 24."""
    vm = read_json(os.path.join(vdir(slug, vid or ""), "meta.json"), {})
    if is_fps_plausible(vm.get("fps")):
        return float(vm["fps"])
    if is_fps_plausible(fallback):
        return float(fallback)
    return FPS_DEFAULT


def note_time(n):
    """El momento (s) que la nota representa, segun lo que esta guardado.

    frame/fps es la fuente primaria: es exactamente como se escribio el campo
    "time". Si la nota no trae fps se cae a "time" y por ultimo a 0.
    """
    try:
        f = float(n.get("frame") or 0)
    except (TypeError, ValueError):
        f = 0.0
    fp = n.get("fps")
    try:
        fp = float(fp) if fp else 0.0
    except (TypeError, ValueError):
        fp = 0.0
    if fp > 0:
        return f / fp
    t = n.get("time")
    if isinstance(t, (int, float)):
        return float(t)
    return f / FPS_DEFAULT


def plan_note_fps(n, vfps, realign_mismatch=False):
    """Calcula como dejar una nota coherente con el fps del video. NO muta nada.

    Devuelve None si ya esta coherente (la migracion es idempotente), o un dict
    con los campos nuevos. El TIEMPO se conserva: frame_nuevo = round(t * vfps),
    asi la nota sigue apuntando al mismo momento del video.
    """
    nf = n.get("fps")
    if is_fps_plausible(nf):
        if abs(float(nf) - vfps) < 0.001:
            return None                  # ya coherente
        if not realign_mismatch:
            return None                  # fps valido pero distinto: solo con --todas
    try:
        tiene_fps = float(nf or 0) > 0
    except (TypeError, ValueError):
        tiene_fps = False
    new = {"fps": round(vfps, 3)}
    if tiene_fps:
        # el fps guardado es basura, asi que el frame (= round(t * basura)) tambien.
        # Lo unico confiable es el MOMENTO: se reconstruye el frame desde ahi.
        new["frame"] = max(0, int(round(note_time(n) * vfps)))
    else:
        # sin fps no hay como reinterpretar: el frame es el dato real, se respeta
        new["frame"] = max(0, int(n.get("frame") or 0))
    new["timecode"] = tc_from(new["frame"], vfps)
    new["time"] = round(new["frame"] / vfps, 3)
    ef = n.get("end_frame")
    if ef not in (None, "", 0):
        # el final se mueve con la misma regla, conservando su propio tiempo
        if tiene_fps:
            et = note_time({"frame": ef, "fps": nf, "time": n.get("end_time")})
            new["end_frame"] = max(new["frame"], int(round(et * vfps)))
        else:
            new["end_frame"] = max(new["frame"], int(ef))
        new["end_timecode"] = tc_from(new["end_frame"], vfps)
        new["end_time"] = round(new["end_frame"] / vfps, 3)
    return new


# ── API ───────────────────────────────────────────────────────
def archivar_proyecto(slug, flag):
    """Marca (o desmarca) un proyecto como archivado. Archivado NO borra nada: el
    proyecto sale de la lista normal, deja de abrirse al recargar y se puede volver
    a sacar. Cristian: "el 1 ya esta terminado, deberia archivarse o algo"."""
    with LOCK:
        path = os.path.join(pdir(slug), "meta.json")
        if not os.path.isfile(path):
            return {"ok": False, "error": "no existe"}
        m = read_json(path, {}) or {}
        m["archivado"] = bool(flag)
        m["archivado_el"] = now_iso() if flag else ""
        write_json(path, m)
        return {"ok": True, "slug": slug, "archivado": bool(flag)}


def es_pendiente(n):
    """Que cuenta como pendiente. La MISMA regla en el servidor y en la UI.

    Antes contaba todo lo no resuelto: 37 marcadores de cambio y 2 respuestas. La
    tarjeta del proyecto decia "51 pendientes" cuando Cristian tenia 2 notas que
    atender. Un cambio no se "resuelve": se mira, y se marca visto.
    """
    if n.get("kind") == "cambio":
        return False
    if n.get("parent"):
        return False
    return not n.get("resolved")


def api_proyectos():
    """Proyectos con su estado. `archivado` sale de la meta del proyecto; los
    archivados se devuelven aparte para que la UI pueda esconderlos y no los abra
    por defecto al arrancar."""
    out, arch = [], []
    for slug in sorted(os.listdir(DATA)):
        m = plist(slug)
        if not m:
            continue
        notes = load_notes(slug)
        vids = load_videos(slug)
        item = {
            "slug": slug, "nombre": m.get("nombre", slug),
            "cliente": m.get("cliente", ""), "nota": m.get("nota", ""),
            "created": m.get("created", ""), "videos": len(vids),
            "notas": len(notes),
            # Una sola regla de "pendiente", igual que en la UI:
            # pendiente = nota de Cristian sin cerrar. Los marcadores de cambio NO
            # cuentan (son 37 y hangueaban el contador: decia "51 pend" siendo 2),
            # y las respuestas tampoco: cuelgan de su raiz.
            "pendientes": sum(1 for n in notes if es_pendiente(n)),
            "cambios": sum(1 for n in notes if n.get("kind") == "cambio"),
            "cambios_vistos": sum(1 for n in notes
                                  if n.get("kind") == "cambio" and n.get("visto")),
            "archivado": bool(m.get("archivado")),
            "archivado_el": m.get("archivado_el", ""),
            # P5: estado del CORTE ACTUAL (el video mas reciente) para la tarjeta
            # del proyecto. Sin videos no hay corte que revisar: «revision».
            "revision": (vids[-1]["revision"] if vids
                         else {"estado": REV_DEFECTO, "desde": ""}),
            # notas ya enviadas al Agente en la ronda abierta
            "enviadas": sum(1 for n in notes if n.get("enviada_el")),
        }
        (arch if item["archivado"] else out).append(item)
    # lo mas reciente primero (igual que los videos dentro de un proyecto)
    out.sort(key=lambda x: x.get("created", ""), reverse=True)
    arch.sort(key=lambda x: x.get("archivado_el", ""), reverse=True)
    return {"proyectos": out, "archivados": arch, "todos": out + arch}


def crear_proyecto(nombre, cliente="", nota=""):
    with LOCK:
        base = slugify(nombre)
        slug = base
        i = 2
        while os.path.isdir(pdir(slug)):
            slug = "%s-%d" % (base, i)
            i += 1
        os.makedirs(os.path.join(pdir(slug), "videos"), exist_ok=True)
        write_json(os.path.join(pdir(slug), "meta.json"), {
            "nombre": nombre or slug, "cliente": cliente, "nota": nota,
            "created": now_iso(), "slug": slug,
        })
        save_notes(slug, [])
        bump()
        return slug


def add_video(slug, src_path, nombre=None, origen="claude"):
    with LOCK:
        if not os.path.isdir(pdir(slug)):
            raise ValueError("proyecto no existe: %s" % slug)
        ext = os.path.splitext(src_path)[1].lower() or ".mp4"
        vid = "v_" + uuid.uuid4().hex[:8]
        dst_dir = vdir(slug, vid)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, "media" + ext)
        shutil.copy2(src_path, dst)
        size = os.path.getsize(dst)
        codec = sniff_codec(dst)
        dur, fps = probe_mp4(dst)
        meta = {
            "nombre": nombre or os.path.basename(src_path),
            "archivo": "media" + ext, "bytes": size,
            "codec": codec, "reproducible": playable(codec),
            # un fps absurdo leido del contenedor se guarda como 0: mejor "no se"
            # que un numero que luego se propaga a las notas
            "duracion": dur, "fps": (fps if is_fps_plausible(fps) else 0.0),
            "ancho": 0, "alto": 0,
            "created": now_iso(), "origen": origen,
        }
        write_json(os.path.join(dst_dir, "meta.json"), meta)
        bump()
        out = dict(meta)
        out["id"] = vid
        return out


# ── HILOS ─────────────────────────────────────────────────────
# Una nota es RAIZ (parent = None) o RESPUESTA (parent = id de la raiz).
# Las notas antiguas no traen el campo: son raices, sin migracion.
#
# Una respuesta NO tiene momento propio: hereda video/frame/end_frame de su raiz.
# Por eso no pinta marcador en la linea de tiempo — el hilo entero vive en UN punto
# del video, igual que en Frame.io.
#
# El estado del hilo es DERIVADO, no un campo mas que pueda desincronizarse:
#   pendiente  = raiz sin respuestas y sin resolver
#   respondida = raiz con al menos una respuesta y sin resolver
#   cerrada    = raiz con resolved = true   (lo que ya hacia "marcar como hecha")
EST_PENDIENTE, EST_RESPONDIDA, EST_CERRADA = "pendiente", "respondida", "cerrada"


def find_note(notes, nid):
    for n in notes:
        if n.get("id") == nid:
            return n
    return None


def is_reply(n):
    return bool(n.get("parent"))


def replies_of(notes, nid):
    out = [n for n in notes if n.get("parent") == nid]
    out.sort(key=lambda n: (n.get("created", ""), n.get("id", "")))
    return out


def thread_state(notes, root):
    if root.get("resolved"):
        return EST_CERRADA
    return EST_RESPONDIDA if replies_of(notes, root["id"]) else EST_PENDIENTE


def decorate(notes):
    """Copia de las notas con los campos DERIVADOS del hilo, para servir por HTTP.

    No se escriben en notes.json: se calculan al leer. Asi no hay dos verdades.
    """
    out = []
    # Numeracion estable por fecha de creacion (id como desempate). Las respuestas
    # no consumen numero: pertenecen al hilo de su raiz. Los campos son derivados y
    # opcionales, por lo que un notes.json antiguo no necesita migracion.
    # sorted() es estable: si varias entradas nacen en el mismo segundo conserva el
    # orden de notes.json (el orden real de creacion), en vez de barajarlas por UUID.
    ordered = sorted((n for n in notes if not is_reply(n)),
                     key=lambda n: n.get("created", ""))
    note_no, change_no = {}, {}
    nn = cn = 0
    for item in ordered:
        if item.get("kind") == "cambio":
            cn += 1
            change_no[item.get("id")] = cn
        else:
            nn += 1
            note_no[item.get("id")] = nn
    for n in notes:
        c = dict(n)
        if is_reply(n):
            c["respuestas"] = 0
            c["estado"] = None
        else:
            rs = replies_of(notes, n["id"])
            c["respuestas"] = len(rs)
            c["estado"] = thread_state(notes, n)
            if n.get("kind") == "cambio":
                c["numero"] = "A%d" % change_no.get(n.get("id"), 0)
            else:
                c["numero"] = "Nota %d" % note_no.get(n.get("id"), 0)
        out.append(c)
    return out


def group_threads(notes, video=None, solo_abiertos=False):
    """[{raiz, respuestas, estado}] ordenado por video y fotograma."""
    roots = [n for n in notes if not is_reply(n) and n.get("kind") != "cambio"]
    if video:
        roots = [n for n in roots if n.get("video") == video]
    if solo_abiertos:
        roots = [n for n in roots if not n.get("resolved")]
    roots.sort(key=lambda n: (n.get("video", ""), n.get("frame", 0), n.get("id", "")))
    return [{"raiz": r, "respuestas": replies_of(notes, r["id"]),
             "estado": thread_state(notes, r)} for r in roots]


def add_note(slug, vid, frame, text, end_frame=None, author="claude",
             resolved=False, drawing=None, thumb=None, fps=None, note_id=None,
             kind="nota", parent=None, created=None,
             from_note=None, from_video=None, resuelve=None, visto=False,
             decision=None,
             autor_nombre=None, enlace_id=None, enviada_el=None):
    # R1b: un fotograma gigante (p. ej. 10**400) desbordaba `frame / fps` con OverflowError -> 500.
    for _nm, _v in (("fotograma", frame), ("fotograma de salida", end_frame)):
        if _nm == "fotograma de salida" and _v in (None, "", 0):
            continue
        try:
            _fv = float(_v)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(_nm + " invalido")
        if not (0 <= _fv <= 10000000):
            raise ValueError(_nm + " fuera de rango")
    with LOCK:
        notes = load_notes(slug)
        # ── RESPUESTA: el momento no se elige, se hereda de la raiz ──
        if parent:
            p = find_note(notes, parent)
            if p is None:
                raise ValueError("no existe la nota a la que responder: %s" % parent)
            if is_reply(p):
                # Frame.io tampoco anida: una respuesta a una respuesta entra en el
                # MISMO hilo. Asi el hilo siempre se lee como una lista plana.
                parent = p["parent"]
                p = find_note(notes, parent) or p
            if not (text or "").strip():
                raise ValueError("una respuesta sin texto no dice nada")
            vid = p.get("video")
            frame = p.get("frame", 0)
            end_frame = p.get("end_frame")
            kind = "nota"
            resolved = False
        # el fps del VIDEO manda; el que manda el cliente es solo un respaldo para
        # videos cuyo contenedor no lo declara. Antes era al reves y por eso se
        # guardaron notas con fps 8.0 y 3.43 medidos mal en el navegador.
        eff_fps = video_fps(slug, vid, fps)
        frame = int(frame)
        # R2-2/R2-1: la misma regla que el PATCH (rango real del video; tramo no invertido).
        # Heredar un hilo a otro corte (from_note) queda fuera: puede venir de un video mas largo.
        if from_note is None:
            _vm = read_json(os.path.join(vdir(slug, vid), "meta.json"), {})
            _lim = int(round(float(_vm.get("duracion") or 0) * eff_fps))
            if _lim and frame > _lim:
                raise ValueError("fotograma %d fuera de rango (max %d)" % (frame, _lim))
            if end_frame not in (None, "", 0):
                _ef = int(end_frame)
                if _ef < frame:
                    raise ValueError("el fin del tramo (%d) no puede ser anterior al inicio (%d)" % (_ef, frame))
                if _lim and _ef > _lim:
                    end_frame = _lim
        n = {
            # note_id lo usa "deshacer un borrado": la nota vuelve con su MISMO id,
            # para que los marcadores de la barra y la seleccion sigan siendo validos.
            "id": note_id or ("n_" + uuid.uuid4().hex[:8]),
            "video": vid, "frame": frame,
            "fps": round(eff_fps, 3),
            "timecode": tc_from(frame, eff_fps),
            "time": round(frame / eff_fps, 3),
            "end_frame": int(end_frame) if end_frame not in (None, "", 0) else None,
            "text": text or "",
            # kind: "nota" = comentario normal (con texto, se ve en la lista).
            #        "cambio" = marcador de edicion: Claude lo pone donde cambio algo.
            #                  No lleva texto; solo aparece como punto verde en la barra,
            #                  para saltar directo al cambio sin ver el video entero.
            "kind": "cambio" if kind == "cambio" else "nota",
            "resolved": bool(resolved),
            "author": author,
            # created se puede imponer: "deshacer un borrado" devuelve las respuestas
            # con su hora original, para que el hilo se relea en el mismo orden
            "created": created or now_iso(),
            # hilo: parent = None en una raiz; thread = id de la raiz del hilo
            "parent": parent or None,
        }
        n["thread"] = parent or n["id"]
        if author == "invitado":
            n["autor_nombre"] = (autor_nombre or "")[:40]
            n["enlace_id"] = enlace_id
        # de donde viene (herencia entre versiones). Se acepta por la API para que
        # "deshacer el borrado" de un hilo heredado lo devuelva siendo heredado.
        if from_note:
            n["from_note"] = from_note
            n["from_video"] = from_video
            n["heredado"] = True
        # `resuelve`: el cambio se apunta a la nota de Cristian que lo origino, para
        # que la UI pueda decir "por tu nota de 00:07:15" y enlazar a ella. Sin esto
        # el cambio era un punto suelto: habia 37 y ninguno llevaba a nada.
        if resuelve:
            # se guarda el id de la RAIZ (si llega el de una respuesta, sube al hilo) y
            # se comprueba que exista: un enlace a una nota fantasma es peor que ninguno.
            o = find_note(notes, resuelve)
            if o is None:
                raise ValueError("no existe la nota que el cambio dice resolver: %s" % resuelve)
            if is_reply(o):
                o = find_note(notes, o["parent"]) or o
            n["resuelve"] = o["id"]
        # `visto`: un cambio no se resuelve, se mira. Aterrizar en el lo marca.
        if visto:
            n["visto"] = True
        if decision in ("approved", "adjust"):
            n["decision"] = decision
        # P5: se acepta por la API para que "deshacer un borrado" devuelva la nota
        # con su marca de enviada intacta.
        if isinstance(enviada_el, str) and enviada_el and len(enviada_el) <= 40 and parse_iso(enviada_el):
            n["enviada_el"] = enviada_el
        if end_frame not in (None, "", 0):
            n["end_timecode"] = tc_from(int(end_frame), eff_fps)
            n["end_time"] = round(int(end_frame) / eff_fps, 3)
        if drawing:
            n["drawing"] = drawing
        if thumb:
            try:
                raw = thumb.split(",", 1)[-1]
                tdir = os.path.join(THUMBS, slug)
                os.makedirs(tdir, exist_ok=True)
                with open(os.path.join(tdir, n["id"] + ".jpg"), "wb") as f:
                    f.write(base64.b64decode(raw))
                n["thumb"] = n["id"] + ".jpg"
            except Exception:
                pass
        notes.append(n)
        save_notes(slug, notes)
        return n


def video_notes(slug, only_pending=False, video=None):
    out = [n for n in load_notes(slug)]
    if only_pending:
        out = [n for n in out if not n.get("resolved")]
    if video:
        out = [n for n in out if n.get("video") == video]
    out.sort(key=lambda n: (n.get("video", ""), n.get("frame", 0)))
    return out


# ── ENLACES DE INVITADO ──────────────────────────────────────
def crear_enlace(slug, vid, dias=7, etiqueta="", ve_otras=False):
    if not os.path.isdir(vdir(slug, vid)):
        raise ValueError("video no existe")
    try:
        dias = int(dias)
    except (TypeError, ValueError):
        raise ValueError("dias debe ser un entero entre 1 y 90")
    if not 1 <= dias <= 90:
        raise ValueError("dias debe estar entre 1 y 90")
    if not isinstance(etiqueta, str):
        raise ValueError("etiqueta invalida")
    etiqueta = etiqueta.strip()
    if len(etiqueta) > 60 or any(ord(ch) < 32 for ch in etiqueta):
        raise ValueError("etiqueta invalida")
    creado_dt = datetime.now(timezone.utc)
    link = {
        "id": secrets.token_hex(4),
        "token": secrets.token_urlsafe(32),
        "creado": creado_dt.isoformat(timespec="seconds"),
        "expira": (creado_dt + timedelta(days=dias)).isoformat(timespec="seconds"),
        "revocado": False,
        "etiqueta": etiqueta,
        "ve_otras": bool(ve_otras),
        "usos": 0,
        "ultimo_uso": None,
    }

    def append(links):
        links.append(link)
        return dict(link)

    _locked_links(slug, vid, append)
    return link


def listar_enlaces(slug, vid):
    notes = load_notes(slug)
    out = []
    for link in _locked_links(slug, vid):
        item = {k: link.get(k) for k in (
            "id", "creado", "expira", "revocado", "etiqueta", "ve_otras",
            "usos", "ultimo_uso")}
        item["url"] = base_publica() + "/r/" + link.get("token", "")
        item["notas"] = sum(1 for n in notes if n.get("enlace_id") == link.get("id"))
        out.append(item)
    out.sort(key=lambda x: x.get("creado") or "", reverse=True)
    return out


def enlaces_vivos_todos():
    """Todos los enlaces VIVOS de todos los proyectos (panel «Compartir»: revocar a mano desde un solo sitio)."""
    out = []
    for slug, vid in sorted({(s_, v_) for s_, v_, _l in iter_enlaces()}):
        try:
            items = listar_enlaces(slug, vid)
        except ValueError:
            continue
        pn = (plist(slug) or {}).get("nombre", slug)
        vn = next((v.get("nombre") for v in load_videos(slug) if v.get("id") == vid), None) or vid
        for it in items:
            if link_activo(it):
                it.update({"slug": slug, "vid": vid, "proyecto": pn, "video": vn})
                out.append(it)
    out.sort(key=lambda x: x.get("creado") or "", reverse=True)
    return out


def revocar_enlace(slug, vid, enlace_id):
    found = {"ok": False}

    def revoke(links):
        for link in links:
            if link.get("id") == enlace_id:
                link["revocado"] = True
                found["ok"] = True
                break
        return found["ok"]

    _locked_links(slug, vid, revoke)
    return found["ok"]


def enlace_valido_id(slug, vid, enlace_id):
    try:
        links = _locked_links(slug, vid)
    except ValueError:
        return False
    return any(link.get("id") == enlace_id and link_activo(link) for link in links)


def actividad_invitados(desde):
    since = parse_iso(desde) if desde else datetime.fromtimestamp(0, timezone.utc)
    if since is None:
        raise ValueError("desde no es ISO")
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    out = []
    for slug in sorted(os.listdir(DATA)):
        pm = plist(slug)
        if not pm:
            continue
        videos = {v["id"]: v for v in load_videos(slug)}
        etiquetas = {}
        for vid in videos:
            path = invitados_path(slug, vid)
            for link in read_json(path, []):
                etiquetas[link.get("id")] = link.get("etiqueta", "")
        for n in load_notes(slug):
            if n.get("author") != "invitado":
                continue
            created = parse_iso(n.get("created"))
            if created is None:
                continue
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created <= since:
                continue
            vm = videos.get(n.get("video"), {})
            out.append({
                "slug": slug, "vid": n.get("video"), "id": n.get("id"),
                "nombre": n.get("autor_nombre", ""),
                "etiqueta": etiquetas.get(n.get("enlace_id"), ""),
                "text": n.get("text", ""), "frame": n.get("frame", 0),
                "timecode": n.get("timecode", ""), "created": n.get("created"),
                "proyecto": pm.get("nombre", slug),
                "version": vm.get("nombre", n.get("video", "")),
            })
    out.sort(key=lambda x: (x.get("created") or "", x.get("id") or ""))
    return out


# ── HERENCIA ENTRE VERSIONES ──────────────────────────────────
# "las marcas en la version siguiente pueden mostrar ese hilo de conversacion".
# Copiar un hilo del corte viejo al nuevo conservando el MOMENTO (segundos), no el
# fotograma: si v2 es de 25 fps y v1 de 24, el fotograma cambia y el instante no.
# El hilo original NO se toca: queda como registro de la version anterior.
def heredar_hilos(slug, desde, hacia, solo_pendientes=True, offset_frames=0):
    with LOCK:
        if desde == hacia:
            raise ValueError("el video de origen y el de destino son el mismo")
        notes = load_notes(slug)
        vm_hacia = read_json(os.path.join(vdir(slug, hacia), "meta.json"), None)
        if vm_hacia is None:
            raise ValueError("no existe el video de destino: %s" % hacia)
        if read_json(os.path.join(vdir(slug, desde), "meta.json"), None) is None:
            raise ValueError("no existe el video de origen: %s" % desde)
        fps_h = video_fps(slug, hacia)
        dur_h = float(vm_hacia.get("duracion") or 0)
        max_f = int(round(dur_h * fps_h)) if dur_h > 0 else 0
        # idempotente: lo que ya se heredo antes no se duplica
        ya = {n.get("from_note") for n in notes
              if n.get("video") == hacia and n.get("from_note")}

        def remap(frame_src, fps_src):
            t = (float(frame_src) / fps_src) if fps_src else 0.0
            f = int(round(t * fps_h)) + int(offset_frames)
            f = max(0, f)
            return min(f, max_f) if max_f else f

        nuevos, saltados = [], 0
        for h in group_threads(notes, video=desde, solo_abiertos=solo_pendientes):
            raiz = h["raiz"]
            if raiz["id"] in ya:
                saltados += 1
                continue
            fps_src = float(raiz.get("fps") or 0) or video_fps(slug, desde)
            nf = remap(raiz.get("frame") or 0, fps_src)
            nr = {
                "id": "n_" + uuid.uuid4().hex[:8],
                "video": hacia, "frame": nf, "fps": round(fps_h, 3),
                "timecode": tc_from(nf, fps_h), "time": round(nf / fps_h, 3),
                "end_frame": None, "text": raiz.get("text", ""), "kind": "nota",
                "resolved": False, "author": raiz.get("author", "cristian"),
                "created": now_iso(), "parent": None,
                # de donde viene: la UI lo muestra como "v1" en la tarjeta y el
                # marcador, y asi el hilo heredado se distingue de uno nuevo
                "from_note": raiz["id"], "from_video": desde, "heredado": True,
            }
            nr["thread"] = nr["id"]
            ef = raiz.get("end_frame")
            if ef not in (None, "", 0):
                nr["end_frame"] = max(nf, remap(ef, fps_src))
                nr["end_timecode"] = tc_from(nr["end_frame"], fps_h)
                nr["end_time"] = round(nr["end_frame"] / fps_h, 3)
            if raiz.get("drawing"):
                # el dibujo esta en coordenadas 0..1: vale igual en otra resolucion
                nr["drawing"] = raiz["drawing"]
            notes.append(nr)
            nuevos.append(nr)
            for r in h["respuestas"]:
                rr = dict(nr)
                rr.update({
                    "id": "n_" + uuid.uuid4().hex[:8],
                    "parent": nr["id"], "thread": nr["id"],
                    "text": r.get("text", ""), "author": r.get("author", "cristian"),
                    "created": r.get("created") or now_iso(),
                    "from_note": r["id"], "resolved": False,
                })
                rr.pop("drawing", None)
                notes.append(rr)
        save_notes(slug, notes)
        return {"heredados": len(nuevos), "saltados": saltados, "notas": nuevos}


# ── HTTP ──────────────────────────────────────────────────────
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".m4v"}

H = {
    "text/html": "text/html; charset=utf-8",
    "application/json": "application/json; charset=utf-8",
    "image/jpeg": "image/jpeg",
    "video/mp4": "video/mp4",
    "text/markdown": "text/markdown; charset=utf-8",
}


# ── Apagado por inactividad ──
# OpenFrame no se queda residente: lo levanta la app (o `visor`) y se apaga solo tras unos minutos sin
# ninguna peticion (la interfaz abierta consulta cada ~2 s; la CLI tambien cuenta). Solo el servidor
# real (8477); los de prueba no se apagan. Si la puerta de invitados esta abierta NO se apaga: guest.py
# le pide los datos a este servidor.
_ultimo_uso = [time.time()]


def _vigia_inactividad(srv, minutos, guest_port):
    import socket
    while True:
        time.sleep(15)
        if time.time() - _ultimo_uso[0] < minutos * 60:
            continue
        try:
            socket.create_connection(("127.0.0.1", guest_port), timeout=1).close()
            continue
        except OSError:
            pass
        print("Sin uso desde hace %g min: me apago (se levanta al abrir OpenFrame)" % minutos, flush=True)
        srv.shutdown()
        return


class Handler(BaseHTTPRequestHandler):
    server_version = "VisorNotas/2.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # silencio: solo queremos errores reales

    def handle_one_request(self):
        _ultimo_uso[0] = time.time()
        super().handle_one_request()

    # utilidades
    def _send(self, code, body=b"", ctype="application/json", extra=None):
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
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), H["application/json"])

    def _err(self, code, msg):
        self._json({"error": msg}, code)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _jbody(self):
        raw = self._body()
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # ── GET ──
    # ── defensa en profundidad: 8477 es de confianza y SOLO local ──────────────────────────────
    # Si alguien apunta por error el tunel de Cloudflare (o cualquier proxy) a ESTE puerto, toda
    # peticion llega con cabeceras de proxy y se rechaza aqui con 404; igual con un Host no local
    # (DNS rebinding). La unica puerta publica es guest.py (8478), que habla con este puerto con
    # sus propias cabeceras.
    _HDR_PROXY = ("cf-ray", "cf-connecting-ip", "cf-visitor", "cdn-loop", "x-forwarded-for",
                  "x-forwarded-host", "x-real-ip", "forwarded")

    def _trusted_local(self):
        h = self.headers
        for k in self._HDR_PROXY:
            if h.get(k) is not None:
                return False
        host = (h.get("Host") or "").strip().lower()
        if not host:
            return True
        hn = (host.split("]")[0] + "]") if host.startswith("[") else host.rsplit(":", 1)[0]
        return hn in ("127.0.0.1", "localhost", "[::1]")

    def _err500(self, e):
        """Error interno: a Cristian/Claude (local) el detalle; a quien llega por la puerta de
        invitados (X-Guest-Gate) nunca el texto de la excepcion, solo se registra."""
        if self.headers.get("X-Guest-Gate"):
            try:
                sys.stderr.write("ERROR interno %s: %s\n" % (type(e).__name__, e))
            except Exception:
                pass
            return self._err(500, "interno")
        return self._err(500, "%s: %s" % (type(e).__name__, e))

    def do_GET(self):
        if not self._trusted_local():
            return self._err(404, "no encontrado")
        parsed = urlsplit(self.path)
        p = parsed.path
        q = parse_qs(parsed.query, keep_blank_values=True)
        try:
            if p in ("/", "/index.html"):
                return self._index()
            if p == "/api/ping":
                return self._json({"ok": True, "rev": rev(), "uptime": round(time.time() - STARTED)})
            if p == "/api/proyectos":
                return self._json(dict({"rev": rev()}, **api_proyectos()))
            if p == "/api/invitados/estado":
                return self._json({"publicada": puerta_estado(),
                                   "enlaces_activos": enlaces_activos()})
            if p == "/api/invitados/activos":
                return self._json({"enlaces": enlaces_vivos_todos()})
            if p == "/api/invitados/actividad":
                try:
                    notas = actividad_invitados((q.get("desde") or [""])[0])
                except ValueError as exc:
                    return self._err(400, str(exc))
                return self._json({"notas": notas})
            m = re.match(r"^/api/proyectos/([A-Za-z0-9][A-Za-z0-9.-]{0,63})/videos/(v_[0-9a-f]{8})/invitar$", p)
            if m:
                try:
                    return self._json({"enlaces": listar_enlaces(m.group(1), m.group(2))})
                except ValueError:
                    return self._err(404, "video no existe")
            m = re.match(r"^/api/proyectos/([\w.-]+)$", p)
            if m:
                slug = m.group(1)
                if not os.path.isdir(pdir(slug)):
                    return self._err(404, "proyecto no existe")
                return self._json({
                    "rev": rev(),
                    "proyecto": plist(slug),
                    "videos": load_videos(slug),
                    "notas": decorate(load_notes(slug)),
                })
            m = re.match(r"^/api/proyectos/([\w.-]+)/hilos$", p)
            if m:
                slug = m.group(1)
                if not os.path.isdir(pdir(slug)):
                    return self._err(404, "proyecto no existe")
                notes = load_notes(slug)
                video = (q.get("video") or [""])[0]
                todas = (q.get("todas") or [""])[0]
                hs = group_threads(notes, video=video or None,
                                   solo_abiertos=todas not in ("1", "si", "true"))
                return self._json({"rev": rev(), "hilos": hs,
                                   "videos": load_videos(slug)})
            m = re.match(r"^/api/notas/([\w.-]+)$", p)
            if m:
                slug = m.group(1)
                if not os.path.isdir(pdir(slug)):
                    return self._err(404, "proyecto no existe")
                return self._json({"rev": rev(), "notas": decorate(video_notes(slug))})
            m = re.match(r"^/thumbs/([\w.-]+)/([\w.-]+\.jpg)$", p)
            if m:
                return self._file(os.path.join(THUMBS, m.group(1), m.group(2)),
                                  H["image/jpeg"], root=THUMBS)
            m = re.match(r"^/media/([A-Za-z0-9][A-Za-z0-9.-]{0,63})/(v_[0-9a-f]{8})/([A-Za-z0-9][A-Za-z0-9._-]{0,127})$", p)
            if m:
                vm = read_json(os.path.join(vdir(m.group(1), m.group(2)), "meta.json"), {})
                allowed = {vm.get("archivo"), "proxy-720.mp4"}
                if m.group(3) not in allowed or os.path.splitext(m.group(3))[1].lower() not in VIDEO_EXT:
                    return self._err(404, "no encontrado")
                return self._media(os.path.join(vdir(m.group(1), m.group(2)), m.group(3)))
            return self._err(404, "no encontrado: " + p)
        except Exception as e:
            return self._err500(e)

    # ── POST ──
    def do_POST(self):
        if not self._trusted_local():
            return self._err(404, "no encontrado")
        p = self.path.split("?")[0]
        try:
            if p == "/api/proyectos":
                d = self._jbody()
                return self._json({"slug": crear_proyecto(d.get("nombre", ""),
                                                          d.get("cliente", ""), d.get("nota", ""))})
            m = re.match(r"^/api/proyectos/([\w.-]+)/archivar$", p)
            if m:
                d = self._jbody()
                return self._json(archivar_proyecto(m.group(1), bool(d.get("archivado", True))))
            m = re.match(r"^/api/proyectos/([\w.-]+)/videos$", p)
            if m:
                slug = m.group(1)
                fname = self.headers.get("X-Filename", "video.mp4")
                raw = self._body()
                if not raw:
                    return self._err(400, "cuerpo vacio")
                ext = os.path.splitext(fname)[1].lower() or ".mp4"
                if ext not in VIDEO_EXT:
                    return self._err(400, "extension no soportada: %s" % ext)
                tmp = os.path.join(THUMBS, "up%s" % uuid.uuid4().hex[:6])
                with open(tmp, "wb") as f:
                    f.write(raw)
                try:
                    meta = add_video(slug, tmp, nombre=fname, origen="cristian")
                finally:
                    os.unlink(tmp)
                return self._json({"video": meta})
            m = re.match(r"^/api/proyectos/([A-Za-z0-9][A-Za-z0-9.-]{0,63})/videos/(v_[0-9a-f]{8})/invitar$", p)
            if m:
                d = self._jbody()
                try:
                    link = crear_enlace(m.group(1), m.group(2), d.get("dias", 7),
                                        d.get("etiqueta", ""), d.get("ve_otras", False))
                except ValueError as exc:
                    return self._err(400, str(exc))
                publicada, aviso = publicar("on")
                out = {k: link[k] for k in ("id", "token", "expira", "etiqueta", "ve_otras")}
                out.update({"url": base_publica() + "/r/" + link["token"],
                            "publicada": publicada, "aviso": aviso})
                return self._json(out, 201)
            m = re.match(r"^/api/proyectos/([\w.-]+)/notas$", p)
            if m:
                d = self._jbody()
                # una respuesta no trae video: lo hereda de la nota a la que responde
                if not d.get("video") and not d.get("parent"):
                    return self._err(400, "falta video")
                supplied_gate = self.headers.get("X-Guest-Gate", "")
                valid_gate = secrets.compare_digest(supplied_gate, guest_secret().hex())
                if valid_gate:
                    nombre = d.get("autor_nombre")
                    enlace_id = d.get("enlace_id")
                    # el nombre firma las notas del invitado: en blanco deja la
                    # insignia «Invitado · » vacia (igual que la de cualquier otro)
                    if (not isinstance(nombre, str) or not 1 <= len(nombre) <= 40 or
                            not nombre.strip() or
                            any(ord(ch) < 32 or ord(ch) == 127 for ch in nombre)):
                        return self._err(400, "nombre de invitado invalido")
                    if not enlace_valido_id(m.group(1), d.get("video"), enlace_id):
                        return self._err(404, "enlace no disponible")
                    author = "invitado"
                else:
                    nombre = None
                    enlace_id = None
                    author = "claude" if d.get("author") == "claude" else "cristian"
                try:
                    n = add_note(m.group(1), d.get("video"), d.get("frame", 0), d.get("text", ""),
                                 d.get("end_frame"), author,
                                 d.get("resolved", False), d.get("drawing"),
                                 d.get("thumb"), d.get("fps"), d.get("id"),
                                 d.get("kind", "nota"), d.get("parent"),
                                 d.get("created"), d.get("from_note"),
                                 d.get("from_video"), d.get("resuelve"),
                                 bool(d.get("visto")), d.get("decision"), nombre, enlace_id,
                                 None if valid_gate else d.get("enviada_el"))
                except ValueError as e:
                    return self._err(400, str(e))
                return self._json({"nota": n}, 201)
            m = re.match(r"^/api/proyectos/([\w.-]+)/heredar$", p)
            if m:
                d = self._jbody()
                if not d.get("desde") or not d.get("hacia"):
                    return self._err(400, "faltan desde y hacia (ids de video)")
                try:
                    r = heredar_hilos(m.group(1), d["desde"], d["hacia"],
                                      bool(d.get("solo_pendientes", True)),
                                      int(d.get("offset_frames") or 0))
                except ValueError as e:
                    return self._err(400, str(e))
                return self._json(r, 201)
            m = re.match(r"^/api/proyectos/([\w.-]+)/videos/([\w.-]+)/meta$", p)
            if m:
                d = self._jbody()
                mp = os.path.join(vdir(m.group(1), m.group(2)), "meta.json")
                cur = read_json(mp, {})
                for k in ("duracion", "fps", "ancho", "alto"):
                    if k not in d:
                        continue
                    if k == "fps":
                        # frontera de entrada: no se acepta un fps que no es un fps
                        if is_fps_plausible(d[k]):
                            cur[k] = round(float(d[k]), 3)
                        continue
                    try:
                        cur[k] = int(d[k]) if k in ("ancho", "alto") else float(d[k])
                    except Exception:
                        pass
                write_json(mp, cur)
                bump()
                return self._json({"video": cur})
            return self._err(404, "no encontrado: " + p)
        except Exception as e:
            return self._err500(e)

    # ── PATCH ──
    def do_PATCH(self):
        if not self._trusted_local():
            return self._err(404, "no encontrado")
        # do_GET y do_POST ya envolvian su cuerpo en try/except; PATCH y DELETE no.
        # Una excepcion ahi dejaba la peticion SIN respuesta: con el keep-alive de
        # HTTP/1.1 el navegador se quedaba esperando hasta el timeout y la UI parecia
        # colgada en lugar de decir "no se pudo guardar".
        try:
            p = urlsplit(self.path).path
            m = re.match(r"^/api/proyectos/([A-Za-z0-9][A-Za-z0-9.-]{0,63})/videos/(v_[0-9a-f]{8})$", p)
            if m:
                return self._patch_video(m.group(1), m.group(2))
            return self._patch_nota()
        except Exception as e:
            return self._err500(e)

    def _patch_video(self, slug, vid):
        """P5: cambiar el estado de revision del corte. Unico campo que acepta."""
        d = self._jbody()
        if "estado" not in d:
            return self._err(400, "falta estado (%s)" % " | ".join(REV_ESTADOS))
        try:
            nuevo = set_rev_estado(slug, vid, d["estado"])
        except ValueError as e:
            code = 404 if str(e) == "video no existe" else 400
            return self._err(code, str(e))
        return self._json({"ok": True, "video": vid, "revision": nuevo})

    def _patch_nota(self):
        p = self.path.split("?")[0]
        # la UI usa /api/proyectos/<slug>/notas/<id>; la CLI usa /api/notas/<slug>/<id>
        m = re.match(r"^/api/(?:proyectos/([\w.-]+)/notas|notas/([\w.-]+))/([\w.-]+)$", p)
        if not m:
            return self._err(404, "no encontrado")
        slug, nid = (m.group(1) or m.group(2)), m.group(3)
        d = self._jbody()
        updated = None
        healed = False
        with LOCK:
            notes = load_notes(slug)
            for n in notes:
                if n["id"] == nid:
                    vfps = video_fps(slug, n.get("video", ""))
                    # nota con fps roto: se repara ANTES de aplicar el cambio, con la
                    # misma regla que migrar-fps.py (conserva el momento del video).
                    heal = plan_note_fps(n, vfps)
                    if heal:
                        n.update(heal)
                        healed = True
                    for k in ("text", "resolved", "visto", "resuelve"):
                        if k in d:
                            n[k] = d[k]
                    # P5: `enviada_el` = cuando la nota viajo al Agente. Opcional;
                    # null/"" lo quita (asi Ctrl+Z revierte «Enviar al Agente»).
                    if "enviada_el" in d:
                        ev = d["enviada_el"]
                        if ev in (None, ""):
                            n.pop("enviada_el", None)
                        elif isinstance(ev, str) and len(ev) <= 40 and parse_iso(ev):
                            n["enviada_el"] = ev
                        else:
                            return self._err(400, "enviada_el invalido")
                    if "decision" in d:
                        if d["decision"] in ("approved", "adjust"):
                            n["decision"] = d["decision"]
                        elif d["decision"] in (None, ""):
                            n.pop("decision", None)
                    if d.get("kind") in ("nota", "cambio"):
                        n["kind"] = "cambio" if d.get("kind") == "cambio" else "nota"
                    if "end_frame" in d:
                        n["end_frame"] = int(d["end_frame"]) if d["end_frame"] not in (None, "", 0) else None
                    # una respuesta no tiene momento propio: el frame lo manda la raiz
                    if "frame" in d and is_reply(n):
                        return self._err(400, "una respuesta no se mueve: mueve la nota raiz")
                    if "frame" in d:
                        nf = int(d["frame"])
                        if nf < 0:
                            nf = 0
                        vm = read_json(os.path.join(vdir(slug, n.get("video", "")), "meta.json"), {})
                        # el limite se calcula con el fps del VIDEO: con el fps de la
                        # nota, una nota rota (3.43) rechazaba fotogramas legitimos
                        limit = int(round(float(vm.get("duracion") or 0) * vfps))
                        if limit and nf > limit:
                            return self._json({"error": "fotograma %d fuera de rango (max %d)" % (nf, limit)}, 400)
                        _oldf = int(n.get("frame") or 0)
                        n["frame"] = nf
                        # R2-1: mover una nota con tramo conserva su duracion (antes el fin se
                        # quedaba atras y el dibujo no aparecia en ningun fotograma)
                        if "end_frame" not in d and n.get("end_frame") not in (None, "", 0):
                            _ef = int(n["end_frame"]) + (nf - _oldf)
                            if limit and _ef > limit:
                                _ef = limit
                            n["end_frame"] = _ef if _ef >= nf else None
                    if ("frame" in d or "end_frame" in d) and n.get("end_frame") not in (None, "", 0) \
                            and int(n["end_frame"]) < int(n["frame"]):
                        return self._err(400, "el fin del tramo no puede ser anterior al inicio")
                    # recalcular timecode si se movio el frame
                    eff_fps = float(n.get("fps") or 0) or FPS_DEFAULT
                    n["timecode"] = tc_from(n["frame"], eff_fps)
                    n["time"] = round(n["frame"] / eff_fps, 3)
                    if n.get("end_frame") not in (None, "", 0):
                        n["end_timecode"] = tc_from(int(n["end_frame"]), eff_fps)
                        n["end_time"] = round(int(n["end_frame"]) / eff_fps, 3)
                    else:
                        n["end_timecode"] = None
                        n["end_time"] = None
                    if "drawing" in d:
                        if d["drawing"] is None:
                            n.pop("drawing", None)
                        else:
                            n["drawing"] = d["drawing"]
                    if d.get("thumb"):
                        try:
                            raw = d["thumb"].split(",", 1)[-1]
                            tdir = os.path.join(THUMBS, slug)
                            os.makedirs(tdir, exist_ok=True)
                            with open(os.path.join(tdir, nid + ".jpg"), "wb") as f:
                                f.write(base64.b64decode(raw))
                            n["thumb"] = nid + ".jpg"
                        except Exception:
                            pass
                    updated = n
                    break
            if not updated:
                return self._err(404, "nota no encontrada: " + nid)
            # el hilo viaja pegado a su raiz: si la raiz se movio, las respuestas
            # tienen que apuntar al mismo fotograma o dejarian de ser el mismo hilo
            if not is_reply(updated):
                for r in replies_of(notes, updated["id"]):
                    for k in ("video", "frame", "fps", "timecode", "time",
                              "end_frame", "end_timecode", "end_time"):
                        r[k] = updated.get(k)
            save_notes(slug, notes)
        return self._json({"ok": True, "nota": updated, "fps_reparado": healed})

    # ── DELETE ──
    def do_DELETE(self):
        if not self._trusted_local():
            return self._err(404, "no encontrado")
        try:
            p = urlsplit(self.path).path
            m = re.match(r"^/api/proyectos/([A-Za-z0-9][A-Za-z0-9.-]{0,63})/videos/(v_[0-9a-f]{8})/invitar/([0-9a-f]{8})$", p)
            if m:
                try:
                    ok = revocar_enlace(m.group(1), m.group(2), m.group(3))
                except ValueError:
                    ok = False
                if not ok:
                    return self._err(404, "enlace no existe")
                if enlaces_activos() == 0:
                    publicar("off")
                return self._json({"ok": True})
            return self._delete_nota()
        except Exception as e:
            return self._err500(e)

    def _delete_nota(self):
        p = self.path.split("?")[0]
        # misma dualidad de ruta que en do_PATCH
        m = re.match(r"^/api/(?:proyectos/([\w.-]+)/notas|notas/([\w.-]+))/([\w.-]+)$", p)
        if not m:
            return self._err(404, "no encontrado")
        slug, nid = (m.group(1) or m.group(2)), m.group(3)
        with LOCK:
            notes = load_notes(slug)
            victima = find_note(notes, nid)
            if victima is None:
                return self._err(404, "nota no encontrada: " + nid)
            # borrar la raiz se lleva su hilo: una respuesta huerfana no tiene
            # momento propio (lo heredaba de la raiz) y quedaria invisible
            hijos = [] if is_reply(victima) else replies_of(notes, nid)
            fuera = {nid} | {h["id"] for h in hijos}
            save_notes(slug, [n for n in notes if n["id"] not in fuera])
        return self._json({"ok": True, "borradas": len(fuera),
                           "respuestas": hijos})

    # ── archivos y video con Range ──
    def _index(self):
        """Sirve la UI injecting un sello de version = md5 del propio HTML.
        Asi Cristian puede confirmar de un vistazo que esta viendo el codigo nuevo."""
        path = os.path.join(BASE, "visor.html")
        if not os.path.isfile(path):
            return self._err(404, "no existe visor.html")
        html = open(path, "rb").read()
        try:
            tag = hashlib.md5(html).hexdigest()[:6]
        except Exception:
            tag = "??????"
        txt = html.decode("utf-8", "replace")
        if 'id="sello"' in txt and ">build \u2014<" in txt:
            txt = txt.replace(">build \u2014<", ">build " + tag + "<", 1)
        elif 'id="sello"' in txt:
            import re as _re
            txt = _re.sub(r'(id="sello"[^>]*>)[^<]*(<)', r"\g<1>build " + tag + r"\g<2>", txt, count=1)
        body = txt.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("X-Build", tag)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _file(self, path, ctype, root=None):
        if root is not None and not inside(root, path):
            return self._err(403, "ruta fuera de la carpeta permitida")
        if not os.path.isfile(path):
            return self._err(404, "no existe: " + os.path.basename(path))
        data = open(path, "rb").read()
        self._send(200, data, ctype)

    def _media(self, path):
        if not inside(DATA, path):
            return self._err(403, "ruta fuera de la carpeta de proyectos")
        if not os.path.isfile(path):
            return self._err(404, "no existe el video")
        size = os.path.getsize(path)
        ctype = "video/mp4" if path.lower().endswith((".mp4", ".m4v")) else "video/quicktime"
        rng = self.headers.get("Range")
        if not rng:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            try:
                with open(path, "rb") as f:
                    shutil.copyfileobj(f, self.wfile, 65536)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if not m:
            return self._err(416, "rango invalido")
        start = int(m.group(1)) if m.group(1) else 0
        end = int(m.group(2)) if m.group(2) else size - 1
        start = max(0, min(start, size - 1))
        end = max(start, min(end, size - 1))
        length = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8477)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--inactividad", type=float, default=None,
                    help="minutos sin uso tras los que se apaga (0 = nunca; por defecto 10 en el 8477, 0 en los demas)")
    a = ap.parse_args()
    guest_secret()
    srv = ThreadingHTTPServer((a.host, a.puerto), Handler)
    srv.daemon_threads = True
    watcher = threading.Thread(target=publicar_watchdog, name="publicar-watchdog")
    watcher.daemon = True
    watcher.start()
    mins = a.inactividad if a.inactividad is not None else float(os.environ.get("OPENFRAME_IDLE_MIN", "10" if a.puerto == 8477 else "0"))
    if mins > 0:
        threading.Thread(target=_vigia_inactividad, name="inactividad", daemon=True,
                         args=(srv, mins, int(os.environ.get("OPENFRAME_GUEST_PORT", "8478")))).start()
    print("Visor de Notas escuchando en http://%s:%d" % (a.host, a.puerto))
    print("Proyectos en %s" % DATA)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nparado")


if __name__ == "__main__":
    main()
