# REPORT · P6 — atajos, accesibilidad, pasada final

`run-todo.sh` **todo verde**: x2/i2/p4/p5/p7/**p6**/guest/ataque/e2e/inv = 11/38/27/61/45/**90**/619/159/142/55 ✔ · `audit-a11y.py` **0 fallos** ✔

**Atajos** nuevos: **I O J K L**, **Ctrl/Cmd+Entrar**, **?**. Choque → gana el existente (`N`/`n`, `[`/`]`, `C`); «nota nueva» sigue en **E**. `I`=entrada del tramo; `O`=el botón «fin» (invitado: `st.invTramo` en el POST, **`guest.py` sin tocar**). Escribiendo no dispara ninguno; enfocar el cuadro **pausa** el vídeo. ✔
**Chuleta** `#keysPop`: `role=dialog`, `aria-modal`, foco atrapado, Esc cierra y devuelve el foco, sin scroll. 22 filas = 22 atajos; invitado 21. Icono `keyboard` de `__iconNode`.

**Accesibilidad** (antes→después): contraste < AA **153→0** ✔ · letra < 11 px **282→0** ✔ · agarre < 28 px **258→0** ✔ · sin nombre **141→0** ✔. Por valores: `--fg-mute` #8a8a8a→**#6b6b6b**, 30 `font-size` a 11 px (glifo del grupo, 9), alturas 28 px, 2 `::before` de agarre (iconos intactos). `:focus-visible` de 2 px, un solo trazo; `prefers-reduced-motion` medido con `setEmulatedMedia`; `aria-live`/`aria-pressed`/`aria-expanded`; nombres del `data-tip` existente.

**Calidad** (3 tamaños × 6 estados, capturas vistas con Read): 0 scroll, 0 scroll oculto, 0 desbordes, 0 recortes, 0 excepciones. Arreglado: el transporte partía un par (`«`/`»`) → `.tp-grupo`; la cabecera de Notas partía el contador; nombre de vídeo cortado a seco → elipsis; el círculo anunciaba un atajo `C` inexistente. Datos reales (4 proyectos, 155/100/82/1 notas): **0 excepciones**.

**`visor.sh ayuda`** (alias nuevo): 20 comandos, 25 ejemplos (`estado … <nuevo>`, `notas … enviadas`, `ajustes`). ✔

**No verificado**
- ✘ `.vfilter` (`max-width:118px`) corta «Todos los vídeos». Propuesta: ancho fluido y `min-width:0` en `.x2checks`.
- Chat a 2 tarjetas/página a 1280 con notas largas: tamaño **medido** de X2/I2.
- Contraste contra el fondo compuesto de ancestros.
- Tabulación deducida del DOM (0 `tabindex` positivos).
- Sin lector de pantalla, `forced-colors`, pantalla completa ni tema oscuro. Datos reales sin vídeo (404 esperados).
