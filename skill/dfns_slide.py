#!/usr/bin/env python3
"""
DFNS slide builder — one spec in, an editable SVG and a brand-exact JPG out.

    python3 dfns_slide.py make slide.json            -> slide.svg + slide.jpg
    python3 dfns_slide.py build slide.json -o a.svg  -> the editable source
    python3 dfns_slide.py render slide.json -o a.jpg -> the deliverable
    python3 dfns_slide.py check slide.json           -> the fact guard alone

Why the raster is drawn natively rather than rasterized from the SVG:
cairosvg, svglib, reportlab, rsvg and resvg are all routinely absent from an
AI code sandbox, and a missing one is a hard stop. Pillow is not. So the SVG
is the source of truth for editing, and the same geometry is drawn a second
time through Pillow for the bitmap. Both read tokens.json and layouts.json,
so they cannot drift apart.

Requires: Pillow. Nothing else.
"""

import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ASSETS = os.path.join(HERE, "assets")
FONTS = os.path.join(ASSETS, "fonts")

FONT_FILES = {
    ("sans", 300): "Inter-Light.ttf",
    ("sans", 400): "Inter-Regular.ttf",
    ("sans", 500): "Inter-Medium.ttf",
    ("sans", 600): "Inter-SemiBold.ttf",
    ("mono", 300): "RobotoMono-Light.ttf",
    ("mono", 400): "RobotoMono-Light.ttf",
}


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


TOKENS = load("tokens.json")
LAYOUTS = load("layouts.json")
FACTS = load("facts.json")
with open(os.path.join(ASSETS, "icons.json"), encoding="utf-8") as fh:
    ICONS = json.load(fh)["icons"]


# --------------------------------------------------------------------------
# colour
# --------------------------------------------------------------------------

def rgba(value, default_alpha=255):
    """'#RRGGBB' or 'rgba(r,g,b,a)' -> (r, g, b, a)."""
    if value is None:
        return None
    value = value.strip()
    if value.startswith("#"):
        v = value[1:]
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), default_alpha)
    m = re.match(r"rgba?\(([^)]+)\)", value)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        r, g, b = (int(float(p)) for p in parts[:3])
        a = int(float(parts[3]) * 255) if len(parts) > 3 else default_alpha
        return (r, g, b, a)
    raise ValueError("cannot parse colour %r" % value)


def css(value):
    """Back to a string SVG understands."""
    return value


# --------------------------------------------------------------------------
# styles
# --------------------------------------------------------------------------

class Style:
    def __init__(self, name, **over):
        spec = dict(TOKENS["type"][name])
        spec.update({k: v for k, v in over.items() if v is not None})
        self.name = name
        self.font = spec.get("font", "sans")
        self.weight = int(spec.get("weight", 400))
        self.size = float(spec.get("size", 20))
        self.color = spec.get("color", "#363A5B")
        self.align = spec.get("align", "left")
        self.decoration = spec.get("decoration")
        self.case = spec.get("case")
        ls = spec.get("letterSpacing", 0)
        self.tracking = self._em(ls)
        lh = spec.get("lineHeight", "1.35em")
        self.line_height = self._len(lh)

    def _em(self, v):
        if isinstance(v, (int, float)):
            return float(v)
        v = str(v).strip()
        if v.endswith("em"):
            return float(v[:-2]) * self.size
        if v.endswith("px"):
            return float(v[:-2])
        return float(v or 0)

    def _len(self, v):
        if isinstance(v, (int, float)):
            return float(v)
        v = str(v).strip()
        if v.endswith("em"):
            return float(v[:-2]) * self.size
        if v.endswith("px"):
            return float(v[:-2])
        return self.size * 1.35

    @property
    def family(self):
        return "Inter" if self.font == "sans" else "Roboto Mono"


_font_cache = {}


def pil_font(style):
    from PIL import ImageFont
    key = (style.font, style.weight, round(style.size, 2))
    if key not in _font_cache:
        fname = FONT_FILES.get((style.font, style.weight))
        if fname is None:
            fname = FONT_FILES[(style.font, 400)]
        path = os.path.join(FONTS, fname)
        if not os.path.exists(path):
            raise SystemExit(
                "FONT MISSING: %s\n"
                "The pack cannot render without its bundled fonts. A substituted\n"
                "font would produce an off-brand slide that still claims to be on\n"
                "brand, so this is a hard stop rather than a fallback." % path
            )
        _font_cache[key] = ImageFont.truetype(path, int(round(style.size)))
    return _font_cache[key]


def text_width(text, style):
    if not text:
        return 0.0
    f = pil_font(style)
    w = f.getlength(text)
    if style.tracking:
        w += style.tracking * len(text)
    return w


def text_height(style):
    """Ascent + descent — what Figma calls a hugging text frame."""
    a, d = pil_font(style).getmetrics()
    return a + d


def wrap(text, style, max_width):
    """Greedy wrap honouring explicit newlines."""
    lines = []
    for para in str(text).split("\n"):
        words, cur = para.split(), ""
        for word in words:
            probe = (cur + " " + word).strip()
            if cur and text_width(probe, style) > max_width:
                lines.append(cur)
                cur = word
            else:
                cur = probe
        lines.append(cur)
    return lines


# --------------------------------------------------------------------------
# SVG path -> polygons (for icons and the logotype under Pillow)
# --------------------------------------------------------------------------

_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")


def _bezier3(p0, p1, p2, p3, steps=14):
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append((
            u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
        ))
    return out


def _bezier2(p0, p1, p2, steps=10):
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return out


