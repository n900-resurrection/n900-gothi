"""Scenes and the manager that holds them: a stack, the top scene draws and gets the keys (like the view dispatcher of the Flipper firmware)."""
import os

from . import keys


class Scene:
    title = ""

    def draw(self, c, gothi):
        pass

    def key(self, k, gothi):
        if k == keys.BACK:
            gothi.pop()

    def tick(self, now, gothi):
        pass


class Gothi:
    def __init__(self, root, settings=None):
        from .settings import Settings
        self.stack = [root]
        self.mode = "keyboard"             # set by the frontend: "keyboard" or "touch"
        self.settings = settings or Settings(path=os.devnull)
        self.h = self.settings.height      # rows of the screen, set by the frontend when it changes

    @property
    def top(self):
        return self.stack[-1]

    def push(self, scene):
        self.stack.append(scene)

    def pop(self):
        if len(self.stack) > 1:
            self.stack.pop()

    def key(self, k):
        self.top.key(k, self)

    def tick(self, now):
        self.top.tick(now, self)

    def draw(self, c):
        c.clear()
        self.top.draw(c, self)


class Menu(Scene):
    """A list; the selected row is inverted, a scroll bar on the right (the submenu of the Flipper)."""
    ROW = 12

    def __init__(self, title, items):
        self.title, self.items = title, items      # items: [(label, factory(gothi) -> Scene)]
        self.sel = 0
        self.top_row = 0
        self.ROWS = 4

    def draw(self, c, gothi):
        c.text(2, 2, self.title)
        c.hline(0, 9, c.w)
        self.ROWS = (c.h - 12) // self.ROW            # rows visible below the title bar
        for i in range(self.ROWS):
            n = self.top_row + i
            if n >= len(self.items):
                break
            y = 12 + i * self.ROW
            if n == self.sel:
                c.box(0, y - 1, c.w - 5, self.ROW - 1)
            c.text(4, y + 2, self.items[n][0], v=0 if n == self.sel else 1)
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
