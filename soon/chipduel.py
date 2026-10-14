"""Chip duels, moved over from Soon Classic (separate from the quick-draw `soon duel`).
`duel @name 20` → they `accept` within 5 minutes → spectators get 5 more minutes to `bet 5-25 on @name`
→ Soon flips the taco. Winner takes both stakes; spectators who backed the winner get double.
One duel at a time per server. Stakes and bets are held as soon as they're placed (refunded if it's called off),
so nobody can spend chips they've already put on the table. Duel alerts ping a sign-up list when a duel starts."""
import asyncio
import json
import random
import re
import time

import discord

from . import buttons
from .casino import C, casino_channel, test_note
from .economy import Bank

ARMS = "<a:dancingtacorainbowarmsv20:1556420777644003391>"
WAIT, BETTING, MIN_BET, MAX_BET, MAX_BETS, MAX_STAKE = 300, 300, 5, 25, 6, 100
MAX_SUBS = 40

DUEL_RE = re.compile(r"(?i)^\s*duel\b(?!\s+record)")
ANSWER_RE = re.compile(r"(?i)^\s*(accept|decline)\s*[!.]*\s*$")
BET_RE = re.compile(r"(?i)^\s*bet\s+\d+\s+on\s+<@!?\d+>\s*[!.]*\s*$")
ALERT_RE = re.compile(r"(?i)^\s*duels?\s+(?:alerts?|notif\w*|ping\w*|subscri\w*)\b")
ALERTS_BTN = ("duel alerts toggle", "Duel alerts on/off", "🔔", discord.ButtonStyle.secondary)
_locks: dict[int, asyncio.Lock] = {}


def ids_in(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"<@!?(\d+)>", text)]


async def state(bank: Bank, gid: int) -> dict | None:
    raw = await bank.m.get_kv(f"duel:{gid}")
    return json.loads(raw) if raw else None


async def save(bank: Bank, gid: int, d: dict | None):
    await bank.m.set_kv(f"duel:{gid}", json.dumps(d) if d else "")


def bet_buttons(d: dict, accepted: bool):
    btns = [] if accepted else [("accept", "Accept", "⚔️", discord.ButtonStyle.success),
                                ("decline", "Decline", "🐔", discord.ButtonStyle.danger)]
    btns += [(f"bet 10 on <@{d['c']}>", "Bet 10 on challenger", "🍿", discord.ButtonStyle.primary),
             (f"bet 10 on <@{d['t']}>", "Bet 10 on defender", "🍿", discord.ButtonStyle.primary), ALERTS_BTN]
    return buttons.view(*btns)


async def handle(message, bank: Bank, mod: bool) -> bool:
    if not casino_channel(message.channel):
        return False
    text = message.content.strip()
    gid = message.guild.id
    if ALERT_RE.match(text):
        await alerts(message, bank)
        return True
    if BET_RE.match(text):
        async with _locks.setdefault(gid, asyncio.Lock()):
            await bet(message, bank)
        return True
    if ANSWER_RE.match(text):
        async with _locks.setdefault(gid, asyncio.Lock()):
            return await answer(message, bank, ANSWER_RE.match(text).group(1).lower())
    if DUEL_RE.match(text):
        async with _locks.setdefault(gid, asyncio.Lock()):
            await challenge(message, bank)
        return True
    return False


async def alerts(message, bank: Bank):
    gid, me, u = message.guild.id, str(message.author.id), message.author.mention
    subs = await bank.get_house(gid, "duelsubs", [])
    toggle_off = "toggle" in message.content.lower() and me in subs
    if toggle_off or re.search(r"(?i)\boff\b|\bstop\b|\bno\b|unsub", message.content):
        await bank.set_house(gid, "duelsubs", [s for s in subs if s != me])
        await message.channel.send(f"🔔 {u} Duel alerts **off**. Enjoy missing the bloodshed.")
    elif me in subs:
        await message.channel.send(f"🔔 {u} You're already on the duel list. `duel alerts off` to stop.")
    elif len(subs) >= MAX_SUBS:
        await message.channel.send(f"🔔 {u} The duel list is full ({MAX_SUBS}).")
    else:
        await bank.set_house(gid, "duelsubs", subs + [me])
        await message.channel.send(f"🔔 {u} Duel alerts **on**. I'll tag you whenever a duel starts, so you can bet on it. "
                                   "`duel alerts off` to stop.")


