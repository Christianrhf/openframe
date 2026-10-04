#!/usr/bin/env python3
"""Suite de R1 · cimientos de la réplica literal: tokens, tipografía, encabezado y rejilla.

    OPENFRAME_NO_PUBLICAR=1 python3 server.py --puerto 9501 &
    python3 tools/setup-x2.py --api http://127.0.0.1:9501
    tools/chrome.sh start 9502
    CDP_PORT=9502 /tmp/o8/venv/bin/python tools/test-R1.py

Comprueba lo que R1 cambió, no lo que R3/R4/R5 harán después.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.environ.get("R1_API", "http://127.0.0.1:9501")
RES = []


def check(nombre, ok, detalle=""):
    RES.append((nombre, bool(ok)))
    print(("  ✔ " if ok else "  ✘ ") + nombre + (("  — " + str(detalle)[:200]) if (detalle and not ok) else ""))


def var(pg, nombre):
    return pg.ev("getComputedStyle(document.documentElement).getPropertyValue(%s).trim()" % json.dumps(nombre))


def css(pg, sel, prop):
    return pg.ev("(()=>{const e=document.querySelector(%s);return e?getComputedStyle(e)[%s]:null})()"
                 % (json.dumps(sel), json.dumps(prop)))


def rect(pg, sel):
    return pg.rect(sel) or {}


def main():
    fuente = open(os.path.join(ROOT, "visor.html"), encoding="utf-8").read()

    print("\n── tokens y tipografía (ref/maqueta/src/app.css)")
    pg = Page(url=API + "/", w=1440, h=900)
    time.sleep(2.2)
    check("--ink = #171717", var(pg, "--ink") == "#171717", var(pg, "--ink"))
    check("--line = #e7e7e5 y --line2 = #d4d4cf",
          var(pg, "--line") == "#e7e7e5" and var(pg, "--line2") == "#d4d4cf",
          (var(pg, "--line"), var(pg, "--line2")))
    check("--wash/--tint = #f5f5f2, --hover = #eaeae6, --fill = #e4e4e0",
          var(pg, "--wash") == "#f5f5f2" and var(pg, "--tint") == "#f5f5f2"
          and var(pg, "--hover") == "#eaeae6" and var(pg, "--fill") == "#e4e4e0")
    check("medidas de la maqueta: --ctl 34px, --grp 40px, --dock 56px",
          var(pg, "--ctl") == "34px" and var(pg, "--grp") == "40px" and var(pg, "--dock") == "56px")
    check("body: 13px / 1.5 y la familia de la maqueta",
          css(pg, "body", "fontSize") == "13px" and css(pg, "body", "lineHeight") == "19.5px"
          and css(pg, "body", "fontFamily").startswith("-apple-system"),
          (css(pg, "body", "fontSize"), css(pg, "body", "lineHeight"), css(pg, "body", "fontFamily")))
    check("fondo de la página = --wash", css(pg, "body", "backgroundColor") == "rgb(245, 245, 242)",
          css(pg, "body", "backgroundColor"))
    check("tema oscuro borrado (la réplica es a tema claro)",
          '[data-theme="dark"]{' not in fuente)
    check("sin -webkit-font-smoothing (la maqueta no lo trae)",
          "-webkit-font-smoothing" not in fuente)
    check("radios de la maqueta: tarjeta 8, control 6, pieza menuda 4",
          var(pg, "--radius") == "8px" and var(pg, "--radius-ctl") == "6px" and var(pg, "--radius-xs") == "4px")
    check("toast = el de la maqueta (negro, radio 6, 12px)",
          css(pg, "#toast", "backgroundColor") == "rgb(23, 23, 23)"
          and css(pg, "#toast", "borderRadius") == "6px" and css(pg, "#toast", "color") == "rgb(255, 255, 255)")

    print("\n── encabezado literal")
    r = rect(pg, ".topbar")
    check("cabecera de 56 px de alto, a todo el ancho",
          abs(r.get("h", 0) - 56) <= 1 and abs(r.get("w", 0) - 1440) <= 1, r)
    check("cabecera blanca con borde inferior --line",
          css(pg, ".topbar", "backgroundColor") == "rgb(255, 255, 255)"
          and css(pg, ".topbar", "borderBottomColor") == "rgb(231, 231, 229)")
    check("marca: 20 px, peso 750, tracking −1 px",
          css(pg, ".brand", "fontSize") == "20px" and css(pg, ".brand", "fontWeight") == "750"
          and css(pg, ".brand", "letterSpacing") == "-1px")
    rb = rect(pg, ".brandmark")
    check("logotipo: marco 23×23 con borde derecho de 7 px",
          abs(rb.get("w", 0) - 23) <= 1 and abs(rb.get("h", 0) - 23) <= 1
          and css(pg, ".brandmark", "borderRightWidth") == "7px"
          and css(pg, ".brandmark", "borderTopWidth") == "2px", (rb, css(pg, ".brandmark", "borderRightWidth")))
    check("migas «Proyectos / <proyecto real>»",
          pg.ev("document.querySelector('.crumb span').textContent") == "Proyectos"
          and pg.ev("document.querySelector('#crumbProj').textContent") == "Prueba X2",
          pg.ev("document.querySelector('.crumb').textContent"))
    check("píldora de pendientes con el número REAL",
          pg.ev("document.querySelector('#hdrPend').textContent")
          == pg.ev("pendientesDe(st.vid)+' pendientes'"),
          pg.ev("document.querySelector('#hdrPend').textContent"))
    check("selector «Corte vNN» con el corte real abierto",
          pg.ev("document.querySelector('#hdrCorte').textContent.trim().startsWith('Corte v')"),
          pg.ev("document.querySelector('#hdrCorte').textContent"))
    pg.click("#hdrCorte"); time.sleep(.4)
    n_vid = pg.ev("(st.videos||[]).length")
    check("el selector abre la lista REAL de cortes del proyecto",
          pg.ev("!document.querySelector('#cortePop').hidden")
          and pg.ev("document.querySelectorAll('#cortePop button').length") == n_vid,
          (pg.ev("document.querySelectorAll('#cortePop button').length"), n_vid))
    check("botón primario negro «Compartir revisión»",
          "Compartir revisión" in (pg.ev("document.querySelector('#bShare').textContent") or "")
          and css(pg, "#bShare", "backgroundColor") == "rgb(23, 23, 23)"
          and css(pg, "#bShare", "color") == "rgb(255, 255, 255)")
    pg.click("#bShare"); time.sleep(.6)
    check("«Compartir revisión» abre el popover real de invitados",
          pg.ev("!document.querySelector('#shPop').hidden"))
    pg.ev("document.querySelector('#shCerrar').click()"); time.sleep(.3)
    ra = rect(pg, "#hdrAvatar")
    check("avatar de iniciales de 28 px, redondo",
          abs(ra.get("w", 0) - 28) <= 1 and css(pg, "#hdrAvatar", "borderRadius") == "50%"
          and (pg.ev("document.querySelector('#hdrAvatar').textContent") or "").strip() == "CH")
    check("miniaturas = botón de icono que gobierna #cThumbs",
          pg.ev("(()=>{const c=document.querySelector('#cThumbs');const a=c.checked;"
                "document.querySelector('#bThumbs').click();const b=c.checked;"
                "document.querySelector('#bThumbs').click();return a!==b && c.checked===a})()"))
    print("\n── menú «⋯»: nada se perdió del encabezado viejo")
    pg.click("#hdrMore"); time.sleep(.4)
    faltan = pg.ev("JSON.stringify(['#bProj','#bClaude','#bCopy','#bOut','#sello','#conn']"
                   ".filter(s=>{const e=document.querySelector(s);return !e||e.offsetParent===null}))")
    check("Nuevo proyecto, Para Agente, Copiar, Exportar, build y «en línea» viven en el menú",
          faltan == "[]", faltan)
    check("el menú usa el popover de la maqueta (borde --line2, radio 8, su sombra)",
          css(pg, "#hdrPop", "borderTopColor") == "rgb(212, 212, 207)"
          and css(pg, "#hdrPop", "borderRadius") == "8px"
          and css(pg, "#hdrPop", "boxShadow").startswith("rgba(0, 0, 0, 0.16)"))
    pg.key("Escape"); time.sleep(.3)
    check("Escape cierra los popovers de la cabecera",
          pg.ev("document.querySelector('#hdrPop').hidden && document.querySelector('#cortePop').hidden"))
    check("iconos Lucide reales nuevos en el sprite (chevron-down, ellipsis, images)",
          'id="i-chevdown"' in fuente and 'id="i-more"' in fuente and 'id="i-images"' in fuente)

    print("\n── rejilla general")
    check("zona de trabajo con el padding de la maqueta (16 arriba/abajo, 24 a la derecha)",
          css(pg, ".workspace", "paddingTop") == "16px" and css(pg, ".workspace", "paddingBottom") == "16px"
          and css(pg, ".workspace", "paddingRight") == "24px")
    check("main-grid: dos columnas con hueco de 16 px",
          css(pg, ".main-grid", "display") == "grid" and css(pg, ".main-grid", "columnGap") == "16px"
          and len((css(pg, ".main-grid", "gridTemplateColumns") or "").split()) == 2,
          css(pg, ".main-grid", "gridTemplateColumns"))
    for w, h, esperado in ((1440, 900, 1440 * 0.29), (1600, 1000, 1600 * 0.29)):
        pg.viewport(w, h); time.sleep(2.2)
        anchoc = rect(pg, ".side").get("w", 0)
        check("Conversación mide clamp(380,29vw,460) a %dx%d" % (w, h),
              abs(anchoc - max(380, min(460, esperado))) <= 1, anchoc)
        check("el visor y Conversación tienen el mismo alto a %dx%d" % (w, h),
              abs(rect(pg, ".stage").get("h", 0) - rect(pg, ".side").get("h", -1)) <= 1,
              (rect(pg, ".stage"), rect(pg, ".side")))
        check("la página NO tiene scroll a %dx%d" % (w, h),
              pg.ev("document.documentElement.scrollHeight <= window.innerHeight + 1"),
              pg.ev("document.documentElement.scrollHeight + ' > ' + window.innerHeight"))
    check("Conversación es la tarjeta de la maqueta (blanca, borde --line, radio 8)",
          css(pg, ".side", "backgroundColor") == "rgb(255, 255, 255)"
          and css(pg, ".side", "borderTopColor") == "rgb(231, 231, 229)"
          and css(pg, ".side", "borderRadius") == "8px")

    print("\n── barra de proyectos: PLEGADA por defecto (lo que el usuario aprobó)")
    pg.viewport(1440, 900); time.sleep(2.2)
    check("arranca plegada sin nada guardado", pg.ev("document.body.classList.contains('nav-plegado')"))
    check("el asa conserva el texto vertical «proyectos» y las dos insignias",
          pg.ev("document.querySelector('#navOpen').textContent.trim().startsWith('proyectos')")
          and css(pg, "#navOpen", "writingMode") == "vertical-rl"
          and pg.ev("document.querySelector('#navNotas').offsetParent!==null"))
    pg.click("#navOpen"); time.sleep(.6)
    check("«proyectos ▸» despliega la barra", pg.ev("!document.body.classList.contains('nav-plegado')"))
    pg.click("#bNavFold"); time.sleep(.5)
    check("se vuelve a plegar", pg.ev("document.body.classList.contains('nav-plegado')"))

    print("\n── modo invitado intacto")
    ocultos = pg.ev("(()=>{document.body.classList.add('invitado');"
                    "const r=['#hdrMore','#hdrCorte','#bShare','#bProj','#bOut','#sello','.topbar .chk']"
                    ".filter(s=>{const e=document.querySelector(s);return e&&e.offsetParent!==null});"
                    "document.body.classList.remove('invitado');return JSON.stringify(r)})()")
    check("el invitado no ve ningún control de anfitrión de la cabecera", ocultos == "[]", ocultos)

    print("\n── arnés de fidelidad")
    mapa = json.load(open(os.path.join(ROOT, "tools", "fidelidad-map.json"), encoding="utf-8"))
    mios = [r for r in mapa["regiones"] if r["region"] in ("tokens", "encabezado", "rejilla")]
    n = sum(len(r["pares"]) for r in mios)
    check("fidelidad-map.json trae >= 25 pares en las regiones de R1 (%d)" % n, n >= 25, n)
    check("tools/fidelidad.py existe y declara las dos ventanas",
          os.path.exists(os.path.join(ROOT, "tools", "fidelidad.py"))
          and "(1440, 900), (1600, 1000)" in open(os.path.join(ROOT, "tools", "fidelidad.py"), encoding="utf-8").read())

    check("0 excepciones de JavaScript en toda la sesión", not pg.errors, pg.errors[:3])

    ok = sum(1 for _, v in RES if v)
    print("\n%d/%d checks" % (ok, len(RES)))
    if ok != len(RES):
        print("FALLAN: " + ", ".join(n for n, v in RES if not v))
    return 0 if ok == len(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
