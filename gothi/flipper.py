"""Reads the graphics of the Flipper Zero firmware as they are in its source tree, so that new ones can be dropped in (tools/fetch-assets.sh).

* PNG files (1 bit; palette or gray; other types work too): decoded here with zlib, no Pillow. Dark pixel = ink, like the firmware does (`png2xbm`).
* An animation is a folder `NAME_WxH/` with `frame_0.png`, `frame_1.png`, ... and `meta.txt` (Filetype: Flipper Animation): frame rate, the order
  of the frames, the speech bubbles. An animated icon is a folder with `frame_rate` instead of `meta.txt`; a still icon is a single `NAME_WxH.png`.
* `manifest.txt` lists the animations of a group with the conditions of the dolphin (level, butthurt, weight).
"""
import os
import struct
import zlib

from .canvas import Canvas


# Where the firmware graphics are: GOTHI_ASSETS, else assets/flipper of the source tree (tools/fetch-assets.sh), else /opt/gothi/share/flipper (the package).
_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.environ.get("GOTHI_ASSETS") or next(
    (d for d in (os.path.join(_here, "assets", "flipper"), "/opt/gothi/share/flipper") if os.path.isdir(d)), os.path.join(_here, "assets", "flipper"))
_icons = {}


class Image:
    """A one bit picture: `px` has width*height bytes, 1 = ink."""
    def __init__(self, w, h, px):
        self.w, self.h, self.px = w, h, px


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def read_png(path):
    """Decode a non-interlaced PNG into an Image (ink where the pixel is dark and not transparent)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    pos, idat, plte, trns = 8, [], None, None
    while pos < len(data):
        n, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"tRNS":
            trns = body
        elif typ == b"IDAT":
            idat.append(body)
        elif typ == b"IEND":
            break
    if interlace:
        raise ValueError(f"{path}: interlaced PNG is not supported")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp_bits = channels * depth
    stride = (w * bpp_bits + 7) // 8
    step = max(1, bpp_bits // 8)
    raw = zlib.decompress(b"".join(idat))
    rows, prev = [], bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        cur = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f == 1:
            for i in range(step, stride):
                cur[i] = (cur[i] + cur[i - step]) & 255
        elif f == 2:
            for i in range(stride):
                cur[i] = (cur[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                cur[i] = (cur[i] + ((cur[i - step] if i >= step else 0) + prev[i]) // 2) & 255
        elif f == 4:
            for i in range(stride):
                cur[i] = (cur[i] + _paeth(cur[i - step] if i >= step else 0, prev[i], prev[i - step] if i >= step else 0)) & 255
        rows.append(cur)
        prev = cur
    px = bytearray(w * h)
    if depth == 1 and ctype in (0, 3) and not trns:             # the usual case in the firmware: fast, a table of eight pixels per byte
        if ctype == 0:
            ink = (1, 0)                                         # index 0 = black
        else:
            ink = tuple(1 if sum(plte[3 * i:3 * i + 3]) < 384 else 0 for i in range(2))
        table = [bytes(ink[b >> (7 - k) & 1] for k in range(8)) for b in range(256)]
        for y, row in enumerate(rows):
            px[y * w:(y + 1) * w] = b"".join([table[b] for b in row])[:w]
        return Image(w, h, px)
    for y, row in enumerate(rows):
        for x in range(w):
            if depth < 8:
                v = (row[x * depth // 8] >> (8 - depth - (x * depth) % 8)) & ((1 << depth) - 1)
            elif depth == 8:
                v = row[x * channels:(x + 1) * channels]
            else:
                v = row[x * channels * 2:(x + 1) * channels * 2:2]
            alpha = 255
            if ctype == 3:
                i = v if depth < 8 else v[0]
                r, g, b = plte[3 * i:3 * i + 3]
                if trns and i < len(trns):
                    alpha = trns[i]
            elif ctype == 0:
                r = g = b = (v * 255 // ((1 << depth) - 1)) if depth < 8 else v[0]
            elif ctype == 4:
                r = g = b = v[0]
                alpha = v[1]
            else:
                r, g, b = v[0], v[1], v[2]
                alpha = v[3] if ctype == 6 else 255
            if alpha >= 128 and (r + g + b) < 384:
                px[y * w + x] = 1
    return Image(w, h, px)


def read_fields(path):
    """The `Key: value` files of the firmware. Returns a list of (key, value) in file order (a key may repeat: Slot, Name)."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if ":" in line and not line.startswith("#"):
                k, _, v = line.partition(":")
                out.append((k.strip(), v.strip()))
    return out


