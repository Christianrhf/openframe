#!/bin/bash
# Levanta server.py (9381) y guest.py (9382) de ESTE clon con datos limpios y lanza la suite de ataque.
export OPENFRAME_NO_PUBLICAR=1
cd "$(dirname "$0")/.." || exit 1
rm -rf data logs; mkdir -p logs
python3 server.py --puerto 9381 > logs/server.out 2>&1 & SP=$!
python3 guest.py --puerto 9382 --api http://127.0.0.1:9381 > logs/guest.out 2>&1 & GP=$!
sleep 3
/tmp/o8/venv/bin/python tools/attack-guest.py --api http://127.0.0.1:9381 --gate http://127.0.0.1:9382 --clip clip.mp4 --data "$PWD/data" --log "$PWD/logs/guest.log" "$@"
RC=$?
kill $SP $GP 2>/dev/null; wait $SP $GP 2>/dev/null
exit $RC
