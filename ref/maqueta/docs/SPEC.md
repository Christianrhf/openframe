# OpenFrame · maqueta VISUAL.html — SPEC COMPARTIDA (léela entera antes de tocar nada)

## Qué es y para quién
Maqueta navegable (un solo HTML sin dependencias) de **OpenFrame**, la app de revisión de video de Cristian
(publicista dominicano, 34 años). Él revisa un corte fotograma a fotograma y deja notas; un **Agente** (IA) aplica los
cambios y responde. El ciclo correcto es: **el Agente responde, Cristian cierra**. Esta maqueta es el diseño que luego se
porta a la app real (`visor.html` + `server.py`); aquí se decide la UX. Proyecto de ejemplo: «Animales Sueltos», corte v02, 24 fps,
60 s, 1440 fotogramas. Interfaz **en español**. En la UI el autor automático es **«Agente»**, nunca «Claude».

## Archivos (todo se edita en `src/`; `dist/VISUAL.html` se genera, no se toca)
- `src/app.css` — todo el CSS. Al final hay secciones `/* ── A · … ── */ … E`: **añade el CSS de tu tarea SOLO dentro de la tuya**.
  Para cambiar una regla existente edítala donde está (cambio mínimo, sin reformatear).
- `src/body.html` — HTML. Iconos: `{{i:nombre}}` o `{{i:nombre:sm}}` (sm=14px, xs=12px). `{{SCENE}}` inserta el fotograma ilustrado.
- `src/app.js` — toda la lógica, un solo bloque `'use strict'`. Sin módulos.
- `ref/scene.html` — SVG del fotograma. `tools/` — herramientas (abajo). `tools/icon-names.txt` — los 1951 iconos Lucide disponibles.

## Cómo construir y probar (puedes ejecutar todo; Chrome headless funciona)
```
cd <tu carpeta>                                   # tu clon, p.ej. /tmp/o8/ag-A
python3 tools/build.py                            # genera dist/VISUAL.html y AUDITA (ids duplicados, $() rotos, iconos, anidamiento, JS)
tools/chrome.sh start $PUERTO                     # tu Chrome propio (puerto de tu tarea); al terminar: tools/chrome.sh stop $PUERTO
export PATH="$HOME/.local/bin:$PATH"
CDP_PORT=$PUERTO uv run --quiet --with websocket-client python3 tools/regress.py     # 59 checks de regresión: deben seguir en verde
```
Escribe tus propias pruebas en `tools/test-<tu-letra>.py` con `from cdp import Page` (ver docstring de `tools/cdp.py`: `pg.ev`, `pg.click`,
`pg.drag`, `pg.key`, `pg.hover`, `pg.shot`, `pg.viewport`). **Mira tus capturas** (`shots/*.png`) con la herramienta Read (lee imágenes) antes de dar nada por bueno:
un test en verde no prueba que se vea bien. Itera hasta que las medidas Y la captura estén bien.
Tu Chrome y tu puerto son TUYOS: nunca mates procesos de otros agentes (`pkill` solo con TU puerto). No salgas de tu carpeta ni de `/tmp/o8/prof-$PUERTO`.
**Prohibido tocar** `~/Documents`, `~/visornotas` y cualquier otra ruta fuera de tu clon.

## Reglas duras del diseño (el usuario las exige; incumplirlas = trabajo rechazado)
1. **Blanco y negro.** Cero color en la interfaz; la distinción la llevan la forma y el grosor. ÚNICA excepción: la paleta del trazo de dibujo.
2. **Cero «IA slop»:** sin degradados, sin sombras difusas (box-shadow con blur) salvo la que ya tienen los popovers existentes, sin dobles bordes / halos /
   barras laterales de color, sin glassmorphism, sin emojis. Una selección es UNA línea de 1–2 px. Radios 4–8 px (círculos solo para marcadores/avatares).
