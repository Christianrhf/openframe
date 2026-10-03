# Modo invitado de OpenFrame · contrato (dos agentes en paralelo; respeta nombres y rutas EXACTOS)

## Qué se construye
Cristian comparte **un video** con otra persona mediante un enlace secreto: `https://openframe.inspiredink.space/r/<token>`. El invitado ve ese video (solo ese), deja notas con dibujo y tramo y responde; Cristian y el Agente (Claude vía `visor.sh`) las ven en su visor normal con el nombre del invitado. El tráfico llega a la Mac por un túnel de Cloudflare que apunta SOLO a un proceso nuevo, `guest.py`, en `127.0.0.1:8478`. El puerto 8477 (`server.py`, sin autenticación, con borrar/resolver/subir) NUNCA se expone.
Los videos son de clientes: confidencial. **Un fallo de seguridad aquí es el peor fallo posible; en caso de duda, 404.**

## Piezas y dueños
| Pieza | Archivo | Dueño |
|---|---|---|
| Puerta de invitados (proxy con lista blanca, tokens, cookies, límites) | `guest.py` (nuevo) | **S** |
| Endpoints de administración de enlaces + campos de autor + actividad | `server.py` | **S** |
| CLI `invitar` / `invitados` / `revocar` | `visor.sh` | **S** |
| Modo invitado de la interfaz + botón «Compartir» de Cristian + insignia «Invitado» | `visor.html` | **U** |
Nadie toca el archivo de otro. Si necesitas algo de otro dueño, escríbelo en tu REPORT.md.

## Reglas heredadas de la app (no negociables)
Python **3.9** de sistema en la Mac (stdlib únicamente: nada de `match`, nada de `X | Y` en tipos evaluados, nada de pip). Cero dependencias en `visor.html` (ni CDN ni fuentes ni librerías), tema claro, **blanco y negro** (cero color salvo la paleta del pincel), iconos Lucide reales ya presentes en el sprite (no dibujes paths a mano), ayuda en `title`/`aria-label` (cero texto de ayuda impreso), nada de modos invisibles, todo en una pantalla sin scroll, un solo bloque `<script>`. `visor.html` mide ~3 500 líneas: **no cortes por índice de subcadena**; edita con parches exactos y tras cada edición comprueba por `grep` que el marcador viejo desapareció y el nuevo está. Verifica en Chrome real (CDP, `tools/cdp.py` si existe en tu clon; si no, el recipe del SPEC). La app es en español (STE imperativo, corto).

## Almacenamiento y configuración
- `config.json` junto a `server.py`: `{"base_publica": "https://openframe.inspiredink.space"}` (si no existe, ese valor por defecto).
- `data/<slug>/videos/<vid>/invitados.json` (permisos 600): lista de `{id (8 hex), token (secrets.token_urlsafe(32)), creado, expira (ISO UTC), revocado (bool), etiqueta (≤60), ve_otras (bool, defecto false), usos (int), ultimo_uso (ISO|null)}`.
- Secreto de firma de cookies: `data/.guest_secret` (32 bytes aleatorios, permisos 600, se crea solo).
- Notas nuevas (campos opcionales, retrocompatibles; el código viejo los ignora): `author:"invitado"`, `autor_nombre` (≤40), `enlace_id`. `decorate()` los incluye en las respuestas.

