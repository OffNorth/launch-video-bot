"""
Ce qui sert aux quatre styles de vidéo : formats, polices, textes en images, logo, couleurs, mouvements.

Un style est une classe Film (voir plus bas) : elle reçoit la description du projet (spec, un dictionnaire déjà
nettoyé par project.py) et le format, et sait dessiner l'image de n'importe quel instant (frame(t)). render.py
enchaîne les images et les confie à ffmpeg.

Tout se dessine avec Pillow, sur une image RGBA de la taille finale. Les textes et le logo sont dessinés une fois
(cache) puis posés à chaque image : une image de 1920 x 1080 se fait en 20 à 60 ms.
"""

from __future__ import annotations

import math
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

FPS = 30
# Les trois formats : X (paysage), carré, TikTok / Reels (portrait)
SIZES = {"landscape": (1920, 1080), "square": (1080, 1080), "portrait": (1080, 1920)}

# Polices de Windows 11 (et d'Office pour Bodoni), la première présente sur le PC est prise
FONT_FILES = {
    "ui": ("SegUIVar.ttf", "segoeui.ttf", "arial.ttf"),  # Segoe UI Variable : graisses de Light à Bold
    "cond": ("bahnschrift.ttf", "impact.ttf", "arialbd.ttf"),  # Bahnschrift : large ou étroite, pour la typo choc
    "serif": ("BOD_R.TTF", "GARA.TTF", "georgia.ttf"),  # Bodoni : le teaser luxe
    "mono": ("consola.ttf", "cour.ttf"),
}
# Graisses nommées dans les polices variables (voir get_variation_names)
WEIGHTS = {
    "ui": {"light": "Light Display", "regular": "Regular Display", "semibold": "Semibold Display", "bold": "Bold Display"},
    "cond": {"regular": "Regular", "bold": "Bold", "boldcond": "Bold Condensed", "semicond": "SemiBold SemiCondensed",
             "light": "Light"},
}

INK = (16, 17, 20)
WHITE = (255, 255, 255)
NIGHT = (7, 8, 10)


# --- polices et textes ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def font(kind: str, size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    size = max(6, int(size))
    for name in FONT_FILES[kind]:
        try:
            face = ImageFont.truetype(name, size)
        except OSError:
            continue
        instance = WEIGHTS.get(kind, {}).get(weight)
        if instance:
            try:
                face.set_variation_by_name(instance)
            except (OSError, ValueError):
                pass  # police de secours sans variantes : graisse normale
        return face
    return ImageFont.load_default(size)


def text_width(text: str, kind: str, size: int, weight: str = "regular", tracking: float = 0.0) -> float:
    face = font(kind, size, weight)
    if not tracking:
        return face.getlength(text)
    return sum(face.getlength(ch) for ch in text) + tracking * size * max(0, len(text) - 1)


