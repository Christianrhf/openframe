#!/usr/bin/env python3
"""Suite de I2: compatibilidad con los datos REALES y las reglas del porte que el
modo invitado toca (hilo continuo, borrador con dibujo, deshacer/rehacer).

    cp -R /tmp/o10/datos-reales data            # solo notes.json/meta.json, sin videos
    OPENFRAME_NO_PUBLICAR=1 /usr/bin/python3 server.py --puerto 9431 &
    tools/chrome.sh start 9433
    CDP_PORT=9433 /tmp/o8/venv/bin/python tools/test-i2.py --api http://127.0.0.1:9431

Sin aleatoriedad: los mismos proyectos, los mismos numeros. Sale 1 si falla algo.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RES = []


def check(nombre, ok, detalle=""):
    RES.append((nombre, bool(ok)))
    print(("  OK  " if ok else "  FALLA ") + nombre +
          (("  -- " + str(detalle)[:260]) if (detalle and not ok) else ""))
    return bool(ok)


def http(method, url, obj=None):
    body = json.dumps(obj).encode("utf-8") if obj is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    if obj is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e)


def notas_en_disco(slug):
    p = os.path.join(DATA, slug, "notes.json")
    if not os.path.isfile(p):
        return []
    d = json.load(open(p))
    return d.get("notas", []) if isinstance(d, dict) else d


def errores_reales(pg):
    """La copia de datos reales NO trae los videos: los 404 de `media.*` y de las
    miniaturas son esperados y no son excepciones de la pagina."""
    fuera = []
    for e in pg.errors:
        s = str(e)
        if "404" in s or "Failed to load resource" in s or "net::ERR_ABORTED" in s:
            continue
        fuera.append(s)
    return fuera


def esperar_js(pg, expr, segundos=15, paso=0.3):
    fin = time.time() + segundos
    ultimo = None
    while time.time() < fin:
        ultimo = pg.ev(expr)
        if ultimo:
            return ultimo
        time.sleep(paso)
    return ultimo


# Todas las raices de la pestaña activa deben existir simultaneamente y en orden.
RECORRER = """(()=>{
  renderList();
  return JSON.stringify({ids:[...document.querySelectorAll('#list .item')].map(n=>n.dataset.id),
    filtradas:x2Filtradas().length, raices:visibleNotes().length});
})()"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:9431")
    args = ap.parse_args()
    api = args.api.rstrip("/")

    st, d = http("GET", api + "/api/proyectos")
    activos = (d or {}).get("proyectos", []) if st == 200 else []
    archivados = (d or {}).get("archivados", []) if st == 200 else []
    proyectos = list(activos) + list(archivados)
    enDisco = sorted(x for x in os.listdir(DATA)
                     if os.path.isdir(os.path.join(DATA, x)) and not x.startswith("."))
    check("server.py sirve TODOS los proyectos de los datos REALES (%d activos + %d archivados = %d en disco)"
          % (len(activos), len(archivados), len(enDisco)),
          st == 200 and len(proyectos) == len(enDisco) and len(enDisco) >= 4,
          (st, len(activos), len(archivados), enDisco))

    pg = Page(url=api + "/", w=1600, h=1000)
    time.sleep(1.6)
    check("la app abre con los datos reales sin ninguna excepcion de pagina",
          not errores_reales(pg), errores_reales(pg)[:3])

    total_disco = total_pintadas = 0
    for p in sorted(proyectos, key=lambda x: x.get("slug", "")):
        slug = p["slug"]
        pg.ev("openProject(%s)" % json.dumps(slug))
        listo = esperar_js(pg, "(st.slug === %s && st.vid) ? 'si' : ''" % json.dumps(slug), 20)
        if not check("«%s» abre con un video seleccionado" % slug, listo == "si",
                     pg.ev("JSON.stringify({slug:st.slug, vid:st.vid})")):
            continue
        # todas las notas del proyecto, no solo las del video actual
        pg.ev("st.filterVid = ''; st.x2Tab='abiertas'; st.x2Type='all'; st.x2Person='all'; "
              "st.x2Search=''; st.onlyPend=false; st.x2Drawing=false; "
              "renderList()")
        abiertas = json.loads(pg.ev(RECORRER))
        pg.ev("x2Tab('resueltas')")
        resueltas = json.loads(pg.ev(RECORRER))
        pg.ev("x2Tab('abiertas')")
        ids = abiertas["ids"] + resueltas["ids"]
        disco = notas_en_disco(slug)
        # las respuestas viajan dentro de su hilo: las raices son las tarjetas
        raices_disco = [n for n in disco if not n.get("parent")]
        delvideo = [n for n in raices_disco if n.get("video") == pg.ev("st.vid")]
        check("«%s»: Abiertas + Resueltas cubren %d notas, %d raices y %d del video abierto"
              % (slug, len(disco), len(raices_disco), len(delvideo)),
              len(ids) == len(delvideo) and abiertas["filtradas"] == len(abiertas["ids"])
              and resueltas["filtradas"] == len(resueltas["ids"]),
              (abiertas, resueltas, len(delvideo)))
        check("«%s»: cada tarjeta aparece una sola vez entre ambas pestañas" % slug,
              len(set(ids)) == len(ids), len(ids) - len(set(ids)))
        check("«%s»: caja desplazable y pagina fija" % slug,
              pg.ev("getComputedStyle(list).overflowY==='auto' && document.documentElement.scrollHeight<=innerHeight+2") is True)
        check("«%s»: sin controles de pagina" % slug,
              pg.ev("!document.querySelector('#x2Prev,#x2Next,#x2Page')") is True)
        total_disco += len(delvideo)
        total_pintadas += len(ids)
        pg.shot("i2-%s.png" % slug)

    check("en total se pintan TODAS las notas raiz de los videos abiertos (%d/%d)"
          % (total_pintadas, total_disco), total_pintadas == total_disco and total_disco > 0,
          (total_pintadas, total_disco))
    check("las notas viejas (sin end_frame/drawing/thumb) no rompen el pintado",
          not errores_reales(pg), errores_reales(pg)[:3])

    # ── notas viejas: ni un campo nuevo inventado ──
    viejas = [n for n in notas_en_disco("v02-golden-gate")
              if "drawing" not in n and "thumb" not in n]
    check("hay notas REALES sin los campos nuevos (drawing/thumb): %d" % len(viejas), len(viejas) > 0)
    pg.ev("openProject('v02-golden-gate')", await_promise=True)
    esperar_js(pg, "st.slug === 'v02-golden-gate' && st.vid ? 'si' : ''", 20)
    check("una nota vieja sin drawing se pinta sin tarjeta de dibujo y sin excepcion",
          pg.ev("(()=>{const n=st.notas.find(x=>x.video===st.vid && !x.drawing && !x.parent);"
                "if(!n) return false; x2Tab(x2Abierta(n)?'abiertas':'resueltas'); x2SeguirNota(n.id);"
                "const e=document.querySelector('.item[data-id=\"'+n.id+'\"]');"
                "return !!e && !e.querySelector('img.thumb')})()"))
    pg.ev("x2Tab('abiertas')")

    # ── reglas del hilo que el invitado tambien usa ──
    print("\n== hilo continuo: seguir solo acciones propias ==")
    # sobre el video del proyecto con MAS notas: debe desbordar la caja
    pg.ev("""(()=>{
      const cuenta = {};
      for(const n of st.notas) if(!n.parent) cuenta[n.video] = (cuenta[n.video] || 0) + 1;
      const mejor = Object.keys(cuenta).sort((a, b) => cuenta[b] - cuenta[a])[0];
      if(mejor && mejor !== st.vid) openVideo(mejor);
      return true })()""")
    esperar_js(pg, "x2Filtradas().length > 5 ? 'si' : ''", 20)
    check("hay un video real con mas de 5 notas raiz para probar el scroll",
          pg.ev("x2Filtradas().length") > 5, pg.ev("x2Filtradas().length"))
    check("todas las raices estan en el DOM simultaneamente",
          pg.ev("document.querySelectorAll('#list .item').length===x2Filtradas().length") is True)
    check("la lista tiene scroll propio", pg.ev("list.scrollHeight>list.clientHeight") is True)
    check("un id inexistente no mueve el hilo", pg.ev("x2SeguirNota('n_noexiste')===false") is True)
    pg.ev("renderList(); x2SeguirNota(x2Filtradas().at(-1).id)")
    time.sleep(.7)
    check("la ultima nota queda dentro del area visible",
          pg.ev("(()=>{const a=list.querySelector('.hilo-b:last-child .item').getBoundingClientRect(),b=list.getBoundingClientRect();return a.top>=b.top-2&&a.bottom<=b.bottom+2})()") is True)
    check("seguir una nota no anula los filtros",
          pg.ev("(()=>{const id=x2Filtradas().at(-1).id; st.x2Search='zzz-no-existe-nada';renderList();"
                "const before=list.scrollTop,m=x2SeguirNota(id),ok=m===false&&list.scrollTop===before;"
                "st.x2Search='';renderList();return ok})()") is True)
    check("x2SeguirNota(null) no hace nada", pg.ev("x2SeguirNota(null) === false"))

    # ── el aviso de llegada de invitado no se dispara con notas de Cristian ──
    pg.ev("st.x2Llegadas = []; document.getElementById('toast').textContent='';"
          "_ultimoRevVisto = st.rev; st.rev = st.rev + 1; avisarSiLlegoAlgoDeClaude(); true")
    check("sin llegadas de invitado no hay aviso de invitado",
          "Invitado" not in (pg.ev("document.getElementById('toast').textContent") or ""),
          pg.ev("document.getElementById('toast').textContent"))
    pg.ev("""st.notas.forEach(n => { if(n.author === 'claude') n._visto = true; });
             st.x2Llegadas = [{id:'n_x', author:'invitado', autor_nombre:'Marta'}];
             document.getElementById('toast').textContent='';
             _ultimoRevVisto = st.rev; st.rev = st.rev + 1; avisarSiLlegoAlgoDeClaude(); true""")
    check("una llegada de invitado avisa con su nombre",
          "Invitado · Marta" in (pg.ev("document.getElementById('toast').textContent") or ""),
          pg.ev("document.getElementById('toast').textContent"))

    # ── borrador de dibujo: Guardar se enciende ──
    print("\n== borrador con dibujo (fase 2) ==")
    r = pg.rect("#cv")
    check("el lienzo tiene medidas (hay video cargado o no, el borrador no depende de eso)",
          isinstance(r, dict), r)
    pg.ev("setDirty(false)")
    check("tras guardar, «Guardar» esta apagado", pg.ev("document.getElementById('bSave').disabled"))
    pg.ev("""(()=>{ const f = snap(v.currentTime);
      st.notas.push({id:'tmp_prueba', video:st.vid, frame:f, fps:fps, timecode:tc(f/fps,f),
                     time:f/fps, end_frame:null, text:'', kind:'nota', resolved:false,
                     author:'cristian', drawing:{strokes:[{tool:'pen', color:'#111', size:3,
                     pts:[{x:.2,y:.2},{x:.6,y:.7}]}]}, pendiente_sync:true});
      st.selId='tmp_prueba'; st.notas.sort(cmpNotas); setDirty(true); renderList(); return true })()""")
    check("un borrador con trazos enciende «Guardar» y se marca «borrador» en la lista",
          not pg.ev("document.getElementById('bSave').disabled")
          and pg.ev("(()=>{x2SeguirNota('tmp_prueba'); renderList();"
                    "const e=document.querySelector('.item[data-id=\"tmp_prueba\"]');"
                    "return !!e && !!e.querySelector('.draft-badge')})()"),
          pg.ev("document.getElementById('list').textContent"))
    check("x2Thumb del borrador devuelve un JPEG en data URL",
          (pg.ev("(()=>{const t=x2Thumb(st.notas.find(n=>n.id==='tmp_prueba'));"
                 "return t ? t.slice(0,23) : ''})()") or "").startswith("data:image/jpeg;base64,"))
    check("x2Thumb de una nota sin dibujo devuelve null",
          pg.ev("x2Thumb({drawing:{strokes:[]}}) === null && x2Thumb(null) === null"))
    pg.ev("st.notas = st.notas.filter(n=>n.id!=='tmp_prueba'); st.selId=null; "
          "setDirty(false); renderList(); true")

    # ── deshacer/rehacer del dibujo sobre la nota correcta ──
    print("\n== deshacer / rehacer del dibujo ==")
    estado = json.loads(pg.ev("""(()=>{
      const n = st.notas.find(x => !x.parent && x.video === st.vid);
      if(!n) return JSON.stringify({error:'sin notas'});
      st.selId = n.id; seek(n.frame/fps);
      n.drawing = {strokes:[]};
      pushHist(n);
      n.drawing = {strokes:[{tool:'pen', color:'#111', size:3, pts:[{x:.1,y:.1},{x:.4,y:.4}]}]};
      const conTrazo = (n.drawing.strokes||[]).length;
      undo();
      const trasUndo = (n.drawing.strokes||[]).length;
      redo();
      const trasRedo = (n.drawing.strokes||[]).length;
      return JSON.stringify({id:n.id, conTrazo:conTrazo, trasUndo:trasUndo, trasRedo:trasRedo});
    })()"""))
    check("deshacer quita el trazo y rehacer lo devuelve (redo era inalcanzable)",
          estado.get("conTrazo") == 1 and estado.get("trasUndo") == 0
          and estado.get("trasRedo") == 1, estado)
    check("rehacer sobre OTRA nota no se aplica (el redo es de la nota en la que se dibujo)",
          pg.ev("""(()=>{
            const a = st.notas.filter(x => !x.parent && x.video === st.vid);
            if(a.length < 2) return false;
            const n = a[0], otra = a[1];
            st.selId = n.id; seek(n.frame/fps);
            n.drawing = {strokes:[]}; pushHist(n);
            n.drawing = {strokes:[{tool:'pen', color:'#111', size:3, pts:[{x:.1,y:.1},{x:.4,y:.4}]}]};
            undo();
            st.selId = otra.id; seek(otra.frame/fps);
            const antes = JSON.stringify(otra.drawing || null);
            redo();
            return JSON.stringify(otra.drawing || null) === antes;
          })()"""))

    malos = [n for n, ok in RES if not ok]
    print("\n%d/%d checks" % (len(RES) - len(malos), len(RES)))
    if malos:
        print("FALLAN:")
        for n in malos:
            print("  - " + n)
    return 1 if malos else 0


if __name__ == "__main__":
    sys.exit(main())
