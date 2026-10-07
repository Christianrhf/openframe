# R1 · cimientos de la réplica literal

## Fidelidad
**72/72 pares pasan** (36 pares × 1440×900 y 1600×1000): tokens 10, encabezado 16, rejilla 10.
`tools/fidelidad.py` + `tools/fidelidad-map.json`; sale 1 si algo falla.
Capturas lado a lado revisadas con Read: `shots/fid-tokens.png`, `fid-encabezado.png`,
`fid-rejilla.png`, y la pantalla entera `shots/r1-final-1600.png`.

## Qué se hizo
- **Tokens y tipografía**: `:root` trae los de `ref/maqueta/src/app.css`; los nombres viejos
  (`--fg`, `--panel`, `--accent`…) quedan como alias sin valor propio. Tema oscuro **borrado**.
  `.btn`, `.ctl`, `.pill`, `.avatar`, `.toast`, popovers y anillo de foco = los de la maqueta.
- **Encabezado literal**: brandmark 23 px (borde derecho 7), «OpenFrame» 20/750/−1 px, migas
  «Proyectos / <proyecto real>», píldora «N pendientes» real, miniaturas, «Corte vNN» (lista
  real de cortes, abre el elegido), botón negro «Compartir revisión» (popover real de
  invitados) y avatar `CH`.
- **Rejilla**: `.workspace` (16/24) > `.main-grid` `1fr | clamp(380px,29vw,460px)`, gap 16.
- `docs/historial/rondas/MAPA-REGIONES.md` con los contenedores estables de R2–R5.

## Diferencias permitidas (las tres)
1. **Datos reales**: proyecto, cortes, pendientes, iniciales.
2. **Funciones que la maqueta no tiene**: Nuevo proyecto, Para Agente, Copiar, Exportar, build
   y «en línea» → menú «⋯» con el popover de la maqueta; miniaturas como botón de icono.
   Ningún id cambió.
3. **Barra de proyectos plegada** (`ref/captura-rail.png`), ahora estado por defecto; a su
   izquierda la rejilla lleva 54 px (30 del asa + 24). Por eso `gridTemplateColumns` no se
   compara entero: sí el gap y el ancho de Conversación.

## Pruebas
`tools/test-R1.py` **43/43**. `tools/run-todo.sh` entero en verde (x2 11, i2 38, p4 27, p5 61,
p7 45, p6 90, bugs-r2 4/4, guest 619, ataque 159, e2e-invitado 142, inv 55). p6 falló una vez
por carrera del `<video>` (AbortError/404) y pasó al repetir: **flaky, no regresión**.
Actualicé con intención dos checks: p5 despliega la barra antes de medir su scroll; p6 mira
`--muted`/`--fg-mute` en vez del literal viejo. Ensanché `#navOpen` a 28 px (agarre AA): antes
casi nunca se veía.

## No verificado
El interior de `.screen`, `.transport`, `.rail`/`.vcol` y `.side` sigue siendo el viejo: es de
R2–R5. No probé Safari ni anchos < 1280.
