"""Duels: Soon Classic's betting (stakes, spectator bets) with a quick-draw fight instead of a taco flip.
`duel @name 20` → they `accept` within 5 minutes → spectators get 2 minutes to `bet 5-25 on @name`
→ 10-second warning (the channel pauses: other messages get swept until the fight ends)
→ WAIT... DRAW! The first fighter to tap wins (tap early = misfire = you lose). Winner takes both stakes;
spectators who backed the winner get double. Nobody taps within 20s of DRAW = everything refunded.
One duel at a time per server. Stakes and bets are held as soon as they're placed (refunded if it's called off),
so nobody can spend chips they've already put on the table. Duel alerts ping a sign-up list when a duel starts.
Double or Nothing: after a duel, both fighters have 60 seconds to press it. If both do, round 2 runs at double stakes,
betting reopens for 2 minutes at a flat 20 chips a bet (winners doubled). Once per duel."""
import asyncio
import json
import random
import re
import time

import discord

from . import buttons
from .casino import C, casino_channel, test_note
from .duel import DrawView
from .economy import Bank

ARMS = "<a:dancingtacorainbowarmsv20:1556420777644003391>"
WAIT, BETTING, MIN_BET, MAX_BET, MAX_BETS, MAX_STAKE = 300, 120, 5, 25, 6, 100
DON_WAIT, DON_BETTING, DON_BET = 60, 120, 20      # double or nothing: decide window, betting window, flat bet
MAX_SUBS = 40
WARNING = 10                  # seconds of heads-up before the fight

DUEL_RE = re.compile(r"(?i)^\s*duel\b(?!\s+record)")
ANSWER_RE = re.compile(r"(?i)^\s*(accept|decline)\s*[!.]*\s*$")
BET_RE = re.compile(r"(?i)^\s*bet\s+\d+\s+on\s+<@!?\d+>\s*[!.]*\s*$")
ALERT_RE = re.compile(r"(?i)^\s*duels?\s+(?:alerts?|notif\w*|ping\w*|subscri\w*)\b")
DON_RE = re.compile(r"(?i)^\s*(?:double\s+or\s+nothing|don)\s*[!.?]*\s*$")
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
    n = DON_BET if d.get("round") == 2 else MAX_BET     # one tap = the max bet
    btns += [(f"bet {n} on <@{d['c']}>", f"Bet {n} on challenger", "🍿", discord.ButtonStyle.primary),
             (f"bet {n} on <@{d['t']}>", f"Bet {n} on defender", "🍿", discord.ButtonStyle.primary), ALERTS_BTN]
    return buttons.view(*btns)


async def handle(message, bank: Bank, mod: bool) -> bool:
    if not casino_channel(message.channel):
        return False
    text = message.content.strip()
    gid = message.guild.id
    if ALERT_RE.match(text):
        await alerts(message, bank)
        return True
    if DON_RE.match(text):
        async with _locks.setdefault(gid, asyncio.Lock()):
            return await double_or_nothing(message, bank)
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
        if d and d.get("stage") == "don":
            await message.channel.send(f"⚔️ {u} The Double or Nothing offer is still open. Just don't press it.")
        elif d and d.get("stage") == "fighting":
            await message.channel.send(f"⚔️ {u} Too late. Hands on holsters.")
        elif d and d["c"] == me and d.get("on"):
            await message.channel.send(f"⚔️ {u} They already accepted. It's happening. Kor locked the doors.")
        elif d and d["c"] == me:
            await save(bank, gid, None)
            await buttons.retire(f"duel:{gid}"); await buttons.retire(f"don:{gid}")
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
            "3. Once accepted, everyone else has **2 minutes to bet** with `bet 25 on @name` (5–25 chips)\n"
            "4. Quick-draw: when the button turns red and says **DRAW!**, tap it first. Tap early and you misfire. The winner takes both stakes. Spectators who backed the winner get **double** their bet. "
            "The rest lose theirs.\n-# One duel at a time • `duel cancel` calls it off before it's accepted • "
            "`duel alerts on` to get tagged when a duel starts"
            + (f" • Happening now: <@{d['c']}> vs <@{d['t']}>" if d else ""),
            view=buttons.view(ALERTS_BTN))
        return
    t = targets[0]
    member = message.guild.get_member(t)
    if d and d.get("stage") == "don":
        await message.channel.send(f"⚔️ {u} <@{d['c']}> and <@{d['t']}> are deciding on Double or Nothing. Give them a minute.")
        return
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
    buttons.remember(f"duel:{gid}", await message.channel.send(
        (f"🔔 {subs}\n" if subs else "") +
        f"# ⚔️🤺⚔️ DUEL! ⚔️🤺⚔️\n{u} challenges <@{t}> to a **quick-draw duel** for **{a} {C}** each!{capped}\n"
        f"## <@{t}> type `accept` or `decline`\nThe challenge expires <t:{int(d['until'])}:R>.\n"
        f"🍿 **Everyone else:** `bet {MIN_BET}-{MAX_BET} on @name` to back a fighter. Winners get double. "
        "Betting stays open 2 minutes after they accept.\n"
        f"-# Pot: {a * 2} {C} • Fastest finger wins. Tap before DRAW and you lose.",
        view=bet_buttons(d, False)))


