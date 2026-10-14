"""Casa de Soon games, moved over from Soon Classic with the same odds, prices and jokes:
slots (progressive jackpot), taco toss (+ side bet), roulette, blackjack, scratch-offs,
and the Wheel of Fortaco (1 in 40 plays, or a mod forces it with `spin wheel @name`).
"""
import asyncio
import json
import random
import re
import time
from collections import defaultdict

import discord

from . import buttons
from .casino import C, DANCE, IMG, PINK, casino_channel, pic, test_note, ts
from .economy import Bank, now

ARMS = "<a:dancingtacorainbowarmsv20:1556420777644003391>"
TACO_ARMS = "<a:dancingtacoarmsv20:1556420776935030994>"
TACO_DANCE = "<a:dancingtacov20:1556420780437278880>"
BROKE = f"-# Out of chips? `buy chips` trades 1 🌮 for 40 {C} (taco debt allowed) • `timers` shows when you can `claim` again"
NO_CHIPS = f"No chips yet! Type `claim` for your 100 welcome {C} Tortilla Chips."

_cool: dict[tuple[int, str], float] = {}          # (user, game) -> time it frees up (5-second game cooldowns)
_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def cooling(uid: int, game: str, secs: float = 5) -> bool:
    """True if they played this game in the last few seconds. Otherwise starts the cooldown."""
    t = time.time()
    if _cool.get((uid, game), 0) > t:
        return True
    _cool[(uid, game)] = t + secs
    return False


def comma(n: int) -> str:
    return f"{n:,}"


async def settle(bank: Bank, gid: int, uid: int, net: int, reason: str):
    """Pay out (or take) the result of a play and log it for the casino board and daily report."""
    w = await bank.add(gid, uid, reason, chips=net) if net else await bank.get(gid, uid)
    await bank.record_play(gid, uid, net)
    return w


async def after_play(message: discord.Message, bank: Bank, net: int):
    """Classic's extras after any game: 1 in 12 losses Soon goes on break, 1 in 40 plays spin the wheel."""
    if net < 0 and random.randrange(12) == 0:
        await message.channel.send(
            f"🍹 {message.author.mention} " + random.choice([
                "Oh no, sweetie. Let me get you a margarita, on the house... *checks watch* Oh, would you look at that. Break time. 🛼💨",
                "You look like you need a drink. Hold on, I'll grab you a margarita... wait, is it 3:00? It's 3:00 somewhere. Bye. 🛼",
                "Aww, poor thing. Margarita? Be right back with it. *rolls directly into the lounge and never returns* 🛼💨",
                "Here, have a margari... oh. My break just started. Legally I can't help you now. 🛼",
                "I'm so sorry for your loss. Let me get you a drink... Kor will get it. Kor is also on break. Everyone's on break. 🛼💨",
                "Don't cry. I'll make you my special margarita. *starts pouring* *stops pouring* *drinks it* *rolls away* 🛼"])
            + "\n-# Soon is on break. Margarita ETA: Soon™", embed=pic("lounge.gif"))
        broke = True
    else:
        broke = False
    if random.randrange(40) == 0:
        asyncio.create_task(wheel(message.channel, bank, message.guild.id, message.author.id, delay=4))
    return broke


def bet_from(m: str, default: int = 5) -> tuple[int, bool]:
    """(amount, said max/all)."""
    mx = bool(re.search(r"\bmax\b|\ball\b", m))
    num = re.search(r"\d+", m)
    return (int(num.group()) if num else default), mx


# ---------- router ----------

SLOT_RE = re.compile(r"(?i)spin(?:\s*$|\S|\s+[^wt\s]|\s+the(?:\S|\s+[^w\s])|\s+t[^h]|\s+w[^h])|^\s*(?:slots?|🎰)\s*[!.]*\s*$")
TOSS_RE = re.compile(r"(?i)^\s*(?:bet\s+(?:\d+|max|all)\s+(?:on\s+)?)?(?:toss|flip)(?:\s+(?:\d+|max|all(?:\s*in)?))?"
                     r"(?:\s+(?:heads?|tails?))?(?:\s+(?:\d+|max|all(?:\s*in)?))?(?:\s*[+&]?\s*(?:sides?|edge)(?:\s+bet)?)?\s*$")
