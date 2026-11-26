"""User settings, kept in ~/.config/gothi/settings.json (every failure to read or write is ignored: the defaults are used)."""
import json
import os

PRESETS = [("Orange", (255, 100, 0)), ("Flipper", (255, 130, 0)), ("Amber", (255, 176, 0)), ("Green", (60, 220, 60)),
           ("Cyan", (0, 200, 220)), ("White", (235, 235, 235))]
DEFAULTS = {"color": list(PRESETS[0][1]), "screen": "classic", "border": True, "happy": False}
SCREENS = {"classic": 64, "tall": 80}        # rows of the screen: the Flipper has 64; 80 fills the height of the N900 (128x80 at x6 = 768x480)


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(os.path.expanduser("~"), ".config", "gothi", "settings.json")
        self.data = dict(DEFAULTS)
        try:
            with open(self.path) as f:
                loaded = json.load(f)
            for k in DEFAULTS:
                if k in loaded:
                    self.data[k] = loaded[k]
            self.data["color"] = [min(255, max(0, int(v))) for v in self.data["color"][:3]]
            self.data["happy"] = bool(self.data["happy"])
            if self.data["screen"] not in SCREENS:
                self.data["screen"] = "classic"
        except (OSError, ValueError, TypeError):
            self.data = dict(DEFAULTS)

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v

    @property
    def color(self):
        return tuple(self.data["color"])

    @property
    def height(self):
        return SCREENS[self.data["screen"]]

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self.data, f)
        except OSError:
            pass
