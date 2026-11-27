"""Tests of the core, no display needed:  python3 -m unittest discover -s tests"""
import os
import sys
import random
import threading
import time
import struct
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gothi import flipper, keys  # noqa: E402
from gothi.apps import Clock, main_menu  # noqa: E402
from gothi.canvas import Canvas  # noqa: E402
from gothi.apps import ColorScene, Keys, Message, SettingsScene  # noqa: E402
from gothi import dolphin as dol  # noqa: E402
from gothi.apps import Stats  # noqa: E402
from gothi import modules as mod  # noqa: E402
from gothi.settings import PRESETS, Settings  # noqa: E402
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
    os.makedirs(os.path.join(base, name), exist_ok=True)
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

    def test_dir_placeholder_in_commands(self):
        make_module(self.d, "srv", dict(GOOD, status="test -f {dir}/module.json"))
        m = mod.discover([self.d])[0][0]
        self.assertTrue(mod.run_cmd(m.cmds["status"])[0] == 0)

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
    from gothi.sdl_frontend import Layout, map_key
except ImportError:                                               # no PySDL2 on this computer: the layout is not tested
    Layout = map_key = None


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


class LevelTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.d = self.t.name
        self.f = os.path.join(self.d, "val")
        open(self.f, "w").write("40\n")

    def tearDown(self):
        self.t.cleanup()

    def mod(self, **over):
        m = {"title": "Vol", "type": "level", "menu": "settings", "get": f"cat {self.f}", "set": f"echo {{value}} > {self.f}", "min": 0, "max": 100, "step": 5, "unit": "%",
             "deed": "vol", "deeds": {"vol": {"group": "settings", "xp": 1}}}
        m.update(over)
        make_module(self.d, "vol", m)
        return mod.discover([self.d])

    def test_level_reads_changes_clamps_and_writes(self):
        mods, errs = self.mod()
        self.assertEqual(errs, [])
        t = [0.0]
        sc = mod.Level(mods[0], spawn=lambda f: f(), clock=lambda: t[0])
        g = Gothi(sc, Settings(os.devnull))
        sc.on_enter(g)
        self.assertEqual(sc.value, 40)
        g.key(keys.RIGHT)
        self.assertEqual((sc.value, open(self.f).read().strip()), (45, "45"))
        g.key(keys.LEFT)
        g.key(keys.DOWN)
        self.assertEqual(open(self.f).read().strip(), "35")
        for _ in range(30):
            g.key(keys.RIGHT)
        self.assertEqual((sc.value, open(self.f).read().strip()), (100, "100"))     # clamped at max
        c = Canvas()
        g.draw(c)
        self.assertGreater(sum(c.px), 40)
        g.tick(100.0)
        self.assertEqual(g.dolphin.xp, 0)                                           # no such deed in this state's rules
        g.key(keys.BACK)

    def test_one_deed_per_visit_and_readback_does_not_fight_the_user(self):
        mods, _ = self.mod()
        st = dol.DolphinState(dol.load_rules(user_path=os.devnull, extra=[{"deeds": mods[0].deeds}]), path="", now=T0)
        t = [0.0]
        sc = mod.Level(mods[0], spawn=lambda f: f(), clock=lambda: t[0])
        g = Gothi(sc, Settings(os.devnull), st)
        sc.on_enter(g)
        g.key(keys.RIGHT)
        g.key(keys.RIGHT)
        g.tick(10.0)
        g.key(keys.RIGHT)
        g.tick(20.0)
        self.assertEqual(st.xp, 1)
        open(self.f, "w").write("5\n")                                              # something else changed it a moment ago ...
        t[0] = 1.0
        sc._read()
        self.assertEqual(sc.value, 55)                                              # ... the user's choice is kept for HOLD seconds
        t[0] = 10.0
        sc._read()
        self.assertEqual(sc.value, 5)

    def test_last_value_wins_while_a_set_runs(self):
        mods, _ = self.mod()
        pending = []
        sc = mod.Level(mods[0], spawn=pending.append)
        g = Gothi(sc, Settings(os.devnull))
        sc.value = 40
        for _ in range(3):
            g.key(keys.RIGHT)                                                        # the setter has not run yet
        self.assertEqual(len(pending), 1)                                            # only one is started
        pending.pop()()
        self.assertEqual(open(self.f).read().strip(), "55")

    def test_bad_level_and_requires_and_menu(self):
        self.assertEqual(self.mod(min=10, max=5)[1][0][0], "vol")
        self.assertEqual(self.mod(step=0)[1][0][0], "vol")
        self.assertEqual(self.mod(menu="nowhere")[1][0][0], "vol")
        with tempfile.TemporaryDirectory() as d2:
            make_module(d2, "x", {"title": "X", "type": "level", "get": "true", "set": "true", "requires": ["/definitely/not/here"]})
            self.assertEqual(mod.discover([d2]), ([], []))                           # a missing tool: no module, no error
            make_module(d2, "y", {"title": "Y", "type": "level", "get": "true", "set": "true", "requires": ["/bin/sh"]})
            self.assertEqual([m.id for m in mod.discover([d2])[0]], ["y"])

    def test_settings_lists_modules_scrolls_and_opens_them(self):
        mods, _ = self.mod()
        others = []
        for i in range(6):
            make_module(self.d, f"s{i}", {"title": f"Switch {i}", "type": "switch", "menu": "settings", "status": "false", "start": "true", "stop": "true"})
        mods, _ = mod.discover([self.d])
        sm = [m for m in mods if m.menu == "settings"]
        g = Gothi(SettingsScene(sm), Settings(os.devnull))
        n = len(g.top.rows(g))
        self.assertEqual(n, 5 + len(sm))
        seen = set()
        for _ in range(n):
            c = Canvas()
            g.draw(c)
            seen.add(bytes(c.px))
            g.key(keys.DOWN)
        self.assertGreater(len(seen), 3)                                             # the list scrolled
        g.stack[0].sel = 5
        g.key(keys.OK)
        self.assertIn(g.top.__class__.__name__, ("Level", "Switch"))
        g.draw(Canvas())
        g.key(keys.BACK)
        self.assertEqual(g.top.__class__.__name__, "SettingsScene")

    def test_bundled_modules_are_valid(self):
        import json
        import shutil
        here = os.path.join(os.path.dirname(__file__), "..", "modules")
        tmp = os.path.join(self.d, "b")
        for n in os.listdir(here):                                                    # requires is not checked here: the tools are not on this computer
            shutil.copytree(os.path.join(here, n), os.path.join(tmp, n), ignore=shutil.ignore_patterns("__pycache__"))
            with open(os.path.join(tmp, n, "module.json")) as f:
                data = json.load(f)
            data["requires"] = []
            with open(os.path.join(tmp, n, "module.json"), "w") as f:
                json.dump(data, f)
        mods, errs = mod.discover([tmp])
        self.assertEqual(errs, [])
        self.assertEqual({m.id for m in mods}, {"volume", "brightness", "bluetooth", "wifi", "wifi-scan", "flashlight", "bluetooth-scan", "sensors"})
        self.assertTrue(all(m.menu == "settings" for m in mods if m.id not in ("wifi-scan", "flashlight", "bluetooth-scan", "sensors")))
        self.assertEqual({m.id: m.menu for m in mods}["wifi-scan"], "modules")
        self.assertEqual({m.id: m.menu for m in mods}["flashlight"], "modules")
        self.assertEqual({m.id: m.menu for m in mods}["bluetooth-scan"], "modules")


