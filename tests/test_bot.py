import asyncio
import tempfile
import unittest
from pathlib import Path

from launchbot.bot import Bot
from launchbot.state import State
from tests.fakes import OTHER, OWNER, FakeMaker, FakeTelegram, make_config, png_bytes, press, private, settle


class BotTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = make_config(self.root)
        self.tg = FakeTelegram()
        self.maker = FakeMaker(self.root / "videos")
        self.state = State(self.cfg.state_path)
        self.bot = Bot(self.cfg, self.state, self.tg, self.maker, check_sound=lambda path: True)

    def tearDown(self):
        self.tmp.cleanup()

    async def say(self, text, user=OWNER, **extra):
        await self.bot.handle(private(user, text=text, **extra))

    async def tap(self, data, user=OWNER, **extra):
        await self.bot.handle(press(user, data, **extra))
        await settle(self.bot)

    async def fill(self, user=OWNER):
        """Répond à toutes les questions, avec un logo."""
        await self.say("/new", user)
        await self.say("Froggy 🐸 Pad", user)
        await self.say("frog", user)
        await self.say("Launch a coin for *anyone* on Solana", user)
        await self.say("- Fair launch\n- Creators earn 1%", user)
        self.tg.files["logo1"] = png_bytes()
        await self.bot.handle(private(user, photo=[{"file_id": "small"}, {"file_id": "logo1", "file_size": 300}]))
        await settle(self.bot)
        await self.tap("c:gold", user)
        await self.tap("st:kinetic", user)
        await self.tap("s:soon", user)
        await self.say("froggypad.fun", user)
        await self.tap("f:portrait", user)

    async def test_whole_conversation_then_video(self):
        await self.fill()
        project = self.state.project(OWNER)
        self.assertEqual(project["name"], "Froggy Pad")
        self.assertEqual(project["ticker"], "$FROG")
        self.assertEqual(project["points"], ["Fair launch", "Creators earn 1%"])
        self.assertEqual(project["logo"], f"u{OWNER}.img")
        self.assertIsNone(project["step"])
        self.assertIn("Your video", self.tg.last()["text"])
        self.assertIn("make", self.tg.buttons())

        await self.tap("make")
        spec = self.maker.specs[-1]
        self.assertEqual((spec["style"], spec["format"], spec["status"]), ("kinetic", "portrait", "soon"))
        self.assertEqual(spec["color"], [226, 182, 92])
        self.assertTrue(spec["logo"].endswith(f"u{OWNER}.img") and Path(spec["logo"]).is_file())
        video = self.tg.of("video")[-1]
        self.assertEqual(video["size"], (1080, 1920))
        self.assertEqual(video["filename"], "froggy-pad.mp4")
        self.assertEqual(self.state.stats, (1, 1))

    async def test_other_style_remakes_at_once(self):
        await self.fill()
        await self.tap("make")
        await self.tap("re:style", text=False)
        self.assertIn("st:luxe", self.tg.buttons())
        await self.tap("st:luxe")
        self.assertEqual([s["style"] for s in self.maker.specs], ["kinetic", "luxe"])
        self.assertEqual(len(self.tg.of("video")), 2)

    async def test_skip_and_required_answers(self):
        await self.say("/new")
        await self.say("🐸🐸")  # rien d'écrivable : redemandé
        self.assertEqual(self.state.project(OWNER)["step"], "name")
        await self.say("Pad")
        await self.tap("skip")  # ticker
        self.assertEqual(self.state.project(OWNER)["step"], "tagline")
        await self.tap("skip")  # l'accroche est obligatoire : le bouton ne fait rien
        self.assertEqual(self.state.project(OWNER)["step"], "tagline")
        await self.say("The pad")
        await self.tap("skip")  # points
        await self.tap("skip")  # logo
        self.assertEqual(self.state.project(OWNER)["step"], "color")
        await self.say("not a colour")
        self.assertEqual(self.state.project(OWNER)["step"], "color")
        await self.say("#5CC46E")
        self.assertEqual(self.state.project(OWNER)["color"], [92, 196, 110])
        await self.say("product")  # le style se choisit par bouton
        self.assertEqual(self.state.project(OWNER)["step"], "style")

    async def test_edit_one_field_comes_back_to_the_summary(self):
        await self.fill()
        await self.tap("edit")
        self.assertIn("e:name", self.tg.buttons())
        await self.tap("e:name")
        await self.say("Toad Pad")
        project = self.state.project(OWNER)
        self.assertEqual(project["name"], "Toad Pad")
        self.assertIsNone(project["step"])
        self.assertIn("Toad Pad", self.tg.last()["text"])

    async def test_old_button_does_not_jump_ahead(self):
        await self.say("/new")
        await self.say("Pad")
        await self.tap("st:coins")  # un vieux bouton de style pendant la question du ticker
        project = self.state.project(OWNER)
        self.assertEqual(project["style"], "coins")
        self.assertEqual(project["step"], "ticker")

    async def test_logo_before_new_opens_a_project(self):
        self.tg.files["l"] = png_bytes()
        await self.bot.handle(private(OWNER, document={"file_id": "l", "mime_type": "image/png", "file_size": 100}))
        await settle(self.bot)
        project = self.state.project(OWNER)
        self.assertEqual(project["step"], "name")
        self.assertEqual(project["logo"], f"u{OWNER}.img")
        self.assertIn("c:logo", (await self._color_buttons()))

    async def _color_buttons(self):
        project = self.state.project(OWNER)
        project.update(step="color")
        self.state.set_project(OWNER, project)
        await self.bot.ask(OWNER, OWNER, project, "color")
        return self.tg.buttons()

    async def test_a_file_that_is_not_a_picture(self):
        await self.say("/new")
        self.tg.files["bad"] = b"not a picture"
        await self.bot.handle(private(OWNER, photo=[{"file_id": "bad"}]))
        await settle(self.bot)
        self.assertIn("could not open", self.tg.last()["text"])
        self.assertEqual(self.state.project(OWNER)["logo"], "")

    async def test_own_sound_with_start_in_caption(self):
        await self.fill()
        self.tg.files["snd"] = b"ID3 fake mp3"
        await self.bot.handle(private(OWNER, audio={"file_id": "snd", "file_size": 12}, caption="1:20"))
        await settle(self.bot)
        project = self.state.project(OWNER)
        self.assertEqual((project["music"], project["sound_start"]), ("file", 80.0))
        await self.tap("make")
        spec = self.maker.specs[-1]
        self.assertEqual(spec["music"], "file")
        self.assertEqual(spec["music_start"], 80.0)
        self.assertTrue(Path(spec["music_file"]).is_file())

    async def test_sound_toggle(self):
        await self.fill()
        await self.tap("sound")
        self.assertEqual(self.state.project(OWNER)["music"], "none")
        await self.tap("sound")
        self.assertEqual(self.state.project(OWNER)["music"], "beat")

    async def test_private_bot_refuses_others(self):
        await self.say("/new", OTHER)
        self.assertEqual(self.tg.last()["text"], "This is a private bot.")
        self.assertIsNone(self.state.project(OTHER))

    async def test_public_bot_limits_others_but_not_the_owner(self):
        self.cfg.public, self.cfg.videos_per_hour = True, 1
        await self.fill(OTHER)
        await self.tap("make", OTHER)
        await self.tap("make", OTHER)
        self.assertIn("1 videos per hour", self.tg.last()["text"])
        self.assertEqual(len(self.maker.specs), 1)
        await self.fill(OWNER)
        await self.tap("make", OWNER)
        await self.tap("make", OWNER)
        self.assertEqual(len(self.maker.specs), 3)

    async def test_one_video_at_a_time_per_person(self):
        await self.fill()
        self.maker.release = asyncio.Event()
        await self.bot.handle(press(OWNER, "make"))
        await self.bot.handle(press(OWNER, "make"))
        self.assertIn("still being made", self.tg.last()["text"])
        self.maker.release.set()
        await settle(self.bot)
        self.assertEqual(len(self.tg.of("video")), 1)

    async def test_failed_video_frees_the_place(self):
        self.maker.fail = True
        await self.fill()
        await self.tap("make")
        self.assertIn("could not be made", self.tg.last()["text"])
        self.assertEqual(self.bot.making, set())

    async def test_project_survives_a_restart(self):
        await self.fill()
        again = Bot(self.cfg, State(self.cfg.state_path), self.tg, self.maker)
        self.assertEqual(again.project(OWNER)["name"], "Froggy Pad")

    async def test_groups_are_ignored(self):
        await self.bot.handle({"message": {"chat": {"id": -100, "type": "supergroup"}, "from": {"id": OWNER}, "text": "/new"}})
        self.assertEqual(self.tg.sent, [])

    async def test_no_owner_tells_the_id(self):
        self.cfg.owner_ids = ()
        await self.say("hello", OTHER)
        self.assertIn(f"TELEGRAM_OWNER_ID={OTHER}", self.tg.last()["text"])


if __name__ == "__main__":
    unittest.main()
