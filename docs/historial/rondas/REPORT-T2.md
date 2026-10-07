# REPORT T2 · línea de tiempo + ANOTAR

## Resultado

- `visor.html`: transporte de 40 px; rejilla literal de regla + dos carriles; cabezal sobre la regla; marcadores de nota/cambio, selección, tramo y dock ANOTAR con valores de `ref/maqueta/src/app.css`.
- Las respuestas ya no generan marcadores ni inflan el total de Notas.
- `loadedmetadata` pinta la regla; sus siete lecturas usan el formato corto de la maqueta.
- `tools/fidelidad-map.json`: 32 pares nuevos en `linea-de-tiempo` y 24 en `anotar` (56 total). Auditoría viva: 56/56 selectores reales resuelven.
- `tools/setup-x2.py`: la segunda nota incluye tramo para cubrir esa geometría.
- `tools/test-p4.py`: API configurable; añade 1920×1080 y prueba recorte de controles.

## Verificación

- `tools/test-p4.py`: **32/32**; 0 solapes con 5/60 marcadores, 40 semillas × 4 zooms; 0 excepciones.
- 1280×800, 1440×900, 1600×1000 y 1920×1080: sin scroll de página y sin controles recortados.
- JSON válido; JS y Python compilan; `git diff --check` limpio.
- Revisadas con herramienta de imagen: `shots/p4-*.png` y `shots/t2-real-{1440x900,1600x1000}.png`.

## Diferencias permitidas

- Chip real `medir` visible.
- Lectura real `todo el video` visible sobre 1700 px y oculta por debajo para conservar la fila literal de 40 px.
- `#rlLbl` permanece oculto.

## No verificado

Chrome 9572 abortó tres veces. No afirmo `fidelidad.py` 100 % ni capturas lado a lado: la sesión Chrome alternativa bloqueó `file://` de la maqueta. El commit tampoco fue posible: `.git/index.lock` es de solo lectura. Servidor 9571 y puerto 9572 cerrados; el Chrome gestionado por la herramienta en 9271 siguió escuchando tras cerrar sus pestañas (`kill` denegado por el sandbox).
