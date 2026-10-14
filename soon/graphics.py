"""Casa de Soon graphics: Soon draws the casino games as pictures (Pillow) instead of text.
Each game gets an animated GIF while it plays (reels spinning, wheel turning, coin flipping, card scratching)
and a still PNG of the result that replaces it. Art = free Twemoji images in art/emoji (swap in custom PNGs with
the same file names later) + the Poppins font. If anything here fails, the games fall back to their old text look.

The look (Shannon: "modern, not a 1995 computer game"): neon glow edges, glossy gradients, soft shadows.
Everything is drawn at 2x size and shrunk at the end (K), which is what makes the edges smooth.
Static parts of each picture (background, cabinet, title) are drawn once and reused, so animations stay fast.

Every public function returns PNG/GIF bytes; call them with `await render(fn, ...)` so drawing never blocks Soon."""
import asyncio
import io
import math
import os
import random
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ART = os.path.join(os.path.dirname(__file__), "art")
K = 2                                                     # draw at 2x, shrink at the end = smooth edges

NIGHT, PLUM, VIOLET = (14, 5, 28), (66, 20, 100), (130, 70, 230)
PINK, GOLD, CREAM, INK = (255, 69, 163), (255, 200, 60), (255, 247, 236), (26, 10, 38)
GOLD_LIGHT, GOLD_DARK = (255, 238, 160), (200, 128, 20)
TEAL, TEAL_LIGHT = (0, 210, 200), (140, 255, 240)        # Shannon: "and teal!"
GREEN, RED, BLACK = (20, 140, 80), (214, 36, 56), (28, 26, 34)
# banner styles: (top color, bottom color)
STYLES = {"win": ((0, 214, 170), (0, 128, 100)), "jackpot": ((255, 80, 170), (255, 160, 40)),
          "push": ((90, 140, 255), (50, 70, 190)), "lose": ((112, 72, 150), (64, 34, 96)),
          "burrito": ((236, 140, 60), (160, 70, 30))}
KIND = {(40, 150, 80): "win", (70, 90, 160): "push", (110, 80, 120): "lose", (200, 40, 140): "jackpot",
        (150, 70, 30): "burrito", (90, 60, 110): "lose"}

CODES = {"🌮": "1f32e", "🥑": "1f951", "🐷": "1f437", "🚀": "1f680", "🍹": "1f379", "🦑": "1f991", "🌯": "1f32f",
         "🌀": "1f300", "🎰": "1f3b0", "🪙": "1fa99", "💸": "1f4b8", "🎡": "1f3a1", "💅": "1f485", "🎟️": "1f39f",
         "🟫": "1f7eb", "🗑️": "1f5d1", "🚨": "1f6a8", "🏆": "1f3c6", "🃏": "1f0cf", "✨": "2728", "🌟": "1f31f",
         "🔥": "1f525", "💀": "1f480", "🎲": "1f3b2", "💥": "1f4a5"}
FONTS = {"black": "Poppins-Black.ttf", "xbold": "Poppins-ExtraBold.ttf", "semi": "Poppins-SemiBold.ttf",
         "sym": "DejaVuSans-Bold.ttf", "symr": "DejaVuSans.ttf"}


async def render(fn, *args, **kwargs) -> bytes:
    return await asyncio.to_thread(fn, *args, **kwargs)


# ---------- basics ----------

def s(v: float) -> int:
    return int(round(v * K))


def sb(box) -> list[int]:
    return [s(v) for v in box]


@lru_cache(maxsize=256)
def font(px: int, weight: str = "xbold") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(ART, "fonts", FONTS[weight]), px)


@lru_cache(maxsize=128)
def emoji(sym: str, px: int) -> Image.Image:
    img = Image.open(os.path.join(ART, "emoji", CODES[sym] + ".png")).convert("RGBA")
    return img.resize((px, px), Image.LANCZOS)


def shrink(img: Image.Image) -> Image.Image:
    return img.convert("RGB").resize((img.width // K, img.height // K), Image.LANCZOS)


def png(img: Image.Image) -> bytes:
    out = io.BytesIO()
    shrink(img).save(out, "PNG", optimize=True)
    return out.getvalue()


def gif(frames: list[Image.Image], durations: list[int]) -> bytes:
    out = io.BytesIO()
    small = [shrink(f) for f in frames]
    picks = [small[0], small[len(small) // 2], small[-1]]  # one shared color set from 3 frames (fast, no flicker)
    strip = Image.new("RGB", (picks[0].width, picks[0].height * 3))
    for i, f in enumerate(picks):
        strip.paste(f, (0, i * f.height))
    palette = strip.quantize(colors=224, method=Image.Quantize.MEDIANCUT)
    pal = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in small]
    pal[0].save(out, "GIF", save_all=True, append_images=pal[1:], duration=durations, loop=0, disposal=2, optimize=False)
    return out.getvalue()


def mix(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vgrad(w: int, h: int, top, bot) -> Image.Image:
    g = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), bot), Image.new("RGB", (w, h), top), g)


def rgrad(w: int, h: int, inner, outer) -> Image.Image:
    g = Image.radial_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), outer), Image.new("RGB", (w, h), inner), g)


def rmask(w: int, h: int, r: int) -> Image.Image:
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return m


