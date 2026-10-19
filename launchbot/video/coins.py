"""
Style « coins » : la pluie de pièces (comme le teaser de Smart Pocket vu sur X, voir RECHERCHE-X.md), joyeux et clair.

1. des pièces frappées du logo tombent en tournant, à trois profondeurs (les lointaines floues et pâles) ; une
   grande pièce monte du bas, tourne et s'arrête de face au milieu ;
2. elle se range (à gauche en paysage, en haut sinon), le nom arrive, puis le ticker dans une pastille ;
3. les points clés en étiquettes blanches, une par une (avec un « ding ») ;
4. la fin : les pièces jaillissent, puis « COMING SOON » ou « LIVE NOW » en grand, le lien, une petite pièce qui tourne.
Fond clair teinté de la couleur du projet. Environ 10 à 13 s.
"""

from __future__ import annotations

import math
import random
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from .base import (INK, WHITE, Film, disc, ease_back, ease_in_out, ease_out, fit_lines, fit_size, luminance, mix, on_color,
                   prog, put, radial, rounded_rect, scaled, text_img, text_width)

SPIN_FRAMES = 32  # images d'un demi-tour de pièce, calculées une fois
RAIN_S = 2.7
TITLE_S = 2.6
CHIP_S = 0.65
END_S = 3.4
# Les trois profondeurs de la pluie : (taille de la pièce en unités, flou, opacité, nombre de pièces)
LAYERS = ((70, 2.2, 0.55, 16), (130, 0.0, 0.95, 12), (230, 4.0, 0.9, 6))


