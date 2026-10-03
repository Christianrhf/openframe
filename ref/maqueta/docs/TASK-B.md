# TAREA B · Densidad de la línea de tiempo: agrupar marcadores + vista previa   (puerto 9352 · modelo Sonnet)

Eres el dueño de: `renderMarkers()`, la sección «B» del CSS, los estilos de `.marker` y de los carriles. Lee `docs/SPEC.md` y `docs/CONTRATO.md`.
Otro agente (A) dibuja barras de tramo con `renderRanges()` y añade `data-out`: no lo toques; tus agrupaciones solo consideran los marcadores circulares/rombos.

## Problema medido
Con 12 notas en el minuto hay **14 pares de marcadores solapados** (círculos de 22 px sobre ~850 px de carril): no se puede pulsar uno concreto ni leerlo.
Además un marcador solo tiene `title` nativo (sin autor ni texto, aparece tarde).

## B1 · Agrupar (prioridad 1)
- En `renderMarkers()`: por carril, los marcadores cuya distancia entre centros sea < su ancho + 4 px **se agrupan** en un marcador de grupo `.cluster-marker` (botón; NO lleva la clase `.marker`; los `.marker` reales siguen en el DOM con `hidden`/clase y `data-clustered`).
  Distinto de nota y cambio, blanco y negro, ≥ 24 px, número legible (≥ 10 px). Un grupo de notas y un grupo de cambios se distinguen por forma como los marcadores sueltos.
- Regla: **el marcador seleccionado nunca se agrupa** (se dibuja suelto, encima). El grupo se recalcula con el zoom y con la ventana visible; al hacer zoom los grupos se deshacen.
- **Clic en un grupo:** acerca la línea de tiempo (usa `zoom`/`viewStart`/`setZoom`, sin pasar de x8) centrando el grupo hasta que sus miembros se separen; si a x8 siguen juntos, abre un **popover de lista** anclado al grupo (cada fila: marcador mini + autor + hora + 40 chars; clic selecciona; Esc/clic fuera cierra).
- Con 0–1 marcadores cercanos todo se ve exactamente como antes.

## B2 · Vista previa al pasar el ratón / foco (prioridad 2)
- Tarjeta flotante propia (no `title`): glifo del marcador + autor + tipo + hora (si hay `data-out` muestra `in → out`) + los primeros ~110 caracteres del texto (`.item > p`).
  Para un grupo: hasta 4 filas + «+N más». Aparece a los 120 ms de hover o al enfocar con teclado, desaparece al salir; posición centrada sobre el marcador, **recortada para no salirse del visor** y que invierte debajo si no hay sitio arriba. No debe aparecer mientras se arrastra el cabezal ni tapar el cabezal (z-index por debajo del popover de grupo).
  Los marcadores conservan `aria-label` y ganan `aria-describedby` hacia la vista previa. Quita el `title` de los marcadores (o lo duplicaría).
- La etiqueta del carril («Notas», «Cambios») muestra además el total en gris pequeño (p. ej. `Notas 12`); no desbordes el gutter de 128 px a 1280×800.

## Criterios de aceptación (mídelos)
1. Con 12 notas en 60 s (las del caso medido: frames 100,112,130,150,165,180,200,210,225,240 + las 2 ya existentes): **0 pares de marcadores/grupos solapados** a zoom 1 y a zoom 2, 4 y 8 (bounding boxes, 40 notas aleatorias incluidas). Prueba con notas creadas por `seek(f/24); noteInput.value=...; noteForm.requestSubmit()`.
2. Clic en un grupo de 5 acerca (zoom sube) y los miembros quedan separados; a x8 con miembros a 1 fotograma de distancia aparece el popover.
3. `renderMarkers()` con 200 notas: medir `performance.now()` y reportarlo (objetivo < 30 ms).
4. La vista previa: aparece con el texto correcto, queda dentro del visor en marcadores de los extremos (frame 0 y 1440) y en 1280×800.
5. `regress.py` en verde; `tools/test-b.py` con ≥ 12 checks nuevos. Capturas: carril denso antes/después, vista previa de nota, de cambio y de grupo, popover.