def _arc(p0, rx, ry, rot, large, sweep, p1, steps=18):
    if rx == 0 or ry == 0 or p0 == p1:
        return [p1]
    phi = math.radians(rot)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2.0, (p0[1] - p1[1]) / 2.0
    x1 = cos_p * dx + sin_p * dy
    y1 = -sin_p * dx + cos_p * dy
    rx, ry = abs(rx), abs(ry)
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        co = -co
    cx1 = co * rx * y1 / ry
    cy1 = -co * ry * x1 / rx
    cx = cos_p * cx1 - sin_p * cy1 + (p0[0] + p1[0]) / 2.0
    cy = sin_p * cx1 + cos_p * cy1 + (p0[1] + p1[1]) / 2.0

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        n = math.hypot(ux, uy) * math.hypot(vx, vy)
        if n == 0:
            return 0.0
        a = math.acos(max(-1.0, min(1.0, dot / n)))
        return -a if ux * vy - uy * vx < 0 else a

    th1 = angle(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    dth = angle((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi
    pts = []
    for i in range(1, steps + 1):
        th = th1 + dth * i / steps
        pts.append((cos_p * rx * math.cos(th) - sin_p * ry * math.sin(th) + cx,
                    sin_p * rx * math.cos(th) + cos_p * ry * math.sin(th) + cy))
    return pts


def path_to_subpaths(d):
    """Flatten an SVG path 'd' into a list of point lists."""
    tokens = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|" + _NUM.pattern, d)
    subpaths, cur = [], []
    x = y = sx = sy = 0.0
    prev_c = prev_q = None
    i, cmd = 0, None
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                if cur:
                    subpaths.append(cur)
                    cur = []
                x, y = sx, sy
                continue
        nums = []
        need = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}[cmd.upper()]
        while len(nums) < need and i < len(tokens) and not re.match(r"[A-Za-z]", tokens[i]):
            nums.append(float(tokens[i]))
            i += 1
        if len(nums) < need:
            break
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            if cur:
                subpaths.append(cur)
            x, y = (x + nums[0], y + nums[1]) if rel else (nums[0], nums[1])
            sx, sy = x, y
            cur = [(x, y)]
            cmd = "l" if rel else "L"
        elif c == "L":
            x, y = (x + nums[0], y + nums[1]) if rel else (nums[0], nums[1])
            cur.append((x, y))
        elif c == "H":
            x = x + nums[0] if rel else nums[0]
            cur.append((x, y))
        elif c == "V":
            y = y + nums[0] if rel else nums[0]
            cur.append((x, y))
        elif c == "C":
            pts = [(x + nums[0], y + nums[1]), (x + nums[2], y + nums[3]), (x + nums[4], y + nums[5])] if rel \
                else [(nums[0], nums[1]), (nums[2], nums[3]), (nums[4], nums[5])]
            cur.extend(_bezier3((x, y), pts[0], pts[1], pts[2]))
            prev_c = pts[1]
            x, y = pts[2]
        elif c == "S":
            p1 = (2 * x - prev_c[0], 2 * y - prev_c[1]) if prev_c else (x, y)
            pts = [(x + nums[0], y + nums[1]), (x + nums[2], y + nums[3])] if rel \
                else [(nums[0], nums[1]), (nums[2], nums[3])]
            cur.extend(_bezier3((x, y), p1, pts[0], pts[1]))
            prev_c = pts[0]
            x, y = pts[1]
        elif c == "Q":
            pts = [(x + nums[0], y + nums[1]), (x + nums[2], y + nums[3])] if rel \
                else [(nums[0], nums[1]), (nums[2], nums[3])]
            cur.extend(_bezier2((x, y), pts[0], pts[1]))
            prev_q = pts[0]
            x, y = pts[1]
        elif c == "T":
            p1 = (2 * x - prev_q[0], 2 * y - prev_q[1]) if prev_q else (x, y)
            p2 = (x + nums[0], y + nums[1]) if rel else (nums[0], nums[1])
            cur.extend(_bezier2((x, y), p1, p2))
            prev_q = p1
            x, y = p2
        elif c == "A":
            p1 = (x + nums[5], y + nums[6]) if rel else (nums[5], nums[6])
            cur.extend(_arc((x, y), nums[0], nums[1], nums[2], int(nums[3]), int(nums[4]), p1))
            x, y = p1
        if c != "C":
            prev_c = None
        if c not in ("Q", "T"):
            prev_q = None
    if cur:
        subpaths.append(cur)
    return [sp for sp in subpaths if len(sp) >= 3]


def render_paths_mask(paths, src_size, out_size, supersample=4):
    """Even-odd fill of a set of path 'd' strings into an alpha mask."""
    from PIL import Image, ImageDraw
    s = out_size * supersample
    scale = s / float(src_size)
    acc = Image.new("L", (s, s), 0)
    for d in paths:
        for sp in path_to_subpaths(d):
            layer = Image.new("L", (s, s), 0)
            ImageDraw.Draw(layer).polygon([(px * scale, py * scale) for px, py in sp], fill=255)
            acc = Image.frombytes("L", acc.size, bytes(
                a ^ b for a, b in zip(acc.tobytes(), layer.tobytes())))
    return acc.resize((out_size, out_size), Image.LANCZOS)


def icon_paths(name):
    entry = ICONS.get(name)
    if entry is None:
        return None
    return re.findall(r'<path[^>]*\sd="([^"]+)"', entry["body"])


def render_art(asset, w, h):
    """Flat-fill a decorative SVG (no holes) into an RGBA image, cached on disk.

    The even-odd machinery above is built for 24px icons; the background art has
    146 paths over 1920px and would be far too slow through it. Decorative fields
    have no holes, so a plain polygon fill is both correct and quick."""
    from PIL import Image, ImageDraw
    src = os.path.join(ASSETS, os.path.basename(asset))
    if not os.path.exists(src):
        return None
    cache = os.path.splitext(src)[0] + ".%dx%d.cache.png" % (w, h)
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(src):
        return Image.open(cache).convert("RGBA")

    raw = open(src, encoding="utf-8").read()
    vb = re.search(r'viewBox="([^"]+)"', raw)
    vw, vh = (float(x) for x in vb.group(1).split()[2:4]) if vb else (1920.0, 454.0)
    ss = 2
    canvas = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    sx, sy = w * ss / vw, h * ss / vh
    for m in re.finditer(r"<path[^>]*>", raw):
        tag = m.group(0)
        dm = re.search(r'\sd="([^"]+)"', tag)
        if not dm:
            continue
        fm = re.search(r'fill="([^"]+)"', tag)
        fill = fm.group(1) if fm else "#E0E3F0"
        if fill.lower() in ("none", "transparent"):
            continue
        om = re.search(r'opacity="([\d.]+)"', tag)
        col = rgba(fill, int(255 * float(om.group(1)))) if om else rgba(fill)
        for sp in path_to_subpaths(dm.group(1)):
            d.polygon([(px * sx, py * sy) for px, py in sp], fill=col)
    canvas = canvas.resize((w, h), Image.LANCZOS)
    try:
        canvas.save(cache)
    except OSError:
        pass
    return canvas


# --------------------------------------------------------------------------
# the fact guard
# --------------------------------------------------------------------------

FIGURE_RE = re.compile(r"(?<![\w.])(?:\$\s?\d[\d.,]*\s?[KMBT]?\+?|\d[\d.,]*\s?%|\d[\d.,]*[KMBT]\+?|\b\d{3,}\+)")
KNOWN = {f["value"].replace(" ", "") for f in FACTS["figures"].values()}


def check_facts(spec):
    """Flag figures in the copy that facts.json does not vouch for."""
    found, text = [], []

    def walk(node):
        if isinstance(node, str):
            text.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(spec)
    for chunk in text:
        if "⟦" in chunk:
            found.append(("MARKER", chunk.strip()))
            continue
        for m in FIGURE_RE.findall(chunk):
            if m.replace(" ", "") not in KNOWN:
                found.append(("UNVOUCHED", m))
    return found


# --------------------------------------------------------------------------
# layout engine — shared by both renderers
# --------------------------------------------------------------------------

class Box:
    """A positioned, styled thing the renderers can draw without thinking."""

    def __init__(self, kind, **kw):
        self.kind = kind
        self.__dict__.update(kw)


BODIES = {}


def body(name):
    def deco(fn):
        BODIES[name] = fn
        return fn
    return deco


def compose(spec):
    """Spec -> a flat display list. This is the single source of geometry."""
    arch = spec.get("archetype")
    if arch not in BODIES and arch not in ("statement", "opening"):
        raise SystemExit(
            "Archetype %r is not in this build.\n"
            "Available: %s.\n"
            "For anything else, reuse the matching MASTER LIBRARY slide rather than\n"
            "approximating it — an approximation that looks finished is worse than a\n"
            "redirect, because nobody fixes it later."
            % (arch, ", ".join(sorted(list(BODIES) + ["statement", "opening"]))))

    C = TOKENS["canvas"]
    out = []
    ground = TOKENS["grounds"][spec.get("ground", "content")]["fill"]
    out.append(Box("ground", fill=ground))

    # ---- chrome -----------------------------------------------------------
    ch = TOKENS["chrome"]
    out.append(Box("rect", x=0, y=ch["borderTop"]["y"], w=1920, h=1, fill=ch["borderTop"]["stroke"]))
    out.append(Box("rect", x=0, y=ch["borderBottom"]["y"], w=1920, h=1, fill=ch["borderBottom"]["stroke"]))
    lg = ch["logotype"]
    out.append(Box("logotype", x=lg["x"], y=lg["y"], w=lg["width"], h=lg["height"]))
    foot = Style("chromeFooter")
    out.append(Box("text", x=1920 / 2, y=ch["confidential"]["y"], text=ch["confidential"]["text"].upper(),
                   style=foot, anchor="center"))

    rail = C["rail"]
    content_w = C["contentWidth"]

    if arch == "statement":
        L = LAYOUTS["archetypes"]["statement"]
        art = L.get("art")
        if art:
            out.append(Box("art", asset=art["asset"], x=art["x"], y=art["y"], w=art["width"], h=art["height"]))
        s1, s2 = Style("statementLight"), Style("statementEmphasis")
        lines = spec.get("title") or []
        if len(lines) != 2:
            raise SystemExit("statement needs exactly two title segments: the premise, then the claim.")
        y = L["container"]["y"]
        out.append(Box("text", x=960, y=y, text=lines[0], style=s1, anchor="center"))
        y += text_height(s1) + L["container"]["gap"]      # Figma hugs, so use the glyph box
        out.append(Box("text", x=960, y=y, text=lines[1], style=s2, anchor="center"))

        fn = spec.get("footnote")
        if fn:
            fs, fl = Style("footnote"), Style("footnoteLink")
            tw = text_width(fn["text"], fs)
            lw = text_width(fn.get("link", ""), fl) if fn.get("link") else 0
            gap = 10 if lw else 0
            x0 = 960 - (tw + gap + lw) / 2
            fy = L["footnote"]["y"]
            out.append(Box("text", x=x0, y=fy, text=fn["text"], style=fs))
            if lw:
                out.append(Box("text", x=x0 + tw + gap, y=fy, text=fn["link"], style=fl, underline=True))
        return out

    if arch == "opening":
        # Cover and section divider are one layout. A divider is a cover whose
        # first beat is the section number.
        O = LAYOUTS["header"]["opening"]
        seg = spec.get("title") or []
        if len(seg) != 2:
            raise SystemExit("opening needs exactly two title segments.")
        y = O["origin"]["y"]
        if spec.get("eyebrow"):
            st = Style("eyebrowOpening")
            out.append(Box("text", x=rail, y=y, text=spec["eyebrow"].upper(), style=st))
            y += text_height(st) + O["gap"]
        o1, o2 = Style("openingLight"), Style("openingEmphasis")
        out.append(Box("text", x=rail, y=y, text=seg[0], style=o1))
        y += text_height(o1) + O["children"][1]["layout"]["gap"]
        out.append(Box("text", x=rail, y=y, text=seg[1], style=o2))
        return out

    # ---- header (content slides) -----------------------------------------
    H = LAYOUTS["header"]["content"]
    y = H["origin"]["y"]
    if spec.get("eyebrow"):
        st = Style("eyebrow")
        out.append(Box("text", x=rail, y=y, text=spec["eyebrow"].upper(), style=st))
        y += st.line_height + H["gap"]

    seg = spec.get("title") or []
    if len(seg) != 2:
        raise SystemExit(
            "The title needs exactly two segments.\n"
            "The DFNS H1 is a two-beat formula: the purple beat sets the premise,\n"
            "the grey beat lands the claim. One flat clause is off-brand.")
    s1, s2 = Style("h1Light"), Style("h1Emphasis")
    gap = 11
    w1 = text_width(seg[0], s1)
    if w1 + gap + text_width(seg[1], s2) <= content_w:
        out.append(Box("text", x=rail, y=y, text=seg[0], style=s1))
        out.append(Box("text", x=rail + w1 + gap, y=y, text=seg[1], style=s2))
        y += s1.line_height
    else:                                    # too long for one line -> stack
        out.append(Box("text", x=rail, y=y, text=seg[0], style=s1))
        y += s1.line_height
        out.append(Box("text", x=rail, y=y, text=seg[1], style=s2))
        y += s2.line_height
    y += H["gap"]

    if spec.get("lead"):
        st = Style("lead")
        for line in wrap(spec["lead"], st, content_w):
            out.append(Box("text", x=rail, y=y, text=line, style=st))
            y += st.line_height
        y += H["gap"]

    # ---- body -------------------------------------------------------------
    body_boxes = BODIES[arch](spec, rail, content_w, y)
    out.extend(body_boxes)

    strip = spec.get("strip")
    if strip:
        out.extend(compose_strip(strip, rail))

    _guard_overflow(body_boxes, arch, spec)
    return out


def _guard_overflow(boxes, arch, spec):
    """Refuse a slide whose content runs past the chrome.

    Overflow is the one defect that still looks finished: the slide renders, the
    type is right, and a card simply bleeds through the footer rule. Nobody
    notices until it is on a screen in front of a client.
    """
    floor = TOKENS["chrome"]["borderBottom"]["y"]
    if spec.get("strip"):
        floor = LAYOUTS["strips"]["origin"]["y"] - 20
    low = 0.0
    for b in boxes:
        if b.kind in ("card", "roundrect", "rect"):
            low = max(low, b.y + b.h)
        elif b.kind == "text":
            low = max(low, b.y + b.style.line_height)
        elif b.kind == "icon":
            low = max(low, b.y + b.size)
    if low <= floor:
        return
    over = int(low - floor)
    raise SystemExit(
        "This slide overflows by %d px — the content runs past %s.\n"
        "\n"
        "The fix is editorial, not technical: one slide carries one idea, and this\n"
        "one is carrying more than fits. Cut the longest body text, drop an item,\n"
        "or split it across two slides. Do not shrink the type — the sizes are the\n"
        "brand.\n"
        "\n"
        "Archetype %r, %d item(s)."
        % (over,
           "the bottom rule" if not spec.get("strip") else "the bottom strip",
           arch,
           len(spec.get("cards") or spec.get("rows") or spec.get("steps")
               or spec.get("entries") or spec.get("columns") or spec.get("kpis") or [])))


# --------------------------------------------------------------------------
# body archetypes
#
# Each takes (spec, rail, content_w, header_bottom) and returns boxes.
# Fixed y origins come from layouts.json — they are what the deck does, and
# they keep slides aligned with each other rather than with their own header.
# --------------------------------------------------------------------------

def _capacity(arch, items, key):
    A = LAYOUTS["archetypes"][arch]
    lo, hi = A["capacity"]["min"], A["capacity"]["max"]
    if not lo <= len(items) <= hi:
        raise SystemExit("%s takes %d to %d %s; the spec has %d."
                         % (arch, lo, hi, key, len(items)))
    return A


def _chip(x, y, label, text):
    """The green PROOF pill. Tint comes from tokens, never hand-mixed."""
    cfg = TOKENS["chip"]["success"]
    pv, ph = cfg["padding"]
    ls, ts = Style(cfg["labelStyle"]), Style(cfg["textStyle"])
    lw, tw = text_width(label.upper(), ls), text_width(text, ts)
    h = max(text_height(ls), text_height(ts)) + pv * 2
    w = ph * 2 + lw + cfg["gap"] + tw
    boxes = [Box("roundrect", x=x, y=y, w=w, h=h, fill=cfg["fill"], radius=cfg["radius"])]
    ty = y + (h - text_height(ts)) / 2
    boxes.append(Box("text", x=x + ph, y=y + (h - text_height(ls)) / 2, text=label.upper(), style=ls))
    boxes.append(Box("text", x=x + ph + lw + cfg["gap"], y=ty, text=text, style=ts))
    return boxes, h


@body("cards-row")
def _cards_row(spec, rail, content_w, y):
    A = _capacity("cards-row", spec.get("cards") or [], "cards")
    cards = spec["cards"]
    it = A["item"]
    pad_v, pad_h = it["padding"]
    gap = A["container"]["gap"]
    top = y + A["container"]["offsetBelowHeader"] - TOKENS["type"]["lead"]["size"]
    n = len(cards)
    cw = (content_w - gap * (n - 1)) / n
    inner = cw - pad_h * 2
    t_st, b_st = Style("cardTitle"), Style("body")

    card_h = max(
        pad_v + (40 + 8 if c.get("icon") else 0)
        + len(wrap(c.get("title", ""), t_st, inner)) * t_st.line_height + 8
        + len(wrap(c.get("body", ""), b_st, inner)) * b_st.line_height + pad_v
        for c in cards)

    out = []
    for i, c in enumerate(cards):
        x = rail + i * (cw + gap)
        out.append(Box("card", x=x, y=top, w=cw, h=card_h, fill=it["fill"],
                       border=TOKENS["border"]["card"], radius=TOKENS["radius"]["card"],
                       shadow=TOKENS["shadow"]["card"]))
        cy = top + pad_v
        if c.get("icon"):
            out.append(Box("icon", name=c["icon"], x=x + pad_h, y=cy, size=40, color=t_st.color))
            cy += 48
        for line in wrap(c.get("title", ""), t_st, inner):
            out.append(Box("text", x=x + pad_h, y=cy, text=line, style=t_st))
            cy += t_st.line_height
        cy += 8
        for line in wrap(c.get("body", ""), b_st, inner):
            out.append(Box("text", x=x + pad_h, y=cy, text=line, style=b_st))
            cy += b_st.line_height
    return out


@body("cards-2x2")
def _cards_2x2(spec, rail, content_w, y):
    A = _capacity("cards-2x2", spec.get("cards") or [], "cards")
    cards, it = spec["cards"], A["item"]
    pad = it["padding"][0]
    col_gap = A["container"]["row"]["gap"]
    row_gap = A["container"]["gap"]
    top = A["container"]["y"]
    cw = (content_w - col_gap) / 2
    inner = cw - pad * 2
    t_st, b_st = Style("cardTitleLarge"), Style("body", size=22)

    def h_of(c):
        return (pad * 2
                + len(wrap(c.get("title", ""), t_st, inner)) * t_st.line_height
                + it["gap"]
                + len(wrap(c.get("body", ""), b_st, inner)) * b_st.line_height)

    rows = [cards[0:2], cards[2:4]]
    out, ry = [], top
    for row in rows:
        rh = max(h_of(c) for c in row)
        for j, c in enumerate(row):
            x = rail + j * (cw + col_gap)
            out.append(Box("card", x=x, y=ry, w=cw, h=rh, fill=it["fill"],
                           border=TOKENS["border"]["card"], radius=TOKENS["radius"]["card"],
                           shadow=None))
            cy = ry + pad
            for line in wrap(c.get("title", ""), t_st, inner):
                out.append(Box("text", x=x + pad, y=cy, text=line, style=t_st))
                cy += t_st.line_height
            cy += it["gap"]
            for line in wrap(c.get("body", ""), b_st, inner):
                out.append(Box("text", x=x + pad, y=cy, text=line, style=b_st))
                cy += b_st.line_height
        ry += rh + row_gap
    return out


@body("columns-ruled")
def _columns_ruled(spec, rail, content_w, y):
    A = _capacity("columns-ruled", spec.get("columns") or [], "columns")
    cols, it = spec["columns"], A["item"]
    pad_v, pad_h = it["padding"]
    gap = A["container"]["gap"]
    top = A["container"]["y"]
    n = len(cols)
    rule_w = 1
    cw = (content_w - gap * 2 * (n - 1) - rule_w * (n - 1)) / n
    inner = cw - pad_h * 2
    t_st, b_st = Style("cardTitleOpen"), Style("body")

    out, x = [], rail
    for i, c in enumerate(cols):
        cy = top + pad_v
        if c.get("icon"):
            out.append(Box("roundrect", x=x + pad_h, y=cy, w=40, h=40,
                           fill="#E0E3F0", radius=TOKENS["radius"]["iconTile"]))
            out.append(Box("icon", name=c["icon"], x=x + pad_h + 8, y=cy + 8, size=24,
                           color=t_st.color))
        tx = x + pad_h + (40 + 12 if c.get("icon") else 0)
        out.append(Box("text", x=tx, y=cy + (40 - text_height(t_st)) / 2,
                       text=c.get("title", ""), style=t_st))
        cy += 40 + it["gap"]
        for line in wrap(c.get("body", ""), b_st, inner):
            out.append(Box("text", x=x + pad_h, y=cy, text=line, style=b_st))
            cy += b_st.line_height
        x += cw
        if i < n - 1:
            out.append(Box("rect", x=x + gap, y=top, w=rule_w,
                           h=A["separator"]["height"], fill=TOKENS["border"]["ruleSoft"]["color"]))
            x += gap * 2 + rule_w
    return out


@body("kpi-row")
def _kpi_row(spec, rail, content_w, y):
    A = _capacity("kpi-row", spec.get("kpis") or [], "KPIs")
    kpis = spec["kpis"]
    f_st, l_st = Style("figure"), Style("kpiLabel")
    widths = [max(text_width(k["value"], f_st), text_width(k["label"], l_st)) for k in kpis]
    gap = min(A["container"]["gap"], (content_w - sum(widths)) / max(1, len(kpis) - 1))
    x = rail
    top = A["container"]["y"]
    out = []
    for k, w in zip(kpis, widths):
        out.append(Box("text", x=x, y=top, text=k["value"], style=f_st))
        out.append(Box("text", x=x, y=top + text_height(f_st), text=k["label"], style=l_st))
        x += w + gap
    return out


@body("numbered-rows")
def _numbered_rows(spec, rail, content_w, y):
    A = _capacity("numbered-rows", spec.get("rows") or [], "rows")
    rows, it = spec["rows"], A["item"]
    pad_v, pad_h = it["padding"]
    gap = A["container"]["gap"]
    top = A["container"]["y"]
    inner = content_w - pad_h * 2
    n_st, t_st, b_st = Style("figureSmall"), Style("cardTitle"), Style("body")

    out, ry = [], top
    for i, r in enumerate(rows, 1):
        lines = wrap(r.get("body", ""), b_st, inner)
        # The Figma "content" frame stacks head and body with no gap; only the
        # card itself gaps before the proof chip.
        h = pad_v * 2 + max(text_height(n_st), text_height(t_st)) \
            + len(lines) * b_st.line_height
        chip = r.get("proof")
        if chip:
            h += 10 + text_height(Style("chipText")) + TOKENS["chip"]["success"]["padding"][0] * 2
        out.append(Box("card", x=rail, y=ry, w=content_w, h=h, fill=it["fill"],
                       border=TOKENS["border"]["card"], radius=TOKENS["radius"]["card"],
                       shadow=TOKENS["shadow"]["card"]))
        cy = ry + pad_v
        num = "%02d" % i
        out.append(Box("text", x=rail + pad_h, y=cy, text=num, style=n_st))
        out.append(Box("text", x=rail + pad_h + text_width(num, n_st) + 10,
                       y=cy + (text_height(n_st) - text_height(t_st)) / 2,
                       text=r.get("title", ""), style=t_st))
        cy += max(text_height(n_st), text_height(t_st))
        for line in lines:
            out.append(Box("text", x=rail + pad_h, y=cy, text=line, style=b_st))
            cy += b_st.line_height
        if chip:
            boxes, ch = _chip(rail + pad_h, cy + 6, "PROOF", chip)
            out.extend(boxes)
        ry += h + gap
    return out


@body("numbered-cards")
def _numbered_cards(spec, rail, content_w, y):
    A = _capacity("numbered-cards", spec.get("steps") or [], "steps")
    steps, it = spec["steps"], A["item"]
    pad_v, pad_h = it["padding"]
    gap = A["container"]["gap"]
    top, height = A["container"]["y"], A["container"]["height"]
    ramp = A["tintRamp"]
    n = len(steps)
    widths = A["taper"]["widths"][:n]
    scale = (content_w - gap * (n - 1)) / sum(widths)
    widths = [w * scale for w in widths]
    tints = ramp[:n] if n == len(ramp) else [ramp[round(i * (len(ramp) - 1) / max(1, n - 1))]
                                             for i in range(n)]
    out, x = [], rail
    for i, (s, w, tint) in enumerate(zip(steps, widths, tints), 1):
        dark_num = i >= it["children"][0]["darkFrom"]
        dark_txt = i >= it["children"][1]["darkFrom"]
        n_st = Style("figureSmall", color=it["children"][0]["colorOnDark"] if dark_num else None)
        t_st = Style("cardTitle", color=it["children"][1]["colorOnDark"] if dark_txt
                     else it["children"][1]["color"])
        b_st = Style("bodySmall", color=it["children"][2]["colorOnDark"] if dark_txt
                     else it["children"][2]["color"])
        out.append(Box("card", x=x, y=top, w=w, h=height, fill=tint, border=None,
                       radius=TOKENS["radius"]["card"], shadow=None))
        cy = top + pad_v
        out.append(Box("text", x=x + pad_h, y=cy, text="%02d" % i, style=n_st))
        cy += text_height(n_st) + it["gap"]
        out.append(Box("text", x=x + pad_h, y=cy, text=s.get("title", ""), style=t_st))
        cy += text_height(t_st) + it["gap"]
        for line in wrap(s.get("body", ""), b_st, w - pad_h * 2):
            out.append(Box("text", x=x + pad_h, y=cy, text=line, style=b_st))
            cy += b_st.line_height
        x += w + gap
    return out


@body("text-table")
def _text_table(spec, rail, content_w, y):
    A = _capacity("text-table", spec.get("rows") or [], "rows")
    rows = spec["rows"]
    headers = spec.get("headers") or []
    R = A["row"]
    gap = R["gap"]
    widths = [c["width"] for c in R["columns"]]
    scale = (content_w - gap * (len(widths) - 1)) / sum(widths)
    widths = [w * scale for w in widths]
    top = A["container"]["y"]
    out = []

    if headers:
        hx = rail + widths[0] + gap + widths[1] + gap
        for j, h in enumerate(headers[:3]):
            st = Style("columnHeaderAccent" if j == 2 else "columnHeader")
            out.append(Box("text", x=hx, y=top, text=h.upper(), style=st))
            hx += widths[2 + j] + gap
        top += text_height(Style("columnHeader")) + A["headerRow"]["padding"][2]

    n_st, t_st = Style("figureSmall", color="#2D1866"), Style("rowTitle")
    cell = [Style("body"), Style("body"), Style("body", size=22, color="#442599")]
    ry = top
    for i, r in enumerate(rows, 1):
        cells = r.get("cells") or []
        blocks = [wrap(cells[j] if j < len(cells) else "", cell[j], widths[2 + j])
                  for j in range(3)]
        title_lines = wrap(r.get("title", ""), t_st, widths[1])
        h = max(max(len(b) * cell[j].line_height for j, b in enumerate(blocks)),
                len(title_lines) * t_st.line_height,
                text_height(n_st)) + R["padding"][0] * 2
        out.append(Box("rect", x=rail, y=ry, w=content_w, h=1,
                       fill=TOKENS["border"]["card"]["color"]))
        cy = ry + R["padding"][0]
        out.append(Box("text", x=rail, y=cy, text="%02d" % i, style=n_st))
        tx = rail + widths[0] + gap
        ty = cy
        for line in title_lines:
            out.append(Box("text", x=tx, y=ty, text=line, style=t_st))
            ty += t_st.line_height
        cx = tx + widths[1] + gap
        for j, blk in enumerate(blocks):
            by = cy
            for line in blk:
                out.append(Box("text", x=cx, y=by, text=line, style=cell[j]))
                by += cell[j].line_height
            cx += widths[2 + j] + gap
        ry += h
    return out


@body("icon-list")
def _icon_list(spec, rail, content_w, y):
    A = _capacity("icon-list", spec.get("entries") or [], "entries")
    entries, it = spec["entries"], A["item"]
    width = A["container"]["width"]
    gap = A["container"]["gap"]
    top = A["container"]["y"]
    tile = it["children"][0]
    tx = rail + tile["size"] + it["gap"]
    inner = width - (tile["size"] + it["gap"])
    t_st, b_st = Style("entryTitle"), Style("body")
    out, ry = [], top
    for i, e in enumerate(entries):
        lines = wrap(e.get("body", ""), b_st, inner)
        block_h = text_height(t_st) + it["children"][1]["gap"] + len(lines) * b_st.line_height
        h = max(block_h, tile["size"])
        if e.get("icon"):
            out.append(Box("roundrect", x=rail, y=ry + (h - tile["size"]) / 2,
                           w=tile["size"], h=tile["size"], fill=tile["fill"],
                           radius=TOKENS["radius"]["tile"]))
            out.append(Box("icon", name=e["icon"], x=rail + tile["padding"],
                           y=ry + (h - tile["size"]) / 2 + tile["padding"],
                           size=tile["icon"], color=tile["iconColor"]))
        cy = ry + (h - block_h) / 2
        out.append(Box("text", x=tx, y=cy, text=e.get("title", ""), style=t_st))
        cy += text_height(t_st) + it["children"][1]["gap"]
        for line in lines:
            out.append(Box("text", x=tx, y=cy, text=line, style=b_st))
            cy += b_st.line_height
        ry += h + gap
        if i < len(entries) - 1:
            out.append(Box("rect", x=rail, y=ry, w=width, h=1, fill=A["separator"]["fill"]))
            ry += gap
    return out


@body("contrast-list")
def _contrast_list(spec, rail, content_w, y):
    A = _capacity("contrast-list", spec.get("rows") or [], "rows")
    rows, C = spec["rows"], A["container"]
    R = A["row"]
    old_st = Style("body", size=R["children"][0]["size"], weight=400,
                   color=R["children"][0]["color"])
    arr_st = Style("body", size=R["children"][1]["size"], color=R["children"][1]["color"])
    new_st = Style("body", size=R["children"][2]["size"], weight=300,
                   color=R["children"][2]["color"])
    row_h = max(text_height(old_st), text_height(new_st))
    panel_h = C["padding"][0] * 2 + len(rows) * row_h + (len(rows) - 1) * C["gap"]
    out = [Box("roundrect", x=C["x"], y=C["y"], w=C["width"], h=panel_h,
               fill=C["fill"], radius=TOKENS["radius"]["tile"])]
    old_w = R["children"][0]["width"]
    ox = C["x"] + C["padding"][1]
    ry = C["y"] + C["padding"][0]
    for r in rows:
        out.append(Box("text", x=ox + old_w, y=ry, text=r.get("old", ""), style=old_st,
                       anchor="right", strike=True))
        ax = ox + old_w + R["gap"]
        out.append(Box("text", x=ax, y=ry, text="→", style=arr_st))
        out.append(Box("text", x=ax + text_width("→", arr_st) + R["gap"], y=ry,
                       text=r.get("new", ""), style=new_st))
        ry += row_h + C["gap"]
    return out


def compose_strip(strip, rail):
    S = LAYOUTS["strips"]
    y = S["origin"]["y"]
    variant = strip.get("variant", "quote")
    if variant not in ("quote", "proof-logos"):
        raise SystemExit("strip variant %r is not in this build (quote, proof-logos)." % variant)
    out, x = [], rail
    rule_col = "#AEB1C9" if variant == "quote" else "#442599"
    label_style = Style("stripAuthor") if variant == "quote" else Style("stripLabel")
    name = (strip.get("author") or strip.get("label", "")).upper()
    role = (strip.get("role") or "").upper()
    out.append(Box("rect", x=x, y=y, w=1, h=54, fill=rule_col))
    x += 25
    if role:                                   # name over role, as the deck sets it
        lh = label_style.line_height
        top = y + 27 - lh
        out.append(Box("text", x=x, y=top, text=name, style=label_style))
        out.append(Box("text", x=x, y=top + lh, text=role, style=label_style))
        label_w = max(text_width(name, label_style), text_width(role, label_style))
    else:
        out.append(Box("text", x=x, y=y + 17, text=name, style=label_style))
        label_w = text_width(name, label_style)
    x += label_w + 25

    box_fill = "#F4F4F8" if variant == "quote" else "rgba(230,222,255,0.30)"
    txt_style = Style("stripText", color=None if variant == "quote" else "#363A5B")
    text = strip.get("text", "")
    tw = text_width(text, txt_style)
    out.append(Box("rect", x=x, y=y, w=25 + tw + 20 + 1, h=54, fill=box_fill))
    out.append(Box("rect", x=x, y=y, w=1, h=54, fill=rule_col))
    out.append(Box("text", x=x + 21, y=y + 18, text=text, style=txt_style))
    return out


# --------------------------------------------------------------------------
# SVG renderer
# --------------------------------------------------------------------------

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def to_svg(display_list):
    W, H = TOKENS["canvas"]["width"], TOKENS["canvas"]["height"]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H)]
    parts.append("<defs><style>"
                 "text{dominant-baseline:hanging}"
                 "</style></defs>")
    for b in display_list:
        if b.kind == "ground":
            parts.append('<rect width="%d" height="%d" fill="%s"/>' % (W, H, b.fill))
        elif b.kind == "rect":
            parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>'
                         % (b.x, b.y, b.w, b.h, css(b.fill)))
        elif b.kind in ("card", "roundrect"):
            attrs = ('x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%d" fill="%s"'
                     % (b.x, b.y, b.w, b.h, b.radius, css(b.fill)))
            bd = getattr(b, "border", None)
            if bd:
                attrs += ' stroke="%s" stroke-width="%d"' % (bd["color"], bd["width"])
            parts.append("<rect %s/>" % attrs)
        elif b.kind == "text":
            st = b.style
            anchor = {"center": "middle", "left": "start", "right": "end"}.get(
                getattr(b, "anchor", "left"), "start")
            attrs = ('x="%.1f" y="%.1f" font-family="%s, sans-serif" font-size="%.1f" '
                     'font-weight="%d" fill="%s" text-anchor="%s"'
                     % (b.x, b.y, st.family, st.size, st.weight, st.color, anchor))
            if st.tracking:
                attrs += ' letter-spacing="%.3f"' % st.tracking
            deco = []
            if getattr(b, "underline", False) or st.decoration == "underline":
                deco.append("underline")
            if getattr(b, "strike", False):
                deco.append("line-through")
            if deco:
                attrs += ' text-decoration="%s"' % " ".join(deco)
            parts.append("<text %s>%s</text>" % (attrs, esc(b.text)))
        elif b.kind == "icon":
            paths = icon_paths(b.name)
            if paths:
                sc = b.size / 24.0
                parts.append('<g transform="translate(%.1f %.1f) scale(%.4f)" fill="%s">'
                             % (b.x, b.y, sc, b.color))
                for d in paths:
                    parts.append('<path d="%s" fill-rule="evenodd"/>' % d)
                parts.append("</g>")
        elif b.kind == "logotype":
            parts.append(embed_logotype_svg(b))
        elif b.kind == "art":
            parts.append(embed_art_svg(b))
    parts.append("</svg>")
    return "\n".join(parts)


