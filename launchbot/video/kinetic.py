"""
Style « kinetic » : la typo choc (comme la vidéo de Shielded Shell vue sur X, voir RECHERCHE-X.md).

Des mots géants qui changent à chaque temps de la musique (128 BPM), en alternant noir / aplat de la couleur du
projet / mot en couleur sur noir ; le logo dessiné en points qui se rassemblent ; les points clés avec un grand
numéro au trait ; le ticker sur un aplat ; « LIVE NOW » ou « COMING SOON » ; à la fin le logo en points, le nom et
le lien tapé dans une petite fenêtre de terminal.

Chaque plan dure un nombre entier de temps (music.beat_s("kinetic")) : les coupes tombent sur la grosse caisse.
Environ 12 à 16 s.
"""

from __future__ import annotations

import random
from functools import lru_cache

from PIL import Image, ImageDraw

from . import music
from .base import (NIGHT, WHITE, Film, ease_in_out, ease_out, fit_lines, fit_size, font, luminance, mix, on_color, prog,
                   put, rounded_rect, scaled, strip_stars, text_img, text_width)

GRID = 30  # le logo en points : nombre de points sur son diamètre
MAX_WORD_SHOTS = 9  # au-delà, les mots de l'accroche sont groupés par deux ou trois
CODE_CHARS = "0123456789ABCDEF$#/<>=+"


