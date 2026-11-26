"""Modules: extensions that are installed on their own (a .deb) and appear in the menu **Modules** after the next start of gothi.

A module is a folder with a manifest `module.json` in one of the search folders (/opt/gothi/modules for packages, ~/.config/gothi/modules for the user,
GOTHI_MODULES = folders separated by colons replaces both, for development). The folder name is the id of the module; the same id in a later folder
replaces the earlier one (so the user can change a packaged module). Nothing is loaded from anywhere else.

Three kinds need no Python: shell commands decide everything. `switch` is an on/off of a service, `action` runs one command and shows what it printed,
`level` is a number that Left/Right change (volume, brightness).

    {"title": "File server",             menu label
     "type": "switch",
     "status": "copyparty-share status | grep -q ^Running",     exit code 0 = on
     "start": "copyparty-share start",   "stop": "copyparty-share stop",
     "info": "copyparty-share url",      optional: printed lines are shown while on (the address of the server)
     "ready": "curl -s -m 2 http://127.0.0.1:3923/",    optional: after `start` the screen says "starting" until this exits 0 (the server needs time)
     "icon": "icon.png",                 optional: 1-bit PNG (a path in the module folder, 14 px high is right)
     "deed": "fileserver_toggle",        optional: the deed a toggle earns,
     "deeds": {"fileserver_toggle": {"group": "modules", "xp": 2}}}      and its XP, merged into the rules of the dolphin

    {"title": "Sync time", "type": "action",
     "run": "...",                       the command; exit code 0 = done, the lines it prints are shown (scrollable)
     "info": "date",                     optional: shown above, asked on entering and after each run
     "timeout": 90,                      optional: seconds the command may take
     "deed": "time_sync", "deeds": {...}}

    {"title": "Volume", "type": "level",
     "get": "...",                       prints the current value (the first number is taken)
     "set": "amixer sset Master {value}%",       {value} is replaced by the number; the last value wins while the command runs
     "min": 0, "max": 100, "step": 5, "unit": "%"}

Every manifest may also have  "menu": "settings"  (the entry goes to the Settings, default "modules": the menu Modules)  and
"requires": ["/usr/bin/amixer"]  (paths that must exist, otherwise the module is not offered at all: the system lacks the tool).

A broken module is skipped and shown as a line in the menu, the rest keeps working. Python modules (module.py with register()) will come with the first module that needs one."""
import json
import os
import re
import subprocess
import threading
import time

from . import keys
from .ui import Menu, Scene, ScrollView

KINDS = {"switch": ("status", "start", "stop"), "action": ("run",), "level": ("get", "set")}      # kind -> the commands it needs
POLL = 5                                            # seconds between two status checks while the scene is open
SHOWN_INFO = 30                                     # lines of `info` that are kept (the page scrolls)
READY_TIMEOUT = 90                                  # seconds to wait for `ready` after a start
READY_STEP = 1.0


def search_dirs():
    env = os.environ.get("GOTHI_MODULES")
    if env is not None:
        return [d for d in env.split(":") if d]
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules")      # the bundled modules when run from the source tree
    return [src, "/opt/gothi/modules", os.path.join(os.path.expanduser("~"), ".config", "gothi", "modules")]


class Missing(Exception):
    """A required tool is not on this system: the module is left out without an error."""