class Coins(Film):
    STYLE = "coins"

    def __init__(self, spec: dict):
        super().__init__(spec)
        u = self.U
        self.ink = INK
        # Sur fond clair, une couleur claire (jaune, menthe) se lit mal : on la fonce pour le texte
        self.deep = mix(self.color, INK, 0.45) if luminance(self.color) > 0.5 else tuple(self.color)
        self.t_title = RAIN_S
        self.t_chips = self.t_title + TITLE_S
        self.t_end = self.t_chips + CHIP_S * len(self.points) + (0.6 if self.points else 0)
        self.duration = self.t_end + END_S
        self.accents = [self.t_title, self.t_end]
        self.dings = [1.0, 2.2, self.t_title + 0.6, *(self.t_chips + i * CHIP_S for i in range(len(self.points))), self.t_end + 0.5]
        self.cover_t = self.duration - 0.8

        tint = mix(self.color, WHITE, 0.86)
        self.bg = Image.new("RGBA", (self.W, self.H), (*tint, 255))
        self.bg.alpha_composite(radial((self.W, self.H), (self.W / 2, self.H / 2), max(self.W, self.H) * 0.55, WHITE, 230))
        self.layers = [_spin_frames(self, u(size), blur * self.u) for size, blur, _, _ in LAYERS]
        rng = random.Random(11)
        self.rain = []  # (profondeur, x, phase de chute, vitesse, phase de rotation, vitesse de rotation)
        for depth, (_, _, _, count) in enumerate(LAYERS):
            for _ in range(count):
                self.rain.append((depth, rng.uniform(-0.05, 1.05), rng.random(), rng.uniform(0.28, 0.5) * (0.7 + 0.25 * depth),
                                  rng.random(), rng.uniform(0.6, 1.6) * rng.choice((-1, 1))))
        self.d_hero = u(560 if self.portrait else 520)
        self.hero_face = _coin_face(self, self.d_hero)
        self.burst = [(rng.uniform(0, 2 * math.pi), rng.uniform(0.6, 1.4), rng.choice((0, 1)), rng.random()) for _ in range(18)]

    # --- dessin --------------------------------------------------------------------------------------

    def draw(self, t: float) -> Image.Image:
        img = self.bg.copy()
        rain = 1.0 if t < self.t_title else 0.45 if t < self.t_end else 0.25
        if self.t_title <= t < self.t_title + 0.6:
            rain = 1.0 - 0.55 * prog(t, self.t_title, 0.6)
        self.draw_rain(img, t, rain, layers=(0, 1))
        if t < self.t_end:
            self.hero(img, t)
            if t >= self.t_title:
                self.title(img, t)
            if t >= self.t_chips:
                self.chips(img, t)
        else:
            self.end(img, t - self.t_end)
        self.draw_rain(img, t, rain, layers=(2,))  # les pièces proches passent devant tout
        return img

    def draw_rain(self, img: Image.Image, t: float, alpha: float, layers: tuple) -> None:
        for depth, x, phase, speed, spin0, spin_speed in self.rain:
            if depth not in layers:
                continue
            frames = self.layers[depth]
            size = frames[0].height
            span = self.H + 2 * size
            y = ((phase + speed * t * (self.H / 1080) * 1080 / span) % 1.0) * span - size
            px = x * self.W + math.sin(t * 1.3 + phase * 6) * size * 0.25
            frame = frames[int(((spin0 + spin_speed * t) % 1.0) * len(frames)) % len(frames)]
            put(img, frame, px, y, alpha * LAYERS[depth][2])

    def hero_place(self, t: float) -> tuple[float, float, float]:
        """Où est la grande pièce, et sa taille (en fraction de d_hero)."""
        u = self.U
        arrive = ease_back(prog(t, 0.9, 1.3), 1.2)
        y = self.H + self.d_hero / 2 + (self.H / 2 - self.H - self.d_hero / 2) * arrive
        x, scale = self.W / 2, 1.0
        settle = ease_in_out(prog(t, self.t_title, 0.7))
        if settle > 0:
            if self.portrait or self.W == self.H:
                target_x, target_y, target_s = self.W / 2, self.H * (0.31 if self.portrait else 0.3), 0.62 if self.portrait else 0.5
            else:
                target_x, target_y, target_s = self.W * 0.28, self.H / 2 - u(10), 0.78
            x, y, scale = x + (target_x - x) * settle, y + (target_y - y) * settle, 1 + (target_s - 1) * settle
        return x, y, scale

    def hero(self, img: Image.Image, t: float) -> None:
        if t < 0.9:
            return
        x, y, scale = self.hero_place(t)
        # Elle tourne vite en montant, ralentit, et s'arrête pile de face à 2,2 s ; ensuite elle oscille à peine
        turns = 3.0 * (1 - ease_out(prog(t, 0.9, 1.3)))
        angle = turns * math.pi + (0.18 * math.sin((t - 2.2) * 2.2) if t > 2.2 else 0.0)
        d = self.d_hero * scale
        put(img, _shadow(int(d)), x, y + d * 0.52, 0.5 * min(1.0, prog(t, 1.4, 0.6)))
        put(img, _turned(self.hero_face, angle, self.color, int(d)), x, y)

    def title(self, img: Image.Image, t: float) -> None:
        u = self.U
        x, y, scale = self.hero_place(self.t_title + 1.0)
        stacked = self.portrait or self.W == self.H
        if stacked:
            cx, top, max_w, anchor = self.W / 2, y + self.d_hero * scale / 2 + u(70), self.W * 0.86, "mm"
        else:
            cx, top, max_w, anchor = self.W * 0.52, self.H / 2 - u(120), self.W * 0.44, "lm"
        size, lines = fit_lines(self.name, "ui", "bold", max_w, u(130 if stacked else 120), 2)
        for row, line in enumerate(lines):
            pop = ease_back(prog(t, self.t_title + 0.35 + row * 0.12, 0.45))
            sprite = scaled(text_img(line, "ui", size, "bold", self.ink), 0.6 + 0.4 * pop)
            put(img, sprite, cx, top + row * size * 1.05, min(1.0, pop * 1.5), anchor)
        y_pill = top + len(lines) * size * 1.05 + u(10)
        label = self.ticker or self.status_text
        if label:
            pop = ease_back(prog(t, self.t_title + 0.6, 0.45))
            pill = _pill(label, u(46), self.color, on_color(self.color))
            put(img, scaled(pill, 0.5 + 0.5 * pop), cx + (0 if stacked else pill.width / 2 * (0.5 + 0.5 * pop)), y_pill + pill.height / 2,
                min(1.0, pop * 1.5))
        self.chip_top = y_pill + u(130)
        self.chip_x, self.chip_anchor, self.chip_w = cx, anchor, max_w

    def chips(self, img: Image.Image, t: float) -> None:
        u = self.U
        for i, text in enumerate(self.points):
            pop = ease_back(prog(t, self.t_chips + i * CHIP_S, 0.4))
            if pop <= 0:
                continue
            chip = _chip(text, u(40), self.deep, int(self.chip_w))
            x = self.chip_x + (0 if self.chip_anchor == "mm" else chip.width / 2)
            put(img, scaled(chip, 0.6 + 0.4 * pop), x, self.chip_top + i * u(100), min(1.0, pop * 1.5))

    def end(self, img: Image.Image, local: float) -> None:
        u = self.U
        # Les pièces jaillissent du milieu
        frames = self.layers[1]
        for angle, speed, depth, spin in self.burst:
            p = ease_out(prog(local, 0.0, 1.2))
            dist = p * speed * max(self.W, self.H) * 0.55
            fx = self.W / 2 + math.cos(angle) * dist
            fy = self.H / 2 + math.sin(angle) * dist + p * p * u(200)
            frame = frames[int((spin + local * 1.5) * len(frames)) % len(frames)]
            put(img, frame, fx, fy, 1 - prog(local, 0.8, 0.6))
        come = ease_back(prog(local, 0.35, 0.5))
        d = u(170)
        top = self.H / 2 - u(190 if not self.portrait else 260)
        put(img, _turned(_coin_face(self, d), (local * 2.2) % math.pi, self.color, d), self.W / 2, top, min(1.0, come * 1.5))
        big = self.status_text or self.ticker or self.name
        size = fit_size(big, "ui", "bold", self.W * 0.86, u(170))
        put(img, scaled(text_img(big, "ui", size, "bold", self.deep), 0.7 + 0.3 * come), self.W / 2, top + d / 2 + u(40) + size * 0.6,
            min(1.0, come * 1.5))
        y = top + d / 2 + u(70) + size * 1.25
        under = self.name if big != self.name else ""
        if under:
            rise = ease_out(prog(local, 0.6, 0.4))
            put(img, text_img(under, "ui", u(54), "semibold", self.ink), self.W / 2, y + u(20) * (1 - rise), rise)
            y += u(80)
        if self.link:
            rise = ease_out(prog(local, 0.8, 0.4))
            put(img, _pill(self.link, u(36), WHITE, self.ink, outline=self.deep), self.W / 2, y + u(30) + u(20) * (1 - rise), rise)