async def answer(message, bank: Bank, word: str) -> bool:
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    d = await state(bank, gid)
    from_button = isinstance(message, buttons.ButtonMessage)
    if not d:
        if from_button:
            await message.channel.send(f"⚔️ {u} That duel is over.")
        return from_button
    if d.get("stage") in ("don", "fighting"):
        return False
    if word == "accept":
        if me == d["c"]:
            await message.channel.send(f"⚔️ {u} You can't accept your own duel. That's just standing in a field alone.")
        elif me == d["t"] and d["on"]:
            await message.channel.send(f"⚔️ {u} You already accepted. The draw starts <t:{int(d['until'])}:R>. Stretch. Hydrate. Pray.")
        elif me == d["t"]:
            if await bank.pay(gid, me, d["a"], "duel stake") is None:
                have = (await bank.get(gid, me)).chips
                await message.channel.send(f"⚔️ {u} You need {d['a']} {C} to accept and you have {have}. `buy chips`, fast.")
                return True
            d["on"], d["until"] = True, time.time() + BETTING
            await save(bank, gid, d)
            await buttons.retire(f"duel:{gid}")         # Accept/Decline are done
            buttons.remember(f"duel:{gid}", await message.channel.send(
                f"# ⚔️ DUEL ACCEPTED! ⚔️\n<@{d['c']}> vs {u} for **{d['a']} {C}** each. " + random.choice([
                    "Brave. Foolish. Mostly foolish.", "Somebody call a medic. Or Kor. Kor is not a medic.",
                    "The crowd gasps. The crowd is three people and a raccoon."]) +
                f"\n## 🍿 Bets are open for 2 minutes!\n`bet {MIN_BET}-{MAX_BET} on @name` to back a fighter. "
                f"Winners get double. The draw starts <t:{int(d['until'])}:R>.\n-# Bets so far: {len(d['bets'])}/{MAX_BETS}",
                view=bet_buttons(d, True)))
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
        await buttons.retire(f"duel:{gid}"); await buttons.retire(f"don:{gid}")
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
    if d.get("stage") == "don":
        await message.channel.send(f"🍿 {u} Hold on. The fighters are deciding on Double or Nothing. Bets reopen if they both go for it.")
        return
    if d.get("stage") == "fighting":
        await message.channel.send(f"🍿 {u} Betting is closed. Hands on holsters.")
        return
    t = ids_in(message.content)[0]
    side = "c" if t == d["c"] else "t" if t == d["t"] else ""
    num = re.search(r"\d+", re.sub(r"<@!?\d+>", "", message.content))
    n = min(max(int(num.group()) if num else MIN_BET, MIN_BET), MAX_BET)
    if d.get("round") == 2:
        n = DON_BET                      # double-or-nothing round: every bet is a flat 20
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
        ch = guild.get_channel(d["channel"])
        if d.get("stage") == "fighting":
            if time.time() > d["until"] + 120:       # Soon restarted mid-draw: give everything back
                await save(bank, guild.id, None)
                await buttons.retire(f"duel:{guild.id}"); await buttons.retire(f"don:{guild.id}")
                await refund(bank, guild.id, d)
                if ch:
                    await ch.send(f"⚠️ The duel between <@{d['c']}> and <@{d['t']}> got interrupted. Stakes and bets refunded.")
            continue
        if d["on"] and d.get("stage") != "don" and ch:
            d["stage"] = "fighting"
            await save(bank, guild.id, d)
            asyncio.create_task(fight(ch, bank, guild.id, d))
            continue
        await save(bank, guild.id, None)
        await buttons.retire(f"duel:{guild.id}"); await buttons.retire(f"don:{guild.id}")
        if d.get("stage") == "don":
            for uid in d["don"]:
                await bank.add(guild.id, uid, "double or nothing refund", chips=d["a"])
            if ch and d["don"]:
                yes = " ".join(f"<@{x}>" for x in d["don"])
                no = " ".join(f"<@{x}>" for x in (d["c"], d["t"]) if x not in d["don"])
                await ch.send(f"🐔 {yes} wanted **Double or Nothing**. {no} walked away. "
                              + random.choice(["Smart. Boring, but smart.", "The taco remembers cowardice.",
                                               "Fine. Keep your chips. Keep your shame too."])
                              + f"\n-# {yes}: double stake refunded.")
        elif not d["on"]:
            await refund(bank, guild.id, d)
            if ch:
                await ch.send(f"🐔 **Duel cancelled.** <@{d['t']}> never showed up. <@{d['c']}> wins by forfeit of courage. "
                              "Stake and bets refunded.")



