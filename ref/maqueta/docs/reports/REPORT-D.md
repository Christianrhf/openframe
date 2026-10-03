# REPORT · Agente D — decidir (aprobar / pedir ajuste) y comparar v01 · v02

## Criterios (`tools/test-d.py`: 44 checks, 44 en verde)
1. ✔ Aprobar a1: `data-reviewed=true`, `data-decision=approved`, n1 `data-resolved=true`, chip «Aprobado», 1 commit. Ctrl+Z revierte las tres cosas; Ctrl+Mayús+Z las repone.
2. ✔ Pedir ajuste: rótulo exacto «Ajuste sobre cambio A1», placeholder propio. Esc y «Cancelar»: `hist.length` igual, sin decisión. Enviar: respuesta en el hilo + `adjust` + `reviewed=true` + n1 reabierta, 1 commit; Ctrl+Z revierte todo.
3. ✔ Dividir: arrastres a 25/75/50/25 % → tirador medido con getBoundingClientRect a ±0 px; `clip-path: inset(0 X% 0 0)` en la capa v01; `elementFromPoint` da v01 izquierda / v02 derecha; ←/→ 2 % (Mayús 10 %); Esc sale; clic con modo activo no cambia `playing`.
4. ✔ Fila de acciones: scrollWidth − clientWidth ≤ 0 a 1280×800 (sidebar 380, «Responder» solo icono con title/aria-label) y 1600×1000 (460, con texto); botones ≥ 28 px.
5. ✔ `regress.py` 59/59, ningún check tocado. Capturas revisadas en `shots/`: tarjeta en 3 estados (+1280), composer en ajuste, video v01, Dividir 50 % y 25 %, marcadores en 3 estados.

## Lo que deben conocer los demás
- `.item.change`: `data-resolves`, `data-decision="approved|adjust"` (ausente = sin decidir), `data-reviewed="true"` ⇔ hay decisión. El `.marker` homónimo recibe el mismo `data-decision` (`dSetDecision`).
- Botones: `.approve-btn`, `.adjust-btn`, `.redecide-btn`, `.compare-btn`; `.review-btn` ya no existe. Texto de `.reply-btn` en `<span>` (oculto ≤ 1400 px).
- Chip `.status`: `.s-un` / `.s-ok` «Aprobado» / `.s-adj` «Ajuste pedido». Iconos nuevos: `wrench`, `replace`, `columns-2`, `film`, `history`, `chevrons-left-right`.
- Funciones: `dApprove`, `dRedecide`, `dStartAdjust/dEndAdjust/dSubmitAdjust`, `dSetCompare('v02'|'v01'|'split')`, `dSetSplit(pct)`. `setReviewed(card,v)` sigue (v=true ⇒ approved).
- Modo ajuste: `dAdjustTarget`; submit interceptado en captura sobre `#noteForm`; clase `adjusting` en el composer; se suelta con Esc, «Cancelar», otro «Responder» o al enviar.
- Video: `#cmpSeg` (`.vseg`, top 44 / right 16), `#cmpCurtain` (`#cmpLine` + `#cmpHandle` role=slider), `#cmpPill` (abajo-izquierda), clon `.scene-v01` (sin `<defs>`, caballo en `translate(1130 338)`). Clases en `#video`: `cmp-v01`, `cmp-split`. `$('video').onclick` base queda envuelto, no editado. En Dividir se oculta `.video-play` (tapaba el tirador al 50 %).

## No medido / límites
- Rótulos «v01»/«v02» a `top:80px` bajo los pills, no en la esquina estricta: comprobado solo en captura.
- No probé pantalla completa ni `.cluster-marker` de B con `data-decision`.
