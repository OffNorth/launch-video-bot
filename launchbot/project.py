"""
Le projet dont on fait la vidéo : ses champs, les questions posées pour les remplir, et le nettoyage de ce que la
personne tape. Aucune dépendance au reste du bot : les tests s'en servent directement.

Un projet est un simple dictionnaire (il est gardé dans data/state.json entre deux lancements) :
    name      le nom (obligatoire, 28 caractères)
    ticker    « $FROG » (facultatif, 10 lettres ou chiffres)
    tagline   la phrase d'accroche, le « thème » (obligatoire, 90 caractères ; *mot* = mis en avant)
    points    jusqu'à 3 points clés (facultatif, 48 caractères chacun)
    logo      le nom du fichier du logo dans data/logos ("" : la première lettre du nom)
    color     [r, g, b]
    style     "product", "kinetic", "luxe" ou "coins"
    status    "live", "soon" ou ""
    link      le lien, le compte ou le CA montré à la fin (facultatif, 44 caractères)
    format    "landscape", "square" ou "portrait"
    music     "beat" (la musique du style), "none", ou "file" (le son envoyé : sound, sound_start)
Le bot y ajoute ses propres clés (step : la question en cours ; editing : revenir au résumé après la réponse).
"""

from __future__ import annotations

import re
import unicodedata

NAME_MAX, TICKER_MAX, TAGLINE_MAX, POINT_MAX, POINTS_MAX, LINK_MAX = 28, 10, 90, 48, 3, 44

STYLES = {
    "product": ("⚫ Product", "dark and clean, like a launchpad launch video"),
    "kinetic": ("💥 Kinetic", "giant words cut on the beat"),
    "luxe": ("🎞 Luxe", "slow dark teaser, metal logo"),
    "coins": ("🪙 Coins", "coins with your logo raining down, bright"),
}
FORMATS = {
    "landscape": ("16:9", "for X"),
    "square": ("1:1", "everywhere"),
    "portrait": ("9:16", "for TikTok / Reels"),
}
STATUSES = {"live": "Live now", "soon": "Coming soon", "": "Neither"}
# Les couleurs proposées en boutons (le nom est aussi ce qu'on peut taper)
COLORS = {
    "green": (34, 197, 94), "mint": (62, 207, 160), "lime": (190, 242, 60), "gold": (226, 182, 92),
    "orange": (249, 140, 40), "red": (239, 68, 68), "pink": (244, 114, 182), "purple": (150, 110, 255),
    "blue": (59, 130, 246), "cyan": (34, 211, 238), "white": (236, 236, 240),
}
COLOR_EMOJI = {"green": "🟢", "mint": "🍃", "lime": "🍋", "gold": "🟡", "orange": "🟠", "red": "🔴", "pink": "🩷",
               "purple": "🟣", "blue": "🔵", "cyan": "🩵", "white": "⚪"}

# Les questions, dans l'ordre. optional : un bouton « Skip » est proposé.
STEPS = ("name", "ticker", "tagline", "points", "logo", "color", "style", "status", "link", "format")
OPTIONAL = {"ticker", "points", "logo", "link"}
REQUIRED = ("name", "tagline")


def new_project(default_format: str = "landscape", default_music: str = "beat") -> dict:
    return {"name": "", "ticker": "", "tagline": "", "points": [], "logo": "", "color": list(COLORS["green"]),
            "style": "product", "status": "", "link": "", "format": default_format, "music": default_music,
            "sound": "", "sound_start": 0.0, "step": STEPS[0], "editing": False}


def missing(project: dict) -> list[str]:
    return [key for key in REQUIRED if not project.get(key)]


def next_step(key: str) -> str | None:
    """La question après celle-ci (None : c'était la dernière)."""
    i = STEPS.index(key) if key in STEPS else -1
    return STEPS[i + 1] if i + 1 < len(STEPS) else None


# --- nettoyage de ce qui est tapé -------------------------------------------------------------------


def drawable(text: str) -> str:
    """
    Le texte sans ce que les polices de la vidéo ne savent pas dessiner : emojis et symboles (ils sortiraient en
    carrés vides), caractères de contrôle. Les espaces sont ramenés à un seul.
    """
    kept = []
    for ch in str(text):
        if ord(ch) > 0xFFFF or ch in "\ufe0e\ufe0f" or unicodedata.category(ch) in ("So", "Cs", "Co", "Cn", "Cc", "Cf"):
            kept.append(" " if ch in "\n\t" else "")
            continue
        kept.append(ch)
    return " ".join("".join(kept).split())


