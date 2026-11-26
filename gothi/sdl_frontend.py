"""The SDL 2 frontend, the same code on the PC and on the N900 (needs PySDL2; on the phone libSDL2 from /opt/sdl2).

Two layouts, like the Flipper app for the computer:
  keyboard  the screen as large as possible (x6 = 768x384), keys: arrows, Enter = OK, Backspace / Esc / Ctrl = Back
  touch     the screen (x4) on the left, a cross and the Back button drawn on the right, a finger works as the mouse
The N900 chooses by the keyboard slide (open = keyboard); F2 switches by hand, `--mode` sets it.
"""
import ctypes
import os
import time

if os.path.isdir("/opt/sdl2/lib"):                      # the N900 (libsdl2 of the n900-resurrection repository)
    os.environ.setdefault("PYSDL2_DLL_PATH", "/opt/sdl2/lib")
import sdl2  # noqa: E402

from . import keys, sysinfo  # noqa: E402
from .canvas import H, W, Canvas  # noqa: E402

INK, BG = (0, 0, 0), (0, 0, 0)                          # black ink, black window; the colour of the paper is a setting
WIN_W, WIN_H = 800, 480
KEYMAP = {
    sdl2.SDLK_UP: keys.UP, sdl2.SDLK_DOWN: keys.DOWN, sdl2.SDLK_LEFT: keys.LEFT, sdl2.SDLK_RIGHT: keys.RIGHT,
    sdl2.SDLK_RETURN: keys.OK, sdl2.SDLK_KP_ENTER: keys.OK, sdl2.SDLK_SPACE: keys.OK,
    sdl2.SDLK_BACKSPACE: keys.BACK, sdl2.SDLK_ESCAPE: keys.BACK, sdl2.SDLK_LCTRL: keys.BACK, sdl2.SDLK_RCTRL: keys.BACK,
}
REPEAT = (keys.UP, keys.DOWN, keys.LEFT, keys.RIGHT)


def rgb565(rgb):
    return ((rgb[0] >> 3) << 11) | ((rgb[1] >> 2) << 5) | (rgb[2] >> 3)


def map_key(sym, typing=False):
    """The key of gothi for an SDL key symbol, None when it is not one. While a scene types, the space bar is a character (it arrives as text input),
    not OK."""
    if typing and sym == sdl2.SDLK_SPACE:
        return None
    return KEYMAP.get(sym)


