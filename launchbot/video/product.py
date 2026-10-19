"""
Style « product » : la vidéo de lancement sombre et nette des launchpads vus sur X (Creator.fun, Make, Borly,
Arena, Gifted ; voir RECHERCHE-X.md).

Le déroulé :
1. noir, grille de points ; le logo apparaît avec une lueur de la couleur du projet, un cercle se trace autour,
   le nom s'écrit lettre à lettre avec un curseur ;
2. le logo et le nom filent en haut à gauche (ils y restent) ; la phrase d'accroche arrive mot à mot, les mots
   entre étoiles en gras et en couleur (« Make a coin for *anyone* on X ») ;
3. les points clés, un par un, avec un grand numéro 01 / 02 / 03 et un trait qui avance ;
4. le ticker en très grand, avec « LIVE NOW » ou « COMING SOON » ;
5. la carte de fin : logo, nom, accroche, lien.
Environ 15 à 19 s selon la longueur de l'accroche et le nombre de points.
"""

from __future__ import annotations

from functools import lru_cache

from PIL import Image

from .base import (NIGHT, WHITE, Film, dot_grid, ease_back, ease_in_out, ease_out, fit_lines, fit_size, glow, lerp, prog,
                   put, radial, ring, rounded_rect, scaled, strip_stars, text_img, text_width)

INTRO_S = 2.8  # le logo et le nom au milieu
MOVE_S = 0.5  # leur trajet vers le coin
POINT_S = 2.0  # chaque point clé
TICKER_S = 1.9
END_S = 3.4
GREY = (150, 154, 162)
SOFT = (232, 234, 238)


