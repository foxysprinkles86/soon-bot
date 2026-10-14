"""The taco van, moved over from Soon Classic. Every message with "taco"/"tacos" (or a taco GIF) is a taco request:
it counts toward 9 ranks (with matching roles + LEVEL UP posts), gets a sassy reply (half the time a clan-lore line
from the Taco Pool), custom orders get a fake ticket, and 1 in 500 requests delivers an ACTUAL taco.
Also: `taco status` (fake tracking) and mod `van audit` / `van refund` / `van audit surprise`.
Runs only in TACO_CHANNELS until cutover (Classic still answers "taco" everywhere else)."""
import json
import random
import re
from collections import defaultdict, deque

import discord

from . import config
from .economy import Bank, casino_day

RANKS = [  # (requests needed, emoji + name, role name, lines)
    (0, "🥬 Fresh Hopeful", "Fresh Hopeful", [
        "Tacos? Coming soon! 🌮 (Bless your heart.)", "Oh, you want a taco? Absolutely. Soon. Take a number.",
        "Aww, a new believer. Your tacos are coming soon, sweetie.", "You're #48,212 in line. Tacos coming soon!",
        "Your taco is being prepared with love, care, and zero urgency.",
        "Taco request logged. It's in the system. The system is a napkin.", "Rookie mistake: thinking 'soon' is a time.",
        "Your tacos have left the kitchen! (The kitchen does not exist.)"]),
    (5, "⏳ Line Stander", "Line Stander", [
        "Still waiting? Wow. Committed AND gullible.", "Good news: your tacos are closer than ever! Bad news: no they're not.",
        "You keep asking like it'll make them come faster. Adorable.", "Patience is a virtue. You have neither patience nor tacos.",
        "Your tacos are 5 minutes away. They've been 5 minutes away since spring.",
        "I see you checking the door. Stop. It's embarrassing for both of us.",
        "Soon. Soon-ish. Soon-adjacent. Soon in spirit.", "Your order has been upgraded to Extra Soon."]),
    (15, "🪑 Waiting Room Regular", "Waiting Room Regular", [
        "You've been here so long the magazines are about you now.", "15+ requests, zero tacos eaten. Elite stats.",
        "Hope is a beautiful thing. Watching you have it is hilarious.", "Your taco ETA has been updated to: lol.",
        "Sit. Stay. Good waiter. Tacos soon.", "I'd give you a taco, but then what would you live for?",
        "Taco status: buffering...", "You're not in line anymore. You ARE the line."]),
    (30, "🕸️ Cobweb Collector", "Cobweb Collector", [
        "30+ tacos requested. 0 delivered. 100% customer satisfaction. (Mine.)",
        "Your tacos are coming soon. Your hairline is going sooner.", "Your taco tracking number just says 'lmao.'",
        "Still here? Respect. Also, therapy. Tacos soon.", "I can almost smell the tacos. Lie. I can smell YOU though.",
        "You've waited longer than some marriages last.", "Tacos are coming soon. This statement is not legally binding.",
        "You've grown roots. Tacos soon, little houseplant."]),
    (50, "💀 Taco Skeleton", "Taco Skeleton", [
        "Died waiting for tacos. Respawned. Still waiting. Tacos soon.", "Even your ghost is in line.",
        "50+ requests and you still believe. That's either faith or brain damage.", "Your tacos are almost here. Emotionally.",
        "Delivery drivers whisper about you. 'The one who waits.'", "The tortillas have been ordered. From the future.",
        "Good news: tacos taste the same with no stomach. Soon.", "Your bones rattle every time you say taco. Haunting."]),
    (100, "👑 Patron Saint of Soon", "Patron Saint of Soon", [
        "You are the Chosen One. Chosen to wait forever.", "Monks meditate for decades to reach your level of waiting.",
        "They'll name the taco after you. Once it exists.",
        "You don't wait for tacos anymore. Tacos wait for you. They're still late.",
        "At this point 'soon' is a lifestyle and you're its CEO.",
        "I'm legally required to say your tacos are coming soon. And to laugh.",
        "100+ requests and still no taco. My most loyal fool. Soon.",
        "Kneel before the Patron Saint. Bring snacks. Not tacos. Those are coming soon."]),
    (200, "🧙 Taco Prophet", "Taco Prophet", [
        "The Prophet speaks: 'Soon.' The Prophet is right. The Prophet is always right.",
        "200 requests. You've started a religion. Its only teaching is disappointment.",
        "You've seen the future. There are no tacos in it.", "Followers gather at your feet. They're also waiting for tacos.",
        "The ancient scrolls foretold your coming. They also said 'tacos: never.'",
        "You speak in tongues now. All of them say 'taco.'", "Prophesy all you want. The kitchen is still closed.",
        "Your visions are vivid, beautiful, and taco-less."]),
    (400, "🗿 Eternal Waiter", "Eternal Waiter", [
        "Civilizations have risen and fallen while you waited. Tacos soon.",
        "You've been in line so long you're now a historical landmark.",
        "They're putting a plaque where you stand. It says 'Still Waiting.'", "400+ requests. Your patience is geological.",
        "The line moved once. It was in the wrong direction.", "Your descendants will inherit this taco request.",
        "You are carved into the side of the van like a monument to bad decisions.",
        "Even your skeleton's skeleton is waiting now."]),
    (750, "🌌 One With the Van", "One With the Van", [
        "You are no longer a person waiting for tacos. You are the waiting.",
        "750 requests. The van has started saying YOUR name when it's hungry.",
        "You've transcended tacos. Unfortunately, you still haven't received one.",
        "When the van dreams, it dreams of you. Asking for tacos. Again.",
        "Scientists want to study you. The van wants you to stop.",
        "You and the van are one. The van is also empty. Draw your own conclusions.",
        "There is no taco. There is only the request.", "At this point the tacos are waiting for YOU. They're also late."]),
]
LEVELS = {r[0] for r in RANKS}

