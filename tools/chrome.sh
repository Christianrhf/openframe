#!/bin/bash
# tools/chrome.sh start PUERTO   |   tools/chrome.sh stop PUERTO
# Chrome headless propio de cada agente (puerto y perfil distintos): nunca toques el de otro.
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
P="${2:?puerto}"
case "$1" in
 start)
  pkill -f "remote-debugging-port=$P " 2>/dev/null; sleep 1; rm -rf "/tmp/o8/prof-$P"
  nohup "$CH" --headless=new --remote-debugging-port=$P "--remote-allow-origins=*" --user-data-dir="/tmp/o8/prof-$P" --no-first-run --disable-gpu --autoplay-policy=no-user-gesture-required about:blank >/tmp/o8/chrome-$P.log 2>&1 &
  for i in $(seq 1 25); do curl -s -m 2 http://127.0.0.1:$P/json/version >/dev/null && { echo "chrome listo en $P"; exit 0; }; sleep 1; done
  echo "chrome NO arranco en $P"; exit 1;;
 stop) pkill -f "remote-debugging-port=$P " 2>/dev/null; echo "chrome $P cerrado";;
esac