class Kinetic(Film):
    STYLE = "kinetic"

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.beat = music.beat_s("kinetic")
        self.ink_on_color = on_color(self.color)
        shots: list[tuple[str, object, int, str]] = [("dots", None, 4, "dark")]
        # Un mot mis en avant (entre étoiles) est sur l'aplat de couleur ; les autres tournent entre les trois fonds,
        # sans jamais deux fois le même de suite
        variants, last = ("dark", "flash", "accent"), "dark"
        for n, (words, bold) in enumerate(self._word_groups()):
            variant = "flash" if bold and last != "flash" else next(
                v for v in variants[n % 3:] + variants[:n % 3] if v != last and not (bold and v == "dark"))
            shots.append(("word", words, 1, variant))
            last = variant
        shots.append(("name", None, 3, "dark"))
        for i in range(len(self.points)):
            shots.append(("point", i, 3, "flash" if i % 2 else "dark"))
        if self.ticker:
            shots.append(("ticker", None, 2, "flash"))
        if self.status_text:
            shots.append(("status", None, 2, "dark"))
        shots.append(("end", None, 8, "dark"))
        self.shots = []
        start = 0.0
        for kind, payload, beats, variant in shots:
            self.shots.append((start, start + beats * self.beat, kind, payload, variant))
            start += beats * self.beat
        self.duration = start
        self.accents = [s for s, _, kind, _, _ in self.shots[1:] if kind in ("name", "point", "ticker", "end")]
        self.cover_t = self.duration - 1.5
        self.dots = self._dot_targets()
        self.code = _code_texture(self.W, self.H * 2, self.U(22))

    # --- préparation -------------------------------------------------------------------------------

    def _word_groups(self) -> list[tuple[str, bool]]:
        """Les mots de l'accroche par plan : un mot par temps, les petits mots collés au suivant."""
        words = strip_stars(self.tagline)
        groups: list[tuple[list[str], bool]] = []
        for word, bold in words:
            if groups and (len(groups[-1][0][-1]) <= 2 or len(" ".join(groups[-1][0])) <= 3) and groups[-1][1] == bold:
                groups[-1][0].append(word)
            else:
                groups.append(([word], bold))
        while len(groups) > MAX_WORD_SHOTS:  # trop de plans : on colle deux à deux, du plus court au plus long
            i = min(range(len(groups) - 1), key=lambda k: len(" ".join(groups[k][0] + groups[k + 1][0])))
            groups[i] = (groups[i][0] + groups[i + 1][0], groups[i][1] or groups[i + 1][1])
            del groups[i + 1]
        return [(" ".join(g).upper(), bold) for g, bold in groups]

    def _dot_targets(self) -> list[tuple[float, float, float, tuple, float, float, float]]:
        """Les points du logo : (x, y relatifs au centre, en fraction du diamètre ; rayon relatif ; couleur ; départ x, y ; retard)."""
        logo = self.logo_disc(GRID * 8).resize((GRID, GRID), Image.BOX)
        rng = random.Random(7)
        dots = []
        for gy in range(GRID):
            for gx in range(GRID):
                r, g, b, a = logo.getpixel((gx, gy))
                if a < 90:
                    continue
                lum = luminance((r, g, b))
                size = 0.32 + 0.68 * min(1.0, 0.2 + lum * 1.1)
                color = mix((r, g, b), WHITE, 0.15) if lum > 0.12 else mix(self.accent, NIGHT, 0.55)
                dots.append(((gx + 0.5) / GRID - 0.5, (gy + 0.5) / GRID - 0.5, size, color,
                             rng.uniform(-0.9, 0.9), rng.uniform(-0.9, 0.9), rng.uniform(0.0, 0.5)))
        return dots

    # --- dessin --------------------------------------------------------------------------------------

    def draw(self, t: float) -> Image.Image:
        for start, end, kind, payload, variant in self.shots:
            if start <= t < end or (kind == "end" and t >= start):
                return self.shot(t, start, end, kind, payload, variant)
        return Image.new("RGBA", (self.W, self.H), (*NIGHT, 255))

    def background(self, variant: str, t: float) -> tuple[Image.Image, tuple]:
        """Le fond du plan et la couleur du texte dessus."""
        if variant == "flash":
            return Image.new("RGBA", (self.W, self.H), (*self.color, 255)), self.ink_on_color
        img = Image.new("RGBA", (self.W, self.H), (*NIGHT, 255))
        # Des colonnes de caractères qui défilent, à peine visibles (le « code » de la vidéo modèle)
        shift = int((t * self.U(60)) % self.H)
        img.alpha_composite(self.code.crop((0, shift, self.W, shift + self.H)))
        return img, (self.accent if variant == "accent" else WHITE)

    def shot(self, t: float, start: float, end: float, kind: str, payload, variant: str) -> Image.Image:
        img, ink = self.background(variant, t)
        local = t - start
        if kind == "dots":
            self.draw_dots(img, min(1.0, local / (self.beat * 3)), self.W / 2, self.H / 2, self.U(560 if self.portrait else 600))
        elif kind == "word":
            self.big_line(img, str(payload), ink, local)
        elif kind == "name":
            self.name_shot(img, ink, local)
        elif kind == "point":
            self.point_shot(img, int(payload), ink, local, variant)
        elif kind == "ticker":
            self.big_line(img, self.ticker.upper(), ink, local, jitter=True)
        elif kind == "status":
            on = local > self.beat * 0.5 or int(local * 30) % 4 < 2  # clignote à l'arrivée, comme un néon qui s'allume
            self.big_line(img, self.status_text, self.accent if on else (60, 60, 60), local, letters=True)
        elif kind == "end":
            self.end_shot(img, local)
        # Un éclair blanc au début de chaque plan, très court
        flash = 1 - prog(local, 0.0, 0.09)
        if flash > 0 and kind != "dots":
            put(img, Image.new("RGBA", (self.W, self.H), (255, 255, 255, int(70 * flash))), 0, 0, 1.0, "lt")
        return img

    def big_line(self, img: Image.Image, text: str, ink: tuple, local: float, jitter: bool = False, letters: bool = False) -> None:
        """Un texte géant au milieu : il arrive de la droite, puis se resserre doucement pendant le temps."""
        u = self.U
        max_w = self.W * 0.9
        size = min(fit_size(text, "cond", "bold", max_w, u(420)), int(self.H * 0.42))
        lines = [text]
        if size < u(150) and " " in text:  # trop long pour une ligne lisible : sur deux ou trois lignes
            size, lines = fit_lines(text, "cond", "bold", max_w, u(300), 3)
        come = ease_out(prog(local, 0.0, 0.12))
        factor = 1.06 - 0.06 * ease_out(prog(local, 0.0, self.beat))
        dx = u(80) * (1 - come)
        dy = 0.0
        if jitter:
            rng = random.Random(int(local * 30))
            dx += rng.uniform(-1, 1) * u(6)
            dy += rng.uniform(-1, 1) * u(6)
        step = size * 0.92
        top = self.H / 2 - step * (len(lines) - 1) / 2
        for row, line in enumerate(lines):
            shown = line
            if letters:  # les lettres arrivent une à une
                shown = line[: max(1, int(len(line) * prog(local, 0.0, self.beat * 0.6)) + 1)]
                sprite = text_img(shown, "cond", size, "bold", ink)
                full = text_width(line, "cond", size, "bold")
                put(img, scaled(sprite, factor), self.W / 2 - full * factor / 2 + dx, top + row * step + dy, come, "lm")
                continue
            put(img, scaled(text_img(shown, "cond", size, "bold", ink), factor), self.W / 2 + dx, top + row * step + dy, come)

    def name_shot(self, img: Image.Image, ink: tuple, local: float) -> None:
        u = self.U
        text = self.name.upper()
        size = min(fit_size(text, "cond", "bold", self.W * 0.88, u(380)), int(self.H * 0.4))
        lines = [text]
        if size < u(140) and " " in text:
            size, lines = fit_lines(text, "cond", "bold", self.W * 0.88, u(300), 2)
        step = size * 0.92
        top = self.H / 2 - step * (len(lines) - 1) / 2
        count = sum(len(line) for line in lines)
        shown_total = int(count * prog(local, 0.0, self.beat * 1.5)) + 1
        for row, line in enumerate(lines):
            shown = line[: max(0, shown_total)]
            shown_total -= len(line)
            if not shown:
                continue
            full = text_width(line, "cond", size, "bold")
            put(img, text_img(shown, "cond", size, "bold", ink), self.W / 2 - full / 2, top + row * step, 1.0, "lm")
        # Le logo, petit, au-dessus (ou à gauche en paysage), quand le nom est écrit
        logo_in = ease_out(prog(local, self.beat * 1.5, 0.3))
        if logo_in > 0:
            d = u(150)
            put(img, self.logo_disc(d), self.W / 2, top - size * 0.5 - d * 0.65 + u(20) * (1 - logo_in), logo_in)

    def point_shot(self, img: Image.Image, i: int, ink: tuple, local: float, variant: str) -> None:
        u = self.U
        come = ease_out(prog(local, 0.0, 0.15))
        number = _outline(f"{i + 1:02d}", int(u(520 if not self.portrait else 440)), ink if variant == "flash" else self.accent,
                          max(3, u(5)))
        text = self.points[i].upper()
        if self.portrait or self.W == self.H:  # empilés : côte à côte, le texte serait trop petit
            put(img, number, self.W / 2, self.H * 0.3 - u(60) * (1 - come), come * 0.9)
            size, lines = fit_lines(text, "cond", "bold", self.W * 0.88, u(150), 4)
            y0 = self.H * 0.58
            anchor, x = "mm", self.W / 2
        else:
            put(img, number, self.W * 0.06 - u(60) * (1 - come), self.H / 2, come * 0.9, "lm")
            x = self.W * 0.06 + number.width + u(40)
            size, lines = fit_lines(text, "cond", "bold", self.W * 0.94 - x, u(170), 3)
            y0 = self.H / 2 - size * 0.95 * (len(lines) - 1) / 2
            anchor = "lm"
        for row, line in enumerate(lines):
            rise = ease_out(prog(local, 0.06 + row * 0.07, 0.18))
            put(img, text_img(line, "cond", size, "bold", ink), x + u(40) * (1 - rise), y0 + row * size * 0.95, rise, anchor)

    def draw_dots(self, img: Image.Image, u_: float, cx: float, cy: float, diameter: float) -> None:
        """Le logo en points ; u_ = 0 : points éparpillés sur tout l'écran, 1 : logo en place."""
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        cell = diameter / GRID
        for x, y, size, color, sx, sy, delay in self.dots:
            p = ease_in_out(prog(u_, delay * 0.6, 0.7))
            px = (sx * self.W / 2 + cx) * (1 - p) + (cx + x * diameter) * p
            py = (sy * self.H / 2 + cy) * (1 - p) + (cy + y * diameter) * p
            r = cell * 0.46 * size * (0.5 + 0.5 * p)
            draw.ellipse((px - r, py - r, px + r, py + r), fill=(*color, int(255 * min(1.0, 0.3 + p))))
        img.alpha_composite(layer)

    def end_shot(self, img: Image.Image, local: float) -> None:
        u = self.U
        d = u(330 if self.portrait else 300)
        name_size = fit_size(self.name.upper(), "cond", "bold", self.W * 0.8, u(150))
        typed_text = "> " + (self.link or self.ticker or self.name)
        mono = u(34)
        box_w = text_width(typed_text + "_", "mono", mono) + u(60)
        total = d + u(40) + name_size + u(50) + mono * 2.2
        top = self.H / 2 - total / 2
        self.draw_dots(img, 0.6 + 0.4 * prog(local, 0.0, self.beat * 2), self.W / 2, top + d / 2, d)
        y = top + d + u(40) + name_size * 0.5
        rise = ease_out(prog(local, self.beat * 0.5, 0.3))
        put(img, text_img(self.name.upper(), "cond", name_size, "bold", WHITE), self.W / 2, y + u(30) * (1 - rise), rise)
        y += name_size * 0.5 + u(50) + mono * 1.1
        box_in = ease_out(prog(local, self.beat * 1.2, 0.3))
        box = rounded_rect((box_w, mono * 2.2), u(10), (*NIGHT, 230), (*self.accent, 255), max(1, u(2)))
        put(img, box, self.W / 2, y, box_in)
        typed = typed_text[: int(len(typed_text) * prog(local, self.beat * 1.6, self.beat * 2.5))]
        cursor = "_" if int(local * 3) % 2 == 0 else " "
        put(img, text_img(typed + cursor, "mono", mono, "regular", self.accent), self.W / 2 - box_w / 2 + u(30), y, box_in, "lm")
        if self.status_text:
            put(img, text_img(self.status_text, "mono", u(24), "regular", (150, 154, 162), 0.2), self.W / 2, y + mono * 1.1 + u(40),
                ease_out(prog(local, self.beat * 3, 0.4)))


