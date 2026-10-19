"""
Réglages : config.toml pour ce qui se règle à la main (accès, limites, format et musique par défaut), .env pour ce
qui ne se partage pas (token du bot Telegram, identifiant du propriétaire).

Ce bot a SON bot Telegram : deux programmes ne peuvent pas lire les messages d'un même bot en même temps.

Le propriétaire : si TELEGRAM_OWNER_ID est vide ici, on reprend celui de pnl-card-bot/.env, puis de
calls-trader-bot/.env (SIBLING_ENVS) : c'est la même personne qui les pilote. Le token, lui, n'est jamais repris.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID")
SIBLING_ENVS = (Path("..") / "pnl-card-bot" / ".env", Path("..") / "calls-trader-bot" / ".env")
FORMATS = ("landscape", "square", "portrait")
MUSICS = ("beat", "none")


class ConfigError(Exception):
    pass


@dataclass
class Config:
    public: bool = False  # tout le monde peut se servir du bot (sinon : le propriétaire seulement)
    videos_per_hour: int = 6  # vidéos qu'une même personne peut demander par heure (le propriétaire n'est pas limité)
    queue_max: int = 5  # vidéos en attente au-delà desquelles le bot demande de revenir plus tard
    default_format: str = "landscape"
    default_music: str = "beat"
    telegram_token: str = ""
    owner_ids: tuple[int, ...] = ()
    data_dir: Path = ROOT / "data"

    @property
    def state_path(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "bot.log"

    @property
    def videos_dir(self) -> Path:
        """Les vidéos fabriquées (les KEEP_VIDEOS dernières), avec leur vignette et leur description."""
        return self.data_dir / "videos"

    @property
    def logos_dir(self) -> Path:
        """Le logo envoyé par chaque personne (un seul par personne : le dernier)."""
        return self.data_dir / "logos"

    @property
    def sounds_dir(self) -> Path:
        """Le son envoyé par chaque personne (un seul par personne : le dernier)."""
        return self.data_dir / "sounds"


def read_env_file(path: Path) -> dict[str, str]:
    """Lit un fichier .env (lignes CLÉ=valeur). Un fichier absent ou illisible donne un dictionnaire vide."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _number(table: dict, key: str, default: float, low: float, high: float, section: str) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"[{section}] {key} must be a number")
    if not low <= value <= high:
        raise ConfigError(f"[{section}] {key} must be between {low:g} and {high:g}")
    return float(value)


def _owners(text: str) -> tuple[int, ...]:
    owners = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if not part.lstrip("-").isdigit():
            raise ConfigError("TELEGRAM_OWNER_ID must be your numeric Telegram id (write to the bot: it tells you)")
        owners.append(int(part))
    return tuple(dict.fromkeys(owners))


def parse_config(raw: dict, env: dict[str, str], root: Path = ROOT, siblings: list[dict[str, str]] | None = None) -> Config:
    """siblings : les .env des autres bots (seul TELEGRAM_OWNER_ID y est lu)."""
    access, video = raw.get("access") or {}, raw.get("video") or {}
    public = access.get("public", False)
    if not isinstance(public, bool):
        raise ConfigError("[access] public must be true or false")
    fmt = str(video.get("format", "landscape")).strip().lower()
    if fmt not in FORMATS:
        raise ConfigError('[video] format must be "landscape", "square" or "portrait"')
    music = str(video.get("music", "beat")).strip().lower()
    if music not in MUSICS:
        raise ConfigError('[video] music must be "beat" or "none"')
    owners = env.get("TELEGRAM_OWNER_ID", "").strip()
    for sibling in siblings or []:
        owners = owners or sibling.get("TELEGRAM_OWNER_ID", "").strip()
    return Config(
        public=public,
        videos_per_hour=int(_number(access, "videos_per_hour", 6, 1, 1000, "access")),
        queue_max=int(_number(access, "queue_max", 5, 1, 100, "access")),
        default_format=fmt,
        default_music=music,
        telegram_token=env.get("TELEGRAM_BOT_TOKEN", "").strip(),
        owner_ids=_owners(owners),
        data_dir=root / "data",
    )


def load_config(path: str | os.PathLike | None = None) -> Config:
    config_path = Path(path) if path else ROOT / "config.toml"
    if not config_path.exists():
        raise ConfigError(f"file not found: {config_path}")
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{config_path.name} cannot be read: {e}") from None
    root = config_path.resolve().parent
    env = read_env_file(root / ".env")
    for key in ENV_KEYS:
        if os.environ.get(key):  # une variable d'environnement passe devant le fichier .env
            env[key] = os.environ[key]
    return parse_config(raw, env, root, [read_env_file(root / sibling) for sibling in SIBLING_ENVS])
