"""Tips, make it rain, and rob the bartender, moved over from Soon Classic.
tip @name 10 (max 100) • make it rain 50 (or "all"): split between up to 5 random people who gambled today
• rob the bartender: 50/50 a free margarita + 25 chips, or banned from the bar for 10 minutes (once per 10 minutes)."""
import random
import re

from .casino import C, DANCE, casino_channel, test_note
from .economy import Bank, casino_day

ARMS = "<a:dancingtacorainbowarmsv20:1556420777644003391>"
TIP_MAX, RAIN_SPLIT, ROB_CD, BAN = 100, 5, 600, 600

TIP_RE = re.compile(r"(?i)^\s*tip\b.*<@!?\d+>.*$")
RAIN_RE = re.compile(r"(?i)^\s*make\s+it\s+rain\b.*$")
ROB_RE = re.compile(r"(?i)^\s*rob\s+(?:the\s+)?(?:bartender|bar)\b.*$")


async def handle(message, bank: Bank, mod: bool) -> bool:
    if not casino_channel(message.channel):
        return False
    text = message.content.strip()
    if TIP_RE.match(text):
        await tip(message, bank)
    elif RAIN_RE.match(text):
        await rain(message, bank)
    elif ROB_RE.match(text):
        await rob(message, bank)
    else:
        return False
    return True


def amount(text: str) -> int:
    num = re.search(r"\d+", re.sub(r"<@!?\d+>", "", text))
    return int(num.group()) if num else 0


