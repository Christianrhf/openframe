# SEGURIDAD · auditoría de caja blanca de la puerta de invitados

Agente R. Solo lectura de código (`guest.py`, partes de `server.py` que tocan
invitados, `publicar.sh`, `launchd/*.plist`). Entorno propio en 9393/9394,
`OPENFRAME_NO_PUBLICAR=1`. Prueba reproducible de cada hallazgo en
`tools/attack-wb.py` (arranca sus propios `server.py`/`guest.py`); hoy: **4
FAIL / 4 PASS**.

## Hallazgos reales

**R1 · ALTA · `guest.py:723-729`, `server.py:738,1230`** — `frame`/`end_frame`
no tienen tope superior en `guest.py` (solo se exige `int >= 0`). Un invitado
autenticado puede mandar `{"frame": 10**400}` en `POST
/api/proyectos/<slug>/notas`. `server.py` hace `frame / eff_fps` sin blindar
(`add_note`, línea 738) → `OverflowError: int too large to convert to float`,
sin capturar por nada más fino que el `except Exception` que envuelve
`do_POST` (línea 1230), que devuelve `{"error": "OverflowError: ..."}` con
**500**. `guest.py._upstream`+`_json` (líneas 748-752) reenvía ese cuerpo y
ese código **tal cual** al invitado: cualquiera con un enlace válido arranca
una excepción interna de Python y la lee en su navegador. Probado contra el
invitado real (`gate.json POST .../notas`) y contra `server.py` directo
(misma causa). Arreglo: acotar `frame`/`end_frame` en `guest.py` (p. ej.
`0 <= frame < 2**31`) y que `server.py` nunca devuelva `str(exc)` al
cliente — loguear el detalle y responder `{"error": "interno"}`.

**R2 · MEDIA · `server.py:1244-1323` (`_patch_nota`), `1344-1362`
(`_delete_nota`)** — Ningún `PATCH`/`DELETE` de notas exige `X-Guest-Gate` ni
revalida al dueño del `enlace_id`. La única barrera hoy es el filtrado que
hace `guest.py` **antes** de reenviar (solo `text`/`drawing`, solo si
`note.enlace_id == su enlace`); 8477 en sí confía ciegamente en el llamador.
Probado: un PATCH directo a la API local con `{"resolved": true, "visto":
true}` sobre una nota de invitado se aplica sin cabecera; un DELETE directo
la borra. Con 8477 solo en loopback y sin publicar, hoy no es explotable
desde internet — pero sin este backstop, un bug futuro en `guest.py` (o una
exposición accidental de 8477) sería crítico en vez de contenido. Arreglo:
si la nota tiene `enlace_id`, exigir `X-Guest-Gate` y limitar campos
también en `server.py` (no confiar solo en el cliente).

## Revisado, no reproducido

- **`$` y `\n` final** en los `re.match(...$...)` de `server.py` (p. ej.
  línea 1164): no explotable, `self.path`/`requestline` son una sola línea
  HTTP y no pueden contener un `\n` literal.
- **Timing token inexistente vs. revocado** (`guest.py` `by_token:164`): el
  bucle recorre todos los enlaces sin cortar antes en ningún caso; coste
  ~igual para ambos casos.
- **SSRF / inyección hacia 8477** (`_upstream:467`): host fijo y validado en
  `main()`; cabeceras con valores propios; rutas siempre por
  `quote(..., safe="")`.
- **Escape de `/media`/`/thumbs`** (symlinks, `..`, `%2f`): `realpath` +
  `startswith(dir+os.sep)`; regex de nombre no admite `%` ni `/`.
- **Cookies `ofg`/`ofn`**: atributos correctos, `ofn` firmado con
  HMAC-SHA256 atado al `enlace_id`, comparación con `compare_digest`.
- **`.gitignore`/`launchd`**: `data/` (`.guest_secret`, `invitados.json`)
  fuera del repo. `~/.cloudflared/config.yml` real está fuera de este clon
  — **no verificado**, no se tocó.

## Opinión (sin PASS/FAIL propio)

`RateLimiter.events` nunca purga enlaces caducados (fuga de memoria lenta,
bajo riesgo). `STORE.refresh()` escanea todo `data/` en cada request.

Commit incluido: `tools/attack-wb.py`.