class MonitorTest(unittest.TestCase):
    def mon(self, run, **over):
        d = tempfile.mkdtemp()
        make_module(d, "m", dict({"title": "Mon", "type": "monitor", "run": run, "deed": "mon", "deeds": {"mon": {"group": "modules", "xp": 1}}}, **over))
        m = mod.discover([d])[0][0]
        st = dol.DolphinState(dol.load_rules(user_path=os.devnull, extra=[{"deeds": m.deeds}]), path="", now=T0)
        sc = mod.Monitor(m, spawn=lambda f: f())
        return sc, Gothi(sc, Settings(os.devnull), st), st

    def test_last_complete_block_is_shown_and_a_deed_given(self):
        sc, g, st = self.mon("echo one; echo two; echo; echo three; echo four; echo")
        g.top.on_enter(g)                                    # the command ends at once: all its output is read
        self.assertEqual(sc.frame, ["three", "four"])
        self.assertEqual(sc.rows(g), ["three", "four", "stopped (0)"])
        g.tick(T0)
        g.tick(T0)
        self.assertEqual(st.xp, 1)                           # once
        g.draw(Canvas())

    def test_block_without_final_empty_line_and_failed_command(self):
        sc, g, _ = self.mon("echo only; exit 3")
        g.top.on_enter(g)
        self.assertEqual(sc.rows(g), ["only", "stopped (3)"])
        sc2, g2, _ = self.mon("exit 1")
        g2.top.on_enter(g2)
        self.assertEqual(sc2.rows(g2), ["stopped (1)"])

    def test_leaving_stops_the_command_and_its_children(self):
        flag = os.path.join(tempfile.mkdtemp(), "alive")
        run = f"trap 'echo bye > {flag}; exit 0' TERM; echo started; echo; while true; do sleep 0.1; done"
        sc, g, _ = self.mon(run)
        sc.spawn = lambda f: threading.Thread(target=f, daemon=True).start()
        g.top.on_enter(g)
        for _ in range(50):
            if sc.frame:
                break
            time.sleep(0.05)
        self.assertEqual(sc.frame, ["started"])
        g.stack = [Menu("root", [("m", lambda gg: sc)]), sc]
        g.pop()                                              # leave the page
        for _ in range(60):
            if sc.proc.poll() is not None:
                break
            time.sleep(0.05)
        self.assertIsNotNone(sc.proc.poll())
        self.assertEqual(open(flag).read().strip(), "bye")    # it got SIGTERM and could clean up
        self.assertNotIn(sc, mod._live)