async def tip(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    t = int(re.search(r"<@!?(\d+)>", message.content).group(1))
    member = message.guild.get_member(t)
    n = amount(message.content)
    cap = ""
    if n > TIP_MAX:
        n, cap = TIP_MAX, f" (tips max out at {TIP_MAX})"
    if (member is not None and member.bot) or t == getattr(message.guild.me, "id", 0):
        await message.channel.send(f"💝 {u} Tipping the staff? Finally. But I only accept tips through `bribe soon`. "
                                   "It's more fun for me.")
    elif t == me:
        await message.channel.send(f"💝 {u} You tipped yourself. Money moved from your left pocket to your right pocket. Riveting.")
    elif n < 1:
        await message.channel.send(f"💝 {u} Tip how much? `tip @name 10`. Don't be cheap. Be a little cheap. Not that cheap.")
    else:
        moved = await bank.transfer(gid, me, t, n, "tip")
        if moved is None:
            have = (await bank.get(gid, me)).chips
            await message.channel.send(f"💝 {u} You have {have} {C}. You can't tip {n}. Generous heart, empty pockets.")
            return
        a, b = moved
        if n < 10:
            line = random.choice(["Wow. Big spender. Don't hurt yourself.", "That's not a tip. That's a crumb.",
                                  "They'll frame it. As a joke."])
        elif n < 50:
            line = random.choice(["Respectable. I'm mildly impressed. Don't let it go to your head.",
                                  "Generous. Suspiciously generous. What did they do for you?",
                                  "A fine tip. I've tipped worse. I've never tipped."])
        else:
            line = random.choice(["WHOA. Somebody's buying friendship.",
                                  "That's a LOT of chips. Are you two okay? Blink twice.",
                                  "Philanthropist energy. Disgusting. Beautiful."])
        await message.channel.send(f"💝 {u} tips <@{t}> **{n} {C}**{cap}. {line}\n"
                                   f"-# {message.author.display_name}: {a.chips} {C} • <@{t}>: {b.chips} {C}")


async def rain(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    have = (await bank.get(gid, me)).chips
    n = have if re.search(r"(?i)\ball\b|\bmax\b|\beverything\b", message.content) else amount(message.content)
    n = min(n, have)
    if have < 5:
        await message.channel.send(f"🌧️ {u} You have {have} {C}. That's not rain. That's a drizzle. That's a damp sneeze.")
        return
    if n < 5:
        await message.channel.send(f"🌧️ {u} Make it rain HOW MUCH? `make it rain 50` (or `make it rain all` if you're feeling unwell).")
        return
    pool = [uid for uid, _ in await bank.day_results(gid, casino_day()) if uid != me]
    if not pool:
        await message.channel.send(f"🌧️ {u} Nobody else has gambled today. You're making it rain on an empty casino. "
                                   "Kor is the only one here, and Kor is asleep.")
        return
    random.shuffle(pool)
    pool = pool[:RAIN_SPLIT]
    each = n // len(pool)
    if each < 1:
        await message.channel.send(f"🌧️ {u} {n} {C} split {len(pool)} ways is less than 1 chip each. Make it rain harder.")
        return
    spent = each * len(pool)
    w = await bank.pay(gid, me, spent, "make it rain")
    if w is None:
        await message.channel.send(f"🌧️ {u} Your chips moved while I was counting. Try again.")
        return
    lines = ""
    for uid in pool:
        await bank.add(gid, uid, "caught the rain", chips=each)
        lines += f"\n💸 <@{uid}> +{each} {C}"
    await message.channel.send(
        f"# 💸🌧️ {message.author.display_name.upper()} IS MAKING IT RAIN 🌧️💸\n{ARMS} **{spent} {C}** flying through the casino! {ARMS}"
        f"{lines}\n" + random.choice([
            "I'm sweeping up whatever hits the floor. House rules.", "Kor caught three chips in his mouth. He's keeping them.",
            "This is either generosity or a cry for help. I support both.", "Somebody check on them. Actually, don't. Keep it coming."])
        + f"\n-# Chips left: {w.chips} {C} • Rain falls on whoever gambled today")


async def rob(message, bank: Bank):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    ban = await bank.timer(gid, me, "barban")
    if ban:
        await message.channel.send(f"🚫 {u} You're banned from the bar. I have your photo taped to the register. "
                                   f"Ban lifts <t:{int(ban[0].timestamp())}:R>.")
        return
    cd = await bank.timer(gid, me, "robbar")
    if cd:
        await message.channel.send(f"👀 {u} I'm still counting the till and staring at you. Try again <t:{int(cd[0].timestamp())}:R>.")
        return
    await bank.set_timer(gid, me, "robbar", ROB_CD)
    if random.randrange(2) == 0:
        w = await bank.add(gid, me, "robbed the bartender", chips=25, margs=1)
        await message.channel.send(
            f"🍹 {u} " + random.choice([
                "vaults over the bar while I'm restocking limes.",
                "yells \"LOOK, A FREE TACO!\" and I actually look. Everyone looks.",
                "slides a margarita AND my tip jar down the bar. Smooth. Criminal. Smooth.",
                "distracts me with a compliment. It works. I'm lonely."]) +
            f"\n# 🍹 +1 margarita • +25 {C}\n" + random.choice([
                "I'm adding it to your tab. You don't have a tab. You do now.",
                "I'm giving myself a stern talking-to. In the mirror. Later.",
                "Enjoy it. Lime's on the house. Everything's on the house. Apparently."]) +
            f"\n-# Margaritas: {w.margs} 🍹 • Chips: {w.chips} {C}" + test_note(message.channel))
    else:
        await bank.set_timer(gid, me, "barban", BAN)
        await message.channel.send(
            f"🚫 {u} " + random.choice([
                "reaches for the tequila and gets a lime squeezed directly into their eye.",
                "gets caught with a bottle up their sleeve. It's a big sleeve. It's a big bottle.",
                "tries to rob the bartender. The bartender is me. I'm everywhere."]) +
            "\n# 🚫 BANNED FROM THE BAR\nNo margaritas for you for **10 minutes**. " + random.choice([
                "Go think about what you did. Sober.", "Sit in the corner. The dry corner.",
                "Your margarita privileges have been revoked. Cry into a water."]) +
            f"\n-# Ban lifts <t:{int((await bank.timer(gid, me, 'barban'))[0].timestamp())}:R>")
