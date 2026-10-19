"""
La musique des vidéos, fabriquée de toutes pièces en Python (aucun morceau téléchargé, donc aucun droit d'auteur) :
une ambiance par style, aux coupes de la vidéo près.

    product   beat électronique calme, 112 battements par minute, la mineur (comme les vidéos de Pump Radar)
    kinetic   beat dur et rapide, 128 BPM, fa mineur : la typo choc coupe sur chaque temps
    luxe      nappe grave et lente, cloches espacées, gros coups sourds aux coupes (bande-annonce)
    coins     pop joyeuse, 120 BPM, do majeur, et un « ding » de pièce à chaque apparition

Chaque coupe de la vidéo (accents) reçoit un coup ; le style « coins » ajoute ses dings (Film.dings).
Le son entre et sort en fondu. Écrit en WAV stéréo 44,1 kHz ; 15 à 20 s se font en 2 à 5 s.

Quand la personne envoie son propre son (fichier audio ou vidéo), render.py le prend à la place de celui-ci.
"""

from __future__ import annotations

import math
import random
import struct
import wave
from functools import lru_cache
from pathlib import Path

SR = 44100
FADE_IN_S, FADE_OUT_S = 0.1, 1.4
PEAK = 0.85  # le plus fort échantillon, sur 1 : de la marge avant l'écrêtage de la lecture

# Les accords, une mesure chacun : (fondamentale de la basse, notes de l'accord), en hertz
MINOR_A = ((55.00, (220.00, 261.63, 329.63)), (43.65, (174.61, 220.00, 261.63)),
           (65.41, (196.00, 261.63, 329.63)), (49.00, (196.00, 246.94, 293.66)))  # Am F C G
MINOR_F = ((43.65, (174.61, 207.65, 261.63)), (34.65, (138.59, 174.61, 207.65)),
           (51.91, (207.65, 261.63, 311.13)), (38.89, (155.56, 196.00, 233.08)))  # Fm Db Ab Eb
MAJOR_C = ((65.41, (261.63, 329.63, 392.00)), (49.00, (196.00, 246.94, 293.66)),
           (55.00, (220.00, 261.63, 329.63)), (43.65, (174.61, 220.00, 261.63)))  # C G Am F

MOODS = {
    "product": dict(bpm=112, chords=MINOR_A),
    "kinetic": dict(bpm=128, chords=MINOR_F),
    "luxe": dict(bpm=70, chords=MINOR_A),
    "coins": dict(bpm=120, chords=MAJOR_C),
}


def beat_s(mood: str) -> float:
    """La durée d'un temps de cette ambiance, en secondes (le style « kinetic » coupe dessus)."""
    return 60 / MOODS.get(mood, MOODS["product"])["bpm"]


def add(mix: list, start: float, sound: list, gain: float) -> None:
    """Pose un son (liste d'échantillons) dans le mélange, à start secondes."""
    first = int(start * SR)
    if first < 0:
        sound, first = sound[-first:], 0
    end = min(len(mix), first + len(sound))
    for j in range(first, end):
        mix[j] += sound[j - first] * gain


@lru_cache(maxsize=None)
def kick(punch: float = 1.0) -> tuple:
    out, phase = [], 0.0
    for i in range(int(0.24 * SR)):
        t = i / SR
        phase += 2 * math.pi * (45 + 95 * punch * math.exp(-t * 28)) / SR  # la hauteur chute vite : le « boum »
        out.append(math.sin(phase) * math.exp(-t * (15 / punch)) * (1 if i > 30 else i / 30))
    return tuple(out)


@lru_cache(maxsize=None)
def noise(length_s: float, decay: float, bright: bool, seed: int = 7) -> tuple:
    """Un souffle qui s'éteint. bright : sans les graves : charleston, cymbale."""
    rng = random.Random(seed)
    out, last = [], 0.0
    for i in range(int(length_s * SR)):
        v = rng.uniform(-1, 1)
        out.append((v - last if bright else v) * math.exp(-i / SR * decay))
        last = v
    return tuple(out)


@lru_cache(maxsize=None)
def pluck(freq: float, length_s: float, decay: float, harmonic: float) -> tuple:
    return tuple((math.sin(2 * math.pi * freq * i / SR) + harmonic * math.sin(4 * math.pi * freq * i / SR))
                 * math.exp(-i / SR * decay) for i in range(int(length_s * SR)))


@lru_cache(maxsize=None)
def pad(freq: float, length_s: float, attack: float = 0.5) -> tuple:
    """Une note tenue : naissance lente, mort lente, un peu de vibrato."""
    n = int(length_s * SR)
    return tuple(math.sin(2 * math.pi * freq * i / SR + 0.002 * math.sin(2 * math.pi * 5 * i / SR) * freq)
                 * min(i / (attack * SR), 1.0, (n - i) / (attack * SR)) for i in range(n))


@lru_cache(maxsize=None)
def bell(freq: float, length_s: float) -> tuple:
    """Une cloche : fondamentale et partiels non harmoniques, extinction lente."""
    ratios = ((1.0, 1.0), (2.76, 0.4), (5.4, 0.18))
    return tuple(sum(g * math.sin(2 * math.pi * freq * r * i / SR) for r, g in ratios) * math.exp(-i / SR * 2.2)
                 for i in range(int(length_s * SR)))


@lru_cache(maxsize=None)
def ding() -> tuple:
    """Le son d'une pièce : deux notes aiguës, très vite."""
    a, b = bell(1975.5, 0.5), bell(2637.0, 0.6)
    shift = int(0.06 * SR)
    return tuple((a[i] if i < len(a) else 0) * 0.6 + (b[i - shift] if 0 <= i - shift < len(b) else 0)
                 for i in range(shift + len(b)))


