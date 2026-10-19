r"""
Fabrique une vidéo à partir de sa description (un fichier JSON écrit par maker.py), dans un programme à part :
dessiner 300 à 600 images occupe un cœur du processeur 20 à 60 s, et le bot doit rester joignable pendant ce temps.

    venv\Scripts\python.exe -m launchbot.video.render projet.json sortie.mp4               la vidéo
    venv\Scripts\python.exe -m launchbot.video.render projet.json sortie.mp4 --stills 1,5  des images de contrôle

Ce que la description contient en plus du projet (voir base.Film) :
    style        "product", "kinetic", "luxe" ou "coins"
    music        "beat" (la musique fabriquée pour le style, music.py), "none" (muette) ou "file" (le son envoyé)
    music_file   le fichier dont on prend le son (audio ou vidéo), avec music = "file"
    music_start  à partir de quelle seconde de ce fichier
À côté de la vidéo, une image fixe (même nom, .png) : la vignette, au moment choisi par le style (cover_t).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import music
from .base import FPS, Film

OUT_COLORS = "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
STYLES = ("product", "kinetic", "luxe", "coins")


def film_of(spec: dict) -> Film:
    style = str(spec.get("style") or "product")
    if style == "kinetic":
        from .kinetic import Kinetic as cls
    elif style == "luxe":
        from .luxe import Luxe as cls
    elif style == "coins":
        from .coins import Coins as cls
    else:
        from .product import Product as cls
    return cls(spec)


def find_ffmpeg() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise SystemExit("ffmpeg not found: install the imageio-ffmpeg package (requirements.txt)") from None


def audio_input(spec: dict, film: Film, out: Path) -> list[str]:
    """Les options ffmpeg de la piste son ([] : vidéo muette)."""
    choice = str(spec.get("music") or "beat")
    if choice == "file":
        source = Path(str(spec.get("music_file") or ""))
        if source.is_file():
            start = max(0.0, float(spec.get("music_start") or 0))
            return ["-ss", f"{start:.2f}", "-t", f"{film.duration:.3f}", "-i", str(source)]
        choice = "beat"  # le fichier a disparu : la musique du style
    if choice == "none":
        return []
    wav = out.with_name(out.stem + ".music.wav")
    music.make_track(film.STYLE, film.duration, wav, film.accents, getattr(film, "dings", ()))
    return ["-i", str(wav)]


def render(spec: dict, out: Path, stills: list[float] | None = None) -> None:
    film = film_of(spec)
    if stills:
        for t in stills:
            path = out.with_name(f"{out.stem}-{t:05.2f}.png")
            film.frame(t).save(path)
            print(path)
        print(f"{film.STYLE}: {film.duration:.1f} s, {film.W}x{film.H}")
        return

    ffmpeg = find_ffmpeg()
    out.parent.mkdir(parents=True, exist_ok=True)
    audio = audio_input(spec, film, out)
    frames_in = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{film.W}x{film.H}", "-r", str(FPS), "-i", "pipe:0"]
    video_out = ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-maxrate", "12M", "-bufsize", "24M", "-vf", OUT_COLORS, "-movflags", "+faststart"]
    if audio:
        fade = f"afade=t=in:d=0.05,afade=t=out:st={max(0.0, film.duration - 1.2):.2f}:d=1.2"
        command = [ffmpeg, "-loglevel", "error", "-y", *frames_in, *audio, "-map", "0:v", "-map", "1:a:0?", "-af", fade,
                   "-c:a", "aac", "-b:a", "192k", "-shortest", *video_out, str(out)]
    else:
        command = [ffmpeg, "-loglevel", "error", "-y", *frames_in, *video_out, str(out)]
    writer = subprocess.Popen(command, stdin=subprocess.PIPE)
    total = round(film.duration * FPS)
    cover = min(total - 1, round(film.cover_t * FPS))
    try:
        for n in range(total):
            img = film.frame(n / FPS)
            if n == cover:
                img.save(out.with_suffix(".png"))
            writer.stdin.write(img.tobytes())
    finally:
        writer.stdin.close()
        writer.wait()
        out.with_name(out.stem + ".music.wav").unlink(missing_ok=True)
    if writer.returncode:
        raise SystemExit(f"ffmpeg failed (code {writer.returncode})")
    print(f"{out}: {film.duration:.1f} s, {film.W}x{film.H}, {out.stat().st_size / 1e6:.1f} MB")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fabrique la vidéo de présentation décrite dans un fichier JSON.")
    parser.add_argument("spec", help="le fichier JSON qui décrit le projet")
    parser.add_argument("out", help="la vidéo à écrire (.mp4)")
    parser.add_argument("--stills", default="", help="instants (s, séparés par des virgules) à enregistrer en images, sans faire la vidéo")
    args = parser.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    render(spec, Path(args.out), [float(x) for x in args.stills.split(",")] if args.stills else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
