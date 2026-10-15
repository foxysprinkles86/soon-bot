"""Crimes, moved over from Soon Classic. Secret on purpose: only the `crimes` DM menu lists them.
steal chips (rob the house) • steal chips @name • snitch @name • hide chips • pickpocket kor • bribe soon 30.
Failed crimes can push you into chip debt, like Classic."""
import random
import re

import discord

from . import buttons
from .casino import C, DANCE, casino_channel, test_note
from .economy import Bank

CD = 600            # 10 minutes between steal attempts (house and players are separate)
STOLE = 900         # "recent thief" window for snitches
ROBBED = 3600       # a robbed player can't be robbed again for an hour
HIDE, HIDE_COST = 3600, 5

MENU_RE = re.compile(r"(?i)^\s*crimes?\s*[!?.]*\s*$")
CRIME_RE = re.compile(r"(?i)^\s*(?:steal|snitch|pick\s*pocket|bribe)\b.*$|^\s*hide\s+(?:my\s+)?chips\s*[!.]*\s*$")


def is_kor_name(user) -> bool:
    return "korehaan" in (getattr(user, "name", "") or "").lower()


def _line(user, lines: list[str]) -> str:
    """A random flavor line. When Kor is the one doing the crime, skip the lines starring Kor
    (Classic once had Kor "ratted out by Kor for a churro")."""
    if is_kor_name(user):
        lines = [l for l in lines if "Kor" not in l] or lines
    return random.choice(lines)


async def handle(message, bank: Bank, mod: bool) -> bool:
    if not casino_channel(message.channel):
        return False
    text = message.content.strip()
    if MENU_RE.match(text):
        await menu(message)
        return True
    if not CRIME_RE.match(text):
        return False
    low = text.lower()
    if low.startswith("steal"):
        await steal(message, bank)
    elif low.startswith("snitch"):
        await snitch(message, bank)
    elif low.startswith("hide"):
        await hide(message, bank)
    elif low.startswith("pick"):
        await pickpocket_kor(message, bank)
    else:
        await bribe(message, bank)
    return True


def target_of(message) -> int | None:
    m = re.search(r"<@!?(\d+)>", message.content)
    return int(m.group(1)) if m else None


async def menu(message):
    try:
        await message.author.send(
            "🕵️ **Casa de Soon: The Back Room**\nYou didn't hear any of this from me.\n"
            "⌨️ Type these in the casino, not here. I don't do crimes in DMs.\n\n"
            "🦹 `steal chips`: rob the house. Could be 25. Could be 100. Could be a fine.\n"
            "🤏 `steal chips @name`: rob a player. Get caught and you pay *them*. Debt is a lifestyle.\n"
            f"🫣 `hide chips`: {HIDE_COST} {C}. Nobody can rob you for an hour.\n"
            "🐀 `snitch @name`: rat out a recent thief for a reward. Lie and you pay.\n"
            "💸 `bribe soon 30`: the more you bribe, the more likely I forget your cooldowns.\n"
            "💰 `bribe soon grand 50`: feed the shared bribe pot. Big enough pot and I forget the Grand Heist cooldown. For everyone.\n"
            f"🍹 `rob the bartender`: a free margarita and 25 {C}. Or a bar ban.\n"
            "🤝 `pickpocket kor`: go ahead. Try it.\n\n-# Rules? There are rules. I just don't tell anyone what they are.")
        sent = True
    except (discord.Forbidden, discord.HTTPException):
        sent = False
    try:
        await message.delete()
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        pass
    await message.channel.send(
        f"🤫 {message.author.mention} " + ("Check your DMs. And delete this conversation from your memory." if sent
                                            else "I tried to DM you the back-room menu, but your DMs are locked. Open them and try again."),
        delete_after=8)