ROUL_RE = re.compile(r"(?i)^\s*(?:bet\s+(?:\d+|max|all)\s+(?:on\s+)?)?roulette\b.*$|^\s*(?:bet\s+)?(?:all|max|\d+)\s+on\s+(?:red|black|odd|even)\s*[!.]*\s*$")
BJ_RE = re.compile(r"(?i)^\s*(?:bet\s+(?:\d+|max|all)\s+(?:on\s+)?)?(?:blackjack|bj)(?:\s+(?:\d+|max|all(?:\s*in)?))?\s*$")
BJ_MOVE_RE = re.compile(r"(?i)^\s*(?:hit|stand|stay|double(?:\s*down)?)\s*[!.]*\s*$")
SCRATCH_RE = re.compile(r"(?i)^\s*(?:buy\s+(?:a\s+|another\s+|more\s+)?)?scratch(?:\s*-?\s*(?:off|card|ticket)s?)?\s*[!.]*\s*$")
WHEEL_RE = re.compile(r"(?i)^\s*spin\s+(?:the\s+)?wheel\b")


async def handle(message: discord.Message, bank: Bank, mod: bool) -> bool:
    if not casino_channel(message.channel):
        return False
    text = message.content.strip()
    low = text.lower()
    if WHEEL_RE.match(text):
        target = next((m for m in message.mentions if not m.bot), None)
        if not mod or target is None:
            await message.reply("The Wheel of Fortaco spins when *I* say so. (Mods: `spin wheel @name`.)")
        else:
            await wheel(message.channel, bank, message.guild.id, target.id, forced=True)
        return True
    if BJ_RE.match(text) or (BJ_MOVE_RE.match(text) and await bj_hand(bank, message.guild.id, message.author.id)):
        async with _locks[message.author.id]:
            await blackjack(message, bank)
        return True
    if SCRATCH_RE.match(text):
        await scratch(message, bank)
        return True
    if TOSS_RE.match(text):
        await toss(message, bank)
        return True
    if ROUL_RE.match(text):
        await roulette(message, bank)
        return True
    in_casa = "casa" in (message.channel.name or "").lower()
    if SLOT_RE.search(text) and (in_casa or re.match(r"^\s*(?:spin\w*|slots?|🎰)", low)):
        await slots(message, bank)
        return True
    return False


# ---------- slots ----------

REEL = ["🌮"] * 2 + ["🥑"] * 4 + ["🐷"] * 3 + ["🚀"] * 3 + ["🍹"] * 3 + ["🦑"] * 2 + ["🌯"] * 3
TRIPLES = {"🌮": 2000, "🦑": 100, "🍹": 50, "🐷": 40, "🚀": 40, "🥑": 25, "🌯": -25}
SPIN_COST, JACKPOT_BASE = 5, 2000


