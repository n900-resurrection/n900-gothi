"""A 128x64 one bit canvas, the screen of the Flipper Zero. Pure Python, no dependencies."""
from . import font

W, H = 128, 64


class Canvas:
    def __init__(self, w=W, h=H):
        self.w, self.h = w, h
        self.px = bytearray(w * h)          # 1 = ink (black), 0 = paper

    def clear(self, v=0):
        self.px[:] = bytes([v]) * (self.w * self.h)

    def pixel(self, x, y, v=1):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y * self.w + x] = v

    def hline(self, x, y, n, v=1):
        if 0 <= y < self.h and n > 0:
            x0, x1 = max(x, 0), min(x + n, self.w)
            if x1 > x0:
                self.px[y * self.w + x0:y * self.w + x1] = bytes([v]) * (x1 - x0)

    def vline(self, x, y, n, v=1):
        for j in range(y, y + n):
            self.pixel(x, j, v)

    def box(self, x, y, w, h, v=1):
        """A filled rectangle."""
        for j in range(y, y + h):
            self.hline(x, j, w, v)

    def frame(self, x, y, w, h, v=1):
        """The outline of a rectangle."""
        self.hline(x, y, w, v)
        self.hline(x, y + h - 1, w, v)
        self.vline(x, y, h, v)
        self.vline(x + w - 1, y, h, v)

    def invert(self, x, y, w, h):
        for j in range(max(y, 0), min(y + h, self.h)):
            for i in range(max(x, 0), min(x + w, self.w)):
                self.px[j * self.w + i] ^= 1

    def text_width(self, s, scale=1):
        return sum(font.GLYPHS.get(ch, font.GLYPHS["?"])[0] for ch in s) * scale if s else 0

    def text(self, x, y, s, scale=1, v=1):
        """Draw `s` with the top of the capital letters at row `y`; returns the width drawn."""
        x0 = x
        for ch in s:
            adv, rows = font.GLYPHS.get(ch, font.GLYPHS["?"])
            for r, bits in enumerate(rows):
                if not bits:
                    continue
                yy = y + (r - font.CAP_TOP) * scale
                for c in range(adv):
                    if bits >> c & 1:
                        if scale == 1:
                            self.pixel(x + c, yy, v)
                        else:
                            self.box(x + c * scale, yy, scale, scale, v)
            x += adv * scale
        return x - x0

    def to_text(self):
        """The screen as lines of # and . (for tests and for a terminal)."""
        return "\n".join("".join("#" if self.px[y * self.w + x] else "." for x in range(self.w)) for y in range(self.h))
