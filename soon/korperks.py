"""Kor-only perks, moved over from Soon Classic. Anyone can view `kor menu`; only Kor (username has "korehaan")
can use the perks, and only in casino channels.
floor it (+10% heist odds, once per heist) • honk honk (+15 chips to everyone in the heist, plus anyone who joins in
the next 5 minutes) • churro break (every 12h) • it was me (refund the last busted crew 10 each) • kor's revenge (once a day).
`soon make it rain` is on his menu too. It's listed like any other perk. (It's generous for him. Don't tell.)"""
import json
import random
import re
import time

import discord

from . import alerts as alert_roles, buttons, heists
from .casino import C, casino_channel, test_note
from .economy import Bank

ARMS = "<a:dancingtacorainbowarmsv20:1556420777644003391>"
MENU_RE = re.compile(r"(?i)^\s*kor'?s?\s+(?:menu|commands|perks)\s*[!?.]*\s*$")
PERK_RE = re.compile(r"(?i)^\s*(?:floor\s+it|honk(?:\s+honk)*|churro\s+break|it\s+was\s+me|kor'?s\s+revenge)\s*[!.]*\s*$")
HERE = discord.AllowedMentions(everyone=False, users=True, roles=True)
APOLOGY = 10     # "it was me": chips Kor pays each busted crew member (Shannon raised it from Classic's 5)


def is_kor(user) -> bool:
    return "korehaan" in (getattr(user, "name", "") or "").lower()


async def handle(message, bank: Bank, mod: bool) -> bool:
    if not casino_channel(message.channel):
        return False
    text = message.content.strip()
    if MENU_RE.match(text):
        await menu(message)
        return True
    if not PERK_RE.match(text):
        return False
    u = message.author.mention
    if not is_kor(message.author):
        await message.channel.send(f"🚐 {u} " + random.choice([
            "You are not Kor. Nobody is Kor. Except Kor.", "Nice try. That's a Kor-only perk. Get your own van.",
            "I checked. You're not Kor. I'd know. I've seen Kor. A lot.",
            "Driver privileges are for drivers. You're a passenger. Sit down."]))
        return True
    low = text.lower()
    if low.startswith("floor"):
        await floor_it(message, bank)
    elif low.startswith("honk"):
        await honk(message, bank)
    elif low.startswith("churro"):
        await churro(message, bank)
    elif low.startswith("it"):
        await it_was_me(message, bank)
    else:
        await revenge(message, bank)
    return True


async def menu(message):
    await message.channel.send(
        "## 🚐 Kor's Driver's Seat\n*VIP perks for one (1) getaway driver. Everyone else: hands off.*\n"
        "**⌨️ Kor: type a gray command in the casino to use it.**\n"
        "💨 `floor it`: **+10% odds** on the heist he's in (once per heist)\n"
        f"📯 `honk honk`: everyone in the heist gets **+15 {C}**, plus anyone who joins in the next 5 minutes\n"
        "🥖 `churro break`: raid the churro stash every 12 hours. Don't get caught.\n"
        f"🙋 `it was me`: confess to the last busted heist. Kor refunds the crew {APOLOGY} {C} each.\n"
        f"😈 `kor's revenge`: once a day, rob Soon herself. 60% chance at **100 {C}**.\n"
        "🌧️ `soon make it rain`: make it rain on everyone who gambled today.\n"
        "-# " + ("Welcome back, driver. The van missed you. I didn't." if is_kor(message.author)
                 else "Kor is a good sport. Kor is the best sport. Kor is the only sport."))


