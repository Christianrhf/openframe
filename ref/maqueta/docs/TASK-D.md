# TAREA D · Cambios del Agente: decidir (aprobar / pedir ajuste) y comparar v01 · v02   (puerto 9354 · modelo Fable)

Eres el dueño de: las `.item.change` (HTML y lógica de sus acciones: `setReviewed`, el handler `.review-btn`), la capa de comparación sobre el video, la sección «D» del CSS.
Lee `docs/SPEC.md` y `docs/CONTRATO.md`. C cuenta pendientes leyendo `data-reviewed`; B pinta los marcadores; A toca el composer (dibujo y tramo) y `addNote`.

## Problema medido
- Un cambio del Agente solo se puede «marcar revisado» (pasivo). El ciclo real es: el Agente responde, **Cristian decide**: o lo aprueba (cierra la nota que lo motivó) o pide otro ajuste (reabre).
- No hay forma de ver el antes y el después de un cambio en su fotograma, que es el valor de un cambio.

## D1 · Decidir (prioridad 1)
- Cada cambio lleva `data-resolves="n1"` (a1→n1, a2→n2). Sustituye «Marcar revisado» por dos acciones con etiqueta visible: **Aprobar** (`check`) y **Pedir otro ajuste** (icono Lucide propio, distinto de `rotate-ccw` que ya es «Reabrir» y de undo/redo).
  - **Aprobar**: en UN solo `commit`: `data-reviewed="true"`, `data-decision="approved"`, y resuelve la nota enlazada (`data-resolved="true"` con el mismo efecto visual que su botón «Resolver»). Estado visible «Aprobado».
  - **Pedir otro ajuste**: abre el composer en modo respuesta sobre el cambio con rótulo explícito («Ajuste sobre cambio A1») y placeholder propio, y **solo al enviar** aplica en un `commit`: `data-decision="adjust"`, `data-reviewed="true"`, reabre la nota enlazada (`data-resolved="false"`) y añade la respuesta al hilo del cambio. Si se cancela (Esc o «Cancelar») no cambia nada y el modo se suelta.
  - Tras decidir aparece un texto-botón «Cambiar decisión» que devuelve el cambio a sin revisar (y deshace sus efectos sobre la nota) — también en un `commit`.
- Estado visible en la tarjeta (chip existente `.status`): «Sin revisar» · «Aprobado» (check) · «Ajuste pedido» (icono). El marcador del cambio en el carril refleja los 3 estados con forma/trazo (blanco y negro): aprobado = el `.done` actual; ajuste pedido = borde discontinuo; sin revisar = el normal. Pide a B por contrato que `data-decision` ya existe; tú añades solo el CSS de esos estados en tu sección (selector `.marker.change[data-decision=…]` sirve sin tocar a B).
- Mantén "Responder" en las tarjetas de cambio. La fila de acciones debe caber **en una línea** con sidebar de 380 px y de 460 px: etiquetas visibles en Aprobar / Pedir ajuste / Comparar; Responder puede quedar solo con icono si hace falta (con `aria-label`/`title`). Hit area ≥ 28 px de alto.
- Los atributos que C lee: `data-reviewed` (boolean como string) debe seguir significando «hay decisión».

## D2 · Comparar v01 · v02 (prioridad 2)
- Control **segmentado arriba-derecha del video** (`top:44px;right:16px`, no solapes `.vpill.viewing` arriba-izquierda ni `.vpill.tool` abajo-centro): `v02` · `v01` · `Dividir` con iconos Lucide (p. ej. `columns-2` para dividir). Activo = relleno negro. Por defecto v02 (estado normal, sin cambios visuales).
- **v01** = el mismo fotograma ilustrado pero con el caballo **entrando** (desplazado a la derecha, recortado por el borde, como dice la nota n1 «el caballo todavía está entrando cuando cortamos»): se genera en JS clonando `.scene` y cambiando el `transform` del grupo del caballo. Rótulo «v01» (esquina) cuando se ve v01. El video v02 queda intacto.
- **Dividir**: cortina arrastrable (`pointer events`, 100% del alto del video): izquierda v01, derecha v02, tirador circular con icono `chevrons-left-right` y `role="slider"` (`aria-valuenow`, flechas ←/→ mueven el tirador 2 %; Mayús 10 %). Rótulos «v01» / «v02» en las esquinas de cada mitad. La capa de dibujo y los `.vpill` quedan por encima.
- **Modo visible y que se suelta solo**: en Dividir/v01 aparece un rótulo «Comparando v01 · v02 ✕» (patrón de `.vpill`, abajo-izquierda para no chocar) y Esc lo cierra. Con el modo activo, un clic en el video **no** reproduce/pausa y el dibujo sigue funcionando según la herramienta.
- En cada tarjeta de cambio, botón **Comparar** (`columns-2`): selecciona el cambio (salta a su fotograma) y entra en Dividir con el tirador al 50 %.
- Comparar es un estado de vista, no un cambio de datos: no va al historial.

## Criterios de aceptación (mídelos)
1. Aprobar a1: `data-reviewed`, `data-decision=approved`, n1 `data-resolved=true`, chip «Aprobado»; Ctrl+Z revierte las tres cosas de golpe; Ctrl+Mayús+Z las repone.
2. Pedir ajuste: composer en modo respuesta con el rótulo exacto; cancelar con Esc no cambia nada (`hist.length` igual); enviar: respuesta en el hilo + `data-decision=adjust` + nota reabierta; Ctrl+Z revierte.
3. Dividir: tirador arrastrado a x=25 %, 50 %, 75 % del video (medido con getBoundingClientRect del tirador ±3 px); a la izquierda se ve la escena v01 y a la derecha v02 (compara el `clip-path`/rect de cada capa); Esc sale; clic en el video con el modo activo no cambia `playing`.
4. La fila de acciones de una tarjeta de cambio no desborda (scrollWidth ≤ clientWidth) a 1280×800 y 1600×1000 y mide ≥ 28 px de alto por botón.
5. `regress.py` en verde (ajusta los checks de revisar/«Marcar revisado» si los hay y dilo), `tools/test-d.py` con ≥ 14 checks. Capturas: tarjeta de cambio en sus 3 estados, composer en «pedir ajuste», video en v01, en Dividir (tirador al 50 % y al 25 %), marcadores de cambio en los 3 estados.
