"""Sensor data for the Sensors module: the accelerometer (lis302dl), the ambient light sensor (tsl2563) and the gpio switches of the N900 (proximity, keyboard
slide, lock, lens cover, camera buttons, headphone jack). Pure functions over text plus a small sampler; the sysfs root is a parameter, so everything is
testable with a fake tree. Nothing is written to the sensors: they are only read (all of it works as the normal user)."""
import json
import math
import os
import time

ACC = "bus/i2c/drivers/lis302dl/3-001d/coord"                    # "x y z" in mg (1000 = 1 g); an accelerometer, not a gyroscope
LUX = "class/i2c-adapter/i2c-2/2-0029/lux"
SWITCH_DIR = "devices/platform/gpio-switch"
SWITCHES = [("slide", "slide"), ("kb_lock", "lock"), ("cam_shutter", "lens"), ("proximity", "prox"), ("headphone", "jack"),
            ("cam_focus", "focus"), ("cam_launch", "launch")]    # (the file in SWITCH_DIR, the short name shown)
SHORT = {"connected": "in", "disconnected": "out"}                     # words that are too long for a row
MAX_LUX = 50000
SHAKE_G = 1.8                                                      # the strength (in g) above which a movement is a shake
SHAKE_GAP = 0.5                                                    # seconds between two shakes
PERIOD = 0.2                                                       # seconds between two readings
LOG_LINES = 30


def read(root, rel):
    """The text of a file below the sysfs root, None when it is not there or cannot be read."""
    try:
        with open(os.path.join(root, rel)) as f:
            return f.read().strip()
    except OSError:
        return None


def parse_coord(text):
    """"18 -450 -918" -> (18, -450, -918) in mg, None for anything else."""
    try:
        v = tuple(int(w) for w in (text or "").split())
    except ValueError:
        return None
    return v if len(v) == 3 else None


def magnitude(v):
    """The strength of the acceleration in g (about 1.0 at rest)."""
    return math.sqrt(sum(a * a for a in v)) / 1000.0


def tilt(v):
    """(x, y) angles in degrees: how far the two axes of the display lean from the horizontal, 0 and 0 when the phone lies flat (face up or down)."""
    m = math.sqrt(sum(a * a for a in v)) or 1.0
    return tuple(math.degrees(math.asin(max(-1.0, min(1.0, a / m)))) for a in v[:2])


def position(v):
    """A word for how the phone is held, from the strongest axis. The axes are those of the screen: x to the right, y down, z into the display (face up reads
    z = -1000: the sensor gives the reaction to gravity, so a positive value means that side is higher). The screen is landscape, so the phone is held
    "landscape" when the top edge of the screen is the high side (y = -1000)."""
    ax = [abs(a) for a in v]
    i = ax.index(max(ax))
    if i == 2:
        return "face up" if v[2] < 0 else "face down"
    if i == 1:
        return "landscape" if v[1] < 0 else "landscape flipped"
    return "portrait right up" if v[0] > 0 else "portrait left up"


def bubble(v, r, zero=(0, 0), full=30.0):
    """The offset (dx, dy) in pixels of the bubble of a level inside a circle of radius r; `full` degrees of tilt reach the edge, `zero` is the (x, y) of the
    reading that counts as level."""
    ax, ay = tilt((v[0] - zero[0], v[1] - zero[1], v[2]))
    dx, dy = ax / full * r, ay / full * r
    d = math.hypot(dx, dy)
    if d > r:
        dx, dy = dx * r / d, dy * r / d
    return round(dx), round(dy)


def lux_word(lux):
    if lux is None:
        return "?"
    for limit, word in ((1, "dark"), (30, "dim"), (1000, "indoor"), (10000, "bright")):
        if lux < limit:
            return word
    return "sun"


def lux_bar(lux):
    """0..1 on a logarithmic scale from 0 to MAX_LUX (the eye is logarithmic too)."""
    if not lux or lux < 0:
        return 0.0
    return min(1.0, math.log10(1 + lux) / math.log10(1 + MAX_LUX))