POOL = [
    "We merely claimed to *have* tacos. We never said anything about **sharing**.",
    "Your Piggy score is so low the pig filed a missing persons report.", "Tacos are coming soon. Unlike your Piggy lines.",
    "You NQ'd in Space Race and still have the nerve to ask for tacos?",
    "Hit 5,000 Piggy lines and maybe the taco van stops by. Maybe.",
    "The taco van looked for you on the leaderboard. It gave up scrolling.",
    "Your x2 ended before you found the play button.", "Your mobs run at the enemy with more purpose than you've ever had.",
    "Your race score called. It wants a refund.", "You aim your cannon like you aim your life: at the wall.",
    "Tacos arrive the day you reach God tier. So... soon™.", "Immortal tiers? You're in the 'Mortal and Struggling' tier.",
    "Your score is so low the leaderboard needs a basement.", "You lost to a pig. A cartoon pig.",
    "I've seen bots with better race scores. At least they show up.",
    "Terms of Abduction, fine print: 'Tacos coming soon.' (They're not.)",
    "You got abducted by the taco van and they still didn't feed you.",
    "Tacos are performance-based now. Based on your performance, you owe US tacos.",
    "Your Piggy score is an embarrassment to the color blue. Sip slow, loser. 🍹",
    "Deluxe tacos are for 1st place. Look at your rank. Now look at me. No cheese.",
    "Your Kraken score needs to double before you see any seasoned beef. Tick-tock. 🦑",
    "Your taco is on the rocket. It just needs 1,000,000 Space Race fuel. You have... less. 🚀",
    "We ran your taco through a x50 gate. Now the blue mobs are taping 50 tiny tacos back together.",
    "The x100 gate turned your taco into a sentient wall of shells. Don't look it in the shell. 🧱",
    "We hired the Kraken as prep cook. Eight arms. Zero tortilla-folding skills.",
    "Piggy Race champs get double tacos. Two times zero is still being reviewed.",
    "Space Race fuel can be traded for tacos at a rate management refuses to disclose.",
    "More Kraken damage means more tacos. This statement has not been audited.",
    "Your Space Race rocket runs on hopes and dreams. Explains the score.",
    "You play Mob Control like the mobs are controlling you.", "The red mobs saw your name on the roster and relaxed.",
    "Your best race was the one you skipped.", "You'd need a x100 gate just to reach mediocre.",
    "The pig is faster than you and it's made of coins.", "Your Kraken damage wouldn't bother a goldfish. 🐟",
    "You hit the gate wall more than the gates.", "Your race results are giving 'participation trophy,' minus the trophy.",
    "Even the bots in your race felt bad for you.", "Your champion asked to be traded.",
    "Tacos are for people who race. You're more of a snack-adjacent spectator.",
    "Your Piggy run looked like the pig was the one chasing you.",
    "Space Race? You didn't leave the atmosphere. You barely left the couch.",
    "I'd roast your score, but there's nothing there to cook.", "Your score is why the pig has trust issues.",
    "You don't need tacos. You need a tutorial.", "Your race plan is just vibes and a dying phone battery.",
    "Somewhere a Space Race rocket is ashamed to carry you.", "You're the reason the clan average has a footnote.",
    "Your mobs file complaints with HR after every match.", "You couldn't hit a gate if it was the size of Texas.",
    "Your score looks like a typo.", "The leaderboard uses your name as a speed bump.",
    "Your cannon aim has the confidence of a toddler with a hose.",
    "You race like the pig owes you money and you're scared to collect.",
    "Your last race score is still loading. It's been days.", "You play like your thumbs are on a lunch break.",
    "The Kraken laughed at you. Krakens don't laugh.", "You'd get lapped in a race you're not even in.",
    "Your x2 window has a bigger impact than you do.", "Even your alt account is embarrassed to be related to you.",
    "You're not bad at the game. You're just... available.", "Your score is so low it qualifies for the Mariana Trench.",
    "You bring the energy of a mob that walks into the wall first.",
    "Your champion retired out of second-hand embarrassment.", "Tacos are a reward. You are a cautionary tale.",
    "Your tacos are coming. Hey, look over there!", "Have a margarita. The tacos will seem closer. 🍹",
    "One taco emoji has been deposited into your account. Actual tacos pending. 🌮",
    "The taco bar is almost done. We just need a bar. And tacos.",
    "You've been upgraded to Taco Bar Priority Status. Nothing else has changed.",
    "The driver says the taco bar is just ahead. He's said that for three exits.", "Kor ate them all.",
    "Kor insists the tacos are almost here. Kor is also chewing suspiciously loudly.",
    "Kor was spotted near the taco van with salsa on his shirt. Kor denies everything.",
    "Viking says the tacos were lost honorably in battle. Nobody declared war on dinner.",
    "Viking will raid the Taco Bar for your order. Allow 6-8 business pillagings. ⚔️",
    "Foxy says the tacos are coming. Foxy also runs taco communications.",
    "Foxy promised a deluxe taco for 10,000 Piggy lines. Legal clarified that Foxy is also Legal.",
    "The tacos were ready until Kor found them. The backups were ready until Panda found them. Foxy is hiding batch three.",
    "Foxy approved the taco budget. Kor spent it on snacks and filed the receipts as 'clan expenses.'",
    "{X} cut in line again. Your taco moved back another spot.", "I gave your taco to {X}. Kidding. {X} ate it.",
    "{X} says you'll never get a taco. {X} is right.",
    "Ask {X}, they've been waiting longer. Oh wait, no they haven't. You're just slow.",
    "{X} just tipped the bartender to skip you. Bold move.", "Your taco was last seen with {X}. Investigate.",
    "{X} is ahead of you in line and they've never raced a day in their life.",
    "Even {X} has more tacos than you, and {X} has zero.",
    "I'd deliver your taco, but {X} is standing in the van door looking suspicious.",
    "Devo already drank 30 margs this week. He's the reason the bar is out of limes.",
    "Ryan proposed to me once. I said 'soon.' He's still waiting too.",
    "Devo and Kor think they're winning. Nobody is winning. That's the whole point.",
    "Moochie warned you. We have tacos. We do not share.",
    "Nylarese was promised a taco salad. Nylarese is still waiting. Welcome to the van.",
    "Kor ate your taco, then ordered a marg to wash it down.", "Foxy built this van and even she doesn't get tacos.",
]

