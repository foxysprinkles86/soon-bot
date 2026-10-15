"""Race betting (Shannon's add): bet chips on who'll be TnT's top scorer in the clan race.
`race bet @name 20` (1-100 per race, one pick each, top up the same pick any time) • `race bets` = the betting book.
Mods: `race bets open [note]` • `race bets close` • `race winner @name` (a tie: @ both) • `race bets cancel` (refunds).
With SCHEDULES=1 the book opens by itself when pre-join opens and closes at the 10-minute race warning.
Payout: winners split the WHOLE pot plus a 20% house bonus, by how much they bet. Nobody picked the winner = refunds.
Betting on yourself is allowed (and encouraged: it's motivation). Saved in house kv `racebook`."""
import random
import re
import time

from . import buttons
from .casino import C, casino_channel, test_note
from .economy import Bank

MAX_BET, BONUS = 100, 0.2
RACE_RE = re.compile(r"(?i)^\s*race\s+(bets?|book|winners?|odds)\b(.*)$", re.S)


async def _book(bank: Bank, gid: int) -> dict | None:
    return await bank.get_house(gid, "racebook")


async def open_book(bank: Bank, gid: int, label: str = "") -> bool:
    """Opens a new book unless one is already running. True if it opened."""
    if await _book(bank, gid):
        return False
    await bank.set_house(gid, "racebook", {"state": "open", "label": label, "bets": {}, "opened": int(time.time())})
    return True


async def close_book(bank: Bank, gid: int) -> dict | None:
    b = await _book(bank, gid)
    if b and b["state"] == "open":
        b["state"] = "closed"
        await bank.set_house(gid, "racebook", b if b["bets"] else None)    # no bets = nothing to settle
        return b
    return None


def _totals(b: dict) -> dict[str, list]:
    """pick -> [chips on them, number of backers]"""
    out: dict[str, list] = {}
    for pick, n in b["bets"].values():
        t = out.setdefault(pick, [0, 0])
        t[0] += n
        t[1] += 1
    return out


def book_text(guild, b: dict) -> str:
    pot = sum(n for _, n in b["bets"].values())
    head = "## 🏁 Race Betting Book" + (f": {b['label']}" if b.get("label") else "") + "\n"
    state = ("🟢 **OPEN**: `race bet @name 20` (who scores the most for TnT this race?)" if b["state"] == "open"
             else "🔒 **CLOSED**: the race is on. Waiting for a mod to call the winner.")
    if not b["bets"]:
        return head + state + "\nNo bets yet. Somebody believe in somebody."
    rows = sorted(_totals(b).items(), key=lambda x: -x[1][0])
    lines = []
    for pick, (n, k) in rows[:12]:
        m = guild.get_member(int(pick))
        name = m.display_name if m else f"<@{pick}>"
        lines.append(f"**{name}**: {n} {C} from {k} backer{'s' if k != 1 else ''} • pays about **x{pot * (1 + BONUS) / n:.1f}**")
    return (head + state + "\n" + "\n".join(lines) + f"\n-# Pot: {pot} {C} + 20% house bonus for the winners • "
            "max 100 per person • one pick each")


async def handle(message, bank: Bank, mod: bool) -> bool:
    if not casino_channel(message.channel):
        return False
    m = RACE_RE.match(message.content or "")
    if not m:
        return False
    word, rest = m.group(1).lower(), m.group(2).strip()
    gid, u = message.guild.id, message.author.mention
    if word.startswith("winner"):
        if not mod:
            await message.channel.send(f"🏁 {u} Only mods call the winner. Nice try. I'm writing that down.")
        else:
            await settle(message, bank)
        return True
    if word in ("bets", "book", "odds"):
        low = rest.lower()
        if mod and low.startswith("open"):
            label = rest[4:].strip()
            if await open_book(bank, gid, label):
                await message.channel.send("# 🏁 Race betting is OPEN!\nWho's going to score the most for TnT this race? "
                                           f"Put your chips where your mouth is: `race bet @name 20` (up to 100 {C}).\n"
                                           "-# Betting on yourself is allowed. Losing on yourself is embarrassing.",
                                           view=_view())
            else:
                await message.channel.send("🏁 There's already a book running. `race winner @name` or `race bets cancel` first.")
            return True
        if mod and low.startswith("close"):
            b = await close_book(bank, gid)
            await message.channel.send("🔒 Race betting is closed. The race is on. Pray." if b else "🏁 No open book to close.")
            return True
        if mod and low.startswith("cancel"):
            await cancel(message, bank)
            return True
        if not mod and re.match(r"(?i)(open|close|cancel)", low):
            await message.channel.send(f"🏁 {u} Mods run the book. You just lose money in it.")
            return True
        if word == "bets" and re.search(r"<@!?\d+>", rest):     # "race bets @name 20" typo: treat it as a bet
            await bet(message, bank, rest)
            return True
        b = await _book(bank, gid)
        await message.channel.send(book_text(message.guild, b) if b else
                                   "🏁 No race betting right now. It opens when race pre-join opens (or when a mod "
                                   "types `race bets open`).", view=_view() if b else None)
        return True
    await bet(message, bank, rest)
    return True


def _view():
    return buttons.view(("race bets", "Race book", "🏁"))


