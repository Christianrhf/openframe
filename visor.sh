#!/bin/bash
# visor.sh — CLI del Visor de Notas (para Claude y para Cristian)
# Habla con el servidor local en 127.0.0.1:8477

set -uo pipefail
API="${VISOR_API:-http://127.0.0.1:8477}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Si el servidor no responde, lo levanta en background
ensure_up() {
  if curl -sf -m 2 "$API/api/ping" >/dev/null 2>&1; then return 0; fi
  mkdir -p "$HERE/logs"
  nohup python3 "$HERE/server.py" --puerto 8477 >> "$HERE/logs/server.log" 2>&1 &
  for _ in $(seq 1 20); do
    sleep 0.4
    curl -sf -m 2 "$API/api/ping" >/dev/null 2>&1 && return 0
  done
  echo "ERROR: el servidor no arranca. Revisa $HERE/logs/server.log" >&2
  return 1
}

# $1 = cuerpo python que recibe `d` = el JSON de stdin.
# Antes era `python3 -c "...;$1" 2>/dev/null`: si el servidor contestaba un error, o
# curl -f no devolvia nada, la salida quedaba COMPLETAMENTE VACIA y no habia forma de
# saber que habia pasado (ni para Cristian ni para Claude, que es quien usa esta CLI).
j() {
  local cuerpo
  cuerpo="$(cat)"
  if [ -z "$cuerpo" ]; then
    echo "ERROR: el servidor no devolvio nada (revisa el slug, el id o $HERE/logs/server.log)" >&2
    return 1
  fi
  printf '%s' "$cuerpo" | python3 -c "import sys, json
try:
    d = json.load(sys.stdin)
except Exception as e:
    sys.exit('ERROR: la respuesta no es JSON (%s)' % e)
if isinstance(d, dict) and d.get('error'):
    sys.exit('ERROR del servidor: %s' % d['error'])
$1"
}

usage() {
cat <<'EOF'
visor.sh — revision de video con notas por fotograma

  proyectos                        lista proyectos activos
  proyectos --todos               incluye los archivados
  archivar <slug> [on|off]        archiva o devuelve un proyecto (no borra nada)
  nuevo <nombre> [cliente] [nota]  crea un proyecto
  subir <slug> <archivo> [--sin-heredar]
                                   sube un video y trae los hilos ABIERTOS del corte anterior
  estado <slug>                    resumen del proyecto
  notas <slug> [todas|pendientes]  lista las notas (default: pendientes)
  nota <slug> <video-id> <frame> "<texto>" [fin-frame]   deja una nota
  responder <slug> <nota-id> "<texto>"   responde EN el hilo (id de la raiz o de una respuesta)
  cambio <slug> <video-id> <frame> "<que cambiaste>" [--por <nota-id>]
                                   marca un cambio. --por = la nota que lo motivo
  cambios-lista <slug>                    lista los cambios marcados, por timecode
  borrar-cambio <slug> <cambio-id>       quita un marcador de cambio
  resolver <slug> <nota-id>        marca una nota como resuelta
  resolver-todas <slug>            resuelve todas las pendientes
  desmarcar <slug> <nota-id>       vuelve a abrir una nota
  borrar-nota <slug> <nota-id>     elimina una nota
  vids <slug>                      lista los videos con id, fps y duracion
  invitar <slug> <vid> [--dias N] [--etiqueta T] [--ve-otras]
                                   crea un enlace privado para ese video
  invitados [slug]                lista enlaces, uso y notas
  revocar <slug> <vid> <id>       revoca un enlace de inmediato

Ejemplos:
  visor.sh subir animales-sueltos trailer.mov
  visor.sh notas animales-sueltos
  visor.sh nota animales-sueltos v_1a2b3c4d 341 "el logo sale 2s temprano" 400
EOF
}

cmd="${1:-}"; shift 2>/dev/null || true
case "$cmd" in
  ""|-h|--help|help) usage; exit 0 ;;
esac

ensure_up || exit 1

