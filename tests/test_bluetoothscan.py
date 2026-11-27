"""Tests of the bundled module modules/bluetooth-scan (screens, background scanner, known devices) with a fake scanner:  python3 -m unittest discover -s tests"""
import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from gothi import bluetooth, keys, modules as mod  # noqa: E402
from gothi.canvas import Canvas  # noqa: E402
from gothi.ui import Gothi  # noqa: E402
from test_bluetooth import KNOWN_FILES, SCAN  # noqa: E402

PATH = os.path.join(HERE, "..", "modules", "bluetooth-scan")
spec = importlib.util.spec_from_file_location("bluetooth_scan_module", os.path.join(PATH, "module.py"))
bs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bs)


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


def make(text=SCAN, on=True):
    clock = Clock()
    box = {"text": text, "on": on, "calls": 0}

    def scan():
        box["calls"] += 1
        return bluetooth.parse_scan(box["text"])
    sc = bs.Scanner(scan=scan, up=lambda: box["on"], spawn=lambda fn: fn(), clock=clock)
    return sc, clock, box


def draw(scene, h=64):
    c = Canvas()
    c.h = h
    c.px = bytearray(c.w * h)
    g = Gothi(scene)
    g.h = h
    scene.draw(c, g)
    return c


class ManifestTest(unittest.TestCase):
    def test_it_is_a_valid_bundled_module(self):
        with open(os.path.join(PATH, "module.json")) as f:
            data = json.load(f)
        self.assertEqual(data["type"], "python")
        self.assertTrue(os.path.isfile(os.path.join(PATH, data["entry"])))
        self.assertIn(data["deed"], data["deeds"])
        data["requires"] = []
        m = mod.Module(PATH, data)
        self.assertEqual((m.kind, m.menu), ("python", "modules"))


class ScannerTest(unittest.TestCase):
    def test_scans_at_once_then_waits_for_the_period(self):
        sc, clock, box = make()
        sc.poll()
        self.assertEqual((box["calls"], len(sc.devs)), (1, 4))
        sc.poll()
        self.assertEqual(box["calls"], 1)
        clock.t += bs.PERIOD + 0.1
        sc.poll()
        self.assertEqual(box["calls"], 2)

    def test_no_second_scan_while_one_runs(self):
        sc, clock, box = make()
        started = []
        sc.spawn = started.append
        sc.poll()
        sc.poll()
        self.assertEqual(len(started), 1)
        started[0]()
        self.assertFalse(sc.busy)

    def test_remembers_everything_seen(self):
        sc, clock, box = make()
        sc.poll()
        box["text"] = SCAN.split("BD Address:\t00:11:22:33:44:02")[0]
        clock.t += 10
        sc.poll()
        self.assertEqual((len(sc.devs), len(sc.known)), (1, 4))
        self.assertEqual(sc.find("00:11:22:33:44:01")["seen"], 2)

    def test_bluetooth_off_is_not_a_scan(self):
        sc, clock, box = make(on=False)
        sc.poll()
        self.assertEqual((sc.on, sc.devs, box["calls"]), (False, [], 0))

    def test_a_failing_scan_does_not_leave_it_busy(self):
        sc, clock, box = make()
        sc.scan = lambda: 1 / 0
        with self.assertRaises(ZeroDivisionError):
            sc.poll()
        self.assertFalse(sc.busy)


class ScreensTest(unittest.TestCase):
    def test_list_detail_and_back(self):
        sc, clock, box = make()
        d = bs.Devices(sc)
        g = Gothi(d)
        g.tick(clock())
        self.assertEqual(d.title, "Devices 4")
        self.assertEqual(d.items[0][0], "Living Room tv")
        self.assertIn("33:44:03 input", [i[0] for i in d.items])             # the name did not come: the end of the address
        self.assertTrue(all(len(i[0]) <= 24 for i in d.items))
        draw(d)
        g.key(keys.OK)
        self.assertIsInstance(g.top, bs.Detail)
        rows = g.top.rows(g)
        self.assertEqual(rows[0], "Living Room TV")
        self.assertIn("kind video display", rows)
        self.assertIn("in range", rows)
        draw(g.top)
        g.key(keys.BACK)
        self.assertIs(g.top, d)

    def test_the_selection_follows_the_device(self):
        sc, clock, box = make()
        d = bs.Devices(sc)
        g = Gothi(d)
        g.tick(clock())
        g.key(keys.DOWN)
        keep = d.ids[d.sel]
        box["text"] = "\n\n".join(reversed(SCAN.split("\n\n")))
        clock.t += 10
        g.tick(clock())
        self.assertEqual(d.ids[d.sel], keep)

    def test_a_device_that_went_away_is_out_of_range(self):
        sc, clock, box = make()
        d = bs.Devices(sc)
        g = Gothi(d)
        g.tick(clock())
        det = bs.Detail(sc, "00:11:22:33:44:02")
        box["text"] = "Scanning ...\n"
        clock.t += 10
        det.tick(clock(), g)
        self.assertIn("out of range", det.rows(g))
        self.assertEqual(bs.Detail(sc, "00:00:00:00:00:00").rows(g)[0], "not found")

    def test_empty_and_off(self):
        sc, clock, box = make(text="Scanning ...\n")
        d = bs.Devices(sc)
        Gothi(d).tick(clock())
        self.assertEqual(d.items[0][0], "none found")
        sc, clock, box = make(on=False)
        d = bs.Devices(sc)
        Gothi(d).tick(clock())
        self.assertEqual(d.title, "Bluetooth is off")
        draw(d)

    def test_nothing_before_the_first_scan_ends(self):
        sc, clock, box = make()
        sc.spawn = lambda fn: None
        d = bs.Devices(sc)
        Gothi(d).tick(clock())
        self.assertEqual(d.items[0][0], "scanning...")

    def test_summary(self):
        sc, clock, box = make()
        sc.poll()
        s = bs.Summary(sc)
        rows = s.rows(Gothi(s))
        self.assertEqual(rows[:2], ["devices 4", "with a name 3"])
        self.assertIn("phone 1", rows)
        draw(s)
        sc.on = False
        self.assertEqual(s.rows(Gothi(s))[0], "Bluetooth is off")

    def test_known_devices(self):
        k = bs.Known(read=lambda: bluetooth.known_devices(KNOWN_FILES["names"], KNOWN_FILES["linkkeys"], KNOWN_FILES["lastseen"]))
        self.assertEqual([i[0] for i in k.items], ["* car-kit", "* Pocket Phone", "  Old Laptop"])
        g = Gothi(k)
        g.key(keys.DOWN)
        g.key(keys.OK)
        self.assertEqual(g.top.__class__.__name__, "Message")
        draw(k)
        self.assertEqual(bs.Known(read=lambda: []).items[0][0], "none known")

    def test_create_makes_the_menu_with_the_deed(self):
        class M:
            deed = "bluetooth_scan"
        m = bs.create(M())
        self.assertEqual([i[0] for i in m.items], ["Devices", "Summary", "Known devices"])
        self.assertEqual(m.deed_name, "bluetooth_scan")


if __name__ == "__main__":
    unittest.main()
