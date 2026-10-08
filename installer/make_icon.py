"""Draw the installer's art from the app's pixel sprites:
lithnode.ico (16 to 256 px), wizard.bmp (welcome/finish side panel) and wizard-small.bmp (corner logo), at 1x and 2x.
"""
import math
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SPRITES = {
    "crab":   ("#D97757", ["..########..", "..#e####e#..", "############", "############", "..########..", "..########..", "..#.#..#.#..", "..#.#..#.#.."]),
    "scout":  ("#2fb5a0", ["...#....#...", "....#..#....", "..########..", ".#e######e#.", ".##########.", "..########..", "...#.##.#...", "..##....##.."]),
    "bug":    ("#6cc070", ["..k......k..", "...k....k...", "..########..", ".#e##kk##e#.", "#####kk#####", ".####kk####.", "#.########.#", "#..#....#..#"]),
    "rocket": ("#bb9af7", [".....##.....", "....####....", "...######...", "...#e##e#...", "...######...", "..########..", ".##.####.##.", "....k..k...."]),
}
ONYX = (10, 10, 10)


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


class Canvas:
    def __init__(self, w, h, fill=ONYX, alpha=255):
        self.w, self.h = w, h
        self.px = [[(*fill, alpha) for _ in range(w)] for _ in range(h)]

    def put(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = (*c, 255)

    def sprite(self, name, x0, y0, cell):
        color, rows = SPRITES[name]
        body, dark = rgb(color), tuple(int(v * .6) for v in rgb(color))
        for ry, row in enumerate(rows):
            for rx, ch in enumerate(row):
                if ch == ".":
                    continue
                c = (20, 10, 6) if ch == "e" else dark if ch == "k" else body
                for y in range(int(y0 + ry * cell), int(y0 + (ry + 1) * cell)):
                    for x in range(int(x0 + rx * cell), int(x0 + (rx + 1) * cell)):
                        self.put(x, y, c)

    def png(self):
        raw = b"".join(b"\0" + b"".join(bytes(p) for p in row) for row in self.px)

        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

    def bmp(self):
        pad = (4 - self.w * 3 % 4) % 4
        body = b"".join(b"".join(bytes((b, g, r)) for r, g, b, _ in row) + b"\0" * pad for row in reversed(self.px))
        return (b"BM" + struct.pack("<IHHI", 54 + len(body), 0, 0, 54)
                + struct.pack("<IiiHHIIiiII", 40, self.w, self.h, 1, 24, 0, len(body), 2835, 2835, 0, 0) + body)


def icon_png(size):
    c, r = Canvas(size, size, (20, 20, 20), 0), size * .22
    for y in range(size):
        for x in range(size):
            cx, cy = min(max(x, r), size - 1 - r), min(max(y, r), size - 1 - r)
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                c.px[y][x] = (20, 20, 20, 255)
    c.sprite("crab", size / 14, size * 3 / 14, size / 14)
    return c.png()


def side_panel(scale):
    """Welcome/finish side panel: onyx, a warm glow, a dot grid, the crab big and its crew under it."""
    w, h = 240 * scale, 459 * scale
    c = Canvas(w, h)
    gx, gy, rad = w * .5, h * .42, h * .55
    for y in range(h):
        for x in range(w):
            d = math.hypot(x - gx, (y - gy) * .9) / rad
            glow = max(0.0, 1 - d) ** 2 * .55
            c.px[y][x] = (int(10 + (217 - 10) * glow * .5), int(10 + (119 - 10) * glow * .5), int(10 + (87 - 10) * glow * .5), 255)
    step = 12 * scale
    for y in range(step // 2, h, step):
        for x in range(step // 2, w, step):
            for dy in range(scale):
                for dx in range(scale):
                    r, g, b, _ = c.px[y + dy][x + dx]
                    c.px[y + dy][x + dx] = (min(255, r + 14), min(255, g + 14), min(255, b + 14), 255)
    cell = 12 * scale
    c.sprite("crab", w / 2 - 6 * cell, h * .30, cell)
    small = 4 * scale
    crew = ["scout", "bug", "rocket"]
    span = len(crew) * 12 * small + (len(crew) - 1) * 10 * scale
    for i, name in enumerate(crew):
        c.sprite(name, w / 2 - span / 2 + i * (12 * small + 10 * scale), h * .62, small)
    # an orange rule near the bottom, like the site's accent bars
    for y in range(int(h * .86), int(h * .86) + 2 * scale):
        for x in range(int(w * .3), int(w * .7)):
            c.put(x, y, (217, 119, 87))
    return c.bmp()


def corner(scale):
    size = 58 * scale
    c = Canvas(size, size, (14, 14, 14))
    cell = size / 14
    c.sprite("crab", cell, cell * 3, cell)
    return c.bmp()


sizes = (256, 64, 48, 32, 16)
images = [icon_png(s) for s in sizes]
offset, entries = 6 + 16 * len(images), b""
for img, s in zip(images, sizes):
    entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), offset)
    offset += len(img)
(HERE / "lithnode.ico").write_bytes(struct.pack("<HHH", 0, 1, len(images)) + entries + b"".join(images))
for scale in (1, 2):
    (HERE / f"wizard-{scale}x.bmp").write_bytes(side_panel(scale))
    (HERE / f"wizard-small-{scale}x.bmp").write_bytes(corner(scale))
print("installer art written")
