"""Tests of gothi/sensors.py and of the bundled module modules/sensors with a fake sysfs tree (made-up readings):  python3 -m unittest discover -s tests"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from gothi import keys, modules as mod, sensors as sn  # noqa: E402
from gothi.canvas import Canvas  # noqa: E402
from gothi.dolphin import DolphinState, load_rules  # noqa: E402
from gothi.settings import Settings  # noqa: E402
from gothi.ui import Gothi  # noqa: E402

PATH = os.path.join(HERE, "..", "modules", "sensors")
spec = importlib.util.spec_from_file_location("sensors_module", os.path.join(PATH, "module.py"))
sm_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sm_mod)


class Tree:
    """A fake /sys in a temporary folder."""

    def __init__(self):
        self.root = tempfile.mkdtemp()

    def put(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text + "\n")

    def full(self, acc="18 -450 -918", lux="1492", switches=None):
        if acc is not None:
            self.put(sn.ACC, acc)
        if lux is not None:
            self.put(sn.LUX, lux)
        base = {"slide": "open", "kb_lock": "open", "cam_shutter": "open", "proximity": "open", "headphone": "disconnected", "cam_focus": "inactive",
                "cam_launch": "inactive"}
        base.update(switches or {})
        for f, state in base.items():
            self.put(f"{sn.SWITCH_DIR}/{f}/state", state)
        return self

    def __del__(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


class MathTest(unittest.TestCase):
    def test_parse_coord(self):
        self.assertEqual(sn.parse_coord("18 -450 -918"), (18, -450, -918))
        for bad in ("", None, "1 2", "a b c", "1 2 3 4"):
            self.assertIsNone(sn.parse_coord(bad))

    def test_magnitude_at_rest_is_one_g(self):
        self.assertAlmostEqual(sn.magnitude((0, 0, -1000)), 1.0)
        self.assertAlmostEqual(sn.magnitude((600, 800, 0)), 1.0)

    def test_tilt_angles_for_the_six_positions(self):
        self.assertEqual(tuple(round(a) for a in sn.tilt((0, 0, -1000))), (0, 0))        # flat face up
        self.assertEqual(tuple(round(a) for a in sn.tilt((0, 0, 1000))), (0, 0))         # flat face down
        self.assertEqual(round(sn.tilt((1000, 0, 0))[0]), 90)                            # on its side
        self.assertEqual(round(sn.tilt((-1000, 0, 0))[0]), -90)
        self.assertEqual(round(sn.tilt((0, 1000, 0))[1]), 90)                            # upright
        self.assertEqual(round(sn.tilt((0, -1000, 0))[1]), -90)
        self.assertEqual(round(sn.tilt((500, 0, -866))[0]), 30)
        self.assertEqual(sn.tilt((0, 0, 0)), (0.0, 0.0))                                 # no reading is not a division by zero

    def test_position_words(self):
        self.assertEqual(sn.position((10, 20, -990)), "face up")
        self.assertEqual(sn.position((10, 20, 990)), "face down")
        self.assertEqual(sn.position((10, -990, 20)), "landscape")
        self.assertEqual(sn.position((10, 990, 20)), "landscape flipped")
        self.assertEqual(sn.position((990, 20, 10)), "portrait right up")
        self.assertEqual(sn.position((-990, 20, 10)), "portrait left up")
        self.assertTrue(all(len(sn.position(v)) <= 17 for v in ((0, 0, -9), (0, 0, 9), (0, -9, 0), (0, 9, 0), (9, 0, 0), (-9, 0, 0))))

    def test_bubble_stays_in_the_circle(self):
        self.assertEqual(sn.bubble((0, 0, -1000), 20), (0, 0))
        dx, dy = sn.bubble((500, 0, -866), 20)                                           # 30 degrees: at the edge
        self.assertEqual((dx, dy), (20, 0))
        for v in ((1000, 1000, 0), (-900, 900, 100), (0, -1000, 0)):
            dx, dy = sn.bubble(v, 20)
            self.assertLessEqual((dx * dx + dy * dy) ** 0.5, 20.6)
        self.assertEqual(sn.bubble((18, -450, -918), 20, zero=(18, -450))[0:2], (0, 0))   # the zero makes the tilt vanish

    def test_lux_words_and_bar(self):
        words = [sn.lux_word(x) for x in (None, 0, 5, 100, 1492, 20000)]
        self.assertEqual(words, ["?", "dark", "dim", "indoor", "bright", "sun"])
        self.assertEqual((sn.lux_bar(0), sn.lux_bar(None), sn.lux_bar(-3)), (0.0, 0.0, 0.0))
        self.assertEqual(sn.lux_bar(10 ** 6), 1.0)
        self.assertTrue(0 < sn.lux_bar(100) < sn.lux_bar(1000) < 1)

    def test_series_keeps_the_last_n(self):
        s = sn.Series(3)
        for i in range(5):
            s.add(i)
        self.assertEqual(s.values(), [2, 3, 4])

    def test_shake_detector(self):
        sh = sn.Shake()
        self.assertFalse(sh.update((0, 0, -1000), 0))                                   # at rest
        self.assertTrue(sh.update((0, 0, -2100), 1.0))
        self.assertFalse(sh.update((0, 0, -2100), 1.2))                                 # the same shake
        self.assertTrue(sh.update((0, 0, -2100), 1.6))
        self.assertEqual(sh.count, 2)
        self.assertFalse(sh.update((300, 300, -1100), 5.0))                             # a noisy table is not a shake

    def test_line_and_trace_draw_inside(self):
        c = Canvas()
        sn.line(c, 0, 0, 20, 10)
        self.assertEqual(c.px[0], 1)
        c2 = Canvas()
        sn.trace(c2, [0, 1000, 2500, 5000, -100], 10, 20, 30, 20, 0, 2500)
        self.assertTrue(any(c2.px))
        sn.trace(c2, [1], 0, 0, 5, 5, 0, 1)                                              # too short: nothing, no error
        sn.trace(c2, [1, 2], 0, 0, 5, 5, 1, 1)                                           # empty range: nothing, no error


class SamplerTest(unittest.TestCase):
    def make(self, **kw):
        t = Tree().full(**kw)
        clock = Clock()
        cfg = os.path.join(t.root, "config", "sensors.json")
        return t, clock, sn.Sensors(root=t.root, config=cfg, clock=clock)

    def test_reads_everything(self):
        t, clock, s = self.make()
        self.assertTrue(s.poll())
        self.assertEqual((s.acc, s.lux), ((18, -450, -918), 1492))
        self.assertEqual(s.switches["slide"], "open")
        self.assertEqual(s.present(), {"acc": True, "light": True, "switches": True})

    def test_missing_sensors_are_none_and_do_not_fail(self):
        t, clock, s = self.make(acc=None, lux=None)
        s.poll()
        self.assertEqual((s.acc, s.lux), (None, None))
        self.assertEqual(s.present()["acc"], False)
        empty = sn.Sensors(root=tempfile.mkdtemp(), config=os.devnull, clock=clock)
        empty.poll()
        self.assertEqual(empty.present(), {"acc": False, "light": False, "switches": False})

    def test_garbage_is_not_a_reading(self):
        t, clock, s = self.make(acc="oops", lux="x")
        s.poll()
        self.assertEqual((s.acc, s.lux), (None, None))

    def test_poll_waits_for_the_period(self):
        t, clock, s = self.make()
        self.assertTrue(s.poll())
        self.assertFalse(s.poll())
        clock.t += sn.PERIOD + 0.01
        self.assertTrue(s.poll())
        self.assertEqual(len(s.mag.values()), 2)

    def test_history_and_shake(self):
        t, clock, s = self.make(acc="0 0 -2300")
        s.poll()
        self.assertTrue(s.shook)
        self.assertEqual(s.shake.count, 1)
        clock.t += 1
        t.put(sn.ACC, "0 0 -1000")
        s.poll()
        self.assertFalse(s.shook)

    def test_switch_changes_are_logged_but_not_the_first_reading(self):
        t, clock, s = self.make()
        s.poll()
        self.assertEqual(s.log, [])
        t.put(f"{sn.SWITCH_DIR}/slide/state", "closed")
        t.put(f"{sn.SWITCH_DIR}/headphone/state", "connected")
        clock.t += 1
        s.poll()
        self.assertEqual({(n, st) for _, n, st in s.log}, {("slide", "closed"), ("jack", "connected")})
        clock.t += 1
        s.poll()
        self.assertEqual(len(s.log), 2)                                                  # nothing new, nothing logged again

    def test_log_is_limited(self):
        t, clock, s = self.make()
        s.poll()
        for i in range(sn.LOG_LINES + 10):
            t.put(f"{sn.SWITCH_DIR}/slide/state", "closed" if i % 2 == 0 else "open")
            clock.t += 1
            s.poll()
        self.assertEqual(len(s.log), sn.LOG_LINES)

    def test_zero_is_kept_in_the_config(self):
        t, clock, s = self.make()
        self.assertFalse(s.set_zero())                                                   # no reading yet
        s.poll()
        self.assertTrue(s.set_zero())
        again = sn.Sensors(root=t.root, config=s.config, clock=clock)
        self.assertEqual(again.zero, (18, -450))
        with open(s.config) as f:
            self.assertEqual(json.load(f), {"zero": [18, -450]})

    def test_broken_config_is_zero(self):
        t = Tree()
        for text in ("", "{", '{"zero": "x"}', '{"zero": [1]}'):
            t.put("c.json", text)
            self.assertEqual(sn.Sensors(root=t.root, config=os.path.join(t.root, "c.json")).zero, (0, 0))


def make(**kw):
    t = Tree().full(**kw)
    clock = Clock()
    sm = sn.Sensors(root=t.root, config=os.path.join(t.root, "c.json"), clock=clock)
    return t, clock, sm


def draw(scene, h=64):
    c = Canvas()
    c.h = h
    c.px = bytearray(c.w * h)
    g = Gothi(scene)
    g.h = h
    scene.draw(c, g)
    return c


class ScreensTest(unittest.TestCase):
    def test_manifest(self):
        with open(os.path.join(PATH, "module.json")) as f:
            data = json.load(f)
        data["requires"] = []
        m = mod.Module(PATH, data)
        self.assertEqual((m.kind, m.menu, m.deed), ("python", "modules", "sensors_view"))
        for d in ("sensors_view", "level_used", "shake"):
            self.assertIn(d, data["deeds"])

    def test_overview_rows(self):
        t, clock, sm = make()
        o = sm_mod.Overview(sm)
        g = Gothi(o)
        self.assertEqual(o.rows(g), ["reading..."])
        g.tick(clock())
        rows = o.rows(g)
        self.assertEqual(rows[:3], ["acc 18 -450 -918 mg", "1.02 g", "face up"])
        self.assertIn("light 1492 lx, bright", rows)
        self.assertIn("jack out", rows)
        self.assertTrue(all(len(r) <= 21 for r in rows))
        t.put(sn.ACC, "0 1000 -20")
        clock.t += 1
        g.tick(clock())
        self.assertTrue(all(len(r) <= 21 for r in o.rows(g)))                           # also with the longest position word
        for h in (64, 80):
            draw(o, h)

    def test_overview_without_sensors(self):
        t, clock, sm = make(acc=None, lux=None)
        o = sm_mod.Overview(sm)
        g = Gothi(o)
        g.tick(clock())
        self.assertEqual(o.rows(g)[:2], ["acc not available", "light not available"])
        draw(o)

    def test_level_sets_the_zero_and_the_bubble_centres(self):
        t, clock, sm = make()
        lv = sm_mod.Level(sm)
        g = Gothi(lv, Settings(os.devnull), DolphinState(load_rules(extra=[{"deeds": {"level_used": {"group": "modules", "xp": 1}}}]), path=""))
        draw(lv)                                                                        # "reading..." before the first poll
        g.tick(clock())
        before = draw(lv).px[:]
        g.key(keys.OK)
        self.assertEqual(lv.msg, "zero set")
        after = draw(lv).px[:]
        self.assertNotEqual(before, after)                                              # the bubble moved to the middle
        self.assertEqual(sm.zero, (18, -450))
        for h in (64, 80):
            draw(lv, h)
        for acc in ("0 1000 -20", "900 0 -20", "-900 0 -20"):                           # the longest words stay left of the circle
            t.put(sn.ACC, acc)
            clock.t += 1
            g.tick(clock())
            c = draw(lv, 64)
            self.assertEqual(sum(c.px[y * c.w + x] for y in range(38, 44) for x in range(68, 72)), 0)

    def test_level_without_a_reading(self):
        t, clock, sm = make(acc=None)
        lv = sm_mod.Level(sm)
        g = Gothi(lv)
        g.tick(clock())
        g.key(keys.OK)
        self.assertEqual(lv.msg, "no reading")
        draw(lv)

    def test_level_back_leaves(self):
        t, clock, sm = make()
        root = sm_mod.Menu("x", [("Level", lambda g: sm_mod.Level(sm))])
        g = Gothi(root)
        g.key(keys.OK)
        self.assertIsInstance(g.top, sm_mod.Level)
        g.key(keys.BACK)
        self.assertIs(g.top, root)

    def test_accelerometer_counts_shakes_and_gives_a_deed(self):
        t, clock, sm = make(acc="0 0 -1000")
        ac = sm_mod.Accelerometer(sm)
        st = DolphinState(load_rules(extra=[{"deeds": {"shake": {"group": "modules", "xp": 1}}}]), path="")
        g = Gothi(ac, Settings(os.devnull), st)
        g.tick(clock())
        t.put(sn.ACC, "0 0 -2300")
        clock.t += 1
        g.tick(clock())
        self.assertEqual(sm.shake.count, 1)
        self.assertEqual(st.xp, 1)                                                      # the first shake is a deed
        for h in (64, 80):
            draw(ac, h)

    def test_light_screen(self):
        t, clock, sm = make()
        li = sm_mod.Light(sm)
        g = Gothi(li)
        g.tick(clock())
        for v in ("0", "12", "5000", "70000"):
            t.put(sn.LUX, v)
            clock.t += 1
            g.tick(clock())
            draw(li)
        t.put(sn.LUX, "")
        clock.t += 1
        g.tick(clock())
        draw(li)                                                                        # a failed reading is "no light sensor"

    def test_switches_screen_shows_the_log(self):
        t, clock, sm = make()
        sw = sm_mod.Switches(sm)
        g = Gothi(sw)
        g.tick(clock())
        self.assertIn("-- changes --", sw.rows(g))
        self.assertEqual(sw.rows(g)[-1], "none yet")
        t.put(f"{sn.SWITCH_DIR}/slide/state", "closed")
        clock.t += 1
        g.tick(clock())
        self.assertTrue(sw.rows(g)[-1].endswith("slide closed"))
        draw(sw)

    def test_no_switches(self):
        sm = sn.Sensors(root=tempfile.mkdtemp(), config=os.devnull)
        sw = sm_mod.Switches(sm)
        g = Gothi(sw)
        g.tick(1.0)
        self.assertEqual(sw.rows(g), ["no switches"])

    def test_create_makes_the_menu(self):
        class M:
            deed = "sensors_view"
        m = sm_mod.create(M())
        self.assertEqual([i[0] for i in m.items], ["Overview", "Level", "Accelerometer", "Light", "Switches"])
        self.assertEqual(m.deed_name, "sensors_view")


if __name__ == "__main__":
    unittest.main()
