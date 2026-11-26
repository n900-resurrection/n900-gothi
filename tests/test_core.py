"""Tests of the core, no display needed:  python3 -m unittest discover -s tests"""
import os
import sys
import random
import struct
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gothi import flipper, keys  # noqa: E402
from gothi.apps import Clock, main_menu  # noqa: E402
from gothi.canvas import Canvas  # noqa: E402
from gothi.apps import ColorScene, SettingsScene  # noqa: E402
from gothi import dolphin as dol  # noqa: E402
from gothi.apps import Stats  # noqa: E402
from gothi import modules as mod  # noqa: E402
from gothi.settings import Settings  # noqa: E402
from gothi.ui import Gothi, Menu  # noqa: E402


class CanvasTest(unittest.TestCase):
    def test_pixel_and_clipping(self):
        c = Canvas()
        c.pixel(0, 0)
        c.pixel(-1, 5)
        c.pixel(128, 5)
        self.assertEqual(sum(c.px), 1)

    def test_box_and_frame(self):
        c = Canvas()
        c.box(2, 2, 4, 3)
        self.assertEqual(sum(c.px), 12)
        c.clear()
        c.frame(0, 0, 5, 5)
        self.assertEqual(sum(c.px), 16)

    def test_invert_twice(self):
        c = Canvas()
        c.text(1, 10, "gothi")
        before = bytes(c.px)
        c.invert(0, 0, 60, 30)
        c.invert(0, 0, 60, 30)
        self.assertEqual(before, bytes(c.px))

    def test_text_draws_czech_and_width(self):
        c = Canvas()
        w = c.text(0, 10, "Příliš žluťoučký")
        self.assertEqual(w, c.text_width("Příliš žluťoučký"))
        self.assertGreater(sum(c.px), 40)

    def test_text_scale(self):
        a, b = Canvas(), Canvas()
        a.text(0, 10, "A")
        b.text(0, 10, "A", scale=2)
        self.assertEqual(sum(b.px), 4 * sum(a.px))


class MenuTest(unittest.TestCase):
    def test_navigation_and_back(self):
        g = Gothi(main_menu())
        g.key(keys.DOWN)
        self.assertEqual(g.top.sel, 1)
        g.key(keys.UP)
        g.key(keys.UP)
        self.assertEqual(g.top.sel, len(g.top.items) - 1)      # wraps around
        g.key(keys.OK)
        self.assertEqual(len(g.stack), 2)
        g.key(keys.BACK)
        self.assertEqual(len(g.stack), 1)
        g.key(keys.BACK)
        self.assertEqual(len(g.stack), 1)                      # the root stays

    def test_scrolling_keeps_selection_visible(self):
        m = Menu("t", [(str(i), lambda g: Clock()) for i in range(10)])
        g = Gothi(m)
        for _ in range(7):
            g.key(keys.DOWN)
        self.assertLessEqual(m.top_row, m.sel)
        self.assertLess(m.sel, m.top_row + m.ROWS)

    def test_every_scene_draws(self):
        g = Gothi(main_menu())
        c = Canvas()
        for i in range(len(g.top.items)):
            g.stack = g.stack[:1]
            g.top.sel = i
            g.key(keys.OK)
            g.draw(c)
            self.assertGreater(sum(c.px), 0, g.top.__class__.__name__)


class SettingsTest(unittest.TestCase):
    def test_defaults_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "s.json")
            st = Settings(p)
            self.assertEqual(st.height, 64)
            st["color"], st["screen"] = [1, 2, 3], "tall"
            st.save()
            st2 = Settings(p)
            self.assertEqual((st2.color, st2.height), ((1, 2, 3), 80))

    def test_broken_file_gives_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            open(p, "w").write("{not json")
            self.assertEqual(Settings(p).height, 64)

    def test_color_scene_changes_and_clamps(self):
        with tempfile.TemporaryDirectory() as d:
            g = Gothi(ColorScene(), Settings(os.path.join(d, "s.json")))
            g.settings["color"] = [250, 100, 0]
            g.key(keys.DOWN)                       # row R
            for _ in range(3):
                g.key(keys.RIGHT)
            self.assertEqual(g.settings.color[0], 255)
            g.key(keys.DOWN)
            g.key(keys.DOWN)                       # row B
            g.key(keys.LEFT)
            self.assertEqual(g.settings.color[2], 0)
            g.draw(Canvas())

    def test_tall_screen_menu_has_more_rows(self):
        with tempfile.TemporaryDirectory() as d:
            st = Settings(os.path.join(d, "s.json"))
            g = Gothi(SettingsScene(), st)
            g.key(keys.DOWN)
            g.key(keys.OK)                         # screen -> tall
            self.assertEqual(g.h, 80)
            m = Menu("t", [(str(i), lambda g: Clock()) for i in range(9)])
            g2 = Gothi(m, st)
            c = Canvas(128, 80)
            g2.draw(c)
            self.assertEqual(m.ROWS, 5)