@lru_cache(maxsize=4)
def _outline(text: str, size: int, color: tuple, width: int) -> Image.Image:
    """Un texte au trait seulement (le grand numéro des points clés)."""
    face = font("cond", size, "bold")
    ascent, descent = face.getmetrics()
    w = int(face.getlength(text)) + 4 * width
    img = Image.new("RGBA", (w, ascent + descent + 4 * width), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2 * width, 2 * width), text, font=face, fill=(0, 0, 0, 0), stroke_width=width,
                             stroke_fill=(*color[:3], 255))
    return img.crop(img.getbbox() or (0, 0, 1, 1))


@lru_cache(maxsize=2)
def _code_texture(w: int, h: int, size: int) -> Image.Image:
    """Des colonnes de caractères, très pâles, deux écrans de haut (le fond défile dedans)."""
    rng = random.Random(3)
    img = Image.new("RGBA", (w, int(h)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    face = font("mono", size)
    step_x, step_y = int(size * 1.6), int(size * 1.3)
    for x in range(0, w, step_x):
        if rng.random() < 0.45:
            continue
        for y in range(0, int(h), step_y):
            if rng.random() < 0.35:
                draw.text((x, y), rng.choice(CODE_CHARS), font=face, fill=(255, 255, 255, rng.choice((10, 16, 24))))
    return img