case "$cmd" in
  invitar)
    SLUG="${1:-}"; VID="${2:-}"; shift 2 2>/dev/null || true
    DIAS=7; ETIQUETA=""; VE=false
    while [ $# -gt 0 ]; do
      case "$1" in
        --dias)
          [ $# -ge 2 ] || { echo "ERROR: --dias necesita un numero" >&2; exit 1; }
          DIAS="$2"; shift 2 ;;
        --dias=*) DIAS="${1#--dias=}"; shift ;;
        --etiqueta)
          [ $# -ge 2 ] || { echo "ERROR: --etiqueta necesita texto" >&2; exit 1; }
          ETIQUETA="$2"; shift 2 ;;
        --etiqueta=*) ETIQUETA="${1#--etiqueta=}"; shift ;;
        --ve-otras) VE=true; shift ;;
        *) echo "ERROR: opcion desconocida: $1" >&2; exit 1 ;;
      esac
    done
    if [ -z "$SLUG" ] || [ -z "$VID" ]; then
      echo "uso: visor.sh invitar <slug> <vid> [--dias N] [--etiqueta T] [--ve-otras]" >&2; exit 1; fi
    BODY=$(python3 -c 'import json,sys
try: dias=int(sys.argv[1])
except ValueError: sys.exit("ERROR: --dias debe ser un numero")
print(json.dumps({"dias":dias,"etiqueta":sys.argv[2],"ve_otras":sys.argv[3]=="true"}))' "$DIAS" "$ETIQUETA" "$VE") || exit 1
    curl -s -X POST "$API/api/proyectos/$SLUG/videos/$VID/invitar" \
      -H 'Content-Type: application/json' -d "$BODY" | j '
print(d["url"])
if not d.get("publicada"):
    print("AVISO: la puerta publica NO quedo abierta: %s" % d.get("aviso","sin detalle"), file=sys.stderr)'
    ;;

  invitados)
    SLUG="${1:-}"
    python3 - "$API" "$SLUG" <<'PY'
import json, sys, urllib.error, urllib.request
api, wanted = sys.argv[1].rstrip('/'), sys.argv[2]
def get(path):
    try:
        return json.load(urllib.request.urlopen(api + path, timeout=10))
    except urllib.error.HTTPError as e:
        try: msg=json.load(e).get('error','HTTP %d' % e.code)
        except Exception: msg='HTTP %d' % e.code
        raise SystemExit('ERROR del servidor: ' + msg)
if wanted:
    projects=[get('/api/proyectos/' + wanted)]
else:
    index=get('/api/proyectos')
    projects=[get('/api/proyectos/' + p['slug']) for p in index.get('todos', index.get('proyectos',[]))]
rows=[]
for project in projects:
    slug=project.get('proyecto',{}).get('slug')
    for video in project.get('videos',[]):
        data=get('/api/proyectos/%s/videos/%s/invitar' % (slug, video['id']))
        for link in data.get('enlaces',[]):
            rows.append((slug, video['id'], video.get('nombre',''), link))
print('%-18s %-11s %-8s %-10s %5s %5s  %s' % ('PROYECTO','VIDEO','ID','ESTADO','USOS','NOTAS','ETIQUETA'))
for slug, vid, _name, link in rows:
    if link.get('revocado'): state='revocado'
    else:
        import datetime
        try: expired=datetime.datetime.fromisoformat(link['expira'].replace('Z','+00:00')) <= datetime.datetime.now(datetime.timezone.utc)
        except Exception: expired=True
        state='caducado' if expired else 'activo'
    print('%-18s %-11s %-8s %-10s %5d %5d  %s' %
          (slug[:18], vid[:11], link.get('id',''), state, int(link.get('usos') or 0),
           int(link.get('notas') or 0), link.get('etiqueta','')))
