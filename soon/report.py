"""The Van Daily Report, moved over from Soon Classic (#14, #15, #26). At 11:55 PM (Classic's day: UTC-5) Soon posts
the day's MVPs, with Classic's prizes and fines:
  🌮 Most Desperate (most taco requests): +1 taco      🍹 Thirstiest (most margaritas): -1 taco (bar tab)
  🧾 Biggest Mouth (most disrespect to Soon): -2 tacos  💖 Teacher's Pet (most kindness to Soon): +1 taco
Then the Casa de Soon Report: 🤩 High Roller (biggest net win today): -10 chips (tips Soon, the cocktail waitress)
and 💸 Biggest Loser (biggest net loss): +25 chips pity comp. Posts in REPORT_CHANNEL (default: #soons-diary, falls back to #soon-lab)."""
import datetime as dt
import random

import discord

from . import config
from .casino import C, pic
from .economy import Bank, casino_day, now


def _top(day: dict):
    if not day:
        return None, 0
    uid, n = max(day.items(), key=lambda kv: kv[1])
    return int(uid), n


def _s(n: int) -> str:
    return "" if n == 1 else "s"


def due(when: dt.datetime | None = None) -> bool:
    """11:55 PM or later on Classic's clock (UTC-5)."""
    t = (when or now()) - dt.timedelta(hours=5)
    return t.hour == 23 and t.minute >= 55


async def post(guild: discord.Guild, bank: Bank, force: bool = False) -> bool:
    """Post today's report once (force=True for a mod preview/test). Returns True if it posted."""
    gid, day = guild.id, casino_day()
    if not force:
        if await bank.get_house(gid, "vanday") == day:
            return False
        await bank.set_house(gid, "vanday", day)
    ch = (next((c for c in guild.text_channels if config.REPORT_CHANNEL in c.name.lower()), None)
          or next((c for c in guild.text_channels if "soon-lab" in c.name.lower()), None))
    if not ch:
        return False
    stamp = (now() - dt.timedelta(hours=5)).strftime("%b %-d")
    lines = []
    t, tn = _top(await bank.get_house(gid, f"tacoday:{day}", {}) or {})
    if t:
        w = await bank.add(gid, t, "van report: most desperate", tacobal=1)
        lines.append(f"🌮 **Most Desperate:** <@{t}> with {tn} taco request{_s(tn)}. " + random.choice(
            ["Tacos received: 0. Respect.", "Commitment to disappointment.", "Still waiting. Still believing.",
             "The van admires your delusion."]) + f"\n-# 🎁 Pity prize: +1 taco. Tacos: {w.tacobal} 🌮")
    m, mn = _top(await bank.get_house(gid, f"margday:{day}", {}) or {})
    if m:
        w = await bank.add(gid, m, "van report: thirstiest", tacobal=-1)
        lines.append(f"🍹 **Thirstiest:** <@{m}> with {mn} margarita{_s(mn)}. " + random.choice(
            ["The bartender bought a boat.", "Liver status: concerning.", "Single-handedly keeping the van bar open.",
             "Hydrate. With water. Just once."]) + f"\n-# 🧾 Bar tab due: -1 taco. Tacos: {w.tacobal} 🌮")
    d, dn = _top(await bank.get_house(gid, f"disrespectday:{day}", {}) or {})
    if d:
        w = await bank.add(gid, d, "van report: biggest mouth", tacobal=-2)
        lines.append(f"🧾 **Biggest Mouth:** <@{d}> with {dn} insult{_s(dn)}. " + random.choice(
            ["Soon has filed a restraining order.", "Every one of those cost a taco. Worth it?", "The van remembers.",
             "Absolutely unhinged. We love to see it."]) + f"\n-# 🧾 Mouth tax: -2 tacos. Tacos: {w.tacobal} 🌮")
    k, kn = _top(await bank.get_house(gid, f"kindnessday:{day}", {}) or {})
    if k:
        w = await bank.add(gid, k, "van report: teacher's pet", tacobal=1)
        lines.append(f"💖 **Teacher's Pet:** <@{k}> with {kn} compliment{_s(kn)}. " + random.choice(
            ["Suspiciously nice. What are you hiding?", "Soon's favorite. Don't tell the others.",
             "Kissing up won't get you tacos. But keep going.", "The van feels seen."])
            + f"\n-# 🌟 Gold star: +1 taco. Tacos: {w.tacobal} 🌮")
    if lines:
        await ch.send(f"## 🚐 The Van Daily Report: {stamp}\n" + "\n".join(lines)
                      + "\n-# Today's stats. Tacos delivered: still 0. Come back tomorrow for more disappointment.")
    results = await bank.day_results(gid, day)
    hi = results[0] if results and results[0][1] > 0 else None
    lo = results[-1] if results and results[-1][1] < 0 else None
    casino = []
    if hi:
        w = await bank.add(gid, hi[0], "casino report: high roller tip", chips=-10)
        casino.append(f"🤩 **High Roller:** <@{hi[0]}> won **{hi[1]} {C}** today. " + random.choice(
            ["Security is reviewing the tapes.", "Suspiciously lucky.", "The manager would like a word.",
             "Casa de Soon wants its chips back."])
            + f"\n-# 🍹 Tipped Soon the cocktail waitress: -10 {C}. Chips: {w.chips} {C}")
    if lo:
        w = await bank.add(gid, lo[0], "casino report: pity comp", chips=25)
        casino.append(f"💸 **Biggest Loser:** <@{lo[0]}> lost **{-lo[1]} {C}** today. " + random.choice(
            ["Casa de Soon thanks you for your service.", "Kor sends his regards (and your chips).",
             "A true patron of the arts.", "We named a slot machine after you."])
            + f"\n-# 💝 Pity comp from the manager: +25 {C}. Chips: {w.chips} {C}")
    if casino:
        await ch.send("### 🎰 Casa de Soon Report\n" + "\n".join(casino), embed=pic("lounge.gif"))
    return bool(lines or casino)
