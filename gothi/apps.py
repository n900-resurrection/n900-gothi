"""The applications of the main menu. Each is a Scene; `main_menu()` builds the root."""
import os
import time

from . import __version__, keys, sysinfo
from . import flipper
from .settings import PRESETS
from .ui import Menu, Scene


class Clock(Scene):
    title = "Clock"

    def draw(self, c, gothi):
        t = time.localtime()
        s = time.strftime("%H:%M:%S", t)
        c.text((c.w - c.text_width(s, 3)) // 2, c.h // 2 - 12, s, scale=3)
        d = time.strftime("%Y-%m-%d", t)
        c.text((c.w - c.text_width(d)) // 2, c.h // 2 + 14, d)


class Battery(Scene):
    title = "Battery"

    def draw(self, c, gothi):
        c.text(2, 2, "Battery")
        c.hline(0, 9, c.w)
        b = sysinfo.battery()
        if not b:
            c.text(4, 24, "no battery data")
            return
        if b["percent"] is not None:
            c.text(4, 16, f"{b['percent']}%", scale=3)
            c.frame(60, 16, 60, 15)
            c.box(62, 18, 56 * b["percent"] // 100, 11)
        lines = ["charging" if b["charging"] else "on battery"]
        if b["mV"]:
            lines.append(f"{b['mV'] / 1000:.2f} V")
        if b["mAh"] is not None:
            lines.append(f"{b['mAh']} / {b['full_mAh']} mAh")
        for i, s in enumerate(lines):
            c.text(4, 38 + i * 8, s)


class Keys(Scene):
    """Shows the last keys, to try the keyboard and the touch buttons."""
    title = "Key test"

    def __init__(self):
        self.last = []

    def key(self, k, gothi):
        self.last = (self.last + [k])[-6:]
        if self.last[-3:] == [keys.BACK] * 3:
            gothi.pop()

    def draw(self, c, gothi):
        c.text(2, 2, "Key test (back x3 = exit)")
        c.hline(0, 9, c.w)
        c.text(4, 16, f"mode: {gothi.mode}")
        for i, k in enumerate(reversed(self.last)):
            c.text(4, 28 + i * 6, k.upper(), scale=1)


class About(Scene):
    title = "About"

    def draw(self, c, gothi):
        c.text(2, 2, "About")
        c.hline(0, 9, c.w)
        for i, s in enumerate((f"gothi {__version__}", "for the Nokia N900", "MIT licence", "art style: Flipper", "github.com/n900-", "resurrection/n900-gothi")):
            c.text(4, 14 + i * 8, s)


ASSETS = os.environ.get("GOTHI_ASSETS") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "flipper")


class Player(Scene):
    """Plays one animation of the firmware (frame rate and frame order from its meta.txt)."""

    def __init__(self, path):
        self.anim, self.start = flipper.Animation(path), None
        self.title = self.anim.name

    def draw(self, c, gothi):
        self.start = self.start or time.time()
        a = self.anim
        x, y = (c.w - a.w) // 2, (c.h - a.h) // 2
        if gothi.settings["border"] and (a.w < c.w or a.h < c.h):
            c.clear(1)                                         # a black frame around the animation, as on a screen larger than the Flipper's
            c.box(x, y, a.w, a.h, 0)
        c.blit(a.frame_at(time.time() - self.start), x, y)


class Message(Scene):
    def __init__(self, title, lines):
        self.title, self.lines = title, lines

    def draw(self, c, gothi):
        c.text(2, 2, self.title)
        c.hline(0, 9, c.w)
        for i, s in enumerate(self.lines):
            c.text(4, 16 + i * 8, s)


def animations(gothi):
    """The animations of assets/flipper/dolphin/external (tools/fetch-assets.sh downloads them)."""
    d = os.path.join(ASSETS, "dolphin", "external")
    if not os.path.isdir(d):
        return Message("Animations", ["no graphics found", "run tools/fetch-", "assets.sh"])
    names = sorted(n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n)))
    return Menu("Animations", [(n.rsplit("_", 1)[0][3:] or n, (lambda g, n=n: Player(os.path.join(d, n)))) for n in names])


