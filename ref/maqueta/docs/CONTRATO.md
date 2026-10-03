# Contrato de datos entre agentes (cuatro agentes trabajan a la vez; respeta estos nombres EXACTOS)

| Dato | Atributo / función | Dueño | Lo usan |
|---|---|---|---|
| Tramo de una nota | `data-out="<fotograma de salida>"` en la `.item` y en su `.marker` (el fotograma de entrada sigue siendo `data-frame`) | A | B (marcadores), C (búsqueda), D |
| Nota con dibujo | `data-drawing="true"` en la `.item` (y `data-drawing` ausente si no hay) | A | C (filtro «Con dibujo») |
| Cambio: nota que resuelve | `data-resolves="n1"` en la `.item.change` | D | D, C |
| Decisión sobre un cambio | `data-decision="approved|adjust"` (ausente = sin decidir) y `data-reviewed="true"` cuando hay decisión | D | C (progreso), B (estado del marcador) |
| Autor de una entrada | texto de `.item-who strong` | base | B (vista previa), C (filtro persona) |
| Texto de una entrada | `.item > p` (primer párrafo) | base | B (vista previa), C (búsqueda) |
| ¿Visible en la vista? | `cardVisible(c)` | C | todos (`c.hidden`) |
| Posición de marcadores | `renderMarkers()` | B | — |
| Barras de tramo | `renderRanges()` | A | — |
| Marcador de grupo | clase `.cluster-marker` (NO lleva la clase `.marker`; los `.marker` reales siguen en el DOM) | B | — |
| Composer | `#noteForm`, `#noteInput`, `#noteTime`, `.composer-top` | A (chips de dibujo y tramo) | D (modo «pedir ajuste» reutiliza `setReply`) |
| Posiciones fijas sobre el video | `.vpill.viewing` arriba-izquierda (top:44px;left:16px) · `.vpill.tool` abajo-centro · **comparar: arriba-derecha (top:44px;right:16px)** · selector de tramo/otros: no sobre el video | base / D | — |

Atajos de teclado que ya existen: Espacio, ←/→ (Mayús = 1 s), Esc, Ctrl/Cmd+Z, Ctrl/Cmd+Mayús+Z / Ctrl+Y. **El agente E (más tarde) añade I, O, N, J/K/L, [ ], ?, Ctrl+Enter** —
A puede cablear `I`/`O` para el tramo, pero solo cuando el foco NO está en un campo de texto.
