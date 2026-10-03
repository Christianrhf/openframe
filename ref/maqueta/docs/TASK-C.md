# TAREA C · El chat a escala (filtros + búsqueda) y el cierre de ronda   (puerto 9353 · modelo Sonnet)

Eres el dueño de: `cardVisible(c)`, el bloque `.side-head` / `.tabs` / `.review-filter` del HTML, `refreshNotes()` (solo su lógica de visibilidad/contadores), la sección «C» del CSS y el cabecero derecho (`.header-right`) para el cierre de ronda.
Lee `docs/SPEC.md` y `docs/CONTRATO.md`. A añade `data-drawing`/`data-out`, D añade `data-decision`/`data-resolves`; tú **lees** esos atributos aunque aún no existan (trátalos como ausentes) y pruebas poniéndolos a mano.

## Problema medido
Con 12 notas el chat ya necesita 4 páginas (2 entradas por página). No hay forma de filtrar por tipo ni persona ni buscar. Y no se ve qué falta para terminar la ronda.

## C1 · Filtros y búsqueda (prioridad 1)
- Barra bajo las pestañas, **altura total ≤ 96 px** (ahora el feed ya está justo). Siempre visible: **búsqueda** (icono `search`, ✕ para limpiar, placeholder corto) y un **segmentado Todo · Notas · Cambios** con el número de cada uno.
  Detrás de un botón «Filtros» (icono `sliders-horizontal`, punto/contador cuando hay filtros activos): **Persona** (Todas + los autores que existan, derivados del DOM), **Con dibujo** (`data-drawing="true"`), **Cambios revisados** (mostrar/ocultar; sustituye al select actual «Cambios del agente: solo sin revisar / todos» manteniendo su comportamiento por defecto = ocultar revisados) y un enlace **Limpiar filtros**.
- `cardVisible(c)` = pestaña (abiertas/resueltas) ∧ tipo ∧ persona ∧ dibujo ∧ revisados ∧ búsqueda. La búsqueda ignora mayúsculas y tildes y mira: autor, texto (incluidas respuestas), hora («12:12», «00:26»), y etiquetas «nota 1» / «A1».
- Contador de resultados «N de M» (texto pequeño, ≥ 11 px). Estado vacío: «Ningún resultado» + botón «Quitar filtros». Cambiar un filtro lleva a la página 1; seleccionar algo fuera de página sigue saltando a su página (`goToPage`).
- Los marcadores de entradas filtradas se atenúan en la línea de tiempo (`.filtered-out`, opacidad ~.3; añádelo en `refreshNotes`, B pinta los marcadores). Los contadores de las pestañas siguen contando solo notas abiertas / resueltas (sin filtros).

## C2 · Cierre de ronda (prioridad 2)
- En `.header-right`, un indicador de **pendientes** = notas abiertas + cambios sin decisión (`data-reviewed !== "true"`): «3 pendientes» o «Todo al día» (con `check`). Clic → popover «Cierre de ronda» con las dos filas (Notas abiertas N · Cambios sin revisar M; cada una con enlace «Ver» que aplica el filtro correspondiente y cierra el popover) y dos acciones:
  **Enviar al Agente** (activa si hay notas abiertas; marca esas notas con `data-sent="true"` + pequeño badge `send` en la tarjeta; el estado de cabecera pasa de «En revisión» a «Con el Agente»; toast con el número) y **Aprobar corte** (activa solo con 0 pendientes; estado «Corte v02 aprobado» con `badge-check`).
  Todo con `commit(...)` (Ctrl+Z revierte estado y badges). Esc/clic fuera cierra el popover. Reemplaza el `.pill` «En revisión» actual por este estado (misma posición).
- El indicador y los estados se actualizan solos al resolver/reabrir/revisar (`refreshNotes`).

## Criterios de aceptación (mídelos)
1. Con 20 notas creadas por script: buscar «caballo» deja solo las coincidentes; segmentado Notas/Cambios suma bien; persona filtra; «Con dibujo» (poniendo `data-drawing` a mano en 3) deja 3; «N de M» correcto en cada caso; vacío muestra el estado y «Quitar filtros» restaura.
2. Altura de la barra de filtros medida ≤ 96 px a 1280×800 y 1600×1000; **0 scroll** en página y cajas; regress.py en verde (ajusta SOLO los checks que dependían del select antiguo y dilo).
3. Cierre de ronda: con 1 nota abierta «Aprobar corte» desactivado; resolver todo + revisar cambios → activo → estado aprobado; Ctrl+Z lo deshace; «Enviar al Agente» marca notas y cambia el estado.
4. `tools/test-c.py` con ≥ 14 checks. Capturas: barra de filtros, popover de filtros con filtros activos, vacío, popover de cierre de ronda, cabecero en los tres estados.