STATUS = [
    "Your taco is in a sorting facility in Narnia.", "Your taco has departed the origin facility. The origin facility is a rumor.",
    "Out for delivery! The delivery driver is a pigeon. The pigeon is lost.", "Your taco was held at customs for being too spicy.",
    "Delivery attempted. Nobody was home. You were home. We know. We didn't knock.",
    "Your taco is currently orbiting the moon. Space Race fuel low.",
    "Your taco has been rerouted through the Bermuda Triangle for 'efficiency.'",
    "Package damaged in transit. Kor is investigating. Kor has salsa on his face.",
    "Your taco is stuck behind a red mob wave on the highway.", "The driver says he's 5 minutes away. He said that in March.",
    "Your taco is waiting at the pickup counter. The counter is in another dimension.",
    "Label printed! That's it. That's the update.", "Your taco was mistakenly delivered to the Kraken. The Kraken says thanks.",
    "Your taco has entered the x50 gate. Expect 50 tiny tacos. Eventually.",
    "In transit: Foxy is personally carrying it. Foxy stopped to check race scores. Foxy is still checking.",
    "Your tortilla left the warehouse. The filling did not. They're working it out.",
    "The taco van ran out of gas. The driver is asking the pig for directions.",
    "Your package has been flagged for 'excessive hope.'",
    "Your taco is on a slow boat. The boat is also a taco. The boat is sinking.",
    "Delivery delayed due to weather. The weather is 'Soon.'",
    "Your taco has been upgraded to Priority Soon. Expect it never, but faster.",
    "Your taco is clearing security. It forgot to take out its hot sauce.",
    "Your taco is in a holding pattern over the van. Air traffic control is a llama.",
    "Arrived at local facility! The local facility is a cardboard box behind the van.",
    "Your taco has been signed for by 'Mr. Soon.' We don't know who that is either.",
    "Tracking unavailable. The tracker ate the taco.", "Your taco is being reheated for the 47th time. It's tougher than you now.",
    "Your taco was abducted. Ironically. We're negotiating with the aliens.",
    "Exception: Address not found. You are listed as living 'in the waiting room.'",
    "Your taco is in line behind your Piggy score. It's going to be a while.",
    "Your taco is on hold with customer service. Estimated wait: soon.",
    "Your taco is on a scenic tour of every Immortal tier. Currently: Forsaken.",
    "Your taco was delivered! (To someone with a better race score.)", "Your taco has been successfully forgotten.",
    "Your taco left the kitchen at a brisk 0 mph.",
    "Your taco is being assembled by blue mobs using tiny blue fists. Progress: emotional.",
    "Your shipment fell off the truck and is now living a happy life in the wild.",
    "Your taco is in the van. The van is in park. The driver is on his phone.",
    "Your taco was sent via carrier snail. The snail just unionized.", "Shipping label says 'Fragile: handle with soon.'",
]