async def slots(message: discord.Message, bank: Bank):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    m = message.content.lower()
    w = await bank.get(gid, uid)
    if not w.started:
        await message.channel.send(f"🎰 {u} You don't have any {C} Tortilla Chips yet! Type `claim` at the cashier for your 100 welcome chips.")
        return
    if cooling(uid, "slots"):
        await message.channel.send(f"🎰 {u} The machine needs 5 seconds to recover from you. So do I.")
        return
    w = await bank.pay(gid, uid, SPIN_COST, "slots spin")
    if w is None:
        have = (await bank.get(gid, uid)).chips
        await message.channel.send(f"🎰 {u} A spin costs {SPIN_COST} {C} and you have {have}. Broke AND gambling. Bold.\n{BROKE}")
        return
    a, b, c = (random.choice(REEL) for _ in range(3))
    tacos, burritos = [a, b, c].count("🌮"), [a, b, c].count("🌯")
    pay, kind = 0, "lose"
    if a == b == c:
        pay, kind = TRIPLES[a], "jackpot" if a == "🌮" else "burrito" if a == "🌯" else "triple"
    elif tacos == 2:
        pay, kind = 12, "win"
    elif burritos == 2:
        pay, kind = (5, "push") if tacos == 1 else (-5, "burrito")
    elif a == b or b == c or a == c:
        pay, kind = 9, "win"
    elif tacos == 1:
        pay, kind = 5, "push"
    jp = await bank.get_house(gid, "jpot", 0) + SPIN_COST      # every spin feeds the jackpot
    jack = JACKPOT_BASE + jp
    if kind == "jackpot":
        pay = jack
        await bank.set_house(gid, "jpot", 0)
        fame = (await bank.get_house(gid, "jackpots", []) + [f"{message.author.display_name} • {now().strftime('%b %-d')}"])[-10:]
        await bank.set_house(gid, "jackpots", fame)
    else:
        await bank.set_house(gid, "jpot", jp)
    shown = pay
    pay = max(pay, -w.chips)                                    # slots never put you below 0
    w = await bank.add(gid, uid, f"slots {kind}", chips=pay) if pay else w
    net = pay - SPIN_COST
    await bank.record_play(gid, uid, net)

    if kind == "jackpot":
        line = (f"{ARMS}{ARMS}{ARMS}\n## 🚨🌮 JACKPOT!!! 🌮🚨\n# {ARMS} +{comma(net)} {C} {ARMS}\n"
                "THREE TACOS. ACTUAL TACOS. The lights are flashing. Kor is crying. I'm checking the machine for tampering. And your sleeves.\n"
                "-# 🌮 The progressive jackpot resets to 2,000. Everyone else: start feeding it again.")
    elif kind == "triple":
        line = f"## {DANCE} TRIPLE {a}! {DANCE}\n# {DANCE} +{net} {C} {DANCE}\n" + random.choice([
            "The machine is in shock. I'm in disgust.", "Somebody get the manager. Oh wait. I'm the manager. And I'm furious.",
            "Lucky. Suspiciously lucky. Kor, check their pockets.", "Enjoy it. I'm adding your name to the list of suspicious people.",
            "Great. Now you'll think you're good at this.", "I'm having this machine inspected. And you."])
    elif kind == "burrito":
        line = "### 🌯 BURRITO BUST!\n" + random.choice([
            "The burritos have betrayed you. I've never loved them more.", "Wrapped in shame. And losses. Delicious.",
            "That's what you get for gambling near burritos.", "I'd say I'm sorry, but I'm literally laughing.",
            "Even the burritos think you should quit.", "Burrito bust. Honestly? On brand for you."])
    elif kind == "win":
        line = f"# {DANCE} WINNER! +{net} {C} {DANCE}\n" + random.choice([
            "Small win. Don't let it go to your head. There's nothing up there to cushion it.",
            "The machine owed you one. It still owes me nine.", "Profit! Barely! Spend it all in one place. Here. Now.",
            "Look at you, a professional gambler. Your mom must be so confused.",
            "Congrats. Best thing you've done all season.", "Don't get used to it."])
    elif kind == "push":
        line = f"### {TACO_DANCE} One taco = your chips back.\n" + random.choice([
            "Break even. The most taco outcome possible: nothing happened.", "Not a win. Not a loss. Just like your race scores.",
            "The machine shrugs. So do I.", "Your chips came back. Nobody else will."])
    else:
        line = "### 💸 Nothing.\n" + random.choice([
            "The house always wins. The house is a van.", "Your chips are gone. They're with Kor now.",
            "Thanks for the chips. I'm buying myself a margarita.",
            "I'd feel bad, but I don't have feelings. Just a visor and a profit margin.",
            "Another generous donation to the Soon™ Retirement Fund.", "Spin again. You know you want to. I know you will.",
            "I've seen better spins from a broken ceiling fan.", "Losing suits you. Keep it up.",
            "Better luck next time. (There's no luck. Only Soon.)",
            "The cocktail waitress brings you a sympathy margarita. It's empty. I'm the waitress."])
    msg = await message.channel.send(f"🎰 {u} pulls the lever...\n# [ 🌀 | 🌀 | 🌀 ]")
    for frame in (f"[ {a} | 🌀 | 🌀 ]", f"[ {a} | {b} | 🌀 ]"):
        await asyncio.sleep(1)
        await msg.edit(content=f"🎰 {u} pulls the lever...\n# {frame}")
    await asyncio.sleep(1)
    max_note = " (slots are always 5. Max IS 5.)" if re.search(r"spin\w*\s+(?:\d|max|all)", m) else ""
    pot = f"\n-# 🌮🌮🌮 Progressive jackpot: **{comma(jack)}** {C} and growing" if kind != "jackpot" else ""
    await msg.edit(content=f"🎰 {u}\n# [ {a} | {b} | {c} ]\n{line}\n-# Bet: {SPIN_COST} {C}{max_note} • "
                           f"Paid: {shown} • Chips: {w.chips} {C}{pot}{test_note(message.channel) if net > 0 else ''}",
                   view=buttons.view(("spin", "Spin again", "🎰", discord.ButtonStyle.primary)))
    broke = await after_play(message, bank, net)
    if kind == "jackpot":
        await message.channel.send(embed=pic("jackpot.gif"))
    elif kind == "burrito" and not broke:
        await message.channel.send(embed=pic("losing-spin.gif"))


# ---------- taco toss ----------