if not rows: print('(sin enlaces)')
PY
    ;;

  revocar)
    SLUG="${1:-}"; VID="${2:-}"; ID="${3:-}"
    if [ -z "$SLUG" ] || [ -z "$VID" ] || [ -z "$ID" ]; then
      echo "uso: visor.sh revocar <slug> <vid> <id>" >&2; exit 1; fi
    curl -s -X DELETE "$API/api/proyectos/$SLUG/videos/$VID/invitar/$ID" \
      | j 'print("REVOCADO " + "'"$ID"'") if d.get("ok") else sys.exit("ERROR: no se pudo revocar")'
    ;;

  proyectos|ls|ps)
    curl -sf "$API/api/proyectos" | j '
p=d.get("proyectos",[]); a=d.get("archivados",[])
print("PROYECTOS (%d)" % len(p))
for x in p:
    print("  %-24s %2d vid  %3d notas (%d pend)  %s" % (x["slug"], x["videos"], x["notas"], x["pendientes"], x["nombre"]))
if not p: print("  (ninguno — crea uno con: visor.sh nuevo <nombre>)")
if a:
    print("\nARCHIVADOS (%d) — fuera de la lista de trabajo, no se abren al recargar" % len(a))
    for x in a:
        print("  %-24s %2d vid  %3d notas            %s   (sacar: visor.sh archivar %s off)" % (x["slug"], x["videos"], x["notas"], x["nombre"], x["slug"]))
'
    ;;

  nuevo|new|crear)
    NOMBRE="${1:-}"; CLIENTE="${2:-}"; NOTA="${3:-}"
    [ -z "$NOMBRE" ] && { echo "uso: visor.sh nuevo <nombre> [cliente] [nota]" >&2; exit 1; }
    BODY=$(python3 -c "import json,sys;print(json.dumps({'nombre':sys.argv[1],'cliente':sys.argv[2],'nota':sys.argv[3]}))" "$NOMBRE" "$CLIENTE" "$NOTA")
    curl -sf -X POST "$API/api/proyectos" -H 'Content-Type: application/json' -d "$BODY" \
      | j 'print("CREADO: " + d["slug"])'
    ;;

  subir|up|add|upload)
    SLUG="${1:-}"; ARCH="${2:-}"; HEREDAR=1
    # --sin-heredar: subir sin traer los hilos abiertos del corte anterior
    [ "${3:-}" = "--sin-heredar" ] && HEREDAR=0
    if [ -z "$SLUG" ] || [ -z "$ARCH" ]; then
      echo "uso: visor.sh subir <slug> <archivo-video> [--sin-heredar]" >&2; exit 1; fi
    if [ ! -f "$ARCH" ]; then echo "ERROR: no existe el archivo: $ARCH" >&2; exit 1; fi
    NAME=$(basename "$ARCH")
    SZ=$(wc -c < "$ARCH" | tr -d ' ')
    echo "subiendo $NAME ($((SZ/1024/1024)) MB)…" >&2
    RESP=$(curl -sf -X POST "$API/api/proyectos/$SLUG/videos" \
      -H "X-Filename: $(printf %s "$NAME" | python3 -c 'import sys;print(sys.stdin.buffer.read().decode("utf-8"),end="")')" \
      -H "Content-Type: application/octet-stream" \
      --data-binary "@$ARCH")
    printf '%s' "$RESP" | j 'v=d.get("video") or d
