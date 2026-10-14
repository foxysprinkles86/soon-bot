"""Heists, moved over from Soon Classic: the Vault Heist and the Grand Heist.
One heist at a time per server. Someone starts it (pays the buy-in), others `join` (or press Join) within
10/15 minutes, a 5-minute warning goes out, then the van leaves and everyone wins or gets busted together.
The heist is saved in the database, so it still finishes if Soon restarts in the middle."""
import asyncio
import json
import random
import re
import time

import discord

from . import buttons
from .casino import C, DANCE, casino_channel, pic, test_note
from .economy import Bank

ARMS = "<a:dancingtacorainbowarmsv20:1556420777644003391>"
PLANS = {
    "v": {"n": "Vault Heist", "buy": 15, "win": 35, "base": 30, "tot": 600, "cd": 3600, "ck": "heistcd",
          "tgt": "the Taco Vault"},
    "g": {"n": "Grand Heist", "buy": 50, "win": 500, "base": 10, "tot": 900, "cd": 43200, "ck": "gheistcd",
          "tgt": "the Casa de Soon Reserve"},
}
SEATS, MAX_ODDS, MAX_SUBS = 7, 80, 40
HOUSE = 0      # timers on user 0 = server-wide cooldowns
HERE = discord.AllowedMentions(everyone=True, users=True, roles=False)   # heists ping @here, like Classic

ALERT_RE = re.compile(r"(?i)^\s*heists?\s+(?:alerts?|notif\w*|ping\w*|subscri\w*)\b.*$")
JOIN_RE = re.compile(r"(?i)^\s*join(?:\s+(?:the\s+)?heist)?\s*[!.]*\s*$")
START_RE = re.compile(r"(?i)^\s*(?:heist\s+)?(?:vault|grand)(?:\s+heist)?\s*[!.]*\s*$|^\s*heist\s+(?:go|start)\s*[!.]*\s*$|^\s*go\s*[!.]*\s*$")
BOARD_RE = re.compile(r"(?i)^\s*heists?\s*(?:board|menu|status)?\s*[!?.]*\s*$")

_locks: dict[int, asyncio.Lock] = {}


def lock(gid: int) -> asyncio.Lock:
    return _locks.setdefault(gid, asyncio.Lock())


def odds(plan: dict, crew: int, boost: bool) -> int:
    o = min(plan["base"] + crew * 10, MAX_ODDS)
    return o + 10 if boost else o


async def state(bank: Bank, gid: int) -> dict | None:
    raw = await bank.m.get_kv(f"heist:{gid}")
    return json.loads(raw) if raw else None


async def save(bank: Bank, gid: int, h: dict | None):
    await bank.m.set_kv(f"heist:{gid}", json.dumps(h) if h else "")


ALERTS_BTN = ("heist alerts toggle", "Heist alerts on/off", "🔔", discord.ButtonStyle.secondary)


def join_view(ty: str) -> discord.ui.View:
    return buttons.view(("join", "Join the heist", "🦹", discord.ButtonStyle.success), ALERTS_BTN)


def alerts_view() -> discord.ui.View:
    return buttons.view(ALERTS_BTN)


async def handle(message: discord.Message, bank: Bank, mod: bool) -> bool:
    if not casino_channel(message.channel):
        return False
    text = message.content.strip()
    in_casa = "casa" in (getattr(message.channel, "name", "") or "").lower()
    if ALERT_RE.match(text):
        await alerts(message, bank)
    elif JOIN_RE.match(text):
        async with lock(message.guild.id):
            await join(message, bank)
    elif START_RE.match(text) and (in_casa or not re.match(r"(?i)^\s*go\s*[!.]*\s*$", text)):
        async with lock(message.guild.id):
            await start(message, bank, "g" if "grand" in text.lower() else "v")
    elif BOARD_RE.match(text):
        await board(message, bank)
    else:
        return False
    return True