async def bet(message, bank: Bank, rest: str):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    b = await _book(bank, gid)
    if not b:
        await message.channel.send(f"🏁 {u} No race betting right now. It opens when pre-join opens.")
        return
    if b["state"] != "open":
        await message.channel.send(f"🔒 {u} Betting's closed. The race already started. Bet faster next time.")
        return
    pm = re.search(r"<@!?(\d+)>", rest)
    num = re.search(r"\d+", re.sub(r"<@!?\d+>", "", rest))
    if not pm or not num:
        await message.channel.send(f"🏁 {u} Like this: `race bet @name 20`. Who, and how much.")
        return
    pick, n = pm.group(1), int(num.group())
    member = message.guild.get_member(int(pick))
    if (member and member.bot) or int(pick) == getattr(message.guild.me, "id", 0):
        await message.channel.send(f"🏁 {u} Bots don't race. I'd win, obviously, but they won't let me.")
        return
    mine = b["bets"].get(str(uid))
    if mine and mine[0] != pick:
        await message.channel.send(f"🏁 {u} You already backed <@{mine[0]}>. No switching sides. Loyalty, darling.")
        return
    already = mine[1] if mine else 0
    n = min(n, MAX_BET - already)
    if n < 1:
        await message.channel.send(f"🏁 {u} You're maxed out at {MAX_BET} {C} on this race. Calm down.")
        return
    w = await bank.pay(gid, uid, n, "race bet")
    if w is None:
        have = (await bank.get(gid, uid)).chips
        await message.channel.send(f"🏁 {u} You have {have} {C}. You can't bet {n}. Faith is free. Bets aren't.")
        return
    b = await _book(bank, gid) or b                   # re-read in case someone else bet meanwhile
    b["bets"][str(uid)] = [pick, already + n]
    await bank.set_house(gid, "racebook", b)
    who = "yourself" if pick == str(uid) else f"<@{pick}>"
    line = (random.choice(["Self-belief. Disgusting. I love it.", "Bold. Now go race like your chips depend on it. They do."])
            if pick == str(uid) else
            random.choice(["Noted. I'll pretend I'm not judging your pick.", "Interesting choice. Wrong, probably.",
                           "The book is updated. So is my opinion of you.", "Bold. Let's see if they deserve you."]))
    await message.channel.send(f"🏁 {u} bets **{n} {C}** on {who} (total {already + n}). {line}\n"
                               f"-# Chips left: {w.chips} {C} • `race bets` shows the book",
                               allowed_mentions=_quiet())


def _quiet():
    import discord
    return discord.AllowedMentions(users=False, everyone=False, roles=False)


async def settle(message, bank: Bank):
    gid = message.guild.id
    b = await _book(bank, gid)
    winners = set(re.findall(r"<@!?(\d+)>", message.content))
    if not b:
        await message.channel.send("🏁 There's no race book to settle.")
        return
    if not winners:
        await message.channel.send("🏁 Who won? `race winner @name` (a tie: `race winner @name @name`).")
        return
    await bank.set_house(gid, "racebook", None)        # settle once, even if two mods type it together
    pot = sum(n for _, n in b["bets"].values())
    backers = {uid: n for uid, (pick, n) in b["bets"].items() if pick in winners}
    names = " & ".join(f"<@{w}>" for w in winners)
    if not b["bets"]:
        await message.channel.send(f"🏁 {names} won the race! Nobody bet on anything. Cowards. Book closed.")
        return
    if not backers:
        for uid, (_, n) in b["bets"].items():
            await bank.add(gid, int(uid), "race bet refund", chips=n)
        await message.channel.send(f"# 🏁 {names} won the race!\nNobody saw THAT coming. Not one of you backed them. "
                                   f"Everyone gets their chips back ({pot} {C} refunded). Shameful.",
                                   allowed_mentions=_quiet())
        return
    prize = int(pot * (1 + BONUS))
    on_winner = sum(backers.values())
    lines = []
    for uid, n in sorted(backers.items(), key=lambda x: -x[1]):
        won = max(n, prize * n // on_winner)
        await bank.add(gid, int(uid), "race bet win", chips=won)
        await bank.record_play(gid, int(uid), won - n)
        lines.append(f"💰 <@{uid}> bet {n} → **+{won} {C}**")
    for uid, (pick, n) in b["bets"].items():
        if pick not in winners:
            await bank.record_play(gid, int(uid), -n)
    losers = len(b["bets"]) - len(backers)
    await message.channel.send(
        f"# 🏁 {names} won the race!\n" + "\n".join(lines)
        + f"\n{losers} {'person' if losers == 1 else 'people'} bet on the wrong horse. The house thanks you."
        + f"\n-# Pot {pot} {C} + 20% house bonus, split by how much each winner bet" + test_note(message.channel),
        allowed_mentions=_quiet())


async def cancel(message, bank: Bank):
    gid = message.guild.id
    b = await _book(bank, gid)
    if not b:
        await message.channel.send("🏁 No race book to cancel.")
        return
    await bank.set_house(gid, "racebook", None)
    for uid, (_, n) in b["bets"].items():
        await bank.add(gid, int(uid), "race bet refund", chips=n)
    await message.channel.send(f"🏁 Race book cancelled. {len(b['bets'])} bet(s) refunded. Nobody won. Nobody lost. Boring.")
