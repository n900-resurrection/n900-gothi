"""Scenes and the manager that holds them: a stack, the top scene draws and gets the keys (like the view dispatcher of the Flipper firmware)."""
import os

import time

from . import flipper, keys, sysinfo


class Scene:
    title = ""
    deed_name = None           # the deed (rules.json) the dolphin gets for opening this scene

    def draw(self, c, gothi):
        pass

    def key(self, k, gothi):
        if k == keys.BACK:
            gothi.pop()

    def on_enter(self, gothi):
        """Called when the scene is pushed: by default it reports the deed named in `deed_name`."""
        if self.deed_name:
            gothi.deed(self.deed_name)

    def tick(self, now, gothi):
        pass


class Gothi:
    def __init__(self, root, settings=None, dolphin=None):
        from .dolphin import DolphinState
        from .settings import Settings
        self.stack = [root]
        self.mode = "keyboard"             # set by the frontend: "keyboard" or "touch"
        self.settings = settings or Settings(path=os.devnull)
        self.h = self.settings.height      # rows of the screen, set by the frontend when it changes
        self.dolphin = dolphin or DolphinState(path="")      # the character: XP and butthurt (without a file unless given)
        self._levelups = []
        self._checked = 0

    def deed(self, name):
        """The dolphin did something worth XP. A level-up is confirmed at once and announced by a message on top of the stack at the next key or tick."""
        if self.dolphin.deed(name):
            if self.dolphin.levelup_pending():
                self.dolphin.confirm_levelup()
                self._levelups.append(self.dolphin.level)
            self.dolphin.save()

    def _announce(self):
        from .apps import Message
        while self._levelups:
            self.stack.append(Message("Level up!", [f"The dolphin is now", f"level {self._levelups.pop(0)}"]))

    @property
    def top(self):
        return self.stack[-1]

    def push(self, scene):
        self.stack.append(scene)
        scene.on_enter(self)

    def pop(self):
        if len(self.stack) > 1:
            self.stack.pop()

    def key(self, k):
        self.top.key(k, self)
        self._announce()

    def tick(self, now):
        self.top.tick(now, self)
        if now - self._checked > 60:                       # the day and the butthurt move slowly
            self._checked = now
            if self.dolphin.update(now):
                self.dolphin.save()
        self._announce()

    def draw(self, c):
        c.clear()
        self.top.draw(c, self)


class ScrollView(Scene):
    """A page of rows that scrolls when it does not fit (the number of rows is worked out from the screen height). Up/Down scroll, Back leaves.
    A subclass gives `rows(gothi)`: a list of strings, or ("bar", 0..1) for a progress bar."""
    ROW = 10

    def __init__(self):
        self.top = 0

    def rows(self, gothi):
        return []

    def visible(self, h):
        return max(1, (h - 12) // self.ROW)

    def _clamp(self, n, h):
        self.top = max(0, min(self.top, n - self.visible(h)))

    def draw(self, c, gothi):
        c.text(2, 2, self.title)
        c.hline(0, 9, c.w)
        rows = self.rows(gothi)
        n = self.visible(c.h)
        self._clamp(len(rows), c.h)
        for i, r in enumerate(rows[self.top:self.top + n]):
            y = 12 + i * self.ROW
            if isinstance(r, tuple):
                w = c.w - 14 if len(rows) <= n else c.w - 18
                c.frame(4, y + 1, w + 2, 7)
                c.box(5, y + 2, int(w * min(1.0, max(0.0, r[1]))), 5)
            else:
                c.text(4, y + (self.ROW - 5) // 2, r)
        if len(rows) > n:                                     # scroll bar, as in the Menu
            bar = c.h - 12
            c.vline(c.w - 2, 11, bar)
            h = max(4, bar * n // len(rows))
            c.box(c.w - 3, 11 + (bar - h) * self.top // (len(rows) - n), 3, h)

    def key(self, k, gothi):
        if k == keys.UP:
            self.top -= 1
        elif k == keys.DOWN:
            self.top += 1
        elif k in (keys.BACK, keys.LEFT):
            gothi.pop()
        self._clamp(len(self.rows(gothi)), gothi.h)


class Menu(Scene):
    """A list; the selected row is inverted, a scroll bar on the right (the submenu of the Flipper)."""
    ROW = 12

    def __init__(self, title, items, status=False):
        """items: [(label, factory(gothi) -> Scene)] or (label, factory, icon) with the icon as a path below flipper.ASSETS; `status`: battery and time on the title line."""
        self.title, self.items, self.status = title, items, status
        self.selected_at = time.time()
        if any(len(i) > 2 and i[2] and flipper.load_icon(i[2]) for i in items):
            self.ROW = 16                          # rows tall enough for the 14 px icons
        self.sel = 0
        self.top_row = 0
        self.ROWS = 4

    def draw(self, c, gothi):
        c.text(2, 2, self.title)
        if self.status:
            b = sysinfo.battery()
            s = time.strftime("%H:%M") + (f" {b['percent']}%" if b and b["percent"] is not None else "")
            c.text(c.w - 2 - c.text_width(s), 2, s)
        c.hline(0, 9, c.w)
        self.ROWS = (c.h - 12) // self.ROW            # rows visible below the title bar
        for i in range(self.ROWS):
            n = self.top_row + i
            if n >= len(self.items):
                break
            y = 12 + i * self.ROW
            if n == self.sel:
                c.box(0, y - 1, c.w - 5, self.ROW - 1)
            ink = 0 if n == self.sel else 1
            x = 4
            icon = flipper.load_icon(self.items[n][2]) if len(self.items[n]) > 2 and self.items[n][2] else None
            if self.ROW == 16:
                x = 24
                if icon:
                    c.blit(icon.frame_at(time.time() - self.selected_at if n == self.sel else 0), 4, y + (self.ROW - 1 - icon.h) // 2, v=ink)
            c.text(x, y + (self.ROW - 5) // 2, self.items[n][0], v=ink)
        if len(self.items) > self.ROWS:                       # scroll bar
            bar = c.h - 12
            c.vline(c.w - 2, 11, bar)
            h = max(4, bar * self.ROWS // len(self.items))
            y = 11 + (bar - h) * self.top_row // (len(self.items) - self.ROWS)
            c.box(c.w - 3, y, 3, h)

    def key(self, k, gothi):
        self.ROWS = (gothi.h - 12) // self.ROW
        n = len(self.items)
        if k == keys.UP:
            self.sel = (self.sel - 1) % n
        elif k == keys.DOWN:
            self.sel = (self.sel + 1) % n
        elif k in (keys.OK, keys.RIGHT):
            gothi.push(self.items[self.sel][1](gothi))
        elif k in (keys.BACK, keys.LEFT):
            gothi.pop()
        self.top_row = min(max(self.top_row, self.sel - self.ROWS + 1), self.sel)
        self.selected_at = time.time()