TACO_RE = re.compile(r"(?i)\btacos?\b")
SKIP_RE = re.compile(r"(?i)\btaco ?(?:status|board|audit|refund)\b|\b(?:when|where)\b.{0,25}\btacos?\b|who ate|"
                     r"taco (?:tuesday|bell|cabana)|del taco|free tacos?|^\s*(?:van|taco) (?:audit|refund)\b")
ORDER_RE = re.compile(r"(?i)\b(?:cherry|piggy|pig|kraken|space|rocket|fish|shrimp|chicken|beef|pork|steak|al pastor|carnitas|"
                      r"birria|veggie|vegan|breakfast|street|crunchy|hard shell|soft shell|spicy|cheesy|double|triple|deluxe|"
                      r"supreme|mango|lime|lobster|brisket|chorizo|bean|potato|egg|mystery|golden|burnt|frozen|margarita)"
                      r"\s+tacos?\b|\btaco salad\b")
STATUS_RE = re.compile(r"(?i)\btaco ?status\b")
AUDIT_RE = re.compile(r"(?i)^\s*(?:van|taco) (?:audit|refund)\b")

_recent: dict[int, deque] = defaultdict(lambda: deque(maxlen=15))   # channel -> recent speakers (for {X} lines)


def taco_channel(channel) -> bool:
    name = (getattr(channel, "name", "") or "").lower()
    return any(w in name for w in config.TACO_CHANNELS)


def note_speaker(message):
    if not message.author.bot:
        q = _recent[message.channel.id]
        if message.author.id in q:
            q.remove(message.author.id)
        q.append(message.author.id)


def rank_for(n: int):
    return [r for r in RANKS if n >= r[0]][-1]


def is_taco_gif(message) -> bool:
    names = [a.filename for a in getattr(message, "attachments", []) or []]
    names += [e.url or "" for e in getattr(message, "embeds", []) or []]
    names += re.findall(r"https?://\S+", message.content or "")
    return any("taco" in (n or "").lower() for n in names)


async def handle(message, bank: Bank, mod: bool, reply=None) -> bool:
    """reply: Soon's AI reply function (special, footer, fallback) -> bool. Without it (buttons), canned lines are used."""
    if not taco_channel(message.channel):
        return False
    text = message.content or ""
    if AUDIT_RE.match(text):
        if mod:
            await audit(message, bank)
            return True
        return False
    if STATUS_RE.search(text):
        await status(message, bank)
        return True
    gif = is_taco_gif(message) and not TACO_RE.search(text)
    if not (TACO_RE.search(text) or gif) or SKIP_RE.search(text):
        return False
    await request(message, bank, gif=gif, reply=reply)
    return True


