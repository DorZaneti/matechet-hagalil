"""Draws a synthetic hand sketch for example 4 (the original photo isn't in the appendix).

What it shows: a stair railing, height 90, "שחור", length "to measure on site", no client name and no quantity.
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

random.seed(4)
W, H = 1000, 740
img = Image.new("RGB", (W, H), (247, 244, 236))  # paper
d = ImageDraw.Draw(img)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
f_big, f = ImageFont.truetype(FONT, 40), ImageFont.truetype(FONT, 32)
INK = (35, 45, 90)


def rtl(s: str) -> str:  # PIL with libraqm already lays out RTL text, so nothing to flip
    return s


def wobbly(p1, p2, width=4):
    (x1, y1), (x2, y2) = p1, p2
    pts = []
    for i in range(11):
        t = i / 10
        pts.append((x1 + (x2 - x1) * t + random.uniform(-2.5, 2.5), y1 + (y2 - y1) * t + random.uniform(-2.5, 2.5)))
    d.line(pts, fill=INK, width=width, joint="curve")


# stairs
x, y = 260, 640
for _ in range(7):
    wobbly((x, y), (x, y - 60))
    wobbly((x, y - 60), (x + 90, y - 60))
    x, y = x + 90, y - 60
wobbly((260, 640), (x, 640), 2)
# railing: posts + handrail
posts = [(305 + 90 * i, 580 - 60 * i) for i in range(0, 7, 2)]
for px, py in posts:
    wobbly((px, py), (px, py - 150), 5)
wobbly((posts[0][0], posts[0][1] - 150), (posts[-1][0], posts[-1][1] - 150), 6)
# height dimension on the first post
hx = posts[0][0] - 45
wobbly((hx, posts[0][1]), (hx, posts[0][1] - 150), 2)
d.text((hx - 140, posts[0][1] - 95), rtl("גובה 90"), font=f, fill=INK)
# length with a question mark
wobbly((260, 680), (x, 680), 2)
d.text((400, 686), rtl("אורך ? למדוד באתר"), font=f, fill=INK)
# notes
d.text((40, 40), rtl("מעקה למדרגות"), font=f_big, fill=INK)
d.text((40, 100), rtl("צבע שחור"), font=f, fill=INK)
d.text((40, 150), rtl("עמודים כל 1.2 בערך"), font=f, fill=INK)

out = Path(__file__).parent / "sketch_example4.png"
img.save(out)
print(out)
