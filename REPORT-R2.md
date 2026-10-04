# R2 · navegación de proyectos y videos

## Resultado
Rehice el estado **desplegado** de `.rail` y `.vcol` con el lenguaje literal de la maqueta: panel blanco con borde `--line` y radio 8; cabeceras 13/650; tarjetas 9×14 con borde/radio 8; selección con un único contorno negro de 2 px; metadatos a 11 px; estado del corte en píldora; botones 34 px; objetivos de archivar 28 px. «Nuevo proyecto», «Traer hilos» y «Subir video» quedan visibles en los pies de panel, conservando sus IDs y funciones.

El rail **plegado por defecto** conserva texto vertical «proyectos ▸», ancho de 30 px e insignias. Al plegar, los paneles eliminan también sus márgenes.

## Fidelidad
`tools/fidelidad-map.json`: región `navegacion`, **22 pares por viewport** (44 comparaciones previstas). `tools/fidelidad.py` prepara explícitamente el estado abierto solo para R2.

**No medido:** Chrome 9512 abortó cuatro veces antes de abrir CDP (`Abort trap: 6`) bajo fuerte compresión/swap. Por tanto no se generó ni revisó `shots/fid-navegacion.png`; no afirmo pares aprobados ni cero excepciones JS.

## Pruebas
Añadí `tools/test-R2.py` con **35 checks**. Pasaron: parse JS (un bloque), `py_compile`, JSON (22 pares), HTTP del visor, IDs únicos relevantes y `git diff --check`. No pudieron ejecutarse `test-R2.py`, fidelidad ni regresiones CDP por el aborto de Chrome.

## Diferencias permitidas
1. Datos reales y conteos reales.
2. Funciones ausentes en la maqueta, resueltas con sus mismos tokens/componentes.
3. Rail plegado aprobado, intacto como estado inicial.

`.git` es de solo lectura; cambios dejados en el árbol. Puertos 9511/9512 cerrados.
