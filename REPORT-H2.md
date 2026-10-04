HILO — H2 — 2026-10-04

✔ Causa raiz real, no del test: `x2SeguirNota` usaba `scrollIntoView({behavior:"smooth"})`. Este Chrome headless falla el display link (`CVDisplayLinkCreateWithCGDisplay`), asi que el scroll suave a veces no avanza o queda a medias si se encadenan dos desplazamientos (usuario sube el scroll a mano y reselecciona la misma nota). Verificado con muestreo rAF en Chrome real: el segundo `scrollIntoView` quedaba parado 4 s. Fix de 1 linea: `behavior:"auto"` (misma alineacion "nearest", sin animacion). Chokepoint unico: 15 llamadas (marcador, clic, atajo, saveNote, saveReply, sondeo) pasan por ahi.

✔ test-hilo.py: 205/205, repetible (3 corridas limpias). Antes 174-175/205, fallos no deterministas en "marcador deja nota visible", "repetir seleccion", "clic en tarjeta", "nota/respuesta nueva dentro de caja" — resueltos sin debilitar ningun check.

✔ Resto de suites, una a la vez, sin tocar datos reales: x2 17/17, i2 42/42 (copia de /tmp/o10/datos-reales), p6 96/96, e2e-invitado 143/143, inv (run-inv.sh) 57/57, guest 619/619. Nada roto.

✘ Entorno compartido muy cargado (load ~5, swap casi lleno, ~70 Chrome de otros agentes): mi Chrome murio varias veces a mitad de corrida antes de cada numero final; no es regresion del fix, reintentado hasta pasar limpio.

✔ JS, Python y bash correctos; `git diff --check` limpio. Commit 09ac458. Procesos propios parados con `tools/chrome.sh stop` + kill de mis PIDs; 0 puertos residuales.
