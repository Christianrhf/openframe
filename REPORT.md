# REPORT · P5 — Fase 5: cierre de ronda y estado del video

## Qué quedó hecho

✔ **(a) Estado del corte.** `meta.json` del video gana `revision:{estado,desde}` **opcional**:
`rev_estado()` deriva «revision» cuando el campo no está (los 5 proyectos reales abren sin
migración). `PATCH /api/proyectos/<slug>/videos/<vid>` con `{"estado": revision|con_agente|aprobado}`
(400 si el estado no vale o falta, 404 si el video no existe). Lo exponen `load_videos()`
(→ GET del proyecto) y `/api/proyectos`, que añade `revision` del corte actual y `enviadas`.
`PATCH` de nota acepta `enviada_el` (ISO; `null` lo quita → así revierte Ctrl+Z; texto libre = 400).

✔ **(b) UI.** `#roundStatus` en la cabecera de Notas: **texto + forma** (reloj / avión / roseta,
iconos Lucide `clock`/`send`/`badge-check` copiados de `__iconNode`), sin color. Popover `#p5Pop`
con el resumen (notas nuevas · con dibujo · cambios sin revisar / aprobados / con ajuste) y las dos
acciones. «Enviar al Agente» marca `enviada_el` en las pendientes sin enviar y pasa a `con_agente`;
«Aprobar corte» solo se activa con 0 pendientes y 0 ajustes abiertos. Ambas entran en la pila única
(`pushUndo` tipo `multi` con una acción nueva `estado`): Ctrl+Z y Ctrl+Shift+Z las revierten/reponen.
El corte **sigue «Con el Agente» hasta aprobar** aunque no queden pendientes (comprobado).

✔ **(c) CLI.** `visor.sh notas <slug> enviadas` (+ `[enviada …]` por nota), el estado del corte en la
cabecera de cada video de `notas` y en `estado <slug>`, y `estado <slug> <video> [nuevo]` (lee o
cambia). `cambio`, `responder` y `resolver` **no** mueven el estado (3 checks).

✔ **(d)** Tarjeta del proyecto (activa y archivada) con el chip de estado, icono + texto.

✔ **(e) Invitados.** `guest.py` quita `revision` de los videos y `enviada_el` de las notas antes de
servirlas; el PATCH del video no casa con ninguna ruta de la puerta → 404, y el PATCH de nota del
invitado sigue aceptando solo `text`/`drawing` → 404. 6 checks lo verifican.

## Números

- `tools/test-p5.py` (nuevo, sin aleatoriedad): **61/61** (API 10 · `enviada_el` 4 · CLI 11 · puerta 8 ·
  UI por CDP 28). Puertos 9451/9452, Chrome 9453.
- Suites existentes: `test-guest.py` **619/619** · `run-attack.sh` **159/159** (1 hallazgo preexistente) ·
  `test-x2.py` **11/11** (sembré el proyecto `Prueba X2`, que el repo no trae) ·
  `e2e-invitado.py` **116/120** (el 116 de base, I2) · `test-inv.py` **50/54**.
- `test-inv.py`: los 4 fallos son **idénticos en el commit base b50990b** (50/54 allí también,
  mismos rótulos: dibujo del invitado que queda en borrador `tmp_`). No son míos; lo verifiqué
  levantando el código base en 9456/9457/9458.
- Chrome real a 1280×800, 1440×900 y 1600×1000: `scrollWidth == clientWidth` en página, `.side`,
  `.side-head` y `.rail`; el popover cabe entero dentro de la ventana en los tres. **0 excepciones**.
  Miré con Read `shots/p5-1280x800.png` y `p5-1600x1000.png` y corregí dos cosas que vi: el icono del
  popover salía a tamaño completo y el chip se partía en la tarjeta.
- Datos reales (copia en `data/`, 5 proyectos / 338 notas / 23 videos, ninguno con `revision`):
  los 5 abren, estado derivado «En revisión»/«N pendientes», **0 excepciones** de JS (solo 2 404 de
  los videos, que esa copia no trae). `visor.sh notas/estado` sobre `v02-golden-gate` también.
- `python3 -m py_compile` ✔, `bash -n visor.sh` ✔, `node --check` del `<script>` extraído ✔,
  `git diff --check` ✔, un solo `<script>` en `visor.html` ✔.

## Lo que NO verifiqué

- No probé la fase 7 (comparar v01·v02) ni atajos de teclado nuevos: no son de P5.
- No medí contraste con herramienta automática; el estado se distingue por icono y texto, no por color.
- No probé el estado del corte en pantalla completa ni por debajo de 1280 px de ancho.
- `e2e-invitado.py` y `test-inv.py` no llegan al 100 %: asumí el baseline que indica
  `PORTE-COMUN.md` (116/120) y, para `test-inv.py`, lo comprobé contra el commit base en vez de
  arreglarlo (es territorio de I2).
- `test-x2.py` tiene los puertos fijos (9421/9422) y no trae semilla: lo corrí con un `Prueba X2`
  sembrado a mano; **no toqué ese archivo**.
