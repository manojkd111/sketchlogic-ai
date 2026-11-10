"""Whiteboard-style rendering of a `Spec` + `Layout` with Pillow.

Style is randomised per sample (ink colour, stroke width, wobble, background, blur) so a model
trained on these images learns structure rather than one pixel style. Shapes hint at node kinds
the way people draw them: cylinders for databases, ellipses for actors, a doubled border for
external systems, divided boxes for queues.
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .generate import Box, Layout, Spec

BACKGROUNDS = [(250, 250, 247), (255, 255, 255), (246, 243, 235), (238, 241, 236)]
INKS = [(25, 25, 25), (28, 58, 150), (24, 92, 52), (90, 40, 120)]
FONT_SIZE = 18
LABEL_FONT_SIZE = 14

Point = tuple[float, float]


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def node_widths(spec: Spec) -> dict[str, float]:
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    f = font(FONT_SIZE)
    return {n.id: max(140.0, probe.textlength(n.label, font=f) + 44) for n in spec.nodes}


class _Pen:
    def __init__(self, draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
        self.draw = draw
        self.rng = rng
        self.ink = rng.choice(INKS)
        self.width = rng.choice([2, 2, 3, 3, 4])
        self.wobble = rng.uniform(0.3, 2.2)

    def line(self, a: Point, b: Point, *, dashed: bool = False) -> None:
        length = math.dist(a, b)
        if length < 1:
            return
        steps = max(2, int(length / 18))
        nx, ny = (a[1] - b[1]) / length, (b[0] - a[0]) / length  # unit normal
        pts: list[Point] = []
        for i in range(steps + 1):
            t = i / steps
            off = 0.0 if i in (0, steps) else self.rng.gauss(0, self.wobble)
            pts.append((a[0] + (b[0] - a[0]) * t + nx * off, a[1] + (b[1] - a[1]) * t + ny * off))
        if dashed:
            for i in range(0, len(pts) - 1, 2):
                self.draw.line([pts[i], pts[i + 1]], fill=self.ink, width=self.width)
        else:
            self.draw.line(pts, fill=self.ink, width=self.width, joint="curve")

    def rect(self, box: Box, *, dashed: bool = False) -> None:
        x, y, w, h = box
        # Slight overshoot at corners, like a marker.
        o = self.rng.uniform(0, 4)
        self.line((x - o, y), (x + w + o, y), dashed=dashed)
        self.line((x + w, y - o), (x + w, y + h + o), dashed=dashed)
        self.line((x + w + o, y + h), (x - o, y + h), dashed=dashed)
        self.line((x, y + h + o), (x, y - o), dashed=dashed)

    def ellipse(self, box: Box) -> None:
        x, y, w, h = box
        cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2, h / 2
        steps = 36
        pts = [
            (
                cx + (rx + self.rng.gauss(0, self.wobble / 2)) * math.cos(2 * math.pi * i / steps),
                cy + (ry + self.rng.gauss(0, self.wobble / 2)) * math.sin(2 * math.pi * i / steps),
            )
            for i in range(steps + 1)
        ]
        self.draw.line(pts, fill=self.ink, width=self.width, joint="curve")

    def arrowhead(self, tip: Point, frm: Point) -> None:
        angle = math.atan2(tip[1] - frm[1], tip[0] - frm[0])
        size = 10 + self.width * 2
        for side in (-1, 1):
            a = angle + math.pi - side * math.radians(self.rng.uniform(22, 30))
            self.line(tip, (tip[0] + size * math.cos(a), tip[1] + size * math.sin(a)))


def _shape(pen: _Pen, kind: str, box: Box) -> None:
    x, y, w, h = box
    if kind == "actor":
        pen.ellipse(box)
    elif kind == "database":
        cap = 12.0
        pen.ellipse((x, y, w, cap * 2))
        pen.line((x, y + cap), (x, y + h - cap))
        pen.line((x + w, y + cap), (x + w, y + h - cap))
        pen.draw.arc((x, y + h - cap * 2, x + w, y + h), 0, 180, fill=pen.ink, width=pen.width)
    elif kind == "queue":
        pen.rect(box)
        for i in (1, 2):
            xi = x + w - 12 * i
            pen.line((xi, y + 4), (xi, y + h - 4))
    elif kind == "external":
        pen.rect(box)
        pen.rect((x + 5, y + 5, w - 10, h - 10))
    else:
        pen.rect(box)


def _text_center(
    draw: ImageDraw.ImageDraw, text: str, center: Point, f: object, fill: object
) -> None:
    draw.text(center, text, font=f, fill=fill, anchor="mm")  # type: ignore[arg-type]


def render(spec: Spec, lay: Layout, rng: random.Random) -> Image.Image:
    bg = rng.choice(BACKGROUNDS)
    img = Image.new("RGB", (lay.width, lay.height), bg)
    draw = ImageDraw.Draw(img)
    pen = _Pen(draw, rng)
    f, small = font(FONT_SIZE), font(LABEL_FONT_SIZE)

    for g in spec.groups:
        gx, gy, _, _ = lay.groups[g.id]
        pen.rect(lay.groups[g.id], dashed=True)
        draw.text((gx + 12, gy + 8), g.label, font=small, fill=pen.ink)

    for n in spec.nodes:
        box = lay.nodes[n.id]
        _shape(pen, n.kind, box)
        _text_center(draw, n.label, (box[0] + box[2] / 2, box[1] + box[3] / 2), f, pen.ink)

    for e in spec.edges:
        s, t = lay.nodes[e.source], lay.nodes[e.target]
        a: Point = (s[0] + s[2] + 4, s[1] + s[3] / 2)
        b: Point = (t[0] - 4, t[1] + t[3] / 2)
        pen.line(a, b)
        pen.arrowhead(b, a)
        if e.direction == "bidirectional":
            pen.arrowhead(a, b)
        if e.label:
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 12
            tw = draw.textlength(e.label, font=small)
            draw.rectangle((mx - tw / 2 - 3, my - 9, mx + tw / 2 + 3, my + 9), fill=bg)
            _text_center(draw, e.label, (mx, my), small, pen.ink)

    blur = rng.uniform(0.0, 0.8)
    return img.filter(ImageFilter.GaussianBlur(blur)) if blur > 0.2 else img
