HILO — H2 — 2026-10-04

✔ Causa raiz real, no del test: `x2SeguirNota` usaba scroll "smooth". Este Chrome headless falla el display link (CVDisplayLinkCreateWithCGDisplay), asi que el scroll suave a veces queda a medias al encadenar dos desplazamientos (usuario sube el scroll a mano y reselecciona la misma nota). Verificado con muestreo rAF en Chrome real: el segundo scroll quedaba parado 4 s. Fix de 1 linea: behavior "auto" (misma alineacion "nearest", sin animacion). Chokepoint unico: 15 llamadas pasan por ahi.

✔ test-hilo.py: 205/205, repetible (3 corridas limpias). Antes 174-175/205, fallos no deterministas en marcador/repetir-seleccion/clic-tarjeta/nota-respuesta-nueva — resueltos sin debilitar ningun check.

✔ Resto de suites, sin tocar datos reales: x2 17/17, i2 42/42 (copia de datos-reales), p6 96/96, e2e-invitado 143/143, inv (run-inv.sh) 57/57, guest 619/619. Nada roto.

✘ Entorno compartido muy cargado (load ~5, swap casi lleno, ~70 Chrome de otros agentes): mi Chrome murio varias veces a mitad de corrida antes de cada numero final; no es regresion, reintentado hasta pasar limpio.

✔ JS/Python/bash correctos; diff --check limpio. Commit 09ac458. Procesos propios parados con chrome.sh stop + kill de mis PIDs; 0 puertos residuales.
