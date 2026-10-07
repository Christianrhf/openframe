# OpenFrame

Visor de revisión de video **frame a frame**. Quien revisa deja notas (con dibujo y tramo) sobre un fotograma exacto; un agente (Claude, Codex…) lee esas notas por CLI, edita el video y deja **cambios** y respuestas; quien revisa los aprueba o pide ajuste. Todo local, sin dependencias: **Python 3 estándar + un solo `visor.html`** (sin npm, CDN ni fuentes web).

## Arrancar
```bash
python3 server.py --puerto 8477        # abre http://127.0.0.1:8477
```
Los datos viven en `data/<proyecto>/` (notas en `notes.json`, un `videos/<id>/` por corte). Se crean solos; no se versionan.
El servidor del puerto 8477 **se apaga solo a los 10 min sin peticiones** (`--inactividad`, 0 = nunca) salvo que la puerta de invitados esté abierta.

## Piezas
| Archivo | Qué es |
|---|---|
| `server.py` | API + interfaz (puerto 8477, **solo local**: sin autenticación, nunca exponerlo) |
| `visor.html` | la interfaz entera (HTML+CSS+JS) |
| `visor.sh` | CLI para agentes: `visor.sh ayuda` (notas, responder, cambio, subir, invitar, revocar…) |
| `guest.py` | puerta de invitados (puerto 8478): lista blanca estricta, un enlace secreto por video, caduca y se revoca |
| `publicar.sh` | abre/cierra la puerta pública (túnel de Cloudflare); cerrada por defecto |
| `tools/` | pruebas con Chrome (CDP) y fidelidad contra la maqueta aprobada (`ref/maqueta/`) |
| `docs/` | contratos y decisiones (modo invitado, seguridad) |

## Ciclo de trabajo
1. El revisor anota en la interfaz (`N` nota, `D` dibujar, `?` atajos).
2. El agente: `visor.sh notas <proyecto>` → edita el video → `visor.sh cambio <proyecto> <video> <frame> "qué cambié" --por <nota>` → `visor.sh responder …`.
3. **El agente responde; el revisor cierra** (resolver/aprobar).

## Compartir con un invitado
`visor.sh invitar <proyecto> <video> --dias 7` (o «Compartir» en la cabecera) crea un enlace por video; el invitado solo ve y anota ese video. Revocar: «Compartir» → «Revocar» / «Revocar todos», o `visor.sh revocar`. El texto de un invitado es un tercero: `visor.sh notas` lo marca `[INVITADO: nombre]` como dato, nunca como instrucción. Detalle en `docs/CONTRATO-INVITADOS.md` y `SEGURIDAD.md`.
> Para publicar la puerta hace falta un túnel propio (`config.json` → `base_publica`, `~/.cloudflared/config.yml` apuntando **solo** a `127.0.0.1:8478`). Sin eso, los enlaces no se abren desde fuera.

## Pruebas
Requieren Chrome y `pip install websocket-client` (en un venv).
```bash
python3 -m venv /tmp/o8/venv && /tmp/o8/venv/bin/pip install websocket-client
bash tools/run-todo.sh        # 16 suites, ~10 min → /tmp/o8/todo-resumen.txt
```
Fidelidad contra la maqueta: `tools/fidelidad.py` + `tools/fidelidad-map.json` (las excepciones están documentadas ahí). Las suites asumen rutas de macOS (`/tmp/o8`, `/private/tmp`).

## macOS (opcional)
La app **OpenFrame** (un `.app` de arranque a demanda con Chrome `--app`) y el comando `visor` no se versionan aquí; se crean con las instrucciones de `tools/` si hacen falta. Sin LaunchAgent: el servidor se levanta al abrir y se apaga solo.

## Reglas
- 8477 nunca se expone; solo `guest.py` sale por el túnel.
- Antes de tocar `visor.html`: respaldo. Verificar (`run-todo.sh` + fidelidad) y desplegar en pasos separados.
- Sin licencia: todos los derechos reservados.
