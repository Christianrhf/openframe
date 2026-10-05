# Fuente del visor (réplica literal de la maqueta) — pruebas y herramientas

Copia de trabajo completa del visor desplegado en `~/visornotas` (mismo `visor.html`, `server.py`, `guest.py`, `visor.sh`),
más lo que NO se despliega: `tools/` (pruebas CDP, fidelidad contra la maqueta, `run-todo.sh`), `ref/maqueta/` (maqueta aprobada), `docs/`.

## Correr todo
1. Entorno de pruebas (vive en /tmp, se pierde al reiniciar): `python3 -m venv /tmp/o8/venv && /tmp/o8/venv/bin/pip install websocket-client`
2. `cd` aquí y `bash tools/run-todo.sh` → resumen en `/tmp/o8/todo-resumen.txt` (14 suites, ~7 min; usa Chrome en puertos 9300-9500, uno a la vez).
3. Fidelidad contra la maqueta: `tools/fidelidad.py` + `tools/fidelidad-map.json` (excepciones documentadas, todas por decisión del usuario).

## Desplegar
Verificar PRIMERO (run-todo + fidelidad en verde) y desplegar DESPUÉS, en otro paso:
`cp ~/visornotas/visor.html ~/visornotas/visor.html.bak-$(date +%s) && cp visor.html ~/visornotas/visor.html && cmp visor.html ~/visornotas/visor.html`
