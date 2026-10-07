# API HTTP de OpenFrame

Referencia obtenida de los manejadores y regex de `server.py` y `guest.py`. Los nombres entre llaves son segmentos variables. No es una especificación para exponer `server.py` a internet.

## API local (`server.py`, puerto 8477)

Solo debe escuchar en loopback. Rechaza peticiones cuyo origen de red o `Host` no sea local; `guest.py` accede mediante el secreto interno `X-Guest-Gate`.

| Método | Ruta | Función |
|---|---|---|
| GET | `/` o `/index.html` | Sirve `visor.html` e inyecta el identificador de build. |
| GET | `/api/ping` | Salud, revisión y tiempo activo. |
| GET | `/api/proyectos` | Lista proyectos activos y archivados. |
| POST | `/api/proyectos` | Crea proyecto con `nombre`, `cliente` y `nota`. |
| GET | `/api/proyectos/{slug}` | Devuelve proyecto, videos y notas decoradas. |
| POST | `/api/proyectos/{slug}/archivar` | Archiva o recupera el proyecto. |
| GET | `/api/proyectos/{slug}/hilos` | Lista hilos; acepta `video` y `todas` en la query. |
| GET | `/api/notas/{slug}` | Lista las notas del proyecto. |
| POST | `/api/proyectos/{slug}/notas` | Crea nota, respuesta o cambio. |
| PATCH | `/api/proyectos/{slug}/notas/{id}` | Modifica una nota. |
| PATCH | `/api/notas/{slug}/{id}` | Alias de modificación usado por la CLI y la puerta. |
| DELETE | `/api/proyectos/{slug}/notas/{id}` | Borra nota; si es raíz, borra también sus respuestas. |
| DELETE | `/api/notas/{slug}/{id}` | Alias de borrado usado por la CLI. |
| POST | `/api/proyectos/{slug}/videos` | Sube video binario; nombre en `X-Filename`. |
| PATCH | `/api/proyectos/{slug}/videos/{video}` | Cambia `estado`: `revision`, `con_agente` o `aprobado`. |
| POST | `/api/proyectos/{slug}/videos/{video}/meta` | Actualiza duración, fps, ancho y alto medidos. |
| POST | `/api/proyectos/{slug}/heredar` | Hereda hilos entre dos videos. |
| GET | `/media/{slug}/{video}/{archivo}` | Sirve el video declarado o `proxy-720.mp4`, con Range. |
| GET | `/thumbs/{slug}/{nota}.jpg` | Sirve la miniatura de una nota. |
| GET | `/api/invitados/estado` | Estado de publicación y cantidad de enlaces activos. |
| GET | `/api/invitados/activos` | Lista enlaces vivos de todos los proyectos. |
| GET | `/api/invitados/actividad?desde={iso}` | Actividad de invitados desde una fecha ISO. |
| GET | `/api/proyectos/{slug}/videos/{video}/invitar` | Lista enlaces del video. |
| POST | `/api/proyectos/{slug}/videos/{video}/invitar` | Crea enlace y solicita abrir la puerta. |
| DELETE | `/api/proyectos/{slug}/videos/{video}/invitar/{id}` | Revoca enlace; cierra la puerta si no queda ninguno activo. |

## Lista blanca pública (`guest.py`, puerto 8478)

Salvo `/api/ping` y el canje inicial `/r/{token}`, las rutas requieren una sesión de invitado válida. `{slug}` y `{video}` deben coincidir exactamente con el enlace. Las rutas no listadas y los métodos `DELETE`, `PUT`, `OPTIONS`, `TRACE` y `CONNECT` responden 404.

| Método | Ruta | Función y restricciones |
|---|---|---|
| GET | `/api/ping` | Salud sin autenticación; lo usa `publicar.sh`. |
| GET | `/r/{token}` | Valida el token, registra uso, crea cookie `ofg` y redirige a `/`. |
| GET | `/` | Sirve el visor inyectando solo el proyecto/video autorizado. |
| GET | `/api/proyectos/{slug}` | Devuelve un solo video, sin estado de revisión, y notas visibles. |
| GET | `/api/notas/{slug}` | Devuelve las notas visibles según `ve_otras`. |
| GET | `/media/{slug}/{video}/{archivo}` | Sirve solo el video enlazado; admite Range. |
| HEAD | `/media/{slug}/{video}/{archivo}` | Igual que GET, sin cuerpo. |
| GET | `/thumbs/{slug}/{nota}.jpg` | Sirve solo miniaturas de notas visibles. |
| POST | `/api/invitado/nombre` | Guarda el nombre firmado en cookie `ofn`. |
| POST | `/api/proyectos/{slug}/notas` | Crea nota/respuesta forzando video, autor e identidad del enlace. |
| PATCH | `/api/notas/{slug}/{id}` | Edita solo `text` o `drawing` de una nota del mismo enlace. |

Las escrituras comprueban mismo origen cuando `Origin` o `Referer` están presentes, límites de cuerpo y tasa, nombre válido y propiedad de la nota.
