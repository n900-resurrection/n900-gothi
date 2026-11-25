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
        meta, rate = os.path.join(path, "meta.txt"), os.path.join(path, "frame_rate")
        if os.path.exists(meta):
            cur = None
            for k, v in read_fields(meta):
                if k == "Frame rate":
                    self.frame_rate = max(1, int(v))
                elif k == "Frames order":
                    self.order = [int(x) for x in v.split()]
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


def read_manifest(path):
    """manifest.txt of a group: a list of dicts (Name, Min butthurt, Max butthurt, Min level, Max level, Weight)."""
    items = []
    for k, v in read_fields(path):
        if k == "Name":
            items.append({"Name": v})
        elif items:
            items[-1][k] = v
    return items


def blit(c, image, x, y, scale=1):
    """Draw the ink of an Image on a Canvas (white stays transparent, like canvas_draw_icon)."""
    for j in range(image.h):
        row = image.px[j * image.w:(j + 1) * image.w]
        for i in range(image.w):
            if row[i]:
                if scale == 1:
                    c.pixel(x + i, y + j)
                else:
                    c.box(x + i * scale, y + j * scale, scale, scale)


Canvas.blit = lambda self, image, x, y, scale=1: blit(self, image, x, y, scale)
