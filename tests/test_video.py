"""
Le dessin : chaque style, chaque format, se dessine du début à la fin sans erreur, avec ou sans logo, avec des
textes longs ou absents. La vraie vidéo (ffmpeg) n'est fabriquée que par un test, court.
"""

import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

from launchbot import maker
from launchbot.project import FORMATS, STYLES
from launchbot.video import base, music
from launchbot.video.render import STYLES as RENDER_STYLES, film_of

ROOT = Path(__file__).resolve().parent.parent
FULL = {"name": "Froggy Pad", "ticker": "$FROG", "tagline": "Launch a coin for *anyone* on Solana",
        "points": ["Fair launch, no presale", "Creators earn 1% of every trade", "Graduates to PumpSwap"],
        "color": [92, 196, 110], "logo": str(ROOT / "samples" / "logo-demo.png"), "status": "live", "link": "froggypad.fun"}
BARE = {"name": "Q", "ticker": "", "tagline": "go", "points": [], "color": [10, 10, 60], "logo": "", "status": "", "link": ""}
LONG = {**FULL, "name": "The Extremely Long Project Name", "logo": "/nowhere/logo.png", "points": ["W" * 48] * 3,
        "tagline": " ".join(["supercalifragilistic"] * 5), "link": "x" * 44, "color": [250, 250, 250]}


class DrawingTest(unittest.TestCase):
    def test_lists_match(self):
        self.assertEqual(set(STYLES), set(RENDER_STYLES))
        self.assertEqual(maker.SIZES, base.SIZES)
        self.assertEqual(set(FORMATS), set(base.SIZES))

    def test_every_style_and_format_draws(self):
        for style in STYLES:
            for fmt in FORMATS:
                for spec in (FULL, BARE, LONG):
                    with self.subTest(style=style, format=fmt, name=spec["name"]):
                        film = film_of({**spec, "style": style, "format": fmt})
                        self.assertGreater(film.duration, 6)
                        self.assertLess(film.duration, 30)
                        for t in (0.0, film.duration * 0.3, film.duration * 0.6, film.cover_t, film.duration):
                            img = film.frame(t)
                            self.assertEqual(img.size, base.SIZES[fmt])
                        self.assertTrue(all(0 <= a <= film.duration for a in film.accents))

    def test_a_missing_logo_gives_the_first_letter(self):
        film = film_of({**BARE, "style": "product"})
        self.assertIsNone(film.logo)
        disc = film.logo_disc(100)
        self.assertEqual(disc.size, (100, 100))

    def test_dark_colour_is_lightened_for_text_on_black(self):
        self.assertGreater(base.luminance(base.vivid((10, 10, 60))), 0.3)
        self.assertEqual(base.vivid((92, 196, 110)), (92, 196, 110))

    def test_kinetic_cuts_fall_on_the_beat(self):
        film = film_of({**FULL, "style": "kinetic"})
        beat = music.beat_s("kinetic")
        for start, *_ in film.shots:
            self.assertAlmostEqual(start / beat, round(start / beat), places=6)

    def test_kinetic_never_two_identical_backgrounds_in_a_row(self):
        film = film_of({**FULL, "style": "kinetic", "tagline": "one two three four five six seven *eight* nine"})
        words = [variant for _, _, kind, _, variant in film.shots if kind == "word"]
        self.assertTrue(all(a != b for a, b in zip(words, words[1:])), words)


class MusicTest(unittest.TestCase):
    def test_every_mood_writes_a_track_of_the_right_length(self):
        with tempfile.TemporaryDirectory() as folder:
            for mood in music.MOODS:
                path = music.make_track(mood, 2.0, Path(folder) / f"{mood}.wav", accents=[0.5], dings=[1.0])
                with wave.open(str(path)) as wav:
                    self.assertEqual(wav.getnframes(), 2 * music.SR)
                    self.assertEqual(wav.getnchannels(), 2)


class RenderTest(unittest.TestCase):
    def test_a_real_video_with_its_cover(self):
        """Une vraie fabrication (ffmpeg), en carré, du style le plus court."""
        with tempfile.TemporaryDirectory() as folder:
            spec = Path(folder) / "p.json"
            spec.write_text(json.dumps({**BARE, "style": "coins", "format": "square", "music": "beat"}), encoding="utf-8")
            out = Path(folder) / "p.mp4"
            done = subprocess.run([sys.executable, "-m", "launchbot.video.render", str(spec), str(out)], cwd=ROOT,
                                  capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertGreater(out.stat().st_size, 10_000)
            self.assertTrue(out.with_suffix(".png").is_file())
            self.assertFalse(out.with_name("p.music.wav").exists())


if __name__ == "__main__":
    unittest.main()