def _read_asset(name):
    path = os.path.join(ASSETS, os.path.basename(name))
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def embed_logotype_svg(b):
    raw = _read_asset("logotype-light-full.svg")
    if raw is None:
        return ""
    vb = re.search(r'viewBox="([^"]+)"', raw)
    inner = raw.split(">", 1)[-1]
    inner = re.sub(r"</?svg[^>]*>", "", inner)
    inner = re.sub(r"<\?xml[^>]*\?>", "", inner)
    inner = re.sub(r"<!--.*?-->", "", inner, flags=re.S)
    inner = re.sub(r"\.st(\d+)", r".dfnslogo-st\1", inner)      # scope the classes
    inner = re.sub(r'class="st(\d+)"', r'class="dfnslogo-st\1"', inner)
    return ('<svg x="%.1f" y="%.1f" width="%.1f" height="%.1f" viewBox="%s" overflow="visible">%s</svg>'
            % (b.x, b.y, b.w, b.h, vb.group(1) if vb else "0 0 3497.9 900", inner))


def embed_art_svg(b):
    raw = _read_asset(b.asset)
    if raw is None:
        return ""
    vb = re.search(r'viewBox="([^"]+)"', raw)
    inner = re.sub(r"</?svg[^>]*>", "", raw)
    inner = re.sub(r"<\?xml[^>]*\?>", "", inner)
    return ('<svg x="%.1f" y="%.1f" width="%.1f" height="%.1f" viewBox="%s">%s</svg>'
            % (b.x, b.y, b.w, b.h, vb.group(1) if vb else "0 0 1920 454", inner))