class Product(Film):
    STYLE = "product"

    def __init__(self, spec: dict):
        super().__init__(spec)
        u = self.U
        self.margin = u(64)
        # Les temps
        self.words = strip_stars(self.tagline)
        count = max(1, len(self.words))
        self.word_step = min(0.13, 1.6 / count)
        self.t_tag = INTRO_S + MOVE_S - 0.1
        self.tag_end = self.t_tag + count * self.word_step + 1.7
        self.t_points = self.tag_end + 0.35
        self.t_ticker = self.t_points + POINT_S * len(self.points)
        self.t_end = self.t_ticker + TICKER_S
        self.duration = self.t_end + END_S
        self.accents = [INTRO_S, *(self.t_points + i * POINT_S for i in range(len(self.points))), self.t_ticker, self.t_end]
        self.cover_t = self.t_end + 1.6

        # Le fond : noir, grille de points, et une lueur de la couleur du projet
        self.bg = Image.new("RGBA", (self.W, self.H), (*NIGHT, 255))
        self.bg.alpha_composite(dot_grid((self.W, self.H), WHITE, u(34), max(1.0, 1.6 * self.u), 20))
        self.halo = radial((self.W, self.H), (self.W / 2, self.H / 2 - u(60)), u(520), self.accent, 70)

        # Le logo du milieu, sa lueur, et le nom
        self.d0 = u(340 if self.portrait else 300)
        self.d1 = u(64)
        self.logo_big = self.logo_disc(self.d0)
        self.logo_glow = glow(self.logo_big, self.accent, u(42), 0.9)
        self.name_size = fit_size(self.name, "ui", "bold", self.W * 0.82, u(104))
        self.head_size = u(30)
        self.logo_y = self.H / 2 - u(70 if not self.portrait else 120)
        self.name_y = self.logo_y + self.d0 / 2 + u(56) + self.name_size * 0.62

        # L'accroche, mise en page une fois pour toutes
        self.tag_layout = self._layout_tagline()

    # --- mise en page ---------------------------------------------------------------------------

    def _layout_tagline(self) -> tuple[int, list]:
        """Taille et place de chaque mot de l'accroche : [(mot, en avant, x, y)], lignes centrées."""
        stars = any(bold for _, bold in self.words)
        max_w = self.W * (0.84 if self.portrait else 0.8)
        max_lines = 5 if self.portrait else 3
        size = self.U(100 if not self.portrait else 92)
        while True:
            lines, line, width = [], [], 0.0
            space = text_width(" ", "ui", size, "regular") * 1.1
            for word, bold in self.words:
                w = text_width(word, "ui", size, self._weight(bold, stars))
                if line and width + space + w > max_w:
                    lines.append((line, width))
                    line, width = [], 0.0
                line.append((word, bold, w))
                width += (space if len(line) > 1 else 0) + w
            if line:
                lines.append((line, width))
            if (len(lines) <= max_lines and all(w <= max_w for _, w in lines)) or size < self.U(30):
                break
            size = int(size * 0.93)
        placed = []
        step = size * 1.18
        top = self.H / 2 - step * len(lines) / 2 + step / 2
        for row, (line, width) in enumerate(lines):
            x = self.W / 2 - width / 2
            for word, bold, w in line:
                placed.append((word, bold, x, top + row * step))
                x += w + space
        return size, placed

    @staticmethod
    def _weight(bold: bool, stars: bool) -> str:
        if not stars:
            return "semibold"
        return "bold" if bold else "light"

    # --- dessin ---------------------------------------------------------------------------------

    def draw(self, t: float) -> Image.Image:
        img = self.bg.copy()
        halo = 1.0 if t < INTRO_S else 0.45 if t < self.t_end else 0.8
        if INTRO_S <= t < INTRO_S + MOVE_S:
            halo = lerp(1.0, 0.45, prog(t, INTRO_S, MOVE_S))
        elif self.t_end <= t < self.t_end + 0.6:
            halo = lerp(0.45, 0.8, prog(t, self.t_end, 0.6))
        put(img, self.halo, self.W / 2, self.H / 2, halo * ease_out(prog(t, 0.0, 0.8)))

        if t < INTRO_S + MOVE_S:
            self.intro(img, t)
        elif t < self.t_end:
            self.header(img, t)
        if self.t_tag <= t < self.tag_end + 0.35:
            self.tagline_scene(img, t)
        for i in range(len(self.points)):
            start = self.t_points + i * POINT_S
            if start <= t < start + POINT_S:
                self.point_scene(img, t, i, start)
        if self.t_ticker <= t < self.t_end:
            self.ticker_scene(img, t)
        if t >= self.t_end:
            self.end_scene(img, t)
        return img

    def intro(self, img: Image.Image, t: float) -> None:
        u = self.U
        appear = prog(t, 0.15, 0.6)
        move = ease_in_out(prog(t, INTRO_S, MOVE_S))
        # Le logo : il grandit en « pop », puis rejoint le coin en haut à gauche
        size = lerp(self.d0 * (0.7 + 0.3 * ease_back(appear)), self.d1, move)
        x = lerp(self.W / 2, self.margin + self.d1 / 2, move)
        y = lerp(self.logo_y, self.margin + self.d1 / 2, move)
        factor = size / self.d0
        put(img, scaled(self.logo_glow, factor), x, y, ease_out(appear) * (1 - move) * (0.85 + 0.15 * abs((t * 1.3) % 2 - 1)))
        sweep = ease_in_out(prog(t, 0.35, 0.9))
        if sweep > 0 and move < 1:
            put(img, ring(self.d0 + u(44), self.accent, max(2, u(3)), sweep), self.W / 2, self.logo_y, 1 - move * 2.5)
        put(img, scaled(self.logo_big, factor), x, y, ease_out(appear))

        # Le nom : il s'écrit lettre à lettre, puis rejoint le logo dans le coin
        typed = int(max(0.0, t - 1.0) / 0.045)
        shown = self.name[:typed]
        if not shown:
            return
        size_now = int(lerp(self.name_size, self.head_size, move))
        weight = "bold" if move < 0.5 else "semibold"
        sprite = text_img(shown, "ui", size_now, weight, WHITE)
        full = text_width(self.name, "ui", size_now, weight)
        left = lerp(self.W / 2 - full / 2, self.margin + self.d1 + u(18), move)
        ny = lerp(self.name_y, self.margin + self.d1 / 2, move)
        put(img, sprite, left, ny, 1.0, "lm")
        typing = typed < len(self.name)
        if move < 0.3 and (typing or int(t * 2.6) % 2 == 0):
            cursor = rounded_rect((size_now * 0.42, size_now * 0.86), 2, (*self.accent, 255))
            put(img, cursor, left + sprite.width + u(6), ny + size_now * 0.04, 1 - move * 3, "lm")

    def header(self, img: Image.Image, t: float) -> None:
        u = self.U
        fade = 1 - prog(t, self.t_end - 0.3, 0.3)
        put(img, self.logo_disc(self.d1), self.margin + self.d1 / 2, self.margin + self.d1 / 2, fade)
        put(img, text_img(self.name, "ui", self.head_size, "semibold", WHITE), self.margin + self.d1 + u(18),
            self.margin + self.d1 / 2, fade, "lm")
        right = self.ticker or self.status_text
        if right:
            put(img, text_img(right, "ui", u(26), "semibold", GREY, 0.08), self.W - self.margin, self.margin + self.d1 / 2,
                fade * ease_out(prog(t, INTRO_S + MOVE_S, 0.5)), "rm")

    def tagline_scene(self, img: Image.Image, t: float) -> None:
        size, placed = self.tag_layout
        stars = any(bold for _, bold in self.words)
        leave = ease_in_out(prog(t, self.tag_end, 0.35))
        for i, (word, bold, x, y) in enumerate(placed):
            come = ease_out(prog(t, self.t_tag + i * self.word_step, 0.35))
            if come <= 0:
                continue
            color = self.accent if bold and stars else WHITE if not stars else SOFT
            sprite = text_img(word, "ui", size, self._weight(bold, stars), color)
            put(img, sprite, x, y + self.U(26) * (1 - come) - self.U(30) * leave, come * (1 - leave), "lm")

    def point_scene(self, img: Image.Image, t: float, i: int, start: float) -> None:
        u = self.U
        come = ease_out(prog(t, start, 0.4))
        leave = ease_in_out(prog(t, start + POINT_S - 0.3, 0.3))
        alpha = come * (1 - leave)
        number = text_img(f"{i + 1:02d}", "ui", u(200), "bold", self.accent)
        text = self.points[i]
        if self.portrait or self.W == self.H:
            size, lines = fit_lines(text, "ui", "semibold", self.W * 0.82, u(76), 4)
            block = size * 1.2 * len(lines)
            top = self.H / 2 - (number.height + u(30) + block) / 2
            put(img, number, self.W / 2 - u(40) * (1 - come), top + number.height / 2, alpha)
            y0 = top + number.height + u(30) + size * 0.6
            for row, line in enumerate(lines):
                rise = ease_out(prog(t, start + 0.12 + row * 0.08, 0.4))
                put(img, text_img(line, "ui", size, "semibold", WHITE), self.W / 2, y0 + row * size * 1.2 + u(20) * (1 - rise),
                    rise * (1 - leave))
            bar_y, x0, x1 = y0 + block + u(10), self.W * 0.2, self.W * 0.8
        else:
            x_num = self.W * 0.12
            x_text = x_num + number.width + u(56)
            size, lines = fit_lines(text, "ui", "semibold", self.W * 0.88 - x_text, u(80), 3)
            block = size * 1.2 * len(lines)
            put(img, number, x_num - u(50) * (1 - come), self.H / 2, alpha, "lm")
            y0 = self.H / 2 - block / 2 + size * 0.6
            for row, line in enumerate(lines):
                rise = ease_out(prog(t, start + 0.12 + row * 0.08, 0.4))
                put(img, text_img(line, "ui", size, "semibold", WHITE), x_text, y0 + row * size * 1.2 + u(20) * (1 - rise),
                    rise * (1 - leave), "lm")
            bar_y, x0, x1 = self.H / 2 + max(block / 2, number.height / 2) + u(40), x_num, self.W * 0.88
        # Le trait qui avance pendant que le point reste à l'écran, sur un trait gris
        full = int(x1 - x0)
        put(img, rounded_rect((full, max(2, u(3))), 1, (255, 255, 255, 40)), x0, bar_y, alpha, "lm")
        done = int(full * ease_in_out(prog(t, start + 0.2, POINT_S - 0.5)))
        if done > 2:
            put(img, rounded_rect((done, max(2, u(3))), 1, (*self.accent, 255)), x0, bar_y, alpha, "lm")
        put(img, text_img(f"{i + 1:02d} / {len(self.points):02d}", "mono", u(24), "regular", GREY), x1, bar_y + u(30), alpha, "rm")

    def ticker_scene(self, img: Image.Image, t: float) -> None:
        u = self.U
        start = self.t_ticker
        big_text = self.ticker or self.name
        big, aura = _big(big_text, int(fit_size(big_text, "ui", "bold", self.W * 0.8, u(260))), self.accent, u(40))
        come = ease_out(prog(t, start, 0.5))
        leave = ease_in_out(prog(t, self.t_end - 0.3, 0.3))
        factor = 1.12 - 0.12 * come
        y = self.H / 2 - u(40)
        put(img, scaled(aura, factor), self.W / 2, y, come * (1 - leave) * 0.9)
        put(img, scaled(big, factor), self.W / 2, y, come * (1 - leave))
        label = self.status_text or (self.link if self.ticker else "")
        if label:
            pill_come = ease_out(prog(t, start + 0.35, 0.4))
            self.pill(img, label, self.W / 2, y + big.height / 2 + u(70) + u(16) * (1 - pill_come), pill_come * (1 - leave), t,
                      dot=bool(self.status_text))

    def pill(self, img: Image.Image, label: str, x: float, y: float, alpha: float, t: float, dot: bool) -> None:
        u = self.U
        size = u(32)
        text = text_img(label, "ui" if dot else "mono", size, "semibold", WHITE, 0.1 if dot else 0.0)
        pad = u(30)
        dot_w = u(18) + u(14) if dot else 0
        box = rounded_rect((text.width + 2 * pad + dot_w, size * 2.0), size, (*self.accent, 38), (*self.accent, 255), max(1, u(2)))
        put(img, box, x, y, alpha)
        left = x - box.width / 2 + pad
        if dot:
            beat = 0.55 + 0.45 * abs((t * 1.6) % 2 - 1)
            put(img, rounded_rect((u(18), u(18)), u(9), (*self.accent, 255)), left + u(9), y, alpha * beat)
            left += dot_w
        put(img, text, left, y, alpha, "lm")

    def end_scene(self, img: Image.Image, t: float) -> None:
        u = self.U
        start = self.t_end
        d = u(230 if not self.portrait else 270)
        top = self.H / 2 - u(150 if not self.portrait else 260)
        logo = self.logo_disc(d)
        come = ease_out(prog(t, start, 0.6))
        put(img, scaled(_logo_glow(self, d), 0.9 + 0.1 * come), self.W / 2, top, come)
        put(img, ring(d + u(36), self.accent, max(2, u(3)), ease_in_out(prog(t, start + 0.1, 0.8))), self.W / 2, top, come)
        put(img, scaled(logo, 0.85 + 0.15 * ease_back(prog(t, start, 0.6))), self.W / 2, top, come)
        y = top + d / 2 + u(40)
        size = fit_size(self.name, "ui", "bold", self.W * 0.8, u(88))
        rise = ease_out(prog(t, start + 0.15, 0.5))
        put(img, text_img(self.name, "ui", size, "bold", WHITE), self.W / 2, y + size * 0.6 + u(20) * (1 - rise), rise)
        y += size * 1.25
        plain = " ".join(word for word, _ in self.words)
        if plain:
            tsize, lines = fit_lines(plain, "ui", "regular", self.W * (0.8 if self.portrait else 0.62), u(34), 2)
            rise = ease_out(prog(t, start + 0.3, 0.5))
            for row, line in enumerate(lines):
                put(img, text_img(line, "ui", tsize, "regular", GREY), self.W / 2, y + tsize * 0.6 + row * tsize * 1.3 + u(16) * (1 - rise), rise)
            y += tsize * 1.3 * len(lines) + u(20)
        rise = ease_out(prog(t, start + 0.45, 0.5))
        if self.link:
            self.pill(img, self.link, self.W / 2, y + u(42) + u(16) * (1 - rise), rise, t, dot=False)
            y += u(100)
        if self.status_text:
            rise = ease_out(prog(t, start + 0.6, 0.5))
            chip = text_img("● " + self.status_text, "ui", u(26), "semibold", self.accent, 0.12)
            put(img, chip, self.W / 2, y + u(28), rise)


@lru_cache(maxsize=8)
def _big(text: str, size: int, color: tuple, radius: int) -> tuple:
    big = text_img(text, "ui", size, "bold", WHITE)
    return big, glow(big, color, radius, 0.8)


@lru_cache(maxsize=8)
def _logo_glow(film: Film, d: int) -> Image.Image:
    return glow(film.logo_disc(d), film.accent, film.U(34), 0.8)

