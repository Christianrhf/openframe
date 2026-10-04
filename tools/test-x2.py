#!/usr/bin/env python3
"""Regresión CDP de X2 contra el proyecto sintético ``prueba-x2``.

Requiere server.py en 9421 y Chrome CDP en 9422. No usa ni crea datos reales.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page  # noqa: E402


checks = []


def check(name, value, detail=""):
    ok = bool(value)
    checks.append(ok)
    print(("✔ " if ok else "✘ ") + name + ((" — " + str(detail)) if detail and not ok else ""))


def metric(pg):
    return json.loads(pg.ev("JSON.stringify({page:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],"
                            "view:[innerWidth,innerHeight],list:[list.clientWidth,list.scrollWidth,list.clientHeight,list.scrollHeight],"
                            "side:[document.querySelector('.side').clientWidth,document.querySelector('.side').scrollWidth],"
                            "stage:[document.querySelector('.stage').clientWidth,document.querySelector('.stage').scrollWidth],"
                            "pageText:hiloCount.textContent,cards:list.querySelectorAll('.hilo-b').length})"))


def main():
    pg = Page("http://127.0.0.1:9421/", 1280, 800)
    pg.ev("[...document.querySelectorAll('.pitem')].find(e=>e.textContent.includes('Prueba X2'))?.click()")
    time.sleep(.5)
    for w, h in ((1280, 800), (1440, 900), (1600, 1000)):
        pg.viewport(w, h, clear_storage=False)
        pg.ev("[...document.querySelectorAll('.pitem')].find(e=>e.textContent.includes('Prueba X2'))?.click()")
        time.sleep(.35)
        m = metric(pg)
        check("scroll solo en el hilo %dx%d" % (w, h), m["page"] == m["view"] and m["list"][0] == m["list"][1]
              and m["list"][3] > m["list"][2] and m["side"][0] == m["side"][1]
              and m["stage"][0] == m["stage"][1], m)
        check("hilo completo y contador %dx%d" % (w, h), m["pageText"] == "11 de 11" and m["cards"] == 11, m)
        check("sin controles de pagina %dx%d" % (w, h), pg.ev("!document.querySelector('#x2Prev,#x2Next,#x2Page')") is True)
        pg.ev("saltarANota(x2Filtradas().at(-1).id)")
        time.sleep(.7)
        check("seleccion visible %dx%d" % (w, h), pg.ev("(()=>{const a=list.querySelector('.note.on').getBoundingClientRect(),b=list.getBoundingClientRect();return a.top>=b.top-2&&a.bottom<=b.bottom+2})()") is True)
        pg.shot("x2-%dx%d.png" % (w, h))

    pg.ev("x2Search.value='Cambio aplicado 4';x2Search.dispatchEvent(new Event('input',{bubbles:true}))")
    check("busqueda N de M", pg.ev("list.querySelectorAll('.hilo-b').length===1 && hiloCount.textContent==='1 de 11'"))
    pg.ev("x2Search.value='';x2Search.dispatchEvent(new Event('input',{bubbles:true}))")
    pg.ev("x2Type.value='cambio';x2Type.dispatchEvent(new Event('change',{bubbles:true}))")
    check("filtro de cambios", pg.ev("[...list.querySelectorAll('.note')].every(e=>e.classList.contains('change'))"))
    pg.ev("x2Type.value='all';x2Type.dispatchEvent(new Event('change',{bubbles:true}))")

    check("rotulo Agente", pg.ev("document.body.innerText.includes('Agente') && !document.body.innerText.includes('Claude')"))
    check("numeros Nota/A", pg.ev("!![...list.querySelectorAll('.note')].find(e=>/Nota \\d|A\\d/.test(e.innerText))"))
    check("cero excepciones de pagina", not pg.errors, pg.errors)
    print("\n%d/%d checks" % (sum(checks), len(checks)))
    raise SystemExit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
