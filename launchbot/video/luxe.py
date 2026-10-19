"""
Style « luxe » : le teaser lent et sombre, façon bande-annonce (comme la vidéo de ZAT vue sur X, voir RECHERCHE-X.md).

Sans images de film (le bot n'en a pas et n'en invente pas), le « cinéma » vient de la lumière :
1. le logo sort du noir, gravé dans un métal de la couleur du projet ; un reflet de lumière le traverse, des
   poussières flottent devant ; bandes noires du cinéma en haut et en bas (en paysage) ;
2. un carton : l'accroche, en petites lettres à empattements, blanches sur noir, qui apparaissent et s'effacent ;
3. le nom en capitales espacées, devant des lumières floues de la couleur du projet qui glissent ;
4. un carton par point clé ;
5. la fin : le logo en métal, le nom, un filet, « COMING SOON » ou « LIVE NOW », le lien.
Grain de film et coins assombris sur toute la vidéo. Environ 17 à 22 s.
"""

from __future__ import annotations

import random
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from .base import (WHITE, Film, clamp, disc, ease_in_out, ease_out, fit_lines, fit_size, glow, grain, mix, prog, put, scaled,
                   strip_stars, text_img, vignette)

REVEAL_S = 4.2
CARD_S = 3.0
NAME_S = 3.2
POINT_S = 2.5
FINAL_S = 4.8
FADE_S = 0.7  # fondu d'entrée et de sortie des cartons
GRAINS = 6  # nombre de voiles de grain différents (ils tournent)
BLACK = (4, 4, 5)
GREY = (138, 136, 132)