class Animation:
    """A folder of the firmware: frames and, for the dolphin animations, the meta.txt."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path.rstrip("/"))
        self.frame_rate, self.order, self.bubbles = 2, None, []
        self.passive, self.active, self.cycles, self.duration, self.cooldown = 0, 0, 1, 0, 0
        meta, rate = os.path.join(path, "meta.txt"), os.path.join(path, "frame_rate")
        if os.path.exists(meta):
            cur = None
            for k, v in read_fields(meta):
                if k == "Frame rate":
                    self.frame_rate = max(1, int(v))
                elif k == "Frames order":
                    self.order = [int(x) for x in v.split()]
                elif k == "Passive frames":
                    self.passive = int(v)
                elif k == "Active frames":
                    self.active = int(v)
                elif k == "Active cycles":
                    self.cycles = max(1, int(v))
                elif k == "Duration":
                    self.duration = int(v)
                elif k == "Active cooldown":
                    self.cooldown = int(v)
                elif k == "Slot":
                    cur = {}
                    self.bubbles.append(cur)
                elif cur is not None and k in ("X", "Y", "StartFrame", "EndFrame"):
                    cur[k] = int(v)
                elif cur is not None:
                    cur[k] = v.replace("\\n", "\n")
        elif os.path.exists(rate):
            with open(rate) as f:
                self.frame_rate = max(1, int(f.read().split()[0]))
        files = sorted((int(f[6:-4]), f) for f in os.listdir(path) if f.startswith("frame_") and f.endswith(".png") and f[6:-4].isdigit())
        n = len(files)                       # dolphin animations count from frame_0, animated icons from frame_01
        self.frames = [read_png(os.path.join(path, f)) for _, f in files]
        if not self.order:
            self.order = list(range(n))
        self.w, self.h = (self.frames[0].w, self.frames[0].h) if self.frames else (0, 0)

    def frame_at(self, t):
        """The frame to show `t` seconds after the start (the animation loops)."""
        return self.frames[self.order[int(t * self.frame_rate) % len(self.order)]]


class Playback:
    """The life of one dolphin animation: the passive frames loop; `activate()` (the user does something) plays the active frames `Active cycles` times,
    then the passive ones again and a cooldown of `Active cooldown` seconds before the next activation. `at(now)` gives (frame, position in `Frames order`);
    the position selects the speech bubbles (StartFrame..EndFrame). An animation without Passive/Active frames (an icon) just loops."""

    def __init__(self, anim, now):
        self.anim = anim
        order = anim.order
        self.passive_seq = order[:anim.passive] if anim.passive else order
        self.active_seq = order[anim.passive:anim.passive + anim.active] if anim.passive else []
        self.state, self.t0, self.cooldown_until, self.cycles = "passive", now, 0.0, 0

    def activate(self, now):
        if self.state == "passive" and self.active_seq and now >= self.cooldown_until:
            self.state, self.t0, self.cycles = "active", now, self.anim.cycles
            return True
        return False

    def at(self, now):
        a = self.anim
        i = int((now - self.t0) * a.frame_rate)
        if self.state == "active":
            if i >= self.cycles * len(self.active_seq):
                self.state, self.t0, self.cooldown_until = "passive", now, now + a.cooldown
                return self.at(now)
            k = i % len(self.active_seq)
            return a.frames[self.active_seq[k]], len(self.passive_seq) + k
        k = i % len(self.passive_seq)
        return a.frames[self.passive_seq[k]], k

    def bubbles(self, pos):
        return [b for b in self.anim.bubbles if b.get("StartFrame", 0) <= pos <= b.get("EndFrame", -1)]


def draw_bubble(c, b, ox=0, oy=0):
    """A speech bubble of a Slot of meta.txt: a box with rounded corners around the text (lines split at \\n); X, Y is the anchor, AlignH / AlignV tell
    on which side of it the box lies (Left: the box starts at X, Right: ends at X, Center: centred; Bottom: the box ends at Y, Top: starts at Y). A short
    tail points at the anchor. An approximation of elements_bubble_str of the firmware."""
    lines = b.get("Text", "").split("\n")
    w = max(c.text_width(t) for t in lines) + 6
    h = 7 * len(lines) + 4
    x, y = b.get("X", 0) + ox, b.get("Y", 0) + oy
    ah, av = b.get("AlignH", "Left"), b.get("AlignV", "Bottom")
    bx = x if ah == "Left" else (x - w if ah == "Right" else x - w // 2)
    by = y - h if av == "Bottom" else (y if av == "Top" else y - h // 2)
    c.box(bx, by, w, h, 0)
    c.frame(bx, by, w, h)
    for cx, cy in ((bx, by), (bx + w - 1, by), (bx, by + h - 1), (bx + w - 1, by + h - 1)):      # rounded corners
        c.pixel(cx, cy, 0)
    for i, t in enumerate(lines):
        c.text(bx + 3, by + 3 + i * 7, t)
    if av in ("Bottom", "Top"):                                                                 # the tail
        ty = by + h if av == "Bottom" else by - 3
        tx = bx + 3 if ah != "Right" else bx + w - 6
        for k in range(3):
            c.hline(tx + (k if av == "Top" else 0), ty + k if av == "Bottom" else ty + 2 - k, 3 - k, 1)


def read_manifest(path):
    """manifest.txt of a group: a list of dicts (Name, Min butthurt, Max butthurt, Min level, Max level, Weight)."""
    items = []
    for k, v in read_fields(path):
        if k == "Name":
            items.append({"Name": v})
        elif items:
            items[-1][k] = v
    return items


class Still:
    """A single PNG icon with the interface of an Animation."""
    def __init__(self, path):
        self.frames = [read_png(path)]
        self.w, self.h = self.frames[0].w, self.frames[0].h

    def frame_at(self, t):
        return self.frames[0]


def load_icon(rel):
    """An icon of the firmware by its path below ASSETS ('icons/MainMenu/Settings_14' is an animated icon, 'icons/Power/Battery_16x16.png' a still one);
    None when it is not there. Loaded once."""
    if rel not in _icons:
        path = os.path.join(ASSETS, rel)
        try:
            _icons[rel] = Animation(path) if os.path.isdir(path) else Still(path)
        except (OSError, ValueError, KeyError):
            _icons[rel] = None
    return _icons[rel]


def pick(manifest, level, rng, butthurt=0):
    """A random animation name of a manifest by Weight among those that fit the level (Min/Max level) and butthurt (Min/Max butthurt)."""
    ok = [m for m in manifest if int(m.get("Min level", 1)) <= level <= int(m.get("Max level", 99))
          and int(m.get("Min butthurt", 0)) <= butthurt <= int(m.get("Max butthurt", 99))]
    if not ok:
        ok = manifest                      # nothing fits the level: any animation is better than none
    return rng.choices([m["Name"] for m in ok], weights=[max(1, int(m.get("Weight", 1))) for m in ok])[0]


def blit(c, image, x, y, scale=1, v=1):
    """Draw the ink of an Image on a Canvas (white stays transparent, like canvas_draw_icon); v=0 draws it in paper colour (on an inverted row)."""
    for j in range(image.h):
        row = image.px[j * image.w:(j + 1) * image.w]
        for i in range(image.w):
            if row[i]:
                if scale == 1:
                    c.pixel(x + i, y + j, v)
                else:
                    c.box(x + i * scale, y + j * scale, scale, scale, v)


Canvas.blit = lambda self, image, x, y, scale=1, v=1: blit(self, image, x, y, scale, v)