def clean_line(text: str, limit: int) -> str:
    return drawable(text)[:limit].strip()


def clean_ticker(text: str) -> str:
    """« frog », « $FROG », « $ frog » → « $FROG ». "" si rien d'utilisable."""
    letters = re.sub(r"[^A-Za-z0-9]", "", drawable(text))[:TICKER_MAX].upper()
    return "$" + letters if letters else ""


def clean_tagline(text: str) -> str:
    """L'accroche, avec ses étoiles (une étoile seule est gardée telle quelle : strip_stars la traite)."""
    return clean_line(text, TAGLINE_MAX)


def parse_points(text: str) -> list[str]:
    """Les points clés : un par ligne (ou séparés par « ; » ou « | »), sans les puces ni les numéros tapés devant."""
    parts = re.split(r"[\n;|]+", str(text))
    points = []
    for part in parts:
        part = re.sub(r"^\s*(?:[-•*·>]+|\d+[.)]|[✅✔️➡️👉]+)\s*", "", part)
        part = clean_line(part, POINT_MAX)
        if part:
            points.append(part)
    return points[:POINTS_MAX]


def parse_color(text: str) -> tuple | None:
    """Une couleur tapée : un nom de la liste (« gold »), ou un code « #5CC46E » / « 5cc46e » / « #5c6 »."""
    value = str(text).strip().lower().lstrip("#")
    if value in COLORS:
        return COLORS[value]
    if re.fullmatch(r"[0-9a-f]{3}", value):
        value = "".join(ch * 2 for ch in value)
    if re.fullmatch(r"[0-9a-f]{6}", value):
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    return None


def parse_start(text: str) -> float | None:
    """Le début du son, écrit « 1:20 », « 80 », « 80s » ou « 1m20 ». None si ce n'en est pas un."""
    value = str(text).strip().lower().replace(" ", "")
    match = re.fullmatch(r"(\d{1,3}):(\d{1,2}(?:\.\d+)?)", value) or re.fullmatch(r"(\d{1,3})m(\d{1,2}(?:\.\d+)?)?s?", value)
    if match:
        return int(match.group(1)) * 60 + float(match.group(2) or 0)
    match = re.fullmatch(r"(\d{1,4}(?:\.\d+)?)s?", value)
    return float(match.group(1)) if match else None


def with_stars(text: str, entities: list | None) -> str:
    """
    Le texte d'un message où les mots mis en GRAS dans Telegram deviennent *mots* (même sens que les étoiles).
    Telegram compte les positions en unités UTF-16 : on travaille donc sur le texte encodé ainsi.
    """
    bold = [e for e in entities or [] if isinstance(e, dict) and e.get("type") == "bold"]
    if not bold:
        return text
    raw = text.encode("utf-16-le")
    out, last = [], 0
    for entity in sorted(bold, key=lambda e: int(e.get("offset", 0))):
        start, length = int(entity.get("offset", 0)) * 2, int(entity.get("length", 0)) * 2
        if start < last or length <= 0:
            continue
        out.append(raw[last:start].decode("utf-16-le", "ignore"))
        out.append("*" + raw[start:start + length].decode("utf-16-le", "ignore").strip() + "*")
        last = start + length
    out.append(raw[last:].decode("utf-16-le", "ignore"))
    return "".join(out)


def spec_of(project: dict, logo_path: str = "", sound_path: str = "") -> dict:
    """La description donnée au fabricant de vidéo (render.py)."""
    music = project.get("music") or "beat"
    if music == "file" and not sound_path:
        music = "beat"
    return {
        "style": project.get("style") if project.get("style") in STYLES else "product",
        "format": project.get("format") if project.get("format") in FORMATS else "landscape",
        "name": project.get("name") or "",
        "ticker": project.get("ticker") or "",
        "tagline": project.get("tagline") or "",
        "points": list(project.get("points") or [])[:POINTS_MAX],
        "color": list(project.get("color") or COLORS["green"])[:3],
        "logo": logo_path,
        "status": project.get("status") if project.get("status") in STATUSES else "",
        "link": project.get("link") or "",
        "music": music,
        "music_file": sound_path if music == "file" else "",
        "music_start": float(project.get("sound_start") or 0),
    }


def color_name(color) -> str:
    """Le nom de la couleur si c'est une des couleurs proposées, sinon son code."""
    rgb = tuple(color or ())[:3]
    for name, value in COLORS.items():
        if value == rgb:
            return name
    return "#" + "".join(f"{v:02X}" for v in rgb) if len(rgb) == 3 else "?"