class Layout:
    """Where the screen and the touch buttons are on the 800x480 window."""
    def __init__(self, mode, h=H):
        self.mode, self.h = mode, h
        if mode == "keyboard":
            self.scale, self.x, self.y = 6, (WIN_W - W * 6) // 2, (WIN_H - h * 6) // 2
            self.buttons = {}
        else:
            self.scale, self.x, self.y = 4, 16, 24 if h > 64 else 40
            cx, cy, r, wx = 664, 180, 52, 60       # the cross: centre, height of a key, width of a key (wide: easier for a finger)
            self.buttons = {
                keys.UP: (cx - wx, cy - 2 * r, 2 * wx, 2 * r), keys.DOWN: (cx - wx, cy, 2 * wx, 2 * r),
                keys.LEFT: (cx - 2 * wx, cy - r, 2 * wx, 2 * r), keys.RIGHT: (cx, cy - r, 2 * wx, 2 * r),
                keys.OK: (cx - wx // 2, cy - r // 2, wx, r),
                keys.BACK: (cx - 2 * wx, 362, 4 * wx, 90),
            }
            self.buttons_order = [keys.OK, keys.UP, keys.DOWN, keys.LEFT, keys.RIGHT, keys.BACK]
        self.screen = (self.x, self.y, W * self.scale, h * self.scale)

    def hit(self, px, py):
        for k in getattr(self, "buttons_order", []):        # the first match wins: OK is first because it lies on top of the cross
            x, y, w, h = self.buttons[k]
            if x <= px < x + w and y <= py < y + h:
                return k
        return None


class Frontend:
    def __init__(self, gothi, mode="auto", fullscreen=None):
        self.gothi, self.want = gothi, mode
        if fullscreen is None:
            fullscreen = sysinfo.is_n900()
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO) != 0:
            raise RuntimeError(sdl2.SDL_GetError().decode())
        flags = sdl2.SDL_WINDOW_SHOWN | (sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP if fullscreen else 0)
        self.win = sdl2.SDL_CreateWindow(b"gothi", sdl2.SDL_WINDOWPOS_CENTERED, sdl2.SDL_WINDOWPOS_CENTERED, WIN_W, WIN_H, flags)
        if not self.win:
            raise RuntimeError(sdl2.SDL_GetError().decode())
        self.canvas = self.buf = self.small = self.arr = None
        self.paper = self.height = None
        self.layout = None
        self.apply_settings()
        self.set_mode("keyboard")
        self.last_slide = 0
        self.snapshot = None
        self.down = None                                      # (key, time of the next repeat) of a held touch button
        self.typing = False                                   # SDL text input is on
        self.running = True

    # ---- settings ---------------------------------------------------------
    def apply_settings(self):
        """Rebuild the canvas when the height of the screen changed, the colour tables when the colour did."""
        st = self.gothi.settings
        if st.height != self.height:
            self.height = st.height
            self.gothi.h = self.height
            self.canvas = Canvas(W, self.height)
            self.buf = bytearray(W * self.height * 2)           # RGB565, the format of the phone: the blit is a plain scaled copy
            self.arr = (ctypes.c_ubyte * len(self.buf)).from_buffer(self.buf)
            self.small = sdl2.SDL_CreateRGBSurfaceWithFormatFrom(self.arr, W, self.height, 16, W * 2, sdl2.SDL_PIXELFORMAT_RGB565)
            if self.layout is not None:
                self.layout = Layout(self.layout.mode, self.height)
            self.snapshot = None
        if st.color != self.paper:
            self.paper = st.color
            p, i = rgb565(self.paper), rgb565(INK)
            self.lo = (bytes([p & 255, i & 255]) + bytes(254))
            self.hi = (bytes([p >> 8, i >> 8]) + bytes(254))
            self.snapshot = None

    # ---- mode -------------------------------------------------------------
    def set_mode(self, mode):
        if self.layout is None or self.layout.mode != mode:
            self.layout = Layout(mode, self.height)
            self.gothi.mode = mode
            self.snapshot = None

    def auto_mode(self, now):
        if self.want in ("keyboard", "touch"):
            self.set_mode(self.want)
        elif now - self.last_slide > 0.5:
            self.last_slide = now
            s = sysinfo.slide_open()
            if s is not None:
                self.set_mode("keyboard" if s else "touch")

    # ---- drawing ----------------------------------------------------------
    def draw_touch_ui(self, surf):
        fmt = surf.contents.format
        col = lambda rgb: sdl2.SDL_MapRGB(fmt, *rgb)             # noqa: E731
        for k in self.layout.buttons_order:
            x, y, w, h = self.layout.buttons[k]
            pressed = self.down and self.down[0] == k
            r = sdl2.SDL_Rect(x + 2, y + 2, w - 4, h - 4)
            paper = self.paper
            dim = tuple(v // 4 for v in paper)
            sdl2.SDL_FillRect(surf, r, col(paper if pressed else dim))
            self.arrow(surf, k, x, y, w, h, col(INK if pressed else paper))

    def arrow(self, surf, k, x, y, w, h, color):
        cx, cy = x + w // 2, y + h // 2
        n = 14
        if k == keys.OK:
            sdl2.SDL_FillRect(surf, sdl2.SDL_Rect(cx - 8, cy - 8, 16, 16), color)
        elif k == keys.BACK:                                    # a bent arrow: a bar and a head
            sdl2.SDL_FillRect(surf, sdl2.SDL_Rect(cx - 10, cy - 4, 40, 8), color)
            for i in range(14):                                 # the head, pointing left
                sdl2.SDL_FillRect(surf, sdl2.SDL_Rect(cx - 24 + i * 1, cy - i, 2, 2 * i + 1), color)
        else:
            for i in range(n):
                if k == keys.UP:
                    r = sdl2.SDL_Rect(cx - i, cy - 14 + i * 2, 2 * i + 1, 2)
                elif k == keys.DOWN:
                    r = sdl2.SDL_Rect(cx - i, cy + 12 - i * 2, 2 * i + 1, 2)
                elif k == keys.LEFT:
                    r = sdl2.SDL_Rect(cx - 14 + i * 2, cy - i, 2, 2 * i + 1)
                else:
                    r = sdl2.SDL_Rect(cx + 12 - i * 2, cy - i, 2, 2 * i + 1)
                sdl2.SDL_FillRect(surf, r, color)

    def render(self):
        c = self.canvas
        self.gothi.draw(c)
        state = (bytes(c.px), self.layout.mode, self.down and self.down[0])
        if state == self.snapshot:
            return False
        self.snapshot = state
        self.buf[0::2] = c.px.translate(self.lo)
        self.buf[1::2] = c.px.translate(self.hi)
        surf = sdl2.SDL_GetWindowSurface(self.win)
        sdl2.SDL_FillRect(surf, None, sdl2.SDL_MapRGB(surf.contents.format, *BG))
        x, y, w, h = self.layout.screen
        sdl2.SDL_BlitScaled(self.small, None, surf, sdl2.SDL_Rect(x, y, w, h))
        if self.layout.mode == "touch":
            self.draw_touch_ui(surf)
        sdl2.SDL_UpdateWindowSurface(self.win)
        return True

    def screenshot(self, path):
        sdl2.SDL_SaveBMP(sdl2.SDL_GetWindowSurface(self.win), path.encode())

    # ---- input ------------------------------------------------------------
    def press(self, k):
        self.gothi.key(k)

    def handle(self, e, now):
        t = e.type
        if t == sdl2.SDL_QUIT:
            self.running = False
        elif t == sdl2.SDL_KEYDOWN:
            sym = e.key.keysym.sym
            if sym == sdl2.SDLK_F2:
                self.want = "touch" if self.layout.mode == "keyboard" else "keyboard"
            elif sym == sdl2.SDLK_q and e.key.keysym.mod & sdl2.KMOD_CTRL:
                self.running = False
            elif sym == sdl2.SDLK_BACKSPACE and self.gothi.top.text_input:
                self.gothi.text("\b")
            elif map_key(sym, self.gothi.top.text_input):
                self.press(map_key(sym, self.gothi.top.text_input))
        elif t == sdl2.SDL_TEXTINPUT:
            self.gothi.text(e.text.text.decode("utf-8", "replace"))
        elif t == sdl2.SDL_MOUSEBUTTONDOWN and e.button.button == sdl2.SDL_BUTTON_LEFT:
            k = self.layout.hit(e.button.x, e.button.y)
            if k:
                self.press(k)
                self.down = (k, now + 0.4)
        elif t == sdl2.SDL_MOUSEBUTTONUP:
            self.down = None
        elif t == sdl2.SDL_WINDOWEVENT and e.window.event in (sdl2.SDL_WINDOWEVENT_EXPOSED, sdl2.SDL_WINDOWEVENT_SHOWN):
            self.snapshot = None

    def run(self, frames=None, script=(), shot=None):
        """Main loop at ~30 fps. `script`: keys fed one per frame (tests); `frames`: stop after that many; `shot`: BMP written at the end."""
        ev = sdl2.SDL_Event()
        n = 0
        script = list(script)
        while self.running:
            now = time.time()
            self.auto_mode(now)
            self.apply_settings()
            while sdl2.SDL_PollEvent(ctypes.byref(ev)):
                self.handle(ev, now)
            if script:
                item = script.pop(0)
                if item.startswith("t:"):
                    self.gothi.text(item[2:])                       # typed text (tests): t:hello\bx
                else:
                    self.press(item)
            if self.down and self.down[0] in REPEAT and now >= self.down[1]:
                self.press(self.down[0])
                self.down = (self.down[0], now + 0.12)
            self.gothi.tick(now)
            want = bool(self.gothi.top.text_input)               # the text input of SDL runs only while a scene types
            if want != self.typing:
                (sdl2.SDL_StartTextInput if want else sdl2.SDL_StopTextInput)()
                self.typing = want
            self.render()
            n += 1
            if frames is not None and n >= frames:
                break
            sdl2.SDL_Delay(33)
        if shot:
            self.render()
            self.screenshot(shot)
        sdl2.SDL_DestroyWindow(self.win)
        sdl2.SDL_Quit()