# --- la pièce ------------------------------------------------------------------------------------------


def _rim_colors(color: tuple) -> tuple:
    return mix(color, INK, 0.35), mix(color, WHITE, 0.45), mix(color, INK, 0.55)


@lru_cache(maxsize=16)
def _coin_face(film: Film, d: int) -> Image.Image:
    """Une pièce vue de face : bord épais en relief de la couleur du projet, logo au centre, reflet en haut à gauche."""
    d = max(8, d)
    dark, light, edge = _rim_colors(film.color)
    face = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    # Le bord : dégradé du clair (haut gauche) au sombre (bas droite)
    gradient = Image.linear_gradient("L").rotate(45, expand=False).resize((d, d))
    rim = Image.merge("RGB", [gradient.point(lambda v, i=i: mix(light, dark, v / 255)[i]) for i in range(3)])
    face.paste(rim, (0, 0), disc(d, (255, 255, 255, 255)).getchannel("A"))
    inner = int(d * 0.84)
    put(face, disc(inner, (*film.color, 255)), d / 2, d / 2)
    put(face, film.logo_disc(int(d * 0.72)), d / 2, d / 2)
    # Le filet clair du bord intérieur, et le reflet
    ring = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((d * 0.08, d * 0.08, d * 0.92, d * 0.92), outline=(*light, 200), width=max(1, d // 90))
    face.alpha_composite(ring)
    shine = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    ImageDraw.Draw(shine).ellipse((d * 0.14, d * 0.08, d * 0.62, d * 0.4), fill=(255, 255, 255, 70))
    face.alpha_composite(shine.filter(ImageFilter.GaussianBlur(d * 0.05)))
    return face


def _turned(face: Image.Image, angle: float, color: tuple, d: int) -> Image.Image:
    """La pièce tournée d'un angle (radians) autour de son axe vertical : face rétrécie, tranche visible à côté."""
    d = max(8, d)
    if face.width != d:
        face = face.resize((d, d), Image.BILINEAR)
    c, s = math.cos(angle), math.sin(angle)
    width = max(2, int(abs(c) * d))
    thick = int(d * 0.09 * abs(s))
    _, _, edge = _rim_colors(color)
    out = Image.new("RGBA", (d + thick + 2, d), (0, 0, 0, 0))
    draw = ImageDraw.Draw(out)
    left = (out.width - width - thick) // 2
    back = left + thick if s >= 0 else left
    front = left if s >= 0 else left + thick
    # La tranche : un ovale derrière, relié à la face par un rectangle
    draw.ellipse((back, 0, back + width, d - 1), fill=(*edge, 255))
    draw.rectangle((min(back, front) + width // 2, 0, max(back, front) + width // 2, d - 1), fill=(*edge, 255))
    shown = face.resize((width, d), Image.BILINEAR) if width != d else face
    if c < 0:
        shown = shown.transpose(Image.FLIP_LEFT_RIGHT)
    out.alpha_composite(shown, (front, 0))
    return out


@lru_cache(maxsize=8)
def _spin_frames(film: Film, d: int, blur: float) -> list:
    """Un demi-tour de pièce en SPIN_FRAMES images, à cette taille et ce flou (la pluie les réutilise)."""
    face = _coin_face(film, d)
    frames = []
    for k in range(SPIN_FRAMES):
        img = _turned(face, math.pi * k / SPIN_FRAMES, film.color, d)
        frames.append(img.filter(ImageFilter.GaussianBlur(blur)) if blur > 0.3 else img)
    return frames


@lru_cache(maxsize=8)
def _shadow(d: int) -> Image.Image:
    img = Image.new("RGBA", (int(d * 1.1), int(d * 0.3)), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((d * 0.15, d * 0.08, d * 0.95, d * 0.22), fill=(0, 0, 0, 90))
    return img.filter(ImageFilter.GaussianBlur(d * 0.04))


@lru_cache(maxsize=16)
def _pill(text: str, size: int, fill: tuple, ink: tuple, outline: tuple | None = None) -> Image.Image:
    label = text_img(text, "ui", size, "bold", ink)
    pad = size * 0.8
    pill = rounded_rect((label.width + 2 * pad, size * 1.9), size * 0.95, (*fill[:3], 255),
                        (*outline[:3], 255) if outline else None, max(1, size // 14) if outline else 0)
    put(pill, label, pill.width / 2, pill.height / 2)
    return pill


@lru_cache(maxsize=16)
def _chip(text: str, size: int, dot: tuple, max_w: int) -> Image.Image:
    """Une étiquette blanche avec une ombre douce et un point de couleur."""
    while size > 16 and text_width(text, "ui", size, "semibold") + size * 3 > max_w:
        size = int(size * 0.92)
    label = text_img(text, "ui", size, "semibold", INK)
    pad = size * 0.75
    w, h = int(label.width + pad * 2 + size * 0.9), int(size * 1.9)
    out = Image.new("RGBA", (w + 24, h + 24), (0, 0, 0, 0))
    shadow = rounded_rect((w, h), h / 2, (0, 0, 0, 50)).filter(ImageFilter.GaussianBlur(6))
    out.alpha_composite(shadow, (12, 16))
    out.alpha_composite(rounded_rect((w, h), h / 2, (255, 255, 255, 255)), (12, 12))
    put(out, disc(size * 0.5, (*dot[:3], 255)), 12 + pad + size * 0.25, 12 + h / 2)
    put(out, label, 12 + pad + size * 0.9, 12 + h / 2, 1.0, "lm")
    return out