class Luxe(Film):
    STYLE = "luxe"

    def __init__(self, spec: dict):
        super().__init__(spec)
        u = self.U
        self.tag_plain = " ".join(word for word, _ in strip_stars(self.tagline))
        # Les temps
        self.t_card = REVEAL_S
        self.t_name = self.t_card + (CARD_S if self.tag_plain else 0)
        self.t_points = self.t_name + NAME_S
        self.t_final = self.t_points + POINT_S * len(self.points)
        self.duration = self.t_final + FINAL_S
        self.accents = [0.35, self.t_name, self.t_final]
        self.cover_t = self.t_final + 3.2

        # Le cadre du cinéma (2,39:1) en paysage ; rien en carré et en portrait
        self.bar = int((self.H - self.W / 2.39) / 2) if self.W > self.H else 0
        self.metal = _metal_palette(self.color)
        self.d_big = u(560 if self.portrait else 460)
        self.emblem = _emblem(self, self.d_big)
        self.vignette = vignette((self.W, self.H), 190)
        self.grains = [grain((self.W, self.H), seed, 10) for seed in range(GRAINS)]
        rng = random.Random(5)
        # Les poussières : (x, y en fraction de l'écran, rayon, vitesse, phase)
        self.dust = [(rng.random(), rng.random(), rng.uniform(1.2, 4.5), rng.uniform(0.01, 0.04), rng.random()) for _ in range(70)]
        # Les lumières floues de la scène du nom : (x, y, diamètre, vitesse, teinte)
        self.lights = [(rng.random(), rng.uniform(0.15, 0.85), rng.uniform(90, 300), rng.uniform(0.015, 0.05), rng.random())
                       for _ in range(26)]

    def draw(self, t: float) -> Image.Image:
        img = Image.new("RGBA", (self.W, self.H), (*BLACK, 255))
        if t < self.t_card:
            self.reveal(img, t)
        elif t < self.t_name:
            self.card(img, self.tag_plain, t - self.t_card, CARD_S)
        elif t < self.t_points:
            self.name_scene(img, t - self.t_name)
        elif t < self.t_final:
            i = int((t - self.t_points) // POINT_S)
            self.card(img, self.points[min(i, len(self.points) - 1)], t - self.t_points - i * POINT_S, POINT_S)
        else:
            self.final(img, t - self.t_final)
        img.alpha_composite(self.vignette)
        img.alpha_composite(self.grains[int(t * 10) % GRAINS])  # le grain change 10 fois par seconde, comme sur pellicule
        if self.bar:
            draw = ImageDraw.Draw(img)
            draw.rectangle((0, 0, self.W, self.bar), fill=(0, 0, 0, 255))
            draw.rectangle((0, self.H - self.bar, self.W, self.H), fill=(0, 0, 0, 255))
        return img

    # --- scènes --------------------------------------------------------------------------------------

    def reveal(self, img: Image.Image, t: float) -> None:
        light = ease_in_out(prog(t, 0.3, 2.4)) * (1 - prog(t, REVEAL_S - 0.6, 0.6))
        factor = 1.08 - 0.08 * ease_out(prog(t, 0.0, REVEAL_S))  # la caméra recule lentement
        emblem = scaled(self.emblem, factor)
        put(img, _halo(self, self.d_big), self.W / 2, self.H / 2, light * 0.55)
        put(img, emblem, self.W / 2, self.H / 2, light)
        sweep = prog(t, 1.4, 1.8)
        if 0 < sweep < 1:
            put(img, _sheen(emblem, sweep), self.W / 2, self.H / 2, light)
        self.draw_dust(img, t, light)

    def card(self, img: Image.Image, text: str, local: float, length: float) -> None:
        """Un carton : texte blanc à empattements sur noir, qui apparaît puis s'efface."""
        u = self.U
        alpha = ease_in_out(prog(local, 0.1, FADE_S)) * (1 - ease_in_out(prog(local, length - FADE_S, FADE_S)))
        size, lines = fit_lines(text, "serif", "regular", self.W * (0.8 if self.portrait else 0.62), u(62), 3)
        step = size * 1.45
        top = self.H / 2 - step * (len(lines) - 1) / 2
        drift = u(8) * prog(local, 0, length)  # le texte monte à peine pendant qu'il est là
        for row, line in enumerate(lines):
            put(img, text_img(line, "serif", size, "regular", (236, 233, 226), 0.03), self.W / 2, top + row * step - drift, alpha)

    def name_scene(self, img: Image.Image, local: float) -> None:
        u = self.U
        alpha = ease_in_out(prog(local, 0.0, 0.9)) * (1 - ease_in_out(prog(local, NAME_S - 0.6, 0.6)))
        for x, y, d, speed, tone in self.lights:
            light = _bokeh(int(u(d)), mix(self.metal[2], self.metal[3], tone))
            px = ((x + speed * local) % 1.2 - 0.1) * self.W
            put(img, light, px, y * self.H, alpha * 0.4)
        text = self.name.upper()
        size = fit_size(text, "serif", "regular", self.W * 0.8, u(84), tracking=0.32)
        put(img, text_img(text, "serif", size, "regular", WHITE, 0.32), self.W / 2, self.H / 2, alpha)
        line_w = int(self.W * 0.18 * ease_out(prog(local, 0.6, 1.2)))
        if line_w > 2:
            put(img, Image.new("RGBA", (line_w, max(1, u(2))), (*self.metal[2], 255)), self.W / 2, self.H / 2 + size * 0.95, alpha)

    def final(self, img: Image.Image, local: float) -> None:
        u = self.U
        come = ease_in_out(prog(local, 0.0, 1.2))
        d = u(330 if self.portrait else 270)
        emblem = _emblem(self, d)
        top = self.H / 2 - u(140 if not self.portrait else 240)
        put(img, _halo(self, d), self.W / 2, top, come * 0.5)
        put(img, emblem, self.W / 2, top, come)
        sweep = prog(local, 1.2, 1.6)
        if 0 < sweep < 1:
            put(img, _sheen(emblem, sweep), self.W / 2, top, come)
        y = top + d / 2 + u(70)
        text = self.name.upper()
        size = fit_size(text, "serif", "regular", self.W * 0.78, u(64), tracking=0.28)
        rise = ease_in_out(prog(local, 0.5, 1.0))
        put(img, text_img(text, "serif", size, "regular", WHITE, 0.28), self.W / 2, y, rise)
        y += size * 0.9
        line_w = int(u(220) * ease_out(prog(local, 0.9, 1.0)))
        if line_w > 2:
            put(img, Image.new("RGBA", (line_w, max(1, u(2))), (*self.metal[2], 255)), self.W / 2, y, 1.0)
        y += u(46)
        if self.status_text:
            put(img, text_img(self.status_text, "serif", u(30), "regular", self.metal[2], 0.42), self.W / 2, y,
                ease_in_out(prog(local, 1.3, 0.9)))
            y += u(52)
        if self.link:
            put(img, text_img(self.link, "serif", u(26), "regular", GREY, 0.12), self.W / 2, y, ease_in_out(prog(local, 1.7, 0.9)))
        self.draw_dust(img, local + 7.0, come * 0.6)

    def draw_dust(self, img: Image.Image, t: float, alpha: float) -> None:
        """Des poussières dans la lumière : de petits points flous qui montent lentement et scintillent."""
        if alpha <= 0.01:
            return
        for x, y, r, speed, phase in self.dust:
            py = ((y - speed * t) % 1.0) * self.H
            px = (x + 0.01 * ((t * 0.3 + phase) % 1.0 - 0.5)) * self.W
            twinkle = 0.4 + 0.6 * abs(((t * 0.5 + phase) % 1.0) * 2 - 1)
            put(img, _speck(max(2, int(r * 2 * self.u))), px, py, alpha * twinkle * 0.7)


# --- le métal ------------------------------------------------------------------------------------------


def _metal_palette(color: tuple) -> tuple:
    """Quatre tons du métal tiré de la couleur du projet : ombre, corps, reflet, éclat."""
    base = tuple(color[:3])
    return (mix(base, (0, 0, 0), 0.82), mix(base, (0, 0, 0), 0.35), mix(base, WHITE, 0.25), mix(base, WHITE, 0.75))


@lru_cache(maxsize=8)
def _emblem(film: Luxe, d: int) -> Image.Image:
    """
    Le logo frappé dans le métal : son relief (gris du logo, avec un léger estampage) passé dans les tons du métal,
    et un liseré biseauté autour. Sans logo : la première lettre du nom, frappée de la même façon.
    """
    face = film.logo_disc(d)
    gray = ImageOps.autocontrast(face.convert("L"), cutoff=2)
    relief = ImageChops.blend(gray, gray.filter(ImageFilter.EMBOSS), 0.35)
    # La lumière vient d'en haut : le haut du métal plus clair, le bas plus sombre ; puis une courbe en S qui
    # creuse les ombres et fait briller les reliefs (sans elle, le métal paraît terne)
    light_from_top = Image.linear_gradient("L").resize((d, d)).point(lambda v: 255 - v // 2)
    relief = ImageChops.multiply(relief, light_from_top).point(lambda v: int(255 / (1 + 2.718 ** (-(v - 110) / 28))))
    shadow, body, light, shine = film.metal
    lut = []
    for v in range(256):
        u = v / 255
        if u < 0.45:
            c = mix(shadow, body, u / 0.45)
        elif u < 0.8:
            c = mix(body, light, (u - 0.45) / 0.35)
        else:
            c = mix(light, shine, (u - 0.8) / 0.2)
        lut.append(c)
    rgb = Image.merge("RGB", [relief.point([c[i] for c in lut]) for i in range(3)])
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    out.paste(rgb, (0, 0), face.getchannel("A"))
    # Le liseré : un anneau clair en haut, sombre en bas (la lumière vient d'en haut)
    rim = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    gradient = Image.linear_gradient("L").resize((d, d))
    ring_mask = ImageChops.subtract(disc(d, (255, 255, 255, 255)).getchannel("A"),
                                    _inner(d, max(3, d // 60)))
    colors = Image.merge("RGB", [gradient.point(lambda v, i=i: mix(shine, shadow, v / 255)[i]) for i in range(3)])
    rim.paste(colors, (0, 0), ring_mask)
    out.alpha_composite(rim)
    return out


def _inner(d: int, width: int) -> Image.Image:
    mask = Image.new("L", (d, d), 0)
    inner = disc(d - 2 * width, (255, 255, 255, 255)).getchannel("A")
    mask.paste(inner, (width, width))
    return mask


def _sheen(emblem: Image.Image, u: float) -> Image.Image:
    """Le reflet qui traverse le métal en diagonale (u de 0 à 1 : de gauche à droite)."""
    w, h = emblem.size
    band = Image.new("L", (w * 3, h), 0)
    ImageDraw.Draw(band).rectangle((int(w * 1.5 - w * 0.08), 0, int(w * 1.5 + w * 0.08), h), fill=170)
    band = band.filter(ImageFilter.GaussianBlur(w * 0.04)).rotate(-25, resample=Image.BILINEAR)
    offset = int((clamp(u) * 2 - 1) * w * 1.1)
    mask = band.crop((w + offset, 0, 2 * w + offset, h))
    mask = ImageChops.multiply(mask, emblem.getchannel("A"))
    out = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    out.putalpha(mask)
    return out


@lru_cache(maxsize=8)
def _halo(film: Luxe, d: int) -> Image.Image:
    return glow(disc(d, (255, 255, 255, 255)), film.metal[2], d * 0.12, 0.6)


@lru_cache(maxsize=64)
def _bokeh(d: int, color: tuple) -> Image.Image:
    """Une lumière floue : un disque doux, un peu plus clair au bord (comme un objectif)."""
    d = max(8, d)
    img = disc(d, (*color[:3], 60), (*color[:3], 110), max(1, d // 30))
    return img.filter(ImageFilter.GaussianBlur(d * 0.04))


@lru_cache(maxsize=16)
def _speck(d: int) -> Image.Image:
    return disc(d, (255, 244, 220, 200)).filter(ImageFilter.GaussianBlur(max(0.6, d * 0.25)))
