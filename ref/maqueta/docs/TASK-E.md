# TAREA E · Legibilidad, atajos y accesibilidad (pasada final sobre la maqueta YA FUSIONADA)   (puerto 9356 · modelo Opus)

La base ya incluye lo de A (dibujo por fotograma + tramos), B (agrupar marcadores + vista previa), C (filtros, búsqueda, cierre de ronda) y D (aprobar/pedir ajuste, comparar v01·v02). Eres el dueño de la sección «E» del CSS y de una pasada transversal.
Lee `docs/SPEC.md`, `docs/CONTRATO.md`, `REPORT-*.md` de cada agente (si están en `docs/reports/`) y todo `src/`. Los cambios transversales deben ser **mínimos y localizados**: valores, no reestructuración.

## Problema medido en la base (antes de A–D)
- **7 grupos de texto no llegan a contraste 4.5:1**: `.ago` (#999 → 2.85:1), `.tab`/`.count`/`.live` (#888 → 3.54), `/ 00:01:00:00` (#8c8c8c → 3.36), separador `/` del breadcrumb (#b5b5b5 → 2.05), un span de reloj (#777 → 4.48).
- **17 estilos de letra ≤ 10 px** (`.ago`, `.count`, `.live`, `.now`, `.link-chip`, `.eyebrow`, `.tl-corner`, `small`, `avatar`, …).
- **Hit areas pequeñas:** `.text-btn` 17 px de alto, flechas de carril 22×22, paginador 26×24, `.time-link` 22 px.
- Sin chuleta de atajos; sin atajo para nota nueva, tramo, J/K/L ni para ir a la nota anterior/siguiente.

## E1 · Contraste y tamaños (prioridad 1)
- Escribe `tools/audit-a11y.py` (CDP) que mida: (a) contraste de TODO texto visible contra su fondo efectivo (WCAG; texto < 18.66 px normal → 4.5:1), (b) tamaño de letra mínimo, (c) hit area de todo `button, select, input, [role=slider], .item` visibles (≥ 28×28, o ≥ 24×24 si está dentro de una fila con ≥ 8 px de separación), (d) botones sin nombre accesible. Imprime lista de fallos con selector, valor y ejemplo. **Objetivo final: 0 fallos en (a), (b), (c), (d)** salvo numerales dentro de marcadores (`.mk`, ≥ 9 px).
- Arréglalos con **cambios de valor** (grises más oscuros, `font-size: 11px`, `min-height`/padding invisible o `::before` para ampliar el área sin engordar el diseño). Consolida los grises en ≤ 6 tokens (`--ink`, `--muted` #6b6b6b mínimo para texto, `--faint` solo para bordes/iconos decorativos).
  Reporta antes/después con números (nº de fallos, nº de tamaños de letra distintos, nº de grises distintos).

## E2 · Atajos y chuleta (prioridad 2)
- **Una sola fuente de verdad:** un array `SHORTCUTS` (grupo, teclas, descripción, acción) del que sale tanto el manejador de teclado como la chuleta. Botón `keyboard` (Lucide) en el cabecero abre un popover «Atajos» agrupado (Reproducción · Navegación · Notas · Dibujo · General); `?` también lo abre; Esc cierra; foco vuelve al botón.
- Atajos (solo cuando el foco NO está en input/textarea/select/contenteditable, salvo Ctrl+Enter): `Espacio` play/pausa (ya), `←/→` fotograma y `Mayús+←/→` 1 s (ya), `,`/`.` fotograma, `J` −1 s, `K` pausa, `L` play (pulsar otra vez = siguiente velocidad), `N` nota nueva (pausa, enfoca el composer en el fotograma actual), `I`/`O` entrada/salida de tramo (los cableó A; si ya existen no los dupliques), `[`/`]` nota anterior/siguiente, `{`/`}` (Mayús) cambio anterior/siguiente, `/` enfoca la búsqueda (la creó C), `C` activa/desactiva comparar (lo creó D; si no existe una función pública, añade un hook mínimo), `Ctrl/Cmd+Enter` envía desde el textarea, `Esc` cierra popover/modo.
  Si un atajo choca con otro existente, gana el existente; documenta el choque en tu informe. Cada botón con atajo lleva el atajo en `title` y `aria-keyshortcuts`.
## E3 · Pulido transversal (prioridad 3)
- Foco: anillo `focus-visible` coherente (2 px, un solo trazo, sin halo doble); al cerrar un popover el foco vuelve a su disparador; orden de Tab lógico (video → línea de tiempo → barra de anotar → chat → composer).
- `prefers-reduced-motion: reduce` apaga transiciones/animaciones. `aria-live="polite"` en el contador de resultados y en `#toast`.
- Auditoría de acabado con números (antes/después): nº de `linear-gradient`/`radial-gradient` (objetivo 0), `box-shadow` con blur (objetivo ≤ popovers/hover-previews), `border-radius` distintos (≤ 5 valores + 50%), colores distintos (≤ 12 incluyendo la paleta del trazo), `font-size` distintos (≤ 7).

## Criterios de aceptación
1. `tools/audit-a11y.py`: 0 fallos en las 4 familias a 1280×800 y 1600×1000 (con el chat en su estado inicial y con una nota seleccionada). 2. `regress.py` y los `test-*.py` de A–D siguen en verde (ejecútalos todos; si alguno cae por tu cambio, es tuyo). 3. Chuleta: abre con `?` y con el botón, cierra con Esc, foco de vuelta, contiene todos los atajos de `SHORTCUTS` (compara conteo). 4. Cada atajo nuevo probado por CDP (`tools/test-e.py`, ≥ 16 checks). 5. Capturas: chuleta, textos antes/después de contraste, fila de acciones de una tarjeta con áreas de 28 px, 1280×800 sin desbordes.