class AskTest(unittest.TestCase):
    def ask(self, run="echo \"You said: $GOTHI_INPUT\"", **over):
        d = tempfile.mkdtemp()
        make_module(d, "a", dict({"title": "Ask", "type": "ask", "run": run, "hint": "what is it", "deed": "ask", "deeds": {"ask": {"group": "modules", "xp": 1}}}, **over))
        m = mod.discover([d])[0][0]
        st = dol.DolphinState(dol.load_rules(user_path=os.devnull, extra=[{"deeds": m.deeds}]), path="", now=T0)
        sc = mod.Ask(m, spawn=lambda f: f())
        return sc, Gothi(sc, Settings(os.devnull), st), st

    def test_typing_backspace_and_limits(self):
        sc, g, _ = self.ask()
        g.text("hel")
        g.text("lx")
        g.text("\b")
        g.text("o 'q' $x")
        self.assertEqual(sc.text, "hello 'q' $x")
        g.text("é")                                              # any printable character, also non-ASCII
        g.text("\n")                                             # Enter is a key (OK), not text
        self.assertTrue(sc.text.endswith("é"))
        g.text("x" * 500)
        self.assertEqual(len(sc.text), sc.MAX_QUESTION)
        g.draw(Canvas())

    def test_question_reaches_the_command_safely_and_answer_is_shown(self):
        sc, g, st = self.ask()
        g.key(keys.OK)                                           # nothing typed: nothing asked
        self.assertEqual(sc.phase, "input")
        g.text("a \"quoted\" $(echo hacked) `x` question")
        g.key(keys.OK)
        self.assertEqual(sc.phase, "answer")
        self.assertEqual(sc.answer.strip(), "You said: a \"quoted\" $(echo hacked) `x` question")   # the text is data, never part of the shell command
        self.assertTrue(sc.done)
        c = Canvas()
        g.draw(c)
        self.assertGreater(sum(c.px), 100)
        g.tick(T0)
        g.tick(T0)
        self.assertEqual(st.xp, 1)
        g.key(keys.OK)                                           # again: back to typing, the text is kept for editing
        self.assertEqual((sc.phase, sc.text_input), ("input", True))
        self.assertTrue(sc.text.startswith("a "))
        g.key(keys.BACK)
        self.assertEqual(g.stack, [sc])                          # the only scene: nothing to pop, but no crash

    def test_text_goes_only_to_scenes_that_type_and_long_answers_scroll(self):
        sc, g, _ = self.ask(run="i=1; while [ $i -le 40 ]; do echo \"line number $i of a long answer\"; i=$((i+1)); done")
        g.text("go")
        g.key(keys.OK)
        g.text("ignored while the answer shows")
        self.assertEqual(sc.text, "go")
        first = Canvas()
        g.draw(first)
        for _ in range(100):
            g.key(keys.DOWN)
        last = Canvas()
        g.draw(last)
        self.assertNotEqual(bytes(first.px), bytes(last.px))
        for _ in range(100):
            g.key(keys.UP)
        self.assertEqual(sc.top, 0)
        m = Gothi(main_menu(([], [])))
        m.text("x")                                              # the menu does not type: ignored
        m.draw(Canvas())

    def test_leaving_stops_the_command_and_touch_mode_says_to_slide_out(self):
        flag = os.path.join(tempfile.mkdtemp(), "f")
        sc, g, _ = self.ask(run=f"trap 'echo stopped > {flag}; exit 0' TERM; echo thinking; while true; do sleep 0.1; done")
        sc.spawn = lambda f: threading.Thread(target=f, daemon=True).start()
        g.stack = [Menu("root", [("a", lambda gg: sc)]), sc]
        g.text("q")
        g.key(keys.OK)
        for _ in range(50):
            if "thinking" in sc.answer:
                break
            time.sleep(0.05)
        self.assertIn("thinking", sc.answer)
        g.key(keys.BACK)                                         # to the question
        for _ in range(60):
            if sc.p.proc.poll() is not None:
                break
            time.sleep(0.05)
        self.assertIsNotNone(sc.p.proc.poll())
        self.assertEqual(open(flag).read().strip(), "stopped")
        g.mode = "touch"
        c = Canvas()
        g.draw(c)
        self.assertGreater(sum(c.px), 50)

    def test_missing_animation_still_draws_and_bad_names_are_rejected(self):
        sc, g, _ = self.ask(animation="No_Such_Animation_1x1")
        g.text("hi")
        g.key(keys.OK)
        g.draw(Canvas())
        self.assertIsNone(sc.m.animation)                        # the module goes on without it
        sc2, _, _ = self.ask(animation="../../etc")
        self.assertIsNone(sc2.m.animation)                       # no path tricks


