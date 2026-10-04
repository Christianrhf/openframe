#!/usr/bin/env python3
"""Suite R2 · navegación de proyectos/videos en el lenguaje de la maqueta.

    OPENFRAME_NO_PUBLICAR=1 /tmp/o8/venv/bin/python server.py --puerto 9511 &
    /tmp/o8/venv/bin/python tools/setup-x2.py --api http://127.0.0.1:9511
    tools/chrome.sh start 9512
    CDP_PORT=9512 /tmp/o8/venv/bin/python tools/test-R2.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.environ.get("R2_API", "http://127.0.0.1:9511")
RES = []


def check(nombre, ok, detalle=""):
    RES.append((nombre, bool(ok)))
    print(("  ✔ " if ok else "  ✘ ") + nombre
          + (("  — " + str(detalle)[:220]) if detalle and not ok else ""))


def css(pg, sel, prop):
    return pg.ev("(()=>{const e=document.querySelector(%s);return e?getComputedStyle(e)[%s]:null})()"
                 % (json.dumps(sel), json.dumps(prop)))


def rect(pg, sel):
    return pg.rect(sel) or {}


def main():
    print("\n── estado plegado aprobado")
    pg = Page(url=API + "/", w=1440, h=900)
    time.sleep(2.4)
    pg.ev("localStorage.removeItem('openframe:nav')")
    pg.send("Page.reload", ignoreCache=True)
    time.sleep(2.4)
    check("arranca plegada sin preferencia guardada",
          pg.ev("document.body.classList.contains('nav-plegado')"))
    check("rail y videos no consumen ancho ni margen al plegarse",
          rect(pg, ".rail").get("w", -1) == 0 and rect(pg, ".vcol").get("w", -1) == 0
          and css(pg, ".rail", "marginLeft") == "0px" and css(pg, ".vcol", "marginLeft") == "0px")
    check("el asa mide 30 px y queda visible", abs(rect(pg, "#navhandle").get("w", 0) - 30) <= 1
          and pg.ev("document.querySelector('#navhandle').offsetParent!==null"), rect(pg, "#navhandle"))
    check("texto vertical literal «proyectos ▸»",
          pg.ev("document.querySelector('#navOpen').textContent.trim()") == "proyectos ▸"
          and css(pg, "#navOpen", "writingMode") == "vertical-rl")
    check("insignias de notas y cambios siguen en el asa",
          pg.ev("!!document.querySelector('#navNotas') && !!document.querySelector('#navChg')"))
    check("workspace conserva 54 px a la izquierda",
          css(pg, ".workspace", "paddingLeft") == "54px", css(pg, ".workspace", "paddingLeft"))

    print("\n── paneles desplegados")
    pg.click("#navOpen")
    time.sleep(.7)
    check("el asa despliega ambos paneles", not pg.ev("document.body.classList.contains('nav-plegado')"))
    check("la preferencia abierta se recuerda", pg.ev("localStorage.getItem('openframe:nav')") == "abierto")
    check("el asa desaparece al desplegar", pg.ev("document.querySelector('#navhandle').offsetParent===null"))
    for sel, nombre in ((".rail", "Proyectos"), (".vcol", "Videos")):
        check("panel %s = tarjeta blanca de la maqueta" % nombre,
              css(pg, sel, "backgroundColor") == "rgb(255, 255, 255)"
              and css(pg, sel, "borderTopColor") == "rgb(231, 231, 229)"
              and css(pg, sel, "borderRadius") == "8px")
        check("panel %s respeta margen base de 16 px" % nombre,
              css(pg, sel, "marginTop") == "16px" and css(pg, sel, "marginLeft") == "16px")
    check("títulos visibles en español",
          pg.ev("document.querySelector('.rail-head h2').textContent") == "Proyectos"
          and pg.ev("document.querySelector('.vcol-head h3').textContent") == "Videos")
    check("títulos usan 13 px / 650",
          css(pg, ".rail-head h2", "fontSize") == "13px"
          and css(pg, ".rail-head h2", "fontWeight") == "650"
          and css(pg, ".vcol-head h3", "fontWeight") == "650")
    check("el nombre real del proyecto figura bajo Videos",
          pg.ev("document.querySelector('#vcolName').textContent") == "Prueba X2")

    print("\n── acciones conservadas")
    check("acciones visibles: Nuevo proyecto, Traer hilos y Subir video",
          pg.ev("document.querySelector('#bProj2').textContent.trim()") == "Nuevo proyecto"
          and pg.ev("document.querySelector('#bHer').textContent.trim()") == "Traer hilos"
          and pg.ev("document.querySelector('#bUp').textContent.trim()") == "Subir video")
    check("botones principales miden 34 px",
          all(abs(rect(pg, s).get("h", 0) - 34) <= 1 for s in ("#bProj2", "#bHer", "#bUp")))
    check("botón de plegar mide al menos 28×28",
          rect(pg, "#bNavFold").get("w", 0) >= 28 and rect(pg, "#bNavFold").get("h", 0) >= 28)
    pg.click("#bProj2")
    time.sleep(.25)
    check("Nuevo proyecto conserva su función real",
          pg.ev("document.querySelector('#modal').classList.contains('on')")
          and pg.ev("document.querySelector('#mTitle').textContent") == "Nuevo proyecto")
    pg.click("#mClose")
    pg.click("#bHer")
    time.sleep(.25)
    check("Traer hilos conserva respuesta funcional",
          "dos versiones" in (pg.ev("document.querySelector('#toast').textContent") or ""))

    print("\n── tarjetas y datos reales")
    check("se renderiza el proyecto activo", pg.ev("document.querySelectorAll('.pitem.on').length") == 1)
    check("tarjeta de proyecto: borde/radio/padding de .item",
          css(pg, ".pitem.on", "borderRadius") == "8px"
          and css(pg, ".pitem.on", "paddingTop") == "9px"
          and css(pg, ".pitem.on", "paddingLeft") == "14px")
    check("selección = un contorno negro de 2 px",
          css(pg, ".pitem.on", "borderTopColor") == "rgb(23, 23, 23)"
          and "1px" in (css(pg, ".pitem.on", "boxShadow") or ""))
    check("proyecto expone conteos y estado del corte",
          pg.ev("document.querySelector('.pitem .pmeta').textContent.includes('video')")
          and pg.ev("document.querySelector('.pitem .pmeta').textContent.includes('nota')")
          and pg.ev("!!document.querySelector('.pitem .pest')"))
    check("estado del corte usa píldora literal",
          css(pg, ".pitem .pest", "minHeight") == "28px"
          and css(pg, ".pitem .pest", "borderRadius") == "99px"
          and css(pg, ".pitem .pest", "fontSize") == "11px")
    check("archivar es un objetivo 28×28",
          css(pg, ".parch", "width") == "28px" and css(pg, ".parch", "height") == "28px")
    check("tarjeta de proyecto es operable por teclado",
          pg.ev("document.querySelector('.pitem').tabIndex===0 && document.querySelector('.pitem').getAttribute('role')==='button'"))
    check("se renderiza el video activo", pg.ev("document.querySelectorAll('.vitem.on').length") == 1)
    check("tarjeta de video replica .item",
          css(pg, ".vitem.on", "paddingTop") == "9px"
          and css(pg, ".vitem.on", "paddingRight") == "14px"
          and css(pg, ".vitem.on", "borderRadius") == "8px")
    check("video muestra datos técnicos reales",
          bool((pg.ev("document.querySelector('.vitem .vc').textContent") or "").strip()))
    check("barra de notas expone progreso accesible",
          pg.ev("document.querySelector('.bar').getAttribute('role')") == "progressbar"
          and pg.ev("document.querySelector('.bar').hasAttribute('aria-valuenow')"))
    check("tarjeta de video es operable por teclado",
          pg.ev("document.querySelector('.vitem').tabIndex===0 && document.querySelector('.vitem').getAttribute('role')==='button'"))

    print("\n── contratos")
    mapa = json.load(open(os.path.join(ROOT, "tools", "fidelidad-map.json"), encoding="utf-8"))
    regiones = [r for r in mapa["regiones"] if r["region"] == "navegacion"]
    check("mapa R2 declara al menos 15 pares", len(regiones) == 1 and len(regiones[0]["pares"]) >= 15,
          len(regiones[0]["pares"]) if regiones else 0)
    check("la página completa sigue sin scroll",
          pg.ev("document.documentElement.scrollHeight <= window.innerHeight + 1"),
          pg.ev("document.documentElement.scrollHeight + ' / ' + innerHeight"))
    check("modo invitado oculta navegación y acciones de anfitrión",
          pg.ev("(()=>{document.body.classList.add('invitado');const ok=['.rail','.vcol','#navhandle','#bProj2','#bHer','#bUp'].every(s=>document.querySelector(s).offsetParent===null);document.body.classList.remove('invitado');return ok})()"))
    pg.click("#bNavFold")
    time.sleep(.25)
    check("plegar restaura el estado aprobado", pg.ev("document.body.classList.contains('nav-plegado')"))
    check("la preferencia plegada se recuerda", pg.ev("localStorage.getItem('openframe:nav')") == "plegado")
    check("0 excepciones JavaScript", not pg.errors, pg.errors[:3])

    ok = sum(1 for _, value in RES if value)
    print("\n%d/%d checks" % (ok, len(RES)))
    if ok != len(RES):
        print("FALLAN: " + ", ".join(name for name, value in RES if not value))
    return 0 if ok == len(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