@lru_cache(maxsize=2048)
def text_img(text: str, kind: str, size: int, weight: str = "regular", color: tuple = WHITE, tracking: float = 0.0) -> Image.Image:
    """
    Le texte en image RGBA, rognée à sa largeur exacte et à la hauteur de la police (ascendante + descendante) :
    deux textes de même taille ont la même hauteur, ils s'alignent donc sur la même ligne de base.
    tracking : espace ajouté entre les lettres, en fraction de la taille.
    """
    face = font(kind, size, weight)
    ascent, descent = face.getmetrics()
    width = math.ceil(text_width(text, kind, size, weight, tracking)) + 4
    img = Image.new("RGBA", (max(1, width), ascent + descent + 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fill = color if len(color) == 4 else (*color, 255)
    if not tracking:
        draw.text((2, 2), text, font=face, fill=fill)
    else:
        x = 2.0
        for ch in text:
            draw.text((x, 2), ch, font=face, fill=fill)
            x += face.getlength(ch) + tracking * size
    return img


def fit_size(text: str, kind: str, weight: str, max_w: float, start: int, low: int = 12, tracking: float = 0.0) -> int:
    """La plus grande taille (≤ start) à laquelle le texte tient dans max_w pixels."""
    size = int(start)
    while size > low and text_width(text, kind, size, weight, tracking) > max_w:
        size = int(size * 0.94)
    return max(low, size)


def wrap(text: str, kind: str, size: int, weight: str, max_w: float, tracking: float = 0.0) -> list[str]:
    """Coupe le texte en lignes de max_w pixels au plus (un mot trop long reste seul sur sa ligne)."""
    lines: list[str] = []
    for word in text.split():
        if lines and text_width(lines[-1] + " " + word, kind, size, weight, tracking) <= max_w:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines or [""]


def fit_lines(text: str, kind: str, weight: str, max_w: float, start: int, max_lines: int, low: int = 12) -> tuple[int, list[str]]:
    """La plus grande taille (≤ start) à laquelle le texte tient en max_lines lignes de max_w pixels."""
    size = int(start)
    while True:
        lines = wrap(text, kind, size, weight, max_w)
        widest = max(text_width(line, kind, size, weight) for line in lines)
        if (len(lines) <= max_lines and widest <= max_w) or size <= low:
            return size, lines
        size = int(size * 0.94)


# --- couleurs ------------------------------------------------------------------------------------


def mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def luminance(c: tuple) -> float:
    r, g, b = (v / 255 for v in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def on_color(c: tuple) -> tuple:
    """La couleur de texte lisible sur un fond de couleur c : presque noir sur une couleur claire, blanc sinon."""
    return INK if luminance(c) > 0.55 else WHITE


def vivid(c: tuple, low: float = 0.38) -> tuple:
    """La couleur, éclaircie si elle est trop sombre pour se voir sur du noir (bleu marine, bordeaux…)."""
    lum = luminance(c)
    if lum >= low:
        return tuple(c[:3])
    return mix(c, WHITE, min(0.7, (low - lum) / max(0.01, 1 - lum) * 1.4))


def with_alpha(img: Image.Image, alpha: float) -> Image.Image:
    """Une copie de l'image RGBA dont l'opacité est multipliée par alpha (0 à 1)."""
    if alpha >= 0.999:
        return img
    out = img.copy()
    out.putalpha(out.getchannel("A").point(_alpha_lut(round(max(0.0, alpha) * 100))))
    return out


@lru_cache(maxsize=None)
def _alpha_lut(percent: int) -> list:
    return [v * percent // 100 for v in range(256)]


def tinted(img: Image.Image, color: tuple) -> Image.Image:
    """La même forme (canal alpha) remplie d'une couleur unie."""
    out = Image.new("RGBA", img.size, (*color[:3], 255))
    out.putalpha(img.getchannel("A"))
    return out


def glow(img: Image.Image, color: tuple, radius: float, strength: float = 1.0, pad: int | None = None) -> Image.Image:
    """Le halo flou de la forme, de la couleur donnée, avec une marge de pad pixels autour (centré sur l'image)."""
    pad = int(radius * 2.5) if pad is None else pad
    base = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    base.paste(tinted(img, color), (pad, pad))
    blurred = base.filter(ImageFilter.GaussianBlur(radius))
    if strength != 1.0:
        blurred.putalpha(blurred.getchannel("A").point(lambda v: min(255, int(v * strength))))
    return blurred


# --- poser des images ----------------------------------------------------------------------------


def put(canvas: Image.Image, sprite: Image.Image, x: float, y: float, alpha: float = 1.0, anchor: str = "mm") -> None:
    """
    Pose sprite (RGBA) sur canvas (RGBA). anchor : deux lettres, horizontale (l, m, r) puis verticale (t, m, b),
    comme Pillow. Ce qui dépasse du cadre est coupé.
    """
    if alpha <= 0.003 or sprite.width == 0 or sprite.height == 0:
        return
    ax, ay = anchor[0], anchor[1]
    left = x - (0 if ax == "l" else sprite.width / 2 if ax == "m" else sprite.width)
    top = y - (0 if ay == "t" else sprite.height / 2 if ay == "m" else sprite.height)
    left, top = int(round(left)), int(round(top))
    if left >= canvas.width or top >= canvas.height or left + sprite.width <= 0 or top + sprite.height <= 0:
        return
    sprite = with_alpha(sprite, alpha)
    # alpha_composite refuse une position négative : on coupe le morceau qui sort à gauche ou en haut
    cut_l, cut_t = max(0, -left), max(0, -top)
    if cut_l or cut_t:
        sprite = sprite.crop((cut_l, cut_t, sprite.width, sprite.height))
        left, top = left + cut_l, top + cut_t
    cut_r = max(0, left + sprite.width - canvas.width)
    cut_b = max(0, top + sprite.height - canvas.height)
    if cut_r or cut_b:
        sprite = sprite.crop((0, 0, sprite.width - cut_r, sprite.height - cut_b))
    canvas.alpha_composite(sprite, (left, top))


def scaled(img: Image.Image, factor: float) -> Image.Image:
    if abs(factor - 1.0) < 0.004:
        return img
    w, h = max(1, round(img.width * factor)), max(1, round(img.height * factor))
    return img.resize((w, h), Image.BILINEAR if factor < 1 else Image.BICUBIC)


def rounded_rect(size: tuple, radius: float, fill: tuple, outline: tuple | None = None, width: int = 0, scale: int = 3) -> Image.Image:
    """Un rectangle aux coins arrondis, dessiné 3 fois plus grand puis réduit (bords lisses)."""
    w, h = max(1, int(size[0])), max(1, int(size[1]))
    big = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * scale - 1, h * scale - 1), radius=radius * scale, fill=fill,
                                          outline=outline, width=width * scale)
    return big.resize((w, h), Image.LANCZOS)


def disc(diameter: float, fill: tuple, outline: tuple | None = None, width: float = 0, scale: int = 3) -> Image.Image:
    d = max(1, int(round(diameter)))
    big = Image.new("RGBA", (d * scale, d * scale), (0, 0, 0, 0))
    ImageDraw.Draw(big).ellipse((0, 0, d * scale - 1, d * scale - 1), fill=fill, outline=outline, width=int(width * scale))
    return big.resize((d, d), Image.LANCZOS)


def ring(diameter: float, color: tuple, width: float, sweep: float = 1.0, start_deg: float = -90.0, scale: int = 3) -> Image.Image:
    """Un cercle (ou un arc : sweep de 0 à 1 = la part du tour) de la couleur donnée."""
    d = max(1, int(round(diameter)))
    big = Image.new("RGBA", (d * scale, d * scale), (0, 0, 0, 0))
    if sweep > 0.001:
        ImageDraw.Draw(big).arc((width * scale / 2, width * scale / 2, d * scale - width * scale / 2, d * scale - width * scale / 2),
                                start_deg, start_deg + 360 * min(1.0, sweep), fill=(*color[:3], 255), width=max(1, int(width * scale)))
    return big.resize((d, d), Image.LANCZOS)


# --- le logo -------------------------------------------------------------------------------------


def open_logo(path: str) -> Image.Image | None:
    """L'image envoyée (photo de profil, logo), carrée (milieu gardé), en RGBA. None si absente ou illisible."""
    if not path:
        return None
    try:
        with Image.open(path) as raw:
            img = ImageOps.exif_transpose(raw).convert("RGBA")
    except (OSError, ValueError, SyntaxError):
        return None
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side))
    return img.resize((1024, 1024), Image.LANCZOS) if side > 1024 else img