@unittest.skipIf(Layout is None, "needs PySDL2")
class KeyMapTest(unittest.TestCase):
    def test_space_is_ok_except_while_typing(self):
        import sdl2
        self.assertEqual(map_key(sdl2.SDLK_SPACE), keys.OK)                 # in menus the space bar is OK
        self.assertIsNone(map_key(sdl2.SDLK_SPACE, typing=True))            # in a text field it is a space (it comes as text input)
        self.assertEqual(map_key(sdl2.SDLK_RETURN, typing=True), keys.OK)   # Enter still asks
        self.assertEqual(map_key(sdl2.SDLK_ESCAPE, typing=True), keys.BACK)
        self.assertIsNone(map_key(sdl2.SDLK_a))


class SwitchExtrasTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.d = self.t.name
        self.flag = os.path.join(self.d, "on")
        self.val = os.path.join(self.d, "val")
        open(self.val, "w").write("90500\n")
        self.home = os.environ.get("HOME")
        os.environ["HOME"] = self.d                              # the timer files go to ~/.cache/gothi

    def tearDown(self):
        os.environ["HOME"] = self.home
        self.t.cleanup()

    def sw(self, **over):
        man = {"title": "Radio", "type": "switch", "status": f"test -f {self.flag}", "start": f"touch {self.flag}", "stop": f"rm -f {self.flag}",
               "info": "echo extra", "labels": {"on": "ON AIR"},
               "level": {"get": f"cat {self.val}", "set": f"echo {{value}} > {self.val}", "min": 88100, "max": 107900, "step": 100, "unit": "MHz",
                         "divisor": 1000, "decimals": 1}}
        man.update(over)
        make_module(self.d, "radio", man)
        mods, errs = mod.discover([self.d])
        self.assertEqual(errs, [], errs)
        sc = mod.Switch(mods[0], spawn=lambda f: f())
        return sc, Gothi(sc, Settings(os.devnull))

    def test_level_on_the_same_screen_and_label(self):
        sc, g = self.sw()
        sc.on_enter(g)
        self.assertEqual(sc.sub.value, 90500)
        self.assertEqual(mod._fmt_value(sc.sub.m, 90500), "90.5 MHz")
        g.key(keys.RIGHT)
        g.key(keys.RIGHT)
        g.key(keys.LEFT)
        self.assertEqual(open(self.val).read().strip(), "90600")
        g.key(keys.OK)
        self.assertTrue(sc.on)
        c = Canvas()
        g.draw(c)
        self.assertGreater(sum(c.px), 100)
        g.draw(Canvas(h=80))

    def test_confirm_is_asked_before_every_start_and_back_says_no(self):
        sc, g = self.sw(confirm="It will transmit. Sure?")
        sc.on_enter(g)
        g.key(keys.OK)
        self.assertTrue(sc.asking)
        self.assertFalse(os.path.exists(self.flag))              # nothing started yet
        g.draw(Canvas())
        g.key(keys.BACK)                                         # no: the screen stays, nothing runs
        self.assertEqual((sc.asking, os.path.exists(self.flag), g.stack), (False, False, [sc]))
        g.key(keys.OK)
        g.key(keys.OK)                                           # yes
        self.assertTrue(os.path.exists(self.flag))
        g.key(keys.OK)                                           # stopping needs no question
        self.assertFalse(os.path.exists(self.flag))
        g.key(keys.OK)
        self.assertTrue(sc.asking)                               # the next start asks again

    def test_auto_off_runs_detached_and_a_manual_stop_cancels_it(self):
        sc, g = self.sw(auto_off=1, level=None)
        sc.on_enter(g)
        g.key(keys.OK)
        self.assertTrue(os.path.exists(self.flag))
        self.assertTrue(any("auto-off in" in x for x in sc.info))
        time.sleep(2.0)
        self.assertFalse(os.path.exists(self.flag))              # the timer switched it off
        g.key(keys.OK)                                           # on again, now stop by hand before the timer
        sc.m.auto_off = 3
        g.key(keys.OK)
        g.key(keys.OK)
        self.assertFalse(os.path.exists(self.flag))
        sc.m.auto_off = 1
        g.key(keys.OK)
        g.key(keys.OK)                                           # started and stopped: the timer must be gone
        open(self.flag, "w").close()                             # something else switches it on afterwards ...
        time.sleep(1.6)
        self.assertTrue(os.path.exists(self.flag))               # ... and the cancelled timer does not touch it

    def test_bad_extras_are_rejected(self):
        for bad in ({"auto_off": -1}, {"auto_off": "soon"}, {"labels": "x"}, {"level": {"get": "x"}},
                    {"level": {"get": "x", "set": "y", "min": 5, "max": 1}}, {"level": {"get": "x", "set": "y", "divisor": 0}}):
            with tempfile.TemporaryDirectory() as d2:
                man = {"title": "R", "type": "switch", "status": "true", "start": "true", "stop": "true"}
                man.update(bad)
                make_module(d2, "r", man)
                self.assertEqual(len(mod.discover([d2])[1]), 1, bad)


