#!/usr/bin/env python3
"""Arnes de FIDELIDAD de la replica literal: compara el visor real contra la maqueta.

    OPENFRAME_NO_PUBLICAR=1 python3 server.py --puerto 9501 &
    python3 tools/setup-x2.py --api http://127.0.0.1:9501
    tools/chrome.sh start 9502
    CDP_PORT=9502 /tmp/o8/venv/bin/python tools/fidelidad.py

Abre la maqueta (`ref/maqueta/VISUAL.html` por file://) y el visor real (el servidor con
el proyecto de prueba) a 1440x900 y 1600x1000, y compara PARES de elementos declarados en
`tools/fidelidad-map.json` con getComputedStyle + getBoundingClientRect.

Cada agente de la tanda AÑADE sus pares a su region (>= 15 por region) y deben pasar al
100 %. Sale 1 si algo falla.

Formato de `tools/fidelidad-map.json`:

    {"regiones":[
      {"region":"encabezado","pares":[
        {"n":"cabecera","m":"header","r":".topbar",
         "props":["height","backgroundColor","fontFamily","w","h","relx","rely"],
         "tol":1,                  # opcional, px (por defecto 1)
         "cm":"body","cr":"body",  # opcional: contenedor para relx/rely (por defecto el padre)
         "vp":[1440]}              # opcional: solo en estos anchos de ventana
      ]}
    ]}

Propiedades admitidas: cualquier nombre camelCase de getComputedStyle (se compara el texto
normalizado) y ademas las geometricas `w`, `h`, `relx`, `rely` (numericas, tolerancia +-1 px).
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAQUETA = "file://" + os.path.join(ROOT, "ref", "maqueta", "VISUAL.html")
MAPA = os.path.join(ROOT, "tools", "fidelidad-map.json")
SHOTS = os.path.join(ROOT, "shots")
VIEWPORTS = [(1440, 900), (1600, 1000)]
GEOM = ("w", "h", "relx", "rely")
TOL_POR_DEFECTO = 1.0

# ── recoleccion en el navegador ─────────────────────────────────────────────
# Devuelve {nombre_del_par: {prop: valor}}; si el selector no existe, {"__falta__": sel}.
JS_MEDIR = r"""
(() => {
  const pares = __PARES__;
  const salida = {};
  for(const p of pares){
    const el = document.querySelector(p.sel);
    if(!el){ salida[p.n] = {__falta__: p.sel}; continue; }
    const cs = getComputedStyle(el), b = el.getBoundingClientRect();
    const cont = (p.cont ? document.querySelector(p.cont) : el.parentElement) || document.body;
    const cb = cont.getBoundingClientRect();
    const v = {};
    for(const prop of p.props){
      if(prop === "w") v.w = Math.round(b.width * 100) / 100;
      else if(prop === "h") v.h = Math.round(b.height * 100) / 100;
      else if(prop === "relx") v.relx = Math.round((b.left - cb.left) * 100) / 100;
      else if(prop === "rely") v.rely = Math.round((b.top - cb.top) * 100) / 100;
      else v[prop] = String(cs[prop]);
    }
    salida[p.n] = v;
  }
  return salida;
})()
"""


def normalizar(valor):
    """Texto de CSS comparable: espacios colapsados, rgb(a) y ceros decimales iguales."""
    s = str(valor).strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"rgba\(([^)]+?),\s*1\)", r"rgb(\1)", s)
    s = re.sub(r"(\d+)\.0+(?=px|%|\b)", r"\1", s)
    return s


def medir(pagina, pares):
    datos = [{"n": p["n"], "sel": p["sel"], "props": p["props"], "cont": p.get("cont")} for p in pares]
    js = JS_MEDIR.replace("__PARES__", json.dumps(datos))
    r = pagina.ev(js)
    if not isinstance(r, dict):
        raise SystemExit("la medicion fallo: %r" % (r,))
    return r


def comparar(par, vm, vr):
    """Devuelve la lista de diferencias (prop, maqueta, real) del par."""
    if "__falta__" in vm:
        return [("selector maqueta", vm["__falta__"], "NO EXISTE")]
    if "__falta__" in vr:
        return [("selector real", vr["__falta__"], "NO EXISTE")]
    tol = float(par.get("tol", TOL_POR_DEFECTO))
    fallos = []
    for prop in par["props"]:
        a, b = vm.get(prop), vr.get(prop)
        if prop in GEOM:
            if a is None or b is None or abs(float(a) - float(b)) > tol:
                fallos.append((prop, a, b))
        elif normalizar(a) != normalizar(b):
            fallos.append((prop, a, b))
    return fallos


# ── preparacion de las dos paginas ──────────────────────────────────────────
def abrir_maqueta(w, h):
    pg = Page(url=MAQUETA, w=w, h=h)
    time.sleep(1.2)
    return pg


def abrir_real(api, w, h):
    """Visor real con el proyecto de prueba abierto y UNA NOTA SELECCIONADA.

    Es el estado comparable con el de la maqueta (que pinta la nota 1 en pantalla)."""
    pg = Page(url=api + "/", w=w, h=h)
    time.sleep(2.0)
    pg.ev("(()=>{const n=document.querySelector('#list .item');if(n)n.click();return !!n})()")
    time.sleep(0.8)
    return pg


def preparar_estado(pgm, pgr, region):
    """Coloca cada región en el estado visual declarado por el mapa.

    La navegación R2 se compara desplegada; las regiones comunes conservan el estado
    plegado aprobado. Se cambia solo la vista, sin escribir localStorage ni datos.
    """
    if region.get("estado") == "nav-abierta":
        pgm.ev("(()=>{const e=document.querySelector('.item');if(e)e.click();return !!e})()")
        pgr.ev("document.body.classList.remove('nav-plegado')")
    else:
        pgr.ev("document.body.classList.add('nav-plegado')")
    time.sleep(0.15)


# ── capturas lado a lado (sin PIL: se componen en el propio Chrome) ─────────
def recorte(pagina, sel, margen=8):
    r = pagina.rect(sel)
    if not r:
        return None
    x = max(0, r["x"] - margen)
    y = max(0, r["y"] - margen)
    w = min(pagina.w - x, r["w"] + 2 * margen)
    h = min(pagina.h - y, r["h"] + 2 * margen)
    if w <= 1 or h <= 1:
        return None
    import base64
    res = pagina.send("Page.captureScreenshot", format="png",
                      clip=dict(x=x, y=y, width=w, height=h, scale=1))
    return base64.b64decode(res["data"])


def lado_a_lado(pg_comp, img_m, img_r, destino, titulo):
    """Compone las dos capturas en una pagina de Chrome y la fotografia."""
    import base64
    if not img_m or not img_r:
        return None
    b64m = base64.b64encode(img_m).decode()
    b64r = base64.b64encode(img_r).decode()
    html = (
        "<!doctype html><meta charset=utf-8><style>"
        "body{margin:0;background:#fff;font:12px -apple-system,sans-serif;color:#171717}"
        ".f{display:flex;gap:12px;padding:12px;align-items:flex-start}"
        ".c{display:flex;flex-direction:column;gap:6px}"
        "b{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#6b6b6b}"
        "img{display:block;border:1px solid #d4d4cf}"
        "h1{font:600 13px -apple-system,sans-serif;margin:12px 12px 0}"
        "</style><h1>" + titulo + "</h1><div class=f>"
        "<div class=c><b>maqueta</b><img src='data:image/png;base64," + b64m + "'></div>"
        "<div class=c><b>real</b><img src='data:image/png;base64," + b64r + "'></div></div>"
    )
    ruta = os.path.join(SHOTS, "_cmp.html")
    open(ruta, "w").write(html)
    pg_comp.url = "file://" + ruta
    pg_comp.send("Page.navigate", url=pg_comp.url)
    time.sleep(0.9)
    alto = pg_comp.ev("document.body.scrollHeight") or 900
    ancho = pg_comp.ev("document.body.scrollWidth") or 1600
    pg_comp.send("Emulation.setDeviceMetricsOverride", width=int(ancho) + 24,
                 height=int(alto) + 24, deviceScaleFactor=1, mobile=False)
    time.sleep(0.4)
    return pg_comp.shot(destino)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:9501")
    ap.add_argument("--region", action="append", help="limita a estas regiones")
    ap.add_argument("--sin-capturas", action="store_true")
    args = ap.parse_args()

    mapa = json.load(open(MAPA, encoding="utf-8"))
    regiones = [r for r in mapa["regiones"] if not args.region or r["region"] in args.region]
    if not regiones:
        raise SystemExit("ninguna region coincide con %s" % args.region)

    os.makedirs(SHOTS, exist_ok=True)
    total = fallan = 0
    resumen = {}
    detalle = []

    for w, h in VIEWPORTS:
        pgm = abrir_maqueta(w, h)
        pgr = abrir_real(args.api, w, h)
        print("\n════ %dx%d ════" % (w, h))
        for reg in regiones:
            preparar_estado(pgm, pgr, reg)
            pares = [p for p in reg["pares"] if not p.get("vp") or w in p["vp"]]
            if not pares:
                continue
            dm = medir(pgm, [{"n": p["n"], "sel": p["m"], "props": p["props"], "cont": p.get("cm")} for p in pares])
            dr = medir(pgr, [{"n": p["n"], "sel": p["r"], "props": p["props"], "cont": p.get("cr")} for p in pares])
            ok = mal = 0
            print("\n── %s" % reg["region"])
            for p in pares:
                fallos = comparar(p, dm.get(p["n"], {}), dr.get(p["n"], {}))
                total += 1
                if fallos:
                    mal += 1
                    fallan += 1
                    print("  ✘ %-28s %s" % (p["n"], "; ".join(
                        "%s: maqueta=%r real=%r" % f for f in fallos[:4])))
                    detalle.append((w, reg["region"], p["n"], fallos))
                else:
                    ok += 1
                    print("  ✔ %s" % p["n"])
            k = (reg["region"], w)
            resumen[k] = (ok, ok + mal)
        if not args.sin_capturas and w == VIEWPORTS[0][0]:
            pgc = Page(url="about:blank", w=1600, h=1000)
            for reg in regiones:
                preparar_estado(pgm, pgr, reg)
                sels = reg.get("captura")
                if not sels:
                    continue
                im = recorte(pgm, sels["m"])
                ir = recorte(pgr, sels["r"])
                ruta = lado_a_lado(pgc, im, ir, "fid-%s.png" % reg["region"], reg["region"])
                if ruta:
                    print("  capt %s" % ruta)
        for e in (pgm.errors + pgr.errors):
            print("  ⚠ excepcion en pagina: %s" % str(e)[:160])

    print("\n═══ RESUMEN POR REGION")
    for (reg, vp), (ok, tot) in sorted(resumen.items()):
        print("  %-18s %dx%-5s %d/%d" % (reg, vp, "", ok, tot))
    print("\n%d/%d pares pasan · %d fallan" % (total - fallan, total, fallan))
    return 1 if fallan else 0


if __name__ == "__main__":
    sys.exit(main())
