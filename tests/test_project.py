import unittest

from launchbot import project as P
from launchbot.video.base import strip_stars


class CleaningTest(unittest.TestCase):
    def test_ticker(self):
        self.assertEqual(P.clean_ticker("frog"), "$FROG")
        self.assertEqual(P.clean_ticker("$ frog-2"), "$FROG2")
        self.assertEqual(P.clean_ticker("🐸"), "")
        self.assertEqual(len(P.clean_ticker("A" * 30)), 1 + P.TICKER_MAX)

    def test_emojis_are_removed_because_the_fonts_cannot_draw_them(self):
        self.assertEqual(P.clean_line("Froggy 🐸 Pad ✅", 30), "Froggy Pad")
        self.assertEqual(P.clean_line("Café ✔️ ok", 30), "Café ok")  # les accents restent

    def test_points_drop_bullets_and_keep_three(self):
        text = "- Fair launch\n• No presale\n1. Creators earn 1%\n4) Too many"
        self.assertEqual(P.parse_points(text), ["Fair launch", "No presale", "Creators earn 1%"])
        self.assertEqual(P.parse_points("a; b | c"), ["a", "b", "c"])
        self.assertEqual(P.parse_points("\n\n"), [])

    def test_colors(self):
        self.assertEqual(P.parse_color("gold"), P.COLORS["gold"])
        self.assertEqual(P.parse_color("#5CC46E"), (92, 196, 110))
        self.assertEqual(P.parse_color("5c6"), (0x55, 0xCC, 0x66))
        self.assertIsNone(P.parse_color("greenish"))
        self.assertEqual(P.color_name((92, 196, 110)), "#5CC46E")
        self.assertEqual(P.color_name(P.COLORS["mint"]), "mint")

    def test_sound_start(self):
        self.assertEqual(P.parse_start("1:20"), 80)
        self.assertEqual(P.parse_start("80"), 80)
        self.assertEqual(P.parse_start("80s"), 80)
        self.assertEqual(P.parse_start("1m20"), 80)
        self.assertIsNone(P.parse_start("the drop"))

    def test_bold_text_in_telegram_becomes_stars(self):
        text = "Launch a coin for anyone on X"
        entities = [{"type": "bold", "offset": 18, "length": 6}]
        self.assertEqual(P.with_stars(text, entities), "Launch a coin for *anyone* on X")
        # Telegram compte en UTF-16 : un emoji avant le mot compte pour deux
        self.assertEqual(P.with_stars("🐸 go now", [{"type": "bold", "offset": 3, "length": 2}]), "🐸 *go* now")

    def test_stars(self):
        self.assertEqual(strip_stars("Make a coin for *anyone* on X"),
                         [("Make", False), ("a", False), ("coin", False), ("for", False), ("anyone", True), ("on", False), ("X", False)])
        self.assertEqual(strip_stars("*two words* here"), [("two", True), ("words", True), ("here", False)])
        self.assertEqual(strip_stars("a * b"), [("a", False), ("b", False)])  # une étoile seule ne compte pas

    def test_spec_falls_back_to_the_beat_when_the_sound_is_gone(self):
        project = {**P.new_project(), "name": "X", "tagline": "Y", "music": "file", "sound": "u1.snd"}
        self.assertEqual(P.spec_of(project, "", "")["music"], "beat")
        self.assertEqual(P.spec_of(project, "", "C:/s.snd")["music_file"], "C:/s.snd")

    def test_steps(self):
        self.assertEqual(P.next_step("name"), "ticker")
        self.assertIsNone(P.next_step(P.STEPS[-1]))
        self.assertEqual(P.missing(P.new_project()), ["name", "tagline"])


if __name__ == "__main__":
    unittest.main()