class PythonModuleTest(unittest.TestCase):
    def mk(self, code, **over):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "py"))
        open(os.path.join(d, "py", "module.py"), "w").write(code)
        open(os.path.join(d, "py", "helper_for_test.py"), "w").write("VALUE = 'from the helper'\n")
        man = dict({"title": "Py", "type": "python", "entry": "module.py"}, **over)
        open(os.path.join(d, "py", "module.json"), "w").write(__import__("json").dumps(man))
        return mod.discover([d])

    def test_create_gives_the_scene_and_siblings_can_be_imported(self):
        mods, errs = self.mk("from gothi.apps import Message\nimport helper_for_test\ndef create(module):\n    return Message(module.title, [helper_for_test.VALUE])\n")
        self.assertEqual(errs, [])
        sc = mod.scene_for(mods[0])
        self.assertEqual(sc.lines, ["from the helper"])
        g = Gothi(sc, Settings(os.devnull))
        g.draw(Canvas())

    def test_errors_in_the_module_become_a_page_not_a_crash(self):
        for code in ("raise RuntimeError('boom at import')\n", "def create(module):\n    raise ValueError('boom in create')\n", "x = 1\n"):
            mods, _ = self.mk(code)
            sc = mod.scene_for(mods[0])
            self.assertEqual(sc.title, "Py")
            self.assertEqual(sc.lines[0], "module failed:")
            Gothi(sc, Settings(os.devnull)).draw(Canvas())

    def test_entry_must_be_a_plain_file_next_to_the_manifest(self):
        for bad in ("../module.py", "sub/module.py", "module.txt", "", None, 5, "nothere.py"):
            self.assertEqual(len(self.mk("def create(m): pass\n", entry=bad)[1]), 1, bad)


def tap(g, x, y):
    g.touch("down", x, y)
    g.touch("up", x, y)


