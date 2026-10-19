import unittest
from pathlib import Path

from launchbot.config import ConfigError, parse_config


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        cfg = parse_config({}, {"TELEGRAM_BOT_TOKEN": "t"}, Path("."))
        self.assertFalse(cfg.public)
        self.assertEqual((cfg.default_format, cfg.default_music, cfg.videos_per_hour), ("landscape", "beat", 6))

    def test_owner_from_a_sibling_bot_but_never_its_token(self):
        cfg = parse_config({}, {}, Path("."), [{"TELEGRAM_OWNER_ID": "", "TELEGRAM_BOT_TOKEN": "other"},
                                               {"TELEGRAM_OWNER_ID": "12"}])
        self.assertEqual(cfg.owner_ids, (12,))
        self.assertEqual(cfg.telegram_token, "")

    def test_own_owner_first(self):
        cfg = parse_config({}, {"TELEGRAM_OWNER_ID": "5, 6"}, Path("."), [{"TELEGRAM_OWNER_ID": "12"}])
        self.assertEqual(cfg.owner_ids, (5, 6))

    def test_bad_values(self):
        for raw in ({"access": {"public": "yes"}}, {"access": {"videos_per_hour": 0}}, {"video": {"format": "wide"}},
                    {"video": {"music": "loud"}}):
            with self.subTest(raw=raw), self.assertRaises(ConfigError):
                parse_config(raw, {}, Path("."))
        with self.assertRaises(ConfigError):
            parse_config({}, {"TELEGRAM_OWNER_ID": "zig"}, Path("."))


if __name__ == "__main__":
    unittest.main()
