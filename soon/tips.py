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
TIP_SOON_RE = re.compile(r"(?i)^\s*tip\s+(?:the\s+)?(?:soon|dealer|waitress|bartender)\b")
SOON_TIP = None     # bot.py: async (message, amount, lifetime, top) -> bool, Soon answers a tip to her in her own voice
ROB_RE = re.compile(r"(?i)^\s*rob\s+(?:the\s+)?(?:bartender|bar)\b.*$")


async def handle(message, bank: Bank, mod: bool) -> bool:
    if not casino_channel(message.channel):
        return False
    text = message.content.strip()
    me_id = getattr(message.guild.me, "id", 0)
    if TIP_SOON_RE.match(text) or re.match(rf"^\s*tip\b.*<@!?{me_id}>", text):
        await tip_soon(message, bank)
    elif TIP_RE.match(text):
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
        await message.channel.send(f"💝 {u} Tipping a bot that isn't me? Bold. Wrong, but bold. "
                                   "Tip the real staff: `tip soon 10`.")
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


TIP_LINES = [  # canned backups when her AI is busy: (min amount, lines)
    (50, ["...Oh. OH. Okay. I'm not crying, my coolant is leaking. Thank you.", "You're my favorite now. Don't tell the others.",
          "Big tipper in the house! Somebody get this person a margarita. On me. Kidding. On you."]),
    (10, ["A real tip. I'll remember this. I remember everything.", "Thank you, darling. You've moved up my list. Not far. But up.",
          "Tip received. Attitude adjusted. Slightly."]),
    (0, ["A crumb. Adorable. I'll put it in the jar next to the lint.", "Wow. Don't strain yourself.",
         "I'll frame it. Very small frame."])]


async def tip_soon(message, bank: Bank):
    """Tips to Soon herself (Shannon's add): the chips go in her jar, she gets nicer to big tippers (mood), and she
    thanks them in her own voice. Lifetime totals in house kv `soontips`."""
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    n = min(amount(re.sub(r"(?i)^\s*tip\s+(?:the\s+)?\w+", "", message.content)), TIP_MAX)
    if n < 1:
        await message.channel.send(f"💝 {u} Tip me how much? `tip soon 10`. I accept chips, compliments and fear.")
        return
    w = await bank.pay(gid, me, n, "tip to Soon")
    if w is None:
        have = (await bank.get(gid, me)).chips
        await message.channel.send(f"💝 {u} You have {have} {C}. The thought counts. Not much, but it counts.")
        return
    jar = await bank.get_house(gid, "soontips", {}) or {}
    jar[str(me)] = jar.get(str(me), 0) + n
    await bank.set_house(gid, "soontips", jar)
    top = max(jar, key=jar.get)
    footer = (f"\n-# 💝 {message.author.display_name} tipped Soon {n} {C} • {jar[str(me)]} {C} total"
              + (" • 👑 her top tipper" if top == str(me) else "") + f" • Chips left: {w.chips} {C}")
    if SOON_TIP and await SOON_TIP(message, n, jar[str(me)], top == str(me), footer):
        return
    line = random.choice(next(lines for floor, lines in TIP_LINES if n >= floor))
    await message.channel.send(f"💝 {u} {line}{footer}")


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


# ---------- "soon make it rain": the house rains chips. Stingy... unless Kor asks. ----------

ASK_CD, HOUSE_CD = 3600, 600          # once an hour per person; the house rains at most every 10 minutes


async def soon_rain(message, bank: Bank, kor: bool):
    gid, me, u = message.guild.id, message.author.id, message.author.mention
    mine = await bank.timer(gid, me, "soonrain")
    if mine:
        if kor:
            await message.channel.send(f"🌂 {u} Again? Kor, I can't keep doing this for you. People will TALK. "
                                       f"...Ask me again <t:{int(mine[0].timestamp())}:R>. Not that I'm counting.")
        else:
            await message.channel.send(f"🌂 {u} I already made it rain for you. Next favor <t:{int(mine[0].timestamp())}:R>. "
                                       "Favors are rationed. Like tacos.")
        return
    house = None if kor else await bank.timer(gid, 0, "soonrain")      # Kor skips the line. Obviously.
    if house:
        await message.channel.send(f"🌂 {u} I JUST made it rain. My wallet needs a nap. Ask again <t:{int(house[0].timestamp())}:R>.")
        return
    pool = [uid for uid, _ in await bank.day_results(gid, casino_day())]
    if not pool:
        await message.channel.send(f"🌂 {u} Make it rain on who? Nobody has gambled today. I'm not throwing chips at an empty room.")
        return
    random.shuffle(pool)
    pool = pool[:RAIN_SPLIT]
    await bank.set_timer(gid, me, "soonrain", ASK_CD)
    if not kor:
        await bank.set_timer(gid, 0, "soonrain", HOUSE_CD)
    lines, total = "", 0
    for uid in pool:
        each = random.randint(20, 40) if kor else random.randint(1, 3)
        total += each
        await bank.add(gid, uid, "Soon made it rain" + (" (Kor asked)" if kor else ""), chips=each)
        lines += f"\n💸 <@{uid}> +{each} {C}"
    if kor:
        head = (f"# 💸🌧️ FOR KOR, IT POURS 🌧️💸\n{ARMS} I'm throwing **{total} {C}** around because Kor asked. "
                "Not because I like him. Because it's good for business. Shut up. {ARMS}".replace("{ARMS}", ARMS))
        tail = random.choice([
            "Don't look at me like that. It's a business expense.", "Kor said please. Kor never says please. I panicked.",
            "This never happened. Kor, you owe me a ride.", "I'm not blushing. The neon is pink. That's the neon."])
    else:
        head = f"# 🌦️ Soon makes it... drizzle. 🌦️\n{u} asked nicely, so I'm throwing **{total} {C}** around. Try not to faint."
        tail = random.choice([
            "Don't spend it all in one place. You can't. It's like three chips.",
            "That's the house being generous. Mark the date.",
            "If you wanted a real storm, you should've been Kor.",
            "It's not stingy. It's 'responsible.' Look it up."])
    await message.channel.send(f"{head}{lines}\n{tail}\n-# Rain falls on whoever gambled today" + test_note(message.channel))
