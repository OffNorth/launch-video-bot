"""
Dialogue avec Telegram par l'API des bots : lire les messages et les boutons pressés, recevoir logos et sons,
envoyer textes et vidéos. (Copie de celui du bot des vidéos de PnL, pnl-card-bot, lui-même copié de calls-trader-bot.)

Le token fait partie de l'adresse appelée : il ne doit jamais apparaître dans un journal.
Les erreurs sont donc décrites par leur nature, jamais par l'adresse ni l'exception brute.
"""

from __future__ import annotations

import asyncio
import json
import logging

import aiohttp

log = logging.getLogger("telegram")

API = "https://api.telegram.org"
MAX_RATE_LIMIT_WAIT_S = 60.0
POLL_S = 25
UPDATES = ["message", "callback_query"]
# Temps laissé à l'envoi d'une vidéo (2 à 20 Mo), en secondes
UPLOAD_TIMEOUT_S = 180
# Telegram refuse un texte de plus de 4096 caractères : on coupe avant, sur une fin de ligne
MAX_TEXT = 3900
# Un bot ne peut télécharger que les fichiers de 20 Mo au plus (limite de l'API des bots de Telegram)
FILE_LIMIT = 20 * 1024 * 1024
DOWNLOAD_TIMEOUT_S = 120


class TelegramError(Exception):
    def __init__(self, message: str, status: int = 0, description: str = ""):
        super().__init__(message)
        self.status = status
        self.description = description.lower()

    @property
    def bad_token(self) -> bool:
        return self.status in (401, 404)

    @property
    def conflict(self) -> bool:
        """Un autre programme lit les messages du même bot."""
        return self.status == 409

    @property
    def too_big(self) -> bool:
        """Le fichier demandé dépasse ce qu'un bot a le droit de télécharger."""
        return "too big" in self.description

    @property
    def unchanged(self) -> bool:
        """Le message qu'on voulait modifier a déjà ce contenu : ce n'est pas une erreur."""
        return "message is not modified" in self.description


def clip(text: str) -> str:
    """Raccourcit un texte trop long pour Telegram, sur une fin de ligne (une balise HTML ne doit pas être coupée)."""
    if len(text) <= MAX_TEXT:
        return text
    return text[:MAX_TEXT].rsplit("\n", 1)[0] + "\n…"


class Telegram:
    def __init__(self, session: aiohttp.ClientSession, token: str):
        self.session = session
        self.token = token

    async def call(self, method: str, payload: dict | None = None, files: dict | None = None, timeout: float = 15):
        """files : fichiers joints, {nom du champ: (nom du fichier, contenu, type)}."""
        url = f"{API}/bot{self.token}/{method}"
        for attempt in range(3):
            if not files:
                body = {"json": payload or {}}
            else:
                # Un fichier part en formulaire, refait à chaque essai : il ne sert qu'une fois
                form = aiohttp.FormData()
                for key, value in (payload or {}).items():
                    form.add_field(key, value if isinstance(value, str) else json.dumps(value))
                for key, (filename, content, content_type) in files.items():
                    form.add_field(key, content, filename=filename, content_type=content_type)
                body = {"data": form}
            try:
                async with self.session.post(url, timeout=aiohttp.ClientTimeout(total=timeout), **body) as resp:
                    status = resp.status
                    try:
                        data = await resp.json(content_type=None)
                    except ValueError:
                        data = None  # pas du JSON : une page d'erreur (fichier trop gros, panne), le code HTTP le dira
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                raise TelegramError(f"Telegram unreachable ({type(e).__name__})") from None
            if data is None:
                raise TelegramError(f"unreadable Telegram response (HTTP {status})", status)

            if status == 200 and isinstance(data, dict) and data.get("ok"):
                return data.get("result")
            description = str(data.get("description") or "") if isinstance(data, dict) else ""
            if status == 429:
                wait = float(((data or {}).get("parameters") or {}).get("retry_after") or 5)
                if attempt < 2 and wait <= MAX_RATE_LIMIT_WAIT_S:
                    log.warning("Telegram asks to wait %.0f s", wait)
                    await asyncio.sleep(wait + 0.5)
                    continue
            raise TelegramError(f"{method} rejected (HTTP {status}: {description})", status, description)
        raise TelegramError("Telegram is rate limiting", 429)

    async def me(self) -> str:
        """Nom d'utilisateur du bot : sert à vérifier le token."""
        return str((await self.call("getMe") or {}).get("username") or "")

    async def updates(self, offset: int) -> list[dict]:
        payload = {"offset": offset, "timeout": POLL_S, "allowed_updates": UPDATES}
        return await self.call("getUpdates", payload, timeout=POLL_S + 15) or []

    async def send(self, chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> int | None:
        payload = {"chat_id": chat_id, "text": clip(text), "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        return (await self.call("sendMessage", payload) or {}).get("message_id")

    async def edit(self, chat_id: int, message_id: int, text: str, buttons: list[list[dict]] | None = None) -> None:
        """Remplace le texte et les boutons d'un message déjà envoyé (les menus se mettent à jour sur place)."""
        payload = {"chat_id": chat_id, "message_id": message_id, "text": clip(text), "parse_mode": "HTML",
                   "link_preview_options": {"is_disabled": True}, "reply_markup": {"inline_keyboard": buttons or []}}
        try:
            await self.call("editMessageText", payload)
        except TelegramError as e:
            if not e.unchanged:
                raise

    async def answer(self, callback_id: str, text: str = "") -> None:
        """Accuse réception d'un bouton pressé (sinon Telegram laisse le bouton « tourner »). text : petit message affiché."""
        payload = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text[:190]
        try:
            await self.call("answerCallbackQuery", payload)
        except TelegramError:
            pass  # bouton pressé il y a trop longtemps : sans importance

    async def send_video(self, chat_id: int, video: bytes, caption: str, width: int, height: int,
                         buttons: list[list[dict]] | None = None, filename: str = "video.mp4") -> None:
        """Envoie une vidéo MP4 avec son, et son texte en légende (1024 caractères au plus). width, height : en pixels."""
        payload = {"chat_id": str(chat_id), "caption": caption[:1000], "parse_mode": "HTML", "width": width, "height": height,
                   "supports_streaming": True}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        await self.call("sendVideo", payload, files={"video": (filename, video, "video/mp4")}, timeout=UPLOAD_TIMEOUT_S)

    async def download(self, file_id: str, limit: int = FILE_LIMIT) -> bytes:
        """
        Le contenu d'un fichier envoyé au bot (une capture, une vidéo de fond). Lève TelegramError s'il est trop gros (Telegram
        refuse au-delà de 20 Mo) ou introuvable. L'adresse de téléchargement contient le token : jamais dans une erreur.
        """
        info = await self.call("getFile", {"file_id": file_id})
        path = str((info or {}).get("file_path") or "")
        if not path:
            raise TelegramError("Telegram did not give the file")
        content = bytearray()
        try:
            async with self.session.get(f"{API}/file/bot{self.token}/{path}",
                                        timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT_S)) as resp:
                if resp.status != 200:
                    raise TelegramError(f"file download refused (HTTP {resp.status})", resp.status)
                async for chunk in resp.content.iter_chunked(65536):
                    content += chunk
                    if len(content) > limit:
                        raise TelegramError("file is too big", 400, "file is too big")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise TelegramError(f"Telegram unreachable ({type(e).__name__})") from None
        return bytes(content)

    async def set_commands(self, commands) -> None:
        """La liste proposée quand on tape « / » dans la conversation."""
        await self.call("setMyCommands", {"commands": [{"command": name, "description": text} for name, text in commands]})
