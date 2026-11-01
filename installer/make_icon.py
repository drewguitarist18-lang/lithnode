"""Draw the installer's art from the app's pixel crab:
lithnode.ico (16 to 256 px), and the one-click installer's crab and Install button (oneclick/, one per display scale).
"""
import math
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).parent
ONYX = (10, 10, 10)
WHITE = (236, 235, 230)
# Lithnode's crab: the logo
LOGO = [".##..........##.", "#.#..........#.#", "###..........###", ".#............#.", ".#............#.", ".##.########.##.",
        "..############..", "..##.######.##..", "..############..", "...##########...", "...#.#....#.#...", "...#.#....#.#...",
        "..##.##..##.##.."]


class Canvas:
    def __init__(self, w, h, fill=ONYX, alpha=255):
        self.w, self.h = w, h
        self.px = [[(*fill, alpha) for _ in range(w)] for _ in range(h)]

    def put(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = (*c, 255)

    def logo(self, x0, y0, cell, color=WHITE):
        for ry, row in enumerate(LOGO):
            for rx, ch in enumerate(row):
                if ch == "#":
                    for y in range(int(y0 + ry * cell), int(y0 + (ry + 1) * cell)):
                        for x in range(int(x0 + rx * cell), int(x0 + (rx + 1) * cell)):
                            self.put(x, y, color)

    def png(self):
        raw = b"".join(b"\0" + b"".join(bytes(p) for p in row) for row in self.px)

        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def icon_png(size):
    c, r = Canvas(size, size, (20, 20, 20), 0), size * .22
    for y in range(size):
        for x in range(size):
            cx, cy = min(max(x, r), size - 1 - r), min(max(y, r), size - 1 - r)
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                c.px[y][x] = (20, 20, 20, 255)
    cell = size / 20
    c.logo((size - 16 * cell) / 2, (size - 13 * cell) / 2, cell)
    return c.png()


def oneclick_crab(scale):
    """The crab alone on a clear background, for the one-click window: whole-pixel cells so it stays crisp."""
    cell = round(5 * scale)
    c = Canvas(16 * cell, 13 * cell, (0, 0, 0), 0)
    c.logo(0, 0, cell)
    return c.png()


def oneclick_pill(scale, w=132, h=40):
    """The Install button: a white pill with soft (anti-aliased) ends on a clear background."""
    W, H = round(w * scale), round(h * scale)
    r = H / 2
    c = Canvas(W, H, (0, 0, 0), 0)
    for y in range(H):
        for x in range(W):
            cx = min(max(x + .5, r), W - r)
            d = math.hypot(x + .5 - cx, y + .5 - r) - r   # < 0 inside
            a = max(0.0, min(1.0, .5 - d))
            if a:
                c.px[y][x] = (*WHITE, round(a * 255))
    return c.png()


ONECLICK_SCALES = {100: 1, 125: 1.25, 150: 1.5, 175: 1.75, 200: 2, 250: 2.5, 300: 3}

sizes = (256, 64, 48, 32, 16)
images = [icon_png(s) for s in sizes]
offset, entries = 6 + 16 * len(images), b""
for img, s in zip(images, sizes, strict=True):
    entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), offset)
    offset += len(img)
(HERE / "lithnode.ico").write_bytes(struct.pack("<HHH", 0, 1, len(images)) + entries + b"".join(images))
(HERE / "lithnode.png").write_bytes(icon_png(512))
(HERE.parent / "static" / "logo-512.png").write_bytes(icon_png(512))   # Mac and Linux
art = HERE / "oneclick"
art.mkdir(exist_ok=True)
for pct, scale in ONECLICK_SCALES.items():
    (art / f"crab-{pct}.png").write_bytes(oneclick_crab(scale))
    (art / f"pill-{pct}.png").write_bytes(oneclick_pill(scale))
print("installer art written")
