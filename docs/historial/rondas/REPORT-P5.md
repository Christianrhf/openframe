# REPORT · P5 — cierre de ronda y estado del video

✔ **(a)** `meta.json` del video gana `revision:{estado,desde}` **opcional** (sin campo = «revision»;
los proyectos reales abren sin migrar). `PATCH /api/proyectos/<slug>/videos/<vid>` con
`estado=revision|con_agente|aprobado` (400 inválido/ausente, 404 video). Lo exponen `load_videos()`
(GET del proyecto) y `/api/proyectos` (`revision` del corte actual + `enviadas`). `PATCH` de nota
acepta `enviada_el` ISO; `null` lo quita (así revierte Ctrl+Z), texto libre → 400.

✔ **(b)** `#roundStatus` en la cabecera de Notas: **texto + forma** (Lucide `clock`/`send`/`badge-check`), sin color. Popover `#p5Pop` con resumen (notas nuevas · con dibujo ·
cambios sin revisar/aprobados/con ajuste) y las dos acciones. «Enviar al Agente» marca `enviada_el` en
las pendientes y pasa a `con_agente`; «Aprobar corte» solo con 0 pendientes y 0 ajustes. Ambas en la
pila única (`pushUndo` `multi` + acción nueva `estado`): Ctrl+Z y Ctrl+Shift+Z las revierten/reponen.
El corte **sigue «Con el Agente» hasta aprobar** aunque no queden pendientes.

✔ **(c)** `visor.sh notas <slug> enviadas` (+ `[enviada …]`), estado del corte en `notas` y `estado
<slug>`, y `estado <slug> <video> [nuevo]`. `cambio`/`responder`/`resolver` no mueven el estado.

✔ **(d)** Chip de estado en la tarjeta del proyecto (activa y archivada).

✔ **(e)** `guest.py` quita `revision` y `enviada_el` antes de servir; PATCH del video y de
`enviada_el` por la puerta → 404.

**Números.** `tools/test-p5.py` **61/61** (9451/9452, Chrome 9453). `test-guest.py` 619/619 ·
`run-attack.sh` 159/159 · `test-x2.py` 11/11 (sembré «Prueba X2») · `e2e-invitado.py` 116/120
(baseline) · `test-inv.py` 50/54, **idéntico en el commit base** (lo levanté en 9456 para
comprobarlo). CDP 1280×800/1440×900/1600×1000: `scrollWidth==clientWidth` en página, `.side`, `.side-head` y
`.rail`; popover entero en pantalla; **0 excepciones**. Miré 2 capturas con Read: corregí el icono del
popover y el chip partido. Datos reales (5 proyectos, 338 notas, 23 videos, 0 con
`revision`): abren todos, 0 excepciones. `py_compile`, `bash -n`, `node --check`, `git diff --check` ✔.

**No verificado.** Fase 7, atajos, pantalla completa, anchos <1280, contraste automático. No arreglé
los fallos de `e2e-invitado`/`test-inv` (I2) ni toqué `test-x2.py` (puertos fijos, sin semilla).
