# X2 · Portado de fases 1–3

✔ **Fase 1 · Decidir.** `decision=approved|adjust` opcional; numeración derivada `Nota N`/`AN`; UI «Agente»; aprobar cierra la nota vinculada; pedir ajuste la reabre y añade respuesta. El historial `multi` deshace cambio + nota (+ respuesta) como 1 acción. `visor.sh ajustes` y estados `[aprobado]`/`[AJUSTE]` probados contra API.

✔ **Fase 2 · Anotar.** Un trazo nuevo crea 1 borrador `tmp_` local: el servidor conservó 12 notas antes de Guardar y pasó a 13 después. El único POST guardó texto, 1 trazo, `end_frame=3` y JPEG compuesto de 124×224 (7,513 bytes; máximo 224 px). Las miniaturas se limitan a 1,280 px.

✔ **Fase 3 · Chat a escala.** Búsqueda, tipo, persona y dibujo; contador «N de M»; 3–4 entradas por página. A 1280×800, 1440×900 y 1600×1000: página, lista, panel y reproductor tuvieron `scrollWidth == clientWidth`; revisé visualmente las 3 capturas. Modo invitado real: 1 nota enviada, autor «Invitado · Ana QA», 1280×800 sin scroll.

**Pruebas:** `test-guest.py` 619/619; `run-attack.sh` 159/159 (1 hallazgo preexistente); sintaxis Python/Bash/JS y `git diff --check` ✔. Chrome conectado: aprobar/deshacer, ajuste/deshacer, búsqueda, filtros y borrador ✔; 0 errores de página (solo avisos de extensión). `tools/test-x2.py` queda reproducible.

## SUPUESTOS A CONFIRMAR

- Pedir ajuste reabre la nota original.
- El video permanece «Con el Agente» hasta aprobación explícita (fase 5).
- JPEG por cada nota con dibujo.
- Comparar v01·v02 no entra.

**NO verificado:** `test-inv.py`/CDP 9422: el Chrome headless instalado abortó al arrancar; la suite falló sin sus prerrequisitos. Sustituí esa cobertura por Chrome conectado, sin afirmar CDP. ✘ No pude crear commits: el sandbox denegó `.git/index.lock` porque `.git` está montado solo lectura.
