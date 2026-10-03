# TAREA A · Anotaciones: el dibujo pertenece a su fotograma + notas con tramo   (puerto 9351 · modelo Opus)

Eres el dueño de: `renderRanges()`, `makeNoteCard()`, `addNote()`, el código de dibujo (`layer.on*`, `toggleDrawing`, `drawBefore`…), el bloque `.composer*`, la sección «A» del CSS.
Lee primero `docs/SPEC.md` y `docs/CONTRATO.md`. Un agente B toca marcadores, uno C el filtro del chat y el cierre de ronda, uno D las tarjetas de cambios y el video.

## Problema medido
1. **Hoy el dibujo es global.** Dibujé en el 00:12 y al saltar al 00:50 el trazo seguía encima del video. Un dibujo debe pertenecer a un fotograma.
2. **Muchas notas son de un tramo**, no de un punto (la nota 2 de Diego habla de la música tapando «la última frase», que dura varios segundos).

## A1 · Dibujo por fotograma (prioridad 1)
- Modelo: los trazos se dibujan en un **borrador por fotograma** (`drafts[frame]`). El borrador solo se ve cuando `frame === ese fotograma`. Al cambiar de fotograma la capa cambia sola (también al reproducir, al seek, al deshacer).
- **Al crear una nota** (`addNote`) con borrador en el fotograma de la nota (su `in`), los trazos se **adjuntan a la nota** (`noteDrawings[id]`), el borrador se vacía y la `.item` recibe `data-drawing="true"`.
  La tarjeta lleva un indicador visible «Dibujo» (icono `pencil`/`pen-line`, no un emoji) en su fila de meta. Seleccionar la nota (frame === su fotograma) muestra su dibujo sobre el video; al salir de ese fotograma desaparece.
- **Composer:** cuando hay borrador en el fotograma actual aparece un chip arriba del textarea: «Dibujo · N trazos» con botón ✕ «quitar» (Lucide `x`). Quitarlo es deshacible. Con borrador, enviar la nota SIN texto está permitido (un dibujo es una nota válida: el texto queda «(sin texto)» — decide tú el copy, corto) — pero sin borrador y sin texto sigue sin enviarse.
- «Borrar dibujos» (papelera) borra **solo el borrador del fotograma actual** (title: «Borrar el dibujo de este fotograma»); si no hay, el botón está desactivado (`disabled`) y el aviso lo dice. Deshacer/rehacer siguen funcionando para trazo, borrar, nota con dibujo (deshacer una nota con dibujo **devuelve el borrador** a su fotograma).
- Dibujar con una nota seleccionada NO modifica el dibujo de esa nota: crea/continúa el borrador (se adjuntará a la próxima nota).
- Pantalla completa y `preserveAspectRatio="none"` no cambian. El dato de ejemplo n1 puede llevar un dibujo precargado (una flecha + un círculo sobre el caballo, SVG simple en el espacio 1000×562.5) para que se vea el estado desde el primer momento.

## A2 · Notas con tramo (prioridad 2)
- Composer: grupo «Tramo» con dos botones de icono + etiqueta corta, **Entrada** y **Salida** (iconos Lucide distintos entre sí y distintos de cualquier otro control; p. ej. `arrow-right-to-line` / `arrow-left-to-line`), que fijan entrada/salida en el fotograma actual. Teclas `I`/`O` hacen lo mismo cuando el foco no está en un campo.
  Con tramo definido, un chip muestra `00:26:00 → 00:29:04 · 3,2 s` con ✕ para quitarlo, y la hora del composer (`#noteTime`) muestra el rango. Reglas: salida > entrada (si no, aviso y no se aplica); poner la entrada después de la salida limpia la salida.
- Al enviar: la nota se ancla en `in` (`data-frame`) y lleva `data-out` (también el marcador). Tarjeta: la hora muestra `in → out` y duración.
- **`renderRanges()`**: en el carril «Notas» dibuja una barra por cada nota con tramo (de `in` a `out`, recortada a la ventana visible, altura ~6 px, 1 px de borde negro y relleno gris claro; seleccionada = relleno negro). El marcador circular sigue en `in` por encima de la barra. Clic en la barra selecciona la nota.
- **Selección derivada:** una nota con tramo está «en pantalla» si `in <= frame <= out` (y no hay otra entrada con ese fotograma exacto; el match exacto gana). `selectItem` salta a `in`. Ajusta `syncSel` mínimamente.
- Botón en la tarjeta con tramo: **«Reproducir tramo»** (icono propio, p. ej. `repeat-1`/`play`-variante; que no confunda con play general): reproduce de `in` a `out` y se pausa en `out`.
- Dato de ejemplo: convierte **n2** en tramo `26:00 → 29:04` (fotogramas 624 → 700); a2 (677) queda dentro del tramo: comprueba que exacto > tramo.
- Todo con `commit(...)` (Ctrl+Z).

## Criterios de aceptación (mídelos; cuéntalos en REPORT.md)
1. Dibujar a 00:12 → saltar a 00:50: `#drawLayer` tiene **0 trazos visibles**; volver a 00:12: reaparece.
2. Crear nota con dibujo: `data-drawing="true"`, indicador en la tarjeta, borrador vacío, y al seleccionar la nota el dibujo se ve; Ctrl+Z: nota fuera y borrador de vuelta.
3. Nota con tramo: barra con ancho = (out−in)/60 × ancho del carril (±2 px) a zoom 1 y a zoom 4 (medido con getBoundingClientRect); clic en barra selecciona.
4. `regress.py` sigue en verde (59 checks) y escribes `tools/test-a.py` con ≥ 12 checks nuevos de lo anterior.
5. Capturas revisadas: composer con chip de dibujo, composer con tramo, carril con barra (seleccionada y no), tarjeta con indicador y rango. Nada se desborda en 1280×800.
