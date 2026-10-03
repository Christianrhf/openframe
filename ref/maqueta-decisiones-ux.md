# Decisiones de UX de la maqueta de revisión (tramos, agrupación, filtros, cierre de ronda, decisión, comparar)

Modelo y reglas con las que se construyó la maqueta `VISUAL.html` en la ronda de funciones. Son decisiones de diseño aplicadas (el usuario las pidió como lista; el detalle no lo aprobó pantalla por pantalla): al portarlas a `visor.html`/`server.py`/`visor.sh`, esto es el modelo de datos y de interacción a conservar. El dibujo por fotograma está en `canvas-frame-scoped-drawing.md`.

## Modelo de datos que la maqueta ya asume (hay que dar campo y comando en el visor real)

| Dato | Atributo en la maqueta | Regla |
|---|---|---|
| Tramo de una nota | `data-frame` = entrada, `data-out` = salida | salida > entrada; la nota se ancla en la entrada; el marcador va en la entrada y una barra cubre el tramo |
| Nota con dibujo | `data-drawing="true"` | el borrador vive por fotograma y se adjunta al enviar la nota |
| Cambio → nota que resuelve | `data-resolves` | hoy es `resuelve` en `notes.json` |
| Decisión sobre un cambio | `data-decision="approved\|adjust"`, `data-reviewed="true"` cuando hay decisión | sustituye al «visto» pasivo |
| Estado enviado | `data-sent` en notas abiertas | marca lo mandado al Agente en el cierre de ronda |

El autor automático se muestra como **Agente**, nunca como el nombre de la herramienta.

## Reglas de interacción

- **El Agente responde, Cristian decide.** *Aprobar* cierra la nota enlazada en UN solo paso deshacible. *Pedir otro ajuste* abre el composer en modo respuesta sobre el cambio (rótulo «Ajuste sobre cambio A1») y **solo al enviar** reabre la nota y marca la decisión; Esc no cambia nada. Tras decidir queda «Cambiar decisión». Pendientes = notas abiertas + cambios sin decisión.
- **Selección derivada del fotograma**: el fotograma exacto gana sobre un tramo que lo contiene; «Reproducir tramo» pausa exactamente en la salida.
- **Marcadores densos**: se agrupan por carril cuando el hueco entre cajas medidas es < 4 px; el marcador seleccionado participa en el cálculo y, si cae en un grupo, el grupo lo absorbe y recibe UN trazo `.has-sel` (dejarlo suelto y encima tapaba al grupo vecino: no se veía ni se podía pulsar); su selección se deriva con la misma cadena que `syncSel` (fotograma exacto > nota ya seleccionada en su tramo > primera en su tramo), no con una copia que solo mire el fotograma; clic en un grupo acerca hasta separarlos (máx ×8) y, si siguen juntos, abre una lista. La vista previa (autor, tipo, hora o rango, 110 caracteres) es una tarjeta propia, no `title`, con retardo de 120 ms y recortada al visor.
- **Chat a escala sin scroll**: búsqueda + segmentado Todo/Notas/Cambios siempre visibles; persona, «con dibujo» y revisados detrás de un botón Filtros; la barra mide ≤ 96 px; lo que no cabe se pagina. La búsqueda ignora tildes y mira autor, texto, respuestas, hora y etiqueta.
- **Cierre de ronda**: indicador de pendientes en la cabecera → popover con *Enviar al Agente* (activo con notas abiertas) y *Aprobar corte* (solo con 0 pendientes); todo deshacible.
- **Comparar v01 · v02 · Dividir** arriba a la derecha del video, cortina arrastrable con `role="slider"` y flechas; el modo se ve («Comparando v01 · v02 ✕») y Esc lo suelta; comparar es estado de vista, no va al historial.
- **Posiciones fijas sobre el video**: «Viendo…» arriba-izquierda, comparar arriba-derecha, herramienta de dibujo abajo-centro, rótulo de comparación abajo-izquierda.

## Pendiente en esta línea

Legibilidad (contraste ≥ 4.5:1, letra ≥ 11 px, áreas ≥ 28 px, medido por script) y atajos con una sola tabla de la que sale también la chuleta: segunda ola, medidos con `tools/audit-a11y.py`. El port al visor real tiene plan por fases en `portar-maqueta-a-visor-real.md`; `visor.sh` necesita comandos para tramo y decisión antes de que el Agente pueda usarlos.