async def alerts(message, bank: Bank):
    gid, me, u = message.guild.id, str(message.author.id), message.author.mention
    subs = await bank.get_house(gid, "heistsubs", [])
    toggle_off = "toggle" in message.content.lower() and me in subs     # the button flips it
    if toggle_off or re.search(r"(?i)\boff\b|\bstop\b|\bno\b|unsub", message.content):
        await bank.set_house(gid, "heistsubs", [s for s in subs if s != me])
        await message.channel.send(f"🔔 {u} Heist alerts **off**. You'll miss everything.")
    elif me in subs:
        await message.channel.send(f"🔔 {u} You're already on the heist list. I'll tag you. Loudly. `heist alerts off` to stop.")
    elif len(subs) >= MAX_SUBS:
        await message.channel.send(f"🔔 {u} List is full ({MAX_SUBS}).")
    else:
        await bank.set_house(gid, "heistsubs", subs + [me])
        await message.channel.send(f"🔔 {u} Heist alerts **on**. I'll tag you by name every time a heist starts. "
                                   "`heist alerts off` to stop.")


async def start(message, bank: Bank, ty: str):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    p = PLANS[ty]
    h = await state(bank, gid)
    if h:
        await message.channel.send(f"🦹 {u} A heist is already running. Type `join`. The van leaves <t:{int(h['end'])}:R>.",
                                   view=join_view(h["ty"]))
        return
    cd = await bank.timer(gid, HOUSE, p["ck"])
    if cd:
        await message.channel.send(f"🦹 {u} The cops are still circling from the last {p['n']}. "
                                   f"Next one <t:{int(cd[0].timestamp())}:R>.")
        return
    if await bank.pay(gid, uid, p["buy"], f"{p['n']} buy-in") is None:
        have = (await bank.get(gid, uid)).chips
        await message.channel.send(f"🦹 {u} The {p['n']} buy-in is {p['buy']} {C} and you have {have}. Try `buy chips`.")
        return
    end = time.time() + p["tot"]
    await save(bank, gid, {"ty": ty, "crew": [uid], "end": end, "warned": False, "channel": message.channel.id,
                           "boost": False})
    subs = " ".join(f"<@{s}>" for s in await bank.get_house(gid, "heistsubs", []) if s != str(uid))
    await message.channel.send(embed=pic("heist-start.gif"))
    if ty == "g":
        head = (f"# 💰 GRAND HEIST ALERT! 💰\n{u} is planning the job of the century: the **Casa de Soon Reserve**. "
                "Kor is driving.\n## ⏰ 15 MINUTES TO JOIN • Type `join`")
    else:
        head = (f"# 🦹 HEIST ALERT! 🦹\n{u} is planning to rob the **Taco Vault**. Kor is driving the getaway van. "
                "That's already a problem.\n## ⏰ 10 MINUTES TO JOIN • Type `join`")
    await message.channel.send(
        "@here" + (f" 🔔 {subs}" if subs else "") + "\n" + head +
        f"\n# 🚐 The van leaves <t:{int(end)}:R>\n## 📣 @mention your friends to join! Every new crew member = +10% odds\n"
        f"💰 Buy-in: {p['buy']} {C} • Success pays **{p['win']} {C} to EVERYONE**\n"
        f"📊 Odds: {odds(p, 1, False)}% solo, +10% for every crew member (max {MAX_ODDS}%) • Van seats {SEATS}\n"
        f"-# {'One Grand Heist every 12 hours.' if ty == 'g' else 'One Vault Heist per hour.'} "
        "`heist alerts on` to get tagged next time.",
        view=join_view(ty), allowed_mentions=HERE)


