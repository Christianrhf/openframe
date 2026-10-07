HILO — 2026-10-04

✔ Lista continua con scroll propio; eliminados controles, estado, cálculo de tamaño y navegación por páginas. Búsqueda, filtros y contador N de M conservados. Orden idéntico a 84d68cc: vídeo, fotograma, ID. Respuestas anidadas y cambios del Agente incluidos.

✔ Crear/seleccionar sigue la tarjeta con scrollIntoView suave, nearest; selección con contorno de 2 px. El sondeo conserva selección y ancla visual. Se mide renderList incluyendo layout; por encima de 80 ms activa content-visibility:auto y contain-intrinsic-size. Mismo flujo para invitados. 1 script, 0 dependencias añadidas.

✔ Actualizadas X2, I2, P6, e2e-invitado y test-inv sin eliminar sus otras comprobaciones. test-hilo.py añade 32 aserciones distintas de UI, 160 notas, 2 modos y 3 tamaños: 1280×800, 1440×900, 1600×1000; puertos 9491/9493. Integrado en run-todo.sh.

✔ Ejecutado: test-guest 619/619; P5 33/34; P6 19/20; HILO 20/21. Total: 691 aprobadas; los 3 fallos son disponibilidad de Chrome. JavaScript, sintaxis Python, bash y git diff --check correctos.

✘ Chrome headless aborta: SIGABRT, código 134/-6, log vacío. NO verificados: tiempos reales, geometría, scroll, contorno y cero excepciones en navegador. No ejecutados run-todo completo ni suites exclusivamente visuales.

✘ Commit imposible: git add falla al crear .git/index.lock (Operation not permitted). Cambios conservados en el árbol de trabajo.

✔ Procesos propios terminados; 9 puertos comprobados cerrados. Logs: /tmp/o11/hilo-{suite,p5,p6,guest}.log.