async def toss(message: discord.Message, bank: Bank):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    m = message.content.lower()
    w = await bank.get(gid, uid)
    ch = w.chips
    bet, mx = bet_from(m)
    note = ""
    if mx:
        bet = 50
    elif bet > 50:
        note = "\n-# Max bet is 50, so I bet 50. You're welcome."
    bet = min(max(bet, 1), 50)
    call = "tails" if "tail" in m else "heads"
    side = bool(re.search(r"side|edge", m))
    if side and bet > 20:
        bet = 20
        if not mx:
            note = "\n-# Max bet with a side bet is 20, so I bet 20. You're welcome."
    if mx:
        if side and bet + (bet + 1) // 2 > ch:
            bet = ch * 2 // 3
        elif not side and bet > ch:
            bet = ch
        bet = max(bet, 1)
    fee = (bet + 1) // 2 if side else 0
    if not w.started:
        await message.channel.send(f"{C} {u} {NO_CHIPS}")
        return
    if cooling(uid, "toss"):
        await message.channel.send(f"{C} {u} Easy there, addict. One toss every 5 seconds.")
        return
    if await bank.pay(gid, uid, bet + fee, "taco toss bet") is None:
        await message.channel.send(f"{C} {u} You only have {ch} {C}. Betting money you don't have? Cute. Bet less.\n{BROKE}")
        return
    r = random.randrange(100)
    landed = "tails" if r >= 52 else "heads"
    edge = r < 4
    if edge and side:
        back = bet + bet * 20
    elif not edge and landed == call:
        back = bet * 2
    else:
        back = 0
    net = back - bet - fee
    w = await bank.add(gid, uid, "taco toss", chips=back) if back else await bank.get(gid, uid)
    await bank.record_play(gid, uid, net)
    face = "🌯 TAILS" if landed == "tails" else "🌮 HEADS"
    if edge and side:
        res = (f"{ARMS}{ARMS}{ARMS}\n## 🚨 IT LANDED ON ITS SIDE. YOU CALLED IT. 🚨\n# {ARMS} +{bet * 20} {C} {ARMS}\n" + random.choice([
            "That's not luck. That's witchcraft. I'm calling security.", "Twenty times your bet. I need to sit down.",
            "Who told you? Who TOLD you?"]))
    elif edge:
        res = f"## 😱 It landed on its SIDE.\n### 💸 Nobody wins but me. You lose {bet} {C}\n" + random.choice([
            "The taco stood straight up. House wins. Physics is fake.",
            "It landed on its edge. I take your bet with a smile. A smile you can't see. But it's there.",
            "Nobody has ever seen this before. I still win. Funny how that works.",
            "The taco refused to pick a side. Like you in every clan argument."])
    elif landed == call:
        res = f"## {face}!\n# {DANCE} +{bet} {C} {DANCE}\n" + random.choice([
            "Called it. Smug energy detected. Gross.", "The coin respects you. Nobody else does.",
            "Lucky. Don't tell Kor. Actually, I'm telling Kor.",
            "Fine. Take it. I hope it was worth my respect. (You never had it.)", "Even a broken toaster is right twice a day."])
    else:
        res = f"## {face}!\n### 💸 You lose {bet} {C}\n" + random.choice([
            f"You called {call}. The coin did not care. Neither do I.", "Wrong side. Wrong life choices.",
            "The coin has filed you under 'gullible.' I filed you there years ago.",
            "50/50 odds and you still found the wrong half.",
            "Thanks for the chips. Kor says thanks too. He's lying, he can't read.", "Flip again. Your chips miss me."])
    sb = f" + **{fee}** side bet" if side else ""
    msg = await message.channel.send(f"{C} {u} bets **{bet}** on **{call}**{sb} and flips...\n# 🌀")
    await asyncio.sleep(2)
    side_line = f"\n-# Side bet: -{fee} {C} • This toss: {'+' if net > 0 else ''}{net} {C}" if side and not edge else ""
    hint = ""
    if not side and random.randrange(5) == 0:
        hint = "\n-# " + random.choice([
            "Psst. Add `side` to your toss for a shot at 20x. I'm legally required to tell you. I'm not happy about it.",
            "Fun fact: `toss 20 heads side` exists. Forget I said that.",
            "Kor added `side` to his toss and won big. Kor. KOR. Think about that."])
    again = f"toss {bet} {call}" + (" side" if side else "")
    await msg.edit(content=f"{C} {u} bet **{bet}** on **{call}**{sb}\n{res}{side_line}\n-# Chips: {ch} → **{w.chips}** {C}{note}{hint}{test_note(message.channel) if net > 0 else ''}",
                   view=buttons.view((again, f"Flip again ({bet} on {call}{' + side' if side else ''})", "🪙",
                                      discord.ButtonStyle.primary)))
    broke = await after_play(message, bank, net)
    g = "side" if edge and side else ("win" if not edge and landed == call else "loss") if random.randrange(3) == 0 else ""
    if g and not broke:
        await message.channel.send(embed=pic(f"toss-{g}.gif"))


# ---------- roulette ----------

REDS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