def png(w, h, rows, depth=1, ctype=0, plte=None):
    """A tiny PNG built by hand (filter 0), `rows`: packed bytes of every row."""
    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
    raw = b"".join(b"\0" + r for r in rows)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, 0))
    if plte:
        out += chunk(b"PLTE", plte)
    return out + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class FlipperTest(unittest.TestCase):
    def test_png_one_bit_gray(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png")
            open(p, "wb").write(png(3, 2, [bytes([0b01000000]), bytes([0b10100000])]))   # 1 = white
            im = flipper.read_png(p)
            self.assertEqual((im.w, im.h), (3, 2))
            self.assertEqual(list(im.px), [1, 0, 1, 0, 1, 0])                              # dark = ink

    def test_png_palette(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png")
            open(p, "wb").write(png(2, 1, [bytes([0b01000000])], ctype=3, plte=bytes([255, 255, 255, 0, 0, 0])))
            self.assertEqual(list(flipper.read_png(p).px), [0, 1])

    def test_animation_meta_and_frames(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "L1_Test_4x1")
            os.mkdir(a)
            for i in range(2):
                open(os.path.join(a, f"frame_{i}.png"), "wb").write(png(4, 1, [bytes([0b00000000 if i else 0b11110000])]))
            open(os.path.join(a, "meta.txt"), "w").write("Filetype: Flipper Animation\nWidth: 4\nHeight: 1\nFrame rate: 2\nFrames order: 1 0 0\n"
                                                           "Bubble slots: 1\nSlot: 0\nX: 5\nY: 6\nText: Hi\\nthere\nStartFrame: 1\nEndFrame: 2\n")
            an = flipper.Animation(a)
            self.assertEqual((an.frame_rate, an.order, an.w, an.h), (2, [1, 0, 0], 4, 1))
            self.assertEqual(an.bubbles[0]["Text"], "Hi\nthere")
            self.assertEqual(list(an.frame_at(0).px), [1, 1, 1, 1])        # order[0] = frame 1 (all dark)
            self.assertEqual(list(an.frame_at(0.6).px), [0, 0, 0, 0])      # 0.6 s at 2 fps = index 1 -> frame 0

    def make_dolphin(self, d, frames=5):
        a = os.path.join(d, "L1_Dog_8x1")
        os.mkdir(a)
        for i in range(frames):
            open(os.path.join(a, f"frame_{i}.png"), "wb").write(png(8, 1, [bytes([1 << i])]))
        open(os.path.join(a, "meta.txt"), "w").write(
            "Filetype: Flipper Animation\nWidth: 8\nHeight: 1\nPassive frames: 3\nActive frames: 2\nFrames order: 0 1 2 3 4\n"
            "Active cycles: 2\nFrame rate: 1\nDuration: 60\nActive cooldown: 5\nBubble slots: 1\nSlot: 0\nX: 4\nY: 20\nText: Woof\n"
            "AlignH: Left\nAlignV: Bottom\nStartFrame: 1\nEndFrame: 3\n")
        return flipper.Animation(a)

    def test_playback_passive_active_cooldown(self):
        with tempfile.TemporaryDirectory() as d:
            pb = flipper.Playback(self.make_dolphin(d), 100.0)
            self.assertEqual([pb.at(100 + t)[1] for t in (0, 1, 2, 3, 4)], [0, 1, 2, 0, 1])     # passive loops
            self.assertTrue(pb.activate(110.0))
            self.assertEqual([pb.at(110 + t)[1] for t in (0, 1, 2, 3)], [3, 4, 3, 4])          # active part, 2 cycles
            self.assertEqual(pb.at(114.0)[1], 0)                                                   # 2 cycles of 2 frames are over: passive again
            self.assertEqual(pb.state, "passive")
            self.assertFalse(pb.activate(118.0))                                                   # cooldown of 5 s, counted from 114
            self.assertTrue(pb.activate(119.5))

    def test_bubbles_by_position_and_drawing(self):
        with tempfile.TemporaryDirectory() as d:
            an = self.make_dolphin(d)
            pb = flipper.Playback(an, 0.0)
            self.assertEqual(pb.bubbles(0), [])
            self.assertEqual(pb.bubbles(2)[0]["Text"], "Woof")
            self.assertEqual(pb.bubbles(4), [])
            c = Canvas()
            flipper.draw_bubble(c, an.bubbles[0], 0, 10)
            self.assertGreater(sum(c.px), 20)

    def test_pick_by_level_and_weight(self):
        m = [{"Name": "A", "Min level": "1", "Max level": "1", "Weight": "1"}, {"Name": "B", "Min level": "2", "Max level": "3", "Weight": "5"}]
        rng = random.Random(1)
        self.assertEqual({flipper.pick(m, 1, rng) for _ in range(20)}, {"A"})
        self.assertEqual({flipper.pick(m, 3, rng) for _ in range(20)}, {"B"})
        self.assertIn(flipper.pick(m, 9, rng), ("A", "B"))                                         # nothing fits: any

    def test_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "manifest.txt")
            open(p, "w").write("Filetype: Flipper Animation Manifest\nVersion: 1\n\nName: A_1x1\nWeight: 3\n\nName: B_1x1\nWeight: 1\n")
            m = flipper.read_manifest(p)
            self.assertEqual([x["Name"] for x in m], ["A_1x1", "B_1x1"])

    def test_firmware_assets_when_present(self):
        root = os.path.join(os.path.dirname(__file__), "..", "assets", "flipper", "dolphin", "external")
        if not os.path.isdir(root):
            self.skipTest("run tools/fetch-assets.sh")
        for n in sorted(os.listdir(root))[:6]:
            if os.path.isdir(os.path.join(root, n)):
                an = flipper.Animation(os.path.join(root, n))
                self.assertGreater(len(an.frames), 0, n)
                self.assertGreater(sum(an.frames[0].px), 0, n)


if __name__ == "__main__":
    unittest.main()


DAY = 86400
T0 = 1_800_000_000 + 12 * 3600        # some day around noon (local time zone only moves the 05:00 limit by hours)


def mk(**over):
    r = dol.load_rules(user_path=os.devnull)
    r.update(over)
    return dol.DolphinState(r, path="", now=T0)


class DolphinTest(unittest.TestCase):
    def test_shipped_rules_are_valid(self):
        r = dol.load_rules(user_path=os.devnull)
        self.assertEqual(r["levels"], [300, 1800])
        self.assertEqual(r["butthurt"]["increase_hours"], 48)

    def test_levels_follow_the_firmware(self):
        d = mk()
        for xp, lv in ((0, 1), (300, 1), (301, 2), (1800, 2), (1801, 3), (99999, 3)):
            d.xp = xp
            self.assertEqual(d.level, lv, xp)
        d.xp = 100
        self.assertEqual(d.xp_to_levelup(), 200)
        d.xp = 5000
        self.assertIsNone(d.xp_to_levelup())

    def test_xp_stops_at_threshold_until_confirmed(self):
        d = mk(default_limit=1000)
        d.xp = 299
        self.assertEqual(d.deed("dolphin_active", T0), 1)         # weight 2, one XP to the threshold
        self.assertTrue(d.levelup_pending())
        self.assertEqual(d.deed("dolphin_active", T0), 0)
        self.assertTrue(d.confirm_levelup())
        self.assertEqual(d.level, 2)
        self.assertEqual(d.deed("dolphin_active", T0), 2)

    def test_daily_limit_per_group_and_reset_at_five(self):
        d = mk()
        self.assertEqual(sum(d.deed("dolphin_active", T0) for _ in range(30)), 20)
        self.assertEqual(d.deed("clock_view", T0), 1)             # another group
        self.assertEqual(d.deed("dolphin_active", T0 + DAY), 2)                    # the next day
        self.assertEqual(d.deed("nonsense", T0), 0)

    def test_butthurt_grows_every_48_hours_and_is_capped(self):
        d = mk()
        d.update(T0 + 47 * 3600)
        self.assertEqual(d.butthurt, 0)
        d.update(T0 + 49 * 3600)
        self.assertEqual(d.butthurt, 1)
        d.update(T0 + 49 * 3600 + 10 * 48 * 3600)
        self.assertEqual(d.butthurt, 11)
        d.update(T0 + 400 * DAY)
        self.assertEqual(d.butthurt, 14)
        d.update(T0)                                              # the clock went back: no crash, no change
        self.assertEqual(d.butthurt, 14)

    def test_deeds_lower_butthurt_in_steps_at_most_four_a_day(self):
        d = mk(default_limit=1000)
        d.butthurt = 10
        gains = [d.deed("dolphin_active", T0) for _ in range(40)]       # 80 XP
        self.assertEqual(sum(gains), 80)
        self.assertEqual(d.butthurt, 6)
        d.butthurt = 10
        d.deed("dolphin_active", T0 + DAY)                              # the next day: one more step (the first XP)
        self.assertEqual(d.butthurt, 9)

    def test_happy_mode_hides_butthurt(self):
        d = mk()
        d.butthurt = 9
        self.assertEqual((d.mood(False), d.mood(True), d.butthurt), (9, 0, 9))

    def test_state_is_saved_and_loaded(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "x", "state.json")
            d = dol.DolphinState(dol.load_rules(user_path=os.devnull), p, T0)
            d.deed("clock_view", T0)
            d.save()
            d2 = dol.DolphinState(dol.load_rules(user_path=os.devnull), p, T0)
            self.assertEqual((d2.xp, d2.group_xp), (1, {"tools": 1}))
            open(p, "w").write("{broken")
            self.assertEqual(dol.DolphinState(dol.load_rules(user_path=os.devnull), p, T0).xp, 0)

    def test_user_rules_override_and_broken_ones_are_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "rules.json")
            open(p, "w").write('{"levels": [10, 20, 30], "deeds": {"clock_view": {"xp": 5}, "my_deed": {"group": "mine", "xp": 3}}}')
            r = dol.load_rules(p)
            self.assertEqual((r["levels"], r["deeds"]["clock_view"], r["deeds"]["battery_view"]["xp"], r["deeds"]["my_deed"]["xp"]), ([10, 20, 30], {"group": "tools", "xp": 5}, 1, 3))
            for bad in ('{"levels": [20, 10]}', '{"levels": []}', "nonsense", '{"deeds": {"x": {"xp": -1, "group": "g"}}}'):
                open(p, "w").write(bad)
                self.assertEqual(dol.load_rules(p)["levels"], [300, 1800], bad)

    def test_levelup_message_and_deed_by_scene(self):
        r = dol.load_rules(user_path=os.devnull)
        st = dol.DolphinState(r, "", T0)
        st.xp = 299
        g = Gothi(main_menu(), Settings(os.devnull), st)
        g.top.sel = 0
        g.key(keys.OK)                                            # Clock: +1 -> threshold -> level 2
        self.assertEqual((st.xp, st.level), (301, 2))
        self.assertEqual(g.top.title, "Level up!")
        g.key(keys.BACK)
        g.key(keys.BACK)
        self.assertEqual(g.top.__class__.__name__, "Menu")

    def test_stats_scene_draws_and_happy_switch(self):
        with tempfile.TemporaryDirectory() as t:
            g = Gothi(SettingsScene(), Settings(os.path.join(t, "s.json")))
            for _ in range(3):
                g.key(keys.DOWN)
            g.key(keys.OK)
            self.assertTrue(g.settings["happy"])
            self.assertEqual(Settings(os.path.join(t, "s.json"))["happy"], True)
            for tall in (False, True):
                g.settings["screen"] = "tall" if tall else "classic"
                g.h = g.settings.height
                c = Canvas(h=g.h)
                g.stack = [Stats()]
                g.draw(c)
                self.assertGreater(sum(c.px), 50)