@lru_cache(maxsize=None)
def boom() -> tuple:
    """Le gros coup sourd des bandes-annonces : une basse qui tombe, longue."""
    out, phase = [], 0.0
    for i in range(int(2.2 * SR)):
        t = i / SR
        phase += 2 * math.pi * (32 + 60 * math.exp(-t * 6)) / SR
        out.append(math.sin(phase) * math.exp(-t * 1.6) * (1 if i > 60 else i / 60))
    return tuple(out)


def make_track(mood: str, duration_s: float, path: Path, accents: list | tuple = (), dings: list | tuple = ()) -> Path:
    """Écrit un fichier WAV de duration_s secondes dans l'ambiance mood. accents : instants (s) des coupes."""
    cfg = MOODS.get(mood, MOODS["product"])
    beat = 60 / cfg["bpm"]
    step = beat / 4  # une double-croche
    chords = cfg["chords"]
    mix = [0.0] * (int(duration_s * SR) + SR)
    clap = list(noise(0.16, 22, False))
    for i in range(len(clap)):  # une caisse claire sans le grondement du bruit brut
        clap[i] *= 1.0 if i % 2 else 0.35
    hat = noise(0.05, 70, True)

    for n in range(int(duration_s / step) + 1):
        t = n * step
        bar, in_bar = divmod(n, 16)
        root, chord = chords[bar % len(chords)]
        beat_no, sub = divmod(in_bar, 4)
        if mood == "luxe":
            if in_bar == 0:  # une nappe grave par mesure, et la quinte
                add(mix, t, pad(root * 2, beat * 4.6, 0.9), 0.22)
                add(mix, t, pad(root * 3, beat * 4.6, 0.9), 0.08)
                for freq in chord:
                    add(mix, t, pad(freq / 2, beat * 4.6, 1.2), 0.05)
            if in_bar in (0, 6, 10) and bar % 2 == 0:  # quelques cloches, espacées
                add(mix, t, bell(chord[(bar // 2 + in_bar) % 3] * 2, 2.5), 0.05)
            if sub == 0 and beat_no in (0, 2):  # un battement de cœur, à peine
                add(mix, t, kick(0.6), 0.22)
            continue
        if sub == 0:
            add(mix, t, kick(1.2 if mood == "kinetic" else 1.0), 1.0 if mood == "kinetic" else 0.95)
            if beat_no in (1, 3):
                add(mix, t, tuple(clap), 0.3 if mood == "kinetic" else 0.22)
        if mood == "kinetic":
            add(mix, t, hat, 0.12 if sub else 0.05)  # charleston à chaque double-croche
            if sub == 2:  # basse sur le contretemps, avec ses harmoniques : plus mordante
                add(mix, t, pluck(root * 2, step * 1.8, 9, 0.9), 0.32)
            if in_bar % 3 == 0:
                add(mix, t, pluck(chord[(n // 3) % 3] * 2, step * 1.6, 14, 0.7), 0.06)
            continue
        if in_bar % 2 == 0 and sub != 0:
            add(mix, t, hat, 0.16)  # charleston sur les contretemps
        elif sub == 0:
            add(mix, t, hat, 0.06)
        if mood == "coins":
            if in_bar % 2 == 0:  # arpège joyeux, en croches
                note = chord[(0, 1, 2, 1, 2, 0, 1, 2)[(in_bar // 2) % 8]] * 2
                add(mix, t, pluck(note, step * 2.4, 10, 0.3), 0.09)
            if sub == 2:
                add(mix, t, pluck(root * 2, step * 2.5, 8, 0.3), 0.3)
            continue
        if in_bar in (2, 6, 10, 14, 11, 15):  # basse sur les contretemps, entre les grosses caisses
            add(mix, t, pluck(root, step * 3.2, 7, 0.35), 0.34)
        note = chord[(0, 1, 2, 1)[n % 4]] * (2 if in_bar >= 8 else 1)
        voice = pluck(note, step * 2.6, 9, 0.5)
        add(mix, t, voice, 0.085)
        add(mix, t + step * 3, voice, 0.03)  # un écho, trois doubles-croches plus tard
        if in_bar == 0:
            for freq in chord:
                add(mix, t, pad(freq / 2, beat * 4.4), 0.045)

    for when in accents:
        if mood == "luxe":
            add(mix, when, boom(), 0.75)
            add(mix, when, noise(1.6, 2.5, True, 11), 0.05)
        else:
            add(mix, when, pluck(52.0, 0.9, 3.2, 0.0), 0.5)  # un coup grave
            add(mix, when, noise(0.7, 6, True, 11), 0.11)  # et une cymbale
    for when in dings:
        add(mix, when, ding(), 0.16)

    # Écrêtage doux, puis fondus et niveau
    total = int(duration_s * SR)
    mix = [math.tanh(v * 1.1) for v in mix[:total]]
    peak = max((abs(v) for v in mix), default=0.0) or 1.0
    fade_in, fade_out = int(FADE_IN_S * SR), int(FADE_OUT_S * SR)
    frames = bytearray()
    pack = struct.Struct("<hh").pack
    for i, v in enumerate(mix):
        gain = min(1.0, i / fade_in if fade_in else 1.0, (total - i) / fade_out if fade_out else 1.0)
        sample = int(max(-1.0, min(1.0, v / peak * PEAK * gain)) * 32767)
        frames += pack(sample, sample)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes(bytes(frames))
    return path