async def join(message, bank: Bank):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    h = await state(bank, gid)
    if not h:
        await message.channel.send(f"🦹 {u} There's no heist going right now. Type `heist` to see your options.")
        return
    p = PLANS[h["ty"]]
    if uid in h["crew"]:
        await message.channel.send(f"🦹 {u} You're already in the crew. The van leaves <t:{int(h['end'])}:R>.")
        return
    if len(h["crew"]) >= SEATS:
        await message.channel.send(f"🦹 {u} The van is full. Seven seats, seven idiots. Kor says you can ride on the roof next time.")
        return
    w = await bank.pay(gid, uid, p["buy"], f"{p['n']} buy-in")
    if w is None:
        have = (await bank.get(gid, uid)).chips
        await message.channel.send(f"🦹 {u} The buy-in is {p['buy']} {C} and you have {have}. "
                                   "The crew doesn't do IOUs. Try `buy chips`.")
        return
    honk = 15 if await bank.timer(gid, HOUSE, "honk") else 0      # Kor's "honk honk" perk
    if honk:
        w = await bank.add(gid, uid, "honk bonus", chips=honk)
    h["crew"].append(uid)
    await save(bank, gid, h)
    o = odds(p, len(h["crew"]), h.get("boost"))
    if "korehaan" in (message.author.name or "").lower():
        line = "**The driver has arrived.** Everyone buckle up. No, seriously."
    else:
        line = random.choice(["squeezes into the getaway van!", "joins the crew!",
                              "is in. Kor hands them a ski mask. It's used.", "climbs in the back with the taco sacks."])
    await message.channel.send(
        f"🦹 {u} {line}" + (f" 📯 **Honk bonus: +{honk} {C}!**" if honk else "") +
        f"\n### {p['n']} • Crew: {len(h['crew'])} • Odds: {o}%{' (MAX!)' if o >= MAX_ODDS else ''}"
        f"{' 🚐💨' if h.get('boost') else ''} • Seats left: {SEATS - len(h['crew'])} • Van leaves <t:{int(h['end'])}:R>\n"
        + ("📣 @mention more friends to raise the odds!\n" if o < MAX_ODDS else "")
        + f"-# Buy-in: -{p['buy']} {C} • Chips: {w.chips} {C}",
        view=join_view(h["ty"]) if len(h["crew"]) < SEATS else None)


async def board(message, bank: Bank):
    gid = message.guild.id
    h = await state(bank, gid)
    lines = ["## 🦹 The Heist Board"]
    btns = []
    for ty in ("v", "g"):
        p = PLANS[ty]
        lines.append(f"{'🏦' if ty == 'v' else '💰'} **{p['n']}** • {p['buy']} {C} buy-in • pays **{p['win']} {C}** each • "
                     f"{odds(p, 1, False)}% solo, +10% per crew (max {MAX_ODDS}%)")
        if h and h["ty"] == ty:
            lines.append(f"🚨 **Running now!** Type `join`. Van leaves <t:{int(h['end'])}:R>")
            btns.append(("join", "Join the heist", "🦹", discord.ButtonStyle.success))
        else:
            cd = await bank.timer(gid, HOUSE, p["ck"])
            if cd:
                lines.append(f"⏳ Next one <t:{int(cd[0].timestamp())}:R>")
            else:
                word = "vault" if ty == "v" else "grand"
                lines.append(f"✅ **Ready!** Type `{word}` to start")
                if not h:
                    btns.append((word, f"Start {p['n']}", "🏦" if ty == "v" else "💰", discord.ButtonStyle.primary))
    subs = await bank.get_house(gid, "heistsubs", [])
    lines.append(f"🔔 `heist alerts on`: get tagged when any heist starts ({len(subs)} on the list)")
    await message.channel.send("\n".join(lines), view=buttons.view(*btns, ALERTS_BTN))


# ---------- the clock: warnings and getaways (runs every few seconds from bot.py) ----------

async def tick(client: discord.Client, bank: Bank):
    for guild in client.guilds:
        h = await state(bank, guild.id)
        if not h:
            continue
        ch = guild.get_channel(h["channel"])
        now = time.time()
        if ch is None:
            continue
        if now >= h["end"]:
            await save(bank, guild.id, None)
            asyncio.create_task(getaway(ch, bank, guild.id, h))
        elif not h["warned"] and now >= h["end"] - 300:
            h["warned"] = True
            await save(bank, guild.id, h)
            await warn(ch, bank, guild.id, h)


