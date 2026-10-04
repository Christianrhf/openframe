#!/usr/bin/env python3
"""Hilo continuo: fixture determinista de 160 raices, anfitrion y puerta real.

Server 9491 / guest 9492 / Chrome 9493. Sin paquetes nuevos; usa tools/cdp.py.
Arranca y recoge sus propios procesos en finally. --static omite API y navegador.
Comprueba geometria a 1280x800, 1440x900 y 1600x1000, seleccion, creacion,
respuestas, filtros, orden, sondeo, rendimiento y excepciones (>25 checks).
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
API = 'http://127.0.0.1:9491'
GATE = 'http://127.0.0.1:9492'
CDP = 'http://127.0.0.1:9493'
CHECKS, PROCS, HANDLES, PAGES = [], [], [], []
os.environ['CDP_PORT'] = '9493'
os.environ['OPENFRAME_NO_PUBLICAR'] = '1'


def check(label, result, detail=''):
    ok = result is True
    CHECKS.append(ok)
    print(('✔ ' if ok else '✘ ') + label + (f' — {detail}' if detail else ''), flush=True)
    return ok


def request(base, method, path, body=None, headers=None):
    headers = dict(headers or {})
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base + path, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def ready(base, path):
    try:
        request(base, 'GET', path)
        return True
    except (OSError, ValueError):
        return False


def start(args, label, base, path):
    handle = (ROOT / 'logs' / f'hilo-{label}.log').open('w')
    HANDLES.append(handle)
    proc = subprocess.Popen(args, cwd=ROOT, env=dict(os.environ), stdout=handle, stderr=subprocess.STDOUT)
    PROCS.append(proc)
    for _ in range(80):
        if proc.poll() is not None:
            raise RuntimeError(f'{label} no arranco (codigo {proc.returncode})')
        if ready(base, path):
            return
        time.sleep(.1)
    raise RuntimeError(f'{label} no responde en {base}')


def wait_js(pg, expression, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = pg.ev(expression, await_promise=True)
        if value is True:
            return True
        if isinstance(value, str) and value.startswith(('EXC:', 'JSERR')):
            raise AssertionError(value)
        time.sleep(.1)
    return False


def visible(pg, selector):
    return pg.ev('''(()=>{const n=document.querySelector(%s);if(!n)return false;
      const a=n.getBoundingClientRect(),b=list.getBoundingClientRect();
      return a.height>0&&a.top>=b.top-2&&a.bottom<=b.bottom+2})()''' % json.dumps(selector))


def static():
    html = (ROOT / 'visor.html').read_text()
    script = re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.S)
    check('un unico bloque script sin dependencias externas', len(script) == 1 and '<script src=' not in html)
    parsed = subprocess.run(['node', '--check'], input=script[0], text=True, capture_output=True)
    check('JavaScript completo compila', parsed.returncode == 0, parsed.stderr.strip())
    for token in ('x2Page', 'x2Prev', 'x2Next', 'x2Size', 'x2OlvidarTamano', 'x2PaginaDe', 'x2SeguirLlegadas'):
        check('sin estado/UI/medicion ' + token, token not in html)
    old = subprocess.check_output(['git', 'show', '84d68cc:visor.html'], cwd=ROOT, text=True)
    def comparator(text):
        return text.split('function cmpNotas(', 1)[1].split('function visibleNotes(', 1)[0].strip()
    check('comparador identico al orden anterior 84d68cc', comparator(html) == comparator(old))
    check('fallback de rendimiento tiene ambas propiedades CSS',
          'content-visibility:auto;contain-intrinsic-size:' in html)
    check('contador conserva N de M sin pagina', 'id="hiloCount"' in html and '" de " + todos.length' in html)


def fixture():
    project = request(API, 'POST', '/api/proyectos', {'nombre': 'Prueba Hilo', 'cliente': 'QA'})
    slug = project['slug']
    path = '/api/proyectos/' + slug
    video = request(API, 'POST', path + '/videos', (ROOT / 'clip.mp4').read_bytes(),
                    {'X-Filename': 'hilo.mp4', 'Content-Type': 'application/octet-stream'})['video']['id']
    link = request(API, 'POST', path + f'/videos/{video}/invitar',
                   {'dias': 7, 'etiqueta': 'Hilo', 've_otras': False})
    # IDs, contenido y orden de entrada fijos; el servidor solo asigna slug/video/token.
    notes = [dict(id=f'h{i:03d}', video=video, frame=i % 120, text=f'HILO {i:03d} texto de prueba',
                  timecode=f'00:00:{(i % 120) // 24:02d}:{i % 24:02d}', author='invitado', autor_nombre='Hilo',
                  enlace_id=link['id'], created=f'2026-01-01T00:{i // 60:02d}:{i % 60:02d}',
                  resolved=False, drawing={'strokes': []}) for i in range(160)]
    notes[15]['resolved'] = True
    notes[50]['drawing'] = {'strokes': [{'tool': 'pen', 'color': '#111', 'size': 3, 'pts': [{'x': .2, 'y': .2}, {'x': .5, 'y': .5}]}]}
    notes[159]['text'] += '\n' + ('Linea larga de revision. ' * 12)
    notes += [dict(notes[0], id='r001', parent='h000', text='Respuesta anidada', author='cristian'),
              dict(notes[0], id='a001', frame=125, kind='cambio', author='claude', text='Cambio del Agente'),
              dict(notes[0], id='privada', frame=126, author='cristian', text='Solo anfitrion')]
    for n in notes[160:]:
        n.pop('enlace_id', None)
        n.pop('autor_nombre', None)
    # Fixture en SU proyecto, antes de abrir el navegador; ninguna escritura de produccion.
    (ROOT / 'data' / slug / 'notes.json').write_text(json.dumps(notes))
    data = request(API, 'GET', path)
    check('fixture de 163 registros guardada', len(data['notas']) == 163)
    check('162 raices y 1 respuesta', sum(not n.get('parent') for n in data['notas']) == 162)
    check('160 raices del invitado', sum(n.get('author') == 'invitado' for n in data['notas']) == 160)
    check('respuesta conserva parent', next(n for n in data['notas'] if n['id'] == 'r001')['parent'] == 'h000')
    check('cambio del Agente en la misma coleccion', any(n.get('kind') == 'cambio' for n in data['notas']))
    cookie = {'Cookie': 'ofg=' + link['token']}
    request(GATE, 'POST', '/api/invitado/nombre', {'nombre': 'Hilo'}, cookie)
    guest = request(GATE, 'GET', path, headers=cookie)['notas']
    check('puerta devuelve 160 raices propias y respuesta', len(guest) == 161)
    check('puerta oculta nota interna y cambio privado', not {'privada', 'a001'} & {n['id'] for n in guest})
    check('puerta conserva respuesta de Cristian a su hilo', 'r001' in {n['id'] for n in guest})
    return slug, video, link


BOXES = """[...document.querySelectorAll('.topbar,.tp-row,.tlctrls,.editor,.side-head,.filter')]
  .filter(e=>e.offsetParent!==null).every(e=>e.scrollHeight<=e.clientHeight+2&&e.scrollWidth<=e.clientWidth+2)"""


def browser(slug, video, link):
    from cdp import Page
    class StrictPage(Page):
        def ev(self, expression, await_promise=False):
            result = super().ev(expression, await_promise)
            if isinstance(result, str) and result.startswith(('EXC:', 'JSERR')):
                raise AssertionError(result)
            return result
    for guest in (False, True):
        pg = StrictPage(GATE + '/r/' + link['token'] if guest else API + '/', 1280, 800)
        PAGES.append(pg)
        if guest:
            pg.ev("invNombre.value='Hilo'")
            pg.ev('invEnviarNombre()', await_promise=True)
        else:
            pg.ev('openProject(' + json.dumps(slug) + ')', await_promise=True)
        check(('invitado' if guest else 'anfitrion') + ' carga fixture',
              wait_js(pg, f'st.slug==={json.dumps(slug)} && x2Filtradas().length>=160'))
        for w, h in ((1280, 800), (1440, 900), (1600, 1000)):
            tag = f'{"invitado" if guest else "anfitrion"} {w}x{h}'
            pg.viewport(w, h, reload=False)
            pg.ev("st.x2Search='';st.x2Type='all';st.x2Person='all';st.onlyPend=false;st.x2Drawing=false;renderList()")
            first_ms = pg.ev('Number(list.dataset.renderMs)')
            check(tag + ' todas las raices presentes', pg.ev("list.querySelectorAll('.note').length===x2Filtradas().length"))
            check(tag + ' sin controles de pagina', pg.ev("!document.querySelector('#x2Prev,#x2Next,#x2Page,.x2pager')"))
            check(tag + ' scroll propio vertical', pg.ev("list.scrollHeight>list.clientHeight&&getComputedStyle(list).overflowY==='auto'"))
            check(tag + ' pagina sin scroll', pg.ev('document.documentElement.scrollHeight<=innerHeight+2&&document.documentElement.scrollWidth<=innerWidth+2&&scrollY===0'))
            check(tag + ' otras cajas sin scroll', pg.ev(BOXES))
            check(tag + ' orden video/frame/id', pg.ev("JSON.stringify([...list.querySelectorAll('.note')].map(n=>n.dataset.id))===JSON.stringify(x2Filtradas().map(n=>n.id))"))
            check(tag + ' respuesta anidada', pg.ev("!!list.querySelector('[data-hilo=h000] [data-rid=r001]')&&!list.querySelector('.note[data-id=r001]')"))
            pg.ev("activarMarcador(st.notas.find(n=>n.id==='h119'))")
            check(tag + ' marcador deja nota visible', wait_js(pg, "(()=>{const a=list.querySelector('[data-id=h119]').getBoundingClientRect(),b=list.getBoundingClientRect();return a.top>=b.top-2&&a.bottom<=b.bottom+2})()"))
            check(tag + ' contorno unico de 2 px', pg.ev("list.querySelectorAll('.note.on').length===1&&getComputedStyle(list.querySelector('.note.on')).outlineWidth==='2px'&&getComputedStyle(list.querySelector('.note.on'),'::before').display==='none'"))
            pg.ev('list.scrollTop=0;saltarANota("h119")', await_promise=True)
            time.sleep(.7)
            check(tag + ' repetir seleccion tambien desplaza', visible(pg, '.note[data-id=h119]'))
            pg.click('.note[data-id=h000]')
            time.sleep(.7)
            check(tag + ' clic en tarjeta tambien sigue la seleccion', visible(pg, '.note[data-id=h000].on'))
            pg.ev("ta.blur();document.body.focus()")
            pg.key('n')
            time.sleep(.7)
            check(tag + ' atajo de nota recorre el hilo', visible(pg, '.note.on'))
            pg.ev("st.x2Drawing=true;renderList()")
            check(tag + ' filtro de dibujo', pg.ev("list.querySelectorAll('.note').length===1&&!!list.querySelector('[data-id=h050]')"))
            pg.ev("st.x2Drawing=false;st.onlyPend=true;renderList()")
            check(tag + ' filtro pendientes', pg.ev("!list.querySelector('[data-id=h015]')&&list.querySelectorAll('.note').length>0"))
            pg.ev("st.onlyPend=false;st.x2Person='invitado';renderList()")
            check(tag + ' filtro autor', pg.ev("[...list.querySelectorAll('.note')].every(n=>n.dataset.who==='invitado')&&list.querySelectorAll('.note').length>=160"))
            pg.ev("st.x2Person='all';st.x2Type='cambio';renderList()")
            check(tag + ' filtro tipo', pg.ev("list.querySelectorAll('.note').length===" + ('0' if guest else '1')))
            pg.ev("st.x2Type='all';renderList()")
            if not guest:
                pg.ev('saltarANota("a001")', await_promise=True)
                time.sleep(.7)
                check(tag + ' cambio visible y seleccionado', visible(pg, '.note.change.on'))
            pg.ev("x2Search.value='HILO 159';x2Search.dispatchEvent(new Event('input'))")
            check(tag + ' busqueda y contador N de M', pg.ev("list.querySelectorAll('.note').length===1&&/^1 de \\d+$/.test(hiloCount.textContent)"))
            check(tag + ' filtro excluyente no mueve scroll', pg.ev("(()=>{const top=list.scrollTop;return x2SeguirNota('h001')===false&&list.scrollTop===top})()"))
            pg.ev("x2Search.value='';x2Search.dispatchEvent(new Event('input'))")
            pg.ev("cancelReply();list.scrollTop=200;window.__lectura={sel:st.selId,top:list.scrollTop};window.__ancla=[...list.children].find(n=>n.getBoundingClientRect().bottom>list.getBoundingClientRect().top);window.__aid=__ancla.dataset.hilo;window.__y=__ancla.getBoundingClientRect().top")
            # Publicacion remota real; para invitado es respuesta a su propia nota.
            if guest:
                body = {'parent': 'h000', 'text': 'Remota ' + tag, 'author': 'cristian'}
            else:
                body = {'video': video, 'frame': 0, 'text': 'Remota ' + tag, 'author': 'cristian'}
            remote = request(API, 'POST', '/api/proyectos/' + slug + '/notas', body)['nota']['id']
            check(tag + ' sondeo recibe remoto', wait_js(pg, f'st.notas.some(n=>n.id==={json.dumps(remote)})'))
            check(tag + ' sondeo conserva seleccion', pg.ev('st.selId===__lectura.sel'))
            check(tag + ' sondeo conserva tarjeta y posicion visual', pg.ev("Math.abs(list.querySelector('[data-hilo='+CSS.escape(__aid)+']').getBoundingClientRect().top-__y)<=2"))
            # Nueva nota por la UI a un fotograma distinto de las raices del fixture.
            text = 'Nueva ' + tag
            pg.ev(f"cancelReply();editingId=null;st.selId=null;seek(frameT(130));ta.value={json.dumps(text)};setDirty(true)")
            pg.ev('saveNote()', await_promise=True)
            time.sleep(.8)
            nid = pg.ev('st.notas.find(n=>n.text===' + json.dumps(text) + ')?.id')
            check(tag + ' nota nueva guardada', isinstance(nid, str))
            check(tag + ' nota nueva dentro de caja', visible(pg, '.note[data-id=' + str(nid) + ']'))
            check(tag + ' nota nueva seleccionada', pg.ev('st.selId===' + json.dumps(nid)))
            pg.ev('startReply("h000");ta.value=' + json.dumps('Respuesta ' + tag))
            pg.ev('saveReply()', await_promise=True)
            time.sleep(.7)
            rid = pg.ev('st.notas.find(n=>n.text===' + json.dumps('Respuesta ' + tag) + ')?.id')
            check(tag + ' respuesta nueva guardada', isinstance(rid, str))
            check(tag + ' respuesta nueva dentro de caja', visible(pg, '.rep[data-rid=' + str(rid) + ']'))
            check(tag + ' respuesta nueva sigue en su hilo', pg.ev('st.notas.find(n=>n.id===' + json.dumps(rid) + ')?.parent==="h000"'))
            # Variar seleccion obliga a reconstruir; 5 muestras, layout incluido.
            times = pg.ev("(()=>{const out=[];for(let i=0;i<5;i++){st.selId=i%2?'h001':'h002';const t=performance.now();renderList();void list.scrollHeight;out.push(performance.now()-t)}return out})()")
            check(tag + ' pintado <=80 ms o fallback activo', isinstance(times, list) and (max([first_ms] + times) <= 80 or pg.ev("list.classList.contains('hilo-lazy')") is True), [first_ms] + times)
            check(tag + ' ningun scroll exterior tras las acciones', pg.ev('scrollY===0&&document.documentElement.scrollHeight<=innerHeight+2&&' + BOXES))
            check(tag + ' cero excepciones JS', not [e for e in pg.errors if not str(e).startswith('LOG ')], pg.errors)
            pg.shot(f'hilo-{guest}-{w}x{h}.png')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--static', action='store_true')
    args = parser.parse_args()
    (ROOT / 'logs').mkdir(exist_ok=True)
    try:
        static()
        if not args.static:
            for name, port in (('server', 9491), ('guest', 9492)):
                base = API if name == 'server' else GATE
                if ready(base, '/api/ping'):
                    raise RuntimeError(f'puerto {port} ocupado; no se toca el proceso ajeno')
                cmd = [sys.executable, str(ROOT / f'{name}.py'), '--puerto', str(port)]
                if name == 'guest':
                    cmd += ['--api', API]
                start(cmd, name, base, '/api/ping')
            slug, video, link = fixture()
            if not ready(CDP, '/json/version'):
                start(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--headless=new',
                       '--remote-debugging-port=9493', '--remote-allow-origins=*',
                       '--user-data-dir=/tmp/o8/prof-9493', '--no-first-run', '--disable-gpu',
                       '--autoplay-policy=no-user-gesture-required', 'about:blank'], 'chrome', CDP, '/json/version')
            browser(slug, video, link)
    except Exception as error:
        check('ejecucion completa', False, str(error))
        print('NO VERIFICADO: cualquier check de navegador que no figure arriba.', flush=True)
    finally:
        for pg in PAGES:
            pg.ws.close()
        for proc in reversed(PROCS):
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=4)
        for handle in HANDLES:
            handle.close()
    print(f'{sum(CHECKS)}/{len(CHECKS)} checks; navegador omitido' if args.static else f'{sum(CHECKS)}/{len(CHECKS)} checks')
    return 0 if all(CHECKS) else 1


if __name__ == '__main__':
    raise SystemExit(main())
