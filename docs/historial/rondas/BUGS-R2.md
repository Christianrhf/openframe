# BUGS · R2 · caza exploratoria en las uniones del porte fusionado

Metodología: leí `visor.html`/`server.py`/`guest.py` buscando costuras entre fases (tramo+mover, archivar+Comparar, sondeo+responder, POST vs PATCH) y confirmé cada sospecha con `curl`/CDP contra `server.py`:9481 + `guest.py`:9482 + Chrome:9483 reales (sin datos reales). Las 4 quedan automatizadas en `tools/bugs-r2.py` (una prueba por hallazgo, PASS/FAIL, sin aleatoriedad): **hoy da 0/4**, los 4 se reproducen. Solo lectura: no toqué ningún archivo de otro dueño.

## R2-1 · Tramo invertido (`end_frame ≤ frame`) deja el dibujo invisible para siempre — **ALTA**
**Pasos:** nota con tramo válido (`frame=10, end_frame=30`) y dibujo. Mover la nota a `frame=50` (arrastrar su marcador, o «Mover a otro momento»). `server.py` acepta el `PATCH {frame:50}` sin comparar con `end_frame` (`_patch_nota` ~1426; `add_note` ~772 tampoco). Queda `frame=50 > end_frame=30`.
**Debería:** rechazar el movimiento o ajustar `end_frame`. `guest.py` (746-747) **ya rechaza** `end_frame < frame` al crear — falta la misma regla en el camino de host.
**Medido:** `notaVisibleEnElFrameActual()` (~2845: `f>=ini && f<=fin`) nunca es cierto con `ini=50>fin=30`: por CDP, el dibujo no aparece en NINGÚN fotograma (0,10,20,30,50). El trazo sigue en el JSON pero es inalcanzable para siempre, sin aviso.
**Prueba:** `tools/bugs-r2.py::r2_1_tramo_invertido`.

## R2-2 · `POST /notas` acepta fotograma fuera del video; `PATCH` de la misma nota no — **ALTA**
**Pasos:** `POST ... {frame:999999}` sobre un clip de 6 s (~129 fotogramas reales) → `201`, guarda `frame:999999`. `PATCH` de esa misma nota con el mismo valor → `400`: `_patch_nota` limita contra la duración real (~1433) pero `add_note` solo limita contra un techo arbitrario de 10 000 000 (línea 779), nunca contra la duración.
**Debería:** la misma regla en ambos caminos.
**Efecto:** nota fantasma clavada al 100 % de la barra, inalcanzable al reproducir, y ya no se puede corregir por `PATCH` (que sí exige rango real) — solo borrarla.
**Prueba:** `tools/bugs-r2.py::r2_2_frame_fuera_de_rango`.

## R2-3 · «Comparar» queda encendido tras archivar el único proyecto abierto — **MEDIA**
**Pasos:** un solo proyecto activo, abrirlo, entrar en Comparar, archivarlo. `archivarProyecto()` (~1836) solo llama `openProject(otro.slug)` —que sí hace `cmpSalir(false)`— **si existe otro proyecto**; sin ninguno, cae al `else` (`renderProyectos(); toast(...)`) sin pasar por `cmpSalir`.
**Medido:** tras archivar, `st.slug`/`st.vid` quedan `null`, pero `CMP.on` sigue `true`, `#screen` conserva `cmp-on cmp-side` y `#v2` sigue con `src` del proyecto ya archivado.
**Prueba:** `tools/bugs-r2.py::r2_3_comparar_tras_archivar`.

## R2-4 · Responder a un hilo cuya raíz se borra mientras se escribe: la respuesta se envía SIN AVISO como nota suelta — **MEDIA**
**Pasos:** abrir «Responder» en una nota raíz, escribir texto sin enviar. Mientras tanto (p. ej. Agente por `visor.sh borrar`) se borra la raíz. En el siguiente sondeo, `updateEditor()` (~4196) detecta la raíz muerta y limpia `st.replyTo`/`editingId` —correcto— pero no toca el texto ya escrito ni avisa. Si el usuario pulsa Enviar sin fijarse, `saveNote()` ve `replyTo===null` y crea una nota suelta en el fotograma actual con ese texto.
**Medido:** por CDP, `replyTo` pasa a `null` tras el sondeo, el `textarea` conserva el texto, y al guardar se crea una nota con `parent:null` — el usuario cree que respondió a un hilo y creó algo distinto, sin ningún aviso.
**Prueba:** `tools/bugs-r2.py::r2_4_respuesta_huerfana`.

## No verificado
Ventanas <1180 px y zoom 150 % (solo CSS, no medido con CDP); sesión de invitado real contra estos 4 (todos son rutas `if(esInvitado) return`, no debería ser alcanzable, pero no abrí un enlace real para confirmarlo); proyectos con 200 notas (ya cubierto por P4); `visor.sh subir`/heredar con `revision` largo (leído, consistente, no ejecutado contra historial real).