def make_module(base, name, manifest):
    os.makedirs(os.path.join(base, name))
    with open(os.path.join(base, name, "module.json"), "w") as f:
        f.write(manifest if isinstance(manifest, str) else __import__("json").dumps(manifest))


GOOD = {"title": "Server", "type": "switch", "status": "test -f FLAG", "start": "touch FLAG", "stop": "rm FLAG", "info": "echo http://10.0.0.5:3923/; echo ' '; echo two",
        "deed": "srv", "deeds": {"srv": {"group": "modules", "xp": 2}}}


class ModulesTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.d = self.t.name

    def tearDown(self):
        self.t.cleanup()

    def good(self):
        flag = os.path.join(self.d, "flag")
        return {k: (v.replace("FLAG", flag) if isinstance(v, str) else v) for k, v in GOOD.items()}, flag

    def test_discovery_skips_broken_and_later_folder_wins(self):
        a, b = os.path.join(self.d, "a"), os.path.join(self.d, "b")
        make_module(a, "srv", GOOD)
        make_module(a, "broken1", "{nonsense")
        make_module(a, "broken2", {"type": "switch", "status": "true"})              # commands missing
        make_module(a, "broken3", {"type": "magic"})
        make_module(a, "broken4", dict(GOOD, deeds={"x": {"group": "g", "xp": -1}}))
        make_module(b, "srv", dict(GOOD, title="Mine"))
        os.makedirs(os.path.join(a, "no-manifest"))
        mods, errs = mod.discover([a, b, os.path.join(self.d, "missing")])
        self.assertEqual([(m.id, m.title) for m in mods], [("srv", "Mine")])
        self.assertEqual(sorted(n for n, _ in errs), ["broken1", "broken2", "broken3", "broken4"])

    def test_switch_toggles_and_shows_info(self):
        man, flag = self.good()
        make_module(self.d, "srv", man)
        m = mod.discover([self.d])[0][0]
        st = dolphin_state = dol.DolphinState(dol.load_rules(user_path=os.devnull, extra=[{"deeds": m.deeds}]), path="", now=T0)
        g = Gothi(mod.Switch(m, spawn=lambda f: f()), Settings(os.devnull), st)
        g.top.on_enter(g)
        self.assertFalse(g.top.on)
        g.draw(Canvas())
        g.key(keys.OK)                                           # start
        self.assertTrue(os.path.exists(flag))
        self.assertTrue(g.top.on)
        self.assertEqual(g.top.info, ["http://10.0.0.5:3923/", "two"])
        c = Canvas()
        g.draw(c)
        self.assertGreater(sum(c.px), 50)
        g.tick(T0)                                               # the deed of the toggle
        self.assertEqual(dolphin_state.xp, 2)
        g.key(keys.OK)                                           # stop
        self.assertFalse(os.path.exists(flag))
        self.assertFalse(g.top.on)

    def test_start_waits_until_the_service_answers(self):
        man, flag = self.good()
        ready = os.path.join(self.d, "ready")
        man["ready"] = f"test -f {ready}"
        make_module(self.d, "srv", man)
        m = mod.discover([self.d])[0][0]
        old = mod.READY_STEP
        mod.READY_STEP = 0.05
        try:
            seen = []
            def run(cmd, timeout=10):
                if "ready" in cmd:
                    seen.append(cmd)
                    if len(seen) == 3:
                        open(ready, "w").close()
                return mod.run_cmd(cmd, timeout)
            sw = mod.Switch(m, run=run, spawn=lambda f: f())
            g = Gothi(sw, Settings(os.devnull))
            sw.on_enter(g)
            sw.toggle()
            self.assertEqual(len(seen), 3)                       # polled until it answered
            self.assertTrue(sw.on)
            self.assertIsNone(sw.action)
        finally:
            mod.READY_STEP = old

    def test_refresh_never_blanks_the_info_or_shows_checking(self):
        man, flag = self.good()
        make_module(self.d, "srv", man)
        m = mod.discover([self.d])[0][0]
        open(flag, "w").close()
        seen = []
        sw = mod.Switch(m, spawn=lambda f: f())
        sw.run = lambda cmd, timeout=10: (seen.append((sw.on, list(sw.info), sw.action)), mod.run_cmd(cmd, timeout))[1]
        g = Gothi(sw, Settings(os.devnull))
        sw.on_enter(g)
        first = list(sw.info)
        self.assertTrue(first)
        seen.clear()
        sw.refresh()                                             # a second check: the old values stay until the new ones are there
        self.assertTrue(all(i == first and a is None and o for o, i, a in seen), seen)

    def test_long_info_wraps_and_scrolls(self):
        man, flag = self.good()
        man["info"] = "for i in 1 2 3 4 5 6 7 8; do echo \"line $i of the information that is longer than the screen\"; done"
        open(flag, "w").close()
        make_module(self.d, "srv", man)
        m = mod.discover([self.d])[0][0]
        sw = mod.Switch(m, spawn=lambda f: f())
        g = Gothi(sw, Settings(os.devnull))
        sw.on_enter(g)
        self.assertGreater(len(sw.info), 8)
        self.assertTrue(all(Canvas(1, 1).text_width(x) <= 118 for x in sw.info))
        first = Canvas()
        g.draw(first)
        for _ in range(len(sw.info)):
            g.key(keys.DOWN)
        last = Canvas()
        g.draw(last)
        self.assertNotEqual(bytes(first.px), bytes(last.px))                  # the page moved
        self.assertEqual(sw.top, len(sw.info) - sw.visible(64))
        for _ in range(len(sw.info)):
            g.key(keys.UP)
        self.assertEqual(sw.top, 0)

    def test_command_failures_and_timeout(self):
        self.assertEqual(mod.run_cmd("exit 3")[0], 3)
        self.assertEqual(mod.run_cmd("sleep 5", timeout=0.2), (-1, ""))
        self.assertEqual(mod.run_cmd("echo hi"), (0, "hi\n"))

    def test_menu_lists_modules_and_errors_and_empty_message(self):
        make_module(self.d, "srv", GOOD)
        make_module(self.d, "bad", "{")
        mods, errs = mod.discover([self.d])
        g = Gothi(mod.modules_menu(mods, errs), Settings(os.devnull))
        self.assertEqual([i[0] for i in g.top.items], ["Server", "! bad"])
        g.draw(Canvas())
        g.key(keys.DOWN)
        g.key(keys.OK)                                           # the reason of the failure
        g.draw(Canvas())
        self.assertEqual(mod.modules_menu([], []).title, "Modules")

    def test_module_deeds_are_merged_into_the_rules_and_bad_ones_skipped(self):
        r = dol.load_rules(user_path=os.devnull, extra=[{"deeds": {"srv": {"group": "modules", "xp": 2}}}, {"levels": [5, 4]}])
        self.assertEqual(r["deeds"]["srv"]["xp"], 2)
        self.assertEqual(r["levels"], [300, 1800])

    def test_main_menu_has_modules_item(self):
        g = Gothi(main_menu(([], [])))
        names = [i[0] for i in g.top.items]
        self.assertIn("Modules", names)
        g.top.sel = names.index("Modules")
        g.key(keys.OK)
        g.draw(Canvas())