def circle_logo(logo: Image.Image | None, diameter: float, color: tuple, letter: str) -> Image.Image:
    """
    Le logo dans un cercle (comme une photo de profil sur X ou Telegram). Sans logo : un rond de la couleur du
    projet avec sa première lettre.
    """
    d = max(2, int(round(diameter)))
    if logo is None:
        img = disc(d, (*color[:3], 255))
        size = int(d * 0.56)
        glyph = text_img(letter[:1].upper() or "?", "ui", size, "bold", on_color(color))
        put(img, glyph, d / 2, d / 2 - size * 0.06)
        return img
    face = logo.resize((d, d), Image.LANCZOS)
    mask = disc(d, (255, 255, 255, 255)).getchannel("A")
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    out.paste(face, (0, 0), ImageChops.multiply(mask, face.getchannel("A")))
    return out


def logo_colors(logo: Image.Image | None) -> tuple | None:
    """La couleur la plus présente et la plus vive du logo (pour proposer une couleur). None sans logo."""
    if logo is None:
        return None
    small = logo.convert("RGB").resize((48, 48))
    best, score = None, -1.0
    for count, rgb in small.getcolors(48 * 48) or []:
        lum = luminance(rgb)
        sat = (max(rgb) - min(rgb)) / 255
        s = count * (0.2 + sat) * (1.0 if 0.15 < lum < 0.9 else 0.2)
        if s > score:
            best, score = rgb, s
    return best


