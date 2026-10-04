HILO — H2 — 2026-10-04

✔ Causa raiz real (no del test): `x2SeguirNota` usaba `scrollIntoView({behavior:"smooth"})`. En este Chrome headless el display link falla (`CVDisplayLinkCreateWithCGDisplay failed`), asi que el scroll suave a veces no avanza o se queda a medias si se encadenan dos desplazamientos (p. ej. el usuario sube el scroll a mano y vuelve a seleccionar la misma nota). Verificado con muestreo rAF en Chrome real, no solo inferido del test: el segundo `scrollIntoView` quedaba parado en el mismo punto 4 s seguidos. Fix de 1 linea: `behavior:"auto"` (misma alineacion "nearest", sin animacion). Chokepoint unico: 15 llamadas (marcador, clic, atajo, saveNote, saveReply, sondeo) pasan por esa funcion.

✔ test-hilo.py: 205/205, repetible (verificado 3 veces limpias). Antes 174-175/205 con fallos no deterministas en "marcador deja nota visible", "repetir seleccion", "clic en tarjeta", "nota/respuesta nueva dentro de caja" — todos resueltos, mismo check, sin debilitarlo.

✔ Resto de suites, una a la vez, sin tocar datos reales: test-x2 17/17, test-i2 42/42 (contra copia de /tmp/o10/datos-reales), test-p6 96/96, e2e-invitado 143/143, test-inv (run-inv.sh) 57/57, test-guest 619/619. Nada roto por el cambio del hilo.

✘ Entorno compartido muy cargado (load avg ~5, swap casi lleno, ~70 procesos Chrome de otros agentes): mi propio Chrome headless murio varias veces a mitad de corrida (connection reset/refused) en intentos previos a cada numero final de arriba; no es una regresion del fix — reintentado hasta pasar limpio, con mediciones de memoria libre antes de cada reintento.

✔ JavaScript, Python (tools + server.py + guest.py), bash (run-inv.sh) y `git diff --check` correctos. Commit hecho (09ac458). Procesos propios: todos los Chrome y servidores que arranque los pare yo mismo (`tools/chrome.sh stop <puerto>` + kill de PIDs propios); 0 puertos residuales comprobados.
