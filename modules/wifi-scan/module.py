"""Wi-Fi scan for gothi (bundled): the networks around (name, security, signal), how crowded the 2.4 GHz channels are, a summary and the saved networks.
Passive: it only lists what the access points announce (`iwlist wlan0 scan`, about a second, works as the normal user). The data code is gothi/wifi.py."""
import os
import threading
import time

from gothi import keys, wifi
from gothi.apps import Message
from gothi.modules import run_cmd
from gothi.ui import Menu, Scene, ScrollView

PERIOD = 5                                            # seconds between two scans while a scan screen is on top


def _thread(fn):
    threading.Thread(target=fn, daemon=True).start()


def wlan_present():
    return os.path.exists("/sys/class/net/wlan0")


class Scanner:
    """The last scan, refreshed in the background: a screen calls poll() from its tick(), so it scans only while one is on top."""

    def __init__(self, scan=wifi.scan, present=wlan_present, spawn=_thread, clock=time.time):
        self.scan, self.present, self.spawn, self.clock = scan, present, spawn, clock
        self.nets, self.known, self.on, self.scans = [], {}, True, 0
        self.stamp, self.busy = None, False

    def poll(self):
        if self.busy or (self.stamp is not None and self.clock() - self.stamp < PERIOD):
            return
        self.busy = True
        self.spawn(self._work)

    def _work(self):
        try:
            self.on = self.present()
            nets = self.scan() if self.on else []
            self.nets = wifi.sort_by_signal(nets)
            wifi.merge(self.known, nets)
            self.scans += 1
        finally:
            self.stamp = self.clock()
            self.busy = False

    def find(self, bssid):
        return next((n for n in self.nets if n["bssid"] == bssid), None)


SHORT = {"WPA/WPA2": "WPA12", "WPA2 EAP": "EAP", "WPA EAP": "EAP", "WPA/WPA2 EAP": "EAP"}      # the list row has room for five characters


def _name(n):
    return n["ssid"] or "(hidden)"


class Networks(Menu):
    """The networks, the strongest first; OK shows one."""

    def __init__(self, sc):
        super().__init__("Networks", [("scanning...", lambda g: Message("Wi-Fi scan", ["scanning..."]))])
        self.sc, self.shown, self.ids = sc, None, [None]               # ids: the BSSID of every row, to keep the selection on a network

    def tick(self, now, gothi):
        self.sc.poll()
        if self.shown is self.sc.nets and self.shown is not None:
            return
        nets = self.shown = self.sc.nets
        if self.sc.stamp is None:
            return
        keep = self.ids[self.sel] if self.sel < len(self.ids) else None
        if not self.sc.on:
            self.ids = [None]
            self.title, self.items = "Wi-Fi is off", [("switch it on in Settings", lambda g: Message("Wi-Fi scan", ["Wi-Fi is off:", "Settings > Wi-Fi"]))]
        elif not nets:
            self.ids = [None]
            self.title, self.items = "Networks", [("none found", lambda g: Message("Wi-Fi scan", ["no networks found"]))]
        else:
            self.title = f"Networks {len(nets)}"
            self.ids = [n["bssid"] for n in nets]
            self.items = [(f"{_name(n)[:12]} {SHORT.get(n['security'], n['security'])} {n['signal'] if n['signal'] is not None else '?'}",
                           (lambda g, b=n["bssid"]: Detail(self.sc, b))) for n in nets]
        # the selection stays on the same network when the list is reordered
        if keep in self.ids and keep is not None:
            self.sel = self.ids.index(keep)
        else:
            self.sel = min(self.sel, len(self.items) - 1)
        self.top_row = max(0, min(self.top_row, self.sel))
        self.top_row = min(max(self.top_row, self.sel - self.ROWS + 1), self.sel)


class Detail(ScrollView):
    def __init__(self, sc, bssid):
        super().__init__()
        self.sc, self.bssid, self.title = sc, bssid, "Network"

    def tick(self, now, gothi):
        self.sc.poll()

    def rows(self, gothi):
        n = self.sc.find(self.bssid)
        if n is None:
            return ["out of range", self.bssid]
        sig = n["signal"]
        return [_name(n), n["bssid"], f"channel {n['channel']}", f"signal {sig if sig is not None else '?'} dBm", ("bar", wifi.bar(sig) / 4),
                f"security {n['security']}"] + ([f"quality {n['quality']}%"] if n["quality"] is not None else [])


class Channels(Scene):
    """A column per 2.4 GHz channel: how many networks use it; the quietest channel is marked."""
    title = "Channels"

    def __init__(self, sc):
        self.sc = sc

    def tick(self, now, gothi):
        self.sc.poll()

    def draw(self, c, gothi):
        c.text(2, 2, self.title)
        c.hline(0, 9, c.w)
        nets = self.sc.nets
        use = wifi.channel_usage(nets)
        best = wifi.best_channel(nets) if nets else None
        top, base = 12, c.h - 16
        most = max(use.values(), default=1)
        step = c.w // 13
        x0 = (c.w - step * 13) // 2
        for ch in wifi.CHANNELS_24:
            x = x0 + (ch - 1) * step
            h = (base - top) * use.get(ch, 0) // most if use else 0
            c.box(x + 1, base - h, step - 2, h)
            c.hline(x, base, step)
            if ch % 2 or ch == best:
                s = str(ch)
                c.text(x + (step - c.text_width(s)) // 2, base + 3, s)
        if best:
            c.text(2, c.h - 7, f"quietest: channel {best}")
            x = x0 + (best - 1) * step + step // 2
            c.pixel(x, base + 1)
        elif not self.sc.on:
            c.text(2, c.h - 7, "Wi-Fi is off")


class Summary(ScrollView):
    title = "Summary"

    def __init__(self, sc):
        super().__init__()
        self.sc = sc

    def tick(self, now, gothi):
        self.sc.poll()

    def rows(self, gothi):
        s = wifi.summary(self.sc.nets)
        r = [f"networks {s['count']}", f"hidden {s['hidden']}", f"open {s['open']}"]
        r += [f"{k} {v}" for k, v in sorted(s["security"].items(), key=lambda kv: -kv[1])]
        if s["strongest"] is not None:
            r.append(f"strongest {s['strongest']} dBm")
        if self.sc.nets:
            r.append(f"quietest channel {wifi.best_channel(self.sc.nets)}")
        r += [f"seen in total {len(self.sc.known)}", f"scans {self.sc.scans}"]
        return r


class Saved(Menu):
    """The networks saved in the phone (the list of the connection manager), `*` marks those in range now."""

    def __init__(self, sc, run=run_cmd):
        code, out = run("gconftool-2 -R /system/osso/connectivity/IAP", 8)
        saved = wifi.saved_networks(out) if code == 0 else []
        near = {n["ssid"] for n in sc.nets}
        items = [(("* " if s["ssid"] in near else "  ") + s["name"][:20], (lambda g, s=s: self._info(s))) for s in saved]
        super().__init__("Saved networks", items or [("none saved", lambda g: Message("Wi-Fi scan", ["no saved networks"]))])

    @staticmethod
    def _info(s):
        return Message(s["name"][:20], [f"ssid {s['ssid']}"[:24], f"security {s['security'] or '?'}"[:24], "hidden" if s["hidden"] else "visible"])


def create(module):
    sc = Scanner()
    menu = Menu("Wi-Fi scan", [("Networks", lambda g: Networks(sc)), ("Channels", lambda g: Channels(sc)), ("Summary", lambda g: Summary(sc)),
                               ("Saved networks", lambda g: Saved(sc))])
    menu.deed_name = module.deed
    return menu
