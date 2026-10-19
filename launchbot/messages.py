"""
Les textes envoyés dans Telegram (HTML) et leurs boutons. Aucune logique ici : seulement de la mise en forme.

Tout est en anglais, comme les autres bots. Aucun texte ne donne un chemin de fichier, un nom de programme ou un
détail d'erreur (ça va dans le journal, pas dans la conversation).

Les données des boutons (callback_data) sont courtes :
    skip            passer la question en cours          c:<couleur> / c:logo   la couleur
    st:<style>      le style                              s:<live|soon|none>     le statut
    f:<format>      le format                             make, edit, sound, x   le résumé
    e:<champ>       modifier ce champ                     back                   revenir au résumé
    re:style / re:format / new                            après la vidéo
"""

from __future__ import annotations

import html

from .project import COLOR_EMOJI, COLORS, FORMATS, STATUSES, STEPS, STYLES, color_name

HELP = (
    "<b>Launch video maker</b>\n"
    "I make a short presentation video for your launchpad, token or project: you give me a name, a theme, a "
    "logo and a colour, I send back the video.\n\n"
    "Four styles: ⚫ <b>Product</b> (dark launch video), 💥 <b>Kinetic</b> (giant words on the beat), "
    "🎞 <b>Luxe</b> (slow teaser), 🪙 <b>Coins</b> (coin rain).\n"
    "Three formats: 16:9 for X, 1:1, 9:16 for TikTok.\n\n"
    "/new – start a new video\n"
    "/edit – change something in the current one\n"
    "/cancel – forget the current project\n"
    "/help – this message"
)
COMMANDS = (
    ("new", "Make a new video"),
    ("edit", "Change the current project"),
    ("cancel", "Forget the current project"),
    ("help", "How it works"),
)

STARTED = "▶️ <b>Launch video maker started</b>\n/new to make a video · /stats"
PRIVATE = "This is a private bot."
NO_PROJECT = "Tap /new to start a video."
CANCELLED = "Project forgotten. /new to start another one."
NAME_EMPTY = "I need a name I can write on the video (letters or numbers)."
TAGLINE_EMPTY = "I need one line I can write on the video (letters or numbers)."
TICKER_BAD = "A ticker is letters or numbers, like <code>$FROG</code>. Send it again, or tap Skip."
POINTS_EMPTY = "Send one point per line, or tap Skip."
COLOR_BAD = "I don't know that colour. Tap a button, or send a code like <code>#5CC46E</code>."
TAP_BUTTON = "Tap one of the buttons above."
LOGO_SAVED = "🖼 Logo saved."
LOGO_BAD = "⚠️ I could not open this picture. Send it again as a photo, or tap Skip."
LOGO_TOO_BIG = "This picture is too big for me (20 MB at most)."
LOGO_NOT_FETCHED = "⚠️ I could not fetch this picture from Telegram. Send it again."
SOUND_TOO_BIG = "This file is too big: Telegram lets a bot fetch 20 MB at most. Send a shorter one."
SOUND_NOT_FETCHED = "⚠️ I could not fetch this file from Telegram. Send it again."
NOT_USABLE = "Send a picture for the logo, or an audio file / a video for the sound."
ALREADY_MAKING = "Your previous video is still being made: wait for it, then ask for another one."
VIDEO_FAILED = "⚠️ The video could not be made. Try again in a moment."
VIDEO_NOT_SENT = "⚠️ The video is made but Telegram did not take it. Try again."
NOT_READY = "Some answers are missing: {}. /edit to fill them."
TOO_MANY_PICTURES = "That is a lot of files. Wait a few minutes before sending another one."

LABELS = {"name": "Name", "ticker": "Ticker", "tagline": "Theme", "points": "Key points", "logo": "Logo", "color": "Colour",
          "style": "Style", "status": "Status", "link": "Link", "format": "Format", "sound": "Sound"}

QUESTIONS = {
    "name": "What is the project called?\n<i>e.g. Froggy Pad</i>",
    "ticker": "Its ticker?\n<i>e.g. $FROG</i>",
    "tagline": ("One line that says what it is: the theme of the video.\n"
                "Put *stars* around a word to highlight it (or make it bold).\n"
                "<i>e.g. Launch a coin for *anyone* on Solana</i>"),
    "points": ("Up to 3 key points, one per line.\n"
               "<i>e.g.\nFair launch, no presale\nCreators earn 1% of every trade\nGraduates to PumpSwap</i>"),
    "logo": "Send the logo or profile picture (as a photo or as a file).\nNo logo? Tap Skip: I use the first letter of the name.",
    "color": "Main colour? Tap one, or send a code like <code>#5CC46E</code>.",
    "style": "Which style?\n" + "\n".join(f"{label} – {text}" for label, text in STYLES.values()),
    "status": "Is it live?",
    "link": "Link, handle or CA to show at the end?\n<i>e.g. froggypad.fun or @froggypad</i>",
    "format": "Which format?",
}


