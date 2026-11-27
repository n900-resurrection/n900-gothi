"""Bluetooth scan for gothi (bundled): the discoverable devices around (name, kind, address), a summary and the devices the phone has met before.
A scan is an inquiry (`hcitool scan`, about six seconds, works as the normal user); it repeats while a scan screen is on top and stops when you leave.
Bluetooth has to be on (Settings > Bluetooth). The data code is gothi/bluetooth.py."""
import threading
import time

from gothi import bluetooth, keys
from gothi.apps import Message
from gothi.ui import Menu, ScrollView

PERIOD = 4                                            # seconds of rest between two scans while a scan screen is on top (a scan itself takes about six)


def _thread(fn):
    threading.Thread(target=fn, daemon=True).start()


class Scanner:
    """The last scan, refreshed in the background: a screen calls poll() from its tick(), so it scans only while one is on top."""

    def __init__(self, scan=bluetooth.scan, up=bluetooth.adapter_up, spawn=_thread, clock=time.time):
        self.scan, self.up, self.spawn, self.clock = scan, up, spawn, clock
        self.devs, self.known, self.on, self.scans = [], {}, True, 0
        self.stamp, self.busy = None, False

    def poll(self):
        if self.busy or (self.stamp is not None and self.clock() - self.stamp < PERIOD):
            return
        self.busy = True
        self.spawn(self._work)

    def _work(self):
        try:
            self.on = self.up()
            devs = self.scan() if self.on else []
            self.devs = devs
            bluetooth.merge(self.known, devs)
            self.scans += 1
        finally:
            self.stamp = self.clock()
            self.busy = False

    def find(self, addr):
        return self.known.get(addr)                    # every device that was found is in `known`, with the count of scans


class Devices(Menu):
    """The devices of the last scan; OK shows one."""

    def __init__(self, sc):
        super().__init__("Devices", [("scanning...", lambda g: Message("Bluetooth scan", ["scanning..."]))])
        self.sc, self.shown, self.ids, self.was_busy = sc, None, [None], None

    def tick(self, now, gothi):
        self.sc.poll()
        if self.sc.stamp is None:
            return
        if self.shown is self.sc.devs and self.was_busy == self.sc.busy:
            return
        devs = self.shown = self.sc.devs
        self.was_busy = self.sc.busy
        keep = self.ids[self.sel] if self.sel < len(self.ids) else None
        if not self.sc.on:
            self.ids = [None]
            self.title, self.items = "Bluetooth is off", [("switch it on in Settings", lambda g: Message("Bluetooth scan", ["Bluetooth is off:", "Settings > Bluetooth"]))]
        elif not devs:
            self.ids = [None]
            self.title, self.items = "Devices" + (" ..." if self.sc.busy else ""), [("none found", lambda g: Message("Bluetooth scan", ["no discoverable", "devices found"]))]
        else:
            self.title = f"Devices {len(devs)}" + (" ..." if self.sc.busy else "")
            self.ids = [d["addr"] for d in devs]
            self.items = [(f"{bluetooth.label(d)[:12].rstrip()} {bluetooth.short_kind(d['cls'])}", (lambda g, a=d["addr"]: Detail(self.sc, a))) for d in devs]
        if keep in self.ids and keep is not None:
            self.sel = self.ids.index(keep)
        else:
            self.sel = min(self.sel, len(self.items) - 1)
        self.top_row = max(0, min(self.top_row, self.sel))
        self.top_row = min(max(self.top_row, self.sel - self.ROWS + 1), self.sel)


class Detail(ScrollView):
    def __init__(self, sc, addr):
        super().__init__()
        self.sc, self.addr, self.title = sc, addr, "Device"

    def tick(self, now, gothi):
        self.sc.poll()

    def rows(self, gothi):
        d = self.sc.find(self.addr)
        if d is None:
            return ["not found", self.addr]
        here = any(x["addr"] == self.addr for x in self.sc.devs)
        r = [bluetooth.label(d), d["addr"], f"kind {bluetooth.kind(d['cls'])}", "in range" if here else "out of range", f"seen in {d['seen']} scans"]
        if d["cls"] is not None:
            r.append(f"class 0x{d['cls']:06x}")
        return r


class Summary(ScrollView):
    title = "Summary"

    def __init__(self, sc):
        super().__init__()
        self.sc = sc

    def tick(self, now, gothi):
        self.sc.poll()

    def rows(self, gothi):
        s = bluetooth.summary(self.sc.devs)
        r = [f"devices {s['count']}", f"with a name {s['named']}"]
        r += [f"{k} {v}" for k, v in sorted(s["kinds"].items(), key=lambda kv: -kv[1])]
        r += [f"seen in total {len(self.sc.known)}", f"scans {self.sc.scans}"]
        if not self.sc.on:
            r.insert(0, "Bluetooth is off")
        return r


class Known(Menu):
    """The devices the phone has met (its own lists), `*` marks the paired ones."""

    def __init__(self, read=bluetooth.read_known):
        devs = read()
        items = [(("* " if d["paired"] else "  ") + (d["name"] or d["addr"])[:20], (lambda g, d=d: self._info(d))) for d in devs]
        super().__init__("Known devices", items or [("none known", lambda g: Message("Bluetooth scan", ["no known devices"]))])

    @staticmethod
    def _info(d):
        when = bluetooth.ago(d["last"])
        return Message((d["name"] or "device")[:20], [d["addr"], "paired" if d["paired"] else "not paired"] + ([f"last seen {when}"] if when else []))


def create(module):
    sc = Scanner()
    menu = Menu("Bluetooth scan", [("Devices", lambda g: Devices(sc)), ("Summary", lambda g: Summary(sc)), ("Known devices", lambda g: Known())])
    menu.deed_name = module.deed
    return menu
