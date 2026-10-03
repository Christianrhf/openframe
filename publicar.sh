#!/bin/bash
# publicar.sh — abre o cierra la puerta publica de OpenFrame (guest.py + tunel de Cloudflare)
# Uso: publicar.sh on | off | estado
# Por defecto la puerta esta CERRADA: solo se abre mientras haya enlaces de invitado activos.
# Los plist viven en launchd/ (NO en ~/Library/LaunchAgents) para que tras un reinicio quede cerrada.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UIDN="$(id -u)"
DOM="gui/$UIDN"
LA="$HERE/launchd"
GUEST="com.cristian.openframe-guest"
TUN="com.cristian.openframe-tunnel"
PUB="${OPENFRAME_URL_PUBLICA:-https://openframe.inspiredink.space}"
mkdir -p "$HERE/logs"

cargado() { launchctl print "$DOM/$1" >/dev/null 2>&1; }
local_ok() { curl -sf -m 3 http://127.0.0.1:8478/api/ping >/dev/null 2>&1; }
externo() { curl -s -m 12 -o /dev/null -w '%{http_code}' "$PUB/api/ping" 2>/dev/null; }

case "${1:-estado}" in
  on)
    [ -f "$HERE/guest.py" ] || { echo "ERROR: falta guest.py en $HERE" >&2; exit 1; }
    cargado "$GUEST" || launchctl bootstrap "$DOM" "$LA/$GUEST.plist" || { echo "ERROR: no arranca guest.py" >&2; exit 1; }
    for _ in $(seq 1 15); do local_ok && break; sleep 0.4; done
    local_ok || { echo "ERROR: guest.py no responde en 127.0.0.1:8478 (mira $HERE/logs/guest.log)" >&2; exit 1; }
    cargado "$TUN" || launchctl bootstrap "$DOM" "$LA/$TUN.plist" || { echo "ERROR: no arranca el tunel" >&2; exit 1; }
    for _ in $(seq 1 20); do [ "$(externo)" = "200" ] && { echo "abierta: $PUB"; exit 0; }; sleep 1; done
    echo "AVISO: la puerta local esta abierta pero $PUB aun no responde 200 (puede tardar unos segundos mas)" >&2; exit 2 ;;
  off)
    cargado "$TUN" && launchctl bootout "$DOM/$TUN" 2>/dev/null
    cargado "$GUEST" && launchctl bootout "$DOM/$GUEST" 2>/dev/null
    sleep 1
    if cargado "$TUN" || cargado "$GUEST"; then echo "ERROR: no se pudo cerrar" >&2; exit 1; fi
    echo "cerrada" ;;
  estado)
    t=cerrado; g=cerrado; cargado "$TUN" && t=abierto; cargado "$GUEST" && g=abierto
    echo "tunel: $t · puerta local: $g · local_ok: $(local_ok && echo si || echo no) · externo: $(externo)" ;;
  *) echo "Uso: $0 on|off|estado" >&2; exit 64 ;;
esac