def swipe(g, x, y0, y1, steps=4):
    g.touch("down", x, y0)
    for i in range(1, steps + 1):
        g.touch("move", x, y0 + (y1 - y0) * i // steps)
    g.touch("up", x, y1)


def touch_gothi(root, on=True, h=None):
    st = Settings(os.devnull)
    st["touch_screen"] = on
    if h:
        st["screen"] = "tall"
    g = Gothi(root, st)
    return g


class TouchScreenTest(unittest.TestCase):
    def menu(self, n=10, **kw):
        opened = []
        items = [(f"Item {i}", (lambda gg, i=i: opened.append(i) or Menu(f"Sub {i}", []))) for i in range(n)]
        m = Menu("Main", items, **kw)
        return m, opened

    def test_scenes_get_the_finger_down_and_up_even_when_it_drags(self):
        from gothi.ui import Scene

        class Rec(Scene):
            def __init__(self):
                self.log = []

            def on_down(self, x, y, gothi):
                self.log.append(("down", x, y))

            def on_up(self, x, y, gothi):
                self.log.append(("up", x, y))

            def on_tap(self, x, y, gothi):
                self.log.append(("tap", x, y))
        r = Rec()
        g = touch_gothi(r)
        tap(g, 30, 30)
        swipe(g, 40, 50, 10)
        self.assertEqual(r.log, [("down", 30, 30), ("up", 30, 30), ("tap", 30, 30), ("down", 40, 50), ("up", 40, 10)])
        off = Rec()
        g = touch_gothi(off, on=False)
        tap(g, 30, 30)
        self.assertEqual(off.log, [])                                # the setting is off: no finger at all

    def test_key_repeat_flag_defaults_to_false(self):
        self.assertFalse(Gothi(Menu("m", [])).key_repeat)

    def test_nothing_happens_when_the_setting_is_off(self):
        m, opened = self.menu()
        g = touch_gothi(Menu("root", [("m", lambda gg: m)]), on=False)
        g.key(keys.OK)
        tap(g, 40, 14)
        tap(g, 40, 14)
        swipe(g, 40, 50, 10)
        tap(g, 40, 3)
        self.assertEqual((opened, m.sel, m.top_row, g.top is m), ([], 0, 0, True))

    def test_menu_first_tap_selects_second_opens_and_the_title_is_back(self):
        m, opened = self.menu()
        g = touch_gothi(Menu("root", [("m", lambda gg: m)]))
        g.key(keys.OK)
        tap(g, 40, 14 + 12 * 2)                                  # the third row
        self.assertEqual((m.sel, opened), (2, []))
        tap(g, 40, 14 + 12 * 2)
        self.assertEqual((opened, g.top.title), ([2], "Sub 2"))
        tap(g, 20, 4)                                            # the title bar: Back
        self.assertIs(g.top, m)
        tap(g, 40, 6)                                            # again from the menu: Back to the root
        self.assertEqual(g.top.title, "root")

    def test_taps_between_rows_and_below_the_last_do_nothing(self):
        m, opened = self.menu(n=2)
        g = touch_gothi(m)
        tap(g, 40, 11)                                           # between the title bar and the first row
        self.assertEqual(m.sel, 0)
        tap(g, 40, 12 + 12 * 3)                                  # no fourth item
        self.assertEqual((m.sel, opened), (0, []))
        tap(g, 40, 60)
        self.assertEqual(m.sel, 0)

    def test_tap_activates_opens_at_once(self):
        m, opened = self.menu()
        m.tap_activates = True
        g = touch_gothi(m)
        tap(g, 40, 14 + 12)
        self.assertEqual(opened, [1])

    def test_small_movement_is_still_a_tap_and_a_drag_is_not(self):
        m, opened = self.menu()
        g = touch_gothi(m)
        g.touch("down", 40, 26)
        g.touch("move", 41, 27)                                  # a resistive screen jitters
        g.touch("move", 40, 25)
        g.touch("up", 40, 26)
        self.assertEqual(m.sel, 1)
        swipe(g, 40, 40, 10)                                     # a real drag: no tap at the end
        self.assertEqual(m.sel, 1 if m.top_row == 0 else m.sel)
        self.assertGreater(m.top_row, 0)

    def test_drag_scrolls_the_list_and_keeps_the_selection_visible(self):
        m, _ = self.menu(n=12)
        g = touch_gothi(m)
        swipe(g, 40, 50, 14, steps=6)                            # up by 36 px = three rows of 12
        self.assertEqual(m.top_row, 3)
        self.assertTrue(m.top_row <= m.sel < m.top_row + 4)
        swipe(g, 40, 14, 120, steps=10)                          # a long way down: stops at the top
        self.assertEqual(m.top_row, 0)
        for _ in range(3):
            swipe(g, 40, 60, 0, steps=20)
        self.assertEqual(m.top_row, 12 - 4)                      # and at the end (four rows are visible)

    def test_tall_screen_has_more_rows_to_tap(self):
        m, opened = self.menu(n=10)
        g = touch_gothi(m, h=80)
        g.h = 80
        tap(g, 40, 12 + 12 * 4 + 2)                              # the fifth row exists on the tall screen
        tap(g, 40, 12 + 12 * 4 + 2)
        self.assertEqual(opened, [4])

    def test_icon_rows_are_16_pixels(self):
        m = Menu("Icons", [(f"I{i}", (lambda gg: Menu("x", [])), "icons/MainMenu/Settings_14") for i in range(6)])
        if m.ROW != 16:
            self.skipTest("no firmware graphics here")
        g = touch_gothi(m)
        tap(g, 40, 12 + 16 + 3)
        self.assertEqual(m.sel, 1)

    def test_scrollview_follows_the_finger(self):
        sv = Stats()
        g = touch_gothi(sv)
        self.assertEqual(sv.top, 0)
        swipe(g, 40, 50, 20, steps=5)                            # 30 px = three rows of 10
        self.assertEqual(sv.top, 3)
        swipe(g, 40, 20, 100, steps=8)
        self.assertEqual(sv.top, 0)

    def test_settings_rows_tap_toggle_drag_and_open_a_module(self):
        with tempfile.TemporaryDirectory() as t:
            make_module(t, "w", {"title": "Wifi", "type": "switch", "menu": "settings", "status": "false", "start": "true", "stop": "true"})
            mods = mod.discover([t])[0]
            st = Settings(os.path.join(t, "s.json"))
            st["touch_screen"] = True
            g = Gothi(Menu("root", [("s", lambda gg: SettingsScene(mods))]), st)
            g.key(keys.OK)
            sc = g.top
            y = lambda i: 11 + 12 * i + 5
            tap(g, 40, y(3))                                     # Happy mode: selects
            self.assertEqual((sc.sel, st["happy"]), (3, False))
            tap(g, 40, y(3))                                     # selected: toggles
            self.assertTrue(st["happy"])
            swipe(g, 40, 50, 14, steps=6)                        # scroll to the rows below
            self.assertGreater(sc.top, 0)
            self.assertTrue(sc.top <= sc.sel < sc.top + 4)
            sc.top, sc.sel = 2, 5                                # the row "Wifi" is the sixth (index 5); it is the fourth visible row from top 2
            tap(g, 40, y(3))
            self.assertEqual(g.top.__class__.__name__, "Switch")
            tap(g, 10, 3)
            self.assertIs(g.top, sc)
            # the new switch of the touch itself
            sc.top, sc.sel = 1, 4                                # scrolled by one: "Tap the screen" is the fourth visible row
            tap(g, 40, y(3))
            self.assertFalse(st["touch_screen"])                 # one can switch it off by touch (and on again with the keys)
            self.assertFalse(Settings(os.path.join(t, "s.json"))["touch_screen"])

    def test_colour_bar_tap_sets_the_channel(self):
        with tempfile.TemporaryDirectory() as t:
            st = Settings(os.path.join(t, "s.json"))
            st["touch_screen"] = True
            g = Gothi(ColorScene(), st)
            tap(g, 100, 11 + 13 * 1 + 5)                         # the red bar, near its right end
            self.assertGreater(st.color[0], 240)
            tap(g, 31, 11 + 13 * 2 + 5)                          # green: the left end
            self.assertEqual(st.color[1], 0)
            tap(g, 66, 11 + 13 * 3 + 5)                          # blue: the middle
            self.assertTrue(120 < st.color[2] < 135)
            tap(g, 100, 11 + 5)                                  # the preset row: right half = Right (from a custom colour: the first preset)
            self.assertEqual(st.color, PRESETS[0][1])

    def test_message_and_player_and_keys(self):
        g = touch_gothi(Menu("root", [("m", lambda gg: Message("Hi", ["one"]))]))
        g.key(keys.OK)
        tap(g, 50, 30)
        self.assertEqual(g.top.title, "root")                    # a tap closes a message
        k = Keys()
        g = touch_gothi(Menu("root", [("k", lambda gg: k)]))
        g.key(keys.OK)
        tap(g, 33, 44)
        swipe(g, 40, 50, 10)
        self.assertEqual(k.last[0], "tap 33,44")
        self.assertIn("drag", k.last)
        g.draw(Canvas())


class TouchModuleScenesTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.d = self.t.name
        self.flag = os.path.join(self.d, "on")
        self.val = os.path.join(self.d, "val")
        open(self.val, "w").write("50\n")

    def tearDown(self):
        self.t.cleanup()

    def mk(self, kind, **over):
        man = {"title": "T", "type": kind}
        if kind == "switch":
            man.update(status=f"test -f {self.flag}", start=f"touch {self.flag}", stop=f"rm -f {self.flag}", info="echo a; echo b; echo c; echo d; echo e; echo f")
        elif kind == "level":
            man.update(get=f"cat {self.val}", set=f"echo {{value}} > {self.val}", min=0, max=100, step=10)
        elif kind == "action":
            man.update(run=f"touch {self.flag}; echo ran")
        elif kind == "ask":
            man.update(run="echo \"answer: $GOTHI_INPUT\"")
        man.update(over)
        make_module(self.d, "t", man)
        mods, errs = mod.discover([self.d])
        self.assertEqual(errs, [], errs)
        return mods[0]

    def test_switch_taps_toggle_level_ends_confirm_and_info_drag(self):
        m = self.mk("switch", level={"get": f"cat {self.val}", "set": f"echo {{value}} > {self.val}", "min": 0, "max": 100, "step": 10}, confirm="Sure?")
        sc = mod.Switch(m, spawn=lambda f: f())
        g = touch_gothi(sc)
        sc.on_enter(g)
        tap(g, 60, 20)                                           # the big state: asks
        self.assertTrue(sc.asking)
        tap(g, 100, g.h - 4)                                     # the right half of the bottom line: no
        self.assertFalse(sc.asking)
        self.assertFalse(os.path.exists(self.flag))
        tap(g, 60, 20)
        tap(g, 20, g.h - 4)                                      # yes
        self.assertTrue(os.path.exists(self.flag))
        tap(g, 100, 40)                                          # the right end of the level line
        self.assertEqual(open(self.val).read().strip(), "60")
        tap(g, 10, 40)
        tap(g, 10, 40)
        self.assertEqual(open(self.val).read().strip(), "40")
        tap(g, 64, 40)                                           # the middle of the line: nothing
        self.assertEqual(open(self.val).read().strip(), "40")
        tap(g, 60, 20)                                           # stop needs no question
        self.assertFalse(os.path.exists(self.flag))
        g.h = 80
        sc.on = True
        sc.info = [f"l{i}" for i in range(10)]
        swipe(g, 40, 70, 40, steps=6)
        self.assertGreater(sc.top, 0)

    def test_level_bar_and_halves(self):
        sc = mod.Level(self.mk("level"), spawn=lambda f: f(), clock=lambda: 0.0)
        g = touch_gothi(sc)
        sc.on_enter(g)
        self.assertEqual(sc.value, 50)
        tap(g, 20, 30)
        self.assertEqual(sc.value, 40)                           # the left half: less
        tap(g, 100, 30)
        tap(g, 100, 30)
        self.assertEqual(sc.value, 60)
        tap(g, 5, 47)                                            # the bar: the left end
        self.assertEqual(sc.value, 0)
        tap(g, 123, 47)
        self.assertEqual(sc.value, 100)
        tap(g, 64, 47)
        self.assertEqual(sc.value, 50)
        self.assertEqual(open(self.val).read().strip(), "50")
        g.draw(Canvas())

    def test_action_runs_on_a_tap_and_ask_answers_and_scrolls(self):
        sc = mod.Action(self.mk("action"), spawn=lambda f: f())
        g = touch_gothi(sc)
        tap(g, 40, 3)                                            # the title bar: Back (nothing to go back to here)
        self.assertFalse(os.path.exists(self.flag))
        tap(g, 40, 30)
        self.assertTrue(os.path.exists(self.flag))
        self.assertEqual(sc.rc, 0)
        a = mod.Ask(self.mk("ask", run="i=1; while [ $i -le 30 ]; do echo \"line $i of the answer\"; i=$((i+1)); done"), spawn=lambda f: f())
        g = touch_gothi(a)
        g.text("q")
        tap(g, 40, 30)                                           # typing: a tap does nothing
        self.assertEqual(a.phase, "input")
        g.key(keys.OK)
        swipe(g, 40, 60, 10, steps=6)
        self.assertGreater(a.top, 0)
        tap(g, 40, 30)                                           # a tap on the answer: ask again
        self.assertEqual(a.phase, "input")

    def test_dolphin_right_edge_is_next_and_the_rest_pets(self):
        from gothi.apps import Dolphin
        d = Dolphin.__new__(Dolphin)
        got = []
        d.key = lambda k, gg: got.append(k)
        d.on_tap(120, 30, None)
        d.on_tap(30, 30, None)
        self.assertEqual(got, [keys.RIGHT, keys.OK])


@unittest.skipIf(Layout is None, "needs PySDL2")
class TouchMappingTest(unittest.TestCase):
    def test_window_to_canvas_in_both_layouts(self):
        for mode, scale in (("keyboard", 6), ("touch", 4)):
            lay = Layout(mode)
            x, y, w, h = lay.screen
            self.assertEqual(lay.to_canvas(x, y), (0, 0))
            self.assertEqual(lay.to_canvas(x + 5 * scale + 1, y + 7 * scale + 2), (5, 7))
            self.assertEqual(lay.to_canvas(x + w - 1, y + h - 1), (127, 63))
            self.assertIsNone(lay.to_canvas(x - 1, y))
            self.assertIsNone(lay.to_canvas(x, y + h))
            self.assertEqual(lay.to_canvas(x - 50, y + h + 50, clamp=True), (0, 63))            # a finger that left the screen stays on its edge
        tall = Layout("keyboard", 80)
        self.assertEqual(tall.to_canvas(tall.screen[0], tall.screen[1] + 79 * 6 + 1), (0, 79))


class ScriptKeysTest(unittest.TestCase):
    def test_main_keeps_tap_and_swipe_items_of_the_key_script(self):
        # the script is split at commas: the items must not contain any
        import gothi.__main__ as m
        src = open(m.__file__).read()
        self.assertIn('startswith(("t:", "tap:", "swipe:"))', src)
        self.assertEqual("tap:64:30,swipe:64:50:10,ok".split(","), ["tap:64:30", "swipe:64:50:10", "ok"])