class ColorScene(Scene):
    """A preset or the three channels. Up/Down choose the row, Left/Right change it, Back saves."""
    title = "Color"

    def __init__(self):
        self.row = 0

    def draw(self, c, gothi):
        c.text(2, 2, "Color")
        c.hline(0, 9, c.w)
        col = gothi.settings.color
        names = [n for n, v in PRESETS if v == col]
        rows = [("Preset", names[0] if names else "custom")] + [(ch, str(col[i])) for i, ch in enumerate("RGB")]
        for i, (a, b) in enumerate(rows):
            y = 13 + i * 13
            if i == self.row:
                c.box(0, y - 2, c.w, 12)
            ink = 0 if i == self.row else 1
            c.text(4, y + 1, a, v=ink)
            if i == 0:
                c.text(60, y + 1, b, v=ink)
            else:
                c.frame(30, y, 70, 8, ink)
                c.box(31, y + 1, 68 * col[i - 1] // 255, 6, ink)
                c.text(104, y + 1, b, v=ink)

    def key(self, k, gothi):
        col = list(gothi.settings.color)
        if k == keys.UP:
            self.row = (self.row - 1) % 4
        elif k == keys.DOWN:
            self.row = (self.row + 1) % 4
        elif k in (keys.LEFT, keys.RIGHT):
            d = 1 if k == keys.RIGHT else -1
            if self.row == 0:
                idx = next((i for i, (n, v) in enumerate(PRESETS) if v == tuple(col)), -1)
                col = list(PRESETS[(idx + d) % len(PRESETS)][1])
            else:
                col[self.row - 1] = min(255, max(0, col[self.row - 1] + 8 * d))
            gothi.settings["color"] = col
        elif k in (keys.BACK, keys.OK):
            gothi.settings.save()
            gothi.pop()


class SettingsScene(Scene):
    title = "Settings"

    def __init__(self):
        self.sel = 0

    def rows(self, gothi):
        st = gothi.settings
        return [("Color", ""), ("Screen", "tall 128x80" if st["screen"] == "tall" else "classic 128x64"),
                ("Anim. border", "black" if st["border"] else "none")]

    def draw(self, c, gothi):
        c.text(2, 2, "Settings")
        c.hline(0, 9, c.w)
        for i, (a, b) in enumerate(self.rows(gothi)):
            y = 13 + i * 12
            if i == self.sel:
                c.box(0, y - 2, c.w, 11)
            ink = 0 if i == self.sel else 1
            c.text(4, y + 1, a, v=ink)
            c.text(c.w - 4 - c.text_width(b), y + 1, b, v=ink)

    def key(self, k, gothi):
        st = gothi.settings
        n = len(self.rows(gothi))
        if k == keys.UP:
            self.sel = (self.sel - 1) % n
        elif k == keys.DOWN:
            self.sel = (self.sel + 1) % n
        elif k in (keys.OK, keys.LEFT, keys.RIGHT):
            if self.sel == 0 and k in (keys.OK, keys.RIGHT):
                gothi.push(ColorScene())
            elif self.sel == 1:
                st["screen"] = "classic" if st["screen"] == "tall" else "tall"
                gothi.h = st.height
                st.save()
            elif self.sel == 2:
                st["border"] = not st["border"]
                st.save()
            elif k == keys.LEFT:
                gothi.pop()
        elif k == keys.BACK:
            gothi.pop()


def main_menu():
    return Menu("gothi", [
        ("Clock", lambda g: Clock()),
        ("Battery", lambda g: Battery()),
        ("Animations", animations),
        ("Key test", lambda g: Keys()),
        ("Settings", lambda g: SettingsScene()),
        ("About", lambda g: About()),
    ])
