"""
Le bot : il pose les questions une par une (nom, ticker, accroche, points clés, logo, couleur, style, statut, lien,
format), montre le résumé, puis fabrique la vidéo et l'envoie. Après la vidéo, « Other style » et « Other format »
la refont aussitôt avec un seul changement.

À qui il répond ([access] public dans config.toml) :
- public = true : à tout le monde, en conversation privée (jamais dans un groupe) ;
- public = false : à son propriétaire seulement (TELEGRAM_OWNER_ID). Tant que personne n'est déclaré, il répond à
  quiconque lui écrit par son identifiant Telegram et la ligne à mettre dans .env, et rien d'autre.

Le projet en cours de chacun est gardé dans data/state.json (un redémarrage ne fait rien perdre) ; son logo dans
data/logos/u<id>.img et son son dans data/sounds/u<id>.snd (un seul de chaque par personne : le dernier envoyé).
Les fichiers reçus sont rangés sous ces noms fabriqués ici, jamais sous celui choisi par l'expéditeur.

Ouvert à tout le monde, le bot se protège (les vidéos se fabriquent une par une et occupent le PC) :
- une personne n'a qu'une vidéo en fabrication à la fois, et [access] videos_per_hour vidéos par heure ;
- au-delà de [access] queue_max vidéos en attente, il demande de revenir plus tard ;
- FILES_MAX fichiers (logos, sons) par personne par FILES_WINDOW_S.
Le propriétaire n'est limité ni en vidéos ni en fichiers.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import time
from collections import deque
from pathlib import Path

from . import messages
from .config import Config
from .maker import SIZES, VideoError, VideoMaker
from .project import (COLORS, FORMATS, LINK_MAX, NAME_MAX, OPTIONAL, STYLES, clean_line, clean_tagline,
                      clean_ticker, missing, new_project, next_step, parse_color, parse_points, parse_start, spec_of,
                      with_stars)
from .state import State
from .telegram import FILE_LIMIT, Telegram, TelegramError

log = logging.getLogger("bot")

FILES_MAX, FILES_WINDOW_S = 15, 600.0
HOUR_S = 3600.0
ATTACHMENTS = ("photo", "document", "video", "animation", "video_note", "audio", "voice", "sticker")
LOGO_SIDE_MAX = 1024  # un logo reçu est réduit à 1024 px de côté au plus avant d'être gardé


def image_of(message: dict) -> dict | None:
    """L'image jointe à un message : une photo (sa plus grande taille) ou un fichier image. None s'il n'y en a pas."""
    sizes = [size for size in message.get("photo") or [] if isinstance(size, dict) and size.get("file_id")]
    if sizes:
        return sizes[-1]  # Telegram range les tailles de la plus petite à la plus grande
    document = message.get("document")
    if isinstance(document, dict) and str(document.get("mime_type") or "").startswith("image/") and document.get("file_id"):
        return document
    return None


def sound_of(message: dict) -> dict | None:
    """Le fichier dont on peut prendre le son : audio, message vocal, vidéo, vidéo ronde, fichier audio ou vidéo."""
    for key in ("audio", "voice", "video", "video_note"):
        if isinstance(message.get(key), dict) and message[key].get("file_id"):
            return message[key]
    document = message.get("document")
    if isinstance(document, dict) and re.match(r"(audio|video)/", str(document.get("mime_type") or "")):
        return document
    return None


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:24] or "video"


def save_logo(content: bytes, path: Path) -> tuple:
    """
    Vérifie que c'est bien une image, la réduit à LOGO_SIDE_MAX et la range en PNG à path. Renvoie la couleur
    dominante du logo (pour le bouton « From the logo »). Lève OSError / ValueError si ce n'est pas une image.
    """
    import io

    from PIL import Image, ImageOps

    from .video.base import logo_colors

    with Image.open(io.BytesIO(content)) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGBA")
    img.thumbnail((LOGO_SIDE_MAX, LOGO_SIDE_MAX))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    return logo_colors(img) or ()


def has_sound(path: Path) -> bool:
    """Le fichier a-t-il une piste son que ffmpeg sait lire ?"""
    try:
        import imageio_ffmpeg

        info = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True,
                              text=True, errors="replace", timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stderr
    except (OSError, subprocess.TimeoutExpired, ImportError):
        return False
    return "Audio:" in info


