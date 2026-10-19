"""
Bot Telegram des vidéos de présentation de launchpads et de projets memecoin : on lui donne un nom, une accroche,
un logo, une couleur, un style, il renvoie une courte vidéo de présentation.

Usage :
    python run.py                         lance le bot (Ctrl+C pour l'arrêter)
    python run.py --check                 vérifie le réglage (Telegram, propriétaire, fabrication) sans rien envoyer
    python run.py --demo                  fabrique une vidéo d'exemple de chaque style dans data/videos, sans Telegram
    python run.py --demo --format portrait  la même chose, en 9:16
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import aiohttp

from launchbot import messages
from launchbot.bot import Bot
from launchbot.config import ROOT, Config, ConfigError, load_config
from launchbot.log import setup_logging
from launchbot.maker import VideoError, VideoMaker
from launchbot.project import STYLES
from launchbot.state import State
from launchbot.telegram import Telegram, TelegramError

log = logging.getLogger("run")
DEMO = ROOT / "samples" / "demo.json"


def acquire_lock(path):
    """Empêche deux bots de tourner en même temps : ils se disputeraient les messages Telegram."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+")
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def access_text(cfg: Config) -> str:
    if not cfg.public:
        return "owner only ([access] public = false)"
    return f"OPEN TO EVERYONE · {cfg.videos_per_hour} videos per person per hour · {cfg.queue_max} videos in line at most"


async def check(cfg: Config) -> int:
    """Vérifie chaque dépendance. N'envoie rien."""
    ok = True
    if not cfg.telegram_token:
        ok = False
        print("Telegram   : no token in .env (README.md, « Démarrer », says how to create the bot)")
    else:
        async with aiohttp.ClientSession() as session:
            try:
                print(f"Telegram   : @{await Telegram(session, cfg.telegram_token).me()}")
            except TelegramError as e:
                ok = False
                print(f"Telegram   : FAILED: {'token rejected: check TELEGRAM_BOT_TOKEN in .env' if e.bad_token else e}")
    if cfg.owner_ids:
        print(f"Owner      : {', '.join(str(owner) for owner in cfg.owner_ids)}")
    elif cfg.public:
        print("Owner      : not set (nobody gets the start message, /stats, or unlimited videos)")
    else:
        print("Owner      : NOT SET: start the bot, write to it, it tells you the line to put in .env")
    print(f"Access     : {access_text(cfg)}")
    try:
        from launchbot.video import render
        from launchbot.video.base import font

        render.find_ffmpeg()
        missing = [kind for kind in ("ui", "cond", "serif", "mono") if not hasattr(font(kind, 20), "getmetrics")]
        print("Maker      : ready" + (f" (fonts missing: {', '.join(missing)})" if missing else ""))
    except (SystemExit, OSError, ImportError) as e:
        ok = False
        print(f"Maker      : NOT AVAILABLE ({e or type(e).__name__})")
    print("\nAll set: run start.bat." if ok else "\nFix this before starting the bot.")
    return 0 if ok else 1


async def demo(cfg: Config, fmt: str) -> int:
    """Une vidéo d'exemple par style (le projet de samples/demo.json), dans data/videos."""
    spec = json.loads(DEMO.read_text(encoding="utf-8"))
    spec["logo"] = str(ROOT / spec["logo"])
    maker = VideoMaker(cfg)
    for style in STYLES:
        started = time.time()
        try:
            path = await maker.make({**spec, "style": style, "format": fmt}, f"demo-{style}-{fmt}")
        except VideoError as e:
            print(f"{style:8}: FAILED: {e}")
            return 1
        print(f"{style:8}: {path} ({time.time() - started:.0f} s, {path.stat().st_size / 1e6:.1f} MB)")
    return 0


async def poll_updates(bot: Bot, tg: Telegram, state: State):
    offset = state.update_offset
    while True:
        try:
            updates = await tg.updates(offset)
        except TelegramError as e:
            if e.bad_token:
                raise
            if e.conflict:
                log.warning("Another program is reading this bot's messages (same token used elsewhere?): retrying in 15 s")
            else:
                log.warning("Reading messages: %s", e)
            await asyncio.sleep(15 if e.conflict else 5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            try:
                await bot.handle(update)
            except TelegramError as e:
                log.warning("Answer not sent: %s", e)
            except Exception:
                log.exception("Message not processed")
            state.update_offset = offset


async def run_bot(cfg: Config) -> int:
    if not cfg.telegram_token:
        log.error("Cannot start: no TELEGRAM_BOT_TOKEN in .env")
        return 2
    state = State(cfg.state_path)
    async with aiohttp.ClientSession() as session:
        tg = Telegram(session, cfg.telegram_token)
        try:
            username = await tg.me()
            await tg.set_commands(messages.COMMANDS)
        except TelegramError as e:
            log.error("Cannot start: %s", "token rejected: check TELEGRAM_BOT_TOKEN in .env" if e.bad_token else e)
            return 2
        bot = Bot(cfg, state, tg)
        log.info("Launch video maker: /new in Telegram makes a presentation video")
        log.info("Access: %s", access_text(cfg))
        log.info("Telegram: @%s", username)
        if cfg.owner_ids:
            await bot.welcome()
        elif not cfg.public:
            log.warning("This bot has NO OWNER yet. Write to it: it tells you the line to put in .env")
        await poll_updates(bot, tg, state)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Presentation videos for launchpads and memecoin projects, made on Telegram")
    parser.add_argument("--config", default=None, help="path to the configuration file (default: config.toml)")
    parser.add_argument("--check", action="store_true", help="check the setup without sending anything")
    parser.add_argument("--demo", action="store_true", help="make one sample video per style, without Telegram")
    parser.add_argument("--format", default="landscape", choices=("landscape", "square", "portrait"), help="with --demo")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"Configuration error: {e}")
        return 2
    try:
        if args.check:
            return asyncio.run(check(cfg))
        if args.demo:
            return asyncio.run(demo(cfg, args.format))
        lock = acquire_lock(cfg.data_dir / "bot.lock")
        if lock is None:
            print("The bot is already running (another window is open): this one does nothing.")
            return 1
        setup_logging(cfg.log_path)
        try:
            return asyncio.run(run_bot(cfg))
        except Exception:
            log.exception("Stopped on an unexpected error")
            return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
