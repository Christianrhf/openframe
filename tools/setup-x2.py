#!/usr/bin/env python3
"""Crea el proyecto sintetico «Prueba X2» que pide tools/test-x2.py.

    OPENFRAME_NO_PUBLICAR=1 python3 server.py --puerto 9421 &
    /usr/bin/python3 tools/setup-x2.py --api http://127.0.0.1:9421

Notas de Cristian + marcadores de cambio de Agente (`kind:"cambio"`, con `resuelve`)
+ respuestas, suficientes para que el hilo necesite scroll. Sin aleatoriedad: los mismos
datos en cada ejecucion.
"""
import argparse
import json
import os
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTAS = 6          # notas de Cristian
CAMBIOS = 5        # marcadores de cambio de Agente (test-x2 busca «Cambio aplicado 4»)


def http(method, url, obj=None, raw=None, headers=None):
    body = raw if raw is not None else (json.dumps(obj).encode("utf-8") if obj is not None else None)
    req = urllib.request.Request(url, data=body, method=method)
    if raw is None and obj is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:9421")
    args = ap.parse_args()
    api = args.api.rstrip("/")

    st, d = http("POST", api + "/api/proyectos", {"nombre": "Prueba X2", "cliente": "Porte"})
    slug = d.get("slug") if isinstance(d, dict) else None
    if not slug:
        raise SystemExit("no se pudo crear el proyecto: %s %s" % (st, d))
    with open(os.path.join(ROOT, "clip.mp4"), "rb") as f:
        clip = f.read()
    st, d = http("POST", api + "/api/proyectos/%s/videos" % slug, raw=clip,
                 headers={"X-Filename": "v01.mp4", "Content-Type": "application/octet-stream"})
    vid = (d.get("video") or {}).get("id") if isinstance(d, dict) else None
    if not vid:
        raise SystemExit("no se pudo subir el video: %s %s" % (st, d))

    notas = []
    for i in range(1, NOTAS + 1):
        payload = {"video": vid, "frame": i * 7, "author": "cristian",
                   "text": "Nota de Cristian numero %d" % i}
        # La segunda nota cubre un tramo para que el arnés visual compare también
        # la barra de duración de la maqueta, no solo marcadores puntuales.
        if i == 2:
            payload["end_frame"] = i * 7 + 8
        st, d = http("POST", api + "/api/proyectos/%s/notas" % slug,
                     payload)
        notas.append((d.get("nota") or {}).get("id"))
    for i in range(1, CAMBIOS + 1):
        http("POST", api + "/api/proyectos/%s/notas" % slug,
             {"video": vid, "frame": 60 + i * 5, "author": "claude", "kind": "cambio",
              "text": "Cambio aplicado %d" % i, "resuelve": notas[(i - 1) % len(notas)]})
    # una respuesta de Agente en el primer hilo: el rotulo tiene que decir «Agente»
    http("POST", api + "/api/proyectos/%s/notas" % slug,
         {"video": vid, "parent": notas[0], "author": "claude", "text": "Hecho en el corte nuevo."})
    print("prueba-x2 listo: slug=%s video=%s notas=%d cambios=%d" % (slug, vid, NOTAS, CAMBIOS))


if __name__ == "__main__":
    main()
