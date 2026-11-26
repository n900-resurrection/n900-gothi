"""Tests of the bundled module modules/wifi-scan (screens, background scanner, saved networks) with a fake scanner:  python3 -m unittest discover -s tests"""
import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from gothi import keys, modules as mod, wifi  # noqa: E402
from gothi.canvas import Canvas  # noqa: E402
from gothi.ui import Gothi  # noqa: E402
from test_wifi import GCONF, SCAN  # noqa: E402

PATH = os.path.join(HERE, "..", "modules", "wifi-scan")
spec = importlib.util.spec_from_file_location("wifi_scan_module", os.path.join(PATH, "module.py"))
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


def make(nets_text=SCAN, on=True):
    clock = Clock()
    box = {"text": nets_text, "on": on, "calls": 0}

    def scan():
        box["calls"] += 1
        return wifi.parse_scan(box["text"])
    sc = ws.Scanner(scan=scan, present=lambda: box["on"], spawn=lambda fn: fn(), clock=clock)
    return sc, clock, box


def text_of(scene, h=64):
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
        m = mod.Module(PATH, data) if os.path.exists("/sbin/iwlist") else None
        if m:
            self.assertEqual((m.kind, m.menu, m.deed), ("python", "modules", "wifi_scan"))
        self.assertEqual(data["type"], "python")
        self.assertTrue(os.path.isfile(os.path.join(PATH, data["entry"])))
        self.assertIn(data["deed"], data["deeds"])


class ScannerTest(unittest.TestCase):
    def test_scans_at_once_then_waits_for_the_period(self):
        sc, clock, box = make()
        sc.poll()
        self.assertEqual((box["calls"], len(sc.nets)), (1, 6))
        sc.poll()
        self.assertEqual(box["calls"], 1)                              # too soon
        clock.t += ws.PERIOD + 0.1
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

    def test_sorted_and_remembers_everything_seen(self):
        sc, clock, box = make()
        sc.poll()
        self.assertEqual(sc.nets[0]["ssid"], "Home-Net")
        box["text"] = SCAN.replace("Cell 01", "Cell 01").split("Cell 02")[0]       # only the first network is left
        clock.t += 10
        sc.poll()
        self.assertEqual((len(sc.nets), len(sc.known)), (1, 6))

    def test_wifi_off_is_not_a_scan(self):
        sc, clock, box = make(on=False)
        sc.poll()
        self.assertEqual((sc.on, sc.nets, box["calls"]), (False, [], 0))

    def test_a_failing_scan_does_not_leave_it_busy(self):
        sc, clock, box = make()
        sc.scan = lambda: 1 / 0
        with self.assertRaises(ZeroDivisionError):
            sc.poll()
        self.assertFalse(sc.busy)


class ScreensTest(unittest.TestCase):
    def test_networks_list_detail_and_back(self):
        sc, clock, box = make()
        n = ws.Networks(sc)
        g = Gothi(n)
        g.tick(clock())
        self.assertEqual(n.title, "Networks 6")
        self.assertTrue(n.items[0][0].startswith("Home-Net WPA2 -39"))
        self.assertEqual(n.items[-1][0].split()[0], "WEP-Relic")
        text_of(n)
        g.key(keys.OK)
        self.assertIsInstance(g.top, ws.Detail)
        rows = g.top.rows(g)
        self.assertEqual(rows[0], "Home-Net")
        self.assertIn("channel 1", rows)
        self.assertTrue(any(isinstance(r, tuple) for r in rows))
        text_of(g.top)
        g.key(keys.BACK)
        self.assertIs(g.top, n)

    def test_security_is_abbreviated_not_cut(self):
        sc, clock, box = make()
        n = ws.Networks(sc)
        Gothi(n).tick(clock())
        rows = {i[0].split()[0]: i[0] for i in n.items}
        self.assertEqual(rows["Campus"], "Campus EAP -65")
        self.assertEqual(rows["(hidden)"], "(hidden) WPA12 -68")
        self.assertTrue(all(len(i[0]) <= 24 for i in n.items))

    def test_hidden_network_has_a_name(self):
        sc, clock, box = make()
        n = ws.Networks(sc)
        Gothi(n).tick(clock())
        self.assertTrue(any(i[0].startswith("(hidden)") for i in n.items))

    def test_selection_follows_the_network_when_the_order_changes(self):
        sc, clock, box = make()
        n = ws.Networks(sc)
        g = Gothi(n)
        g.tick(clock())
        g.key(keys.DOWN)
        chosen = n.ids[n.sel]
        box["text"] = SCAN.replace("Signal level:-70", "Signal level:-20")            # Cafe Guest becomes the strongest: it moves to the top
        clock.t += 10
        g.tick(clock())
        self.assertEqual(n.ids[n.sel], chosen)
        self.assertEqual(n.ids[0], "AA:BB:CC:00:00:02")

    def test_wifi_off_and_nothing_found_do_not_crash_the_menu(self):
        for kw in ({"on": False}, {"nets_text": "wlan0     No scan results\n"}):
            sc, clock, box = make(**kw)
            n = ws.Networks(sc)
            g = Gothi(n)
            g.tick(clock())
            text_of(n)
            g.key(keys.DOWN)
            g.key(keys.OK)
            self.assertEqual(len(g.stack), 2)
        self.assertEqual(ws.Networks(make(on=False)[0]).items[0][0], "scanning...")        # before the first scan

    def test_detail_of_a_network_that_left(self):
        sc, clock, box = make()
        d = ws.Detail(sc, "AA:BB:CC:00:00:99")
        self.assertEqual(d.rows(Gothi(d))[0], "out of range")

    def test_channels_draws_columns_and_the_quietest(self):
        sc, clock, box = make()
        ch = ws.Channels(sc)
        Gothi(ch).tick(clock())
        c = text_of(ch)
        self.assertGreater(sum(c.px), 100)
        empty = text_of(ws.Channels(make(on=False)[0]))
        self.assertLess(sum(empty.px), sum(c.px))
        for h in (64, 80):
            text_of(ch, h)

    def test_summary_rows(self):
        sc, clock, box = make()
        s = ws.Summary(sc)
        Gothi(s).tick(clock())
        rows = s.rows(Gothi(s))
        self.assertIn("networks 6", rows)
        self.assertIn("hidden 1", rows)
        self.assertIn("strongest -39 dBm", rows)
        self.assertIn("seen in total 6", rows)
        text_of(s)

    def test_saved_networks_mark_those_in_range(self):
        sc, clock, box = make()
        sc.poll()
        saved = ws.Saved(sc, run=lambda cmd, t: (0, GCONF))
        self.assertEqual([i[0] for i in saved.items], ["* Home-Net", "  Hidden"])
        g = Gothi(saved)
        g.key(keys.OK)
        self.assertEqual(g.top.title, "Home-Net")

    def test_saved_networks_when_gconf_fails(self):
        saved = ws.Saved(make()[0], run=lambda cmd, t: (-1, ""))
        self.assertEqual(saved.items[0][0], "none saved")
        g = Gothi(saved)
        g.key(keys.OK)
        text_of(g.top)

    def test_create_gives_the_menu_and_the_deed(self):
        m = type("M", (), {"deed": "wifi_scan"})()
        menu = ws.create(m)
        self.assertEqual([i[0] for i in menu.items], ["Networks", "Channels", "Summary", "Saved networks"])
        self.assertEqual(menu.deed_name, "wifi_scan")


if __name__ == "__main__":
    unittest.main()
