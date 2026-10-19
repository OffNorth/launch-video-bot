"""
Ce que le bot retient d'un lancement à l'autre (data/state.json) : où il en est dans les messages Telegram, le
projet en cours de chacun (pour ne pas tout redemander après un redémarrage), et deux compteurs pour /stats.

Le fichier est réécrit en entier à chaque changement, sous un nom provisoire puis renommé : une coupure au mauvais
moment ne peut pas le laisser à moitié écrit.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Personnes dont on garde le projet et qu'on compte dans /stats : au-delà, les plus anciennes sont oubliées
KEEP_USERS = 1000


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data = loaded
        except (OSError, ValueError):
            pass  # premier lancement, ou fichier abîmé : on repart de zéro

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        part = self.path.with_suffix(".part")
        part.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(part, self.path)

    @property
    def update_offset(self) -> int:
        """Le prochain message Telegram à lire."""
        try:
            return int(self.data.get("update_offset") or 0)
        except (TypeError, ValueError):
            return 0

    @update_offset.setter
    def update_offset(self, value: int) -> None:
        self.data["update_offset"] = int(value)
        self.save()

    def _table(self, key: str) -> dict:
        table = self.data.get(key)
        if not isinstance(table, dict):
            table = self.data[key] = {}
        return table

    def project(self, user_id: int) -> dict | None:
        found = self._table("projects").get(str(user_id))
        return found if isinstance(found, dict) else None

    def set_project(self, user_id: int, project: dict | None) -> None:
        """Garde (ou oublie, avec None) le projet de cette personne."""
        table = self._table("projects")
        table.pop(str(user_id), None)  # remis en dernier : c'est l'ordre d'ancienneté
        if project is not None:
            table[str(user_id)] = project
        for old in list(table)[:-KEEP_USERS]:
            del table[old]
        self.save()

    def count_video(self, user_id: int) -> None:
        """Note une vidéo fabriquée pour cette personne."""
        table = self._table("users")
        made = table.pop(str(user_id), 0)
        table[str(user_id)] = (made if isinstance(made, int) else 0) + 1
        for old in list(table)[:-KEEP_USERS]:
            del table[old]
        try:
            self.data["videos"] = int(self.data.get("videos") or 0) + 1
        except (TypeError, ValueError):
            self.data["videos"] = 1
        self.save()

    @property
    def stats(self) -> tuple[int, int]:
        """(personnes qui ont reçu au moins une vidéo, vidéos fabriquées en tout)."""
        try:
            videos = int(self.data.get("videos") or 0)
        except (TypeError, ValueError):
            videos = 0
        return len(self._table("users")), videos