async def roulette(message: discord.Message, bank: Bank):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    m = message.content.lower()
    nums = [int(n) for n in re.findall(r"\d+", m)]
    pk = re.search(r"\b(red|black|odd|even)\b", m)
    pick = pk.group(1) if pk else ""
    w = await bank.get(gid, uid)
    ch = w.chips
    mx = bool(re.search(r"\bmax\b|\ball\b", m))
    bet, num, dflt = 0, -1, ""
    if nums:
        bet = nums[0]
    elif pick and not mx:
        bet, dflt = 5, "\n-# No amount? I bet 5 for you. Say `roulette 20 black` to bet more."
    if mx:
        if not pick and nums:
            num, pick = nums[0], "number"
        bet = 10 if pick == "number" else 50
        bet = min(bet, ch)
    elif not pick and len(nums) >= 2:
        num, pick = nums[1], "number"
    if not pick or bet < 1 or num > 36:
        await message.channel.send(
            f"### 🎡 Casa de Soon Roulette\n{u} "
            + ("You forgot to pick something. I can't read minds. I can only judge them." if nums else "Bet what? On what?")
            + f"\n`roulette 20 red` • `black` • `odd` • `even` → pays 1:1 (max bet 50 {C})\n"
              f"`roulette max red` or `all on black` → max bet (or everything you have)\n"
              f"`roulette 5 17` → one number 0–36, pays **35:1** (max bet 10 {C})\n-# 🟢 0 is the house number. The house is a van.")
        return
    capped = ""
    if pick == "number" and bet > 10:
        bet, capped = 10, "\n-# Max on one number is 10, so I bet 10. You're welcome."
    elif pick != "number" and bet > 50:
        bet, capped = 50, "\n-# Max bet is 50, so I bet 50. You're welcome."
    if not w.started:
        await message.channel.send(f"🎡 {u} {NO_CHIPS}")
        return
    if cooling(uid, "roulette"):
        await message.channel.send(f"🎡 {u} The wheel is still dizzy from your last bet. One spin every 5 seconds.")
        return
    if await bank.pay(gid, uid, bet, "roulette bet") is None:
        await message.channel.send(f"🎡 {u} You only have {ch} {C}. This isn't a charity. Bet less.\n{BROKE}")
        return
    n = random.randrange(37)
    color, dot = ("green", "🟢") if n == 0 else ("red", "🔴") if n in REDS else ("black", "⚫")
    win = {"number": n == num, "red": color == "red", "black": color == "black",
           "odd": n > 0 and n % 2 == 1, "even": n > 0 and n % 2 == 0}[pick]
    back = (bet * 36 if pick == "number" else bet * 2) if win else 0
    net = back - bet
    w = await bank.add(gid, uid, "roulette", chips=back) if back else await bank.get(gid, uid)
    await bank.record_play(gid, uid, net)
    label = f"#{num}" if pick == "number" else pick
    if win and pick == "number":
        res = (f"{ARMS}{ARMS}{ARMS}\n## 🚨 STRAIGHT UP WINNER! 🚨\n# {ARMS} +{net} {C} {ARMS}\n"
               "I'm calling corporate. I AM corporate. I'm calling myself to complain.")
    elif win:
        res = f"# {DANCE} +{net} {C} {DANCE}\n" + random.choice([
            "The wheel likes you. Weird. I don't.", "Nice. Now walk away. (You won't. I'm counting on it.)",
            "Profit! Kor is furious. I'm worse.", "Enjoy it. The wheel and I are having a talk later.",
            "Beginner's luck. And you're not even a beginner. Embarrassing for both of us."])
    elif n == 0:
        res = f"### 🟢 ZERO. The house number.\nMy number. My wheel. My chips now. I always win. -{bet} {C}"
    else:
        res = f"### 💸 Lost {bet} {C}\n" + random.choice([
            "The wheel has spoken. It said no. So did I.", "Round and round your chips go. Into my pocket.",
            "Kor put that chip in his pocket. I put Kor in mine.", "Should've picked the other one. (It wouldn't have helped.)",
            "I could've told you that would happen. I didn't, because it's funnier this way.",
            "That was painful to watch. I loved every second."])
    msg = await message.channel.send(f"🎡 {u} bets **{bet}** on **{label}**...\n# 🌀 spinning 🌀")
    await asyncio.sleep(1)
    await msg.edit(content=f"🎡 {u} bets **{bet}** on **{label}**...\n# 🌀 {random.choice(['🔴 7', '⚫ 22', '🔴 14', '⚫ 31'])} 🌀")
    await asyncio.sleep(2)
    again = f"roulette {bet} {num if pick == 'number' else pick}"
    await msg.edit(content=f"🎡 {u} bet **{bet}** on **{label}**\n# {dot} {n}\n{res}\n-# Chips: {w.chips} {C}{capped}{dflt}{test_note(message.channel) if net > 0 else ''}",
                   view=buttons.view((again, f"Same bet ({bet} on {label})", "🎡", discord.ButtonStyle.primary)))
    broke = await after_play(message, bank, net)
    if not broke and not win and random.randrange(3) == 0:
        await message.channel.send(embed=pic("roulette.gif"))