class Series:
    """The last `n` values (a ring buffer) for a trace."""

    def __init__(self, n):
        self.n, self.v = n, []

    def add(self, x):
        self.v.append(x)
        del self.v[:-self.n]

    def values(self):
        return list(self.v)


class Shake:
    """Counts the shakes: a reading stronger than SHAKE_G, at most one per SHAKE_GAP seconds."""

    def __init__(self):
        self.count, self.last = 0, None

    def update(self, v, now):
        if magnitude(v) < SHAKE_G or (self.last is not None and now - self.last < SHAKE_GAP):
            return False
        self.count += 1
        self.last = now
        return True


def read_switches(root):
    """{short name: state text or None} of the gpio switches."""
    return {short: read(root, f"{SWITCH_DIR}/{f}/state") for f, short in SWITCHES}


def line(c, x0, y0, x1, y1, v=1):
    """A line of pixels (Bresenham) on a canvas."""
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        c.pixel(x0, y0, v)
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def trace(c, values, x, y, w, h, lo, hi):
    """Draw `values` as a line in the box (x, y, w, h); lo..hi is the range that fits, the newest value is on the right."""
    if len(values) < 2 or hi <= lo:
        return
    pts = []
    for i, val in enumerate(values[-w:]):
        pts.append((x + w - len(values[-w:]) + i, y + h - 1 - round((max(lo, min(hi, val)) - lo) / (hi - lo) * (h - 1))))
    for a, b in zip(pts, pts[1:]):
        line(c, a[0], a[1], b[0], b[1])


class Sensors:
    """The latest readings, refreshed from `poll()` (called from the tick of a sensor screen, so nothing is read while none is open), the history for the
    traces, the shake count, the log of switch changes and the zero of the level (kept in `config`)."""

    def __init__(self, root="/sys", config=None, clock=time.time):
        self.root, self.clock = root, clock
        self.config = config if config is not None else os.path.join(os.path.expanduser("~"), ".config", "gothi", "sensors.json")
        self.acc = None
        self.lux = None
        self.switches = {}
        self.stamp = None
        self.shake = Shake()
        self.hist = [Series(80), Series(80), Series(80)]           # x, y, z
        self.mag = Series(80)
        self.lux_hist = Series(60)
        self.log = []                                              # (time text, name, state), the newest first
        self.zero = self._load_zero()
        self.shook = False                                         # the last poll saw a shake

    def _load_zero(self):
        try:
            with open(self.config) as f:
                z = json.load(f)["zero"]
            return (int(z[0]), int(z[1]))
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            return (0, 0)

    def set_zero(self):
        """The present tilt counts as level (needs a reading); saved. Returns whether it was set."""
        if self.acc is None:
            return False
        self.zero = (self.acc[0], self.acc[1])
        try:
            os.makedirs(os.path.dirname(self.config), exist_ok=True)
            with open(self.config, "w") as f:
                json.dump({"zero": list(self.zero)}, f)
        except OSError:
            pass
        return True

    def present(self):
        """Which sensors answer: {"acc": bool, "light": bool, "switches": bool}."""
        return {"acc": self.acc is not None, "light": self.lux is not None, "switches": any(s is not None for s in self.switches.values())}

    def poll(self, now=None):
        now = self.clock() if now is None else now
        if self.stamp is not None and now - self.stamp < PERIOD:
            return False
        self.stamp = now
        self.acc = parse_coord(read(self.root, ACC))
        try:
            self.lux = int(read(self.root, LUX))
        except (TypeError, ValueError):
            self.lux = None
        self.shook = False
        if self.acc is not None:
            for s, a in zip(self.hist, self.acc):
                s.add(a)
            self.mag.add(round(magnitude(self.acc) * 1000))
            self.shook = self.shake.update(self.acc, now)
        if self.lux is not None:
            self.lux_hist.add(self.lux)
        new = read_switches(self.root)
        if self.switches:                                          # the first reading is the start state, not a change
            stamp = time.strftime("%H:%M:%S", time.localtime(now))
            for name, state in new.items():
                if state != self.switches.get(name) and state is not None:
                    self.log.insert(0, (stamp, name, state))
            del self.log[LOG_LINES:]
        self.switches = new
        return True