class Module:
    def __init__(self, path, data):
        self.path, self.id = path, os.path.basename(path.rstrip("/"))
        self.title = str(data.get("title") or self.id)[:24]
        self.kind = data.get("type")
        if self.kind not in KINDS:
            raise ValueError(f"unknown type {self.kind!r}")
        self.menu = data.get("menu", "modules")
        if self.menu not in ("modules", "settings"):
            raise ValueError("bad menu")
        req = data.get("requires", [])
        if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
            raise ValueError("bad requires")
        if any(not os.path.exists(r) for r in req):
            raise Missing()
        self.lo, self.hi, self.step, self.unit = 0, 100, 5, ""
        if self.kind == "level":
            self.lo, self.hi, self.step = (data.get(k, d) for k, d in (("min", 0), ("max", 100), ("step", 5)))
            self.unit = str(data.get("unit", ""))[:3]
            if not all(isinstance(v, int) and not isinstance(v, bool) for v in (self.lo, self.hi, self.step)) or not self.lo < self.hi or self.step < 1:
                raise ValueError("bad min, max or step")
        self.cmds = {}
        for c in KINDS[self.kind] + ("info", "ready"):
            v = data.get(c)
            if v is None and c not in ("info", "ready"):
                raise ValueError(f"missing command {c!r}")
            if v is not None:
                if not isinstance(v, str) or not v.strip():
                    raise ValueError(f"bad command {c!r}")
                self.cmds[c] = v
        t = data.get("timeout", 90)
        if not isinstance(t, (int, float)) or isinstance(t, bool) or not 1 <= t <= 600:
            raise ValueError("bad timeout")
        self.timeout = t
        icon = data.get("icon")
        self.icon = os.path.join(path, icon) if isinstance(icon, str) and os.path.isfile(os.path.join(path, icon)) else None
        self.deed = data.get("deed") if isinstance(data.get("deed"), str) else None
        deeds = data.get("deeds") or {}
        if not isinstance(deeds, dict) or not all(isinstance(v, dict) and isinstance(v.get("group"), str) and isinstance(v.get("xp"), int) and v["xp"] >= 0
                                                  for v in deeds.values()):
            raise ValueError("bad deeds")
        self.deeds = deeds


def discover(dirs=None):
    """(modules, errors): the modules found in the search folders, errors as [(id, message)]; never raises."""
    found, errors = {}, []
    for base in (search_dirs() if dirs is None else dirs):
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for n in names:
            p = os.path.join(base, n)
            if not os.path.isfile(os.path.join(p, "module.json")):
                continue
            try:
                with open(os.path.join(p, "module.json")) as f:
                    found[n] = Module(p, json.load(f))
                errors = [e for e in errors if e[0] != n]
            except Missing:
                found.pop(n, None)
            except (OSError, ValueError, TypeError, AttributeError) as e:
                found.pop(n, None)
                errors.append((n, str(e)[:40]))
    return sorted(found.values(), key=lambda m: m.title.lower()), errors


