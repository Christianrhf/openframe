# REPORT · TASK-I · Integración de punta a punta (U2 + S3) en Chrome real

## Números
- `tools/e2e-invitado.py`: **120/120 checks**, 11 capturas en `shots/` (revisadas con Read).
  Chrome 9366; `server.py` y `guest.py` reales con Python 3.9.6 del sistema, datos
  limpios, `OPENFRAME_NO_PUBLICAR=1`. Puertos 9391/9392 con caída al siguiente libre
  (el 9392 lo tenía ocupado un `server.py` zombi de `/tmp/o8/inv-U`; no lo maté).
- Regresión tras mis cambios: `tools/test-guest.py` **619/619** ✔ ·
  `bash tools/run-attack.sh` **159/159**, 0 fallos ✔ · `tools/test-inv.py` (mock) **54/54** ✔.
- Latencia medida: nota del invitado → visible sola en la app de Cristian **1,15–1,28 s**
  (sondeo de 2,2 s, clip real de 21,533 fps).
- Video por la puerta: `Range: bytes=0-65535` → **206**, `Content-Range: bytes 0-65535/119411`,
  **0,6–2,5 ms**; fuera de rango → 416; el `<video>` del invitado llega a `readyState 4`
  y `currentTime` avanza reproduciendo de verdad.

## Lo que rompía la integración (arreglado, con su check)
1. **`guest.py`**: `window.__INVITADO` no llevaba `enlace_id` (petición nº 1 de U2). Sin él
   «mía» se decidía por el nombre y dos invitados homónimos se editaban las notas. +4 líneas.
2. **`guest.py` + `server.py`**: un nombre de solo espacios pasaba el 1–40 y dejaba la insignia
   «Invitado · » vacía, indistinguible de otro invitado. Ahora 400 en los dos lados.
3. **`tools/cdp.py`**: `click()` interpolaba el selector crudo en el mensaje de error;
   cualquier selector con comillas (`[data-eid='x']`) lanzaba `SyntaxError` y el clic no ocurría.
4. **`tools/test-inv.py`**: puertos 9384/9385 fijos → `INV_GUEST_PORT`/`INV_ADMIN_PORT`
   (dos clones a la vez probaban el `visor.html` del otro).

El resto del contrato de datos ya casaba: `rev` llega en `/api/proyectos/<slug>` de la puerta,
`autor_nombre`/`enlace_id` viajan en `decorate()`, `frame` entero, tramo en el POST,
PATCH por `/api/notas/<slug>/<id>`.

## Verificado en el navegador contra la puerta real ✔
Diálogo de nombre · nota con texto · dibujo (strokes reescritos a `pts`) · tramo
(`end_frame`) · miniatura creada en canvas y servida por `/thumbs` · respuesta ·
edición de SU texto · 15 controles de Cristian ocultos · 21 acciones prohibidas desde
consola → 404 (borrar, resolver, visto, mover, otro proyecto, otro vídeo, listar/crear
enlaces, actividad, estado, heredar, subir, archivar, meta) · tope de dibujo 413 ·
429 al pasar 60 escrituras/min · nombre y texto con `<img onerror>` literales,
`window.__xss` nunca existe · `ve_otras=false` no ve al otro invitado, `ve_otras=true` sí ·
caducidad a mitad de sesión por 404 del sondeo (aviso + escritura apagada) · revocado con
404 **idéntico** al de un token inventado · `guest.log` con `id` y nunca el token.
Cristian: insignia «Invitado · Nombre» distinta de «Tú»/«Claude», popover Compartir
creando/listando/copiando/revocando contra los endpoints reales, responder y resolver.
`visor.sh invitar|invitados|revocar` probado a mano contra `server.py` real ✔.

## NO verificado ✘
El túnel y `publicar.sh on/off` de verdad (siempre `OPENFRAME_NO_PUBLICAR=1`) ·
Safari/Firefox · dos invitados a la vez en el mismo navegador (las cookies no distinguen
puerto: se prueban en secuencia) · carga sostenida y las 40 conexiones simultáneas desde el
navegador · el desborde preexistente de `.tp-row` con paneles abiertos (ya en la base).

## Nota honesta
Antes de descubrir los `server.py` zombis de otros clones escribí sin querer un proyecto de
prueba (`zz-port-2`) en `/tmp/o8/k-U2/data/`; lo borré. Nada más fuera de `/tmp/o8/k-I`.