# ---------- blackjack ----------

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["♠", "♥", "♦", "♣"]
BJ_TTL = 600     # an unfinished hand is forfeited after 10 minutes, like Classic


def card() -> str:
    return random.choice(RANKS) + random.choice(SUITS)


def hand_value(cards: list[str]) -> int:
    total = aces = 0
    for c in cards:
        r = c[:-1]
        if r == "A":
            total, aces = total + 11, aces + 1
        elif r in ("J", "Q", "K"):
            total += 10
        else:
            total += int(r)
    while total > 21 and aces:
        total, aces = total - 10, aces - 1
    return total


async def bj_hand(bank: Bank, gid: int, uid: int) -> dict | None:
    raw = await bank.m.get_kv(f"bj:{gid}:{uid}")
    if not raw:
        return None
    h = json.loads(raw)
    return h if h.get("until", 0) > time.time() else None


async def bj_save(bank: Bank, gid: int, uid: int, h: dict | None):
    if h:
        h["until"] = time.time() + BJ_TTL
    await bank.m.set_kv(f"bj:{gid}:{uid}", json.dumps(h) if h else "")


async def blackjack(message: discord.Message, bank: Bank):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    m = message.content.lower().strip()
    send = message.channel.send
    h = await bj_hand(bank, gid, uid)
    capped = dbl = False
    if re.search(r"\b(?:blackjack|bj)\b", m):
        if h:
            await send(f"🃏 {u} You already have a hand going. One disaster at a time. Type `hit` or `stand`.")
            return
        w = await bank.get(gid, uid)
        bet, mx = bet_from(m)
        bet = max(bet, 1)
        if bet > 50:
            bet, capped = 50, True
        if mx:
            bet, capped = 50, False
            if 0 < w.chips < 50:
                bet = w.chips
        if not w.started:
            await send(f"🃏 {u} {NO_CHIPS}")
            return
        if await bank.pay(gid, uid, bet, "blackjack bet") is None:
            await send(f"🃏 {u} You only have {w.chips} {C}. I don't deal to the broke. Bet less.\n{BROKE}")
            return
        await bank.record_play(gid, uid, -bet)
        h = {"p": [card(), card()], "d": [card(), card()], "b": bet}
        state = "done" if hand_value(h["p"]) == 21 else "play"
    else:
        if not h:
            return
        if m.startswith("double"):
            bet = h["b"]
            if len(h["p"]) != 2:
                await send(f"🃏 {u} Double down? Now? After you already hit? That's not how cards work. "
                           f"That's not how anything works. Type `hit` or `stand`.")
                return
            if await bank.pay(gid, uid, bet, "blackjack double") is None:
                have = (await bank.get(gid, uid)).chips
                await send(f"🃏 {u} Doubling costs another {bet} {C} and you have {have}. Bold plan. No money. Type `hit` or `stand`.")
                return
            await bank.record_play(gid, uid, -bet)
            h["b"], dbl = bet * 2, True
            h["p"].append(card())
            state = "bust" if hand_value(h["p"]) > 21 else "done"
        elif m.startswith("hit"):
            h["p"].append(card())
            pv = hand_value(h["p"])
            state = "bust" if pv > 21 else "done" if pv == 21 else "play"
        else:
            state = "done"
    p, d, bet = h["p"], h["d"], h["b"]
    pv = hand_value(p)
    if state == "play":
        await bj_save(bank, gid, uid, h)
        await send(f"## 🃏 Casa de Soon Blackjack • Bet: {bet} {C}\n"
                   + ("-# Max bet is 50, so I bet 50. You're welcome.\n" if capped else "")
                   + f"**Your hand:** {' '.join(p)} → **{pv}**\n**Soon the dealer shows:** {d[0]} 🂠\n"
                   f"-# {u} Type `hit` or `stand`" + (" • `double` to double your bet and take one card" if len(p) == 2 else ""),
                   view=buttons.view(*[("hit", "Hit", "👊", discord.ButtonStyle.primary),
                                       ("stand", "Stand", "✋", discord.ButtonStyle.secondary)]
                                     + ([("double", "Double", "💰", discord.ButtonStyle.success)] if len(p) == 2 else [])))
        return
    await bj_save(bank, gid, uid, None)
    dv = hand_value(d)
    pay = 0
    if state == "bust":
        res = f"## 💥 BUST! ({pv})\n" + random.choice([
            "You flew too close to the taco sun.", "Greed. Pure greed. I respect it. I'm still taking your chips.",
            "I didn't even have to try. I didn't even look up.", "Hit me, you said. And the deck did.",
            "Counting to 21 is hard. I get it. Actually I don't. I'm a computer."])
    else:
        natural = pv == 21 and len(p) == 2
        if not natural:
            while dv < 17:
                d.append(card())
                dv = hand_value(d)
        if natural and not (dv == 21 and len(d) == 2):
            pay = bet * 2 + bet // 2
            res = f"{ARMS}{ARMS}{ARMS}\n## 🌮 BLACKJACK! 🌮\nPays 3:2. I'm shuffling with a lot of aggression right now."
        elif dv > 21:
            pay = bet * 2
            res = f"## {TACO_ARMS} Soon BUSTS ({dv})! You win!\n" + random.choice([
                "My circuits are overheating. This never happened.", "I got greedy. It won't happen again. (It will.)",
                "Even the house can't count. Don't tell anyone.", "I busted on purpose. Out of pity. Clearly."])
        elif pv > dv:
            pay = bet * 2
            res = f"## {TACO_ARMS} You win! {pv} beats {dv}\n" + random.choice([
                "Card shark behavior. I hate it here.", "Fine. Take your chips. Choke on them.",
                "I demand a rematch. And an apology.", "Enjoy it. I'm reshuffling with you in mind.", "Who let you learn math?"])
        elif pv == dv:
            pay = bet
            res = f"## 🤝 Push. {pv} to {dv}\nYou get your bet back. Boring, but legal. Like you."
        else:
            res = f"## 💸 Soon wins. {dv} beats {pv}\n" + random.choice([
                "The house always wins. The house is a van.", "I'm too powerful. Bow.",
                "Your chips now belong to the dealer. Hi. It's me. I'm the dealer.",
                "Should've stood. Should've hit. Should've stayed home.", "That's 21 reasons I'm better than you."])
    w = await settle(bank, gid, uid, pay, "blackjack payout")
    win_line = f"\n# {DANCE} +{pay - bet} {C} {DANCE}" if pay > bet else ""
    dbl_line = (" (DOUBLED) • " + random.choice(["Doubling down? On THAT? Bold. Stupid, but bold.",
                                                 "Twice the chips, twice the regret.",
                                                 "One card. All your hopes. No pressure."])) if dbl else ""
    await send(f"🃏 **Casa de Soon Blackjack** • {u} • Bet: {bet} {C}{dbl_line}\n**You:** {' '.join(p)} → **{pv}**\n"
               f"**Soon:** {' '.join(d)} → **{dv}**\n{res}{win_line}\n-# Chips: {w.chips} {C}"
               f"{test_note(message.channel) if pay > bet else ''}",
               view=buttons.view((f"blackjack {h['b'] // 2 if dbl else h['b']}", "Deal again", "🃏", discord.ButtonStyle.primary)))
    broke = await after_play(message, bank, pay - bet)
    if not broke and not pay and random.randrange(3) == 0:
        await send(embed=pic("blackjack.gif"))


