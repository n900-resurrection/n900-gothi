"""The applications of the main menu. Each is a Scene; `main_menu()` builds the root."""
import os
import random
import time

from . import __version__, keys, sysinfo
from . import flipper
from .settings import PRESETS
from .ui import Menu, Scene, ScrollView


class Clock(Scene):
    title = "Clock"
    deed_name = "clock_view"

    def draw(self, c, gothi):
        t = time.localtime()
        s = time.strftime("%H:%M:%S", t)
        c.text((c.w - c.text_width(s, 3)) // 2, c.h // 2 - 12, s, scale=3)
        d = time.strftime("%Y-%m-%d", t)
        c.text((c.w - c.text_width(d)) // 2, c.h // 2 + 14, d)


class Battery(Scene):
    title = "Battery"
    deed_name = "battery_view"

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
    deed_name = "key_test"

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


class About(ScrollView):
    title = "About"
    deed_name = "about_view"

    def rows(self, gothi):
        return [f"gothi {__version__}", "for the Nokia N900", "MIT licence", "art style: Flipper", "github.com/n900-", "resurrection/n900-gothi"]


class Player(Scene):
    """Plays one animation of the firmware: passive frames in a loop, OK plays the active part, the speech bubbles of its meta.txt."""

    deed_name = "animation_view"
    show_bubbles = True                    # the speech bubbles of the animation itself (a scene that talks with its own turns them off)

    def __init__(self, path):
        self.anim, self.play = flipper.Animation(path), None
        self.title = self.anim.name

    def key(self, k, gothi):
        if k == keys.OK and self.play:
            self.play.activate(time.time())
        else:
            super().key(k, gothi)

    def draw(self, c, gothi):
        now = time.time()
        self.play = self.play or flipper.Playback(self.anim, now)
        a = self.anim
        x, y = (c.w - a.w) // 2, (c.h - a.h) // 2
        if gothi.settings["border"] and (a.w < c.w or a.h < c.h):
            c.clear(1)                                         # a black frame around the animation, as on a screen larger than the Flipper's
            c.box(x, y, a.w, a.h, 0)
        frame, pos = self.play.at(now)
        c.blit(frame, x, y)
        for b in (self.play.bubbles(pos) if self.show_bubbles else []):
            flipper.draw_bubble(c, b, x, y)


class Dolphin(Player):
    """Like the desktop of the Flipper: animations of the firmware picked by their weight and the level and mood (butthurt) of the dolphin, one after another.
    Right = the next one, OK = the dolphin does its active part, Back = out."""

    deed_name = None                       # the dolphin on the desktop earns its XP by being petted (OK), not by being looked at

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.manifest = flipper.read_manifest(os.path.join(flipper.ASSETS, "dolphin", "external", "manifest.txt"))
        self.anim = self.play = None
        self.until = 0

    def next(self, gothi, now):
        name = flipper.pick(self.manifest, gothi.dolphin.level, self.rng, gothi.dolphin.mood(gothi.settings["happy"]))
        self.anim = flipper.Animation(os.path.join(flipper.ASSETS, "dolphin", "external", name))
        self.play = flipper.Playback(self.anim, now)
        self.until = now + min(self.anim.duration or 60, 180)         # Duration is the time on the screen (the firmware: up to an hour), shortened

    def draw(self, c, gothi):
        if self.anim is None or time.time() > self.until:
            self.next(gothi, time.time())
        super().draw(c, gothi)

    def key(self, k, gothi):
        if k == keys.RIGHT:
            self.anim = None
        elif k == keys.OK and self.play:
            gothi.deed("dolphin_active")
            super().key(k, gothi)
        else:
            super().key(k, gothi)


class Message(Scene):
    def __init__(self, title, lines):
        self.title, self.lines = title, lines

    def draw(self, c, gothi):
        c.text(2, 2, self.title)
        c.hline(0, 9, c.w)
        for i, s in enumerate(self.lines):
            c.text(4, 16 + i * 8, s)


class Stats(ScrollView):
    """The character: level, XP to the next level, mood (butthurt) and the XP earned today in each group. Scrolls when it does not fit."""
    title = "Dolphin stats"
    deed_name = "stats_view"

    def rows(self, gothi):
        d = gothi.dolphin
        got, need = d.xp_in_level()
        top = d.thresholds[d.level - 1] if need is not None else None
        rows = [f"Level {d.level}" + ("" if need is not None else " (max)"), f"XP {d.xp}" + ("" if top is None else f" / {top}"),
                ("bar", 1.0 if need is None else got / max(1, need))]
        if need is not None:
            rows.append(f"Next level: {d.xp_to_levelup()} XP")
        mx = d.rules["butthurt"]["max"]
        if gothi.settings["happy"]:
            rows.append("Mood: always happy")
        else:
            rows += [f"Butthurt {d.butthurt} / {mx}", ("bar", d.butthurt / max(1, mx))]
        rows.append("Today:")
        for g in sorted({v["group"] for v in d.rules["deeds"].values()}):
            rows.append(f"  {g}: {d.group_xp.get(g, 0)} / {d.limit(g)} XP")
        return rows


def animations(gothi):
    """The animations of assets/flipper/dolphin/external (tools/fetch-assets.sh downloads them)."""
    d = os.path.join(flipper.ASSETS, "dolphin", "external")
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
    """The built-in settings, then the modules that ask for the Settings (volume, brightness, Wi-Fi, Bluetooth, ...). Scrolls when it does not fit."""
    title = "Settings"
    BUILTIN = 4

    def __init__(self, mods=()):
        self.sel = 0
        self.top = 0
        self.mods = list(mods)

    def rows(self, gothi):
        st = gothi.settings
        return [("Color", ""), ("Screen", "tall 128x80" if st["screen"] == "tall" else "classic 128x64"),
                ("Anim. border", "black" if st["border"] else "none"), ("Happy mode", "on" if st["happy"] else "off")] + [(m.title, ">") for m in self.mods]

    def visible(self, h):
        return max(1, (h - 13) // 12)

    def draw(self, c, gothi):
        c.text(2, 2, "Settings")
        c.hline(0, 9, c.w)
        rows = self.rows(gothi)
        n = self.visible(c.h)
        self.top = max(0, min(self.top, len(rows) - n))
        for i, (a, b) in enumerate(rows[self.top:self.top + n]):
            y = 13 + i * 12
            sel = self.top + i == self.sel
            if sel:
                c.box(0, y - 2, c.w - (5 if len(rows) > n else 0), 11)
            ink = 0 if sel else 1
            c.text(4, y + 1, a, v=ink)
            c.text(c.w - 4 - (5 if len(rows) > n else 0) - c.text_width(b), y + 1, b, v=ink)
        if len(rows) > n:                                     # scroll bar, as in the Menu
            bar = c.h - 12
            c.vline(c.w - 2, 11, bar)
            h = max(4, bar * n // len(rows))
            c.box(c.w - 3, 11 + (bar - h) * self.top // (len(rows) - n), 3, h)

    def key(self, k, gothi):
        from . import modules
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
                gothi.deed("settings_change")
            elif self.sel == 2:
                st["border"] = not st["border"]
                st.save()
                gothi.deed("settings_change")
            elif self.sel == 3:
                st["happy"] = not st["happy"]
                st.save()
                gothi.deed("settings_change")
            elif self.sel >= self.BUILTIN and k in (keys.OK, keys.RIGHT):
                gothi.push(modules.scene_for(self.mods[self.sel - self.BUILTIN]))
            elif k == keys.LEFT:
                gothi.pop()
        elif k == keys.BACK:
            gothi.pop()
        self.top = min(max(self.top, self.sel - self.visible(gothi.h) + 1), self.sel)


def dolphin(gothi):
    if not os.path.exists(os.path.join(flipper.ASSETS, "dolphin", "external", "manifest.txt")):
        return Message("Dolphin", ["no graphics found", "run tools/fetch-", "assets.sh"])
    return Dolphin()


def main_menu(found=None):
    """found: (modules, errors) as `modules.discover()` returns them; None = look for them now."""
    from . import modules
    mods, errs = modules.discover() if found is None else found
    mm = "icons/MainMenu/"
    return Menu("gothi", [
        ("Clock", lambda g: Clock(), mm + "Plugins_14"),
        ("Battery", lambda g: Battery(), "icons/Power/Battery_16x16.png"),
        ("Dolphin", dolphin, "icons/Gothi/Smile_14.png"),
        ("Dolphin stats", lambda g: Stats(), mm + "iButton_14"),
        ("Animations", animations, mm + "FileManager_14"),
        ("Key test", lambda g: Keys(), mm + "Debug_14"),
        ("Modules", lambda g: modules.modules_menu(mods, errs), mm + "GPIO_14"),
        ("Settings", lambda g: SettingsScene([m for m in mods if m.menu == "settings"]), mm + "Settings_14"),
        ("About", lambda g: About(), mm + "U2F_14"),
    ], status=True)
