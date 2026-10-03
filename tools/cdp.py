"""Libreria minima de CDP para probar la maqueta en Chrome real (viewport fijo, no 469 px de alto).
Uso (desde la raiz del repo):  CDP_PORT=9351 uv run --quiet --with websocket-client python3 tools/miprueba.py
    from cdp import Page
    pg = Page()                       # abre dist/VISUAL.html a 1600x1000
    pg.ev("frame")                    # evalua JS; devuelve el valor (o 'EXC: ...' si la pagina lanza)
    pg.click('#next'); pg.shot('x.png'); pg.key('z', ctrl=True); pg.drag(x0,y0,x1,y1)
    pg.viewport(1280, 800)            # cambia de tamano y recarga
    pg.errors                         # excepciones de la pagina acumuladas
"""
import json, os, sys, time, base64, urllib.request
try:
    import websocket
except ImportError:
    sys.exit('Falta websocket-client: usa  uv run --quiet --with websocket-client python3 <script>')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get('CDP_PORT', '9351'))
SHOTS = os.path.join(ROOT, 'shots'); os.makedirs(SHOTS, exist_ok=True)

class Page:
    def __init__(self, url=None, w=1600, h=1000):
        req = urllib.request.Request(f'http://127.0.0.1:{PORT}/json/new?about:blank', method='PUT')
        tab = json.loads(urllib.request.urlopen(req, timeout=10).read())
        self.ws = websocket.create_connection(tab['webSocketDebuggerUrl'], timeout=30)
        self._id = 0; self.errors = []
        self.url = url or 'file://' + os.path.join(ROOT, 'dist', 'VISUAL.html')
        self.w, self.h = w, h
        for m in ('Runtime.enable', 'Log.enable', 'Page.enable'): self.send(m)
        self.viewport(w, h)

    def send(self, method, **params):
        self._id += 1
        self.ws.send(json.dumps({'id': self._id, 'method': method, 'params': params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get('method') == 'Runtime.exceptionThrown':
                d = m['params']['exceptionDetails']
                self.errors.append((d.get('exception') or {}).get('description') or d.get('text'))
            elif m.get('method') == 'Log.entryAdded' and m['params']['entry'].get('level') == 'error':
                self.errors.append('LOG ' + m['params']['entry'].get('text', ''))
            if m.get('id') == self._id:
                return m.get('result', {})

    def viewport(self, w, h, reload=True, clear_storage=True):
        self.w, self.h = w, h
        self.send('Emulation.setDeviceMetricsOverride', width=w, height=h, deviceScaleFactor=1, mobile=False)
        if reload:
            self.send('Page.navigate', url=self.url); time.sleep(1.2)
            if clear_storage:
                self.ev("localStorage.clear()"); self.send('Page.reload'); time.sleep(1.0)

    def reload(self): self.send('Page.reload'); time.sleep(1.0)

    def ev(self, expr, await_promise=False):
        r = self.send('Runtime.evaluate', expression=expr, returnByValue=True, awaitPromise=await_promise)
        if 'exceptionDetails' in r:
            d = r['exceptionDetails']; return 'EXC: ' + str((d.get('exception') or {}).get('description') or d.get('text'))
        inner = r.get('result', {})
        if inner.get('subtype') == 'error': return 'JSERR ' + inner.get('description', '')
        return inner.get('value')

    def click(self, sel):  # clic real de DOM (programatico)
        return self.ev(f"(()=>{{const e=document.querySelector({json.dumps(sel)});if(!e)return 'NO EXISTE {sel}';e.click();return true}})()")

    def rect(self, sel):
        return self.ev(f"(()=>{{const e=document.querySelector({json.dumps(sel)});if(!e)return null;const b=e.getBoundingClientRect();return {{x:b.left,y:b.top,w:b.width,h:b.height,r:b.right,b:b.bottom}}}})()")

    def mouse(self, kind, x, y, button='left', **kw):
        self.send('Input.dispatchMouseEvent', type=kind, x=x, y=y, button=button, clickCount=1, **kw)

    def click_xy(self, x, y): self.mouse('mouseMoved', x, y); self.mouse('mousePressed', x, y); self.mouse('mouseReleased', x, y)

    def drag(self, x0, y0, x1, y1, steps=8):
        self.mouse('mouseMoved', x0, y0); self.mouse('mousePressed', x0, y0)
        for k in range(1, steps + 1): self.mouse('mouseMoved', x0 + (x1 - x0) * k / steps, y0 + (y1 - y0) * k / steps, buttons=1)
        self.mouse('mouseReleased', x1, y1)

    def hover(self, x, y): self.mouse('mouseMoved', x, y)

    def key(self, key, ctrl=False, shift=False, alt=False, meta=False):
        mod = (2 if ctrl else 0) | (8 if shift else 0) | (1 if alt else 0) | (4 if meta else 0)
        vk = {'Escape': 27, 'Enter': 13, 'ArrowLeft': 37, 'ArrowRight': 39, 'ArrowUp': 38, 'ArrowDown': 40, 'Tab': 9, ' ': 32}.get(key, ord(key.upper()) if len(key) == 1 else 0)
        code = {' ': 'Space'}.get(key, ('Key' + key.upper()) if len(key) == 1 and key.isalpha() else key)
        text = key if len(key) == 1 and not ctrl and not meta else None
        for t in ('keyDown', 'keyUp'):
            kw = dict(type=t, key=key, code=code, windowsVirtualKeyCode=vk, modifiers=mod)
            if text and t == 'keyDown': kw['text'] = text
            self.send('Input.dispatchKeyEvent', **kw)

    def type(self, text):
        for ch in text: self.send('Input.dispatchKeyEvent', type='char', text=ch)

    def shot(self, name='shot.png', clip=None):
        kw = {'format': 'png'}
        if clip: kw['clip'] = dict(x=clip[0], y=clip[1], width=clip[2], height=clip[3], scale=1)
        r = self.send('Page.captureScreenshot', **kw)
        path = os.path.join(SHOTS, name); open(path, 'wb').write(base64.b64decode(r['data'])); return path

    def sleep(self, s=.25): time.sleep(s)
