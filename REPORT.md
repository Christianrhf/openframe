# REPORT · TASK-U2 (interfaz de invitados) · agente U2

**Punto de partida:** `ref-U/visor.html` era idéntico a la base (diff vacío) y no había `test-inv.py`: el intento previo no dejó nada. Reescrito desde cero. `visor.html` 3 566 → 4 071 líneas (+585/−40).

**Pruebas:** `tools/test-inv.py` = **54/54 checks** por CDP (Chrome 9362, 44 s), 11 capturas en `shots/` revisadas. Servidores: `server.py --puerto 9383` (`zz-port` + `clip.mp4`) y `tools/mock-inv.py` (simula `guest.py` en 9384 y `/invitar` + `/api/invitados/estado` en 9385, mandos `/__mock/*`).

## Entregables
- ✔ **Modo invitado**: banner fijo, diálogo de nombre (Enter envía; Escape no cierra), 20 selectores ocultos medidos con `offsetParent===null`, 20 visibles, edición solo de SUS notas, responder, dibujar, tramo (va en el POST: la puerta no admite PATCH `end_frame`), PATCH por `/api/notas/<slug>/<id>`, sondeo filtrado, caducidad a mitad de sesión (reloj + 404) con escritura apagada.
- ✔ **Compartir**: botón `share-2` (geometría lucide-react) + popover: crear (1/7/30 días, etiqueta, ve_otras), lista activo/caducado/revocado con usos y nº notas, Copiar con aviso, Revocar en dos clics sin `confirm()`, «Puerta abierta/cerrada», aviso si `publicada:false`, línea «El servidor aún no admite enlaces» ante 404.
- ✔ **Insignia** «Invitado · Nombre» (chip discontinuo, barra y marcadores a rayas) en tarjetas, respuestas, barra y regleta.
- ✔ Reglas: `.bak`, cero dependencias, B/N, un `<script>`, `title`/`aria-label`, sin scroll a 1280/1440/1600.
- ✔ Seguridad UI: nombre, texto y etiqueta con `<img onerror>` se ven literales, `window.__xss` nunca existe. Desde consola/teclado del invitado, borrar/resolver/nuevo proyecto/heredar/archivar/exportar/Para Claude/subir/mover/deshacer/⇧N/⇧P/visto no hacen nada (comprobado contra el servidor).

## Arreglos a la base (1 línea cada uno)
`dibujando`→`drawing` en `pull()` (ReferenceError: el sondeo no repintaba); `setIcon` escribía `##i-pause` (play en blanco); `startEdit` no soltaba el modo respuesta; dibujar reutilizaba una nota de otro fotograma; `data-who` de respuestas en minúsculas; `<link rel=icon data:>`.

## NO verificado
`guest.py`/`server.py` reales de S3 (solo mock); túnel; `thumb` desde el navegador; desborde preexistente de `.tp-row` con paneles abiertos (909 px en 434–754 disponibles; ya en la base).

## Necesito de S
1. `enlace_id` dentro de `window.__INVITADO` (si falta, «mía» compara `autor_nombre`).
2. `add_note`/`decorate()` con `autor_nombre` y `enlace_id` (el mock los parchea en `notes.json`).
3. `GET /api/proyectos/<slug>` de la puerta con `rev` (lo usa el sondeo).