async def challenge(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    d = await state(bank, gid)
    m = message.content.lower()
    if re.search(r"\b(?:cancel|off|stop)\b", m):
        if d and d["c"] == me and d.get("on"):
            await message.channel.send(f"⚔️ {u} They already accepted. It's happening. Kor locked the doors.")
        elif d and d["c"] == me:
            await save(bank, gid, None)
            await refund(bank, gid, d)
            await message.channel.send(f"🐔 {u} calls off the duel. " + random.choice([
                "The crowd boos. The crowd is Kor.", "Chickening out of your own duel. A new low. I'm impressed."])
                + "\n-# Stake and bets refunded.")
        else:
            await message.channel.send(f"⚔️ {u} You don't have a duel to cancel.")
        return
    targets = [t for t in ids_in(message.content) if t != getattr(message.guild.me, "id", 0)]
    if not targets:
        await message.channel.send(
            "## ⚔️ How Duels Work\n1. Challenge someone: `duel @name 20` (bet 1–100 chips each)\n"
            "2. They have 5 minutes to type `accept` (or `decline` like a coward)\n"
            "3. Once accepted, everyone else has **5 minutes to bet** with `bet 10 on @name` (5–25 chips)\n"
            "4. Soon flips the taco. The winner takes both stakes. Spectators who backed the winner get **double** their bet. "
            "The rest lose theirs.\n-# One duel at a time • `duel cancel` calls it off before it's accepted • "
            "`duel alerts on` to get tagged when a duel starts"
            + (f" • Happening now: <@{d['c']}> vs <@{d['t']}>" if d else ""),
            view=buttons.view(ALERTS_BTN))
        return
    t = targets[0]
    member = message.guild.get_member(t)
    if d:
        await message.channel.send(f"⚔️ {u} A duel is already happening: <@{d['c']}> vs <@{d['t']}>. Wait your turn, "
                                   "gladiator. Or bet on it: `bet 10 on @name`.")
        return
    if member is not None and member.bot:
        await message.channel.send(f"⚔️ {u} Duel WHO? `duel @name 20`. Pick a human. I don't lose.")
        return
    if t == me:
        await message.channel.send(f"⚔️ {u} You challenged yourself to a duel. You both lost.")
        return
    num = re.search(r"\d+", re.sub(r"<@!?\d+>", "", m))
    a = max(int(num.group()) if num else 10, 1)
    capped = ""
    if a > MAX_STAKE:
        a, capped = MAX_STAKE, f" (max duel is {MAX_STAKE}, so I made it {MAX_STAKE})"
    tc = (await bank.get(gid, t)).chips
    if tc < a:
        await message.channel.send(f"⚔️ {u} <@{t}> only has {tc} {C}. Pick on someone your own size. Or `tip` them first.")
        return
    if await bank.pay(gid, me, a, "duel stake") is None:
        have = (await bank.get(gid, me)).chips
        await message.channel.send(f"⚔️ {u} You have {have} {C}. You can't duel for {a}. Brave. Broke. Mostly broke.")
        return
    d = {"c": me, "t": t, "a": a, "on": False, "bets": [], "until": time.time() + WAIT, "channel": message.channel.id}
    await save(bank, gid, d)
    subs = " ".join(f"<@{s}>" for s in await bank.get_house(gid, "duelsubs", []) if int(s) not in (me, t))
    await message.channel.send(
        (f"🔔 {subs}\n" if subs else "") +
        f"# ⚔️🤺⚔️ DUEL! ⚔️🤺⚔️\n{u} challenges <@{t}> to a **taco toss** for **{a} {C}** each!{capped}\n"
        f"## <@{t}> type `accept` or `decline`\nThe challenge expires <t:{int(d['until'])}:R>.\n"
        f"🍿 **Everyone else:** `bet {MIN_BET}-{MAX_BET} on @name` to back a fighter. Winners get double. "
        "Betting stays open 5 more minutes after they accept.\n"
        f"-# Pot: {a * 2} {C} • The taco decides. The taco is never wrong.",
        view=bet_buttons(d, False))


async def answer(message, bank: Bank, word: str) -> bool:
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    d = await state(bank, gid)
    from_button = isinstance(message, buttons.ButtonMessage)
    if not d:
        if from_button:
            await message.channel.send(f"⚔️ {u} That duel is over.")
        return from_button
    if word == "accept":
        if me == d["c"]:
            await message.channel.send(f"⚔️ {u} You can't accept your own duel. That's just standing in a field alone.")
        elif me == d["t"] and d["on"]:
            await message.channel.send(f"⚔️ {u} You already accepted. The taco flips <t:{int(d['until'])}:R>. Stretch. Hydrate. Pray.")
        elif me == d["t"]:
            if await bank.pay(gid, me, d["a"], "duel stake") is None:
                have = (await bank.get(gid, me)).chips
                await message.channel.send(f"⚔️ {u} You need {d['a']} {C} to accept and you have {have}. `buy chips`, fast.")
                return True
            d["on"], d["until"] = True, time.time() + BETTING
            await save(bank, gid, d)
            await message.channel.send(
                f"# ⚔️ DUEL ACCEPTED! ⚔️\n<@{d['c']}> vs {u} for **{d['a']} {C}** each. " + random.choice([
                    "Brave. Foolish. Mostly foolish.", "Somebody call a medic. Or Kor. Kor is not a medic.",
                    "The crowd gasps. The crowd is three people and a raccoon."]) +
                f"\n## 🍿 Bets are open for 5 more minutes!\n`bet {MIN_BET}-{MAX_BET} on @name` to back a fighter. "
                f"Winners get double. The taco flips <t:{int(d['until'])}:R>.\n-# Bets so far: {len(d['bets'])}/{MAX_BETS}",
                view=bet_buttons(d, True))
        elif from_button:
            await message.channel.send(f"⚔️ {u} This isn't your duel to accept. Bet on it instead.")
        else:
            return False            # someone just said "accept" in chat
        return True
    # decline
    if me == d["t"] and d["on"]:
        await message.channel.send(f"⚔️ {u} Too late. You already accepted. No backing out now. Kor locked the doors.")
    elif me == d["t"]:
        await save(bank, gid, None)
        await refund(bank, gid, d)
        await message.channel.send(f"🐔 {u} declines the duel from <@{d['c']}>. " + random.choice([
            "Bawk bawk.", "Coward. Smart coward, but coward.", "Running away is also a strategy. A bad one. But a strategy."])
            + "\n-# Duel off. Stakes and bets refunded.")
    elif me == d["c"]:
        await message.channel.send(f"⚔️ {u} You started it. Type `duel cancel` to chicken out properly.")
    elif from_button:
        await message.channel.send(f"⚔️ {u} This isn't your duel to decline.")
    else:
        return False
    return True


async def bet(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    d = await state(bank, gid)
    if not d:
        await message.channel.send(f"🍿 {u} There's no duel to bet on. Start one: `duel @name 20`.")
        return
    t = ids_in(message.content)[0]
    side = "c" if t == d["c"] else "t" if t == d["t"] else ""
    num = re.search(r"\d+", re.sub(r"<@!?\d+>", "", message.content))
    n = min(max(int(num.group()) if num else MIN_BET, MIN_BET), MAX_BET)
    if me in (d["c"], d["t"]):
        await message.channel.send(f"🍿 {u} You're IN the duel. You can't bet on it. That's called match fixing. I'd know.")
    elif not side:
        await message.channel.send(f"🍿 {u} That person isn't in this duel. Bet on <@{d['c']}> or <@{d['t']}>.")
    elif any(b["u"] == me for b in d["bets"]):
        await message.channel.send(f"🍿 {u} You already placed a bet. One per customer. Greed is my job.")
    elif len(d["bets"]) >= MAX_BETS:
        await message.channel.send(f"🍿 {u} The betting window is full. Six gamblers max. Sit down and watch.")
    elif await bank.pay(gid, me, n, "duel bet") is None:
        have = (await bank.get(gid, me)).chips
        await message.channel.send(f"🍿 {u} You have {have} {C}. You can't bet {n}. Bet less or `buy chips`.")
    else:
        d["bets"].append({"u": me, "side": side, "n": n})
        await save(bank, gid, d)
        pot = d["a"] * 2 + sum(b["n"] for b in d["bets"])
        await message.channel.send(
            f"🍿 {u} bets **{n} {C}** on <@{t}>. " + random.choice([
                "Bold choice.", "Interesting. Wrong, probably, but interesting.", "I'll remember this.", "The crowd goes mild."]) +
            f"\n-# Total on the table: {pot} {C} • Bets: {len(d['bets'])}/{MAX_BETS} • Back the winner = double your bet")


async def refund(bank: Bank, gid: int, d: dict):
    await bank.add(gid, d["c"], "duel refund", chips=d["a"])
    if d["on"]:
        await bank.add(gid, d["t"], "duel refund", chips=d["a"])
    for b in d["bets"]:
        await bank.add(gid, b["u"], "duel bet refund", chips=b["n"])


# ---------- the clock (called every few seconds from bot.py) ----------

async def tick(client: discord.Client, bank: Bank):
    for guild in client.guilds:
        d = await state(bank, guild.id)
        if not d or time.time() < d["until"]:
            continue
        await save(bank, guild.id, None)
        ch = guild.get_channel(d["channel"])
        if not d["on"]:
            await refund(bank, guild.id, d)
            if ch:
                await ch.send(f"🐔 **Duel cancelled.** <@{d['t']}> never showed up. <@{d['c']}> wins by forfeit of courage. "
                              "Stake and bets refunded.")
        elif ch:
            asyncio.create_task(fight(ch, bank, guild.id, d))


async def fight(ch, bank: Bank, gid: int, d: dict):
    c, t, a = d["c"], d["t"], d["a"]
    w, l = (c, t) if random.randrange(2) else (t, c)
    side = "c" if w == c else "t"
    await bank.add(gid, w, "duel win", chips=a * 2)
    lines = ""
    for b in d["bets"]:
        if b["side"] == side:
            await bank.add(gid, b["u"], "duel bet win", chips=b["n"] * 2)
            lines += f"\n✅ <@{b['u']}> +{b['n']}"
        else:
            lines += f"\n❌ <@{b['u']}> -{b['n']}"
    msg = await ch.send(f"⚔️🤺⚔️ **BETTING IS CLOSED** • <@{c}> vs <@{t}> for **{a} {C}** each\n"
                        "🌮 Soon flips the taco... it spins... it spins... Kor is crying...")
    await asyncio.sleep(3)
    await msg.edit(content=f"⚔️🤺⚔️ **THE DUEL** • <@{c}> vs <@{t}>\n{ARMS}{ARMS}{ARMS}\n# 🏆 <@{w}> WINS +{a} {C}\n"
                           f"💀 <@{l}> loses {a} {C}. " + random.choice([
                               "Shameful. Stunning. Iconic.", "Thoughts and prayers. Mostly thoughts.",
                               "That's going on the casino wall of shame. We don't have one. We do now.", "The taco has spoken."])
                           + (f"\n\n**🍿 Spectator bets** (winners doubled):{lines}" if lines else "") + test_note(ch),
                   view=buttons.view(ALERTS_BTN))
