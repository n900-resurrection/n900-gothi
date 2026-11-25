"""What the system tells: battery, keyboard slide. Every function works on the PC too (returns None or a made-up value)."""
import os
import re
import subprocess
import threading
import time

SLIDE = "/sys/devices/platform/gpio-switch/slide/state"
_cache = {}


def is_n900():
    return os.path.exists(SLIDE)


def slide_open():
    """True when the keyboard is slid out, None when this is not an N900."""
    try:
        with open(SLIDE) as f:
            return f.read().strip() == "open"
    except OSError:
        return None


def _cached(key, ttl, fn):
    now = time.time()
    if key not in _cache or now - _cache[key][0] > ttl:
        _cache[key] = (now, fn())
    return _cache[key][1]


def _battery_n900():
    out = subprocess.run(["hal-device"], capture_output=True, text=True, timeout=10).stdout
    vals = dict(re.findall(r"^\s*(battery\.[\w.]+) = '?(\w+)'?", out, re.M))
    cur, full = int(vals.get("battery.reporting.current", 0)), int(vals.get("battery.reporting.last_full", 0))
    return {"percent": min(100, 100 * cur // full) if full else None,
            "mV": int(vals["battery.voltage.current"]) if "battery.voltage.current" in vals else None,
            "mAh": cur, "full_mAh": full, "charging": vals.get("battery.rechargeable.is_charging") == "true"}


def _battery_sysfs():
    base = "/sys/class/power_supply"
    for d in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        try:
            with open(f"{base}/{d}/capacity") as f:
                pct = int(f.read())
            with open(f"{base}/{d}/status") as f:
                st = f.read().strip()
            return {"percent": pct, "mV": None, "mAh": None, "full_mAh": None, "charging": st == "Charging"}
        except (OSError, ValueError):
            continue
    return None


_battery_state = {"value": None, "time": 0.0, "busy": False}


def battery():
    """{'percent', 'mV', 'mAh', 'full_mAh', 'charging'} or None. Never blocks: the data is read in a thread at most every 10 seconds
    (hal-device is slow), the last value is returned meanwhile (None before the first one arrives)."""
    st = _battery_state
    if not st["busy"] and time.time() - st["time"] > 10:
        st["busy"] = True

        def work():
            try:
                st["value"] = _battery_n900() if is_n900() else _battery_sysfs()
            except Exception:  # noqa: BLE001
                st["value"] = None
            st["time"], st["busy"] = time.time(), False
        threading.Thread(target=work, daemon=True).start()
    return st["value"]
