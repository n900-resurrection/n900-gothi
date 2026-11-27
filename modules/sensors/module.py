"""Sensors for gothi (bundled): all the readings of the built-in sensors on one page, a bubble level, the accelerometer with a shake counter, the ambient
light and the switches (keyboard slide, lens cover, headphones, proximity) with a log of changes. The sensors are only read, nothing is written to them,
and only while one of these screens is on top. The data code is gothi/sensors.py. The N900 has no gyroscope, compass or barometer."""
from gothi import keys, sensors
from gothi.ui import Menu, Scene, ScrollView

NONE = "not available"


def circle(c, cx, cy, r):
    """An outline of a circle (the midpoint algorithm)."""
    x, y, err = r, 0, 1 - r
    while x >= y:
        for px, py in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
            c.pixel(cx + px, cy + py)
        y += 1
        if err < 0:
            err += 2 * y + 1
        else:
            x -= 1
            err += 2 * (y - x) + 1


class Overview(ScrollView):
    title = "Sensors"

    def __init__(self, sm):
        super().__init__()
        self.sm = sm

    def tick(self, now, gothi):
        self.sm.poll(now)

    def rows(self, gothi):
        sm = self.sm
        if sm.stamp is None:
            return ["reading..."]
        r = []
        if sm.acc is not None:
            r += [f"acc {sm.acc[0]} {sm.acc[1]} {sm.acc[2]} mg", f"{sensors.magnitude(sm.acc):.2f} g", sensors.position(sm.acc)]
        else:
            r.append("acc " + NONE)
        r.append(f"light {sm.lux} lx, {sensors.lux_word(sm.lux)}" if sm.lux is not None else "light " + NONE)
        for name in ("prox", "slide", "lock", "lens", "jack"):
            r.append(f"{name} {sensors.SHORT.get(sm.switches.get(name), sm.switches.get(name)) or '?'}")
        return r


class Level(Scene):
    """A bubble level: the bubble leaves the middle as the phone tilts; OK sets the present tilt as level."""
    title = "Level"

    def __init__(self, sm):
        self.sm = sm
        self.msg = ""

    def tick(self, now, gothi):
        self.sm.poll(now)

    def key(self, k, gothi):
        if k == keys.OK:
            self.msg = "zero set" if self.sm.set_zero() else "no reading"
            if self.sm.acc is not None:
                gothi.deed("level_used")
        else:
            super().key(k, gothi)

    def on_tap(self, x, y, gothi):
        self.key(keys.OK, gothi)

    def draw(self, c, gothi):
        c.text(2, 2, self.title)
        c.hline(0, 9, c.w)
        sm = self.sm
        if sm.acc is None:
            c.text(4, 20, "no accelerometer" if sm.stamp is not None else "reading...")
            return
        r = max(8, min(24, (c.h - 14) // 2 - 1))
        cx, cy = c.w - r - 8, 10 + (c.h - 10) // 2
        circle(c, cx, cy, r)
        c.hline(cx - 3, cy, 7)
        c.vline(cx, cy - 3, 7)
        dx, dy = sensors.bubble(sm.acc, r - 3, sm.zero)
        c.box(cx + dx - 2, cy + dy - 2, 5, 5)
        ax, ay = sensors.tilt((sm.acc[0] - sm.zero[0], sm.acc[1] - sm.zero[1], sm.acc[2]))
        c.text(3, 16, f"x {ax:+.1f}")
        c.text(3, 26, f"y {ay:+.1f}")
        word = sensors.position(sm.acc)
        while c.text_width(word) > cx - r - 5 and " " in word:                         # the words do not fit beside the circle: the first ones only
            word = word.rsplit(" ", 1)[0]
        c.text(3, 38, word)
        c.text(3, c.h - 17, "OK = level" if not self.msg else self.msg)


class Accelerometer(Scene):
    """The strength of the acceleration over the last seconds as a line, the three axes and a shake counter."""
    title = "Accelerometer"

    def __init__(self, sm):
        self.sm = sm

    def tick(self, now, gothi):
        if self.sm.poll(now) and self.sm.shook:
            gothi.deed("shake")

    def draw(self, c, gothi):
        c.text(2, 2, self.title)
        c.hline(0, 9, c.w)
        sm = self.sm
        if sm.acc is None:
            c.text(4, 20, "no accelerometer" if sm.stamp is not None else "reading...")
            return
        top, bottom = 14, c.h - 20
        c.frame(0, top - 1, c.w, bottom - top + 2)
        one = bottom - 1 - round(1000 / 2500 * (bottom - top - 1))                  # the line of 1 g
        for x in range(0, c.w, 4):
            c.pixel(x, one)
        sensors.trace(c, sm.mag.values(), 1, top, c.w - 2, bottom - top, 0, 2500)
        c.text(2, c.h - 16, f"{sm.acc[0]} {sm.acc[1]} {sm.acc[2]}")
        c.text(2, c.h - 7, f"{sensors.magnitude(sm.acc):.2f} g  shakes {sm.shake.count}")


class Light(Scene):
    title = "Light"

    def __init__(self, sm):
        self.sm = sm

    def tick(self, now, gothi):
        self.sm.poll(now)

    def draw(self, c, gothi):
        c.text(2, 2, self.title)
        c.hline(0, 9, c.w)
        sm = self.sm
        if sm.lux is None:
            c.text(4, 20, "no light sensor" if sm.stamp is not None else "reading...")
            return
        c.text(3, 14, f"{sm.lux}", scale=2)
        c.text(c.w - 3 - c.text_width(sensors.lux_word(sm.lux)), 16, sensors.lux_word(sm.lux))
        c.text(c.w - 3 - c.text_width("lx"), 26, "lx")
        c.frame(2, 32, c.w - 4, 7)
        c.box(3, 33, int((c.w - 6) * sensors.lux_bar(sm.lux)), 5)
        top = 43
        vals = [sensors.lux_bar(x) for x in sm.lux_hist.values()]
        if vals:
            lo = min(vals)
            sensors.trace(c, vals, 2, top, c.w - 4, c.h - top - 2, lo, max(max(vals), lo + 0.1))       # zoomed to what happened in the last minute


class Switches(ScrollView):
    """The state of the switches (keyboard slide, lock, lens cover, proximity, headphones, camera buttons) and the log of their changes, the newest first."""
    title = "Switches"

    def __init__(self, sm):
        super().__init__()
        self.sm = sm

    def tick(self, now, gothi):
        self.sm.poll(now)

    def rows(self, gothi):
        sm = self.sm
        if sm.stamp is None:
            return ["reading..."]
        if not sm.present()["switches"]:
            return ["no switches"]
        r = [f"{n} {s}" for n, s in sm.switches.items() if s is not None]
        return r + ["-- changes --"] + ([f"{t} {n} {s}" for t, n, s in sm.log] or ["none yet"])


def create(module):
    sm = sensors.Sensors()
    menu = Menu("Sensors", [("Overview", lambda g: Overview(sm)), ("Level", lambda g: Level(sm)), ("Accelerometer", lambda g: Accelerometer(sm)),
                            ("Light", lambda g: Light(sm)), ("Switches", lambda g: Switches(sm))])
    menu.deed_name = module.deed
    return menu