async def request(message, bank: Bank, gif: bool = False, reply=None):
    """Count the request, then Soon answers it herself (denial/excuse in her voice) with Classic's stats line."""
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    w = await bank.add(gid, uid, "taco request", tacos=1)
    n = w.tacos
    need, rank, role, lines = rank_for(n)
    day = await bank.get_house(gid, f"tacoday:{casino_day()}", {}) or {}
    day[str(uid)] = day.get(str(uid), 0) + 1                       # for the Van Daily Report
    await bank.set_house(gid, f"tacoday:{casino_day()}", day)
    footer = f"\n-# {rank} • Taco request #{n} • Status: Coming Soon™"
    order = ORDER_RE.search(message.content or "")
    if random.randrange(1000) == 0:                                # Classic's glitch egg (fake delivery)
        from . import eggs
        await eggs.glitch(message, bank)
    elif random.randrange(500) == 0:
        await deliver(message, bank, n)
    else:
        if order:
            flavor = order.group(0).lower()
            fallback = (f"🧾 **Order #{random.randint(10000, 99999)}: 1 {flavor.title()}**\n"
                        f"Position in line: {random.choice(['behind Kor', 'behind everyone', 'behind a raccoon', 'behind 48,212 people', 'somewhere in Narnia', 'behind your own Piggy score', 'after the Kraken’s order'])} • ETA: Soon™\n"
                        + random.choice(["Chef has been notified. Chef does not exist.", "Ingredients ordered from the future.",
                                         "Kor has been asked not to touch it.", "Prepared with love, care, and zero urgency.",
                                         "Your order has been laminated and hung on the wall of shame.", "Order accepted. Order ignored."]))
            special = (f"TACO ORDER: they just ordered a {flavor} from the taco van (taco request #{n}, rank {rank}). "
                       "The kitchen doesn't exist and tacos never come. Take the order anyway: an absurd order status "
                       "(order number, ridiculous place in line, ETA Soon™), in your own words.")
        else:
            fallback = (await pool_line(message, bank)) if not gif and random.randrange(2) else \
                lines[await fresh(bank, gid, uid, "seenr", len(lines), 4)]
            special = (f"TACO REQUEST: they just asked the taco van for tacos" + (" by posting a taco GIF" if gif else "") +
                       f" (taco request #{n}, rank {rank}). Tacos are always 'coming soon' and never come. "
                       "Deny it or give an excuse, your way, short, aimed at them. "
                       f"If it fits, riff on this old taco-van line (don't just repeat it): \"{fallback}\"")
        sent = await reply(special, footer, fallback) if reply else False
        if not sent:
            await message.channel.send(f"{u} {fallback}{footer}")
    if n in LEVELS or n == 1:
        await set_rank_role(message.author, role)
    if n in LEVELS and n > 0:
        await message.channel.send(f"🎉 **LEVEL UP!** {u} is now a **{rank}**! Reward: your tacos now come *slightly* sooner. "
                                   "(They don't.) 🎉")


async def fresh(bank: Bank, gid: int, uid: int, key: str, size: int, keep: int) -> int:
    """A random line index the player hasn't seen in their last few."""
    seen = await bank.get_house(gid, f"{key}:{uid}", []) or []
    choices = [i for i in range(size) if i not in seen] or list(range(size))
    i = random.choice(choices)
    await bank.set_house(gid, f"{key}:{uid}", (seen + [i])[-keep:])
    return i


async def pool_line(message, bank: Bank) -> str:
    line = POOL[await fresh(bank, message.guild.id, message.author.id, "seenp", len(POOL), 15)]
    if "{X}" in line:
        others = [x for x in _recent[message.channel.id] if x != message.author.id]
        line = line.replace("{X}", f"<@{random.choice(others)}>" if others else "Kor")
    return line


async def set_rank_role(member, role_name: str):
    roles = getattr(getattr(member, "guild", None), "roles", None)
    if not roles or not hasattr(member, "add_roles"):
        return
    names = [r[2] for r in RANKS]
    new = discord.utils.get(roles, name=role_name)
    old = [r for r in member.roles if r.name in names and r.name != role_name]
    try:
        if new and new not in member.roles:
            await member.add_roles(new, reason="Taco rank")
        if old:
            await member.remove_roles(*old, reason="Taco rank")
    except (discord.Forbidden, discord.HTTPException) as e:
        print(f"Taco rank role failed: {e!r}")


