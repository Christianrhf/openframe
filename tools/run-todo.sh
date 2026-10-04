#!/bin/bash
# Corre TODAS las suites del visor, una a la vez, con datos limpios, y resume. Uso: bash tools/run-todo.sh
export OPENFRAME_NO_PUBLICAR=1
cd "$(dirname "$0")/.." || exit 1
PY=/tmp/o8/venv/bin/python
OUT=/tmp/o8/todo-resumen.txt; : > $OUT
limpia(){ pkill -f "server.py --puerto 94" 2>/dev/null; pkill -f "guest.py --puerto 94" 2>/dev/null; pkill -f "mock-inv.py" 2>/dev/null; pkill -f "user-data-dir=/tmp/o8/prof" 2>/dev/null; sleep 1; }
api(){ for i in $(seq 1 50); do curl -s -m 2 http://127.0.0.1:$1/api/ping >/dev/null && return 0; sleep .3; done; return 1; }
res(){ echo "[$1] $2" | tee -a $OUT; }
limpia
# x2
rm -rf data logs; mkdir -p logs; python3 server.py --puerto 9421 >logs/s.out 2>&1 & api 9421
python3 tools/setup-x2.py --api http://127.0.0.1:9421 >/dev/null 2>&1; tools/chrome.sh start 9422 >/dev/null
res test-x2 "$(CDP_PORT=9422 $PY tools/test-x2.py 2>&1 | grep -E 'checks|✘' | tr '\n' ' ')"; limpia
# i2 (datos reales)
rm -rf data logs; mkdir -p logs; cp -R /tmp/o10/datos-reales data; python3 server.py --puerto 9431 >logs/s.out 2>&1 & api 9431; tools/chrome.sh start 9433 >/dev/null
res test-i2 "$(CDP_PORT=9433 $PY tools/test-i2.py --api http://127.0.0.1:9431 2>&1 | grep -E 'checks|✘|FALLAN' | tr '\n' ' ')"; limpia
# p4
rm -rf data logs; mkdir -p logs; python3 server.py --puerto 9441 >logs/s.out 2>&1 & api 9441
curl -s -X POST http://127.0.0.1:9441/api/proyectos -H 'Content-Type: application/json' -d '{"nombre":"prueba-p4"}' >/dev/null; curl -s -X POST http://127.0.0.1:9441/api/proyectos/prueba-p4/videos --data-binary @clip.mp4 -H 'X-Filename: clip.mp4' -H 'Content-Type: application/octet-stream' >/dev/null; tools/chrome.sh start 9443 >/dev/null
res test-p4 "$(CDP_PORT=9443 $PY tools/test-p4.py 2>&1 | grep -E 'checks|✘' | tr '\n' ' ')"; limpia
# p5 (arranca sus servidores)
rm -rf data logs; mkdir -p logs; tools/chrome.sh start 9453 >/dev/null
res test-p5 "$(CDP_PORT=9453 $PY tools/test-p5.py 2>&1 | grep -E 'checks|✘|FALLAN' | tr '\n' ' ')"; limpia
# p7
rm -rf data logs; mkdir -p logs; python3 server.py --puerto 9461 >logs/s.out 2>&1 & python3 guest.py --puerto 9462 --api http://127.0.0.1:9461 >logs/g.out 2>&1 & api 9461; tools/chrome.sh start 9463 >/dev/null
res test-p7 "$(CDP_PORT=9463 $PY tools/test-p7.py 2>&1 | grep -E 'checks|✘|FALLAN' | tr '\n' ' ')"; limpia
# p6 (arranca sus servidores: 9471 server, 9472 guest)
rm -rf data logs; mkdir -p logs; tools/chrome.sh start 9473 >/dev/null
res test-p6 "$(CDP_PORT=9473 $PY tools/test-p6.py 2>&1 | grep -E 'checks|FALLA' | tr '\n' ' ')"; limpia
# guest + ataque
res test-guest "$(python3 tools/test-guest.py 2>&1 | tail -1)"; limpia
res ataque "$(bash tools/run-attack.sh 2>&1 | grep -E 'SUMMARY|PASS.*FAIL|[0-9]+/[0-9]+' | tail -1)"; limpia
# e2e invitado
tools/chrome.sh start 9366 >/dev/null
res e2e-invitado "$(CDP_PORT=9366 $PY tools/e2e-invitado.py 2>&1 | grep -E 'checks|FALLAN|^  - ' | tr '\n' ' ')"; limpia
# test-inv (mock)
tools/chrome.sh start 9362 >/dev/null
res test-inv "$(CDP_PORT=9362 bash tools/run-inv.sh 2>&1 | grep -E 'checks|✘|FALLAN' | tail -2 | tr '\n' ' ')"; limpia
echo; echo "===== RESUMEN"; cat $OUT