print("SUBIDO: %s" % v.get("nombre"))
print("  id: %s" % v.get("id"))
print("  codec: %s   reproducible_en_navegador: %s" % (v.get("codec"), v.get("reproducible")))
sz=v.get("bytes",0); print("  peso: %.1f MB" % (sz/1024/1024))' || exit 1
    [ "$HEREDAR" = 1 ] || exit 0
    NUEVO=$(printf '%s' "$RESP" | j 'print((d.get("video") or d).get("id",""))')
    # el corte anterior = el mas reciente que NO sea el recien subido
    PREV=$(curl -sf "$API/api/proyectos/$SLUG" | j 'vs=[v for v in d.get("videos",[]) if v["id"] != "'"$NUEVO"'"]
vs.sort(key=lambda v: v.get("created",""))
print(vs[-1]["id"] if vs else "")')
    if [ -z "$PREV" ]; then echo "  (primer video del proyecto: nada que heredar)"; exit 0; fi
    # solo_pendientes: viajan los hilos ABIERTOS; los cerrados quedan como registro de v1.
    curl -s -X POST "$API/api/proyectos/$SLUG/heredar" -H 'Content-Type: application/json' \
      -d "{\"desde\":\"$PREV\",\"hacia\":\"$NUEVO\",\"solo_pendientes\":true,\"offset_frames\":0}" \
      | j 'k=d.get("heredados",0); s=d.get("saltados",0)
print("HEREDADOS: %d hilo%s abierto%s" % (k, "" if k==1 else "s", "" if k==1 else "s") + ((" (%d ya estaban)" % s) if s else ""))
for n in d.get("notas", []): print("  %s  %s  %s" % (n["id"], n["timecode"], (n.get("text") or "").replace("\n"," ")[:60]))'
    ;;

  estado|st|info)
    SLUG="${1:-}"; [ -z "$SLUG" ] && { echo "uso: visor.sh estado <slug>" >&2; exit 1; }
    curl -sf "$API/api/proyectos/$SLUG" | j '
p=d.get("proyecto",{}); vs=d.get("videos",[]); ns=d.get("notas",[])
print("PROYECTO: %s (%s)" % (p.get("nombre","?"), p.get("slug","?")))
if p.get("cliente"): print("  cliente: " + p["cliente"])
if p.get("nota"): print("  objetivo: " + p["nota"])
print("VIDEOS (%d)" % len(vs))
for v in vs:
    print("  %-11s %-30s %-14s %6.2fs  %sfps  %sx%s%s" % (
        v["id"], v["nombre"][:30], v.get("codec","?"), v.get("duracion") or 0,
        v.get("fps") or "?", v.get("ancho") or "?", v.get("alto") or "?",
        "" if v.get("reproducible") else "   [NO REPRODUCIBLE]"))
    n=[x for x in ns if x["video"]==v["id"]]
    print("             notas: %d (%d pendientes)" % (len(n), len([x for x in n if not x["resolved"]])))
if not vs: print("  (ninguno)")
print("TOTAL NOTAS: %d (%d pendientes)" % (len(ns), len([x for x in ns if not x["resolved"]])))
'
    ;;

  vids|videos)
    SLUG="${1:-}"; [ -z "$SLUG" ] && { echo "uso: visor.sh vids <slug>" >&2; exit 1; }
    curl -sf "$API/api/proyectos/$SLUG" | j '
vs=d.get("videos",[]); ns=d.get("notas",[])
for v in vs:
    n=[x for x in ns if x["video"]==v["id"]]
    print("%s  %-32s %-14s %6.2fs  %sfps  %d notas" % (v["id"], v["nombre"][:32], v.get("codec","?"),
        v.get("duracion") or 0, v.get("fps") or "?", len(n)))'
    ;;

  notas|notes|ns)
    SLUG="${1:-}"; MODO="${2:-pendientes}"
    [ -z "$SLUG" ] && { echo "uso: visor.sh notas <slug> [todas|pendientes]" >&2; exit 1; }
    curl -sf "$API/api/notas/$SLUG" | python3 -c '
import sys, json
d = json.load(sys.stdin)
todas_ = [n for n in d.get("notas", []) if n.get("kind") != "cambio"]
ns = [n for n in todas_ if not n.get("parent")]      # solo raices: las respuestas van dentro
reps = {}
for r in todas_:
    if r.get("parent"): reps.setdefault(r["parent"], []).append(r)
todo = "'"$MODO"'" != "pendientes"
vs = {}
import urllib.request
# usa $API, no la URL fija: con VISOR_API apuntando a otro puerto esto consultaba
# el servidor equivocado (o ninguno) y la lista salia sin nombres de video ni fps
try:
    pv = json.load(urllib.request.urlopen("'"$API"'/api/proyectos/'"$SLUG"'", timeout=5))
    vs = {v["id"]: v for v in pv.get("videos", [])}
