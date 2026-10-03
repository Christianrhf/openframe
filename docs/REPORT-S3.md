# REPORT · S3 · Puerta de invitados terminada y endurecida

## Base elegida
`ref-S/` **no tenía `guest.py`**: el intento de S murió antes de escribirlo, y su
`server.py`/`visor.sh` son byte a byte los originales del clon. Así que no había
híbrido posible y la base es `ref-S2/` entera (`guest.py` 786 líneas, `server.py`
+240, `visor.sh` +77, `tools/test-guest.py` 522 líneas): su puerta ya tenía lo
caro y lo correcto (lista blanca anclada, `flock` compartido con `server.py`,
`X-Guest-Gate`, campos forzados, streaming por bloques). De `ref-S` no se tomó
nada. La suite de ataque de T, `run-mutants.py` y `tools/mock/` tampoco estaban
en el clon; se copiaron desde `/tmp/o8/ataque`, y `ref-S2/` desde `/tmp/o8/cx-S2`.

## Números
- `tools/attack-guest.py` (caja negra de T): **159/159**, 0 fallos. Partida: 140/159.
- `python3 tools/run-mutants.py`: **6/6** mutantes muertos, correcto en verde.
- `tools/test-guest.py` (mía, puertos 9381/9382): **619/619** con Python 3.9.6 del
  sistema, fuzz de 420 combinaciones con semilla fija, 30 descargas concurrentes.

## Arreglado en el código (bugs)
Dibujo: validación genérica y **reescritura** (acepta `pts` o `points`, `{x,y}` o
`[x,y]`; el tope de puntos se mira antes de las coordenadas, así que pasarse es
413 y la forma mala 400). `thumb` > 600 KB: 413. `Content-Length` duplicado o con
`Transfer-Encoding`: 400; y solo `DIGIT{1,15}` (antes `int()` colaba `+2` y daba
413 con `-1`). `Host` validado contra `base_publica` (+`:443`) y
`127.0.0.1`/`localhost`/`[::1]:<puerto>`; el resto 404. `Origin`/`Referer`
cruzados en POST/PATCH: 403. `PATCH` descarta campos ajenos en vez de tumbar la
petición (igual que POST). Caché de `invitados.json` por `(st_mtime_ns, st_size)`.
`Vary: Cookie`. Rutas hacia 8477 citadas segmento a segmento. Socket mudo cerrado
sin traza. La puerta **espera** a `data/.guest_secret` en vez de morir por la
carrera de arranque (eso tumbaba la suite entera al arrancar los dos procesos a la vez).

## Corregido en la suite (y por qué)
- `/api/ping` sin cookie: vuelve a exigir **200**. CONTRATO línea 35 y `publicar.sh`
  lo usa para comprobar el túnel desde fuera. El sondeo de revocación/caducidad
  pasó a `/api/notas/<slug>`, que sí exige sesión; `mock_gate.py` igual.
- `fps` forzado: se compara con el fps **real** del video (21.533 del clip), no 24.
- Peticiones crudas legítimas llevan el `Host` real; «false Host» acepta 200 o 404.
- Mía: tope superado es 413 (no 400) y el `thumb` grande usa base64 válido (antes
  el relleno inválido hacía pasar el check por la razón equivocada).

## Hallazgos de la última pasada de atacante
Añadí checks de SSRF hacia 8477 (codificación y salto de segmento, `Host` del
puerto de administración, `X-Guest-Gate` del cliente **y el real**),
desincronización de longitudes por socket crudo, `thumb` con ruta al crear y al
descargar, enlaces simbólicos dentro de la carpeta del video (un `proxy-720.mp4`
que apunta al video de otro cliente da el 404 uniforme) y caché por cookie.
Los dos agujeros reales que salieron de ahí son los de `Content-Length` de arriba.

## Para Cristian
- `nombre` y `text` se guardan **tal cual** y viajan como JSON: la seguridad está
  en que la interfaz los pinte con `textContent`. **U2 no puede usar `innerHTML`**
  para el nombre del invitado ni para el texto de sus notas.
- 40 conexiones simultáneas y 20 s de timeout: 40 sockets abiertos y callados
  dejan la puerta sin atender hasta el timeout. Es caída de servicio, no fuga.

## Sin verificar
`publicar.sh on/off` real y el túnel (todo con `OPENFRAME_NO_PUBLICAR=1`, como
pide TASK-S 2b); nada en navegador (`visor.html` es de U2).