# --- mouvements ----------------------------------------------------------------------------------


def clamp(u: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if u < low else high if u > high else u


def lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def prog(t: float, start: float, length: float) -> float:
    """Avancement de 0 à 1 entre start et start + length."""
    return clamp((t - start) / length) if length > 0 else float(t >= start)


def ease_out(u: float) -> float:
    u = clamp(u)
    return 1 - (1 - u) ** 3


def ease_in(u: float) -> float:
    u = clamp(u)
    return u ** 3


def ease_in_out(u: float) -> float:
    u = clamp(u)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def ease_back(u: float, overshoot: float = 1.7) -> float:
    """Arrive un peu trop loin puis revient : l'effet « pop »."""
    u = clamp(u)
    return 1 + (overshoot + 1) * (u - 1) ** 3 + overshoot * (u - 1) ** 2


def window(t: float, start: float, end: float, fade_in: float = 0.3, fade_out: float = 0.3) -> float:
    """Opacité d'un élément visible entre start et end, avec un fondu à l'entrée et à la sortie."""
    if t < start or t > end:
        return 0.0
    return min(prog(t, start, fade_in) if fade_in else 1.0, 1 - prog(t, end - fade_out, fade_out) if fade_out else 1.0)


# --- fonds ---------------------------------------------------------------------------------------


def dot_grid(size: tuple, color: tuple, spacing: int, radius: float, alpha: int) -> Image.Image:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fill = (*color[:3], alpha)
    for y in range(spacing // 2, size[1], spacing):
        for x in range(spacing // 2, size[0], spacing):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)
    return img


def radial(size: tuple, center: tuple, radius: float, color: tuple, alpha: int) -> Image.Image:
    """Une lueur ronde et douce (couleur au centre, transparente au bord)."""
    small = (max(2, size[0] // 8), max(2, size[1] // 8))
    img = Image.new("L", small, 0)
    r = radius / 8
    cx, cy = center[0] / 8, center[1] / 8
    ImageDraw.Draw(img).ellipse((cx - r, cy - r, cx + r, cy + r), fill=alpha)
    img = img.filter(ImageFilter.GaussianBlur(r * 0.55)).resize(size, Image.BILINEAR)
    out = Image.new("RGBA", size, (*color[:3], 255))
    out.putalpha(img)
    return out


def vignette(size: tuple, strength: int = 170) -> Image.Image:
    """Les bords assombris, comme au cinéma."""
    small = Image.new("L", (64, 64), strength)
    ImageDraw.Draw(small).ellipse((-6, -10, 70, 74), fill=0)
    mask = small.filter(ImageFilter.GaussianBlur(9)).resize(size, Image.BILINEAR)
    out = Image.new("RGBA", size, (0, 0, 0, 255))
    out.putalpha(mask)
    return out


def grain(size: tuple, seed: int, amount: int = 18, coarse: int = 3) -> Image.Image:
    """
    Un voile de grain de film (bruit gris, semi-transparent), à poser par-dessus l'image. coarse : taille d'un grain
    en pixels. Le bruit se compresse très mal : un grain fin et fort fait passer une vidéo de 5 à 47 Mo (mesuré le
    19 octobre 2026), au-delà de ce que Telegram accepte d'un bot (50 Mo).
    """
    rng = random.Random(seed)
    w, h = max(1, size[0] // coarse), max(1, size[1] // coarse)
    noise = Image.frombytes("L", (w, h), rng.randbytes(w * h))
    noise = noise.resize(size, Image.BILINEAR)
    out = Image.new("RGBA", size, (128, 128, 128, 0))
    out.putalpha(noise.point(lambda v: amount * abs(v - 128) // 128))
    rgb = noise.convert("RGB")
    out = Image.merge("RGBA", (*rgb.split(), out.getchannel("A")))
    return out


# --- la classe commune ---------------------------------------------------------------------------


class Film:
    """
    Une vidéo. Les classes des styles en héritent et remplissent duration, accents, cover_t et draw(t).

    spec : name, ticker ("$ABC" ou ""), tagline, points (liste), color [r, g, b], logo (chemin ou ""),
           status ("live", "soon" ou ""), link (texte ou ""), format ("landscape", "square", "portrait").
    """

    STYLE = ""
    duration = 10.0

    def __init__(self, spec: dict):
        self.spec = spec
        self.W, self.H = SIZES.get(spec.get("format") or "landscape", SIZES["landscape"])
        self.portrait = self.H > self.W
        self.u = min(self.W, self.H) / 1080  # 1 unité = 1 pixel d'une vidéo de 1080 de côté
        self.color = tuple(spec.get("color") or (120, 220, 140))[:3]
        self.accent = vivid(self.color)
        self.name = str(spec.get("name") or "")
        self.ticker = str(spec.get("ticker") or "")
        self.tagline = str(spec.get("tagline") or "")
        self.points = [str(p) for p in spec.get("points") or []][:3]
        self.status = str(spec.get("status") or "")
        self.link = str(spec.get("link") or "")
        self.logo = open_logo(str(spec.get("logo") or ""))
        self.accents: list[float] = []  # instants des coupes (la musique y met un coup)
        self.cover_t = 0.0  # l'instant gardé comme image fixe (vignette)

    @property
    def status_text(self) -> str:
        return {"live": "LIVE NOW", "soon": "COMING SOON"}.get(self.status, "")

    def U(self, v: float) -> int:
        return int(round(v * self.u))

    def frame(self, t: float) -> Image.Image:
        return self.draw(min(max(t, 0.0), self.duration)).convert("RGB")

    def draw(self, t: float) -> Image.Image:  # à remplir par chaque style
        raise NotImplementedError

    def logo_disc(self, diameter: float) -> Image.Image:
        return _logo_disc(self, int(round(diameter)))


@lru_cache(maxsize=64)
def _logo_disc(film: Film, diameter: int) -> Image.Image:
    return circle_logo(film.logo, diameter, film.color, film.name)


def strip_stars(text: str) -> list[tuple[str, bool]]:
    """
    Les mots d'une phrase, et pour chacun s'il est mis en avant. Un mot entre étoiles (*anyone*, ou *plusieurs
    mots*) est mis en avant : écrit en gras, de la couleur du projet. Les étoiles ne sont pas affichées.
    """
    words, bold = [], False
    for raw in text.split():
        if not raw.strip("*"):
            continue  # une étoile seule (ou « ** ») : ni affichée, ni comptée
        start = raw.startswith("*")
        if start:
            bold = True
        end = raw.endswith("*") and (len(raw) > 1 or not start)
        word = raw.strip("*")
        if word:
            words.append((word, bold))
        if end:
            bold = False
    return words


def path_of(spec_path: str) -> Path:
    return Path(spec_path)
