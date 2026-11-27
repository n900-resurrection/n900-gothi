"""Bluetooth data for the scan screens. Pure functions over the text of `hcitool scan` and of the files in /var/lib/bluetooth, so everything is testable without
a phone. A scan is an inquiry: the phone asks the devices around which are discoverable and they answer (about 6 seconds, works as the normal user)."""
import glob
import re
import subprocess
import time

INQUIRY = ["hcitool", "scan", "--flush", "--class", "--length=5"]        # --length is in units of 1.28 s

MAJOR = {1: "computer", 2: "phone", 3: "network", 4: "audio/video", 5: "input", 6: "imaging", 7: "wearable", 8: "toy", 9: "med"}
SHORT = {1: "comp", 2: "phone", 3: "net", 4: "a/v", 5: "input", 6: "image", 7: "wear", 8: "toy", 9: "med"}
AUDIO_MINOR = {1: "headset", 2: "handsfree", 4: "microphone", 5: "loudspeaker", 6: "headphones", 7: "portable audio", 8: "car audio", 9: "set-top box",
               10: "hi-fi", 11: "VCR", 12: "camera", 13: "camcorder", 14: "video monitor", 15: "video display", 16: "conference", 18: "game"}
MAC = r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})"


def major(cls):
    return (cls >> 8) & 0x1F if cls is not None else 0


def minor(cls):
    return (cls >> 2) & 0x3F if cls is not None else 0


def kind(cls):
    """The long name of the class of a device ("phone", "headphones", "keyboard"), "unknown" without a class."""
    m = major(cls)
    if m == 4 and minor(cls) in AUDIO_MINOR:
        return AUDIO_MINOR[minor(cls)]
    if m == 5:
        bits = minor(cls) >> 4                          # the two top bits of the minor class: keyboard, pointing device
        return {1: "keyboard", 2: "mouse", 3: "keyboard/mouse"}.get(bits, "input")
    return MAJOR.get(m, "unknown")


def short_kind(cls):
    """The same in at most five characters for a row of the list."""
    k = kind(cls)
    if k in ("headset", "headphones", "handsfree", "microphone", "loudspeaker", "car audio", "portable audio", "hi-fi"):
        return "audio"
    if k in ("video monitor", "video display"):
        return "tv"
    if k in ("keyboard", "mouse", "keyboard/mouse"):
        return "input"
    return SHORT.get(major(cls), "?")


def parse_scan(text):
    """The text of `hcitool scan --class` -> [{addr, name, cls (int or None), cached}] in the order given; a device whose name was not answered has name ""."""
    devs = []
    for block in re.split(r"\n\s*\n", "\n" + text):
        m = re.search(r"BD Address:\s*" + MAC, block)
        if not m:
            continue
        d = {"addr": m.group(1).upper(), "name": "", "cls": None, "cached": False}
        m = re.search(r"Device name:\s*(.*)", block)
        if m:
            name = m.group(1).strip()
            d["cached"] = name.endswith("[cached]")
            name = re.sub(r"\s*\[cached\]$", "", name)
            d["name"] = "" if name in ("n/a", "") else name
        m = re.search(r"\(0x([0-9A-Fa-f]{1,6})\)", block)
        if m:
            d["cls"] = int(m.group(1), 16)
        devs.append(d)
    return devs


def label(d):
    """What the list shows for a device: the name, or the end of the address when it did not tell its name."""
    return d["name"] or d["addr"][-8:]


def merge(known, devs):
    """Remember the devices seen in all scans in `known` (address -> device with `seen`, the number of scans that found it); returns the number of new ones."""
    new = 0
    for d in devs:
        old = known.get(d["addr"])
        if old is None:
            known[d["addr"]] = dict(d, seen=1)
            new += 1
        else:
            old["seen"] += 1
            if d["name"]:
                old["name"] = d["name"]
            if d["cls"] is not None:
                old["cls"] = d["cls"]
    return new


def summary(devs):
    """{count, named, kinds: {long kind: count}} of the devices of one scan."""
    kinds = {}
    for d in devs:
        kinds[kind(d["cls"])] = kinds.get(kind(d["cls"]), 0) + 1
    return {"count": len(devs), "named": sum(1 for d in devs if d["name"]), "kinds": kinds}


def paired_addresses(text):
    """The addresses in the `linkkeys` file (the devices that were paired). Only the first word of a line is read: the rest of it is the secret key."""
    return {w[0].upper() for w in (ln.split() for ln in text.splitlines()) if w and re.fullmatch(MAC, w[0])}


def known_devices(names, linkkeys, lastseen):
    """The files names, linkkeys and lastseen of an adapter -> [{addr, name, paired, last}] of the devices the phone has met, the paired ones first and then
    by name; `last` is the text of the date of the last sight ("" when unknown)."""
    paired = paired_addresses(linkkeys)
    seen = {}
    for ln in lastseen.splitlines():
        m = re.match(MAC + r"\s+(\d{4}-\d\d-\d\d)", ln)
        if m:
            seen[m.group(1).upper()] = m.group(2)
    out = []
    for ln in names.splitlines():
        m = re.match(MAC + r"\s+(.*)", ln)
        if m:
            a = m.group(1).upper()
            out.append({"addr": a, "name": m.group(2).strip(), "paired": a in paired, "last": seen.get(a, "")})
    out.sort(key=lambda d: (not d["paired"], d["name"].lower()))
    return out


def adapter_up(run=None):
    """Is the Bluetooth adapter switched on (`hciconfig hci0` says UP)? `run` gives the text, for tests."""
    try:
        out = run() if run else subprocess.run(["hciconfig", "hci0"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                               text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return re.search(r"\bUP\b", out) is not None


def scan(run=None):
    """Scan now ([] when it fails). Takes about six seconds plus a second for every device that has to be asked for its name. `run` is for tests."""
    try:
        if run:
            return parse_scan(run())
        p = subprocess.run(INQUIRY, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=40, start_new_session=True)
        return parse_scan(p.stdout)
    except (OSError, subprocess.SubprocessError):
        return []


def read_known(read=None):
    """The known devices of the first adapter directory in /var/lib/bluetooth ([] when there is none or it cannot be read). `read(name)` is for tests."""
    def default(name):
        for d in glob.glob("/var/lib/bluetooth/*/"):
            try:
                with open(d + name) as f:
                    return f.read()
            except OSError:
                continue
        return ""
    read = read or default
    return known_devices(read("names"), read("linkkeys"), read("lastseen"))


def ago(date, today=None):
    """"2026-11-27" -> "today" / "3 d" / "5 mo" / "2 y" for a short line; "" for an unknown date."""
    try:
        t = time.mktime(time.strptime(date, "%Y-%m-%d"))
    except ValueError:
        return ""
    days = int(((today or time.time()) - t) // 86400)
    if days <= 0:
        return "today"
    if days < 60:
        return f"{days} d"
    if days < 730:
        return f"{days // 30} mo"
    return f"{days // 365} y"
