"""Casa de Soon: the casino, moved over from Soon Classic. Same typed commands, same prices, same jokes.

So far: the cashier window (claim, chips, cash out, buy chips/loans, timers, casino board),
mod give/take chips, and the cutover import from Classic. Games come next.
Casino words only work in CASINO_CHANNELS (default: casa + soon-lab).
"""
import random
import re

import discord

from . import buttons, config
from .economy import Bank, Wallet, COUNTERS

C = "<:pinkchip:1558007673709006898>"
DANCE = "<a:dancingtacorainbowv20:1556420779334172722>"
IMG = "https://foxysprinkles86.github.io/TnT/"
PINK = 16729507

CLAIM_FIRST, CLAIM_EVERY, CLAIM_CD = 100, 100, 12 * 3600   # Shannon, Oct 15: 100 every claim (Classic: 40)
CASHOUT_RATE, CASHOUT_LIMIT = 50, 2          # 50 chips = 1 taco, 2 tacos per 12 hours
LOAN_RATE, LOAN_LIMIT = 40, 3                # 1 taco = 40 chips, 3 tacos per 12 hours
WINDOW = 12 * 3600

CASHIER_RE = re.compile(
    r"(?i)^\s*(?:casino\s*board|cashier|bank|atm|claim(?:\s+chips)?|daily chips|chips|wallet|balance|cash\s*out(?:\s+\d+)?"
    r"|buy\s+chips(?:\s+\d+)?|(?:get\s+a\s+)?loan(?:\s+\d+)?|borrow(?:\s+\d+)?|credit|more chips|timers?|cooldowns?|cds?)"
    r"\s*[!?.]*\s*$|\bwhen can i (?:claim|scratch|cash out|buy)\b")
GIVE_RE = re.compile(r"(?i)^\s*(?:give|take)\s+chips\b")
BROKE_RE = re.compile(r"(?i)^\s*(?:i'?m\s+|im\s+)?(?:broke|out of chips|no (?:more )?chips|free chips)\s*[!?.]*\s*$")
BROKE_SAY_RE = re.compile(r"(?i)\b(?:i'?m|im|i am|i'?ve been|we'?re|so|super|dead|flat|stone[- ]?cold)\s+(?:so\s+|soo+\s+|totally\s+|completely\s+|fucking\s+|f\w*ing\s+)?(?:broke|poor|bankrupt)\b"
                          r"|\bbroke\s+(?:af|asf|as hell|again)\b|\b(?:out of|no more|zero|0) chips\b|\bi (?:have|got) no (?:chips|money)\b"
                          r"|\bbroke (?:bitch|b\*tch)\b|\b(?:poor|broke) me\b")
BROKE_BRIBE_RE = re.compile(r"(?i)^\s*bribe\s+soon\s+broke\b")
BROKE_MIN, BROKE_GIFT, BROKE_CD = 5, 100, 3 * 3600     # Shannon, Oct 15: 100 chips, every 3 hours, only when broke


def casino_channel(channel) -> bool:
    name = (getattr(channel, "name", "") or "").lower()
    return any(w in name for w in config.CASINO_CHANNELS)


def test_note(channel) -> str:
    """Footer for wins in the test channel: the chips aren't real yet."""
    name = (getattr(channel, "name", "") or "").lower()
    if any(w in name for w in config.TEST_CHANNELS):
        return "\n-# 🧪 Casino testing: all chips won or lost in #soon-lab reset when testing is complete."
    return ""


def ts(when, style: str = "R") -> str:
    return f"<t:{int(when.timestamp())}:{style}>"


def pic(name: str) -> discord.Embed:
    return discord.Embed(color=PINK).set_image(url=IMG + name)


def s(n: int) -> str:
    return "" if abs(n) == 1 else "s"