class ScrollTest(unittest.TestCase):
    def test_stats_scrolls_and_shows_every_row(self):
        for screen, h in (("classic", 64), ("tall", 80)):
            g = Gothi(Stats(), Settings(os.devnull))
            g.settings["screen"] = screen
            g.h = g.settings.height
            rows = g.top.rows(g)
            n = g.top.visible(g.h)
            self.assertGreater(len(rows), n - 1)
            shots = set()
            for _ in range(len(rows) + 2):                        # down past the end: it stops, no crash
                c = Canvas(h=h)
                g.draw(c)
                shots.add(bytes(c.px))
                g.key(keys.DOWN)
            self.assertEqual(g.top.top, max(0, len(rows) - n))
            self.assertGreater(len(shots), 1)                     # the picture changed while scrolling
            for _ in range(len(rows) + 2):
                g.key(keys.UP)
            self.assertEqual(g.top.top, 0)

    def test_scrollview_without_overflow_has_no_scrollbar_and_back_leaves(self):
        g = Gothi(Menu("m", [("a", lambda g: Stats())]))
        g.key(keys.OK)
        g.stack[-1].rows = lambda gothi: ["one", "two"]
        c = Canvas()
        g.draw(c)
        self.assertEqual(g.top.top, 0)
        self.assertEqual(c.px[(c.h // 2) * c.w + c.w - 2], 0)     # the track of the scroll bar is not drawn
        g.key(keys.BACK)
        self.assertEqual(g.top.__class__.__name__, "Menu")


try:
    import sdl2  # noqa: F401
    from gothi.sdl_frontend import Layout
except ImportError:                                               # no PySDL2 on this computer: the layout is not tested
    Layout = None


@unittest.skipIf(Layout is None, "needs PySDL2")
class TouchLayoutTest(unittest.TestCase):
    def test_every_button_can_be_hit_and_ok_is_the_centre(self):
        lay = Layout("touch")
        for k in (keys.UP, keys.DOWN, keys.LEFT, keys.RIGHT, keys.BACK):
            x, y, w, h = lay.buttons[k]
            px = {keys.LEFT: x + 3, keys.RIGHT: x + w - 3}.get(k, x + w // 2)             # the outer end of each arm
            py = {keys.UP: y + 3, keys.DOWN: y + h - 3}.get(k, y + h // 2)
            self.assertEqual(lay.hit(px, py), k, k)
        x, y, w, h = lay.buttons[keys.OK]
        self.assertEqual(lay.hit(x + w // 2, y + h // 2), keys.OK)        # the centre of the cross
        self.assertEqual(lay.hit(x + w // 2, y + h // 2 - 40), keys.UP)
        self.assertIsNone(lay.hit(5, 5))


class ActionTest(unittest.TestCase):
    def mod(self, d, **over):
        m = {"title": "Sync", "type": "action", "run": "echo before; echo a-very-long-line-that-will-not-fit-the-screen-of-the-flipper-at-all; echo after",
             "info": "echo now", "deed": "act", "deeds": {"act": {"group": "modules", "xp": 3}}}
        m.update(over)
        make_module(d, "act", m)
        return mod.discover([d])

    def test_action_runs_shows_output_wrapped_and_scrolls(self):
        with tempfile.TemporaryDirectory() as d:
            mods, errs = self.mod(d)
            self.assertEqual(errs, [])
            st = dol.DolphinState(dol.load_rules(user_path=os.devnull, extra=[{"deeds": mods[0].deeds}]), path="", now=T0)
            sc = mod.Action(mods[0], spawn=lambda f: f())
            g = Gothi(sc, Settings(os.devnull), st)
            sc.on_enter(g)
            self.assertEqual(sc.rows(g)[:2], ["OK = run", "now"])
            g.key(keys.OK)
            rows = sc.rows(g)
            self.assertEqual(rows[0], "done")
            self.assertIn("before", rows)
            self.assertGreater(len([r for r in rows if r.startswith("a-very") or r.startswith("-") or r]), 4)
            self.assertTrue(all(Canvas(1, 1).text_width(r) <= 118 for r in rows))     # nothing is wider than the screen
            g.tick(T0)
            self.assertEqual(st.xp, 3)
            g.draw(Canvas())
            for _ in range(len(rows)):
                g.key(keys.DOWN)
            g.draw(Canvas())
            self.assertGreater(sc.top, 0)

    def test_failed_action_and_bad_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            mods, _ = self.mod(d, run="echo oops; exit 4")
            sc = mod.Action(mods[0], spawn=lambda f: f())
            g = Gothi(sc, Settings(os.devnull))
            g.key(keys.OK)
            self.assertEqual(sc.rows(g)[0], "failed (4)")
            self.assertEqual(g.dolphin.xp, 0)                                # a failure earns nothing
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.mod(d, timeout=0)[1][0][0], "act")        # a module with a bad timeout is reported