3. **Iconos = Lucide real** vía `{{i:...}}` / `ico('...')`. Nunca dibujes un `<path>` a mano. Un icono distinto por significado: ninguno repetido con sentido distinto.
4. **Una pantalla, sin scroll** (página ni cajas internas). Lo que no cabe se pagina/agrupa. `tools/regress.py` lo mide en 5 tamaños (1280×800 … 1920×1080).
5. **Cero dependencias**: nada de CDN, fuentes web, librerías ni `fetch`. Abre con doble clic.
6. **Cero texto de ayuda impreso** en la interfaz: la ayuda va en `title`/`aria-label` del control. Todo control tiene `aria-label`.
7. **Nada de modos invisibles**: todo modo (dibujar, responder, comparar, tramo…) se ve (rótulo/placeholder/botón activo) y se suelta solo cuando ya no aplica. Esc lo cierra.
8. **Todo cambio es deshacible**: usa `commit(label, undo, redo)` (Ctrl+Z global). El `label` va en infinitivo pasado: «Nota 3 añadida». Si tu cambio muta el DOM, `undo` y `redo` deben dejarlo EXACTAMENTE como estaba.
9. **La selección es derivada del fotograma** («en pantalla» solo si el fotograma mostrado es el de la entrada; ver `syncSel`). No inventes un segundo estado de selección.
10. **Un control = una función** y debe leerse sin explicación. Hit area mínima 28×28 px en controles nuevos. Texto ≥ 11 px y contraste ≥ 4.5:1 en lo nuevo (`#6b6b6b` sobre blanco es el gris más claro permitido para texto).
11. Si añades un `// icons: a, b` en app.js, el build incluye esos iconos aunque se pidan dinámicamente.
12. No renombres ids/clases existentes ni cambies las firmas de funciones que no son tuyas: otros agentes trabajan EN PARALELO sobre el mismo código y luego se fusiona con git.
    Mantén tus cambios **localizados** (funciones nuevas con tu prefijo, bloques cortos en los puntos de enganche), sin reformatear ni mover código ajeno.

## Mapa del código (estado base)
- Estado global (app.js): `frame, playing, speed, zoom, viewStart, selId, filterResolved, replyTarget, drawing, tool, strokeWidth`. FPS=24, TOTAL=1440 (60 s).
- Entradas del chat = `<article class="item note|change" data-item="n1|a1" data-kind="note|change" data-frame="300" data-resolved|data-reviewed data-label="Nota 1 · Lucía Méndez" tabindex=0>`.
  Cada una tiene su marcador homónimo en la línea de tiempo: `<button class="marker mk note|change" data-item data-frame>` dentro de `#laneNotes` / `#laneChanges`.
  Marcador de nota = círculo negro con número; de cambio = rombo con «A1». Mismo idioma de formas en el chat (`.mk`).
- Helpers: `cards()` (todas las `.item`), `byId(id)`, `tc(frame)` → «00:00:12:12», `seek(seg)`, `selectItem(id)`, `update()`, `refreshNotes()`, `paginate()`, `goToPage(el)`, `toast(msg)`, `setBtn(btn,icono,texto)`, `ico('nombre','sm')`.
- Historial: `commit(label,undo,redo)`, `undoLast()`, `redoLast()`, `hist[]`, `future[]`. Ya integrado: trazo, borrar dibujos, nota nueva, respuesta, resolver/reabrir, revisar.
- **Puntos de enganche con dueño** (comentarios `HOOK · dueño: agente X` en app.js): `renderMarkers()` (B), `renderRanges()` (A), `cardVisible(c)` (C), `makeNoteCard()/addNote()` (A).
  El dueño puede reescribir SU función; los demás solo la llaman.
- La pagina del chat usa columnas CSS (`#noteContent`, `paginate()`): las tarjetas llevan `break-inside:avoid-column`. Pestañas Abiertas/Resueltas + selector «Cambios del agente».
- Layout: `.main-grid` = `.viewer` (video + `.timeline-panel` + `.dock`, una tarjeta 16:9 exacta, altos mínimos `--tl:160px` `--dock:56px`) | `.sidebar`.
- Datos de ejemplo: n1 Lucía @12:12 (con respuesta del Agente) · a1 cambio @13:19 «Resuelve la nota 1» · n2 Diego @26:00 · a2 cambio @28:05. Conserva su sentido.

## Entrega (obligatoria, en este orden)
1. `python3 tools/build.py` en verde + `tools/regress.py` en verde (actualiza un check solo si cambiaste ese comportamiento A PROPÓSITO; dilo en el informe).
2. Tus pruebas `tools/test-<letra>.py` en verde, con capturas revisadas por ti (Read a `shots/*.png`).
3. `git add -A && git commit -m "<letra>: <resumen>"` en tu clon (commit único o pocos; sin archivos de `dist/`, `shots/`).
4. Escribe `REPORT.md` en la raíz de tu clon (≤ 350 palabras): qué hiciste punto por punto contra tus criterios (✔/✘), ids/atributos/funciones nuevas que otros deben conocer,
   checks de regress que tocaste, y lo que NO pudiste hacer. **Sé honesto: si algo no lo mediste, dilo.** Cuenta con números, no con adjetivos.
5. Cierra tu Chrome (`tools/chrome.sh stop $PUERTO`).
**Escribe código a disco pronto y itera**; no esperes a tener todo pensado. Si te quedas sin turnos, lo que esté escrito y commiteado cuenta: ordena tu trabajo por prioridad.