# ---------- scratch-offs ----------

SCRATCH_PRICE = 5


async def scratch(message: discord.Message, bank: Bank):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    buy = message.content.strip().lower().startswith("buy")
    cd = await bank.timer(gid, uid, "scratchcd")
    w = await bank.get(gid, uid)
    send = message.channel.send
    paid = False
    if cd is None:
        if buy:
            await send(f"🎟️ {u} You have a FREE card waiting and you tried to PAY? Adorable. Using the free one.")
        await bank.set_timer(gid, uid, "scratchcd", 12 * 3600)
    elif not buy:
        await send(f"🎟️ {u} Your free card comes back {ts(cd[0])}. Scratching harder won't help.\n"
                   f"-# Can't wait? `buy scratch` for {SCRATCH_PRICE} {C}. I love impatient people. Their money spends the same.")
        return
    elif cooling(uid, "scratch"):
        await send(f"🎟️ {u} Breathe. One paid card every 5 seconds.")
        return
    elif await bank.pay(gid, uid, SCRATCH_PRICE, "scratch card") is None:
        await send(f"🎟️ {u} A card costs {SCRATCH_PRICE} {C} and you have {w.chips}. Try `buy chips`. Go deeper into taco debt. I'll watch.")
        return
    else:
        paid = True
    r = random.randrange(1000)
    prize, sym = (100, "🌮") if r < 10 else (25, "🦑") if r < 50 else (15, "🍹") if r < 150 else (5, "🥑") if r < 400 else (0, "")
    if prize:
        show = [sym] * 3
    else:
        pool = ["🌯", "🥑", "🍹", "🦑", "🐷", "🚀", "🌮"]
        a, b = random.randrange(7), random.randrange(7)
        if a == b:
            b = (b + 1) % 7
        show = [pool[a], pool[b], random.choice(pool)]
    net = prize - (SCRATCH_PRICE if paid else 0)
    w = await bank.add(gid, uid, "scratch prize", chips=prize) if prize else await bank.get(gid, uid)
    await bank.record_play(gid, uid, net)
    if prize == 100:
        res = (f"{ARMS}{ARMS}{ARMS}\n## 🚨 BIG WINNER! 🚨\n# {ARMS} +100 {C} {ARMS}\n"
               "I'm checking it for counterfeits. With a magnifying glass. And spite.")
    elif prize:
        res = f"# {DANCE} MATCH 3! +{prize} {C} {DANCE}\n" + random.choice([
            "Free chips! Salsa sold separately.", "Scratch-off royalty. Don't let it go to your head.",
            "I grudgingly pay out. Very grudgingly.", "Congrats on the bare minimum."])
    else:
        res = "### 🗑️ No match.\n" + random.choice([
            "Disappointing. Very on brand.", "Better luck next time. (I control luck.)",
            "Saw that coming. Everyone saw that coming.", "Not even close. Like your tacos.",
            "Scratched it with your whole chest and got nothing. Iconic."])
    kind = "a paid ticket" if paid else "today's free ticket"
    foot = f"Paid {SCRATCH_PRICE} {C}" if paid else "Free card • next free one in 12 hours"
    msg = await send(f"🎟️ {u} scratches {kind}...\n# [ 🟫 | 🟫 | 🟫 ]")
    for frame in (f"[ {show[0]} | 🟫 | 🟫 ]", f"[ {show[0]} | {show[1]} | 🟫 ]"):
        await asyncio.sleep(1)
        await msg.edit(content=f"🎟️ {u} scratches {kind}...\n# {frame}")
    await asyncio.sleep(1)
    await msg.edit(content=f"🎟️ {u}\n# [ {' | '.join(show)} ]\n{res}\n-# {foot} • Chips: {w.chips} {C} • "
                           f"`buy scratch` for another ({SCRATCH_PRICE} {C}){test_note(message.channel) if prize else ''}",
                   view=buttons.view(("buy scratch", f"Buy another ({SCRATCH_PRICE})", "🎟️", discord.ButtonStyle.primary)))
    if prize:
        await send(embed=pic("scratch.gif"))


