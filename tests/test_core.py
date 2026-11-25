"""Tests of the core, no display needed:  python3 -m unittest discover -s tests"""
import os
import sys
import struct
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gothi import flipper, keys  # noqa: E402
from gothi.apps import Clock, main_menu  # noqa: E402
from gothi.canvas import Canvas  # noqa: E402
from gothi.apps import ColorScene, SettingsScene  # noqa: E402
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