class Fighter:
    def __init__(self, uid: int):
        self.id = uid


async def fight(ch, bank: Bank, gid: int, d: dict):
    """The quick-draw: WAIT... then DRAW! First fighter to tap wins. Tapping early is a misfire (you lose)."""
    c, t, a = d["c"], d["t"], d["a"]
    r2 = d.get("round") == 2
    await buttons.retire(f"duel:{gid}")                  # betting is closed
    buttons.PAUSED.add(ch.id)
    try:
        await ch.send(f"# ⏳ DUEL IN {WARNING} SECONDS\n<@{c}> <@{t}> fingers on the screen. Watch for the button.\n"
                      f"-# 🤫 Channel paused until the duel ends. Anything else posted now gets swept.")
        await asyncio.sleep(WARNING)
        await _fight(ch, bank, gid, d)
    finally:
        buttons.PAUSED.discard(ch.id)


async def _fight(ch, bank: Bank, gid: int, d: dict):
    c, t, a = d["c"], d["t"], d["a"]
    r2 = d.get("round") == 2
    head = (("🎲 **DOUBLE OR NOTHING** • " if r2 else "") +
            f"⚔️🤺⚔️ **BETTING IS CLOSED** • <@{c}> vs <@{t}> for **{a} {C}** each\n")
    draw = DrawView(Fighter(c), Fighter(t))
    msg = await ch.send(head + "## When the button turns red and says DRAW, tap it first. Tap early and you misfire.\n# Ready...",
                        view=draw)
    wait = random.uniform(3, 10)
    if random.random() < 0.35:                       # fake-out
        try:
            await asyncio.wait_for(draw.done.wait(), timeout=wait * 0.5)
        except asyncio.TimeoutError:
            await msg.edit(content=head + "# DR... no. Not yet. 🙂")
        wait *= 0.6
    if not draw.done.is_set():
        try:
            await asyncio.wait_for(draw.done.wait(), timeout=wait)
        except asyncio.TimeoutError:
            await draw.go_live(msg)
            try:
                await asyncio.wait_for(draw.done.wait(), timeout=20)
            except asyncio.TimeoutError:
                await save(bank, gid, None)
                await refund(bank, gid, d)
                await msg.edit(content=head + "# 💤 Nobody drew. You're both cowards.\n-# Stakes and bets refunded.", view=None)
                return
    w = draw.winner.id
    l = t if w == c else c
    side = "c" if w == c else "t"
    await bank.add(gid, w, "duel win", chips=a * 2)
    lines = ""
    for bt in d["bets"]:
        if bt["side"] == side:
            await bank.add(gid, bt["u"], "duel bet win", chips=bt["n"] * 2)
            lines += f"\n✅ <@{bt['u']}> +{bt['n']}"
        else:
            lines += f"\n❌ <@{bt['u']}> -{bt['n']}"
    ww, wl = await record(bank, gid, w, won=True)
    lw, ll = await record(bank, gid, l, won=False)
    how = (f"💥 <@{l}> drew too early. **Misfire.** Humiliating." if draw.misfire else "⚡ Fastest hand in the van.")
    await msg.edit(content=f"⚔️🤺⚔️ **THE DUEL** • <@{c}> vs <@{t}>\n{ARMS}{ARMS}{ARMS}\n# 🏆 <@{w}> WINS +{a} {C}\n"
                           f"{how}\n💀 <@{l}> loses {a} {C}. " + random.choice([
                               "Shameful. Stunning. Iconic.", "Thoughts and prayers. Mostly thoughts.",
                               "That's going on the casino wall of shame. We don't have one. We do now.",
                               "Slow hands. Slower brain."])
                           + (f"\n\n**🍿 Spectator bets** (winners doubled):{lines}" if lines else "")
                           + f"\n-# Duel record: <@{w}> {ww}-{wl} • <@{l}> {lw}-{ll}" + test_note(ch)
                           + ("" if r2 else f"\n\n🎲 <@{c}> <@{t}> **Double or Nothing?** Both press it within 60 seconds "
                              f"for a rematch at **{a * 2} {C}** each. Bets reopen at {DON_BET} {C}."),
                   view=buttons.view(ALERTS_BTN) if r2 else buttons.view(
                       ("double or nothing", "Double or Nothing", "🎲", discord.ButtonStyle.danger), ALERTS_BTN))
    if not r2:
        buttons.remember(f"don:{gid}", msg)
    if r2:
        await save(bank, gid, None)
    else:                                            # open the double-or-nothing window
        await save(bank, gid, {"c": c, "t": t, "a": a * 2, "stage": "don", "don": [], "bets": [], "on": True,
                               "round": 2, "until": time.time() + DON_WAIT, "channel": ch.id})


