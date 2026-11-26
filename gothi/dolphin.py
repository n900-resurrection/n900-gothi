"""The dolphin as a character: XP, levels and butthurt (mood), after applications/services/dolphin of the Flipper Zero firmware.

The numbers are not in the code but in rules.json: the file shipped in this package, optionally overridden value by value by ~/.config/gothi/rules.json
(dicts are merged, lists and numbers are replaced). The state (XP, butthurt, timestamps) is in ~/.config/gothi/dolphin-state.json.
All times are epoch seconds passed in by the caller, so the tests need no clock."""
import copy
import json
import os
import time

SHIPPED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.json")


def config_dir():
    return os.path.join(os.path.expanduser("~"), ".config", "gothi")


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def check_rules(r):
    """Raise ValueError when the rules cannot work (a user file must not crash the app)."""
    lv = r["levels"]
    if not lv or any(not isinstance(x, int) or x <= 0 for x in lv) or lv != sorted(set(lv)):
        raise ValueError("levels must be increasing positive integers")
    if not (0 <= int(r["clear_limits_hour"]) <= 23 and int(r["default_limit"]) >= 0):
        raise ValueError("clear_limits_hour or default_limit out of range")
    b = r["butthurt"]
    if int(b["max"]) < 0 or float(b["increase_hours"]) <= 0 or list(b["decrease_at"]) != sorted(b["decrease_at"]):
        raise ValueError("bad butthurt rules")
    for name, d in r["deeds"].items():
        if int(d["xp"]) < 0 or not d.get("group"):
            raise ValueError("bad deed " + name)
    return r


def load_rules(user_path=None, shipped=SHIPPED):
    """The shipped rules with the user's file merged over them; a missing or broken user file is ignored."""
    with open(shipped) as f:
        rules = check_rules(json.load(f))
    try:
        with open(user_path or os.path.join(config_dir(), "rules.json")) as f:
            merged = _merge(copy.deepcopy(rules), json.load(f))
        return check_rules(merged)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return rules


class DolphinState:
    FIELDS = {"xp": 0, "butthurt": 0, "group_xp": {}, "daily_xp": 0, "limits_day": "", "butthurt_at": 0.0}

    def __init__(self, rules=None, path=None, now=None):
        self.rules = rules or load_rules()
        self.path = os.path.join(config_dir(), "dolphin-state.json") if path is None else path     # path="": nothing is read or saved (tests)
        self.__dict__.update(copy.deepcopy(self.FIELDS))
        try:
            with open(self.path) as f:
                d = json.load(f)
            self.xp = max(0, int(d["xp"]))
            self.butthurt = int(d["butthurt"])
            self.group_xp = {str(k): int(v) for k, v in d["group_xp"].items()}
            self.daily_xp, self.limits_day, self.butthurt_at = int(d["daily_xp"]), str(d["limits_day"]), float(d["butthurt_at"])
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            self.__dict__.update(copy.deepcopy(self.FIELDS))
        self.butthurt = min(max(0, self.butthurt), self.rules["butthurt"]["max"])
        self.update(time.time() if now is None else now)

    # levels
    @property
    def thresholds(self):
        return self.rules["levels"]

    @property
    def level(self):
        """1 up to and including the first threshold, then one more for each threshold passed (like dolphin_get_level)."""
        return 1 + sum(1 for t in self.thresholds if self.xp > t)

    @property
    def max_level(self):
        return len(self.thresholds) + 1

    def xp_to_levelup(self):
        """XP missing to the next threshold; None on the last level."""
        for t in self.thresholds:
            if self.xp <= t:
                return t - self.xp
        return None

    def xp_in_level(self):
        """(XP gained on this level, XP the level takes); the second is None on the last level."""
        lo = ([0] + [t + 1 for t in self.thresholds])[self.level - 1]
        need = self.thresholds[self.level - 1] - lo if self.level <= len(self.thresholds) else None
        return self.xp - lo, need

    def levelup_pending(self):
        """XP stands on a threshold: the firmware waits there until the level-up is confirmed."""
        return self.xp in self.thresholds

    def confirm_levelup(self):
        if self.levelup_pending():
            self.xp += 1
            return True
        return False

    # mood
    def mood(self, happy=False):
        """The butthurt the animations see: 0 in happy mode (the real value is kept)."""
        return 0 if happy else self.butthurt

    # time
    def day_key(self, now):
        """The day for the daily limits: it starts at clear_limits_hour, not at midnight."""
        return time.strftime("%Y-%m-%d", time.localtime(now - self.rules["clear_limits_hour"] * 3600))

    def update(self, now):
        """Daily limits reset, butthurt grows by one for each increase_hours since the last count. Returns True when something changed."""
        changed = False
        key = self.day_key(now)
        if key != self.limits_day:
            self.limits_day, self.group_xp, self.daily_xp = key, {}, 0
            changed = True
        period = self.rules["butthurt"]["increase_hours"] * 3600
        if not self.butthurt_at or self.butthurt_at > now:       # first start, or the clock went back
            self.butthurt_at, changed = now, True
        n = int((now - self.butthurt_at) // period)
        if n > 0:
            self.butthurt = min(self.rules["butthurt"]["max"], self.butthurt + n)
            self.butthurt_at += n * period
            changed = True
        return changed

    # deeds
    def limit(self, group):
        return int(self.rules["limits"].get(group, self.rules["default_limit"]))

    def deed(self, name, now=None):
        """A deed happened. Returns the XP gained (0 for an unknown deed, a group at its daily limit, or a level-up waiting to be confirmed)."""
        d = self.rules["deeds"].get(name)
        if d is None:
            return 0
        now = time.time() if now is None else now
        self.update(now)
        group = d["group"]
        gain = max(0, min(int(d["xp"]), self.limit(group) - self.group_xp.get(group, 0)))
        to_up = self.xp_to_levelup()
        if to_up is not None:                                    # at the threshold the firmware adds nothing until the level-up
            gain = min(gain, to_up)
        if gain:
            self.xp += gain
            self.group_xp[group] = self.group_xp.get(group, 0) + gain
        # butthurt: -1 for each step of the daily XP passed (1, 16, 31, 46)
        steps = self.rules["butthurt"]["decrease_at"]
        old = self.daily_xp
        self.daily_xp = min(old + gain, steps[-1] if steps else 0)
        self.butthurt = max(0, self.butthurt - sum(1 for s in steps if old < s <= self.daily_xp))
        return gain

    def save(self):
        if not self.path:
            return
        d = {k: getattr(self, k) for k in self.FIELDS}
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(d, f)
            os.replace(tmp, self.path)
        except OSError:
            pass
