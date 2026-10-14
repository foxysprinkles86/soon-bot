"""Casa de Soon graphics: Soon draws the casino games as pictures (Pillow) instead of text.
Each game gets an animated GIF while it plays (reels spinning, wheel turning, coin flipping, card scratching)
and a still PNG of the result that replaces it. Art = free Twemoji images in art/emoji (swap in custom PNGs with
the same file names later). If anything here fails, the games fall back to their old text look.

Every function returns PNG/GIF bytes; call them with `await render(fn, ...)` so drawing never blocks Soon."""
import asyncio
import io
import math
import os
import random
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ART = os.path.join(os.path.dirname(__file__), "art")
BG, BG2 = (28, 12, 46), (52, 20, 78)              # deep purple casino night
PINK, GOLD, CREAM, INK = (255, 69, 163), (255, 200, 60), (255, 244, 230), (30, 16, 40)
TEAL, TEAL_DARK = (0, 210, 200), (0, 120, 120)          # Shannon: "and teal!"
GREEN, RED, BLACK = (24, 140, 70), (210, 38, 52), (25, 25, 30)

CODES = {"🌮": "1f32e", "🥑": "1f951", "🐷": "1f437", "🚀": "1f680", "🍹": "1f379", "🦑": "1f991", "🌯": "1f32f",
         "🌀": "1f300", "🎰": "1f3b0", "🪙": "1fa99", "💸": "1f4b8", "🎡": "1f3a1", "💅": "1f485", "🎟️": "1f39f",
         "🟫": "1f7eb", "🗑️": "1f5d1", "🚨": "1f6a8", "🏆": "1f3c6", "🃏": "1f0cf", "✨": "2728", "🌟": "1f31f",
         "🔥": "1f525", "💀": "1f480", "🎲": "1f3b2", "💥": "1f4a5"}


async def render(fn, *args, **kwargs) -> bytes:
    return await asyncio.to_thread(fn, *args, **kwargs)


@lru_cache(maxsize=64)
def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(ART, "fonts", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), size)


@lru_cache(maxsize=128)
def emoji(sym: str, size: int) -> Image.Image:
    img = Image.open(os.path.join(ART, "emoji", CODES[sym] + ".png")).convert("RGBA")
    return img.resize((size, size), Image.LANCZOS)


def png(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


def gif(frames: list[Image.Image], durations: list[int]) -> bytes:
    out = io.BytesIO()
    pal = [f.convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT) for f in frames]
    pal[0].save(out, "GIF", save_all=True, append_images=pal[1:], duration=durations, loop=0, disposal=2, optimize=False)
    return out.getvalue()


def backdrop(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    for y in range(h):                                        # soft vertical glow
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(BG[i] + (BG2[i] - BG[i]) * math.sin(t * math.pi)) for i in range(3)))
    return img


def centered(d: ImageDraw.ImageDraw, xy, text: str, size: int, fill, bold=True, stroke=0, stroke_fill=INK):
    f = font(size, bold)
    l, t, r, b = d.textbbox((0, 0), text, font=f, stroke_width=stroke)
    d.text((xy[0] - (r - l) / 2 - l, xy[1] - (b - t) / 2 - t), text, font=f, fill=fill, stroke_width=stroke,
           stroke_fill=stroke_fill)


def bulbs(d: ImageDraw.ImageDraw, box, step: int, phase: int):
    """Marquee lights around a rectangle; phase makes them chase."""
    x0, y0, x1, y1 = box
    pts = [(x, y0) for x in range(x0, x1, step)] + [(x1, y) for y in range(y0, y1, step)] + \
          [(x, y1) for x in range(x1, x0, -step)] + [(x0, y) for y in range(y1, y0, -step)]
    for i, (x, y) in enumerate(pts):
        on = (i + phase) % 3 == 0
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(GOLD if i % 2 else TEAL) if on else (70, 50, 70))


def banner(img: Image.Image, text: str, color, y: int, x0: int = 30, x1: int | None = None, size: int = 30):
    d = ImageDraw.Draw(img)
    x1 = x1 if x1 is not None else img.width - 30
    while size > 14 and d.textlength(text, font=font(size)) > (x1 - x0) - 30:
        size -= 2                                            # shrink long headlines to fit
    d.rounded_rectangle([x0, y - 26, x1, y + 26], radius=16, fill=color, outline=CREAM, width=3)
    centered(d, ((x0 + x1) / 2, y), text, size, CREAM, stroke=2, stroke_fill=INK)