async def warn(ch, bank: Bank, gid: int, h: dict):
    p = PLANS[h["ty"]]
    subs = " ".join(f"<@{s}>" for s in await bank.get_house(gid, "heistsubs", []) if int(s) not in h["crew"])
    await ch.send(
        "@here" + (f" 🔔 {subs}" if subs else "") + "\n" +
        f"## ⏰ 5 MINUTES LEFT TO JOIN THE {p['n'].upper()}! ⏰\n# 🚐 The van leaves <t:{int(h['end'])}:R>\n"
        f"Crew: **{len(h['crew'])}** • Odds: **{odds(p, len(h['crew']), h.get('boost'))}%**"
        f"{' (Kor floored it 🚐💨)' if h.get('boost') else ''}\n"
        "## 📣 Tag your friends! Every new crew member = +10% odds\n"
        f"**Type `join` to jump in!** Buy-in: {p['buy']} {C} • Pays **{p['win']} {C} each**\n"
        f"-# {random.choice(['Kor is revving the engine. It sounds like a blender.', 'Kor has already eaten the getaway snacks.'])}",
        view=join_view(h["ty"]) if len(h["crew"]) < SEATS else None, allowed_mentions=HERE)


async def getaway(ch, bank: Bank, gid: int, h: dict):
    p, crew = PLANS[h["ty"]], h["crew"]
    o = odds(p, len(crew), h.get("boost"))
    await bank.set_timer(gid, HOUSE, p["ck"], p["cd"])
    nxt = int(time.time() + p["cd"])
    ok = random.randrange(100) < o
    tags = " ".join(f"<@{c}>" for c in crew)
    head = f"🦹 **THE {p['n'].upper()}** • Crew of {len(crew)} • Odds: {o}%\n"
    msg = await ch.send(head + "🚐 " + random.choice([
        f"The getaway van rolls up to {p['tgt']} with its headlights off. Kor forgot to turn them back on.",
        f"The van parks outside {p['tgt']}. Kor parallel parks for nine minutes.",
        "The crew piles out of the van. Kor is wearing a ski mask with his name on it."]))
    await asyncio.sleep(3)
    await msg.edit(content=head + "🔦 " + random.choice([
        "Kor picks the lock... with a churro.", "Kor cuts the lights. Wrong building. Cuts the lights again.",
        "Kor cracks the keypad code. It was 1-2-3-4. It was always 1-2-3-4."]))
    await asyncio.sleep(3)
    await msg.edit(content=head + "👀 The vault door creaks open... something is moving inside...")
    await asyncio.sleep(3)
    if ok:
        for c in crew:
            await bank.add(gid, c, f"{p['n']} payout", chips=p["win"])
        await msg.edit(content=head + f"{ARMS}{ARMS}{ARMS}\n## 💰 {p['n'].upper()} SUCCESSFUL! 💰\n"
                       f"# {DANCE} +{p['win']} {C} EACH {DANCE}\n" + random.choice([
                           "Tacos. Wall to wall tacos. Kor floors it and the van peels out, dropping tacos the whole way home.",
                           "Clean getaway! Kor waves out the window the whole way. Very subtle. Very professional.",
                           "You robbed MY vault. I'm not mad. I'm writing names down."]) +
                       f"\n-# Crew: {tags}\n-# The cops are on high alert. Next {p['n']} <t:{nxt}:R>" + test_note(ch),
                       view=alerts_view())
        await ch.send(embed=pic("heist-win.gif"))
    else:
        await bank.set_house(gid, "lastbust", {"crew": crew, "buy": p["buy"], "until": time.time() + 86400})  # Kor's revenge
        await msg.edit(content=head + "## 🚨 BUSTED! 🚨\n" + random.choice([
            "It was me. I was waiting inside the vault the whole time. Sipping a margarita.",
            "Kor tripped the alarm reaching for a churro.", "Kor stopped for a drive-thru taco during the getaway."]) +
            f"\nEveryone loses their **{p['buy']} {C}** buy-in.\n-# Crew: {tags}\n-# Lay low. Next {p['n']} <t:{nxt}:R>",
            view=alerts_view())
        await ch.send(embed=pic("heist-busted.gif"))