except Exception:
    pass
if not ns:
    print("(sin notas%s)" % ("" if todo else " pendientes"))
    sys.exit(0)
print("NOTAS (%d de %d)" % (len(ns) if todo else len([n for n in ns if not n["resolved"]]), len(ns)))
cur = None
for n in ns:
    if n["resolved"] and not todo:
        continue
    if n["video"] != cur:
        cur = n["video"]
        vn = vs.get(cur, {}).get("nombre", cur)
        fps = vs.get(cur, {}).get("fps") or n.get("fps") or "?"
        print("\n== %s  (video %s, %s fps)" % (vn, cur, fps))
    rng = "  -> %s" % n["end_timecode"] if n.get("end_timecode") else ""
    st_ = " [CERRADA]" if n["resolved"] else (" [RESPONDIDA]" if n.get("estado") == "respondida" else "")
    dr = " [dibujo]" if n.get("drawing") else ""
    print("  %s  f%-6d %-7s%s%s%s" % (n["id"], n["frame"], n["timecode"], rng, st_, dr))
    for line in (n.get("text") or "").split("\n"):
        if line.strip():
            print("      " + line)
    for r in sorted(reps.get(n["id"], []), key=lambda r: (r.get("created", ""), r["id"])):
        quien = "Claude" if r.get("author") == "claude" else "Cristian"
        print("      > %s (%s %s): %s" % (r["id"], quien, (r.get("created") or "")[11:16],
                                          (r.get("text") or "").replace("\n", " ")))
'
    ;;

  nota|add-nota)
    SLUG="${1:-}"; VID="${2:-}"; FRAME="${3:-}"; TEXT="${4:-}"; FIN="${5:-}"
    [ -z "$SLUG" ] || [ -z "$VID" ] || [ -z "$FRAME" ] || [ -z "$TEXT" ] && {
      echo 'uso: visor.sh nota <slug> <video-id> <frame> "texto" [fin-frame]' >&2; exit 1; }
    BODY=$(python3 -c "import json,sys;print(json.dumps({'video':sys.argv[1],'frame':int(sys.argv[2]),'text':sys.argv[3],'end_frame':int(sys.argv[4]) if sys.argv[4] else None,'author':'claude'}))" "$VID" "$FRAME" "$TEXT" "$FIN")
    curl -sf -X POST "$API/api/proyectos/$SLUG/notas" -H 'Content-Type: application/json' -d "$BODY" \
      | j 'n=d.get("nota") or d
print("NOTA %s en %s (f%s)" % (n["id"], n["timecode"], n["frame"]))'
    ;;

  responder|reply|resp)
    SLUG="${1:-}"; NID="${2:-}"; TEXT="${3:-}"
    if [ -z "$SLUG" ] || [ -z "$NID" ] || [ -z "${TEXT// /}" ]; then
      echo 'uso: visor.sh responder <slug> <nota-id> "texto"' >&2
      echo '     (vale el id de la raiz o el de una respuesta: entra en el mismo hilo)' >&2; exit 1; fi
    # Sin video ni frame: una respuesta hereda el momento de su raiz (lo hace el servidor).
    BODY=$(python3 -c "import json,sys;print(json.dumps({'parent':sys.argv[1],'text':sys.argv[2],'author':'claude'}))" "$NID" "$TEXT")
    # Sin -f: si el servidor contesta 400 ("no existe la nota a la que responder"), el
    # cuerpo llega a j y se imprime ese error, no "el servidor no devolvio nada".
    curl -s -X POST "$API/api/proyectos/$SLUG/notas" -H 'Content-Type: application/json' -d "$BODY" \
      | j 'n=d.get("nota") or d
raiz = n.get("parent") or n.get("thread")
est, k = "?", 0
try:
    todas = json.load(urllib.request.urlopen("'"$API"'/api/proyectos/" + "'"$SLUG"'", timeout=5)).get("notas", [])
    r = next((x for x in todas if x["id"] == raiz), None)
    if r: est, k = (r.get("estado") or "?"), int(r.get("respuestas") or 0)