async def record(bank: Bank, gid: int, uid: int, won: bool) -> tuple[int, int]:
    """Win-loss record (same key the old Quick-Draw used, so old records carry over)."""
    raw = await bank.m.get_kv(f"duel:{gid}:{uid}") or "0,0"
    w, l = (int(x) for x in raw.split(","))
    w, l = (w + 1, l) if won else (w, l + 1)
    await bank.m.set_kv(f"duel:{gid}:{uid}", f"{w},{l}")
    return w, l


async def double_or_nothing(message, bank: Bank) -> bool:
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    d = await state(bank, gid)
    if not d or d.get("stage") != "don":
        if isinstance(message, buttons.ButtonMessage):
            await message.channel.send(f"🎲 {u} That Double or Nothing is over. One per duel.")
            return True
        return False
    if me not in (d["c"], d["t"]):
        await message.channel.send(f"🎲 {u} Only the two fighters get to double down. You can bet when they do.")
        return True
    if me in d["don"]:
        await message.channel.send(f"🎲 {u} You're already in. Waiting on the other one to grow a spine.")
        return True
    if await bank.pay(gid, me, d["a"], "double or nothing stake") is None:
        have = (await bank.get(gid, me)).chips
        await message.channel.send(f"🎲 {u} Double or Nothing costs {d['a']} {C} and you have {have}. Brave idea. No money.")
        return True
    d["don"].append(me)
    if len(d["don"]) < 2:
        await save(bank, gid, d)
        other = d["t"] if me == d["c"] else d["c"]
        await message.channel.send(f"🎲 {u} wants **Double or Nothing** for **{d['a']} {C}**! <@{other}>, press it or "
                                   f"live with it. <t:{int(d['until'])}:R>.")
        return True
    d.update(stage="", until=time.time() + DON_BETTING)
    await save(bank, gid, d)
    await buttons.retire(f"don:{gid}")
    subs = " ".join(f"<@{s}>" for s in await bank.get_house(gid, "duelsubs", []) if int(s) not in (d["c"], d["t"]))
    buttons.remember(f"duel:{gid}", await message.channel.send(
        (f"🔔 {subs}\n" if subs else "") +
        f"# 🎲 DOUBLE OR NOTHING! 🎲\n<@{d['c']}> vs <@{d['t']}> for **{d['a']} {C}** each. " + random.choice([
            "Nobody learned anything. I love it.", "Greed: the family business.", "Kor is hiding behind the van."]) +
        f"\n## 🍿 Bets reopen for 2 minutes: **{DON_BET} {C}** a bet, winners get double!\n"
        f"`bet {DON_BET} on @name` or use the buttons. The draw starts <t:{int(d['until'])}:R>.",
        view=bet_buttons(d, True)))
    return True
