#!/usr/bin/env python3
"""Apagado por inactividad: se apaga solo sin uso, NO con trafico, NO con la puerta de invitados abierta, y los de prueba no se apagan."""
import os, socket, subprocess, sys, time, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = []
def check(l, ok, d=""):
    C.append(bool(ok)); print(("  ✔ " if ok else "  ✘ ") + l + ((" — " + str(d)) if (d and not ok) else ""))
def arranca(puerto, *extra, env=None):
    e = dict(os.environ); e.update(env or {})
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py"), "--puerto", str(puerto)] + list(extra),
                         cwd=ROOT, env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try: urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % puerto, timeout=1); return p
        except Exception: time.sleep(.25)
    return p
def ping(puerto):
    try: urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % puerto, timeout=1); return True
    except Exception: return False
GP = 9559
# 1 · sin uso y sin puerta de invitados: se apaga (0.1 min = 6 s; el vigia mira cada 15 s)
p1 = arranca(9551, "--inactividad", "0.1", env={"OPENFRAME_GUEST_PORT": "9558"})
# 2 · con trafico constante: sigue vivo
p2 = arranca(9552, "--inactividad", "0.1", env={"OPENFRAME_GUEST_PORT": "9558"})
# 3 · puerta de invitados abierta (algo escucha en GP): sigue vivo aunque no haya uso
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("127.0.0.1", GP)); srv.listen(128)
p3 = arranca(9553, "--inactividad", "0.1", env={"OPENFRAME_GUEST_PORT": str(GP)})
# 4 · servidor de prueba sin --inactividad (puerto != 8477): nunca se apaga solo
p4 = arranca(9554, env={"OPENFRAME_GUEST_PORT": "9558"})
check("los 4 servidores arrancan", all(ping(x) for x in (9551, 9552, 9553, 9554)))
# el 3 recibe trafico solo al principio; el 2 durante toda la espera
t0 = time.time()
while time.time() - t0 < 45:
    ping(9552); time.sleep(2)
    if time.time() - t0 > 20: pass
# el 1 y el 3 llevan 45 s sin uso; el 3 tiene puerta abierta -> vivo; el 1 -> apagado
time.sleep(1)
check("sin uso ni puerta abierta: se apaga solo", p1.poll() is not None and not ping(9551), p1.poll())
check("con trafico: sigue vivo", p2.poll() is None and ping(9552))
check("con la puerta de invitados abierta: sigue vivo sin uso", p3.poll() is None and ping(9553))
check("servidor de prueba (otro puerto): no se apaga", p4.poll() is None and ping(9554))
# 5 · al cerrar la puerta, el 3 se apaga
srv.close(); time.sleep(32)
check("al cerrarse la puerta de invitados se apaga", p3.poll() is not None and not ping(9553))
for p in (p1, p2, p3, p4):
    if p.poll() is None: p.terminate()
print("%d/%d checks" % (sum(C), len(C))); sys.exit(0 if all(C) else 1)