def run_cmd(cmd, timeout=10):
    """(exit code, output) of a shell command; (-1, "") when it cannot run or takes too long."""
    try:
        p = subprocess.run(["/bin/sh", "-c", cmd], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return -1, ""


def _thread(fn):
    threading.Thread(target=fn, daemon=True).start()


class Switch(Scene):
    """On/off of a service: big ON or OFF, OK toggles. The commands run in a background thread (the screen never waits for them)."""

    def __init__(self, module, run=run_cmd, spawn=_thread):
        self.m, self.run, self.spawn = module, run, spawn
        self.title = module.title
        self.on = None                  # None: not known yet
        self.busy = False               # a command runs in the background (the check too: it is not shown, it would only blink)
        self.action = None              # "starting" / "stopping": shown instead of the hint while the user's command runs
        self.info = []
        self.top = 0                    # the first line of `info` that is shown
        self.checked = 0.0
        self.earned = False

    def on_enter(self, gothi):
        self.refresh()

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.spawn(self._refresh)

    def _refresh(self):
        self._status()
        self.busy = False

    def _status(self):
        """Ask for the state; the new values replace the old ones at the end, so the screen never shows a half-empty state."""
        rc, _ = self.run(self.m.cmds["status"])
        on = rc == 0 if rc >= 0 else None
        info = []
        if on and "info" in self.m.cmds:
            _, out = self.run(self.m.cmds["info"])
            info = _wrap("\n".join(ln.strip() for ln in out.splitlines() if ln.strip()))[:SHOWN_INFO]
        self.info, self.on = info, on

    def toggle(self):
        if self.busy or self.on is None:
            return
        cmd = self.m.cmds["stop" if self.on else "start"]
        starting = not self.on
        self.busy, self.action = True, "starting" if starting else "stopping"
        self.spawn(lambda: self._toggle(cmd, starting))

    def _toggle(self, cmd, starting):
        self.run(cmd, 30)
        if starting and "ready" in self.m.cmds:                  # the process is there, the service may not answer yet
            waited = 0.0
            while waited < READY_TIMEOUT and self.run(self.m.cmds["ready"], 5)[0] != 0:
                time.sleep(READY_STEP)
                waited += READY_STEP
        self._status()
        self.earned = True
        self.action, self.busy = None, False

    def key(self, k, gothi):
        if k == keys.OK:
            self.toggle()
        elif k == keys.UP:
            self.top = max(0, self.top - 1)
        elif k == keys.DOWN:
            self.top = min(self.top + 1, max(0, len(self.info) - self.visible(gothi.h)))
        elif k == keys.BACK:
            gothi.pop()

    INFO_Y = 40

    def visible(self, h):
        return max(1, (h - self.INFO_Y) // 8)

    def tick(self, now, gothi):
        if self.earned:
            self.earned = False
            if self.m.deed:
                gothi.deed(self.m.deed)
        if not self.busy and now - self.checked > POLL:
            self.checked = now
            self.refresh()

    def draw(self, c, gothi):
        c.text(2, 2, self.title)
        c.hline(0, 9, c.w)
        word = "..." if self.on is None else ("ON" if self.on else "OFF")
        c.text(4, 14, word, scale=3)
        hint = self.action or ("" if self.on is None else "OK = " + ("stop" if self.on else "start"))
        c.text(c.w - 4 - c.text_width(hint), 20, hint)
        n = self.visible(c.h)
        self.top = max(0, min(self.top, len(self.info) - n))
        for i, ln in enumerate(self.info[self.top:self.top + n]):
            c.text(4, self.INFO_Y + 2 + i * 8, ln)
        if len(self.info) > n:                                    # scroll bar
            bar = c.h - self.INFO_Y
            c.vline(c.w - 2, self.INFO_Y, bar)
            h = max(4, bar * n // len(self.info))
            c.box(c.w - 3, self.INFO_Y + (bar - h) * self.top // (len(self.info) - n), 3, h)


def _wrap(text, width=118):
    """Lines of a text that fit `width` pixels of the screen."""
    from .canvas import Canvas
    c = Canvas(1, 1)
    out = []
    for line in text.splitlines():
        line = line.rstrip()
        while line:
            n = len(line)
            while n > 1 and c.text_width(line[:n]) > width:
                n -= 1
            if n < len(line) and " " in line[:n].strip():              # break at a space when there is one
                n = line[:n].rfind(" ")
            out.append(line[:n])
            line = line[n:].lstrip()
    return out


class Action(ScrollView):
    """Runs one command on OK and shows its output; the page scrolls (Up/Down) when it does not fit."""
    MAX_LINES = 60

    def __init__(self, module, run=run_cmd, spawn=_thread):
        super().__init__()
        self.m, self.run, self.spawn = module, run, spawn
        self.title = module.title
        self.busy = False               # a command runs (the info too)
        self.running = False            # the command of the user runs: shown as "running..."
        self.rc = None
        self.out = []
        self.info = []
        self.earned = False

    def on_enter(self, gothi):
        self.refresh_info()

    def refresh_info(self):
        if "info" in self.m.cmds and not self.busy:
            self.busy = True
            self.spawn(self._info)

    def _info(self):
        self.info = _wrap(self.run(self.m.cmds["info"])[1])[:SHOWN_INFO]
        self.busy = False

    def _go(self):
        rc, out = self.run(self.m.cmds["run"], self.m.timeout)
        self.out = _wrap(out)[-self.MAX_LINES:]
        if "info" in self.m.cmds:
            self.info = _wrap(self.run(self.m.cmds["info"])[1])[:SHOWN_INFO]
        self.rc, self.earned, self.running, self.busy = rc, rc == 0, False, False
        self.top = 0

    def key(self, k, gothi):
        if k == keys.OK and not self.busy:
            self.busy = self.running = True
            self.rc = None
            self.spawn(self._go)
        else:
            super().key(k, gothi)

    def tick(self, now, gothi):
        if self.earned:
            self.earned = False
            if self.m.deed:
                gothi.deed(self.m.deed)

    def rows(self, gothi):
        state = "running..." if self.running else "OK = run" if self.rc is None else "done" if self.rc == 0 else f"failed ({self.rc})"
        return [state] + self.info + ([""] if self.out else []) + self.out


class Level(Scene):
    """A number between min and max: Left/Right (or Down/Up) change it by `step`; the command `set` runs in the background, the last value wins."""
    HOLD = 3.0                          # seconds after a change during which the value read back does not overwrite what the user chose

    def __init__(self, module, run=run_cmd, spawn=_thread, clock=time.time):
        self.m, self.run, self.spawn, self.clock = module, run, spawn, clock
        self.title = module.title
        self.value = None
        self.target = None              # a value that waits to be set
        self.applying = False
        self.reading = False
        self.changed_at = -1e9
        self.checked = 0.0
        self.earned = False
        self.rewarded = False

    def on_enter(self, gothi):
        self.refresh()

    def refresh(self):
        if not self.reading:
            self.reading = True
            self.spawn(self._read)

    def _read(self):
        _, out = self.run(self.m.cmds["get"])
        mt = re.search(r"-?\d+", out)
        if mt and self.target is None and not self.applying and self.clock() - self.changed_at > self.HOLD:
            self.value = min(self.m.hi, max(self.m.lo, int(mt.group())))
        self.reading = False

    def change(self, d):
        cur = self.m.lo if self.value is None else self.value
        v = min(self.m.hi, max(self.m.lo, cur + d * self.m.step))
        self.value, self.target, self.changed_at = v, v, self.clock()
        if not self.applying:
            self.applying = True
            self.spawn(self._apply)

    def _apply(self):
        while self.target is not None:
            v, self.target = self.target, None
            self.run(self.m.cmds["set"].replace("{value}", str(int(v))))
            self.earned = True
        self.applying = False

    def key(self, k, gothi):
        if k in (keys.RIGHT, keys.UP):
            self.change(1)
        elif k in (keys.LEFT, keys.DOWN):
            self.change(-1)
        elif k == keys.BACK:
            gothi.pop()

    def tick(self, now, gothi):
        if self.earned:
            self.earned = False
            if self.m.deed and not self.rewarded:
                self.rewarded = True                    # one deed per visit, not one per step
                gothi.deed(self.m.deed)
        if now - self.checked > POLL:
            self.checked = now
            self.refresh()

    def draw(self, c, gothi):
        c.text(2, 2, self.title)
        c.hline(0, 9, c.w)
        txt = "..." if self.value is None else f"{self.value}{self.m.unit}"
        c.text(4, 14, txt, scale=3)
        if self.value is not None:
            w = c.w - 10
            c.frame(4, 44, w + 2, 8)
            c.box(5, 45, w * (self.value - self.m.lo) // (self.m.hi - self.m.lo), 6)
        hint = "< > change"
        c.text(c.w - 4 - c.text_width(hint), 20, hint)


SCENES = {"switch": Switch, "action": Action, "level": Level}


def scene_for(module):
    return SCENES[module.kind](module)


def modules_menu(modules, errors):
    """The submenu Modules: one row per module, then the modules that failed to load (OK shows why)."""
    from .apps import Message
    items = [(m.title, (lambda g, m=m: scene_for(m)), m.icon) for m in modules if m.menu == "modules"]
    items += [("! " + n, (lambda g, e=e, n=n: Message(n[:20], [e[i:i + 24] for i in range(0, len(e), 24)] or ["?"]))) for n, e in errors]
    if not items:
        return Message("Modules", ["none installed", "(see README of gothi)"])
    return Menu("Modules", items)