def tint(img: Image.Image, box, color, alpha: int, r: int = 0):
    """See-through color over a box (pixel coords)."""
    x0, y0, x1, y1 = box
    m = rmask(x1 - x0, y1 - y0, r) if r else Image.new("L", (x1 - x0, y1 - y0), 255)
    img.paste(color, (x0, y0, x1, y1), m.point(lambda v: v * alpha // 255))


def shadow(img: Image.Image, box, r: float, off: float = 8, blur: float = 12, alpha: int = 150):
    """Soft drop shadow under a rounded box (logical coords)."""
    x0, y0, x1, y1 = sb(box)
    pad = s(blur * 2)
    m = Image.new("L", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), 0)
    ImageDraw.Draw(m).rounded_rectangle([pad, pad, pad + x1 - x0, pad + y1 - y0], radius=s(r), fill=alpha)
    img.paste((0, 0, 0), (x0 - pad, y0 - pad + s(off)), m.filter(ImageFilter.GaussianBlur(s(blur))))


def glow_edge(img: Image.Image, box, r: float, color, width: float = 3, blur: float = 9, inner: bool = True):
    """Neon tube: a blurred halo, the colored line, and a bright core."""
    x0, y0, x1, y1 = sb(box)
    pad = s(blur * 2.5)
    m = Image.new("L", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), 0)
    ImageDraw.Draw(m).rounded_rectangle([pad, pad, pad + x1 - x0, pad + y1 - y0], radius=s(r), outline=255,
                                        width=s(width * 2.2))
    halo = m.filter(ImageFilter.GaussianBlur(s(blur))).point(lambda v: min(255, int(v * 1.6)))
    img.paste(color, (x0 - pad, y0 - pad), halo)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y0, x1, y1], radius=s(r), outline=color, width=s(width))
    if inner:
        c = s(width) // 2
        d.rounded_rectangle([x0 + c - 1, y0 + c - 1, x1 - c + 1, y1 - c + 1], radius=s(r) - c,
                            outline=mix(color, (255, 255, 255), 0.6), width=max(1, s(width) // 3))


def gloss(img: Image.Image, box, r: float, strength: int = 70, depth: float = 0.48):
    """Glassy highlight on the top part of a rounded box (logical coords)."""
    x0, y0, x1, y1 = sb(box)
    w, h = x1 - x0, y1 - y0
    g = Image.linear_gradient("L").resize((w, max(1, int(h * depth)))).point(lambda v: (255 - v) * strength // 255)
    full = Image.new("L", (w, h), 0)
    full.paste(g, (0, 0))
    m = rmask(w, h, s(r))
    img.paste((255, 255, 255), (x0, y0), ImageChops.multiply(full, m))


def panel(img: Image.Image, box, r: float, top, bot, edge=None, edge_w: float = 3, shine: int = 0, drop: bool = True):
    if drop:
        shadow(img, box, r)
    x0, y0, x1, y1 = sb(box)
    img.paste(vgrad(x1 - x0, y1 - y0, top, bot), (x0, y0), rmask(x1 - x0, y1 - y0, s(r)))
    if shine:
        gloss(img, box, r, shine)
    if edge:
        glow_edge(img, box, r, edge, edge_w)


def text(img: Image.Image, xy, txt: str, size: float, fill=CREAM, weight: str = "xbold", glow=None,
         drop: bool = True, grad=None, maxw: float | None = None, align: str = "c", track: float = 0):
    """Text centered on xy (logical). grad=(top, bottom) for a metallic fill; glow = color of a neon halo."""
    px = s(size)
    if maxw:
        while px > s(10) and font(px, weight).getlength(txt) + track * K * len(txt) > s(maxw):
            px -= 2
    f = font(px, weight)
    l, t, r, b = f.getbbox(txt)
    w = int(r - l + track * K * max(0, len(txt) - 1))
    h = b - t
    pad = s(14)
    m = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    md = ImageDraw.Draw(m)
    if track:
        x = pad - l
        for ch in txt:
            md.text((x, pad - t), ch, font=f, fill=255)
            x += f.getlength(ch) + track * K
    else:
        md.text((pad - l, pad - t), txt, font=f, fill=255)
    ox = s(xy[0]) - (w // 2 if align == "c" else 0) - pad
    oy = s(xy[1]) - h // 2 - pad
    if glow:
        halo = m.filter(ImageFilter.GaussianBlur(s(7))).point(lambda v: min(255, int(v * 1.8)))
        img.paste(glow, (ox, oy), halo)
    if drop:
        img.paste((0, 0, 0), (ox, oy + s(2.5)), m.filter(ImageFilter.GaussianBlur(s(2))).point(lambda v: v * 3 // 4))
    if grad:
        img.paste(vgrad(m.width, m.height, grad[0], grad[1]), (ox, oy), m)
    else:
        img.paste(fill, (ox, oy), m)


def put(img: Image.Image, sym: str, cx: float, cy: float, size: float, drop: bool = True):
    e = emoji(sym, s(size))
    x, y = s(cx) - e.width // 2, s(cy) - e.height // 2
    if drop:
        a = e.getchannel("A").filter(ImageFilter.GaussianBlur(s(3))).point(lambda v: v // 2)
        img.paste((0, 0, 0), (x, y + s(4)), a)
    img.paste(e, (x, y), e)


def pill(img: Image.Image, cx: float, cy: float, txt: str, color, size: float = 15, fill=(30, 10, 50)):
    """Small rounded label: dark glass with a colored neon edge."""
    w = font(s(size), "semi").getlength(txt) / K + 34
    box = (cx - w / 2, cy - size * 0.95, cx + w / 2, cy + size * 0.95)
    panel(img, box, size, mix(fill, (255, 255, 255), 0.06), fill, edge=color, edge_w=1.6, drop=False)
    text(img, (cx, cy + 1), txt, size, color, weight="semi", drop=False)


def banner(img: Image.Image, txt: str, color, y: float, x0: float = 30, x1: float | None = None, size: float = 30):
    """The big result bar. `color` = a style name or one of the old color tuples."""
    kind = color if isinstance(color, str) else KIND.get(tuple(color), "lose")
    top, bot = STYLES[kind]
    x1 = x1 if x1 is not None else img.width / K - 30
    box = (x0, y - 27, x1, y + 27)
    shadow(img, box, 27, off=6, blur=10, alpha=170)
    if kind in ("win", "jackpot"):
        glow_edge(img, box, 27, mix(top, (255, 255, 255), 0.25), 1.5, blur=12, inner=False)
    panel(img, box, 27, top, bot, drop=False, shine=80)
    ImageDraw.Draw(img).rounded_rectangle(sb(box), radius=s(27), outline=mix(top, (255, 255, 255), 0.55), width=s(1.5))
    text(img, ((x0 + x1) / 2, y + 1), txt, size, (255, 255, 255), weight="black", maxw=(x1 - x0) - 36)


@lru_cache(maxsize=8)
def backdrop(w: int, h: int) -> Image.Image:
    """Deep purple night with a soft center light and a few blurry neon bokeh lights."""
    img = rgrad(s(w), s(h), (74, 24, 112), NIGHT)
    rng = random.Random(w * 7 + h)
    dots = Image.new("RGB", img.size, (0, 0, 0))
    mask = Image.new("L", img.size, 0)
    for _ in range(14):
        x, y, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(6, 22)
        col = rng.choice((PINK, TEAL, GOLD, VIOLET))
        ImageDraw.Draw(dots).ellipse(sb((x - r, y - r, x + r, y + r)), fill=col)
        ImageDraw.Draw(mask).ellipse(sb((x - r, y - r, x + r, y + r)), fill=rng.randint(30, 70))
    img.paste(dots.filter(ImageFilter.GaussianBlur(s(6))), (0, 0), mask.filter(ImageFilter.GaussianBlur(s(6))))
    return img


def fresh(cached: Image.Image) -> Image.Image:
    return cached.copy()


# ---------- 🎰 slots ----------

SW, SH = 600, 430
REEL_X = [130, 300, 470]
RW, RTOP, RBOT = 150, 124, 290                            # reel window width / top / bottom


@lru_cache(maxsize=1)
def _slot_chrome() -> Image.Image:
    img = backdrop(SW, SH).copy()
    panel(img, (16, 12, SW - 16, SH - 12), 30, (84, 22, 118), (34, 8, 58), edge=PINK, edge_w=3, shine=26)
    text(img, (SW / 2, 54), "CASA DE SOON SLOTS", 31, weight="black", grad=(GOLD_LIGHT, GOLD_DARK), glow=(255, 60, 150))
    panel(img, (46, RTOP - 12, SW - 46, RBOT + 12), 20, (10, 4, 20), (24, 8, 40), edge=TEAL, edge_w=2.4)
    mid = (RTOP + RBOT) / 2
    d = ImageDraw.Draw(img)
    for side in (1, -1):                                  # glowing pay-line arrows
        x = 30 if side == 1 else SW - 30
        tri = [(x - 8 * side, mid - 12), (x + 8 * side, mid), (x - 8 * side, mid + 12)]
        halo = Image.new("L", img.size, 0)
        ImageDraw.Draw(halo).polygon([(s(a), s(b)) for a, b in tri], fill=255)
        img.paste(PINK, (0, 0), halo.filter(ImageFilter.GaussianBlur(s(5))))
        d.polygon([(s(a), s(b)) for a, b in tri], fill=mix(PINK, (255, 255, 255), 0.3))
    return img


@lru_cache(maxsize=1)
def _cylinder() -> Image.Image:
    """Reel background: bright in the middle, falling off to the top and bottom like a drum."""
    h = s(RBOT - RTOP)
    col = Image.new("RGB", (1, h))
    for y in range(h):
        t = abs(y / (h - 1) - 0.5) * 2                     # 0 middle, 1 edges
        col.putpixel((0, y), mix((255, 252, 246), (120, 96, 140), t ** 2.2))
    return col.resize((s(RW), h))


def _reel(above: str, mid: str, below: str, off: float, blur: bool) -> Image.Image:
    strip = _cylinder().copy().convert("RGBA")
    h = strip.height
    for k, sym in enumerate((above, mid, below)):
        e = emoji(sym, s(100))
        y = h // 2 + s((k - 1) * 112 + off)
        strip.paste(e, (strip.width // 2 - e.width // 2, y - e.height // 2), e)
    if blur:                                              # vertical motion blur
        strip = strip.resize((strip.width, max(1, h // 9)), Image.BILINEAR).resize((strip.width, h), Image.BICUBIC)
    shade = Image.new("RGBA", strip.size, (0, 0, 0, 0))   # drum shading over the symbols too
    sd = ImageDraw.Draw(shade)
    for y in range(h):
        t = abs(y / (h - 1) - 0.5) * 2
        sd.line([(0, y), (strip.width, y)], fill=(40, 10, 60, int(150 * max(0, t - 0.45) / 0.55)))
    strip.alpha_composite(shade)
    return strip


def _slot_frame(reels: list, offsets: list, phase: int, name: str, pot: str, result: tuple | None = None) -> Image.Image:
    img = fresh(_slot_chrome())
    for i, x in enumerate(REEL_X):
        above, mid, below = reels[i]
        r = _reel(above, mid, below, offsets[i], blur=bool(offsets[i]))
        img.paste(r, (s(x - RW / 2), s(RTOP)), r)
    d = ImageDraw.Draw(img)
    for x in REEL_X[1:]:                                  # thin gold dividers
        xx = s(x - RW / 2 - 5)
        d.rectangle([xx - s(2), s(RTOP), xx + s(2), s(RBOT)], fill=GOLD_DARK)
        d.line([(xx - s(1), s(RTOP)), (xx - s(1), s(RBOT))], fill=GOLD_LIGHT, width=s(1))
    mid = s((RTOP + RBOT) / 2)
    tint(img, (s(55), mid - s(1), s(SW - 55), mid + s(1)), PINK, 110)        # pay line
    if phase % 2 and result is None:                      # lights flicker while spinning
        glow_edge(img, (46, RTOP - 12, SW - 46, RBOT + 12), 20, TEAL_LIGHT, 1.2, blur=6, inner=False)
    pill(img, SW / 2, 94, f"JACKPOT  {pot}", GOLD, 14)
    text(img, (SW / 2, 322), name[:28], 17, CREAM, weight="semi")
    return img


def slots_gif(a: str, b: str, c: str, pool: list, name: str, pot: str) -> bytes:
    final = [a, b, c]
    frames, durs = [], []
    stops = [6, 10, 14]                                   # reel 1 stops first, then 2, then 3
    for f in range(16):
        reels, offs = [], []
        for i in range(3):
            if f >= stops[i]:
                reels.append((random.choice(pool), final[i], random.choice(pool)))
                offs.append(0 if f > stops[i] else -16)   # tiny bounce as it lands
            else:
                reels.append((random.choice(pool), random.choice(pool), random.choice(pool)))
                offs.append(random.choice((-40, 0, 40)))
        frames.append(_slot_frame(reels, offs, f, name, pot))
        durs.append(110)
    durs[-1] = 4000
    return gif(frames, durs)


def slots_png(a: str, b: str, c: str, pool: list, name: str, pot: str, headline: str, kind: str) -> bytes:
    rng = random.Random(f"{a}{b}{c}")
    img = _slot_frame([(rng.choice(pool), sym, rng.choice(pool)) for sym in (a, b, c)], [0, 0, 0], 0, name, pot,
                      result=(a, b, c))
    style = {"jackpot": "jackpot", "triple": "win", "win": "win", "push": "push", "burrito": "burrito"}.get(kind, "lose")
    if kind in ("jackpot", "triple"):
        glow_edge(img, (46, RTOP - 12, SW - 46, RBOT + 12), 20, GOLD, 2.4, blur=10)
        for x, y, sz in ((62, 54, 34), (SW - 62, 54, 34), (88, 94, 22), (SW - 88, 94, 22)):
            put(img, "🌟" if kind == "jackpot" else "✨", x, y, sz, drop=False)
    banner(img, headline, style, 374)
    return png(img)


# ---------- 🎟️ scratch-offs ----------

TW, TH = 600, 350


@lru_cache(maxsize=1)
def _ticket_chrome() -> Image.Image:
    img = backdrop(TW, TH).copy()
    box = (24, 18, TW - 24, TH - 18)
    panel(img, box, 22, (255, 232, 140), (246, 168, 62), edge=PINK, edge_w=3, shine=60)
    d = ImageDraw.Draw(img)
    for x in range(44, TW - 40, 20):                      # perforation along the top
        d.ellipse(sb((x, 26, x + 6, 32)), fill=(226, 150, 50))
    text(img, (TW / 2, 58), "CASA DE SOON SCRATCH-OFF", 25, (80, 20, 70), weight="black", drop=False)
    pill(img, TW / 2, 90, "MATCH 3 TO WIN", PINK, 12, fill=(70, 16, 60))
    for i in range(3):
        x0 = 70 + i * 160
        shadow(img, (x0, 112, x0 + 140, 252), 16, off=4, blur=6, alpha=110)
        panel(img, (x0, 112, x0 + 140, 252), 16, (255, 255, 255), (238, 232, 240), drop=False)
    return img


@lru_cache(maxsize=1)
def _foil() -> Image.Image:
    """Silver scratch coating with a little glitter."""
    w, h = s(140), s(140)
    img = vgrad(w, h, (226, 228, 238), (150, 150, 170))
    rng = random.Random(5)
    d = ImageDraw.Draw(img)
    for _ in range(160):
        x, y = rng.randrange(w), rng.randrange(h)
        d.point((x, y), fill=rng.choice(((255, 255, 255), (190, 190, 205), (240, 220, 255))))
    text(img, (70, 70), "?", 58, (122, 120, 140), weight="black", drop=False)
    gloss(img, (0, 0, 140, 140), 16, 60)
    return img


def _ticket(show: list, revealed: int, name: str, scratch_frac: float = 0.0) -> Image.Image:
    img = fresh(_ticket_chrome())
    for i in range(3):
        x0 = 70 + i * 160
        put(img, show[i], x0 + 70, 182, 96, drop=True)
        cover = 1.0 if i >= revealed + (1 if scratch_frac else 0) else (1 - scratch_frac if i == revealed else 0)
        if cover > 0:
            h = s(140 * cover)
            m = Image.new("L", (s(140), s(140)), 0)
            md = ImageDraw.Draw(m)
            md.rounded_rectangle([0, 0, s(140) - 1, max(h, s(16))], radius=s(16), fill=255)
            if cover < 1:                                 # jagged scratched edge
                rng = random.Random(i * 31 + int(scratch_frac * 10))
                pts = [(0, h)] + [(x, h + rng.randint(-s(7), s(7))) for x in range(0, s(140), s(9))] + [(s(140), h)]
                md.polygon(pts + [(s(140), 0), (0, 0)], fill=255)
            img.paste(_foil(), (s(x0), s(112)), m)
    text(img, (TW / 2, 266), name[:30], 14, (90, 30, 70), weight="semi", drop=False)
    return img


def scratch_gif(show: list, name: str) -> bytes:
    frames, durs = [_ticket(show, 0, name)], [400]
    for i in range(3):
        for frac in (0.35, 0.7):
            frames.append(_ticket(show, i, name, frac))
            durs.append(140)
        frames.append(_ticket(show, i + 1, name))
        durs.append(300)
    durs[-1] = 4000
    return gif(frames, durs)


def scratch_png(show: list, name: str, headline: str, win: bool) -> bytes:
    img = _ticket(show, 3, name)
    banner(img, headline, "win" if win else "lose", 306)
    return png(img)


# ---------- 🎡 roulette ----------

ORDER = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18,
         29, 7, 28, 12, 35, 3, 26]                         # real European wheel order
REDS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
RWH = 340                                                  # wheel size
RX, RY = 30, 30                                            # where the wheel sits


def pocket_color(n: int):
    return GREEN if n == 0 else RED if n in REDS else BLACK


def _disc(size: int, inner, outer, box_r: float) -> tuple[Image.Image, Image.Image]:
    g = rgrad(size, size, inner, outer)
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse([0, 0, size - 1, size - 1], fill=255)
    return g, m


@lru_cache(maxsize=1)
def _wheel_base() -> Image.Image:
    S = s(RWH)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    c = S / 2
    rim = Image.new("L", (S, S), 0)
    ImageDraw.Draw(rim).ellipse([0, 0, S - 1, S - 1], fill=255)
    img.paste(rgrad(S, S, (120, 60, 24), (60, 26, 8)), (0, 0), rim)          # wooden rim
    d = ImageDraw.Draw(img)
    d.ellipse([s(2), s(2), S - s(2), S - s(2)], outline=GOLD, width=s(2))
    r = c - s(14)
    seg = 360 / 37
    for i, n in enumerate(ORDER):
        start = -90 - seg / 2 + i * seg
        d.pieslice([c - r, c - r, c + r, c + r], start, start + seg, fill=pocket_color(n))
    for i in range(37):                                    # gold frets between pockets
        a = math.radians(-90 - seg / 2 + i * seg)
        d.line([(c + math.cos(a) * r * 0.6, c + math.sin(a) * r * 0.6), (c + math.cos(a) * r, c + math.sin(a) * r)],
               fill=GOLD, width=s(1.2))
    for i, n in enumerate(ORDER):
        mid = -90 + i * seg
        ang = math.radians(mid)
        tx, ty = c + math.cos(ang) * (r - s(19)), c + math.sin(ang) * (r - s(19))
        lbl = Image.new("RGBA", (s(30), s(20)), (0, 0, 0, 0))
        ImageDraw.Draw(lbl).text((s(15), s(10)), str(n), font=font(s(12.5), "semi"), fill=CREAM, anchor="mm")
        lbl = lbl.rotate(-mid - 90, expand=True, resample=Image.BICUBIC)
        img.paste(lbl, (int(tx - lbl.width / 2), int(ty - lbl.height / 2)), lbl)
    d.ellipse([c - r * 0.62, c - r * 0.62, c + r * 0.62, c + r * 0.62], outline=GOLD, width=s(2))
    cone = int(r * 1.22)
    g, m = _disc(cone, (196, 130, 60), (96, 48, 18), 0)
    img.paste(g, (int(c - cone / 2), int(c - cone / 2)), m)
    hub = int(r * 0.74)
    g, m = _disc(hub, (120, 40, 150), (50, 12, 70), 0)
    img.paste(g, (int(c - hub / 2), int(c - hub / 2)), m)
    d.ellipse([c - hub / 2, c - hub / 2, c + hub / 2, c + hub / 2], outline=PINK, width=s(2.5))
    for k in range(4):                                     # the turret spokes
        a = math.radians(k * 90 + 45)
        d.line([(c + math.cos(a) * hub * 0.5, c + math.sin(a) * hub * 0.5),
                (c + math.cos(a) * cone * 0.48, c + math.sin(a) * cone * 0.48)], fill=GOLD, width=s(3))
    return img


@lru_cache(maxsize=1)
def _wheel_light() -> Image.Image:
    """Fixed lighting over the spinning wheel (light from the top left) + the SOON logo, which doesn't spin."""
    S = s(RWH)
    over = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).ellipse([S * 0.08, S * 0.04, S * 0.72, S * 0.5], fill=60)
    over.paste((255, 255, 255), (0, 0), m.filter(ImageFilter.GaussianBlur(s(26))))
    ring = Image.new("L", (S, S), 0)
    ImageDraw.Draw(ring).ellipse([0, 0, S - 1, S - 1], outline=120, width=s(10))
    over.paste((0, 0, 0), (0, 0), ring.filter(ImageFilter.GaussianBlur(s(6))))
    return over


@lru_cache(maxsize=1)
def _roulette_chrome() -> Image.Image:
    W, H = 600, 400
    img = backdrop(W, H).copy()
    box = (14, 10, W - 14, H - 10)
    shadow(img, box, 28)
    x0, y0, x1, y1 = sb(box)
    img.paste(rgrad(x1 - x0, y1 - y0, (34, 132, 84), (8, 46, 30)), (x0, y0), rmask(x1 - x0, y1 - y0, s(28)))
    glow_edge(img, box, 28, GOLD, 3)
    text(img, (480, 62), "ROULETTE", 32, weight="black", grad=(GOLD_LIGHT, GOLD_DARK), glow=(0, 0, 0))
    shadow(img, (RX + 4, RY + 4, RX + RWH - 4, RY + RWH - 4), RWH / 2, off=10, blur=14, alpha=170)
    return img


def _ball(img: Image.Image, x: float, y: float):
    shadow(img, (x - 8, y - 6, x + 8, y + 10), 8, off=2, blur=3, alpha=150)
    g, m = _disc(s(17), (255, 255, 255), (178, 178, 192), 0)
    img.paste(g, (s(x - 8.5), s(y - 8.5)), m)


def _roulette_frame(angle: float, ball_angle: float, ball_r: float, label: str, result: str = "") -> Image.Image:
    img = fresh(_roulette_chrome())
    wheel = _wheel_base().rotate(angle, resample=Image.BILINEAR)
    img.paste(wheel, (s(RX), s(RY)), wheel)
    light = _wheel_light()
    img.paste(light, (s(RX), s(RY)), light)
    c = (RX + RWH / 2, RY + RWH / 2)
    text(img, c, "SOON", 21, weight="black", grad=(GOLD_LIGHT, GOLD_DARK), drop=True)
    _ball(img, c[0] + math.cos(math.radians(ball_angle)) * ball_r, c[1] + math.sin(math.radians(ball_angle)) * ball_r)
    pill(img, 480, 104, label, TEAL, 15)
    if result:
        panel(img, (402, 146, 558, 302), 22, (44, 20, 66), (20, 6, 34), edge=GOLD, edge_w=2, shine=30)
        n = int(result)
        g, m = _disc(s(84), mix(pocket_color(n), (255, 255, 255), 0.25), pocket_color(n), 0)
        img.paste(g, (s(480 - 42), s(214 - 42)), m)
        ImageDraw.Draw(img).ellipse(sb((438, 172, 522, 256)), outline=GOLD, width=s(2.5))
        gloss(img, (438, 172, 522, 256), 42, 70)
        text(img, (480, 216), result, 36, (255, 255, 255), weight="black")
        text(img, (480, 280), "GREEN" if n == 0 else "RED" if n in REDS else "BLACK", 14, CREAM, weight="semi",
             track=3)
    return img


def roulette_gif(n: int, label: str) -> bytes:
    seg = 360 / 37
    final_wheel = random.uniform(0, 360)
    # where the winning pocket sits on screen after the wheel stops (PIL rotate is counter-clockwise)
    pocket = -90 + ORDER.index(n) * seg - final_wheel
    frames, durs = [], []
    steps = 22
    for f in range(steps):
        t = f / (steps - 1)
        ease = 1 - (1 - t) ** 3
        wheel = final_wheel - 540 * (1 - ease)
        ball = pocket + 900 * (1 - ease)
        ball_r = 152 - 42 * ease
        frames.append(_roulette_frame(wheel, ball, ball_r, label))
        durs.append(70 + int(120 * t))
    durs[-1] = 4000
    return gif(frames, durs), final_wheel, pocket


def roulette_png(n: int, label: str, final_wheel: float, pocket: float, headline: str, win: bool) -> bytes:
    img = _roulette_frame(final_wheel, pocket, 110, label, str(n))
    banner(img, headline, "win" if win else "lose", 347, x0=386, x1=574, size=21)
    return png(img)


# ---------- 🃏 blackjack ----------

CW, CH = 92, 130


@lru_cache(maxsize=64)
def _card(rank: str, suit: str, hidden: bool = False) -> Image.Image:
    W, H = s(CW), s(CH)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    m = rmask(W, H, s(10))
    if hidden:
        back = vgrad(W, H, (255, 96, 180), (176, 24, 110))
        d = ImageDraw.Draw(back)
        for k in range(-H, W + H, s(14)):                  # lattice pattern
            d.line([(k, 0), (k + H, H)], fill=(255, 130, 200), width=s(1.5))
            d.line([(k, H), (k + H, 0)], fill=(255, 130, 200), width=s(1.5))
        d.rounded_rectangle([s(6), s(6), W - s(6), H - s(6)], radius=s(7), outline=CREAM, width=s(2))
        img.paste(back, (0, 0), m)
        e = emoji("🌮", s(46))
        img.paste(e, (W // 2 - e.width // 2, H // 2 - e.height // 2), e)
        return img
    img.paste(vgrad(W, H, (255, 255, 255), (236, 232, 240)), (0, 0), m)
    col = RED if suit in "♥♦" else INK
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=s(10), outline=(200, 194, 210), width=s(1))
    d.text((s(9), s(4)), rank, font=font(s(24), "black"), fill=col)
    d.text((s(10), s(36)), suit, font=font(s(18), "symr"), fill=col)
    d.text((W // 2 + s(8), H // 2 + s(14)), suit, font=font(s(56), "symr"), fill=col, anchor="mm")
    return img


@lru_cache(maxsize=1)
def _bj_chrome() -> Image.Image:
    W, H = 640, 450
    img = Image.new("RGB", (s(W), s(H)), NIGHT)
    box = (6, 6, W - 6, H - 6)
    x0, y0, x1, y1 = sb(box)
    img.paste(rgrad(x1 - x0, y1 - y0, (30, 140, 86), (6, 44, 28)), (x0, y0), rmask(x1 - x0, y1 - y0, s(26)))
    d = ImageDraw.Draw(img)
    d.arc(sb((40, -300, W - 40, 228)), 30, 150, fill=(60, 170, 110), width=s(1.5))      # printed felt arc
    glow_edge(img, box, 26, GOLD, 3)
    text(img, (W / 2, 34), "CASA DE SOON BLACKJACK", 25, weight="black", grad=(GOLD_LIGHT, GOLD_DARK), glow=(0, 0, 0))
    text(img, (W / 2, 62), "SOON STANDS ON 17  •  BLACKJACK PAYS 3:2", 11, TEAL_LIGHT, weight="semi", drop=False,
         track=1.5)
    return img


def _seat(img: Image.Image, y: float, label: str, value):
    text(img, (30, y + 46), label, 17, CREAM, weight="xbold", align="l", maxw=110)
    if value is not None:
        g, m = _disc(s(46), (255, 220, 110), GOLD_DARK, 0)
        img.paste(g, (s(30), s(y + 66)), m)
        text(img, (53, y + 90), str(value), 20, INK, weight="black", drop=False)


def blackjack_png(player: list, dealer: list, pv: int, dv: int | None, name: str, headline: str = "",
                  hide_dealer: bool = False, color=(110, 80, 120)) -> bytes:
    img = fresh(_bj_chrome())

    def row(cards, y, label, value, hide):
        _seat(img, y, label, value)
        x = 156
        for k, cd in enumerate(cards):
            cx = x + k * 66
            shadow(img, (cx, y, cx + CW, y + CH), 10, off=5, blur=6, alpha=120)
            c = _card(cd[:-1], cd[-1], hide and k == 1)
            img.paste(c, (s(cx), s(y)), c)

    row(dealer, 82, "SOON", None if hide_dealer else dv, hide_dealer)
    row(player, 236, name[:10].upper(), pv, False)
    if headline:
        banner(img, headline, color, 406)
    return png(img)


# ---------- 🪙 taco toss ----------

CR = 82                                                    # coin radius


@lru_cache(maxsize=1)
def _toss_chrome() -> Image.Image:
    W, H = 600, 380
    img = backdrop(W, H).copy()
    panel(img, (14, 10, W - 14, H - 10), 28, (72, 20, 104), (26, 6, 46), edge=PINK, edge_w=3, shine=20)
    text(img, (W / 2, 42), "TACO TOSS", 32, weight="black", grad=(GOLD_LIGHT, GOLD_DARK), glow=(255, 60, 150))
    return img


@lru_cache(maxsize=2)
def _coin_face(face: str) -> Image.Image:
    S = s(CR * 2)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    g, m = _disc(S, (255, 226, 120), (206, 132, 20), 0)
    img.paste(g, (0, 0), m)
    d = ImageDraw.Draw(img)
    d.ellipse([s(10), s(10), S - s(10), S - s(10)], outline=(170, 100, 10), width=s(3))
    d.ellipse([s(13), s(13), S - s(13), S - s(13)], outline=(255, 236, 160), width=s(1.5))
    e = emoji("🌮" if face == "heads" else "🌯", s(92))
    img.paste(e, (S // 2 - e.width // 2, S // 2 - e.height // 2), e)
    hl = Image.new("L", (S, S), 0)                         # shine
    ImageDraw.Draw(hl).ellipse([S * 0.16, S * 0.08, S * 0.7, S * 0.46], fill=90)
    hl = hl.filter(ImageFilter.GaussianBlur(s(12)))
    img.paste((255, 255, 255), (0, 0), ImageChops.multiply(hl, m))
    img.putalpha(m)
    return img


def _coin(face: str, squash: float, y_off: float, label: str, side: bool = False) -> Image.Image:
    W = 600
    img = fresh(_toss_chrome())
    pill(img, W / 2, 80, label, TEAL, 14)
    cx, cy = W / 2, 204 + y_off
    lift = max(0.0, -y_off) / 90                           # shadow shrinks as the coin goes up
    sw = 92 * (1 - 0.45 * lift)
    sh_ = Image.new("L", (s(240), s(60)), 0)
    ImageDraw.Draw(sh_).ellipse(sb((120 - sw, 22, 120 + sw, 38)), fill=int(170 * (1 - 0.5 * lift)))
    img.paste((0, 0, 0), (s(cx - 120), s(290)), sh_.filter(ImageFilter.GaussianBlur(s(6))))
    if side:
        box = (cx - 14, cy - CR, cx + 14, cy + CR)
        x0, y0, x1, y1 = sb(box)
        edge = Image.new("RGB", (x1 - x0, y1 - y0))
        for x in range(edge.width):                        # rounded-edge shading
            t = abs(x / max(1, edge.width - 1) - 0.4) * 1.6
            ImageDraw.Draw(edge).line([(x, 0), (x, edge.height)], fill=mix((255, 230, 130), (170, 100, 10), min(1, t)))
        img.paste(edge, (x0, y0), rmask(x1 - x0, y1 - y0, s(10)))
        return img
    R = CR * (1 - 0.3 * lift)                              # smaller as it flies up and away
    w = max(int(s(R * 2) * abs(squash)), s(4))
    c = _coin_face(face).resize((w, s(R * 2)), Image.BICUBIC)
    if abs(squash) < 0.999:                                # the coin's edge shows while it turns
        e = Image.new("RGBA", (w + s(6), s(R * 2)), (0, 0, 0, 0))
        em = Image.new("L", e.size, 0)
        ImageDraw.Draw(em).ellipse([0, 0, e.width - 1, e.height - 1], fill=255)
        e.paste((176, 104, 12), (0, 0), em)
        img.paste(e, (s(cx) - w // 2 - s(3) + (s(3) if squash > 0 else -s(3)), s(cy - R)), e)
    img.paste(c, (s(cx) - w // 2, s(cy - R)), c)
    return img


def toss_gif(landed: str, edge: bool, label: str) -> bytes:
    frames, durs = [], []
    n = 20
    for f in range(n):
        t = f / (n - 1)
        squash = math.cos(t * math.pi * 7)
        face = "heads" if squash >= 0 else "tails"
        y = -int(90 * math.sin(t * math.pi))
        frames.append(_coin(face, squash, y, label))
        durs.append(70)
    frames.append(_coin(landed, 1.0, 0, label, side=edge))
    durs.append(4000)
    return gif(frames, durs)


def toss_png(landed: str, edge: bool, label: str, headline: str, win: bool) -> bytes:
    img = _coin(landed, 1.0, 0, label, side=edge)
    banner(img, headline, "win" if win else "lose", 338)
    return png(img)


# ---------- 🎡 Wheel of Fortaco ----------

FWH = 316                                                  # wheel size
FX, FY = 42, 40
SEG_COLORS = [(PINK, CREAM), (GOLD, INK), (TEAL, INK), (VIOLET, CREAM)]


@lru_cache(maxsize=4)
def _fortaco_wheel_base(segments: tuple) -> Image.Image:
    S = s(FWH)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = S / 2
    rim = Image.new("L", (S, S), 0)
    ImageDraw.Draw(rim).ellipse([0, 0, S - 1, S - 1], fill=255)
    img.paste(rgrad(S, S, (255, 220, 120), GOLD_DARK), (0, 0), rim)
    r = c - s(14)
    seg = 360 / len(segments)
    for i, (sym, txt) in enumerate(segments):
        start = -90 - seg / 2 + i * seg
        bg, _ = SEG_COLORS[i % len(SEG_COLORS)]
        d.pieslice([c - r, c - r, c + r, c + r], start, start + seg, fill=bg)
    shade = Image.new("L", (S, S), 0)                      # deeper color toward the rim
    ImageDraw.Draw(shade).ellipse([c - r, c - r, c + r, c + r], fill=255)
    sh = Image.radial_gradient("L").resize((int(2 * r), int(2 * r))).point(lambda v: int(v * 0.35))
    full = Image.new("L", (S, S), 0)
    full.paste(sh, (int(c - r), int(c - r)))
    img.paste((40, 0, 50), (0, 0), ImageChops.multiply(full, shade))
    for i in range(len(segments)):                         # cream dividers
        a = math.radians(-90 - seg / 2 + i * seg)
        d.line([(c, c), (c + math.cos(a) * r, c + math.sin(a) * r)], fill=CREAM, width=s(2.5))
    for i, (sym, txt) in enumerate(segments):
        start = -90 - seg / 2 + i * seg
        _, fg = SEG_COLORS[i % len(SEG_COLORS)]
        ang = math.radians(start + seg / 2)
        e = emoji(sym, s(36))
        ex, ey = c + math.cos(ang) * r * 0.76, c + math.sin(ang) * r * 0.76
        img.paste(e, (int(ex - e.width / 2), int(ey - e.height / 2)), e)
        lbl = Image.new("RGBA", (s(84), s(24)), (0, 0, 0, 0))
        ImageDraw.Draw(lbl).text((s(42), s(12)), txt, font=font(s(11.5), "black"), fill=fg, anchor="mm")
        lbl = lbl.rotate(-(start + seg / 2), expand=True, resample=Image.BICUBIC)
        tx, ty = c + math.cos(ang) * r * 0.44, c + math.sin(ang) * r * 0.44
        img.paste(lbl, (int(tx - lbl.width / 2), int(ty - lbl.height / 2)), lbl)
    for k in range(24):                                    # rim lights
        a = math.radians(k * 15)
        x, y = c + math.cos(a) * (c - s(7)), c + math.sin(a) * (c - s(7))
        d.ellipse([x - s(3), y - s(3), x + s(3), y + s(3)], fill=(255, 250, 220))
    return img


@lru_cache(maxsize=1)
def _fortaco_chrome() -> Image.Image:
    W, H = 600, 380
    img = backdrop(W, H).copy()
    panel(img, (14, 10, W - 14, H - 10), 28, (72, 20, 104), (26, 6, 46), edge=GOLD, edge_w=3, shine=20)
    text(img, (455, 72), "WHEEL OF", 26, weight="black", grad=(GOLD_LIGHT, GOLD_DARK))
    text(img, (455, 108), "FORTACO", 40, weight="black", grad=((255, 140, 200), (230, 30, 130)), glow=PINK)
    shadow(img, (FX + 4, FY + 4, FX + FWH - 4, FY + FWH - 4), FWH / 2, off=10, blur=14, alpha=170)
    return img


@lru_cache(maxsize=1)
def _fortaco_top() -> Image.Image:
    """Everything that sits still on top of the spinning wheel: shine, hub, pointer."""
    img = Image.new("RGBA", (s(600), s(380)), (0, 0, 0, 0))
    c = (FX + FWH / 2, FY + FWH / 2)
    hl = Image.new("L", (s(FWH), s(FWH)), 0)               # fixed shine on the spinning wheel
    ImageDraw.Draw(hl).ellipse([s(FWH * 0.1), s(FWH * 0.05), s(FWH * 0.7), s(FWH * 0.45)], fill=55)
    img.paste((255, 255, 255, 255), (s(FX), s(FY)), hl.filter(ImageFilter.GaussianBlur(s(22))))
    g, m = _disc(s(54), CREAM, (230, 200, 220), 0)        # hub
    img.paste(g, (s(c[0] - 27), s(c[1] - 27)), m)
    d = ImageDraw.Draw(img)
    d.ellipse(sb((c[0] - 27, c[1] - 27, c[0] + 27, c[1] + 27)), outline=PINK, width=s(3))
    e = emoji("🌮", s(30))
    img.paste(e, (s(c[0]) - e.width // 2, s(c[1]) - e.height // 2), e)
    tip = [(c[0] - 16, FY - 8), (c[0] + 16, FY - 8), (c[0], FY + 26)]                # pointer
    halo = Image.new("L", img.size, 0)
    ImageDraw.Draw(halo).polygon([(s(a), s(b + 3)) for a, b in tip], fill=255)
    img.paste((0, 0, 0, 160), (0, 0), halo.filter(ImageFilter.GaussianBlur(s(4))))
    halo = Image.new("L", img.size, 0)
    ImageDraw.Draw(halo).polygon([(s(a), s(b)) for a, b in tip], fill=255)
    img.paste(PINK + (255,), (0, 0), halo.filter(ImageFilter.GaussianBlur(s(5))))
    d.polygon([(s(a), s(b)) for a, b in tip], fill=CREAM, outline=PINK, width=s(2))
    return img


def _fortaco_frame(segments, angle, name, result=""):
    img = fresh(_fortaco_chrome())
    wheel = _fortaco_wheel_base(tuple(segments)).rotate(angle, resample=Image.BILINEAR)
    img.paste(wheel, (s(FX), s(FY)), wheel)
    top = _fortaco_top()
    img.paste(top, (0, 0), top)
    pill(img, 455, 150, name[:20], TEAL, 14)
    if result:
        sym, txt = result
        panel(img, (372, 190, 538, 300), 20, (60, 22, 90), (24, 6, 40), edge=GOLD, edge_w=2, shine=30)
        put(img, sym, 455, 228, 46)
        text(img, (455, 278), txt, 20, CREAM, weight="black", maxw=150)
    return img


def fortaco_gif(segments: list, land: int, name: str):
    seg = 360 / len(segments)
    final = land * seg + random.uniform(-seg * 0.3, seg * 0.3)      # rotate so segment `land` sits under the pointer
    frames, durs = [], []
    steps = 22
    for f in range(steps):
        t = f / (steps - 1)
        ease = 1 - (1 - t) ** 3
        frames.append(_fortaco_frame(segments, final + 1080 * (1 - ease), name))
        durs.append(70 + int(110 * t))
    durs[-1] = 4000
    return gif(frames, durs), final


def fortaco_png(segments: list, final: float, name: str, result: tuple) -> bytes:
    return png(_fortaco_frame(segments, final, name, result))
