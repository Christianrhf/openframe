#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrar-fps.py — repara las notas cuyo fps guardado no es un fps de video.

El fps es propiedad del VIDEO. Algunas notas viejas se guardaron con el fps que
el navegador "midio" mal (en los datos reales: 8.0 y 3.43 en un clip de 23.976),
y por eso parecen moverse cuando se abre el proyecto.

La reparacion conserva el MOMENTO, no el numero de fotograma:

    t          = frame_viejo / fps_viejo        (el instante que vio la persona)
    frame_nuevo = round(t * fps_del_video)
    fps_nuevo   = fps_del_video

Por defecto NO escribe nada (dry-run). Es idempotente: correrlo dos veces no
cambia nada la segunda vez. Nunca borra notas ni campos.

  python3 migrar-fps.py                      # dry-run, todos los proyectos
  python3 migrar-fps.py v01-hoover-dam       # dry-run, un proyecto
  python3 migrar-fps.py --aplicar            # escribe (hace copia .bak-<ts>)
  python3 migrar-fps.py --todas              # tambien realinea fps validos != video
"""
import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server as S                                      # noqa: E402

TOL_TIEMPO = 0.6        # s: media ventana de un fotograma a 3.43 fps es 0.146 s


def proyectos(args):
    if args.slug:
        return list(args.slug)
    if not os.path.isdir(S.DATA):
        return []
    return [d for d in sorted(os.listdir(S.DATA)) if os.path.isdir(S.pdir(d))]


def revisar(slug, realign):
    """Devuelve (notas, cambios). cambios = [(nota, campos_nuevos, t_antes, t_despues)]."""
    notas = S.load_notes(slug)
    cambios = []
    for n in notas:
        vfps = S.video_fps(slug, n.get("video", ""))
        plan = S.plan_note_fps(n, vfps, realign_mismatch=realign)
        if not plan:
            continue
        t_antes = S.note_time(n)
        t_despues = plan["frame"] / plan["fps"]
        cambios.append((n, plan, t_antes, t_despues))
    return notas, cambios


def main():
    ap = argparse.ArgumentParser(description="repara el fps de las notas guardadas")
    ap.add_argument("slug", nargs="*", help="proyectos a revisar (default: todos)")
    ap.add_argument("--aplicar", action="store_true",
                    help="escribe los cambios (por defecto solo los reporta)")
    ap.add_argument("--todas", action="store_true",
                    help="tambien realinea notas con fps valido distinto al del video")
    a = ap.parse_args()

    total_rotas = total_escritas = 0
    fallos = []

    for slug in proyectos(a):
        if not os.path.isdir(S.pdir(slug)):
            print("  ! %s: el proyecto no existe" % slug)
            fallos.append(slug)
            continue
        notas, cambios = revisar(slug, a.todas)
        vistos = {}
        for n in notas:
            vistos.setdefault(n.get("video", "?"), set()).add(n.get("fps"))

        print("\n### %s — %d notas" % (slug, len(notas)))
        for vid, s in sorted(vistos.items()):
            marca = "  <-- fps mezclados" if len(s) > 1 else ""
            print("  %s  fps del video: %-8s  fps en las notas: %s%s"
                  % (vid, S.video_fps(slug, vid), sorted(s, key=lambda x: (x is None, x)), marca))

        if not cambios:
            print("  nada que migrar (coherente)")
            continue

        total_rotas += len(cambios)
        for n, plan, t0, t1 in cambios:
            dt = abs(t1 - t0)
            ok = "ok" if dt <= TOL_TIEMPO else "!! TIEMPO NO SE CONSERVA"
            if dt > TOL_TIEMPO:
                fallos.append("%s/%s" % (slug, n["id"]))
            print("  %s  f%-6s fps %-8s -> f%-6s fps %-8s | %s -> %s  (t %.3f -> %.3f, d=%.3f s) %s"
                  % (n["id"], n.get("frame"), n.get("fps"), plan["frame"], plan["fps"],
                     n.get("timecode"), plan["timecode"], t0, t1, dt, ok))
            txt = (n.get("text") or "").strip().replace("\n", " ")
            if txt:
                print("      \"%s\"" % txt[:84])

        if not a.aplicar:
            print("  (dry-run: no se escribio nada. Agrega --aplicar)")
            continue

        path = S.notes_path(slug)
        if os.path.isfile(path):
            bak = "%s.bak-%d" % (path, int(time.time()))
            shutil.copy2(path, bak)
            print("  copia de seguridad: %s" % os.path.basename(bak))
        for n, plan, _, _ in cambios:
            n.update(plan)
        S.save_notes(slug, notas)
        total_escritas += len(cambios)
        print("  escritas %d notas" % len(cambios))

        # verificacion post-escritura: ya nada queda por migrar (idempotencia)
        _, resto = revisar(slug, a.todas)
        if resto:
            print("  !! quedaron %d notas por migrar despues de escribir" % len(resto))
            fallos.append("%s (no idempotente)" % slug)
        else:
            print("  verificado: 0 notas pendientes")

    print("\n%s  notas con fps roto: %d   escritas: %d" %
          ("APLICADO" if a.aplicar else "DRY-RUN", total_rotas, total_escritas))
    if fallos:
        print("PROBLEMAS: %s" % ", ".join(str(x) for x in fallos))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
