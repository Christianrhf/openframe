# REPORT · I2 · el porte (fases 1–3) reconciliado con el modo invitado

## Suites (primer plano, una a una, puertos propios)
- ✔ `e2e-invitado.py` (9431/9432, Chrome 9433): 116/120 → **142/142** (+22)
- ✔ `test-inv.py` (`run-inv.sh`, 9434–9436): 50/54 → **55/55**
- ✔ `test-x2.py` (9421): no corría, faltaba `prueba-x2` (`setup-x2.py`) → **11/11**
- ✔ `test-i2.py` (9431), nueva: **38/38**
- ✔ `test-guest.py` **619** · `run-attack.sh` **159/159** (hallazgo *medium* preexistente)

## Diagnóstico con medidas (`tools/probe-i2.py`)
**Dibujo (2 checks):** no era fallo; la fase 2 lo hizo borrador `tmp_` + UN POST al Guardar. Medido: 0 POST al dibujar; 1 POST de 11 193 B, `thumb` 10 543 B, `enlace_id`, `author=invitado`, 11 puntos, `<id>.jpg` en disco. Los checks suponían el flujo viejo: reescritos sobre el real, +4.

**Latencia (2 checks):** la nota entraba en `st.notas` por el sondeo pero no en el DOM: la lista pagina y, ordenada por fotograma, caía en la última. Medido: 10 notas, «Página 1 de 3», nota en la 3. Ahora la lista salta a lo que llega y avisa: **1,15 s** hasta verse con insignia.

## Huecos cerrados (cada uno con check nuevo)
- `#bSave` quedaba apagado tras enviar una nota: el dibujo del invitado **no tenía salida**.
- `Ctrl+Z` del invitado era código muerto y `redo()` inalcanzable. Arreglados; `undo/redo/pushHist/saveDrawing` ya no escriben sobre nota ajena ni sobre otra distinta de la dibujada.
- 0 botones de decisión; `x2Aprobar/x2PedirAjuste/x2Reconsiderar` inertes desde consola; con `ve_otras=false` ningún filtro de persona filtra notas ajenas; con `ve_otras=true` ve el cambio de Agente pero no lo decide.
- Con datos reales la lista desbordaba (650 px en 638, v03): el tamaño de página se **mide**.

## Compatibilidad `/tmp/o10/datos-reales`
4/4 proyectos, **0 excepciones** (los 404 de `media.*` son por la copia sin vídeos). Raíces pintadas = `notes.json` del vídeo abierto: 30/30, 48/48, 32/32, 1/1 → **111/111**, sin duplicados ni scroll. 154 notas sin `drawing`/`thumb` ✔.

## NO verificado
Miré 2 capturas con Read; el resto por `getBoundingClientRect`/`scrollHeight`. No toqué `guest.py` (el contrato no lo pedía). El `Ctrl+Z` de **Cristian** sigue yendo a la pila de acciones: su camino al historial de dibujo sigue muerto, no lo cambié. El tamaño de página solo encoge dentro de una vista: puede quedar conservador. Sin vídeos reales (la copia no los trae).