class Bot:
    def __init__(self, cfg: Config, state: State, tg: Telegram, maker: VideoMaker | None = None, clock=time.time,
                 check_sound=has_sound):
        self.cfg, self.state, self.tg = cfg, state, tg
        self.maker = maker or VideoMaker(cfg)
        self.clock = clock
        self.check_sound = check_sound  # remplacé par un faux dans les tests
        self.making: set[int] = set()  # personnes dont une vidéo est en attente ou en fabrication
        self.video_times: dict[int, deque] = {}
        self.file_times: dict[int, deque] = {}
        self._tasks: set[asyncio.Task] = set()

    def _spawn(self, work) -> None:
        task = asyncio.ensure_future(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _tell(self, chat_id: int, text: str, buttons: list | None = None) -> None:
        """Un message envoyé depuis une tâche de fond : un échec d'envoi ne doit pas la faire planter."""
        try:
            await self.tg.send(chat_id, text, buttons)
        except TelegramError as e:
            log.warning("Message not sent: %s", e)

    async def welcome(self) -> None:
        for owner in self.cfg.owner_ids:
            try:
                await self.tg.send(owner, messages.STARTED)
            except TelegramError as e:
                log.warning("Start message not sent to the owner (bot never opened in Telegram? open it and press Start): %s", e)

    # --- qui, et combien ---------------------------------------------------------------------------

    def is_owner(self, user_id) -> bool:
        return user_id in self.cfg.owner_ids

    def allowed(self, user_id) -> bool:
        return self.cfg.public or self.is_owner(user_id)

    def _recent(self, times: dict[int, deque], user_id: int, window_s: float) -> deque:
        mine = times.setdefault(user_id, deque())
        now = self.clock()
        while mine and now - mine[0] >= window_s:
            mine.popleft()
        return mine

    def reserve(self, user_id: int) -> str:
        """Prend une place dans la file des vidéos. "" si c'est fait, sinon pourquoi c'est refusé. render la rend."""
        if user_id in self.making:
            return messages.ALREADY_MAKING
        if not self.is_owner(user_id):
            recent = self._recent(self.video_times, user_id, HOUR_S)
            if len(recent) >= self.cfg.videos_per_hour:
                return messages.too_many_videos(self.cfg.videos_per_hour, HOUR_S - (self.clock() - recent[0]))
            if len(self.making) >= self.cfg.queue_max:
                return messages.busy(len(self.making))
            recent.append(self.clock())
        self.making.add(user_id)
        return ""

    def file_allowed(self, user_id: int) -> bool:
        if self.is_owner(user_id):
            return True
        recent = self._recent(self.file_times, user_id, FILES_WINDOW_S)
        if len(recent) >= FILES_MAX:
            return False
        recent.append(self.clock())
        return True

    # --- le projet ---------------------------------------------------------------------------------

    def project(self, user_id: int) -> dict | None:
        return self.state.project(user_id)

    def save(self, user_id: int, project: dict | None) -> None:
        self.state.set_project(user_id, project)

    def logo_path(self, project: dict) -> str:
        path = self.cfg.logos_dir / Path(str(project.get("logo") or "")).name
        return str(path) if project.get("logo") and path.is_file() else ""

    def sound_path(self, project: dict) -> str:
        path = self.cfg.sounds_dir / Path(str(project.get("sound") or "")).name
        return str(path) if project.get("sound") and path.is_file() else ""

    async def ask(self, chat_id: int, user_id: int, project: dict, key: str) -> None:
        project["step"] = key
        self.save(user_id, project)
        logo_color = tuple(project.get("logo_color") or ()) if project.get("logo") else None
        await self.tg.send(chat_id, *messages.question(key, bool(project.get("editing")), logo_color or None))

    async def show_summary(self, chat_id: int, project: dict, message_id: int | None = None) -> None:
        text, buttons = messages.summary(project)
        if message_id is not None:
            try:
                await self.tg.edit(chat_id, message_id, text, buttons)
                return
            except TelegramError:
                pass  # message trop vieux ou qui n'est pas un texte (la vidéo) : on en envoie un nouveau
        await self.tg.send(chat_id, text, buttons)

    async def advance(self, chat_id: int, user_id: int, project: dict, key: str) -> None:
        """La réponse à la question key est notée : question suivante, résumé, ou vidéo refaite tout de suite."""
        if project.get("redo"):
            project.update(redo=False, editing=False, step=None)
            self.save(user_id, project)
            await self.start_render(chat_id, user_id, project)
            return
        if project.get("editing"):
            project.update(editing=False, step=None)
            self.save(user_id, project)
            await self.show_summary(chat_id, project)
            return
        following = next_step(key)
        if following:
            await self.ask(chat_id, user_id, project, following)
            return
        project["step"] = None
        self.save(user_id, project)
        await self.show_summary(chat_id, project)

    # --- messages ----------------------------------------------------------------------------------

    async def handle(self, update: dict) -> None:
        if "callback_query" in update:
            await self.on_button(update["callback_query"])
        elif "message" in update:
            await self.on_message(update["message"])

    async def on_message(self, message: dict) -> None:
        chat, sender = message.get("chat") or {}, message.get("from") or {}
        if chat.get("type") != "private":
            return  # ajouté à un groupe : il n'y dit rien
        chat_id, user_id = chat.get("id"), sender.get("id")
        if chat_id is None or user_id is None:
            return
        if not self.allowed(user_id):
            await self.tg.send(chat_id, messages.PRIVATE if self.cfg.owner_ids else messages.no_owner(user_id))
            return
        if any(key in message for key in ATTACHMENTS):
            image, sound = image_of(message), sound_of(message)
            if image is not None:
                await self.take_file(chat_id, user_id, image, "logo", "")
            elif sound is not None:
                await self.take_file(chat_id, user_id, sound, "sound", str(message.get("caption") or ""))
            else:
                await self.tg.send(chat_id, messages.NOT_USABLE)
            return
        text = str(message.get("text") or "").strip()
        if not text:
            return
        if text.startswith("/"):
            await self.command(chat_id, user_id, text)
            return
        project = self.project(user_id)
        if project is None:
            await self.tg.send(chat_id, messages.NO_PROJECT)
        elif project.get("step"):
            await self.answer(chat_id, user_id, project, project["step"], text, message.get("entities"))
        else:
            await self.show_summary(chat_id, project)

    async def command(self, chat_id: int, user_id: int, text: str) -> None:
        name = text[1:].partition(" ")[0].split("@")[0].lower()
        project = self.project(user_id)
        if name == "start":
            await self.tg.send(chat_id, messages.HELP)
            if project is None:
                await self.start_project(chat_id, user_id)
            else:
                await self.show_summary(chat_id, project)
        elif name == "help":
            await self.tg.send(chat_id, messages.HELP)
        elif name == "new":
            await self.start_project(chat_id, user_id)
        elif name == "edit":
            if project is None:
                await self.tg.send(chat_id, messages.NO_PROJECT)
            else:
                await self.tg.send(chat_id, *messages.edit_menu())
        elif name == "cancel":
            self.save(user_id, None)
            await self.tg.send(chat_id, messages.CANCELLED)
        elif name == "stats" and self.is_owner(user_id):
            await self.tg.send(chat_id, messages.stats(*self.state.stats, len(self.making), self.cfg.public))
        else:
            await self.tg.send(chat_id, "Unknown command. /help says how it works.")

    async def start_project(self, chat_id: int, user_id: int, logo: str = "", logo_color: tuple = ()) -> None:
        project = new_project(self.cfg.default_format, self.cfg.default_music)
        if logo:
            project.update(logo=logo, logo_color=list(logo_color))
        await self.ask(chat_id, user_id, project, "name")

    async def answer(self, chat_id: int, user_id: int, project: dict, key: str, text: str, entities) -> None:
        """Une réponse tapée à la question en cours."""
        if key == "name":
            value = clean_line(text, NAME_MAX)
            if not re.search(r"\w", value):
                await self.tg.send(chat_id, messages.NAME_EMPTY)
                return
            project["name"] = value
        elif key == "ticker":
            value = clean_ticker(text)
            if not value:
                await self.tg.send(chat_id, messages.TICKER_BAD, [[{"text": "Skip ⏭", "callback_data": "skip"}]])
                return
            project["ticker"] = value
        elif key == "tagline":
            value = clean_tagline(with_stars(text, entities))
            if not re.search(r"\w", value):
                await self.tg.send(chat_id, messages.TAGLINE_EMPTY)
                return
            project["tagline"] = value
        elif key == "points":
            value = parse_points(text)
            if not value:
                await self.tg.send(chat_id, messages.POINTS_EMPTY)
                return
            project["points"] = value
        elif key == "color":
            color = parse_color(text)
            if color is None:
                await self.tg.send(chat_id, messages.COLOR_BAD)
                return
            project["color"] = list(color)
        elif key == "link":
            project["link"] = clean_line(text, LINK_MAX)
        elif key == "logo":
            await self.tg.send(chat_id, messages.QUESTIONS["logo"], [[{"text": "Skip ⏭", "callback_data": "skip"}]])
            return
        else:  # style, statut, format : des boutons
            await self.tg.send(chat_id, messages.TAP_BUTTON)
            return
        await self.advance(chat_id, user_id, project, key)

    # --- boutons -----------------------------------------------------------------------------------

    async def on_button(self, query: dict) -> None:
        user_id = (query.get("from") or {}).get("id")
        message = query.get("message") or {}
        chat, message_id = message.get("chat") or {}, message.get("message_id")
        chat_id = chat.get("id")
        if chat_id is None or user_id is None or chat.get("type") != "private" or not self.allowed(user_id):
            await self.tg.answer(query.get("id", ""), messages.PRIVATE)
            return
        is_text = "text" in message
        toast = await self.button(chat_id, message_id if is_text else None, user_id, str(query.get("data") or ""))
        await self.tg.answer(query.get("id", ""), toast or "")

    async def button(self, chat_id: int, message_id: int | None, user_id: int, data: str) -> str | None:
        """Traite un bouton. message_id : le message texte qui le porte (None pour la vidéo). Renvoie le petit message à afficher."""
        if data == "new":
            await self.start_project(chat_id, user_id)
            return None
        project = self.project(user_id)
        if project is None:
            return "Tap /new to start a video."
        kind, _, value = data.partition(":")
        step = project.get("step")

        if data == "skip":
            if step not in OPTIONAL:
                return None
            project[step] = [] if step == "points" else ""
            await self.advance(chat_id, user_id, project, step)
        elif kind == "c":
            color = tuple(project.get("logo_color") or ()) if value == "logo" else COLORS.get(value)
            if not color:
                return None
            project["color"] = list(color)
            await self._after_choice(chat_id, user_id, project, "color")
        elif kind == "st" and value in STYLES:
            project["style"] = value
            await self._after_choice(chat_id, user_id, project, "style")
        elif kind == "s" and value in ("live", "soon", "none"):
            project["status"] = "" if value == "none" else value
            await self._after_choice(chat_id, user_id, project, "status")
        elif kind == "f" and value in FORMATS:
            project["format"] = value
            await self._after_choice(chat_id, user_id, project, "format")
        elif data == "make":
            await self.start_render(chat_id, user_id, project)
        elif data == "edit":
            text, buttons = messages.edit_menu()
            if message_id is not None:
                await self.tg.edit(chat_id, message_id, text, buttons)
            else:
                await self.tg.send(chat_id, text, buttons)
        elif kind == "e" and value in messages.LABELS and value != "sound":
            project["editing"] = True
            project["redo"] = False
            await self.ask(chat_id, user_id, project, value)
        elif data == "back":
            project.update(editing=False, redo=False, step=None)
            self.save(user_id, project)
            await self.show_summary(chat_id, project, message_id)
        elif data == "sound":
            project["music"] = "beat" if project.get("music") == "none" else "none"
            self.save(user_id, project)
            await self.show_summary(chat_id, project, message_id)
        elif data == "x":
            self.save(user_id, None)
            if message_id is not None:
                await self.tg.edit(chat_id, message_id, messages.CANCELLED)
            else:
                await self.tg.send(chat_id, messages.CANCELLED)
        elif data in ("re:style", "re:format"):
            project.update(editing=True, redo=True)
            await self.ask(chat_id, user_id, project, data[3:])
        return None

    async def _after_choice(self, chat_id: int, user_id: int, project: dict, key: str) -> None:
        """
        Un bouton de choix pressé. Si c'est la question en cours, on avance ; sinon (un vieux bouton plus haut dans
        la conversation), le choix est noté et on repose la question en cours (ou on remontre le résumé).
        """
        step = project.get("step")
        if step == key:
            await self.advance(chat_id, user_id, project, key)
        elif step:
            await self.ask(chat_id, user_id, project, step)
        else:
            self.save(user_id, project)
            await self.show_summary(chat_id, project)

    # --- fichiers reçus ----------------------------------------------------------------------------

    async def take_file(self, chat_id: int, user_id: int, media: dict, kind: str, caption: str) -> None:
        if int(media.get("file_size") or 0) > FILE_LIMIT:
            await self.tg.send(chat_id, messages.LOGO_TOO_BIG if kind == "logo" else messages.SOUND_TOO_BIG)
            return
        if kind == "sound" and self.project(user_id) is None:
            await self.tg.send(chat_id, messages.NO_PROJECT)
            return
        if not self.file_allowed(user_id):
            await self.tg.send(chat_id, messages.TOO_MANY_PICTURES)
            return
        self._spawn(self.on_logo(chat_id, user_id, media) if kind == "logo" else self.on_sound(chat_id, user_id, media, caption))

    async def on_logo(self, chat_id: int, user_id: int, media: dict) -> None:
        try:
            content = await self.tg.download(str(media.get("file_id") or ""))
        except TelegramError as e:
            log.warning("Logo not fetched: %s", e)
            await self._tell(chat_id, messages.LOGO_TOO_BIG if e.too_big else messages.LOGO_NOT_FETCHED)
            return
        name = f"u{int(user_id)}.img"
        try:
            color = await asyncio.to_thread(save_logo, content, self.cfg.logos_dir / name)
        except (OSError, ValueError, SyntaxError) as e:  # ce que Pillow lève devant un fichier qui n'est pas une image
            log.warning("Logo not opened (%s)", type(e).__name__)
            await self._tell(chat_id, messages.LOGO_BAD)
            return
        log.info("Logo saved for %s", user_id)
        project = self.project(user_id)
        try:
            if project is None:  # un logo envoyé avant /new : il ouvre un projet
                await self.tg.send(chat_id, messages.LOGO_SAVED)
                await self.start_project(chat_id, user_id, name, color)
                return
            project.update(logo=name, logo_color=list(color))
            if project.get("step") == "logo":
                await self.tg.send(chat_id, messages.LOGO_SAVED)
                await self.advance(chat_id, user_id, project, "logo")
            else:
                self.save(user_id, project)
                await self.tg.send(chat_id, messages.LOGO_SAVED)
                if not project.get("step"):
                    await self.show_summary(chat_id, project)
        except TelegramError as e:
            log.warning("Message not sent: %s", e)

    async def on_sound(self, chat_id: int, user_id: int, media: dict, caption: str) -> None:
        try:
            content = await self.tg.download(str(media.get("file_id") or ""))
        except TelegramError as e:
            log.warning("Sound not fetched: %s", e)
            await self._tell(chat_id, messages.SOUND_TOO_BIG if e.too_big else messages.SOUND_NOT_FETCHED)
            return
        name = f"u{int(user_id)}.snd"
        path = self.cfg.sounds_dir / name
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_bytes, content)
        except OSError as e:
            log.warning("Sound not kept (%s)", type(e).__name__)
            await self._tell(chat_id, messages.SOUND_NOT_FETCHED)
            return
        if not await asyncio.to_thread(self.check_sound, path):
            path.unlink(missing_ok=True)
            await self._tell(chat_id, "⚠️ I found no sound in this file. Send an audio file or a video with sound.")
            return
        project = self.project(user_id)
        if project is None:
            return
        start = parse_start(caption) or 0.0
        project.update(music="file", sound=name, sound_start=start)
        self.save(user_id, project)
        log.info("Sound saved for %s (from %.1f s)", user_id, start)
        await self._tell(chat_id, messages.sound_saved(start))
        if not project.get("step"):
            try:
                await self.show_summary(chat_id, project)
            except TelegramError as e:
                log.warning("Message not sent: %s", e)

    # --- fabrication -------------------------------------------------------------------------------

    async def start_render(self, chat_id: int, user_id: int, project: dict) -> None:
        lacking = missing(project)
        if lacking:
            await self.tg.send(chat_id, messages.NOT_READY.format(", ".join(messages.LABELS[key] for key in lacking)))
            return
        refusal = self.reserve(user_id)
        if refusal:
            await self.tg.send(chat_id, refusal)
            return
        await self.tg.send(chat_id, messages.making(project, len(self.making) - 1))
        self._spawn(self.render(chat_id, user_id, dict(project)))

    async def render(self, chat_id: int, user_id: int, project: dict) -> None:
        """Fabrique la vidéo du projet, l'envoie, et rend la place dans la file."""
        fmt = project.get("format") if project.get("format") in FORMATS else "landscape"
        name = f"{slug(project.get('name') or '')}-{project.get('style')}-{fmt}-{int(time.time())}"
        try:
            spec = spec_of(project, self.logo_path(project), self.sound_path(project))
            path = await self.maker.make(spec, name)
            await self.tg.send_video(chat_id, await asyncio.to_thread(path.read_bytes), messages.video_caption(project),
                                     *SIZES[fmt], messages.video_buttons(), filename=f"{slug(project.get('name') or '')}.mp4")
            self.state.count_video(user_id)
            log.info("Video sent to %s: %s", user_id, path.name)
        except VideoError as e:
            log.warning("Video %s: %s", name, e)
            await self._tell(chat_id, messages.VIDEO_FAILED)
        except TelegramError as e:
            log.warning("Video %s not sent: %s", name, e)
            await self._tell(chat_id, messages.VIDEO_NOT_SENT)
        except Exception:
            log.exception("Video %s: unexpected error", name)
            await self._tell(chat_id, messages.VIDEO_FAILED)
        finally:
            self.making.discard(user_id)

