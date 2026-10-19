"""Journalisation : console et fichier tournant dans data/."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_file: Path):
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s : %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    file_handler.setFormatter(formatter)
    handlers: list[logging.Handler] = [file_handler]

    # Lancé sans console (pythonw), la sortie standard n'existe pas
    if sys.stdout is not None:
        # La console Windows n'est pas toujours en UTF-8 : on évite de planter sur un accent ou un emoji
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        handlers.insert(0, console)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = handlers
