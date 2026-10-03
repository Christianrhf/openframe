# TAREA G · Red team: pruebas adversarias de la base (SOLO LECTURA de src/)   (puerto 9355 · modelo Sonnet)

NO modificas `src/`. Tu entregable: `tools/stress.py` (ejecutable con la receta de SPEC.md) y `BUGS.md`.
Eres un QA hostil de la maqueta base. Lee `docs/SPEC.md` y todo `src/` (el JS es corto). Busca fallos REALES, reproducibles en Chrome, y escribe cada uno como check en `tools/stress.py`
(`PASS`/`FAIL` por caso, mismo estilo que `tools/regress.py`). Ideas mínimas (añade las tuyas):
- Teclado: Espacio/flechas con foco en cada tipo de control; Tab recorre todo sin trampas; Esc en cada modo; atajos que se disparan al escribir en el textarea.
- Estado: seleccionar → filtrar pestaña → resolver → deshacer; resolver una nota seleccionada; deshacer una nota seleccionada; crear 40 notas rápido y deshacer todas; redo tras un cambio nuevo.
- Reproducción: al llegar al fotograma 1440 (final) y pulsar play; velocidad + zoom + reproducir; seek a 0 y a 1440 con zoom x8; scrubber con zoom.
- Layout: redimensionar de 1920×1080 a 1280×800 con el chat paginado; 60 notas (paginación, selección fuera de página); texto de nota de 600 caracteres sin espacios; nombre largo.
- Dibujo: dibujar fuera de la capa, con zoom, pantalla completa, herramienta cambiada a mitad de trazo, Ctrl+Z durante el trazo.
- Paleta de color: abrir/cerrar, clic fuera, Esc, reabrir, que no se quede colgada.
- Memoria/rendimiento: 200 notas, medir `update()` y `renderTimeline()`; fugas de listeners (`ResizeObserver`, `document` listeners) tras 50 ciclos.
- Accesibilidad básica: todo `button` con nombre accesible no vacío; ids únicos tras crear notas; `aria-pressed` coherente con la clase `.sel`; contraste de todo texto visible (calcúlalo; lista los < 4.5:1 con ratio y selector).
En `BUGS.md`: tabla ordenada por gravedad: id · qué falla · cómo reproducirlo (pasos o check) · dónde está (archivo:línea aproximada) · arreglo propuesto de 1-3 líneas. Solo bugs que reprodujiste; marca «no reproducido» los dudosos.
Commit de `tools/stress.py` y `BUGS.md`. Honestidad: si un check no es fiable, dilo.