except Exception:
    pass
print("RESPUESTA %s en %s (f%s)" % (n["id"], n["timecode"], n["frame"]))
print("  hilo %s -> %s (%d respuesta%s)" % (raiz, est, k, "" if k == 1 else "s"))'
    ;;

  cambio|cambios|chg)
    SLUG="${1:-}"; shift 2>/dev/null || true
    POR=""; ARGS=()
    # --por <nota-id> (o --por=<nota-id>) puede ir en cualquier posicion
    while [ $# -gt 0 ]; do
      case "$1" in
        # `shift 2` con un solo argumento restante ("--por" al final, sin id) no desplaza
        # nada y el bucle no acabaria nunca: por eso son dos shift condicionados.
        --por)   POR="${2:-}"; shift; [ $# -gt 0 ] && shift ;;
        --por=*) POR="${1#--por=}"; shift ;;
        *)       ARGS+=("$1"); shift ;;
      esac
    done
    VID="${ARGS[0]:-}"; FRAME="${ARGS[1]:-}"; TEXT="${ARGS[2]:-}"
    # Forma corta `visor.sh cambio <slug> <frame> "texto"`: solo si el proyecto tiene UN video.
    # Se detecta porque el 2o argumento es un numero y el 3o no lo es.
    if [[ "$VID" =~ ^[0-9]+$ ]] && ! [[ "$FRAME" =~ ^[0-9]+$ ]]; then
      TEXT="$FRAME"; FRAME="$VID"
      VID=$(curl -sf "$API/api/proyectos/$SLUG" | j 'vs=d.get("videos",[]);print(vs[0]["id"] if len(vs)==1 else "")')
      if [ -z "$VID" ]; then
        echo "ERROR: el proyecto tiene 0 o varios videos: indica el video-id (visor.sh vids $SLUG)" >&2
        exit 1; fi
    fi
    if [ -z "$SLUG" ] || [ -z "$VID" ] || [ -z "$FRAME" ]; then
      echo 'uso: visor.sh cambio <slug> <video-id> <frame> "que cambiaste" [--por <nota-id>]' >&2; exit 1; fi
    # TEXTO OBLIGATORIO. Un cambio sin texto es un punto mudo: Cristian lo ve en la barra y
    # no sabe que se toco. 37 de esos hay hoy.
    if [ -z "${TEXT// /}" ]; then
      echo 'ERROR: un cambio sin texto es un punto mudo. Di QUE cambiaste:' >&2
      echo "  visor.sh cambio $SLUG $VID $FRAME \"Alineé el titulo con el audio\" --por n_xxxxxxxx" >&2; exit 1; fi
    BODY=$(python3 -c "import json,sys;print(json.dumps({'video':sys.argv[1],'frame':int(sys.argv[2]),'text':sys.argv[3],'author':'claude','kind':'cambio','resuelve':(sys.argv[4] or None)}))" "$VID" "$FRAME" "$TEXT" "$POR")
    # Sin -f: si --por apunta a una nota que no existe, el 400 del servidor se imprime.
    curl -s -X POST "$API/api/proyectos/$SLUG/notas" -H 'Content-Type: application/json' -d "$BODY" \
      | j 'n=d.get("nota") or d
print("CAMBIO %s en %s (f%s)" % (n["id"], n["timecode"], n["frame"]))
print("  " + (n.get("text") or ""))
if n.get("resuelve"): print("  por la nota %s" % n["resuelve"])'
    ;;

  cambios-lista|ver-cambios)
    SLUG="${1:-}"
    [ -z "$SLUG" ] && { echo "uso: visor.sh cambios-lista <slug>" >&2; exit 1; }
    curl -sf "$API/api/proyectos/$SLUG" | python3 -c '
import sys, json
d = json.load(sys.stdin)
cs = sorted([n for n in d.get("notas", []) if n.get("kind") == "cambio"], key=lambda x: x["frame"])
if not cs:
    print("SIN CAMBIOS MARCADOS")