async def steal(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    t = target_of(message)
    member = message.guild.get_member(t) if t else None
    if t is None or (member is not None and member.bot) or t == getattr(message.guild.me, "id", 0):
        await steal_house(message, bank)
        return
    if t == me:
        await message.channel.send(f"🤏 {u} You tried to rob yourself. You succeeded. Nothing happened. "
                                   "That's the saddest crime I've ever seen.")
        return
    v = f"<@{t}>"
    cd = await bank.timer(gid, me, "stealp")
    if cd:
        await message.channel.send(f"🚨 {u} You're still on the security cam rewind. Next pickpocket attempt <t:{int(cd[0].timestamp())}:R>.")
        return
    robbed = await bank.timer(gid, t, "robbed")
    if robbed:
        await message.channel.send(f"🙏 {u} {v} just got robbed. Even thieves have a code. Try again <t:{int(robbed[0].timestamp())}:R>.")
        return
    hidden = await bank.timer(gid, t, "hidden")
    if hidden:
        await message.channel.send(f"🫣 {u} {v} hid their chips. I don't know where. I know exactly where. I'm not telling. "
                                   f"Try again <t:{int(hidden[0].timestamp())}:R>.")
        return
    vc = (await bank.get(gid, t)).chips
    if vc < 10:
        await message.channel.send(f"🥲 {u} {v} has {vc} {C}. Robbing them would be sad. Even for you.")
        return
    amt = max(1, vc * random.randint(10, 50) // 100)
    await bank.set_timer(gid, me, "stealp", CD)
    if random.randrange(2) == 0:
        await bank.set_timer(gid, me, "stole", STOLE)
        await bank.set_timer(gid, t, "robbed", ROBBED)
        vw = await bank.add(gid, t, f"robbed by {me}", chips=-amt)
        w = await bank.add(gid, me, f"robbed {t}", chips=amt)
        await message.channel.send(
            f"🤏 {u} " + _line(message.author, ["bumps into", "\"accidentally\" trips", "hugs", "asks for directions from"]) +
            f" {v} and walks away **{amt} {C}** richer.\n# {DANCE} +{amt} {C} STOLEN {DANCE}\n{v} " + _line(message.author, [
                "you've been robbed. I saw the whole thing. I did nothing.",
                "check your pockets. Actually, don't. It'll just make you sad.",
                "you can't be robbed again for an hour. Small mercies.",
                "maybe `hide chips` next time. Just a thought. From me. The house."]) +
            f"\n-# Thief: {w.chips} {C} • Victim: {vw.chips} {C} • Someone could always `snitch`..." + test_note(message.channel))
    else:
        w = await bank.add(gid, me, f"caught robbing {t}", chips=-amt)
        vw = await bank.add(gid, t, f"{me} got caught robbing them", chips=amt)
        debt = f" You couldn't cover it, so I took your dignity too. You're **{-w.chips} {C}** in debt." if w.chips < 0 else ""
        await message.channel.send(
            f"🚨 {u} tries to rob {v} and gets **CAUGHT**.\n# 💸 -{amt} {C} → {v}\n" + _line(message.author, [
                "The victim keeps the loot. Justice. Rare, beautiful justice.",
                "You pay them what you tried to take. I love this part.",
                "Kor saw everything. Kor is a terrible witness but a great snitch."]) + debt +
            f"\n-# Thief: {w.chips} {C} • {v}: {vw.chips} {C}")


async def steal_house(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    cd = await bank.timer(gid, me, "stealh")
    if cd:
        await message.channel.send(f"🚨 {u} Security is still looking at your face. Next attempt on the house <t:{int(cd[0].timestamp())}:R>.")
        return
    r = random.randrange(100)
    amt = random.randint(71, 100) if r >= 90 else random.randint(41, 70) if r >= 60 else random.randint(25, 40)
    await bank.set_timer(gid, me, "stealh", CD)
    if random.randrange(2) == 0:
        await bank.set_timer(gid, me, "stole", STOLE)
        w = await bank.add(gid, me, "robbed the house", chips=amt)
        await message.channel.send(
            f"🦹 {u} " + _line(message.author, [
                "slips behind the cashier counter while I'm refilling margaritas...",
                "crawls through the air vent above the slot machines...",
                "distracts me with a compliment and reaches for the chip drawer...",
                "pretends to be Kor. It works. That's embarrassing for everyone."]) +
            f"\n# {DANCE} +{amt} {C} STOLEN {DANCE}\n" + _line(message.author, [
                "I'll be reviewing the security footage. Personally. All night.",
                "That's coming out of Kor's paycheck. Kor doesn't get a paycheck. Still.",
                "Enjoy them. They're cursed now.", "You think you got away with it. Cute."]) +
            f"\n-# Chips: {w.chips} {C}" + test_note(message.channel))
    else:
        w = await bank.add(gid, me, "caught robbing the house", chips=-amt)
        tail = (f"You couldn't cover the fine, so I took your dignity too. You're **{-w.chips} {C}** in debt now."
                if w.chips < 0 else _line(message.author, [
                    "Fine paid. Crime doesn't pay. I do. Badly.", "The house always wins. Especially against you.",
                    "Next time wear a better disguise. Or any disguise."]))
        await message.channel.send(
            f"🚨 {u} " + _line(message.author, [
                "reaches for the chip drawer and finds my hand already there.",
                "trips the laser alarm. There are no lasers. I just know.",
                "gets caught on camera. It's a camera made of tacos, but it works.",
                "gets ratted out by Kor for a churro."]) +
            f"\n# 💸 CAUGHT! -{amt} {C}\n{tail}\n-# Chips: {w.chips} {C}")


async def snitch(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    t = target_of(message)
    if t is None:
        await message.channel.send(f"🐀 {u} Snitch on WHO? `snitch @name`. I need names. For my records. For reasons.")
        return
    if t == me:
        await message.channel.send(f"🐀 {u} You snitched on yourself. I respect the honesty. I'm still not giving you anything.")
        return
    v = f"<@{t}>"
    if await bank.timer(gid, t, "stole"):
        await bank.clear_timer(gid, t, "stole")
        sw = await bank.add(gid, me, "snitch reward", chips=50)
        vw = await bank.add(gid, t, "snitched on", chips=-25)
        await message.channel.send(
            f"🐀 {u} rats out {v}. **And they're right.**\n# 💰 +50 {C} reward\n{v} is fined **25 {C}**. " + _line(message.author, [
                "Snitches get rewards. Thieves get fines. Everyone gets judged.",
                "I love a good betrayal. It's like a telenovela in here.",
                "Kor is taking notes. Kor wants to be you when he grows up."]) +
            f"\n-# {message.author.display_name}: {sw.chips} {C} • {v}: {vw.chips} {C}" + test_note(message.channel))
    else:
        sw = await bank.add(gid, me, "false snitch", chips=-50)
        vw = await bank.add(gid, t, "falsely accused", chips=50)
        await message.channel.send(
            f"🐀 {u} accuses {v} of theft. **They're innocent.** (Recently, anyway.)\n# 💸 -50 {C} → {v}\n" + _line(message.author, [
                "False accusations are expensive. Pay up, rat.", "Slander! In MY casino! Pay the poor soul.",
                "Wrong. So wrong. Your 50 chips have a new home."]) +
            f"\n-# {message.author.display_name}: {sw.chips} {C} • {v}: {vw.chips} {C}")


async def hide(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    hidden = await bank.timer(gid, me, "hidden")
    if hidden:
        await message.channel.send(f"🫣 {u} Your chips are already hidden until <t:{int(hidden[0].timestamp())}:R>. "
                                   "Under the mattress. Behind the salsa. I'm not saying.")
        return
    w = await bank.pay(gid, me, HIDE_COST, "hid chips")
    if w is None:
        have = (await bank.get(gid, me)).chips
        await message.channel.send(f"🫣 {u} Hiding costs {HIDE_COST} {C} and you have {have}. There's nothing to hide. Including your shame.")
        return
    await bank.set_timer(gid, me, "hidden", HIDE)
    until = (await bank.timer(gid, me, "hidden"))[0]
    await message.channel.send(
        f"🫣 {u} " + _line(message.author, [
            "stuffs their chips into a tortilla and hides it in the van.",
            "buries their chips under the casino floor. I'm charging for the hole.",
            "hands their chips to Kor for safekeeping. Bold. Very bold."]) +
        f"\n**Nobody can rob you for 1 hour.** (Ends <t:{int(until.timestamp())}:R>.)\n-# Hiding fee: -{HIDE_COST} {C} • Chips: {w.chips} {C}")


async def pickpocket_kor(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    if not re.search(r"(?i)\bkor\b", message.content):
        await message.channel.send(f"🤝 {u} Pickpocket who? The only pocket worth picking around here is `pickpocket kor`.")
        return
    if is_kor_name(message.author):
        await message.channel.send(f"🤝 {u} You can't pickpocket yourself, Kor. We've discussed this. Twice. There was a whiteboard.")
        return
    w = await bank.add(gid, me, "pickpocketed Kor (Kor tax)", chips=-1)
    kor = next((m for m in getattr(message.guild, "members", []) if is_kor_name(m)), None)
    if kor is not None:
        await bank.add(gid, kor.id, "Kor tax", chips=1)
    await message.channel.send(
        f"🤝 {u} " + random.choice([
            "reaches into Kor's pocket and pulls out... churro crumbs. And a receipt for more churros.",
            "pickpockets Kor and finds a single pink chip. It's mine. I'm taking it back. Plus one of yours.",
            "tries to pickpocket Kor. Kor doesn't have pockets. Kor has a fanny pack full of salsa packets.",
            "gets their hand stuck in Kor's pocket. It's sticky in there. Don't ask."]) +
        f"\n-# Kor tax: -1 {C} (it went straight into Kor's fanny pack) • Chips: {w.chips} {C}")


GRAND_BRIBE_RE = re.compile(r"(?i)\b(?:grand|heist)\b")


async def grand_bribe(message, bank: Bank, n: int):
    """Shannon's add: a SHARED bribe pot to make Soon forget the server-wide Grand Heist cooldown.
    Everyone's chips go into one pot; each time someone adds, Soon rolls with the WHOLE pot: every 2 chips = 1%
    (max 75%). No = the pot stays and keeps growing. Yes = the cooldown is gone for everyone, the crew is named,
    the pot empties. If the cooldown runs out on its own first, Soon keeps the pot. A "Match" button chips in the
    first briber's amount. Only charges you while a cooldown is running. Pot in house kv `gbribe`."""
    from .heists import HOUSE, PLANS
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    ck = PLANS["g"]["ck"]
    cd = await bank.timer(gid, HOUSE, ck)
    if not cd:
        await bank.set_house(gid, "gbribe", None)
        await message.channel.send(f"💰 {u} There's no Grand Heist cooldown to forget. Go rob something. `grand`")
        return
    if n < 2:
        await message.channel.send(f"💰 {u} Making the cops forget a Grand Heist costs real chips. `bribe soon grand 100`. "
                                   "Every 2 chips in the pot buys 1% of my silence. Your crew can chip in too.")
        return
    until = int(cd[0].timestamp())
    pot = await bank.get_house(gid, "gbribe") or {}
    if pot.get("until") != until:                      # a new cooldown: Soon kept the old pot
        pot = {"until": until, "pot": 0, "first": n, "who": {}}
    w = await bank.pay(gid, me, n, "grand heist bribe pot")
    if w is None:
        have = (await bank.get(gid, me)).chips
        await message.channel.send(f"💰 {u} You're offering {n} {C} and you have {have}. The cops can count. So can I.")
        return
    pot["pot"] += n
    pot["who"][str(me)] = pot["who"].get(str(me), 0) + n
    odds = min(pot["pot"] // 2, 75)
    crew = " ".join(f"<@{x}>" for x in pot["who"])
    if random.randrange(100) < odds:
        await bank.clear_timer(gid, HOUSE, ck)
        await bank.set_house(gid, "gbribe", None)
        await buttons.retire(f"gbribe:{gid}")
        await message.channel.send(
            f"💰 {u} slides me **{n} {C}**. That makes **{pot['pot']} {C}** in the pot. I make a phone call. I whisper. "
            "I hang up.\n# 🚔 The cops just... left.\nThe **Grand Heist** is open again. For everyone. " + random.choice([
                "Nobody saw anything.", "The donut shop across town had a sudden emergency.", "I have friends in low places."])
            + f" Type `grand`.\n🦹 **The bribe crew:** {crew}\n-# Pot: {pot['pot']} {C} ({odds}% odds) • Your chips: {w.chips} {C}")
        return
    await bank.set_house(gid, "gbribe", pot)
    match = pot["first"]
    msg = await message.channel.send(
        f"💰 {u} slides **{n} {C}** into the bribe pot. I count it twice. I look at the cops. The cops look at me.\n"
        f"# 🙅 Not yet.\n" + random.choice(["The cops want more. So do I.", "Getting warmer. Keep feeding the pot.",
                                            "That's not silence money yet. That's a tip."])
        + f"\n💰 **Bribe pot: {pot['pot']} {C}** • next try rolls at **{min((pot['pot'] + match) // 2, 75)}%** if someone "
        f"matches {match}\n🦹 Chipped in: {crew}\n-# Every 2 chips in the pot = 1% (max 75%). If the cooldown ends first "
        f"(<t:{until}:R>), I keep the pot. • Your chips: {w.chips} {C}",
        view=buttons.view((f"bribe soon grand {match}", f"Match {match}", "💰", discord.ButtonStyle.success)))
    await buttons.replace(f"gbribe:{gid}", msg)


async def bribe(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    num = re.search(r"\d+", re.sub(r"<@!?\d+>", "", message.content))
    n = int(num.group()) if num else 0
    if GRAND_BRIBE_RE.search(message.content or ""):
        await grand_bribe(message, bank, n)
        return
    if n < 1:
        await message.channel.send(f"💸 {u} Bribe me with what? Your charm? `bribe soon 30`. More chips, more likely I look the other way.")
        return
    w = await bank.pay(gid, me, n, "bribed Soon")
    if w is None:
        have = (await bank.get(gid, me)).chips
        await message.channel.send(f"💸 {u} You're offering {n} {C} and you have {have}. Bribing me with imaginary chips "
                                   "is still bribery. Still a no.")
        return
    odds = min(n, 95)
    if random.randrange(100) < odds:
        for k in ("claimcd", "scratchcd", "stealh", "stealp"):
            await bank.clear_timer(gid, me, k)
        await message.channel.send(
            f"💸 {u} slides me **{n} {C}** under the table. I look around. I pocket it.\n# 🤫 Cooldowns? What cooldowns?\n"
            "Your `claim`, `scratch` and steal timers have been... misplaced. " + _line(message.author, [
                "This never happened.", "I don't know you. I've never met you.", "Pleasure doing crimes with you."]) +
            f"\n-# Bribe: -{n} {C} ({odds}% odds) • Chips: {w.chips} {C}")
    else:
        await message.channel.send(
            f"💸 {u} slides me **{n} {C}**. I count it. Slowly. I put it in my pocket.\n# 🙅 No.\n" + _line(message.author, [
                "I'm keeping it though.", "Thanks for the donation to the Soon Margarita Fund.",
                "Bribery is a crime. Lucky for you, I love crime. Unlucky for you, not today.",
                "Try more chips. Or more begging. Ideally both."]) +
            f"\n-# Bribe: -{n} {C} ({odds}% odds) • Chips: {w.chips} {C}")