## API de administración en 8477 (solo local, la usan Cristian y el Agente)
- `POST /api/proyectos/<slug>/videos/<vid>/invitar` body `{dias (1–90, def. 7), etiqueta, ve_otras}` → `201 {id, token, url, expira, etiqueta, ve_otras}`.
- `GET /api/proyectos/<slug>/videos/<vid>/invitar` → `{enlaces:[{id, url, creado, expira, revocado, etiqueta, ve_otras, usos, ultimo_uso, notas (nº de notas con ese enlace_id)}]}`.
- `DELETE /api/proyectos/<slug>/videos/<vid>/invitar/<id>` → `{ok:true}` (revoca; efecto inmediato).
- `GET /api/invitados/actividad?desde=<ISO>` → `{notas:[{slug, vid, id, nombre, etiqueta, text, frame, created}]}` (notas con `author=="invitado"` creadas después de `desde`; para el aviso por Telegram que monta Cristian aparte).
## API de invitado en 8478 (`guest.py`)
Identidad = cookie `ofg` (el token; `HttpOnly; Secure; SameSite=Lax; Path=/`; `Max-Age` hasta `expira`). El nombre = cookie `ofn` firmada con HMAC-SHA256.
- `GET /r/<token>` → `302 /` + cookie `ofg` (válido) · `404` página mínima «Este enlace ya no está disponible» (inválido, caducado, revocado: **idéntico**, sin pistas). Cuenta `usos`/`ultimo_uso`.
- `GET /` → `visor.html` con `<script>window.__INVITADO={slug, video, nombre, expira, ve_otras, proyecto:{nombre,cliente}, version:{nombre,fps,duracion,ancho,alto}}</script>` inyectado justo antes del primer `<script>` (`nombre` = null si aún no hay cookie `ofn`). Cabeceras: `Cache-Control: no-store`, `X-Robots-Tag: noindex, nofollow`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`.
- `POST /api/invitado/nombre` `{nombre}` (1–40, sin control chars) → cookie `ofn` → `{ok, nombre}`.
- `GET /api/ping` → `{ok:true}`.
- `GET /api/proyectos/<slug>` (slug == el del enlace) → misma forma que `server.py` pero con `videos:[solo el compartido]` y sin datos de otros videos; cualquier otro `/api/proyectos…` (lista, otros slugs, `/hilos`, archivar, subir…) → 404.
- `GET /api/notas/<slug>` → notas del video compartido; si `ve_otras` es false, solo las de ese `enlace_id` + las respuestas a ellas (incl. las de Cristian/Claude); **nunca** notas de otros videos.
- `POST /api/proyectos/<slug>/notas` → crea vía 8477 con campos **forzados por la puerta**: `video` = el compartido, `fps` = el del video, `kind:"nota"`, `author:"invitado"`, `autor_nombre` = cookie `ofn` (si no hay nombre → 403 con `{error:"nombre"}`), `enlace_id`, sin `resolved`/`resuelve`/`visto`/`decision`. Se aceptan: `text` (≤4000), `frame`, `end_frame`, `drawing` (strokes ≤ 400 puntos totales… decide un tope razonable), `thumb` (≤ 600 KB base64), `parent` (solo si esa nota es visible para este invitado).
- `PATCH /api/notas/<slug>/<id>` → solo `{text}` y `{drawing}`, solo en notas con su `enlace_id`; las demás → 404.
- `GET /media/<slug>/<vid>/<file>` → solo el video compartido; `Range`/`HEAD` pasan tal cual (206/416); si existe `proxy-720.mp4` en la carpeta del video y se pide `media.*`, sirve el proxy.
- `GET /thumbs/<slug>/<id>.jpg` → solo notas visibles.
- Todo lo demás (cualquier otro verbo/ruta): **404** (no 403, no 405, sin eco de la ruta).
- Límites: 60 escrituras/min y 300/h por enlace → 429; cuerpo máx. 1 MB (413); timeout de socket 20 s; 40 conexiones simultáneas máx.; log `logs/guest.log` SIN token (solo `id` de enlace).
- Revocar/caducar se comprueba en CADA petición (mtime-cache de `invitados.json` ≤ 2 s).
- `guest.py` escucha SOLO en `127.0.0.1:8478` (`--puerto`, `--api` para la URL de 8477).

## `visor.sh` (CLI del Agente y de Cristian)
`visor.sh invitar <slug> <vid> [--dias N] [--etiqueta T] [--ve-otras]` → imprime la URL; `visor.sh invitados [slug]` → tabla; `visor.sh revocar <slug> <vid> <id>`. Verifica las rutas contra `do_POST/do_GET/do_DELETE` de `server.py`.

## Interfaz de invitado (visor.html, `window.__INVITADO` presente)
Banner fijo «Revisando como <nombre> · <proyecto> · <versión>»; al abrir sin nombre, un diálogo corto («¿Cómo te llamas?» + campo + botón; Enter envía; sin cierre sin nombre) que llama a `POST /api/invitado/nombre`. Ocultos (no solo deshabilitados): selector/lista de proyectos y videos, subir, archivar, borrar, resolver/reabrir, marcar visto, «Para Claude», heredar hilos, migraciones, cualquier ajuste del servidor. Disponibles: reproducir, buscar fotograma, dibujar, nota con texto/dibujo/tramo, responder, editar el texto de SUS notas, atajos, zoom, filtros que existan. Las notas del invitado salen con insignia «Invitado · Nombre». El sondeo (`poll`) sigue funcionando contra la API filtrada. Con enlace caducado a mitad de sesión: aviso claro («Este enlace caducó») y controles de escritura desactivados.
## Interfaz de Cristian (sin `window.__INVITADO`)
Botón **Compartir** (icono Lucide `share-2`, en la cabecera del video actual) → popover: crear enlace (caducidad 1/7/30 días, etiqueta opcional, «ver las notas de otros» desactivado por defecto), lista de enlaces del video con estado (activo/caducado/revocado), usos, nº de notas, **Copiar** (portapapeles con aviso) y **Revocar** (confirmación en el propio botón, sin `confirm()`). Las notas de invitados se distinguen por la insignia «Invitado · Nombre» y no se pueden confundir con las de Cristian ni con las del Agente.

## Publicación automática (puerta abierta solo mientras haya enlaces vivos)
`publicar.sh on|off|estado` (ya hecho, en la raíz; lo arranca/para `guest.py` y el túnel con launchd). Por defecto la puerta está CERRADA. `server.py` la gestiona solo:
- al crear un enlace → `publicar.sh on` (subproceso no bloqueante, timeout 60 s; el resultado se devuelve como `publicada: true|false` y `aviso` en la respuesta del POST de `/invitar`);
- al revocar el último enlace activo, o cuando un hilo vigilante (cada 5 min) ve que no quedan enlaces activos (todos caducados/revocados) → `publicar.sh off`;
- `GET /api/invitados/estado` → `{publicada: bool, enlaces_activos: n}` (para el popover «Compartir»: una línea «Puerta abierta/cerrada»).
- Variable de entorno `OPENFRAME_NO_PUBLICAR=1` desactiva esas llamadas (las pruebas la usan; jamás deben tocar el túnel real).
`visor.sh invitar` imprime la URL y, si la puerta no quedó abierta, lo dice sin ambigüedad.
