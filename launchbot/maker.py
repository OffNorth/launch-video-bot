"""
La fabrication des vidéos, une à la fois, dans un programme à part (python -m launchbot.video.render) : le bot
reste joignable pendant les 10 à 40 s que ça prend. (Même principe que pnl-card-bot/cardbot/cards.py.)
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path

from .config import ROOT, Config

log = logging.getLogger("maker")

# Temps laissé à la fabrication d'une vidéo, en secondes (10 à 40 s mesurés le 19 octobre 2026 ; large, le PC peut
# être occupé par d'autres bots)
RENDER_TIMEOUT_S = 300.0
# Vidéos gardées dans data/videos : au-delà, les plus anciennes sont effacées (2 à 20 Mo chacune)
KEEP_VIDEOS = 30
# Taille des vidéos selon le format, en pixels (celles de video/base.py, répétées ici pour ne pas charger le dessin
# dans le bot ; un test vérifie qu'elles restent égales)
SIZES = {"landscape": (1920, 1080), "square": (1080, 1080), "portrait": (1080, 1920)}


class VideoError(Exception):
    """La vidéo n'a pas pu être fabriquée. Le message est lisible tel quel."""


class VideoMaker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.lock = asyncio.Lock()

    async def make(self, spec: dict, name: str) -> Path:
        """Fabrique data/videos/<name>.mp4 à partir de la description. Lève VideoError si ça échoue."""
        out = self.cfg.videos_dir / f"{name}.mp4"
        # Fabriquée sous un nom provisoire puis renommée : une vidéo à moitié écrite ne peut pas être envoyée
        part = out.with_name(f"{name}.part.mp4")
        async with self.lock:
            self.cfg.videos_dir.mkdir(parents=True, exist_ok=True)
            spec_path = out.with_suffix(".json")
            spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
            # Priorité basse (Windows) : la fabrication ne doit pas ralentir les bots qui tournent sur ce PC
            flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "launchbot.video.render", str(spec_path), str(part), cwd=str(ROOT),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=flags)
            except OSError as e:
                raise VideoError(f"the video maker did not start ({type(e).__name__})") from None
            try:
                _, errors = await asyncio.wait_for(process.communicate(), RENDER_TIMEOUT_S)
            except asyncio.TimeoutError:
                process.kill()
                raise VideoError("the video took too long to make") from None
            if process.returncode or not part.exists():
                detail = (errors or b"").decode("utf-8", "replace").strip().splitlines()
                log.warning("Video %s failed: %s", name, detail[-1] if detail else f"code {process.returncode}")
                part.unlink(missing_ok=True)
                raise VideoError("the video could not be made (see data/bot.log)")
            part.replace(out)
            if part.with_suffix(".png").exists():
                part.with_suffix(".png").replace(out.with_suffix(".png"))  # la vignette
            self._prune()
        return out

    def _prune(self) -> None:
        """Efface les plus anciennes vidéos au-delà de KEEP_VIDEOS, avec leur vignette et leur description."""
        videos = sorted(self.cfg.videos_dir.glob("*.mp4"), key=lambda path: path.stat().st_mtime, reverse=True)
        for video in videos[KEEP_VIDEOS:]:
            for path in (video, video.with_suffix(".png"), video.with_suffix(".json")):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