# ---------- 🎰 slots ----------

SW, SH = 600, 430
REEL_X = [130, 300, 470]
RW, RTOP, RBOT = 150, 126, 292                            # reel window width / top / bottom


def _reel(above: str, mid: str, below: str, off: int, blur: bool) -> Image.Image:
    strip = Image.new("RGBA", (RW, RBOT - RTOP), (255, 255, 255, 255))
    cy = (RBOT - RTOP) // 2
    for k, sym in enumerate((above, mid, below)):
        y = cy + (k - 1) * 110 + off
        e = emoji(sym, 104)
        strip.paste(e, (RW // 2 - 52, int(y - 52)), e)
    if blur:
        strip = strip.filter(ImageFilter.GaussianBlur(3))
    shade = ImageDraw.Draw(strip)                           # curved-glass shading at top and bottom
    for i in range(18):
        a_ = int(110 * (1 - i / 18))
        shade.line([(0, i), (RW, i)], fill=(60, 30, 70, a_))
        shade.line([(0, RBOT - RTOP - 1 - i), (RW, RBOT - RTOP - 1 - i)], fill=(60, 30, 70, a_))
    return strip


def _slot_frame(reels: list, offsets: list, phase: int, name: str, pot: str, result: tuple | None = None) -> Image.Image:
    img = backdrop(SW, SH)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 14, SW - 20, SH - 14], radius=28, fill=(90, 18, 70), outline=PINK, width=6)
    bulbs(d, (36, 30, SW - 36, SH - 30), 26, phase)
    centered(d, (SW / 2, 66), "CASA DE SOON SLOTS", 30, GOLD, stroke=2)
    centered(d, (SW / 2, 98), f"JACKPOT {pot}", 18, TEAL)
    d.rounded_rectangle([50, RTOP - 8, SW - 50, RBOT + 8], radius=18, fill=CREAM, outline=TEAL, width=5)
    for i, x in enumerate(REEL_X):
        above, mid, below = reels[i]
        r = _reel(above, mid, below, offsets[i], blur=bool(offsets[i]))
        img.paste(r, (x - RW // 2, RTOP), r)
    d = ImageDraw.Draw(img)
    for x in REEL_X[1:]:
        d.line([(x - RW // 2 - 5, RTOP), (x - RW // 2 - 5, RBOT)], fill=(200, 190, 200), width=6)
    mid_y = (RTOP + RBOT) // 2
    d.polygon([(52, mid_y - 10), (66, mid_y), (52, mid_y + 10)], fill=PINK)          # pay-line arrows
    d.polygon([(SW - 52, mid_y - 10), (SW - 66, mid_y), (SW - 52, mid_y + 10)], fill=PINK)
    centered(d, (SW / 2, 322), name[:28], 18, CREAM)
    return img


def slots_gif(a: str, b: str, c: str, pool: list, name: str, pot: str) -> bytes:
    final = [a, b, c]
    frames, durs = [], []
    stops = [6, 10, 14]                                      # reel 1 stops first, then 2, then 3
    for f in range(16):
        reels, offs = [], []
        for i in range(3):
            if f >= stops[i]:
                reels.append((random.choice(pool), final[i], random.choice(pool)))
                offs.append(0 if f > stops[i] else -18)      # tiny bounce as it lands
            else:
                reels.append((random.choice(pool), random.choice(pool), random.choice(pool)))
                offs.append(random.choice((-40, 0, 40)))
        frames.append(_slot_frame(reels, offs, f, name, pot))
        durs.append(110)
    durs[-1] = 4000
    return gif(frames, durs)


def slots_png(a: str, b: str, c: str, pool: list, name: str, pot: str, headline: str, kind: str) -> bytes:
    rng = random.Random(f"{a}{b}{c}")
    img = _slot_frame([(rng.choice(pool), s, rng.choice(pool)) for s in (a, b, c)], [0, 0, 0], 0, name, pot, result=(a, b, c))
    color = {"jackpot": (200, 40, 140), "triple": (40, 150, 80), "win": (40, 150, 80), "push": (70, 90, 160),
             "burrito": (150, 70, 30)}.get(kind, (90, 60, 110))
    banner(img, headline, color, 372)
    if kind in ("jackpot", "triple"):                        # a little sparkle around the title
        for x, y, sz in ((70, 50, 34), (SW - 104, 50, 34), (100, 84, 24), (SW - 124, 84, 24)):
            e = emoji("🌟" if kind == "jackpot" else "✨", sz)
            img.paste(e, (x, y), e)
    return png(img)


# ---------- 🎟️ scratch-offs ----------

def _ticket(show: list, revealed: int, name: str, scratch_frac: float = 0.0) -> Image.Image:
    W, H = 600, 350
    img = backdrop(W, H)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([24, 20, W - 24, H - 20], radius=20, fill=(255, 226, 120), outline=PINK, width=6)
    d.rounded_rectangle([34, 30, W - 34, H - 30], radius=16, outline=TEAL, width=3)
    for x in range(40, W - 40, 22):                           # ticket perforation
        d.ellipse([x, 26, x + 6, 32], fill=(230, 180, 60))
    centered(d, (W / 2, 62), "CASA DE SOON SCRATCH-OFF", 26, INK)
    centered(d, (W / 2, 92), "MATCH 3 TO WIN", 16, (120, 40, 80))
    for i in range(3):
        x0 = 70 + i * 160
        box = [x0, 112, x0 + 140, 252]
        d.rounded_rectangle(box, radius=14, fill=CREAM, outline=INK, width=3)
        e = emoji(show[i], 100)
        img.paste(e, (x0 + 20, 132), e)
        cover = 1.0 if i >= revealed + (1 if scratch_frac else 0) else (1 - scratch_frac if i == revealed else 0)
        if cover > 0:
            h = int(140 * cover)
            d.rounded_rectangle([x0, 112, x0 + 140, 112 + max(h, 14)], radius=14, fill=(160, 160, 170), outline=INK, width=3)
            if cover == 1.0:
                centered(d, (x0 + 70, 182), "?", 54, (110, 110, 120))
            else:                                             # scratch edge flakes
                for _ in range(10):
                    fx = x0 + random.randint(6, 134)
                    d.ellipse([fx, 112 + h - 4, fx + 6, 112 + h + 2], fill=(140, 140, 150))
    centered(d, (W / 2, 272), name[:30], 16, INK, bold=False)
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
    banner(img, headline, (40, 150, 80) if win else (110, 80, 120), 306)
    return png(img)


# ---------- 🎡 roulette ----------

ORDER = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18,
         29, 7, 28, 12, 35, 3, 26]                         # real European wheel order
REDS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


@lru_cache(maxsize=1)
def _wheel_base() -> Image.Image:
    S = 340
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c, r = S / 2, S / 2 - 6
    d.ellipse([c - r - 4, c - r - 4, c + r + 4, c + r + 4], fill=(110, 60, 20))
    seg = 360 / 37
    for i, n in enumerate(ORDER):
        start = -90 - seg / 2 + i * seg
        col = GREEN if n == 0 else RED if n in REDS else BLACK
        d.pieslice([c - r, c - r, c + r, c + r], start, start + seg, fill=col, outline=GOLD)
        ang = math.radians(start + seg / 2)
        tx, ty = c + math.cos(ang) * (r - 20), c + math.sin(ang) * (r - 20)
        lbl = Image.new("RGBA", (30, 18), (0, 0, 0, 0))
        ImageDraw.Draw(lbl).text((15, 9), str(n), font=font(13), fill=CREAM, anchor="mm")
        lbl = lbl.rotate(-(start + seg / 2) - 90, expand=True, resample=Image.BICUBIC)
        img.paste(lbl, (int(tx - lbl.width / 2), int(ty - lbl.height / 2)), lbl)
    d.ellipse([c - r * 0.62, c - r * 0.62, c + r * 0.62, c + r * 0.62], fill=(120, 70, 30), outline=GOLD, width=3)
    d.ellipse([c - r * 0.38, c - r * 0.38, c + r * 0.38, c + r * 0.38], fill=(90, 18, 70), outline=PINK, width=3)
    centered(d, (c, c), "SOON", 22, GOLD, stroke=1)
    return img


def _roulette_frame(angle: float, ball_angle: float, ball_r: float, label: str, result: str = "") -> Image.Image:
    W, H = 600, 400
    img = backdrop(W, H)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([14, 10, W - 14, H - 10], radius=26, fill=(20, 70, 45), outline=GOLD, width=5)
    wheel = _wheel_base().rotate(angle, resample=Image.BICUBIC)
    img.paste(wheel, (30, 30), wheel)
    c = (30 + 170, 30 + 170)
    bx, by = c[0] + math.cos(math.radians(ball_angle)) * ball_r, c[1] + math.sin(math.radians(ball_angle)) * ball_r
    d.ellipse([bx - 8, by - 8, bx + 8, by + 8], fill=(250, 250, 250), outline=INK, width=2)
    centered(d, (480, 70), "ROULETTE", 30, GOLD, stroke=2)
    centered(d, (480, 112), label, 20, TEAL)
    if result:
        d.rounded_rectangle([400, 160, 560, 300], radius=20, fill=CREAM, outline=GOLD, width=4)
        n = int(result)
        col = GREEN if n == 0 else RED if n in REDS else BLACK
        d.ellipse([440, 180, 520, 260], fill=col, outline=GOLD, width=3)
        centered(d, (480, 220), result, 34, CREAM, stroke=1)
        centered(d, (480, 282), "GREEN" if n == 0 else "RED" if n in REDS else "BLACK", 16, INK)
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
        ball_r = 150 - 40 * ease
        frames.append(_roulette_frame(wheel, ball, ball_r, label))
        durs.append(70 + int(120 * t))
    durs[-1] = 4000
    return gif(frames, durs), final_wheel, pocket


def roulette_png(n: int, label: str, final_wheel: float, pocket: float, headline: str, win: bool) -> bytes:
    img = _roulette_frame(final_wheel, pocket, 110, label, str(n))
    banner(img, headline, (40, 150, 80) if win else (110, 80, 120), 345, x0=385, x1=575, size=22)
    return png(img)


# ---------- 🃏 blackjack ----------

def _card(rank: str, suit: str, hidden: bool = False) -> Image.Image:
    W, H = 92, 130
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if hidden:
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=10, fill=PINK, outline=CREAM, width=3)
        for k in range(-H, W, 12):
            d.line([(k, 0), (k + H, H)], fill=(230, 50, 140), width=4)
        e = emoji("🌮", 44)
        img.paste(e, (W // 2 - 22, H // 2 - 22), e)
        return img
    red = suit in "♥♦"
    col = RED if red else INK
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=10, fill=(255, 255, 255), outline=(60, 60, 70), width=2)
    d.text((8, 4), rank, font=font(24), fill=col)
    d.text((8, 32), suit, font=font(20, bold=False), fill=col)
    centered(d, (W / 2 + 6, H / 2 + 12), suit, 54, col, bold=False)
    return img


def blackjack_png(player: list, dealer: list, pv: int, dv: int | None, name: str, headline: str = "",
                  hide_dealer: bool = False, color=(110, 80, 120)) -> bytes:
    W, H = 640, 450
    img = Image.new("RGB", (W, H), (18, 92, 56))
    d = ImageDraw.Draw(img)
    for r in range(0, 360, 6):                                 # felt texture
        d.ellipse([W / 2 - 300 - r, -260 - r, W / 2 + 300 + r, 260 + r], outline=(20, 98, 60))
    d.rounded_rectangle([8, 8, W - 8, H - 8], radius=24, outline=GOLD, width=5)
    centered(d, (W / 2, 34), "CASA DE SOON BLACKJACK", 24, GOLD, stroke=1)
    centered(d, (W / 2, 58), "SOON STANDS ON 17 • BLACKJACK PAYS 3:2", 12, TEAL, bold=False)

    def row(cards, y, label, value, hide):
        d.text((24, y + 50), label, font=font(18), fill=CREAM)
        if value is not None:
            d.text((24, y + 74), str(value), font=font(26), fill=GOLD)
        x = 150
        for k, cd in enumerate(cards):
            hidden = hide and k == 1
            c = _card(cd[:-1], cd[-1], hidden)
            img.paste(c, (x + k * 70, y), c)

    row(dealer, 80, "SOON", None if hide_dealer else dv, hide_dealer)
    row(player, 236, name[:10].upper(), pv, False)
    if headline:
        banner(img, headline, color, 404)
    return png(img)


# ---------- 🪙 taco toss ----------

def _coin(face: str, squash: float, y_off: int, label: str, side: bool = False) -> Image.Image:
    W, H = 600, 380
    img = backdrop(W, H)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([14, 10, W - 14, H - 10], radius=26, outline=PINK, width=5)
    d.rounded_rectangle([24, 20, W - 24, H - 20], radius=20, outline=TEAL, width=2)
    centered(d, (W / 2, 40), "TACO TOSS", 28, GOLD, stroke=2)
    centered(d, (W / 2, 70), label, 16, TEAL)
    cx, cy, r = W / 2, 200 + y_off, 80
    d.ellipse([cx - 90, 292, cx + 90, 312], fill=(15, 6, 25))                     # shadow
    if side:
        d.rounded_rectangle([cx - 14, cy - r, cx + 14, cy + r], radius=8, fill=GOLD, outline=(160, 110, 20), width=4)
        return img
    w = max(int(r * abs(squash)), 3)
    d.ellipse([cx - w, cy - r, cx + w, cy + r], fill=GOLD, outline=(170, 120, 20), width=6)
    if w > 30:
        e = emoji("🌮" if face == "heads" else "🌯", 96).resize((max(int(96 * abs(squash)), 4), 96))
        img.paste(e, (int(cx - e.width / 2), int(cy - 48)), e)
    return img


def toss_gif(landed: str, edge: bool, label: str) -> bytes:
    frames, durs = [], []
    n = 20
    for f in range(n):
        t = f / (n - 1)
        squash = math.cos(t * math.pi * 7)
        face = "heads" if squash >= 0 else "tails"
        y = -int(120 * math.sin(t * math.pi))
        frames.append(_coin(face, squash, y, label))
        durs.append(70)
    frames.append(_coin(landed, 1.0, 0, label, side=edge))
    durs.append(4000)
    return gif(frames, durs)


def toss_png(landed: str, edge: bool, label: str, headline: str, win: bool) -> bytes:
    img = _coin(landed, 1.0, 0, label, side=edge)
    banner(img, headline, (40, 150, 80) if win else (110, 80, 120), 336)
    return png(img)


# ---------- 🎡 Wheel of Fortaco ----------

def _fortaco_wheel(segments: list, angle: float) -> Image.Image:
    S = 320
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c, r = S / 2, S / 2 - 6
    seg = 360 / len(segments)
    colors = [PINK, GOLD, TEAL, (120, 60, 200), PINK, GOLD, TEAL, (120, 60, 200)]
    for i, (sym, txt) in enumerate(segments):
        start = -90 - seg / 2 + i * seg
        d.pieslice([c - r, c - r, c + r, c + r], start, start + seg, fill=colors[i % len(colors)], outline=CREAM, width=3)
        ang = math.radians(start + seg / 2)
        ex, ey = c + math.cos(ang) * r * 0.66, c + math.sin(ang) * r * 0.66
        e = emoji(sym, 40)
        img.paste(e, (int(ex - 20), int(ey - 20)), e)
        tx, ty = c + math.cos(ang) * r * 0.36, c + math.sin(ang) * r * 0.36
        lbl = Image.new("RGBA", (80, 22), (0, 0, 0, 0))
        ImageDraw.Draw(lbl).text((40, 11), txt, font=font(13), fill=INK, anchor="mm")
        lbl = lbl.rotate(-(start + seg / 2), expand=True, resample=Image.BICUBIC)
        img.paste(lbl, (int(tx - lbl.width / 2), int(ty - lbl.height / 2)), lbl)
    d.ellipse([c - 26, c - 26, c + 26, c + 26], fill=CREAM, outline=PINK, width=4)
    return img.rotate(angle, resample=Image.BICUBIC)


def _fortaco_frame(segments, angle, name, result=""):
    W, H = 600, 380
    img = backdrop(W, H)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([14, 10, W - 14, H - 10], radius=26, outline=GOLD, width=5)
    bulbs(d, (30, 26, W - 30, H - 26), 30, int(angle // 15))
    wheel = _fortaco_wheel(segments, angle)
    img.paste(wheel, (40, 36), wheel)
    d.polygon([(200 - 14, 30), (200 + 14, 30), (200, 58)], fill=CREAM, outline=INK)
    centered(d, (455, 80), "WHEEL OF", 26, GOLD, stroke=2)
    centered(d, (455, 112), "FORTACO", 34, PINK, stroke=2)
    centered(d, (455, 150), name[:20], 16, TEAL)
    if result:
        sym, txt = result
        d.rounded_rectangle([370, 196, 545, 300], radius=18, fill=CREAM, outline=GOLD, width=4)
        e = emoji(sym, 44)
        img.paste(e, (435, 204), e)
        centered(d, (457, 272), txt, 20, INK)
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
