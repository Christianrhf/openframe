#!/bin/bash
# Levanta server.py + mock-inv.py de ESTE clon con el proyecto zz-port y lanza test-inv.py.
# Puertos de I2: api 9434, invitado 9435, admin 9436. Chrome: CDP_PORT del entorno.
export OPENFRAME_NO_PUBLICAR=1
cd "$(dirname "$0")/.." || exit 1
API=9434; GP=9435; AP=9436
rm -rf data logs; mkdir -p logs
/usr/bin/python3 server.py --puerto $API > logs/server.out 2>&1 & SP=$!
for i in $(seq 1 30); do curl -s -m 2 http://127.0.0.1:$API/api/ping >/dev/null && break; sleep .4; done
curl -s -X POST -H 'Content-Type: application/json' -d '{"nombre":"zz-port","cliente":"Porte"}' \
  http://127.0.0.1:$API/api/proyectos > /dev/null
VID=$(curl -s -X POST -H 'X-Filename: clip.mp4' -H 'Content-Type: application/octet-stream' \
  --data-binary @clip.mp4 http://127.0.0.1:$API/api/proyectos/zz-port/videos \
  | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["video"]["id"])')
echo "zz-port video=$VID"
/usr/bin/python3 tools/mock-inv.py --api $API --invitado $GP --admin $AP --slug zz-port --video "$VID" \
  > logs/mock-inv.out 2>&1 & MP=$!
sleep 2
INV_GUEST_PORT=$GP INV_ADMIN_PORT=$AP /tmp/o8/venv/bin/python tools/test-inv.py "$@"
RC=$?
kill $SP $MP 2>/dev/null; wait $SP $MP 2>/dev/null
exit $RC