for n in cs:
    por = ("   <- %s" % n["resuelve"]) if n.get("resuelve") else ""
    visto = " [visto]" if n.get("visto") else ""
    print("  %s  %s  f%-6s %s%s%s" % (n["id"], n["timecode"], n["frame"],
                                     (n.get("text") or "(SIN TEXTO - punto mudo)").replace("\n", " ")[:70], visto, por))
print()
print("%d cambios" % len(cs))'
    ;;

  borrar-cambio|rm-cambio)
    SLUG="${1:-}"; NID="${2:-}"
    [ -z "$SLUG" ] || [ -z "$NID" ] && { echo "uso: visor.sh borrar-cambio <slug> <cambio-id>" >&2; exit 1; }
    curl -sf -X DELETE "$API/api/notas/$SLUG/$NID" | j 'print("BORRADO " + "'"$NID"'")'
    ;;

  resolver|res)
    SLUG="${1:-}"; NID="${2:-}"
    [ -z "$SLUG" ] || [ -z "$NID" ] && { echo "uso: visor.sh resolver <slug> <nota-id>" >&2; exit 1; }
    curl -sf -X PATCH "$API/api/notas/$SLUG/$NID" -H 'Content-Type: application/json' -d '{"resolved":true}' \
      | j 'print("RESUELTA " + "'"$NID"'")'
    ;;

  desmarcar|unres)
    SLUG="${1:-}"; NID="${2:-}"
    [ -z "$SLUG" ] || [ -z "$NID" ] && { echo "uso: visor.sh desmarcar <slug> <nota-id>" >&2; exit 1; }
    curl -sf -X PATCH "$API/api/notas/$SLUG/$NID" -H 'Content-Type: application/json' -d '{"resolved":false}' \
      | j 'print("ABIERTA " + "'"$NID"'")'
    ;;

  resolver-todas|res-todas)
    SLUG="${1:-}"; [ -z "$SLUG" ] && { echo "uso: visor.sh resolver-todas <slug>" >&2; exit 1; }
    curl -sf "$API/api/notas/$SLUG" | python3 -c '
import sys, json, urllib.request
d = json.load(sys.stdin)
ns = [n for n in d.get("notas", []) if not n["resolved"]]
for n in ns:
    req = urllib.request.Request("'"$API"'/api/notas/'"$SLUG"'/" + n["id"],
        data=json.dumps({"resolved": True}).encode(), method="PATCH",
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()
print("RESUELTAS %d notas" % len(ns))'
    ;;

  borrar-nota|del)
    SLUG="${1:-}"; NID="${2:-}"
    [ -z "$SLUG" ] || [ -z "$NID" ] && { echo "uso: visor.sh borrar-nota <slug> <nota-id>" >&2; exit 1; }
    curl -sf -X DELETE "$API/api/notas/$SLUG/$NID" | j 'print("BORRADA " + "'"$NID"'")'
    ;;

  archivar|arch)
    # archivar <slug>            saca el proyecto de la lista de trabajo
    # archivar <slug> off        lo devuelve
    SLUG="${1:-}"; MODO="${2:-on}"
    if [ -z "$SLUG" ]; then echo "uso: visor.sh archivar <slug> [on|off]" >&2; exit 1; fi
    FLAG=true; [ "$MODO" = "off" ] && FLAG=false
    ETIQUETA="DEVUELTO"; [ "$FLAG" = "true" ] && ETIQUETA="ARCHIVADO"
    curl -sf -X POST "$API/api/proyectos/$SLUG/archivar" -H 'Content-Type: application/json' \
      -d "{\"archivado\": $FLAG}" | j 'print("'"$ETIQUETA"'", d.get("slug","")) if d.get("ok") else print("ERROR:", d.get("error","?"))'
    ;;

  *)
    echo "comando desconocido: $cmd" >&2
    usage
    exit 1
    ;;
esac