async def deliver(message, bank: Bank, n: int):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    await bank.add(gid, uid, "ACTUAL TACO DELIVERED", tacobal=1, delivered=1)
    witness = discord.utils.get(getattr(message.guild, "roles", []) or [], name="Taco Witness")
    try:
        if witness and hasattr(message.author, "add_roles"):
            await message.author.add_roles(witness, reason="Actual taco delivered")
    except (discord.Forbidden, discord.HTTPException):
        pass
    for ch in getattr(message.guild, "text_channels", []) or []:
        if config.MOD_LOG_CHANNEL in ch.name.lower():
            try:
                await ch.send(f"🌮 **TACO DELIVERED** to {message.author.name} (ID {uid}) on request #{n} • "
                              f"<t:{int(discord.utils.utcnow().timestamp())}:f>")
            except discord.HTTPException:
                pass
            break
    await message.channel.send(
        f"🚨🎉🌮 **THIS IS NOT A DRILL** 🌮🎉🚨\n{u} just received an **ACTUAL TACO** on request #{n}!\n"
        "🎊 The van stopped. The door opened. History was made. 🎊\n-# Now a 🌮 Taco Witness. Everyone else: yours is coming soon.")


async def status(message, bank: Bank):
    w = await bank.get(message.guild.id, message.author.id)
    await message.channel.send(
        f"📦 **Taco Tracking #TACO-{random.randint(10000, 99999)}**\n**Status:** {random.choice(STATUS)}\n"
        f"**Requests on file:** {w.tacos} • **Tacos:** {w.tacobal}\n-# Next update: soon.")


async def audit(message, bank: Bank):
    gid = message.guild.id
    m = re.search(r"<@!?(\d+)>", message.content)
    if not m:
        await message.channel.send("Usage: `van audit @user 6 reasons` • `van audit surprise @user 6 reasons` • "
                                   "`van refund @user 2 reason`")
        return
    t = int(m.group(1))
    rest = re.sub(r"<@!?\d+>", "", message.content)
    refund = bool(re.match(r"(?i)^\s*(?:van|taco) refund", rest))
    rest = re.sub(r"(?i)^\s*(?:van|taco) (?:audit|refund)\s*", "", rest)
    surprise = bool(re.match(r"(?i)^\s*surprise\b", rest))
    rest = re.sub(r"(?i)^\s*surprise\s*", "", rest)
    num = re.search(r"\d+", rest)
    n = max(int(num.group()) if num else 1, 1)
    why = re.sub(r"^\s*\d+\s*", "", rest).strip()
    s = "s" if n > 1 else ""
    if refund:
        w = await bank.add(gid, t, f"van refund: {why}"[:90], tacobal=n)
        await message.channel.send(f"### 🧾 REFUND ISSUED: <@{t}>\n"
                                   + (f"Reason: *{why}*" if why else "The van made a mistake. The van will not be apologizing further.")
                                   + f"\n-# Refund: +{n} taco{s}. Tacos: {w.tacobal} 🌮")
    elif surprise:
        await bank.set_house(gid, f"audit:{t}", {"n": n, "why": why})
        await message.channel.send(f"🤫 Surprise audit scheduled for <@{t}>: -{n} tacos on their next insult.",
                                   allowed_mentions=discord.AllowedMentions.none())
    else:
        w = await bank.add(gid, t, f"van audit: {why}"[:90], tacobal=-n)
        await message.channel.send(f"### 🧾 AUDIT COMPLETE: <@{t}>\n"
                                   + (f"Previously undetected disrespect found: *{why}*" if why else "The van has reviewed your file. It was not good.")
                                   + f"\n-# Back taxes: -{n} taco{s}. Tacos: {w.tacobal} 🌮")


async def surprise_audit(message, bank: Bank) -> str:
    """Called when Soon decides someone was rude to her: fire their scheduled surprise audit, if any."""
    gid, uid = message.guild.id, message.author.id
    a = await bank.get_house(gid, f"audit:{uid}")
    if not a:
        return ""
    await bank.set_house(gid, f"audit:{uid}", None)
    w = await bank.add(gid, uid, f"surprise audit: {a.get('why', '')}"[:90], tacobal=-a["n"])
    return (f"\n### 🧾 SURPRISE AUDIT\n" + (f"Previously undetected disrespect found: *{a['why']}*" if a.get("why") else
                                            "The van has been watching. The van has notes.")
            + f"\n-# Back taxes: -{a['n']} taco{'s' if a['n'] > 1 else ''}. Tacos: {w.tacobal} 🌮")