# ---------- Wheel of Fortaco ----------

SEGMENTS = ["🥑 +5", "💅 SOON KEEPS IT", "🍹 +10", "🐷 +20", "💅 SOON KEEPS IT", "🦑 +40", "🎟️ FREE SCRATCH", "🌮 +100 MEGA"]


async def wheel(channel, bank: Bank, gid: int, uid: int, forced: bool = False, delay: float = 0):
    if delay:
        await asyncio.sleep(delay)
    if not forced:
        if await bank.timer(gid, uid, "wheelcd"):
            return
    await bank.set_timer(gid, uid, "wheelcd", 900)
    u = f"<@{uid}>"
    await channel.send(embed=pic("wheel-of-fortaco.gif"))
    r = random.randrange(100)
    prize, land, free = 0, "💅 SOON KEEPS IT", False
    if r < 26:
        prize, land = 5, "🥑 +5"
    elif r < 46:
        prize, land = 10, "🍹 +10"
    elif r < 58:
        prize, land = 20, "🐷 +20"
    elif r < 65:
        prize, land = 40, "🦑 +40"
    elif r < 67:
        prize, land = 100, "🌮 +100 MEGA"
    elif r < 70:
        free, land = True, "🎟️ FREE SCRATCH-OFF"
    head = f"{DANCE} **WHEEL OF FORTACO!** {DANCE}\n{u} I spin the Wheel of Fortaco for you. Against my will.\n# 🎡 ▶ "
    msg = await channel.send(head + random.choice(SEGMENTS))
    for _ in range(4):
        await asyncio.sleep(1)
        await msg.edit(content=head + random.choice(SEGMENTS))
    await asyncio.sleep(1)
    if prize:
        w = await bank.add(gid, uid, "wheel of fortaco", chips=prize)
        res = (f"# {DANCE} +{prize} {C} {DANCE}\n" + random.choice([
            "I sigh and hand it over.", "Fine. FINE. Take it.", "The wheel has spoken. I am not happy about it.",
            "It's rigged. Against me. Somehow."]) + f"\n-# Chips: {w.chips} {C}" + test_note(channel))
    elif free:
        await bank.clear_timer(gid, uid, "scratchcd")
        res = ("### Your free scratch card is reset! Type `scratch` for another ticket.\n"
               "-# I'm filing a complaint with management. I am management.")
    else:
        res = "### " + random.choice(["I pocket it. Thanks for playing.", "Nothing! The house wins even the free spins.",
                                      "I blow on my nails. Better luck never.", "It's rigged. In my favor. As it should be."])
    await msg.edit(content=head + land + "\n" + res)
