# TAREA H · Dos defectos de integración (A+B+G) en la maqueta fusionada   (puerto 9358 · modelo Sonnet)

Cambios mínimos y localizados (otro agente, E, toca contraste/tamaños/atajos en paralelo: NO reformatees ni toques valores de color/tamaño de letra/atajos).

## H1 · El marcador seleccionado tapa a su grupo (visto en captura)
Reproducir: 6 notas en los fotogramas 100,104,108,112,116,120 (`seek(f/24)` + `noteInput.value` + `noteForm.requestSubmit()`), seleccionar la del 120 (la última). El marcador seleccionado (suelto, encima) cae SOBRE el grupo de 5 y lo oculta: no se ve ni se puede pulsar el grupo. Es la regla de B «el seleccionado nunca se agrupa».
- Nueva regla: **si el marcador seleccionado quedaría solapado con un grupo (o con otro marcador suelto), el seleccionado se absorbe en ese grupo** y el grupo recibe la clase `.has-sel` (UN solo trazo de 2 px, el mismo idioma que la selección de marcadores sueltos) y su vista previa lista al seleccionado primero con un indicador. Si el seleccionado NO solapa con nada, sigue suelto como hoy. Debe haber **0 pares solapados incluyendo al seleccionado**, a zoom 1/2/4/8, con el caso anterior y con 40 notas con PRNG de semilla (como `tools/test-b.py`; reutiliza su patrón).
- Además `liveSelId()` (B) no entiende los tramos de A: una nota con tramo seleccionada en un fotograma interior a su tramo (p. ej. n2 en el 650) puede agruparse mientras «está en pantalla». Haz que `liveSelId()` use la misma lógica que `syncSel()` (exacto > nota ya seleccionada con `aInRange` > primera con `aInRange`) SIN llamar a `syncSel()` (que corre después y mutaría estado).
- Pruebas nuevas en `tools/test-h.py` (≥ 10 checks): el caso medido, el caso del tramo, clic en el grupo con `.has-sel`, y que el marcador seleccionado dentro de un grupo se ve en la lista de la vista previa. Capturas revisadas con Read (antes/después).

## H2 · Check dudoso de G: «cambiar de herramienta a mitad de trazo»
`tools/stress.py` falla este check tras el arreglo ya aplicado (al pulsar otra herramienta con el puntero abajo, el trazo en curso se confirma con SU herramienta antes de cambiar; ver el `.tool` onclick y `layer.onpointerup`). Decide con evidencia (ejecútalo, mira el DOM resultante y una captura) si: (a) el comportamiento actual es el correcto (el trazo ya dibujado conserva su forma; la siguiente herramienta aplica al siguiente trazo; sin excepciones, sin trazo duplicado ni historial incoherente) y el CHECK está mal redactado → corrígelo en `stress.py` explicando por qué en el propio check; o (b) hay un bug real → arréglalo. Cuéntalo en REPORT.md.

## Criterios
`build.py` en verde; `regress.py` (59), `test-a`, `test-b`, `test-c`, `test-d`, `test-h` y `stress.py` (menos los 6 fallos de contraste que arregla E) en verde. Commit + `REPORT.md` (≤ 250 palabras, números).
