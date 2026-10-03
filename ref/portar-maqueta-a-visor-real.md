# Portar la maqueta VISUAL.html al visor real (`visor.html` + `server.py` + `visor.sh`)

Plan por fases sacado de leer la app real entera contra la maqueta fusionada (un agente de solo lectura trabajó sobre copias en `/tmp/o8/port-ref/`; las muestras de `data/*/notes.json` iban truncadas y no traían ningún `cambio` ni trazo, así que el formato de esos campos sale del código). Reglas de interacción: `maqueta-decisiones-ux.md`; dibujo: `canvas-frame-scoped-drawing.md`.

## Lo que la app real ya tiene (no rehacer)

- Nota = fila de `notes.json` con `frame` (dato real), `end_frame`, `kind nota|cambio`, `resolved`, `author cristian|claude`, `parent`, `resuelve`, `visto`, `drawing`, `thumb`. Dibujo = `{strokes:[{tool:pen|arrow|rect|ellipse, color, size:3|5|8, pts:[{x,y}] 0..1}]}`, visible solo en su fotograma/tramo.
- API: PATCH de nota acepta `text, resolved, visto, resuelve, kind, end_frame, frame, drawing, thumb`; responder a un cambio ya pasa (el servidor no mira `kind`); el POST de nota ya acepta `drawing`+`thumb`. Los campos nuevos son opcionales: los proyectos viejos cargan sin migración porque el código ignora lo desconocido.
- **La UI nunca genera `thumb`**: el Agente solo «ve» píxeles, así que al enviar una nota con dibujo hay que pintar fotograma + trazos en un canvas y mandar un JPEG ≤ 1280 px en el mismo POST; `visor.sh notas` lo imprime como ruta.
- «Nota 3 / A1» y el rótulo «Agente»: el número se deriva en `decorate()` por `created` y `kind`; `author:"claude"` no cambia, solo el rótulo.

## Fases (cada una desplegable y reversible; `cp X X.bak-$(date +%s)` antes; probar en un proyecto nuevo, nunca en los de Cristian)

| # | Fase | Campos / API nuevos | Riesgo |
|---|---|---|---|
| 1 | **Decidir** (aprobar / pedir ajuste) + «Agente» + número | cambio `decision: approved\|adjust`; deshacer de DOS notas a la vez (tipo `multi`); `visor.sh ajustes` y `[aprobado]/[AJUSTE]` en `cambios-lista` | bajo; cabe en una sesión |
| 2 | **Anotar** (dibujo por fotograma + tramo) | borrador antes de enviar, un solo POST con texto+trazos+`end_frame`+`thumb`; `.a-rangebar` | medio |
| 3 | **Chat a escala** (filtros, búsqueda, «N de M») | ninguno (persona = `author`, dibujo = `strokes.length>0`) | bajo |
| 4 | **Densidad** (agrupar, vista previa) | ninguno; sobre `tlFrac/tlSetView` | medio |
| 5 | **Cierre de ronda** | nota `enviada_el`; video meta `revision:{estado: revision\|con_agente\|aprobado, desde}`; `visor.sh notas <slug> enviadas` | bajo |
| 6 | **Atajos + accesibilidad** | tabla `ATAJOS` existente; I/O, J/K/L, `?`; `.mark` con `role=button` y `tabindex` | bajo (chocan con teclas actuales: gana la existente) |
| 7 | **Comparar v01·v02** | segundo `<video>` sincronizado + cortina con `clip-path`; par = video anterior por `created` | **alto** |

Aceptación por CDP en cada fase (selectores de la maqueta: `.approve-btn`, `.a-rangebar`, `.mk-preview`…), con 0 excepciones; reversa = restaurar los `.bak` (los campos nuevos no rompen el código viejo).

## Decisiones que solo el usuario puede tomar (con la recomendación que se le dio)

1. Lista del chat con scroll (como la maqueta) o paginada — recomendado: scroll. 2. Dos carriles o una banda — recomendado: dos carriles. 3. *Pedir ajuste* reabre la nota o la deja cerrada — recomendado: reabrir. 4. «Con el Agente» hasta aprobar aunque no queden pendientes — recomendado: sí. 5. JPEG por nota con dibujo o solo JSON — recomendado: JPEG. 6. Comparar contra el corte anterior fijo o elegido — recomendado: anterior + selector.

No empezar la fase 1 sin preguntar 3 y 4: cambian el comportamiento de `resolved`.
