#!/usr/bin/env python3
"""Pruebas por CDP de la interfaz de invitados (tarea U): modo invitado, boton
«Compartir» y la insignia «Invitado · Nombre». Chrome real (headless) + los dos
servidores de prueba:

  python3 server.py --puerto 9383                       # datos del clon (proyecto zz-port)
  python3 tools/mock-inv.py --api 9383 --invitado 9384 --admin 9385
  tools/chrome.sh start 9362
  CDP_PORT=9362 uv run --quiet --with websocket-client python3 tools/test-inv.py

Deja capturas en shots/ (mirarlas con Read) y sale con 1 si falla algun check.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Page  # noqa: E402

# los puertos se pueden mover con INV_GUEST_PORT / INV_ADMIN_PORT: dos clones a la
# vez en la misma Mac chocaban en 9384/9385 (y uno probaba el visor.html del otro)
GUEST = "http://127.0.0.1:%s" % os.environ.get("INV_GUEST_PORT", "9384")
ADMIN = "http://127.0.0.1:%s" % os.environ.get("INV_ADMIN_PORT", "9385")
SLUG = "zz-port"
XSS_NOMBRE = "<img src=x onerror=window.__xss=1>"
XSS_TEXTO = "<img src=x onerror=window.__xss=2> & <b>no</b>"
XSS_ETQ = "<img src=x onerror=window.__xss=3>"
OCULTOS_INVITADO = [".rail", ".vcol", "#navhandle", "#bProj", "#bClaude", "#bCopy", "#bOut", "#bHer", "#bUp",
                    "#bShare", "#bDel", "#bMove", "#tlChg", "#vfilter", "#bUndoAccion", "#bRedoAccion",
                    "#sello", ".topbar .chk", "#plist", "#vlist"]
VISIBLES_INVITADO = ["#invBanner", "#bPlay", "#bPrev", "#bNext", "#ta", "#bSave", "#bEnd", "#bGo",
                     "[data-tool=pen]", "[data-tool=arrow]", "#swBtn", "#tlZout", "#tlZin", "#tlNear",
                     "#cPend", "#cThumb", "#bErase", "#bUndo", "#bMax", "#scrub"]

RES = []


def check(nombre, ok, detalle=""):
    RES.append((nombre, bool(ok), detalle))
    print(("  ✔ " if ok else "  ✘ ") + nombre + (("  — " + str(detalle)[:220]) if (detalle and not ok) else ""))
    return bool(ok)


def http(method, url, obj=None, raw=None):
    body = raw if raw is not None else (json.dumps(obj).encode("utf-8") if obj is not None else None)
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
            return r.status, (json.loads(txt) if txt.startswith(("{", "[")) else txt)
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, txt


def mock(cfg):
    st, d = http("POST", ADMIN + "/__mock/config", cfg)
    assert st == 200, (st, d)


def notas_upstream():
    st, d = http("GET", ADMIN + "/api/notas/" + SLUG)
    return d.get("notas", []) if st == 200 else []


def limpiar_notas():
    for n in notas_upstream():
        http("DELETE", ADMIN + "/api/proyectos/%s/notas/%s" % (SLUG, n["id"]))


def esperar(pg, expr, seg=6.0, paso=0.25):
    t0 = time.time()
    while time.time() - t0 < seg:
        v = pg.ev(expr)
        if v:
            return v
        time.sleep(paso)
    return pg.ev(expr)


def j(pg, expr):
    return pg.ev("JSON.stringify(" + expr + ")")


def sin_scroll(pg):
    return pg.ev("(()=>{const d=document.documentElement;const cajas=[...document.querySelectorAll('.topbar,.tp-row,.tlctrls,.editor,.side-head,.filter,#shPop')]"
                 ".filter(e=>e.offsetParent!==null).map(e=>({s:e.className||e.id,ok:e.scrollHeight<=e.clientHeight+1&&e.scrollWidth<=e.clientWidth+1}));"
                 "return JSON.stringify({pag:d.scrollHeight<=d.clientHeight&&d.scrollWidth<=d.clientWidth,"
                 "w:d.clientWidth,h:d.clientHeight,cajas:cajas.filter(c=>!c.ok)})})()")


def errores(pg, desde=0):
    """Excepciones y errores de consola desde el indice `desde`. Un 404 de red solo se
    tolera en los escenarios que lo producen a proposito (enlace caducado, servidor sin
    endpoints); el resto de la prueba exige cero."""
    return [e for e in pg.errors[desde:]]


def solo_404(lista):
    return all("status of 404" in str(e) for e in lista)


def overflow(pg):
    return json.loads(pg.ev("JSON.stringify({w:document.documentElement.scrollWidth,h:document.documentElement.scrollHeight})"))


def popover_cabe(pg):
    """El popover entra en la ventana, no añade desbordamiento a la pagina y ni el ni su
    lista tienen scroll interno (la fila de transporte desborda YA en la base: se mide aparte)."""
    return json.loads(pg.ev("(()=>{const p=document.querySelector('#shPop'), r=p.getBoundingClientRect(), l=p.querySelector('.shlist');"
                            "return JSON.stringify({dentro:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,"
                            "pop:p.scrollHeight<=p.clientHeight+1&&p.scrollWidth<=p.clientWidth+1,"
                            "lista:l.scrollHeight<=l.clientHeight+1, r:r.toJSON()})})()"))


# ═════════════════════════════════════════ INVITADO ═════════════════════════════════════════
def pruebas_invitado():
    print("\n── Modo invitado ──")
    limpiar_notas()
    mock({"nombre": None, "caducado": False, "ve_otras": False, "sin_endpoints": False,
          "publicada": True, "expira": None, "enlace_id": "ab12cd34"})
    http("POST", ADMIN + "/__mock/enlaces", [])
    # notas de Cristian y de Claude (el invitado no las ve hasta ve_otras)
    _, vd = http("GET", ADMIN + "/api/proyectos/" + SLUG)
    vid = vd["videos"][0]["id"]
    http("POST", ADMIN + "/api/proyectos/%s/notas" % SLUG,
         {"video": vid, "frame": 20, "text": "Nota de Cristian", "author": "cristian"})
    http("POST", ADMIN + "/api/proyectos/%s/notas" % SLUG,
         {"video": vid, "frame": 60, "text": "Nota de Claude", "author": "claude"})

    pg = Page(GUEST + "/", 1280, 800)
    time.sleep(1.5)
    check("window.__INVITADO presente y body.invitado",
          pg.ev("!!window.__INVITADO && document.body.classList.contains('invitado')"))
    check("sin nombre: dialogo «¿Como te llamas?» abierto y con foco en el campo",
          pg.ev("document.querySelector('#invDlg').classList.contains('on') && document.activeElement===document.querySelector('#invNombre') && document.querySelector('#invDlgT').textContent.includes('llamas')"),
          j(pg, "{on:document.querySelector('#invDlg').classList.contains('on'), ae:document.activeElement&&document.activeElement.id}"))
    pg.shot("inv-01-dialogo-nombre.png")
    pg.key("Escape"); time.sleep(0.2)
    pg.key("Enter"); time.sleep(0.4)
    check("Escape no cierra; Enter vacio no cierra y avisa",
          pg.ev("document.querySelector('#invDlg').classList.contains('on') && document.querySelector('#invDlgErr').textContent.length>0"),
          j(pg, "{on:document.querySelector('#invDlg').classList.contains('on'), err:document.querySelector('#invDlgErr').textContent}"))
    # nombre con HTML: debe verse LITERAL
    pg.ev("document.querySelector('#invNombre').focus()")
    pg.type(XSS_NOMBRE); pg.key("Enter")
    esperar(pg, "!document.querySelector('#invDlg').classList.contains('on')", 4)
    st_, d = http("GET", ADMIN + "/__mock/estado")
    check("Enter envia el nombre: POST /api/invitado/nombre y el dialogo se cierra",
          not pg.ev("document.querySelector('#invDlg').classList.contains('on')") and d.get("nombre") == XSS_NOMBRE,
          (d.get("nombre"),))
    check("XSS nombre: el banner lo muestra literal, sin <img>, sin ejecutar",
          pg.ev("(()=>{const b=document.querySelector('#invBanner');return b.textContent.includes(%s) && !b.querySelector('img') && window.__xss===undefined})()" % json.dumps(XSS_NOMBRE)),
          j(pg, "{t:document.querySelector('#invBanner').textContent, x:window.__xss}"))
    # ahora un nombre normal para el resto (y para las capturas)
    mock({"nombre": None}); pg.reload(); time.sleep(1.5)
    pg.ev("document.querySelector('#invNombre').focus()")
    pg.type("Ana Pérez"); pg.key("Enter")
    esperar(pg, "!document.querySelector('#invDlg').classList.contains('on')", 4)
    banner = pg.ev("document.querySelector('#invBanner').textContent")
    check("banner fijo «Revisando como Ana Pérez · zz-port · clip.mp4»",
          banner == "Revisando como Ana Pérez · zz-port · clip.mp4" and pg.ev("document.querySelector('#invBanner').offsetParent!==null"), banner)
    pg.click("#bPlay"); time.sleep(0.5)
    check("reproducir: el boton cambia a pausa y el icono existe (href «#i-pause», no «##i-pause»)",
          pg.ev("!v.paused && document.querySelector('#bPlay use').getAttribute('href')==='#i-pause' && document.querySelector('#bPlay svg').getBBox().width>0"),
          j(pg, "{p:v.paused, h:document.querySelector('#bPlay use')&&document.querySelector('#bPlay use').getAttribute('href')}"))
    pg.click("#bPlay"); pg.ev("seek(0)"); time.sleep(0.3)
    check("video cargado: un solo video, el compartido",
          pg.ev("st.vid===window.__INVITADO.video && (st.videos||[]).length===1 && document.querySelector('#fw').classList.contains('on')"),
          j(pg, "{vid:st.vid, n:(st.videos||[]).length}"))

    oc = json.loads(j(pg, "%s.map(s=>{const e=document.querySelector(s);return [s, e? e.offsetParent===null : 'NOEXISTE']})" % json.dumps(OCULTOS_INVITADO)))
    check("ocultos (offsetParent===null): proyectos, videos, subir, archivar, borrar, resolver, mover, Para Claude, heredar, exportar, compartir…",
          all(v is True for _, v in oc), [s for s, v in oc if v is not True])
    vi = json.loads(j(pg, "%s.map(s=>{const e=document.querySelector(s);return [s, e? e.offsetParent!==null : 'NOEXISTE']})" % json.dumps(VISIBLES_INVITADO)))
    check("visibles: reproducir, buscar fotograma, dibujar, nota, fin, zoom, filtros, atajos",
          all(v is True for _, v in vi), [s for s, v in vi if v is not True])
    check("ve_otras=false: no ve las notas de Cristian ni de Claude",
          pg.ev("st.notas.length===0 && document.querySelectorAll('#list .note').length===0"), j(pg, "st.notas.map(n=>n.author)"))

    # ── crear una nota con texto HTML ──
    pg.ev("document.querySelector('#ta').focus()")
    pg.type(XSS_TEXTO); pg.key("Enter")
    esperar(pg, "document.querySelectorAll('#list .note[data-who=invitado]').length>0", 5)
    check("nota creada: tarjeta con insignia «Invitado · Ana Pérez» y marcador a rayas",
          pg.ev("(()=>{const n=document.querySelector('#list .note[data-who=invitado]');return !!n && n.querySelector('.who.i').textContent==='Invitado · Ana Pérez' && !!document.querySelector('#scrub .mark.inv')})()"),
          j(pg, "{who:[...document.querySelectorAll('#list .who')].map(e=>e.textContent), marks:document.querySelectorAll('.mark').length}"))
    check("XSS texto: la nota se ve literal, sin <img>, sin ejecutar",
          pg.ev("(()=>{const t=document.querySelector('#list .note[data-who=invitado] .txt');return t.textContent===%s && !document.querySelector('#list img') && window.__xss===undefined})()" % json.dumps(XSS_TEXTO)),
          j(pg, "{t:document.querySelector('#list .txt')&&document.querySelector('#list .txt').textContent, x:window.__xss}"))
    ns = notas_upstream()
    mias = [n for n in ns if n.get("author") == "invitado"]
    check("en el servidor: author=invitado, autor_nombre=Ana Pérez, enlace_id del enlace",
          len(mias) == 1 and mias[0].get("autor_nombre") == "Ana Pérez" and mias[0].get("enlace_id") == "ab12cd34" and mias[0].get("text") == XSS_TEXTO,
          [(n.get("author"), n.get("autor_nombre"), n.get("enlace_id")) for n in ns])
    check("tarjeta del invitado: solo responder + editar (sin cerrar/mover/borrar)",
          pg.ev("(()=>{const a=document.querySelector('#list .note[data-who=invitado] .acts');return !!a.querySelector('.rp') && !!a.querySelector('.ed') && !a.querySelector('.ok') && !a.querySelector('.mv') && !a.querySelector('.del')})()"),
          j(pg, "[...document.querySelectorAll('#list .acts button')].map(b=>b.className)"))
    pg.shot("inv-02-vista-1280.png")

    # ── editar el texto de SU nota ──
    mid = mias[0]["id"]
    pg.click("#list .note[data-who=invitado] .ed"); time.sleep(0.4)
    check("editar propia: el cuadro se rellena con el texto",
          pg.ev("editingId===%s && document.querySelector('#ta').value===%s" % (json.dumps(mid), json.dumps(XSS_TEXTO))),
          j(pg, "{e:editingId, v:document.querySelector('#ta').value}"))
    pg.ev("document.querySelector('#ta').value=''; document.querySelector('#ta').focus()")
    pg.type("Texto editado por Ana"); pg.key("Enter")
    esperar(pg, "st.notas.some(n=>n.text==='Texto editado por Ana')", 5)
    n2 = next((n for n in notas_upstream() if n["id"] == mid), {})
    check("PATCH /api/notas/<slug>/<id>: el texto cambio en el servidor", n2.get("text") == "Texto editado por Ana", n2.get("text"))

    # ── tramo: «fin» antes de enviar ──
    pg.ev("seek(0); document.querySelector('#ta').focus()"); time.sleep(0.3)
    pg.type("Nota con tramo"); time.sleep(0.2)
    pg.ev("seek(2)"); time.sleep(0.4)
    pg.click("#bEnd"); time.sleep(0.3)
    check("«fin» del invitado: tramo pendiente y el cuadro lo dice (ini → fin)",
          pg.ev("!!st.invTramo && st.invTramo.fin>st.invTramo.ini && document.querySelector('#edAt').textContent.includes('→')"),
          j(pg, "{t:st.invTramo, at:document.querySelector('#edAt').textContent}"))
    pg.ev("document.querySelector('#ta').focus()"); pg.key("Enter")
    esperar(pg, "st.notas.some(n=>n.text==='Nota con tramo' && n.end_frame!=null)", 5)
    nt = next((n for n in notas_upstream() if n.get("text") == "Nota con tramo"), {})
    check("nota con tramo creada en el servidor (end_frame > frame, author invitado)",
          nt.get("end_frame") is not None and nt.get("end_frame") > nt.get("frame", 0) and nt.get("author") == "invitado",
          (nt.get("frame"), nt.get("end_frame"), nt.get("author")))

    # ── dibujar: crea nota propia con trazo ──
    pg.ev("seek(4)"); time.sleep(0.3)
    pg.click("[data-tool=pen]")
    r = json.loads(j(pg, "document.querySelector('#cv').getBoundingClientRect().toJSON()"))
    x0, y0 = r["x"] + r["width"] * 0.3, r["y"] + r["height"] * 0.3
    pg.drag(x0, y0, x0 + r["width"] * 0.3, y0 + r["height"] * 0.25, steps=10)
    esperar(pg, "st.notas.some(n=>n.author==='invitado' && !String(n.id).startsWith('tmp_') && n.frame===snap(4) && n.drawing && n.drawing.strokes && n.drawing.strokes.length>0)", 6)
    time.sleep(1.2)
    f4 = pg.ev("snap(4)")
    nd = [n for n in notas_upstream() if n.get("author") == "invitado" and n.get("frame") == f4 and (n.get("drawing") or {}).get("strokes")]
    check("dibujar crea una nota del invitado EN ESE fotograma con el trazo guardado en el servidor",
          len(nd) == 1 and len(nd[0]["drawing"]["strokes"][0].get("pts", [])) >= 2 and nd[0].get("autor_nombre") == "Ana Pérez",
          j(pg, "st.notas.filter(n=>n.drawing).map(n=>[n.id,n.author,n.frame,(n.drawing.strokes||[]).length])"))
    pg.ev("st.tool=null; $$('[data-tool]').forEach(x=>x.classList.remove('on'))")

    # ── ve_otras: ve a Cristian y Claude, no los edita, puede responder ──
    mock({"ve_otras": True}); pg.reload(); time.sleep(1.8)
    check("ve_otras=true: ve «Cristian» y «Claude» con sus chips, sin boton de editar en esas",
          pg.ev("(()=>{const c=document.querySelector('#list .note[data-who=cristian]'), k=document.querySelector('#list .note[data-who=claude]');return !!c && !!k && c.querySelector('.who').textContent==='Cristian' && k.querySelector('.who').textContent==='Claude' && !c.querySelector('.ed') && !k.querySelector('.ed')})()"),
          j(pg, "[...document.querySelectorAll('#list .note')].map(n=>[n.dataset.who, n.querySelector('.who').textContent, !!n.querySelector('.ed')])"))
    cid = pg.ev("(st.notas.find(n=>n.author==='cristian')||{}).id")
    pg.ev("startEdit(%s)" % json.dumps(cid)); time.sleep(0.2)
    check("consola: startEdit() sobre la nota de Cristian no entra en edicion", pg.ev("editingId===null"), pg.ev("editingId"))
    pg.click("#list .note[data-who=cristian] .rp"); time.sleep(0.3)
    check("responder: el cuadro entra en modo respuesta al hilo de Cristian", pg.ev("st.replyTo===%s" % json.dumps(cid)), pg.ev("st.replyTo"))
    pg.ev("document.querySelector('#ta').focus()"); pg.type("Respuesta de Ana"); pg.key("Enter")
    esperar(pg, "[...document.querySelectorAll('#list .rep .rtxt')].some(e=>e.textContent==='Respuesta de Ana')", 5)
    check("responder al hilo de Cristian: respuesta con «Invitado · Ana Pérez» bajo su nota",
          pg.ev("(()=>{const r=[...document.querySelectorAll('#list .rep')].find(x=>x.querySelector('.rtxt').textContent==='Respuesta de Ana');return !!r && r.dataset.who==='invitado' && r.querySelector('.rwho').textContent.startsWith('Invitado · Ana Pérez') && r.closest('.hilo-b').querySelector('.note').dataset.who==='cristian'})()"),
          j(pg, "[...document.querySelectorAll('#list .rep')].map(r=>[r.dataset.who, r.querySelector('.rwho').textContent, r.querySelector('.rtxt').textContent])"))
    rp = next((n for n in notas_upstream() if n.get("text") == "Respuesta de Ana"), {})
    check("en el servidor: la respuesta cuelga de la nota de Cristian (parent) con author=invitado",
          rp.get("parent") == cid and rp.get("author") == "invitado" and rp.get("autor_nombre") == "Ana Pérez", rp)

    # ── acciones ocultas: ni teclado ni consola ──
    antes = len(notas_upstream())
    pg.ev("window.confirm=()=>{window.__confirmCalled=true;return true}; window.__xx=0")
    pg.ev("askDelete(%s); nuevoProyecto(); heredarHilos(); archivarProyecto(st.slug,true); document.querySelector('#bOut').click(); document.querySelector('#bClaude').click(); document.querySelector('#bUp').click(); selectNoteById(%s)" % (json.dumps(cid), json.dumps(cid)))
    time.sleep(0.4)
    check("consola: borrar/nuevo proyecto/heredar/archivar/exportar/Para Claude/subir/mover no abren nada",
          pg.ev("!document.querySelector('#modal').classList.contains('on') && !window.__confirmCalled"),
          j(pg, "{modal:document.querySelector('#modal').className, c:window.__confirmCalled}"))
    pg.ev("toggleRes(%s); marcarCambioVisto({id:'x',kind:'cambio'}); deshacer(); rehacer()" % json.dumps(cid))
    pg.ev("document.body.focus()"); pg.key("N"); pg.key("P"); pg.key("z", meta=True); pg.key("z", ctrl=True, shift=True)
    time.sleep(1.0)
    ns2 = notas_upstream()
    cn = next((n for n in ns2 if n["id"] == cid), {})
    check("consola/teclado: resolver, visto, deshacer, rehacer, ⇧N/⇧P no cambian nada en el servidor",
          len(ns2) == antes and not cn.get("resolved") and not pg.ev("document.querySelector('#modal').classList.contains('on')"),
          (len(ns2), antes, cn.get("resolved")))
    check("atajos ocultos: ninguna accion de Cristian tiene tecla viva (deshacer/N/P guardados)",
          pg.ev("(()=>{try{ irACambio(1); return st.selId!=='x'; }catch(e){ return 'EXC '+e.message } })()") is True)

    check("cero errores de consola en toda la sesion del invitado (antes de caducar)", not errores(pg), errores(pg))
    # ── caducidad a mitad de sesion ──
    n_err = len(pg.errors)
    mock({"caducado": True})
    esperar(pg, "document.body.classList.contains('inv-caducado')", 8)
    check("enlace caducado a mitad de sesion: aviso «Este enlace caducó» y escritura apagada",
          pg.ev("document.body.classList.contains('inv-caducado') && document.querySelector('#invBanner').textContent.startsWith('Este enlace caducó') && document.querySelector('#ta').disabled && document.querySelector('#bSave').disabled"),
          j(pg, "{cls:document.body.className, b:document.querySelector('#invBanner').textContent, ta:document.querySelector('#ta').disabled}"))
    pg.ev("document.body.focus()"); pg.key("s"); pg.key("e"); pg.ev("saveNote(); startReply(%s)" % json.dumps(cid)); time.sleep(0.5)
    check("caducado: saveNote()/startReply()/atajos no escriben", pg.ev("st.replyTo===null && editingId===null"), j(pg, "{r:st.replyTo,e:editingId}"))
    pg.shot("inv-03-caducado.png")
    check("sin scroll de pagina ni de cajas a 1280×800 (invitado)", json.loads(sin_scroll(pg))["pag"] and not json.loads(sin_scroll(pg))["cajas"], sin_scroll(pg))
    check("caducado: solo el 404 esperado de la puerta en consola, ninguna excepcion", solo_404(errores(pg, n_err)), errores(pg, n_err))
    mock({"caducado": False})
    for (w, h) in ((1440, 900), (1600, 1000)):
        pg.viewport(w, h, reload=True, clear_storage=False); time.sleep(1.6)
        s = json.loads(sin_scroll(pg))
        check("sin scroll a %d×%d (invitado)" % (w, h), s["pag"] and not s["cajas"] and s["w"] == w, s)
        pg.shot("inv-04-vista-%dx%d.png" % (w, h))
    return pg


# ═════════════════════════════════════════ CRISTIAN ═════════════════════════════════════════
def pruebas_cristian():
    print("\n── Cristian: Compartir e insignia ──")
    mock({"sin_endpoints": False, "publicada": True, "caducado": False})
    http("POST", ADMIN + "/__mock/enlaces", [])
    pg = Page(ADMIN + "/", 1280, 800)
    time.sleep(2.0)
    ov0 = overflow(pg)
    check("sin __INVITADO: vista normal, boton Compartir (share-2) en la cabecera del video, sin banner",
          pg.ev("!document.body.classList.contains('invitado') && document.querySelector('.vcol-head #bShare').offsetParent!==null && document.querySelector('#bShare use').getAttribute('href')==='#i-share2' && document.querySelector('#invBanner').offsetParent===null"))
    check("insignia en la vista de Cristian: «Invitado · Ana Pérez» distinta de «Tú» y «Claude»; marcador a rayas",
          pg.ev("(()=>{const w=[...document.querySelectorAll('#list .note .who')].map(e=>e.className+'|'+e.textContent);return w.includes('who i|Invitado · Ana Pérez') && w.includes('who y|Tú') && w.includes('who c|Claude') && !!document.querySelector('#scrub .mark.inv') && !!document.querySelector('#list .rep[data-who=invitado]')})()"),
          j(pg, "[...document.querySelectorAll('#list .note .who')].map(e=>e.className+'|'+e.textContent)"))
    check("Cristian conserva cerrar/mover/borrar sobre la nota del invitado",
          pg.ev("(()=>{const a=document.querySelector('#list .note[data-who=invitado] .acts');return !!a.querySelector('.ok') && !!a.querySelector('.mv') && !!a.querySelector('.del')})()"))
    r = json.loads(j(pg, "document.querySelector('#list .note[data-who=invitado]').getBoundingClientRect().toJSON()"))
    pg.shot("cri-01-tarjeta-insignia.png", clip=(r["x"] - 2, r["y"] - 2, r["width"] + 4, r["height"] + 4))

    # popover vacio
    pg.click("#bShare"); time.sleep(0.9)
    check("popover Compartir vacio: abierto bajo el boton, «Puerta cerrada», sin enlaces",
          pg.ev("(()=>{const p=document.querySelector('#shPop'), b=document.querySelector('#bShare').getBoundingClientRect(), r=p.getBoundingClientRect();return !p.hidden && r.top>=b.bottom && !!p.querySelector('.shempty') && document.querySelector('#shEstado').textContent.startsWith('Puerta cerrada') && document.querySelector('#bShare').getAttribute('aria-expanded')==='true'})()"),
          j(pg, "{h:document.querySelector('#shPop').hidden, est:document.querySelector('#shEstado').textContent, n:document.querySelectorAll('.shlink').length}"))
    pg.shot("cri-02-popover-vacio.png")
    # crear
    pg.send("Browser.grantPermissions", origin=ADMIN, permissions=["clipboardReadWrite", "clipboardSanitizedWrite"])
    pg.ev("document.querySelector('#shEtq').focus()"); pg.type("Ana")
    pg.ev("document.querySelector('#shDias').value='7'")
    pg.click("#shCrear")
    esperar(pg, "document.querySelectorAll('.shlink').length>0", 5)
    st_, d = http("GET", ADMIN + "/api/proyectos/%s/videos/%s/invitar" % (SLUG, pg.ev("st.vid")))
    check("crear enlace: POST /invitar con dias/etiqueta/ve_otras; la URL aparece y la lista tiene 1 activo",
          pg.ev("(()=>{const u=document.querySelector('#shNuevo .shurl');return !!u && u.textContent.startsWith('https://openframe.inspiredink.space/r/') && document.querySelectorAll('.shlink[data-estado=activo]').length===1 && document.querySelector('#shEstado').textContent.startsWith('Puerta abierta')})()") and len(d.get("enlaces", [])) == 1 and d["enlaces"][0]["etiqueta"] == "Ana",
          (j(pg, "{u:(document.querySelector('#shNuevo .shurl')||{}).textContent, est:document.querySelector('#shEstado').textContent}"), d))
    pg.click("#shNuevo .btn"); time.sleep(0.5)
    tt = pg.ev("document.querySelector('#toast').textContent")
    check("Copiar: portapapeles + aviso («Enlace copiado»)", tt == "Enlace copiado", tt)
    # dos enlaces mas: uno caducado y uno revocado (+ etiqueta con HTML)
    eid = d["enlaces"][0]["id"]
    ayer = "2026-10-02T10:00:00Z"
    http("POST", ADMIN + "/__mock/enlaces", [
        dict(d["enlaces"][0], usos=3, token="t1", slug=SLUG, vid=pg.ev("st.vid")),
        {"id": "ab12cd34", "token": "t2", "url": "https://openframe.inspiredink.space/r/t2", "creado": "2026-09-20T10:00:00Z",
         "expira": ayer, "revocado": False, "etiqueta": XSS_ETQ, "ve_otras": True, "usos": 12, "ultimo_uso": ayer,
         "slug": SLUG, "vid": pg.ev("st.vid")},
        {"id": "ffee0011", "token": "t3", "url": "https://openframe.inspiredink.space/r/t3", "creado": "2026-09-25T10:00:00Z",
         "expira": "2026-10-20T10:00:00Z", "revocado": True, "etiqueta": "Luis (revisor externo)", "ve_otras": False,
         "usos": 1, "ultimo_uso": None, "slug": SLUG, "vid": pg.ev("st.vid")},
    ])
    pg.key("Escape"); time.sleep(0.3)
    check("Escape cierra el popover", pg.ev("document.querySelector('#shPop').hidden"))
    pg.click("#bShare"); esperar(pg, "document.querySelectorAll('.shlink').length===3", 5)
    filas = json.loads(j(pg, "[...document.querySelectorAll('.shlink')].map(r=>({e:r.dataset.estado, etq:r.querySelector('.shetq').textContent, m:r.querySelector('.shm').textContent, btns:[...r.querySelectorAll('button')].map(b=>b.textContent)}))"))
    por = {f["e"]: f for f in filas}
    n_inv = len([n for n in notas_upstream() if n.get("enlace_id") == "ab12cd34"])
    check("lista con 3 enlaces: activo / caducado / revocado, con usos y nº de notas; solo el activo tiene Copiar y Revocar",
          set(por) == {"activo", "caducado", "revocado"} and por["activo"]["btns"] == ["Copiar", "Revocar"] and por["caducado"]["btns"] == [] and por["revocado"]["btns"] == []
          and "3 usos" in por["activo"]["m"] and ("%d notas" % n_inv) in por["caducado"]["m"] and "12 usos" in por["caducado"]["m"],
          filas)
    check("XSS etiqueta: se ve literal, sin <img>, sin ejecutar",
          por.get("caducado", {}).get("etq") == XSS_ETQ and pg.ev("!document.querySelector('#shPop img') && window.__xss===undefined"), por.get("caducado"))
    pg.shot("cri-03-popover-3-enlaces.png")
    c = popover_cabe(pg)
    check("popover con 3 enlaces a 1280×800: dentro de la ventana, sin scroll interno, sin desbordar la pagina",
          c["dentro"] and c["pop"] and c["lista"] and overflow(pg) == ov0, (c, ov0, overflow(pg)))
    # revocar en dos pasos
    pg.click(".shlink[data-estado=activo] [data-rev]"); time.sleep(0.3)
    st1, d1 = http("GET", ADMIN + "/api/proyectos/%s/videos/%s/invitar" % (SLUG, pg.ev("st.vid")))
    arm = pg.ev("(()=>{const b=document.querySelector('.shlink[data-estado=activo] [data-rev]');return !!b && b.textContent==='¿Revocar?' && b.classList.contains('confirmar')})()")
    check("Revocar: el primer clic solo arma el boton («¿Revocar?»), nada se revoca aun",
          arm and not next(e for e in d1["enlaces"] if e["id"] == eid)["revocado"], (arm, d1))
    pg.click(".shlink[data-estado=activo] [data-rev]")
    esperar(pg, "document.querySelectorAll('.shlink[data-estado=activo]').length===0", 5)
    st2, d2 = http("GET", ADMIN + "/api/proyectos/%s/videos/%s/invitar" % (SLUG, pg.ev("st.vid")))
    check("Revocar: el segundo clic hace DELETE /invitar/<id>; queda revocado y «Puerta cerrada»",
          next(e for e in d2["enlaces"] if e["id"] == eid)["revocado"] and pg.ev("document.querySelectorAll('.shlink[data-estado=revocado]').length===2 && document.querySelector('#shEstado').textContent.startsWith('Puerta cerrada')"),
          (d2, pg.ev("document.querySelector('#shEstado').textContent")))
    pg.shot("cri-04-popover-revocado.png")
    # clic fuera cierra
    pg.click_xy(640, 400); time.sleep(0.3)
    check("clic fuera cierra el popover", pg.ev("document.querySelector('#shPop').hidden"))
    check("cero errores de consola hasta aqui (Cristian)", not errores(pg), errores(pg))
    # servidor sin endpoints
    n_err = len(pg.errors)
    mock({"sin_endpoints": True})
    pg.click("#bShare"); esperar(pg, "document.querySelector('#shEstado').textContent.includes('aún no admite')", 5)
    check("servidor sin endpoints (404): una linea lo dice, crear deshabilitado, nada se rompe",
          pg.ev("document.querySelector('#shEstado').textContent==='El servidor aún no admite enlaces de invitado.' && document.querySelector('#shCrear').disabled && !document.querySelector('#shPop').hidden"),
          pg.ev("document.querySelector('#shEstado').textContent"))
    pg.shot("cri-05-popover-sin-endpoints.png")
    pg.key("Escape")
    mock({"sin_endpoints": False})
    # el sondeo repinta: una nota nueva del invitado aparece sola
    antes = pg.ev("document.querySelectorAll('#list .note').length")
    mock({"nombre": "Ana Pérez", "caducado": False})
    http("POST", GUEST + "/api/proyectos/%s/notas" % SLUG, {"video": pg.ev("st.vid"), "frame": 90, "text": "Llego por el sondeo"})
    esperar(pg, "[...document.querySelectorAll('#list .txt')].some(e=>e.textContent==='Llego por el sondeo')", 8)
    check("el sondeo pinta la nota nueva del invitado sin tocar nada (arreglo de `dibujando`)",
          pg.ev("[...document.querySelectorAll('#list .txt')].some(e=>e.textContent==='Llego por el sondeo')") and pg.ev("document.querySelectorAll('#list .note').length") == antes + 1,
          (antes, pg.ev("document.querySelectorAll('#list .note').length")))
    check("servidor sin endpoints: solo el 404 esperado en consola, ninguna excepcion", solo_404(errores(pg, n_err)), errores(pg, n_err))
    for (w, h) in ((1440, 900), (1600, 1000)):
        pg.viewport(w, h, reload=True, clear_storage=False); time.sleep(1.8)
        ov = overflow(pg)
        pg.click("#bShare"); time.sleep(0.8)
        c = popover_cabe(pg)
        check("popover a %d×%d: dentro de la ventana, sin scroll interno, sin desbordar la pagina" % (w, h),
              c["dentro"] and c["pop"] and c["lista"] and overflow(pg) == ov and ov["w"] == w, (c, ov, overflow(pg)))
        pg.shot("cri-06-popover-%dx%d.png" % (w, h))
        pg.key("Escape")
    return pg


def main():
    t0 = time.time()
    pruebas_invitado()
    pruebas_cristian()
    ok = sum(1 for _, o, _ in RES if o)
    print("\n%d/%d checks OK en %.0f s · capturas en shots/" % (ok, len(RES), time.time() - t0))
    for n, o, d in RES:
        if not o:
            print("  FALLO:", n, "—", str(d)[:400])
    sys.exit(0 if ok == len(RES) else 1)


if __name__ == "__main__":
    main()