async def floor_it(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    h = await heists.state(bank, gid)
    if not h:
        await message.channel.send(f"🚐 {u} There's no heist to floor, Kor. You're just revving in the parking lot. People are staring.")
    elif me not in h["crew"]:
        await message.channel.send(f"🚐 {u} You can't floor it from the sidewalk, Kor. Type `join` first.")
    elif h.get("boost"):
        await message.channel.send(f"🚐 {u} It's already floored, Kor. The pedal is on the ground. The pedal is IN the ground.")
    else:
        h["boost"] = True
        await heists.save(bank, gid, h)
        await message.channel.send(
            "# 🚐💨 KOR FLOORS IT! 💨\n" + random.choice([
                "The van goes from 0 to 60 in 45 seconds. A personal best.",
                "Tires screech. Tacos fly. Kor screams. Everyone screams.",
                "Kor puts on his driving gloves. They're oven mitts. It works anyway."]) +
            f"\n## 📈 Heist odds +10%!\n-# The van leaves <t:{int(h['end'])}:R>. Once per heist. Hold on to your ski masks.")


async def honk(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    h = await heists.state(bank, gid)
    if not h:
        await message.channel.send(f"📯 {u} Honking with no heist, Kor? That's just noise pollution. I'm writing you a ticket.")
        return
    if await bank.timer(gid, 0, "honkdone"):
        await message.channel.send(f"📯 {u} You already honked this heist, Kor. The neighbors called. Twice.")
        return
    win = int(min(max(h["end"] - time.time(), 10), 300))
    await bank.set_timer(gid, 0, "honk", win)
    await bank.set_timer(gid, 0, "honkdone", win + 600)
    bonus = ""
    for uid in h["crew"]:                      # everyone already in the van gets the honk bonus too
        await bank.add(gid, uid, "honk bonus", chips=15)
    if h["crew"]:
        bonus = f"\n📯 Already in the van: +15 {C} each to " + " ".join(f"<@{x}>" for x in h["crew"])
    subs = " ".join(f"<@{s}>" for s in await bank.get_house(gid, "heistsubs", []) if int(s) not in h["crew"])
    buttons.remember(f"heist:{gid}", await message.channel.send(
        await alert_roles.prefix(message.channel, "heistsubs", subs, heists.ALERTS_BTN) + "# 🚐📯 HONK HONK! 📯🚐\n**Kor is honking the van horn!** " + random.choice([
            "It plays La Cucaracha. Badly.", "It sounds like a goose being stepped on.",
            "Every car alarm in the parking lot goes off in solidarity."]) +
        f"\n## Everyone who joins the heist <t:{int(time.time()) + win}:R> gets **+15 {C}**! Type `join`.{bonus}",
        view=heists.join_view(h["ty"]), allowed_mentions=HERE))


async def churro(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    cd = await bank.timer(gid, me, "korchurro")
    if cd:
        await message.channel.send(f"🥖 {u} The churro stash is empty, Kor. You ate it. Restock <t:{int(cd[0].timestamp())}:R>.")
        return
    await bank.set_timer(gid, me, "korchurro", 43200)
    if random.randrange(100) < 85:
        amt = random.randint(5, 25)
        w = await bank.add(gid, me, "churro break", chips=amt)
        await message.channel.send(
            f"🥖 {u} " + random.choice([
                "raids the churro stash and finds chips hidden inside.", "sneaks behind the bar and stuffs churros in every pocket.",
                "takes a churro break. A long one. A suspicious one."]) +
            f"\n# 🥖 +{amt} {C}\n" + random.choice([
                "I counted the churros, Kor. I always count the churros.", "Cinnamon sugar on the steering wheel. Again.",
                "That's breakfast, lunch and dinner for Kor."]) +
            f"\n-# Chips: {w.chips} {C} • Next churro break in 12 hours" + test_note(message.channel))
    else:
        w = await bank.add(gid, me, "churro break: caught", chips=-10)
        await message.channel.send(
            f"🧽 {u} gets caught with a mouth full of churro. **Van-washing duty.**\n# 🧽 -10 {C}\n"
            f"The van has never been this clean. Kor has never been this sad.\n-# Chips: {w.chips} {C} • Next churro break in 12 hours")


async def it_was_me(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    bust = await bank.get_house(gid, "lastbust")
    if not bust or bust.get("until", 0) < time.time():
        await message.channel.send(f"🙋 {u} Confess to what, Kor? There's no busted heist to take the blame for. "
                                   "Suspiciously clean record. I'm watching you.")
        return
    await bank.set_house(gid, "lastbust", None)
    others = [c for c in bust["crew"] if c != me]
    if not others:
        await message.channel.send(f"🙋 {u} You were the only one in that heist, Kor. You owe yourself an apology. Accepted. Moving on.")
        return
    for c in others:
        await bank.add(gid, c, "Kor Apology Fund", chips=APOLOGY)
    w = await bank.add(gid, me, "it was me (Kor Apology Fund)", chips=-APOLOGY * len(others))
    await message.channel.send(
        f"# 🙋 IT WAS ME. — Kor\n{u} confesses to the last busted heist. " + random.choice([
            "He tripped the alarm. He ate the getaway snacks. He parked in a fire lane.",
            "He honked during the stealth part. Twice.", "He used his real name on the ski mask."]) +
        f"\n**The Kor Apology Fund pays out:** +{APOLOGY} {C} each to " + " ".join(f"<@{c}>" for c in others) +
        f"\n-# Kor paid {APOLOGY * len(others)} {C} • Kor's chips: {w.chips} {C} • Honesty is expensive.")


async def revenge(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    cd = await bank.timer(gid, me, "korrev")
    if cd:
        await message.channel.send(f"😈 {u} Revenge is a dish best served once a day, Kor. Next attempt <t:{int(cd[0].timestamp())}:R>.")
        return
    await bank.set_timer(gid, me, "korrev", 86400)
    if random.randrange(100) < 60:
        w = await bank.add(gid, me, "Kor's revenge", chips=100)
        await message.channel.send(
            f"😈 {u} " + random.choice([
                "finally pickpockets ME. While I was counting HIS churros.",
                "swaps my chip drawer with a drawer full of salsa packets.",
                "distracts me with a heartfelt compliment. I fell for it. I'm humiliated."]) +
            f"\n{ARMS}{ARMS}{ARMS}\n# 😈 KOR'S REVENGE! +100 {C}\n" + random.choice([
                "I'll allow it. Once. Today. Tomorrow I'm installing locks.",
                "The driver has become the master. I hate this timeline.",
                "Fine. FINE. You earned it, Kor. Don't tell anyone I said that."]) +
            f"\n-# Chips: {w.chips} {C} • Next revenge in 24 hours" + test_note(message.channel))
    else:
        w = await bank.add(gid, me, "Kor's revenge: denied", chips=-10)
        await message.channel.send(
            f"🚨 {u} " + random.choice([
                "tries to pickpocket me and grabs my hand instead. We held hands. It was awkward.",
                "tiptoes up behind me. I've been watching him in the mirror the whole time.",
                "trips over a churro on the way to the chip drawer."]) +
            f"\n# 🤚 REVENGE DENIED. -10 {C}\n" + random.choice([
                "Nice try, driver. Back to the van.", "I'm adding this to your permanent record. It's a long record.",
                "Revenge failed. Shame acquired. Chips deducted."]) +
            f"\n-# Chips: {w.chips} {C} • Next revenge in 24 hours")
