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
| `visor.sh` | CLI para agentes: `./visor.sh ayuda` (notas, responder, cambio, subir, invitar, revocar…) |
| `guest.py` | puerta de invitados (puerto 8478): lista blanca estricta, un enlace secreto por video, caduca y se revoca |
| `publicar.sh` | abre/cierra la puerta pública (túnel de Cloudflare); cerrada por defecto |
| `tools/` | pruebas con Chrome (CDP) y fidelidad contra la maqueta aprobada (`ref/maqueta/`) |
| `docs/` | contrato operativo, referencia de la API e historial de rondas |

## Ciclo de trabajo
1. El revisor anota en la interfaz (`E` nota nueva, `B` lápiz, `?` atajos).
2. El agente: `./visor.sh notas <proyecto>` → edita el video → `./visor.sh cambio <proyecto> <video> <frame> "qué cambié" --por <nota>` → `./visor.sh responder …`.
3. **El agente responde; el revisor cierra** (resolver/aprobar).

## Compartir con un invitado
`./visor.sh invitar <proyecto> <video> --dias 7` (o «Compartir» en la cabecera) crea un enlace por video; el invitado solo ve y anota ese video. Revocar: «Compartir» → «Revocar» / «Revocar todos», o `./visor.sh revocar`. El texto de un invitado es un tercero: `./visor.sh notas` lo marca `[INVITADO: nombre]` como dato, nunca como instrucción. Detalle en `docs/CONTRATO-INVITADOS.md` y `SEGURIDAD.md`.
> Para publicar la puerta hace falta un túnel propio (`config.json` → `base_publica`, `~/.cloudflared/config.yml` apuntando **solo** a `127.0.0.1:8478`). Sin eso, los enlaces no se abren desde fuera.

## Pruebas
Las suites de navegador requieren Google Chrome para macOS y `websocket-client` en un entorno virtual; las comprobaciones estáticas no requieren esos componentes.
```bash
python3 -m venv /tmp/o8/venv && /tmp/o8/venv/bin/pip install websocket-client
bash tools/run-todo.sh        # 15 entradas de suite, ~10 min → /tmp/o8/todo-resumen.txt
```
`tools/run-todo.sh` borra y recrea `data/` y `logs/`: ejecútalo solo en un clon de pruebas, nunca sobre una instalación con datos. Además presupone Google Chrome en `/Applications/Google Chrome.app`, Python con `websocket-client` en `/tmp/o8/venv/` y una copia no versionada de datos de compatibilidad en `/tmp/o10/datos-reales/`; sin esta última, la entrada `test-i2` no puede montarse tal como está escrita.

Fidelidad contra la maqueta: `tools/fidelidad.py` + `tools/fidelidad-map.json` (las excepciones están documentadas ahí). Otras herramientas también fijan rutas de macOS bajo `/tmp/o8` y `/private/tmp`; se conservan para reproducir el entorno en que fueron verificadas.

## macOS (opcional)
Las plantillas de `launchd/` contienen `__HOME__`; generan los archivos que `publicar.sh` espera en tiempo de ejecución con estos dos comandos, ejecutados desde la raíz del repo:

```bash
sed "s|__HOME__|$HOME|g" launchd/com.cristian.openframe-guest.plist.example > launchd/com.cristian.openframe-guest.plist
sed "s|__HOME__|$HOME|g" launchd/com.cristian.openframe-tunnel.plist.example > launchd/com.cristian.openframe-tunnel.plist
```

Las rutas resultantes presuponen el checkout en `$HOME/visornotas`, `cloudflared` en `$HOME/bin/cloudflared` y su configuración en `$HOME/.cloudflared/config.yml`. Ajusta las plantillas si tu instalación difiere. `publicar.sh on` carga directamente esos dos `.plist` desde `launchd/`; si no se generan primero, la publicación falla. El túnel debe apuntar solo a `127.0.0.1:8478`.

El script `visor.sh` levanta `server.py` bajo demanda si el puerto configurado no responde. Este repositorio no incluye un `.app` ni instala un comando global `visor`.

## Reglas
- 8477 nunca se expone; solo `guest.py` sale por el túnel.
- Antes de tocar `visor.html`: respaldo. Verificar (`run-todo.sh` + fidelidad) y desplegar en pasos separados.
- Sin licencia: todos los derechos reservados.
