# REPORT · Tarea G (red team)

## Criterios de aceptación
- ✔ No toqué `src/` (solo lectura, verificado con `git status` antes de commitear: solo `BUGS.md` y `tools/stress.py` nuevos).
- ✔ `python3 tools/build.py` en verde (71106 bytes, 34 iconos, 93 ids).
- ✔ `tools/regress.py` en verde: **59/59**, sin tocar ningún check (no cambié comportamiento a propósito).
- ✔ `tools/stress.py` escrito (34 checks), ejecutado con `CDP_PORT=9355 uv run --quiet --with websocket-client python3 tools/stress.py`: **28/34 OK, 6 FALLAN**. Los 6 `FAIL` son intencionales: documentan bugs reales (ver abajo), no fallos de mi test.
- ✔ Miré las capturas con Read (`shots/g_bug3_before_resize.png`, `shots/g_bug3_after_resize.png`) antes de dar el hallazgo #3 por bueno: el rótulo "Viendo: Nota 62" y la página del chat mostrando notas 41–43 se confirman a simple vista.
- ✔ `BUGS.md` con tabla por gravedad, pasos de repro, archivo:línea y arreglo propuesto de 1-3 líneas, más una sección de "no reproducido"/honestidad.
- ✔ Commit único (`4da848c`) con solo `BUGS.md` y `tools/stress.py`.
- ✔ Chrome del puerto 9355 cerrado al terminar.

## 5 bugs reales confirmados (tabla completa en BUGS.md)
1. **Alta** — Ctrl+Z durante un trazo activo deshace un trazo anterior ya confirmado y además pierde el trazo en curso al soltar el puntero (`app.js:253,269`).
2. **Media** — Cambiar de herramienta a mitad de trazo deja el elemento SVG congelado con la forma vieja mientras `pointermove` aplica atributos de la herramienta nueva (`app.js:247-268`).
3. **Media** — Redimensionar la ventana con el chat paginado puede dejar la tarjeta seleccionada en una página distinta a la mostrada: el pill "Viendo: Nota N" queda desincronizado del contenido visible del feed (`app.js:221-231,237`). Confirmado con capturas.
4. **Baja** — Contraste < 4.5:1 en texto base ya existente: `.ago` 2.85:1, `.live`/`.tab`/`.count`/`.empty` 3.54:1, `.time span` 3.36:1 (`app.css:99,176,179,181,200,255`).
5. **Baja, difícil con mouse real** — La paleta de color no cierra si el clic-fuera llega en el mismo tick de JS que la abrió (listener registrado vía `setTimeout(…,0)`). Confirmado solo con disparo síncrono; no reproducido con clic humano espaciado.

## Ids/atributos/funciones nuevos que otros deben conocer
Ninguno: tarea de solo lectura, no agrego superficie de API. `tools/stress.py` es standalone y no depende de hooks nuevos.

## Checks de regress.py tocados
Ninguno.

## Qué NO pude hacer / no medí
- No medí fugas de memoria reales (heap snapshot), solo conteo de nodos `.ink-pop` tras 50 ciclos (0 sobrantes).
- No probé pantalla completa real ni dibujo dentro de fullscreen (headless no se comporta igual).
- El bug #5 es débil: no confirmé que un usuario con mouse real pueda disparar la condición de carrera, solo vía JS síncrono.
- Descarté un falso positivo propio (ids "duplicados" n3/n3) al confundir `.item[data-item]` + `.marker[data-item]` compartiendo el mismo id por diseño; lo dejé documentado en BUGS.md y en comentario de stress.py para que no se repita.