# --------------------------------------------------------------------------
# Pillow renderer
# --------------------------------------------------------------------------

def to_image(display_list, scale=1):
    from PIL import Image, ImageDraw, ImageFilter

    W = TOKENS["canvas"]["width"] * scale
    H = TOKENS["canvas"]["height"] * scale
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    def S(v):
        return v * scale

    def draw_tracked(d, xy, text, style, anchor="left"):
        font = pil_font(Style(style.name, size=style.size * scale, color=style.color))
        x, y = xy
        col = rgba(style.color)
        tr = style.tracking * scale
        total = font.getlength(text) + tr * len(text)
        if anchor == "center":
            x -= total / 2
        elif anchor == "right":
            x -= total
        if not tr:
            d.text((x, y), text, font=font, fill=col, anchor="la")
            return x, total
        for chn in text:
            d.text((x, y), chn, font=font, fill=col, anchor="la")
            x += font.getlength(chn) + tr
        return x - total, total

    for b in display_list:
        if b.kind == "ground":
            draw.rectangle([0, 0, W, H], fill=rgba(b.fill))
        elif b.kind == "rect":
            draw.rectangle([S(b.x), S(b.y), S(b.x + b.w), S(b.y + b.h)], fill=rgba(b.fill))
        elif b.kind in ("card", "roundrect"):
            box = [S(b.x), S(b.y), S(b.x + b.w), S(b.y + b.h)]
            if getattr(b, "shadow", None):
                sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(sh).rounded_rectangle(
                    [box[0], box[1] + S(1), box[2], box[3] + S(1)],
                    radius=S(b.radius), fill=(0, 0, 0, 26))
                sh = sh.filter(ImageFilter.GaussianBlur(S(2)))
                img.paste(Image.alpha_composite(img.convert("RGBA"), sh).convert("RGB"), (0, 0))
                draw = ImageDraw.Draw(img, "RGBA")
            bd = getattr(b, "border", None)
            draw.rounded_rectangle(
                box, radius=S(b.radius), fill=rgba(b.fill),
                outline=rgba(bd["color"]) if bd else None,
                width=max(1, int(S(bd["width"]))) if bd else 0)
        elif b.kind == "text":
            x0, tw = draw_tracked(draw, (S(b.x), S(b.y)), b.text, b.style,
                                  getattr(b, "anchor", "left"))
            st = b.style
            if getattr(b, "underline", False):
                yy = S(b.y) + st.size * scale * 1.15
                draw.rectangle([x0, yy, x0 + tw, yy + max(1, scale)], fill=rgba(st.color))
            if getattr(b, "strike", False):
                yy = S(b.y) + st.size * scale * 0.68
                draw.rectangle([x0, yy, x0 + tw, yy + max(1, scale)], fill=rgba(st.color))
        elif b.kind == "icon":
            paths = icon_paths(b.name)
            if paths:
                size = int(S(b.size))
                mask = render_paths_mask(paths, 24, size)
                layer = Image.new("RGBA", (size, size), rgba(b.color))
                img.paste(layer, (int(S(b.x)), int(S(b.y))), mask)
        elif b.kind == "logotype":
            raw = _read_asset("logotype-light-full.svg")
            if raw:
                ds = re.findall(r'\sd="([^"]+)"', raw)
                vb = re.search(r'viewBox="([^"]+)"', raw)
                src = float(vb.group(1).split()[2]) if vb else 3497.9
                size = int(S(b.w))
                mask = render_paths_mask(ds, src, size)
                h = int(S(b.h))
                mask = mask.crop((0, 0, size, size)).resize((size, size), Image.LANCZOS)
                layer = Image.new("RGBA", (size, size), rgba("#363A5B"))
                img.paste(layer, (int(S(b.x)), int(S(b.y))), mask)
        elif b.kind == "art":
            art = render_art(b.asset, int(S(b.w)), int(S(b.h)))
            if art is not None:
                img.paste(art, (int(S(b.x)), int(S(b.y))), art)
                draw = ImageDraw.Draw(img, "RGBA")
    return img


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def read_spec(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def report_facts(spec, strict=False):
    issues = check_facts(spec)
    for kind, val in issues:
        if kind == "MARKER":
            print("  ⟦FACT NEEDED⟧ left in the copy: %s" % val[:90], file=sys.stderr)
        else:
            print("  UNVOUCHED FIGURE %r — not in facts.json. Correct the copy, or add the\n"
                  "    fact with an owner and a date. Do not guess." % val, file=sys.stderr)
    if issues and strict:
        raise SystemExit("Refusing to render: the copy states figures this pack cannot vouch for.")
    return issues


# --------------------------------------------------------------------------
# audit — the deterministic half of check mode
#
# Only what a regex can settle honestly. Judgment calls (a flat one-clause
# title, fear framing, a claim that needs evidence) belong to the model and are
# listed in CHECK.md. A linter that guesses at intent produces false positives,
# and a checker nobody trusts is worse than no checker.
# --------------------------------------------------------------------------

# Contexts where "dfns" lowercase is a name, not a casing error. The Voice Drift
# Report found eleven such occurrences flagged as faults; every one was correct.
IDENTIFIER_CONTEXT = re.compile(
    r"(?:https?://|www\.)\S*dfns\S*"
    r"|\S*\.dfns\.\S+|\bdfns\.(?:io|co|com)\S*"
    r"|@dfns/\S+|\bDfns[A-Z]\w*|\bX-Dfns-[\w-]+|\bdfns-[\w-]+|`[^`]*dfns[^`]*`",
    re.I)

QUOTE_SPAN = re.compile(r"[“\"']{1}[^“”\"']{20,}[”\"']{1}")

AUDIT_RULES = [
    ("terminology", r"\bon-chain\b|\bon chain\b", "Write it 'onchain', one word."),
    ("terminology", r"\brules engine\b", "It is the Policy Engine, a proper noun."),
    ("terminology", r"\bapproval workflow\b", "It is the Governance Engine, a proper noun."),
    ("terminology", r"\bkey custody\b", "Use 'key management' outside custody-specific context."),
    ("terminology", r"\bsafe\b(?=\s+(?:for|to|that|which)\b)", "A wallet is not a 'safe'."),
    ("padding", r"\brobust\b|\bpowerful\b|\bseamless(?:ly)?\b|\beasily\b|\bsuper simple\b",
     "Cut it — the sentence gets stronger."),
    ("buzzword", r"\brevolutionary\b|\bgame[- ]changing\b|\bnext[- ]gen(?:eration)?\b|\bcutting[- ]edge\b",
     "Banned outright."),
    ("hedging", r"\bwe believe\b|\bwe think\b", "State what we do and what is on record."),
    ("punctuation", r"!", "No exclamation marks."),
    ("emoji", r"[\U0001F300-\U0001FAFF☀-➿]", "No emoji in formal communication."),
    ("superlative", r"#1\b|\bbest[- ]in[- ]class\b|\bmost secure\b|\bhighest[- ]rated\b|\bthe leading\b",
     "A superlative needs its source named in the same breath, or it goes."),
]


def audit_text(text):
    findings = []
    for ln, line in enumerate(text.splitlines(), 1):
        quoted = [m.span() for m in QUOTE_SPAN.finditer(line)]
        idents = [m.span() for m in IDENTIFIER_CONTEXT.finditer(line)]

        def inside(span, ranges):
            return any(a <= span[0] and span[1] <= b for a, b in ranges)

        for kind, pattern, advice in AUDIT_RULES:
            for m in re.finditer(pattern, line, re.I):
                if inside(m.span(), quoted):
                    findings.append(("quoted", ln, m.group(0),
                                     "Inside a third-party quote — never rewritten. Context, not a fault."))
                else:
                    findings.append((kind, ln, m.group(0), advice))

        for m in re.finditer(r"\bdfns\b", line):
            if m.group(0) == "DFNS":
                continue
            if inside(m.span(), idents) or inside(m.span(), quoted):
                continue
            findings.append(("casing", ln, m.group(0), "DFNS is written in caps in prose."))

        for m in FIGURE_RE.finditer(line):
            if m.group(0).replace(" ", "") in KNOWN:
                continue
            if inside(m.span(), quoted):
                findings.append(("quoted", ln, m.group(0),
                                 "A figure inside a quote. Verify it, but do not rewrite the quote."))
            else:
                findings.append(("figure", ln, m.group(0),
                                 "Not in facts.json. Correct it, or have the fact added with an owner."))
    return findings


SEVERITY = ["figure", "casing", "superlative", "terminology", "buzzword",
            "hedging", "padding", "punctuation", "emoji", "quoted"]


def cmd_audit(path):
    text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    findings = audit_text(text)
    if not findings:
        print("No lexical faults. The judgment checks in CHECK.md still apply —\n"
              "a flat one-clause title and an unevidenced claim both pass a regex.")
        return 0
    by_kind = {}
    for kind, ln, frag, advice in findings:
        by_kind.setdefault(kind, []).append((ln, frag, advice))
    for kind in SEVERITY:
        rows = by_kind.get(kind)
        if not rows:
            continue
        print("\n%s — %d" % (kind.upper(), len(rows)))
        for ln, frag, advice in rows:
            print("  line %-4d %-28s %s" % (ln, repr(frag)[:28], advice))
    real = sum(len(v) for k, v in by_kind.items() if k != "quoted")
    print("\n%d fault(s), %d in quoted material (not faults)."
          % (real, len(by_kind.get("quoted", []))))
    print("Now apply CHECK.md — the parts no regex can settle.")
    return 1 if real else 0


FINGERPRINTS = os.path.join(HERE, "examples", "fingerprints.json")
FP_TOLERANCE = 3          # luminance levels; JPEG encoders differ by 1–2


def fingerprint(img):
    """A 16x9 luminance grid — stable across JPEG encoders, loud when a font
    substitutes or a glyph fails to draw."""
    from PIL import Image
    small = img.convert("RGB").resize((16, 9), Image.LANCZOS)
    return [sum(p) // 3 for p in small.getdata()]


def cmd_verify(update=False):
    """Regression net: re-render every example and compare to the golden grid.

    A real defect — a substituted font, a dropped icon, a shifted column —
    moves a cell by tens of levels. Encoder noise moves it by one or two.
    """
    specs = sorted(f for f in os.listdir(os.path.join(HERE, "examples"))
                   if f.endswith(".json") and f != "fingerprints.json")
    golden = {}
    if os.path.exists(FINGERPRINTS) and not update:
        with open(FINGERPRINTS, encoding="utf-8") as fh:
            golden = json.load(fh).get("slides", {})

    failures, results = 0, {}
    for name in specs:
        spec = read_spec(os.path.join(HERE, "examples", name))
        fp = fingerprint(to_image(compose(spec)))
        results[name] = fp
        if update:
            print("  recorded %s" % name)
            continue
        want = golden.get(name)
        if want is None:
            print("  NEW      %s — no golden fingerprint; run with --update to record it" % name)
            continue
        diffs = [abs(a - b) for a, b in zip(fp, want)]
        worst = max(diffs) if diffs else 0
        if len(fp) != len(want) or worst > FP_TOLERANCE:
            failures += 1
            bad = [(i, d) for i, d in enumerate(diffs) if d > FP_TOLERANCE]
            print("  FAIL     %s — max delta %d over %d cell(s)" % (name, worst, len(bad)))
            for i, d in sorted(bad, key=lambda t: -t[1])[:5]:
                print("             row %d col %d  off by %d" % (i // 16, i % 16, d))
        else:
            print("  ok       %s — max delta %d" % (name, worst))

    if update:
        with open(FINGERPRINTS, "w", encoding="utf-8") as fh:
            json.dump({"_meta": {"tolerance": FP_TOLERANCE,
                                 "grid": "16x9 luminance",
                                 "note": "Regenerate deliberately. A change here is a change to "
                                         "what the slides look like."},
                       "slides": results}, fh, indent=1)
        print("wrote %s" % FINGERPRINTS)
        return 0
    if failures:
        print("\n%d slide(s) drifted. Either the change was intended — then rerun with "
              "--update — or something broke." % failures)
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(description="Build DFNS slides from a JSON spec.")
    ap.add_argument("command", choices=["build", "render", "make", "check", "verify", "audit"])
    ap.add_argument("spec", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--scale", type=int, default=1, help="raster scale (1 = 1920x1080)")
    ap.add_argument("--strict", action="store_true", help="refuse to render on an unvouched figure")
    ap.add_argument("--update", action="store_true", help="verify: rewrite the golden fingerprints")
    args = ap.parse_args()

    if args.command == "verify":
        raise SystemExit(cmd_verify(update=args.update))
    if not args.spec:
        ap.error("a spec file is required for %s" % args.command)
    if args.command == "audit":
        raise SystemExit(cmd_audit(args.spec))

    spec = read_spec(args.spec)
    stem = os.path.splitext(args.spec)[0]

    if args.command == "check":
        issues = report_facts(spec)
        print("fact guard: %d issue(s)" % len(issues))
        return

    report_facts(spec, strict=args.strict)
    dl = compose(spec)

    if args.command in ("build", "make"):
        out = args.out if (args.out and args.command == "build") else stem + ".svg"
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(to_svg(dl))
        print("wrote %s" % out)

    if args.command in ("render", "make"):
        out = args.out if (args.out and args.command == "render") else stem + ".jpg"
        img = to_image(dl, scale=args.scale)
        if out.lower().endswith((".jpg", ".jpeg")):
            img.save(out, quality=94, subsampling=0)
        else:
            img.save(out)
        print("wrote %s (%dx%d)" % (out, img.width, img.height))


if __name__ == "__main__":
    main()
