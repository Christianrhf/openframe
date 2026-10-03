# REPORT · Agente E — legibilidad, atajos y accesibilidad

`build.py` OK · `regress.py` **59/59** (0 checks tocados) · `test-a` 42/42 · `test-b` 30/30 · `test-c` 24/24 · `test-d` 44/44 · **`test-e` 26/26** · `audit-a11y.py` **0 fallos**.

## E1 · Contraste, tamaños y áreas (`tools/audit-a11y.py`, CDP, 2 tamaños × 2 estados = 4 pasadas)

| Familia | Antes | Después |
|---|---|---|
| (a) contraste < WCAG | **30** (7–8 por pasada: `.crumb-sep` 2,05:1 · `.ago` 2,61 · `/ 00:01:00:00` 3,36 · `.live`/`.tab`/`.count` 3,54 · `#noteTime` 4,48) | **0** ✔ |
| (b) letra < 11 px (marcadores ≥ 9) | **120** (28–32 por pasada; mínimo real 6 px en `.mk.mini.change b`) | **0** ✔ |
| (c) hit area < 28×28 (o 24×24 con ≥ 8 px) | **58** (flechas de carril 22×22 · marcador de nota 22×22 · `#searchInput` 224×18,5 · `.seg-btn` 22 · `.time-link` 22 · `.text-btn` 16,5 · `.a-iobtn` 26) | **0** ✔ |
| (d) control sin nombre accesible | 0 | **0** ✔ |

- Medido sobre 72 (1280) / 87 (1600) elementos con texto y 55 / 62 controles visibles por pasada. El área real incluye los `::before` y, en una casilla, el `<label>` que la envuelve.
- Todo por **valores**: grises → tokens; `font-size:10px→11px` (17 reglas); alturas 22→26/28; `min-height:28px` en `.text-btn`, `.person-opt`, `.chk-row`, `.ink-swatch`, `.cluster-pop button`, `.pill`. Único `::before` nuevo: `.marker:before{inset:-3px}` (22 px de círculo, 28 px de área) y `.searchbox .x:before`.
- **Grises: 19 → 11 literales**, con 6 tokens de texto/borde (`--ink` #171717, `--muted` #6b6b6b mínimo para texto, `--faint` #8c8c8c **solo bordes/iconos**, `--line`, `--line2`, `--ondark`) + 3 superficies (`--tint`=`--wash`, `--hover`, `--fill`). `--faint` ya no pinta ningún texto.
- `.tl` gutter 128→**148 px**: los botones de carril pasan a 28×28 y el rótulo ya no desbordaba (lo detectó `test-b`, lo arreglé yo).

## E2 · Atajos (`SHORTCUTS`, 19 entradas, una sola fuente de verdad)
Nuevos: **K · L · J · , · . · [ · ] · { · } · / · C · N · Ctrl+Entrar · ?**. Documentados sin recablear (`base:true`): Espacio, ←/→, Mayús+←/→, I, O, Esc, Ctrl+Z, Ctrl+Mayús+Z. **Ningún choque**: ninguna tecla nueva estaba ocupada; Esc y Ctrl+Z siguen con sus dueños.
Chuleta `#keysPop`: botón `keyboard` en el cabecero y `?`; 5 grupos en el orden pedido; **19 filas = 19 atajos** (comparado por conteo en el test); Esc cierra y el foco vuelve a `#keysBtn`; cabe sin scroll a 1280×800 y 1600×1000. De `SHORTCUTS` salen también `title` + `aria-keyshortcuts` de **18 controles**.

## E3 · Acabado (recuento estático sobre `src/`)
| | Antes | Después | Objetivo |
|---|---|---|---|
| degradados de color | 0 | **0** ✔ | 0 |
| `box-shadow` con blur | 8 | **8** (las mismas: 6 popovers, 2 vpill/vseg, + la viñeta del vídeo) | ≤ popovers |
| `border-radius` distintos | 14 | **10** → valores base 2/4/6/8/99 px + 50% (los otros 4 son `0` y 3 compuestos de 4 y 8) ✔ | 5 + 50% |
| colores distintos | 40 hex + 8 rgba | **21 hex + 8 rgba** | ≤ 12 |
| `font-size` en CSS | 11 | **7** ✔ (en pantalla: 12 → 8, las dos últimas son la misma `clamp()` del titular) | ≤ 7 |

Foco: un solo trazo de 2 px en todo (`.keys-pop{outline:none}` porque su propio marco lo delimita); en la tarjeta es borde + 1 px, sin outline doble. `prefers-reduced-motion:reduce` apaga transiciones y animaciones (medido con `Emulation.setEmulatedMedia`). `aria-live="polite"` en `#resultCount` y `#toast`. Orden de Tab verificado por zonas (vídeo→tiempo→anotar→chat→composer), 0 desórdenes, 0 `tabindex` positivos.

## Lo que otros deben conocer
`SHORTCUTS` (array), `eOpenKeys/eCloseKeys/eToggleKeys`, `eNewNote`, `eToggleCompare`, `ePlayOrFaster`, `eFocusSearch`, `eWireKeyHints`, `eInField`. Ids `keysBtn`, `keysPop`; clases `.keys-pop/.keys-group/.keys-row/.keys-keys/.keys-sep`. Tokens nuevos `--ondark`, `--fill`. Fuera de mi sección toqué **una línea**: el `hint` de `setPlaying()` (ahora lista Espacio·K·L, porque reescribe el `title` en cada cambio).

## Honestidad / lo que no hice
- **`≤12 colores` no se alcanza**: 21 hex = 11 neutros (texto, bordes, 3 superficies, fondo del vídeo, blanco, negro) + 6 de la paleta del trazo (obligatoria por SPEC) + 4 del SVG de la escena y la viñeta (`#262626`, `#00000055`, `#ffffff99`…), que no son míos. Bajarlo más exige rediseñar superficies, no cambiar valores.
- Las 8 sombras con blur son **las que ya había** (no añadí ninguna); la viñeta `inset 0 0 100px` del vídeo es de la base.
- Subir tamaños y áreas engordó las tarjetas (a1 206→207 px) y el chat pasó a 4 páginas a 1280×800; lo recuperé bajando paddings/márgenes y **vuelve a 3 páginas** (igual que antes) y 2 a 1600×1000. Medido, no estimado.
- El cálculo de contraste usa el fondo **compuesto de los ancestros**: no mira el píxel real, así que el texto sobre el SVG del vídeo se mide contra `#222`, no contra la imagen.
- La caja de un `::before` se mide desde el *padding box* sin deshacer `transform`: en el rombo girado (`.marker.change`) el área medida es su AABB, mayor que el rombo real.
- No probé lectores de pantalla reales, ni pantalla completa, ni `forced-colors`. El orden de Tab lo deduje del DOM (ningún `tabindex` positivo), no pulsando Tab 60 veces.
- Capturas revisadas con Read: `e-01` (1280 sin desbordes), `e-02`/`e-03` (chuleta 1280 y 1600), `e-04` (fila de acciones), `e-05`/`e-06` (chat), `e-07` (línea de tiempo), `e-08` (cabecera), `e-09` (glifo mini A1 a 9 px) — con pares antes/después en `e-06..e-08`.