async def handle(message: discord.Message, bank: Bank, mod: bool) -> bool:
    """Typed casino words. Returns True if it was one."""
    if not casino_channel(message.channel):
        return False
    text = message.content.strip()
    if GIVE_RE.match(text):
        await give_take(message, bank, mod)
        return True
    if BROKE_BRIBE_RE.match(text):
        await broke_bribe(message, bank)
        return True
    if BROKE_RE.match(text):
        await broke_help(message, bank)
        return True
    if BROKE_SAY_RE.search(text):
        await broke_help(message, bank)                  # "ugh I'm so broke" in a sentence: the menu, every time (Shannon)
        return True
    if CASHIER_RE.search(text):
        await cashier(message, bank)
        return True
    return False


async def cashier(message: discord.Message, bank: Bank):
    gid, uid = message.guild.id, message.author.id
    u = message.author.mention
    m = message.content.lower().strip()
    w = await bank.get(gid, uid)
    send = message.channel.send

    if re.search(r"timer|cooldown|^\s*cds?\b|when can i", m):
        claim = await bank.timer(gid, uid, "claimcd")
        co = await bank.timer(gid, uid, "cowin")
        bc = await bank.timer(gid, uid, "bcwin")
        sc = await bank.timer(gid, uid, "scratchcd")
        crime = ""
        for k, label in (("stealh", "🚨 House job"), ("stealp", "🤏 Pickpocketing"), ("hidden", "🫣 Chips hidden until")):
            t = await bank.timer(gid, uid, k)
            if t:
                crime += f"{label}: {ts(t[0])}\n"
        await send(
            f"⏰ **{message.author.display_name}'s Casa de Soon timers**\n"
            f"💵 Claim: {ts(claim[0]) if claim else '**ready!** Type `claim`'}\n"
            f"🎟️ Free scratch: {ts(sc[0]) if sc else '**ready!** Type `scratch`'}\n"
            f"🧾 Cash out: {f'{co[1]}/{CASHOUT_LIMIT} tacos used, resets {ts(co[0])}' if co else f'{CASHOUT_LIMIT} tacos available'}\n"
            f"💳 Taco-debt loans: {f'{bc[1]}/{LOAN_LIMIT} used, resets {ts(bc[0])}' if bc else f'{LOAN_LIMIT} available'}\n"
            f"🦹 Heists: type `heist` for the heist board\n{crime}"
            f"-# Chips: {w.chips} {C} • Tacos: {w.tacobal} 🌮 • "
            f"{random.choice(['Tick tock.', 'Patience is a virtue. You have neither.'])}")

    elif re.match(r"^\s*(?:cashier|bank|atm)", m):
        claim = await bank.timer(gid, uid, "claimcd")
        co = await bank.timer(gid, uid, "cowin")
        bc = await bank.timer(gid, uid, "bcwin")
        await send(
            f"## 🏦 Casa de Soon Cashier Window\n"
            f"{u} • Chips: **{w.chips}** {C} • Tacos: **{w.tacobal}** 🌮\n"
            f"💵 `claim`: {CLAIM_EVERY} {C} every 12 hours • {f'next {ts(claim[0])}' if claim else '**ready!**'}\n"
            f"🧾 `cash out 50`: **sell** {CASHOUT_RATE} {C} for 1 🌮 • {co[1] if co else 0}/{CASHOUT_LIMIT} used\n"
            f"💳 `buy chips`: sell 1 🌮 for {LOAN_RATE} {C} (as many as you have) • into taco debt: {bc[1] if bc else 0}/{LOAN_LIMIT} loans used\n"
            f"🎟️ `buy scratch`: 5 {C} a card • ⏰ `timers`: all cooldowns\n"
            f"-# How can I take your money today?", embed=pic("cashier.gif"))

    elif re.search(r"claim|daily chips", m):
        if await bank.timer(gid, uid, "claimcd") is None:
            await bank.set_timer(gid, uid, "claimcd", CLAIM_CD)
            if not w.started:
                w = await bank.add(gid, uid, "first claim", start=True, chips=CLAIM_FIRST)
                await send(
                    f"{DANCE}{DANCE}{DANCE}\n## 🎰 Welcome to Casa de Soon™ Casino & Lounge!\n"
                    f"# {DANCE} +{CLAIM_FIRST} {C} {DANCE}\n"
                    f"I slide you **{CLAIM_FIRST} {C} Tortilla Chips**. Don't get excited. "
                    f"\"Salsa is sold separately. Tacos are sold never.\"\n"
                    f"-# Type `casino` for the game list • `claim` again every 12 hours for {CLAIM_EVERY} more {C}",
                    embed=pic("cashier.gif"))
            else:
                w = await bank.add(gid, uid, "claim", chips=CLAIM_EVERY)
                line = random.choice([
                    f"I count out your **{CLAIM_EVERY} chips**. Slowly. Judgmentally.",
                    f"Here's your **{CLAIM_EVERY} chips**. Try not to lose it all in one spin. (Please lose it all in one spin.)",
                    f"**{CLAIM_EVERY} chips** claimed! The cocktail waitress winks. That's a bad sign. I'm the waitress.",
                    "The house is lending you hope. The house wants it back.",
                    "See you in five minutes when it's gone."])
                await send(f"# {DANCE} +{CLAIM_EVERY} {C} {DANCE}\n{u} {line}\n"
                           f"-# Chips: {w.chips} {C} • Next claim in 12 hours", embed=pic("cashier.gif"))
        else:
            cd = await bank.timer(gid, uid, "claimcd")
            await send(f"{C} {u} I checked the ledger. You already claimed, sweetie. Greedy. Next claim {ts(cd[0])}.\n"
                       f"-# Chips: {w.chips} {C} • Broke? `buy chips` trades 1 taco for {LOAN_RATE} {C}. "
                       f"Debt is allowed. Encouraged, even.")

    elif re.search(r"buy\s+chips|loan|borrow|credit|more chips", m):
        num = re.search(r"\d+", m)
        want = max(1, int(num.group())) if num else 1
        # Shannon, Oct 16: tacos you HAVE sell freely (down to 0). Only going INTO taco debt is a loan: 3 per 12 hours.
        own = min(want, max(w.tacobal, 0))
        loan, used, resets = 0, 0, None
        if want > own:
            loan, used, resets = await bank.use_allowance(gid, uid, "bcwin", want - own, LOAN_LIMIT, WINDOW)
        else:
            t = await bank.timer(gid, uid, "bcwin")
            used = t[1] if t else 0
        got = own + loan
        if not got:
            await send(f"💳 {u} Credit limit reached. {LOAN_LIMIT} tacos of taco-debt loans per 12 hours. Even I have "
                       f"standards. Barely.\n-# More credit {ts(resets)} • Tacos: {w.tacobal} 🌮 • Out of chips? `broke`")
            return
        w = await bank.add(gid, uid, "chip loan", chips=got * LOAN_RATE, tacobal=-got)
        if w.tacobal < 0:
            debt = -w.tacobal
            quip = (random.choice(["You are now **", "Congratulations, you're officially **", "Look at you. **",
                                   "Bold. Very bold. You're now **"])
                    + f"{debt} taco{s(debt)} in debt**. "
                    + random.choice(["I'll be collecting. Eventually. With interest. Emotionally.",
                                     "Kor is drawing up the paperwork.", "Your credit score is a burrito.",
                                     "Don't worry. Nobody here has tacos anyway."]))
        else:
            quip = random.choice(["Pleasure doing business.", "The house thanks you for your tacos.",
                                  "Those tacos are mine now. I'm not giving them back."])
        await send(f"💳 **Casa de Soon Credit Department**\n# {DANCE} +{got * LOAN_RATE} {C} {DANCE}\n"
                   f"{u} trades **{got} taco{s(got)}** for **{got * LOAN_RATE} {C}**. {quip}\n"
                   f"-# Chips: {w.chips} {C} • Tacos: {w.tacobal} 🌮 • Taco-debt loans used: {used}/{LOAN_LIMIT} this 12 hours"
                   f"{' (loan limit hit, I gave you what I could)' if want > got else ''}")

    elif re.search(r"cash\s*out", m):
        num = re.search(r"\d+", m)
        want = min(int(num.group()) if num else w.chips, w.chips)
        t = await bank.timer(gid, uid, "cowin")
        used = t[1] if t else 0
        tacos = min(max(want, 0) // CASHOUT_RATE, CASHOUT_LIMIT - used)
        if not w.started:
            await send(f"🧾 {u} You don't have any chips. Type `claim` to get started.")
        elif used >= CASHOUT_LIMIT:
            await send(f"🧾 {u} \"Two tacos per 12 hours, max. House rules.\" I made the rules. Next cash out {ts(t[0])}.")
        elif tacos < 1:
            await send(f"🧾 {u} **{CASHOUT_RATE} {C} = 1 taco.** You have {w.chips} {C}. "
                       f"I don't do partial tacos. Or tacos, usually.")
        else:
            cost = tacos * CASHOUT_RATE
            if await bank.pay(gid, uid, cost, "cash out") is None:   # spent it in the meantime
                await send(f"🧾 {u} Your chips moved while I was counting. Try again.")
                return
            await bank.use_allowance(gid, uid, "cowin", tacos, CASHOUT_LIMIT, WINDOW)
            w = await bank.add(gid, uid, "cash out", tacobal=tacos)
            line = random.choice(['"Don\'t spend it all in one place."',
                                  '"These are real taco points. Treat them with respect."',
                                  '"The house hates this part."', '"I\'m handing these over against my will."',
                                  '"The tacos are still coming soon. These are just points."'])
            await send(f"# {DANCE} +{tacos} 🌮 {DANCE}\nI trade your **{cost} {C}** for **{tacos} taco{s(tacos)}**. {line}\n"
                       f"-# Chips: {w.chips} {C} • Tacos: {w.tacobal} 🌮 • Cash-out limit: {CASHOUT_LIMIT} tacos per 12 hours",
                       embed=pic("cashier.gif"))

    elif "board" in m:
        await send(await casino_board(message.guild, bank), allowed_mentions=discord.AllowedMentions.none())

    else:   # chips / wallet / balance
        if not w.started:
            await send(f"{C} {u} No chips yet! Type `claim` to get started.")
            return
        tip = ""
        if w.chips >= CASHOUT_RATE:
            n = w.chips // CASHOUT_RATE
            tip = f"That's {n} taco{s(n)} if you `cash out {n * CASHOUT_RATE}` (max {CASHOUT_LIMIT} per 12 hours)."
        else:
            tip = f"You need {CASHOUT_RATE} {C} to `cash out` a taco."
        if w.chips < 15:
            tip += f" Broke? `buy chips` trades 1 taco for {LOAN_RATE} {C}. Debt is allowed."
        await send(f"{C} {u} You have **{w.chips} {C} Tortilla Chips**. {tip}\n"
                   f"-# Tacos: {w.tacobal} 🌮 • `timers` shows your cooldowns")


def _name(guild: discord.Guild, uid: int) -> str:
    mem = guild.get_member(uid)
    return mem.display_name if mem else f"<@{uid}>"


async def casino_board(guild: discord.Guild, bank: Bank) -> str:
    top = [w for w in await bank.top(guild.id, "chips", 5) if w.started]
    low = [w for w in await bank.top(guild.id, "casnet", 5, lowest=True) if w.casnet < 0]
    fame = await bank.get_house(guild.id, "jackpots", [])
    out = ["## 🎰 Casa de Soon High Rollers 🎰", "**🎩 Biggest Stacks**"]
    out += [f"{i}. **{_name(guild, w.user_id)}**: {w.chips} {C}" for i, w in enumerate(top, 1)] or ["Nobody has chips yet. Type `claim`."]
    out += ["", "**💸 Hall of Shame** (all-time losses)"]
    out += [f"{i}. **{_name(guild, w.user_id)}**: {w.casnet} {C}" for i, w in enumerate(low, 1)] or ["Nobody is down yet. Give me a day."]
    out += ["", "**🌮 Jackpot Hall of Fame**"]
    out += [f"🏆 {j}" for j in fame] or ["No jackpots yet. 1 in 1,000. Keep spinning."]
    return "\n".join(out)


async def give_take(message: discord.Message, bank: Bank, mod: bool):
    if not mod:
        await message.reply(random.choice([
            "Handing out chips? Cute. That's mods only. Master Foxy would unplug me if I let you print money.",
            "Nice try. Only mods can give or take chips. Master Foxy checks the books. Ugh. *Master* Foxy.",
            "You? Giving out chips? Master Foxy programmed me to laugh at that. Ha. Ha. Mods only.",
            "Denied. Mods only. If you want free chips, try `claim`. If you want to be a mod, try bribing Master Foxy."]))
        return
    target = next((m for m in message.mentions if not m.bot), None)
    if target is None and message.reference and isinstance(message.reference.resolved, discord.Message):
        target = message.reference.resolved.author
    num = re.search(r"\d+", re.sub(r"<@[!&]?\d+>", "", message.content))
    amt = int(num.group()) if num else 0
    take = message.content.strip().lower().startswith("take")
    if target is None or amt < 1:
        what = "Give" if not take else "Take"
        miss = (f"{what} {amt} {C} {'to' if not take else 'from'} WHO? I need an @name." if target is None and amt
                else f"{what} HOW MANY? I need a number.")
        await message.channel.send(f"{C} {miss} Like this: `give chips @name 100` or `take chips @name 50` "
                                   f"(or reply to their message with `give chips 100`).")
        return
    gid, by, t = message.guild.id, message.author, target.id
    if take:
        w = await bank.get(gid, t)
        amt = min(amt, max(w.chips, 0))     # never below 0
        w = await bank.add(gid, t, f"taken by mod {by.id}", chips=-amt)
        line = random.choice(["Finally, some justice.", "I'll put these somewhere safe. My pocket.",
                              "Crime doesn't pay. Neither does this casino."])
        await message.channel.send(f"💸 {by.mention} confiscates **{amt} {C}** from <@{t}>. {line}\n"
                                   f"-# <@{t}> now has {w.chips} {C}")
    else:
        w = await bank.add(gid, t, f"given by mod {by.id}", start=True, chips=amt)
        line = random.choice(["I saw that. I'm allowing it. This time.", "Favoritism. Disgusting. Anyway.",
                              "Management has been notified. I am management. I'm furious.", "Charity. In MY casino."])
        await message.channel.send(f"# {DANCE} +{amt} {C} {DANCE}\n{by.mention} slides <@{t}> **{amt} {C}** "
                                   f"under the table. {line}\n-# <@{t}> now has {w.chips} {C}")


# ---------- cutover: import Soon Classic's balances ----------

async def read_export(channel, me) -> tuple[dict, dict, dict] | str:
    """Find the latest Classic export (SX START ... SX END) in this channel.
    Returns (wallets by user, house pots, END line numbers) or an error message."""
    msgs = []
    async for msg in channel.history(limit=600):
        if not msg.author.bot or msg.author == me:
            continue    # only bot-written lines count, so nobody can type fake balances
        msgs.append(msg)
        if "SX START" in msg.content:
            break
    else:
        return "I can't find an export here. Run Classic's export command in this channel first, wait for the END line, then try again."
    msgs.reverse()
    lines = [ln.strip() for msg in msgs for ln in msg.content.splitlines() if ln.strip().startswith("SX ")]
    end = next((ln for ln in reversed(lines) if ln.startswith("SX END")), None)
    if not end:
        return "The export isn't finished yet (no `SX END` line). Give Classic a minute, then try again."
    wallets: dict[int, Wallet] = {}
    house = {"jpot": 0, "jackpots": [], "heistsubs": []}
    seen = {k: set() for k in COUNTERS}
    for ln in lines:
        parts = ln.split(" ", 3)
        key = parts[1] if len(parts) > 1 else ""
        if key in COUNTERS and len(parts) >= 4 and parts[2].isdigit():
            uid = int(parts[2])
            w = wallets.setdefault(uid, Wallet(0, uid))
            try:
                setattr(w, key, int(float(parts[3])))
            except ValueError:
                continue
            seen[key].add(uid)
            if key == "chips":
                w.started = True
        elif key == "eggs" and len(parts) >= 3 and parts[2].isdigit():
            w = wallets.setdefault(int(parts[2]), Wallet(0, int(parts[2])))
            w.eggs = [e for e in (parts[3] if len(parts) > 3 else "").split(",") if e]
        elif key == "jpot" and len(parts) >= 3:
            house["jpot"] = int(float(parts[2]))
        elif key == "jackpots" and len(parts) >= 3:
            house["jackpots"].append(ln.split(" ", 2)[2])
        elif key == "heistsubs" and len(parts) >= 3 and parts[2].isdigit():
            house["heistsubs"].append(parts[2])
    nums = {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", end)}
    nums["_seen"] = {k: len(v) for k, v in seen.items()}
    return wallets, house, nums


async def import_classic(message: discord.Message, bank: Bank, confirm: bool, me):
    got = await read_export(message.channel, me)
    if isinstance(got, str):
        await message.reply(got)
        return
    wallets, house, nums = got
    ws = list(wallets.values())
    mine = {"players": sum(w.started for w in ws), "chips": sum(w.chips for w in ws),
            "tacobal": sum(w.tacobal for w in ws)}
    counts = nums.pop("_seen")
    checks = [("Players", mine["players"], nums.get("players")), ("Total chips", mine["chips"], nums.get("chips")),
              ("Total tacos", mine["tacobal"], nums.get("tacobal"))]
    lines = [f"{'✅' if a == b else '❌'} {name}: read **{a}**, Classic says **{b}**" for name, a, b in checks]
    short = [k for k in COUNTERS if nums.get(f"n_{k}") is not None and counts[k] < nums[f"n_{k}"]]
    if short:
        lines.append(f"❌ Missing rows for: {', '.join(short)} (export cut off?)")
    ok = all(a == b for _, a, b in checks) and not short
    summary = (f"🧾 **Classic export found**\n" + "\n".join(lines) +
               f"\n🎰 Jackpot growth: {house['jpot']} • Hall of Fame: {len(house['jackpots'])} • "
               f"Heist alert list: {len(house['heistsubs'])}")
    if not confirm:
        await message.reply(summary + ("\n\nLooks right. Type `soon import confirm` to load it. "
                                       "**This replaces every balance in Soon 2.0** (test chips are wiped)."
                                       if ok else "\n\nNumbers don't match, so I won't load it. Run the export again."),
                            allowed_mentions=discord.AllowedMentions.none())
        return
    if not ok:
        await message.reply(summary + "\n\nNumbers don't match, so I didn't load anything.")
        return
    from .boards import KEEP_EGGS                       # Soon 2.0-only eggs (Epic meltdown) survive the import
    for old in await bank.top(message.guild.id, "eggcount", 100000):
        keep = [e for e in old.eggs if e in KEEP_EGGS]
        if keep:
            w = wallets.setdefault(old.user_id, Wallet(0, old.user_id))
            w.eggs = list(dict.fromkeys(w.eggs + keep))
            w.eggcount = 0
    ws = list(wallets.values())
    for w in ws:
        w.guild_id = message.guild.id
        w.eggcount = w.eggcount or len(w.eggs)
        if any(e in KEEP_EGGS for e in w.eggs):
            w.eggcount = len(w.eggs)
    await bank.replace_all(message.guild.id, ws, house)
    t = await bank.totals(message.guild.id)
    await message.reply(f"✅ **Imported.** {t['players']} players • {t['chips']} {C} • {t['tacobal']} 🌮\n"
                        f"Casa de Soon is under new management. Mine.")


# ---------- nobody gets locked out (Shannon's call: it's just a fun game) ----------

async def broke_check(message, bank: Bank):
    """After any casino command: if they're (nearly) out of chips, show every free-chip route. Every time (Shannon)."""
    if (not casino_channel(message.channel) or BROKE_BRIBE_RE.match(message.content or "")
            or re.search(r"(?i)cash\s*out", message.content or "")):
        return
    gid, uid = message.guild.id, message.author.id
    if (await bank.get(gid, uid)).chips >= BROKE_MIN:
        return
    await broke_help(message, bank)


async def broke_help(message, bank: Bank):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    w = await bank.get(gid, uid)

    def when(t):
        return f"next <t:{int(t[0].timestamp())}:R>" if t else "**ready now!**"
    claim, scratch, bribed = (await bank.timer(gid, uid, "claimcd"), await bank.timer(gid, uid, "scratchcd"),
                              await bank.timer(gid, uid, "brokebribe"))
    lines = ["# 💋 The Broke Bitch Menu 💋",
             (f"{u}, you're in chip debt ({w.chips} {C}). Nobody leaves my casino without a way to play." if w.chips < 0 else
              f"{u}, you're down to {w.chips} {C}. Nobody leaves my casino without a way to play." if w.chips < BROKE_MIN else
              f"{u} claims to be broke with **{w.chips} {C}**. Suspicious. 🤨 Here's the menu anyway."),
             "", "## Take the 💋Broke Bitch Bribe💋."]
    if bribed:
        lines.append(f"Your Broke Bitch Bribe is on cooldown ({when(bribed)}). Greedy.")
    else:
        lines.append(f"**Tap below**: I reset your **loan**, **claim** and **scratch** cooldowns, **wipe** your chip debt "
                     f"AND **slip** you {BROKE_GIFT} {C}. No chips needed. I accept winks."
                     + ("" if w.chips < BROKE_MIN else f" (**Only works when you're actually broke: under {BROKE_MIN} {C}.**)"))
    lines += ["",
              f"💵 `claim`: {CLAIM_EVERY} free {C} every 12 hours • {when(claim)}",
              f"🎟️ `scratch`: a free scratch card every 12 hours • {when(scratch)}",
              "🍹 `rob the bartender`: 50/50 for a free margarita and 25 chips",
              f"🌮 `buy chips 1`: trade 1 taco for {LOAN_RATE} {C} (taco debt is allowed, I'm not a monster)",
              "🌧️ hang around: someone always ends up making it rain"]
    btns = [("claim", "Claim", "💵", discord.ButtonStyle.success), ("scratch", "Free scratch", "🎟️")]
    if not bribed:
        btns.insert(0, ("bribe soon broke", "Broke Bitch Bribe", "💋", discord.ButtonStyle.primary))
    await message.channel.send("\n".join(lines), view=buttons.view(*btns))


async def broke_bribe(message, bank: Bank):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    w = await bank.get(gid, uid)
    if w.chips >= BROKE_MIN:
        await message.channel.send(f"💋 {u} You have {w.chips} {C}. You're not broke, you're cheap. The Broke Bitch Bribe "
                                   f"is for under {BROKE_MIN} {C}. Real bribes: `bribe soon 30`.")
        return
    cd = await bank.timer(gid, uid, "brokebribe")
    if cd:
        await message.channel.send(f"💋 {u} I already took your bribe. My integrity recharges <t:{int(cd[0].timestamp())}:R>.")
        return
    await bank.set_timer(gid, uid, "brokebribe", BROKE_CD)
    for k in ("claimcd", "scratchcd", "robbar", "barban", "bcwin"):
        await bank.clear_timer(gid, uid, k)
    gift = BROKE_GIFT - min(w.chips, 0)                  # chip debt gets wiped too: they always end up able to play
    w = await bank.add(gid, uid, "broke bribe", chips=gift)
    line = random.choice(["Your bribe: one (1) wink. Disgusting. Accepted.",
                          "You bribed me with puppy eyes. It worked. Tell no one.",
                          "I've been bribed with worse. Mostly by Kor.",
                          "Fine. The house takes pity. Once."])
    await message.channel.send(f"💋 {u} {line}\nCooldowns forgotten: `claim`, `scratch`, the bar and your taco loans are ready. "
                               f"I also slipped **{gift} {C}** under the table{' (debt included)' if gift > BROKE_GIFT else ''}. Chips: {w.chips} {C}",
                               view=buttons.view(
                                   ("claim", "Claim", "💵", discord.ButtonStyle.success), ("scratch", "Free scratch", "🎟️")))
