# MAPA DE REGIONES · réplica literal (base dejada por R1)

Qué contenedor del visor real corresponde a cada pieza de `ref/maqueta/src/body.html`, quién
lo rehace y qué ids/clases son estables (R1 no los va a tocar más: constrúyete encima).

## Esqueleto, después de R1

```
body                       (flex columna; sin scroll)
├─ svg.sprite              iconos Lucide (ids i-*)
├─ header.topbar           ← R1 · = <header> de la maqueta           [HECHO]
│   └─ #hdrPop             menú «⋯» (popover de la maqueta)
├─ #cortePop               lista real de cortes («Corte vNN»)
└─ div.main                (flex fila)
    ├─ #navhandle          asa plegada: «proyectos ▸» + insignias     ← R2
    ├─ .rail               proyectos (ancho 0 cuando está plegada)    ← R2
    ├─ .vcol               videos del proyecto                        ← R2
    └─ .workspace          ← R1 · = main.workspace de la maqueta      [HECHO]
        └─ .main-grid      ← R1 · 1fr | clamp(380,29vw,460), gap 16   [HECHO]
            ├─ .stage      = section.viewer de la maqueta
            │   ├─ .screen       = .video (marco, escena, dibujo)     ← R3
            │   │   ├─ #fw/#v/#cv  video + lienzo de dibujo
            │   │   ├─ #cmpWrap/#cmpCurtain/#cmpCtl  comparar v01·v02 ← R3
            │   │   └─ #cmpPill, #nocodec            rótulos          ← R3
            │   └─ .transport    = .timeline-panel + .dock juntos
            │       ├─ .tlinesa  banda de tiempo (#scrub,#tlrail)     ← R4
            │       ├─ .tp-row   transporte + reloj + fps + medir     ← R3
            │       ├─ .tlctrls  zoom, saltar a nota/cambio           ← R4
            │       └─ .tools    barra «Anotar» (lápiz, color, grosor) ← R4
            └─ .side       = aside.sidebar de la maqueta              ← R5
                ├─ .side-head   título + estado del corte (#roundStatus)
                ├─ .x2filters   búsqueda y filtros
                ├─ #list        el hilo de notas
                ├─ .x2pager     paginación (R5 la quita: un solo hilo)
                └─ .editor      composer «Nueva nota»
    (popovers position:fixed, fuera de la rejilla: #swPop, #shPop, #p5Pop)
```

## Contratos que R1 deja cerrados

- **Tokens**: `:root` ya trae los de `ref/maqueta/src/app.css` (`--ink --muted --faint --ondark
  --line --line2 --paper --wash --tint --hover --fill --mono --ctl --grp --tl --dock`) y `--hdr`
  (56 px de cabecera). Los nombres viejos (`--fg`, `--panel`, `--accent`…) siguen existiendo pero
  son **alias**: no tienen valor propio. **No declares colores a mano**: usa los tokens.
- **Radios**: `--radius` 8 (tarjeta), `--radius-ctl` 6 (control), `--radius-xs` 4 (pieza menuda).
- **Tipografía**: `--sans` y `--mono` son las de la maqueta; `body` es 13 px / 1.5. El tema
  oscuro se borró (la réplica es a tema claro).
- **Piezas comunes ya replicadas**: `.btn` (34 px, radio 6, borde `--line2`, peso 550),
  `.btn.black`/`.btn.pri` (negro), `.btn.sm` (28 px), `.ctl` (botón de icono de 34 px, negro
  cuando está activo), `.pill`, `.avatar`, `.toast`, el anillo de foco (2 px, offset 2) y el
  popover (`#hdrPop`/`#cortePop`: `#fff`, borde `--line2`, radio 8, sombra `0 8px 28px rgba(0,0,0,.16)`).
- **Rejilla**: `.workspace` (padding 16/24) y `.main-grid` son de R1. Si una región necesita otro
  reparto, háblalo en su REPORT: no lo cambies por tu cuenta.
- **Barra de proyectos plegada por defecto**: `document.body.classList.add("nav-plegado")` al
  cargar; solo queda abierta si el usuario la abrió antes (`localStorage openframe:nav`).
  `body.nav-plegado .workspace{padding-left:54px}` (30 del asa + 24 de la maqueta).

## Lo que cada agente tiene que rehacer encima

| Región | Contenedor estable | Maqueta | Agente |
|---|---|---|---|
| Barra de proyectos y videos | `#navhandle`, `.rail`, `.vcol` | (no existe) | R2 |
| Escena de video + transporte | `.screen`, `.tp-row` | `.video`, `.tl-bar` | R3 |
| Línea de tiempo + «Anotar» | `.tlinesa`, `.tlctrls`, `.tools` | `.timeline-panel`, `.dock` | R4 |
| Conversación | `.side` y todo lo de dentro | `aside.sidebar` | R5 |

## Pendiente conocido (no es de R1)

- `.screen` pinta el video centrado y pequeño sobre `--wash`; en la maqueta `.video` ocupa el
  ancho de la columna con relación 16/9 y radio `8px 8px 0 0`. Es de **R3**.
- `.transport` ya es la mitad inferior de la tarjeta (borde y radio abajo), pero dentro siguen
  las tres filas viejas: las rehacen **R3** (`.tp-row`) y **R4** (`.tlinesa`, `.tlctrls`, `.tools`).

## Arnés de fidelidad

`tools/fidelidad.py` + `tools/fidelidad-map.json`. Añade tu región al JSON (≥ 15 pares) y
córrela a 1440×900 y 1600×1000:

    CDP_PORT=<tu chrome> /tmp/o8/venv/bin/python tools/fidelidad.py --api http://127.0.0.1:<tu server> --region <tu region>

Deja también la captura lado a lado (`shots/fid-<región>.png`, campo `captura` del JSON) y
**míralas con Read**: que pase la tabla no basta.