def question(key: str, editing: bool, logo_color: tuple | None = None) -> tuple[str, list[list[dict]]]:
    """La question pour ce champ, et ses boutons."""
    number = STEPS.index(key) + 1
    head = "✏️ " if editing else f"<b>{number}/{len(STEPS)}</b> · "
    buttons: list[list[dict]] = []
    if key == "color":
        names = list(COLORS)
        row: list[dict] = []
        for name in names:
            row.append(_button(f"{COLOR_EMOJI[name]} {name.capitalize()}", f"c:{name}"))
            if len(row) == 4:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        if logo_color:
            buttons.append([_button("🎨 From the logo", "c:logo")])
    elif key == "style":
        buttons = [[_button(label, f"st:{name}")] for name, (label, _) in STYLES.items()]
    elif key == "status":
        buttons = [[_button("🟢 Live now", "s:live"), _button("⏳ Coming soon", "s:soon")], [_button("Neither", "s:none")]]
    elif key == "format":
        buttons = [[_button(f"{ratio} {text}", f"f:{name}")] for name, (ratio, text) in FORMATS.items()]
    elif key in ("ticker", "points", "logo", "link"):
        buttons = [[_button("Skip ⏭", "skip")]]
    if editing:
        buttons.append([_button("⬅️ Back", "back")])
    return head + QUESTIONS[key], buttons


def _button(text: str, data: str) -> dict:
    return {"text": text, "callback_data": data}


def _e(text) -> str:
    return html.escape(str(text))


def sound_text(project: dict) -> str:
    music = project.get("music") or "beat"
    if music == "file" and project.get("sound"):
        start = float(project.get("sound_start") or 0)
        return f"your sound, from {int(start // 60)}:{int(start % 60):02d}"
    return "none" if music == "none" else "built-in beat"


def summary(project: dict) -> tuple[str, list[list[dict]]]:
    """Le résumé du projet, avec les boutons pour fabriquer, modifier ou annuler."""
    points = project.get("points") or []
    lines = [
        "<b>Your video</b>",
        f"Name: <b>{_e(project.get('name') or '–')}</b>",
        f"Ticker: {_e(project.get('ticker') or '–')}",
        f"Theme: {_e(project.get('tagline') or '–')}",
        "Key points: " + ("–" if not points else "\n" + "\n".join(f"  • {_e(p)}" for p in points)),
        f"Logo: {'yes' if project.get('logo') else 'none (first letter of the name)'}",
        f"Colour: {_e(color_name(project.get('color')))}",
        f"Style: {STYLES.get(project.get('style'), STYLES['product'])[0]}",
        f"Status: {STATUSES.get(project.get('status') or '', 'Neither')}",
        f"Link: {_e(project.get('link') or '–')}",
        f"Format: {' '.join(FORMATS.get(project.get('format'), FORMATS['landscape']))}",
        f"Sound: {sound_text(project)}",
        "",
        "<i>To use your own sound, send an audio file or a video (write where it starts in the caption, e.g. 1:20).</i>",
    ]
    music = project.get("music") or "beat"
    toggle = "🔇 No sound" if music != "none" else "🎵 Built-in beat"
    buttons = [[_button("🎬 Make the video", "make")],
               [_button("✏️ Edit", "edit"), _button(toggle, "sound")],
               [_button("✖️ Cancel", "x")]]
    return "\n".join(lines), buttons


def edit_menu() -> tuple[str, list[list[dict]]]:
    keys = list(STEPS)
    rows, row = [], []
    for key in keys:
        row.append(_button(LABELS[key], f"e:{key}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_button("⬅️ Back", "back")])
    return "What do you want to change?", rows


def making(project: dict, ahead: int) -> str:
    style = STYLES.get(project.get("style"), STYLES["product"])[0]
    text = f"🎬 Making <b>{_e(project.get('name'))}</b> in {style}, {FORMATS.get(project.get('format'), FORMATS['landscape'])[0]}…"
    if ahead > 0:
        text += f"\n{ahead} video{'s' if ahead > 1 else ''} before yours."
    return text + "\nIt takes about 30 seconds."


def video_caption(project: dict) -> str:
    style = STYLES.get(project.get("style"), STYLES["product"])[0]
    ratio = FORMATS.get(project.get("format"), FORMATS["landscape"])[0]
    return f"<b>{_e(project.get('name'))}</b> · {style} · {ratio}"


def video_buttons() -> list[list[dict]]:
    return [[_button("🎨 Other style", "re:style"), _button("📐 Other format", "re:format")],
            [_button("✏️ Edit", "edit"), _button("🆕 New project", "new")]]


def sound_saved(start: float) -> str:
    return (f"🎵 Sound saved: it starts at {int(start // 60)}:{int(start % 60):02d}. "
            "To start elsewhere, send the file again with the time in the caption (e.g. 1:20).")


def too_many_videos(limit: int, wait_s: float) -> str:
    minutes = max(1, round(wait_s / 60))
    return f"You can make {limit} videos per hour. Try again in about {minutes} minute{'s' if minutes > 1 else ''}."


def busy(waiting: int) -> str:
    return f"I am busy: {waiting} videos are waiting. Try again in a few minutes."


def no_owner(user_id: int) -> str:
    return (f"Your Telegram id is <code>{user_id}</code>.\n"
            f"To make this bot yours, put this line in its .env file and restart it:\n<code>TELEGRAM_OWNER_ID={user_id}</code>")


def stats(people: int, videos: int, making_now: int, public: bool) -> str:
    return (f"<b>Stats</b>\nVideos made: {videos}\nPeople served: {people}\nIn progress now: {making_now}\n"
            f"Access: {'everyone' if public else 'owner only'}")
