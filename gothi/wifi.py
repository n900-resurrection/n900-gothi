"""Wi-Fi data for the scan, channel and saved-network screens, and for the wardriving module (#16). Pure functions over the text of `iwlist wlan0 scan` and
`gconftool-2 -R /system/osso/connectivity/IAP`, so everything is testable without a phone. Passive: it only reads what the access points announce."""
import re
import subprocess

CHANNELS_24 = range(1, 14)


def parse_scan(text):
    """The text of `iwlist wlan0 scan` -> [{bssid, ssid, channel, signal (dBm), quality (0-100), security, hidden}] in the order given."""
    nets = []
    for block in re.split(r"\n\s*Cell \d+ - ", "\n" + text)[1:]:
        n = {"bssid": "", "ssid": "", "channel": 0, "signal": None, "quality": None, "security": "OPEN", "hidden": False}
        m = re.match(r"Address:\s*([0-9A-Fa-f:]{17})", block)
        if not m:
            continue
        n["bssid"] = m.group(1).upper()
        m = re.search(r'ESSID:"(.*)"', block)
        ssid = m.group(1) if m else ""
        n["hidden"] = ssid.strip("\x00") == "" or re.fullmatch(r"(\\x00)+", ssid) is not None
        n["ssid"] = "" if n["hidden"] else ssid
        m = re.search(r"Channel:(\d+)", block)
        if m:
            n["channel"] = int(m.group(1))
        m = re.search(r"Signal level[=:]\s*(-?\d+)", block)
        if m:
            n["signal"] = int(m.group(1))
        m = re.search(r"Quality[=:]\s*(\d+)/(\d+)", block)
        if m and int(m.group(2)):
            n["quality"] = round(100 * int(m.group(1)) / int(m.group(2)))
        n["security"] = _security(block)
        nets.append(n)
    return nets


def _security(block):
    if "Encryption key:off" in block:
        return "OPEN"
    wpa2 = "IEEE 802.11i/WPA2" in block
    wpa = re.search(r"IE: WPA Version", block) is not None
    base = "WPA/WPA2" if wpa and wpa2 else "WPA2" if wpa2 else "WPA" if wpa else "WEP"
    if base != "WEP" and re.search(r"Authentication Suites.*802\.1x", block):
        return base + " EAP"
    return base


def sort_by_signal(nets):
    """The strongest first; networks without a level go last."""
    return sorted(nets, key=lambda n: -(n["signal"] if n["signal"] is not None else -999))


def bar(signal):
    """A signal level in dBm -> 0..4 bars (-50 or better is full, -90 or worse is none)."""
    if signal is None:
        return 0
    return max(0, min(4, round((signal + 90) / 10)))


def channel_usage(nets):
    """{channel: number of networks} for the 2.4 GHz channels that have any (the picture of a crowded band)."""
    use = {}
    for n in nets:
        if n["channel"] in CHANNELS_24:
            use[n["channel"]] = use.get(n["channel"], 0) + 1
    return use


def best_channel(nets):
    """The 2.4 GHz channel with the least interference: a network on channel c disturbs c-4..c+4, weighted by how close it is and by its signal."""
    load = {c: 0.0 for c in CHANNELS_24}
    for n in nets:
        if n["channel"] not in CHANNELS_24:
            continue
        w = 1.0 + (max(-90, min(-30, n["signal"])) + 90) / 30 if n["signal"] is not None else 1.0
        for c in CHANNELS_24:
            d = abs(c - n["channel"])
            if d < 5:
                load[c] += w * (5 - d) / 5
    return min(CHANNELS_24, key=lambda c: (load[c], c))


def summary(nets):
    """Numbers for a statistics screen."""
    sec = {}
    for n in nets:
        sec[n["security"]] = sec.get(n["security"], 0) + 1
    sig = [n["signal"] for n in nets if n["signal"] is not None]
    return {"count": len(nets), "hidden": sum(1 for n in nets if n["hidden"]), "open": sec.get("OPEN", 0), "security": sec,
            "strongest": max(sig) if sig else None, "channels": channel_usage(nets)}


def merge(known, nets):
    """Keep the best sample per BSSID in `known` ({bssid: net}); returns the BSSIDs that were new (for the wardriving log and the dolphin)."""
    new = []
    for n in nets:
        old = known.get(n["bssid"])
        if old is None:
            known[n["bssid"]] = dict(n)
            new.append(n["bssid"])
        elif (n["signal"] if n["signal"] is not None else -999) > (old["signal"] if old["signal"] is not None else -999):
            known[n["bssid"]] = dict(n)
    return new


def _iwlist(sudo, runner=subprocess.run):
    cmd = (["sudo"] if sudo else []) + ["iwlist", "wlan0", "scan"]
    # no terminal and no input: a sudo without the rule fails at once instead of asking for a password
    p = runner(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=15, start_new_session=True)
    return p.stdout


def scan(run=None):
    """Scan now ([] when the interface is off or the tool fails). Takes about a second on the N900. A fresh scan needs root: the package gothi has a sudo rule
    for exactly this command; without it the results of the last scan are read (only what somebody scanned before, often one network). `run` is for tests."""
    if run:
        try:
            return parse_scan(run())
        except (OSError, subprocess.SubprocessError):
            return []
    for sudo in (True, False):
        try:
            nets = parse_scan(_iwlist(sudo))
        except (OSError, subprocess.SubprocessError):
            continue
        if nets:
            return nets
    return []


def decode_ssid(value):
    """GConf stores an SSID as a list of bytes, "[75,111,...]" -> the text."""
    nums = [int(x) for x in re.findall(r"\d+", value or "")]
    return bytes(nums).decode("utf-8", "replace")


def saved_networks(text):
    """The text of `gconftool-2 -R /system/osso/connectivity/IAP` -> [{id, name, ssid, security, hidden}] of the Wi-Fi entries only (mobile data is skipped)."""
    out = []
    for block in re.split(r"^ /system/osso/connectivity/IAP/", text, flags=re.M)[1:]:
        head, _, rest = block.partition(":\n")
        kv = dict(re.findall(r"^\s+(\w+) = (.*)$", rest, flags=re.M))
        if not kv.get("type", "").startswith("WLAN"):
            continue
        ssid = decode_ssid(kv.get("wlan_ssid", ""))
        out.append({"id": head.strip(), "name": kv.get("name") or ssid, "ssid": ssid, "security": kv.get("wlan_security", ""),
                    "hidden": kv.get("wlan_hidden") == "true"})
    return out
