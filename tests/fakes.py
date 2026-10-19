"""
Les faux des tests : un faux Telegram qui note ce qu'on lui envoie et un faux fabricant de vidéos. Aucun test ne
touche au réseau.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

from PIL import Image

from launchbot.config import Config
from launchbot.telegram import TelegramError

OWNER = 4242
OTHER = 777


def make_config(root: Path, **changes) -> Config:
    values = dict(public=False, videos_per_hour=6, queue_max=5, default_format="landscape", default_music="beat",
                  telegram_token="test-token", owner_ids=(OWNER,), data_dir=root / "data")
    values.update(changes)
    return Config(**values)


def png_bytes(color=(200, 40, 40), size=(64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


class FakeTelegram:
    """Note chaque envoi. Ne touche pas au réseau."""

    def __init__(self):
        self.sent: list[dict] = []
        self.files: dict[str, bytes] = {}

    def of(self, kind: str) -> list[dict]:
        return [item for item in self.sent if item["kind"] == kind]

    def texts(self) -> list[str]:
        return [item["text"] for item in self.sent if item["kind"] in ("text", "edit")]

    def last(self) -> dict:
        return [item for item in self.sent if item["kind"] in ("text", "edit")][-1]

    def buttons(self) -> list[str]:
        """Les données des boutons du dernier message."""
        return [b["callback_data"] for row in self.last()["buttons"] for b in row]

    async def send(self, chat_id, text, buttons=None):
        self.sent.append({"kind": "text", "chat": chat_id, "text": text, "buttons": buttons or []})
        return len(self.sent)

    async def edit(self, chat_id, message_id, text, buttons=None):
        self.sent.append({"kind": "edit", "chat": chat_id, "message": message_id, "text": text, "buttons": buttons or []})

    async def answer(self, callback_id, text=""):
        self.sent.append({"kind": "answer", "text": text})

    async def send_video(self, chat_id, video, caption, width, height, buttons=None, filename="video.mp4"):
        self.sent.append({"kind": "video", "chat": chat_id, "video": video, "text": caption, "size": (width, height),
                          "buttons": buttons or [], "filename": filename})

    async def download(self, file_id, limit=0):
        if file_id not in self.files:
            raise TelegramError("file download refused (HTTP 404)", 404)
        return self.files[file_id]


class FakeMaker:
    """Note les descriptions reçues et rend un petit fichier à la place de la vidéo."""

    def __init__(self, folder: Path, fail: bool = False):
        self.folder = folder
        self.specs: list[dict] = []
        self.fail = fail
        self.release = None  # un asyncio.Event : la fabrication attend qu'on la libère

    async def make(self, spec, name):
        from launchbot.maker import VideoError

        self.specs.append(spec)
        if self.release is not None:
            await self.release.wait()
        if self.fail:
            raise VideoError("the video could not be made")
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{name}.mp4"
        path.write_bytes(b"fake video")
        return path


def private(user_id: int, **fields) -> dict:
    return {"message": {"chat": {"id": user_id, "type": "private"}, "from": {"id": user_id}, **fields}}


def press(user_id: int, data: str, message_id: int = 1, text: bool = True) -> dict:
    message = {"chat": {"id": user_id, "type": "private"}, "message_id": message_id}
    if text:
        message["text"] = "…"
    return {"callback_query": {"id": "q", "from": {"id": user_id}, "message": message, "data": data}}


async def settle(bot) -> None:
    """Attend la fin des tâches de fond du bot (téléchargements, fabrications)."""
    for _ in range(50):
        if not bot._tasks:
            return
        await asyncio.sleep(0.01)
