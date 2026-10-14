"""The 23 Easter eggs + the Egg Oracle, moved over from Soon Classic (#08 Easter Eggs, #16 More Eggs, #13 Egg Hints,
the glitch and bedtime from #06 Soon Helper, eggs 5/6 from #10 Soon Mouth).

Say the secret thing → Soon answers (in her own voice via the AI, riffing on Classic's line; canned Classic line if
the AI is busy) + Classic's footer: any taco penalty, "NEW EASTER EGG FOUND!" and "Easter eggs: n/23".
- Eggs 1-4, 7-21: secret phrases (same regexes/lines/penalties as Classic). Every time, not just the first.
- Egg 5 / 6: being genuinely nice / mean to Soon (her AI's read of the tone; awarded in bot.ai_reply).
- Egg g: the 1-in-1,000 "TACO FOUND" glitch on a taco request (tacovan.request).
- Egg b: up between 2 and 5 AM (Chicago), 1 in 75 messages, once per 6 hours for the server.
- Egg Oracle: `egg` / `egg hint` (or "egg" in a sentence) whispers a clue for an egg you HAVEN'T found, once per 30 min.
Same channels as the taco van (TACO_CHANNELS) until cutover."""
import datetime as dt
import random
import re

from . import extras
from .boards import BOARD_RE, EGG_NAMES, TOTAL_EGGS
from .economy import Bank
from .tacovan import TACO_RE, taco_channel

# (id, regex, what's going on for the AI, Classic lines, taco penalty, penalty name)
EGGS = [
    ("1", r"\b(?:when|where)\b.{0,25}\btacos?\b", "They asked when the tacos are coming. The answer is always 'Soon.' "
     "(one word is a fine answer)", ["Soon.", "Soon.", "Soon.", "Soon™.", "Soon. (Asking again resets the timer.)",
                                     "Soon-ish.", "Sooner than you think. (Lie.)", "Soon. Stop asking.", "Two weeks. (Soon.)"], 0, ""),
    ("2", r"\bwho ate\b", "They asked who ate the tacos. It was Kor. It is always Kor.",
     ["Kor.", "Kor. Obviously.", "It was Kor. It's always Kor.", "Kor. And he's not sorry.", "Kor. There's salsa on his shirt.",
      "Kor. He says it was 'quality control.'", "Kor. Check his breath.", "Kor. Case closed. 🔍"], 0, ""),
    ("3", r"\bburritos?\b", "They said 'burrito'. That word is banned in this van and just cost them a taco.",
     ["We don't say that word in this van. 🚐", "A burrito is just a taco that gave up.", "Burrito? In THIS van?",
      "Soon heard that. Soon will remember that.", "Wash your mouth out with salsa.", "Burritos are banned in this van.",
      "That word costs you 1 taco. You have 0. Now you owe us.", "Go wrap yourself in a tortilla and leave."], 1, "🌯 Burrito penalty"),
    ("4", r"\b(?:hungry|starving)\b", "They're hungry. There are no tacos. Waiting is the van's specialty.",
     ["Have you tried waiting? It's our specialty.", "Hungry? Great. Hold that feeling. Forever.",
      "The tacos are coming soon. Your hunger is coming now. Bad timing.", "Eat your Piggy Race rewards. Oh wait.",
      "Have a margarita. Those actually show up. 🍹", "Join the line. It's very long and goes nowhere.",
      "Here's a napkin. Chew on that.", "That growling? That's just the sound of 'soon.'"], 0, ""),
    ("7", r"\b(?:guac(?:amole)?|salsa|queso)\b", "They want guac/salsa/queso. Nothing to dip it in: there are no tacos.",
     ["Guac is extra. Everything is extra. Nothing exists.", "Salsa? On what? There's no taco.",
      "Queso is coming soon. Right behind the tacos.", "Chips not included. Neither are tacos.",
      "Guac costs extra. Extra what? Nobody knows.", "The salsa is ready. The tacos aren't. Awkward.",
      "Dip it in disappointment.", "The chips are in the van. The van is locked."], 0, ""),
    ("8", r"\bopen (?:the|that|ur|your) van\b", "They tried to open the van. Say what's inside (never tacos).",
     ["The door creaks open... it's empty. It was always empty. 🚐", "You open the van. Kor is inside, holding an empty plate. He looks away.",
      "The van is locked. A note on the door says: 'Soon.'", "You open the van. A margarita machine and zero tacos. Priorities.",
      "Inside the van: 14 bags of chips, a Kraken plushie, and a sign that says 'tacos coming soon.'",
      "The door is stuck. Kor is holding it shut from the inside.", "You open the van. A raccoon is driving. He nods at you. 🦝",
      "It smells like tacos in here. There are no tacos. Science can't explain it."], 0, ""),
    ("9", r"\btaco tuesday\b", None, None, 0, ""),                                   # day-aware, see below
    ("10", r"\btaco bell\b|\bchipotle\b|\bdel taco\b|\bqdoba\b|\btaco cabana\b|\btorchy'?s\b",
     "They mentioned another taco place. Betrayal. It just cost them 2 tacos.",
     ["Cheating on us? In front of everyone?", "We don't speak of other restaurants in this van.",
      "They have actual tacos. That's cheating.", "Go get your tacos THERE then. Oh wait, you still want ours.",
      "Betrayal noted. 📝", "We don't acknowledge the bell in this van. 🔔🚫", "The van saw that. The van is hurt.",
      "Take your business elsewhere. Actually, you already did."], 2, "💔 Betrayal tax"),
    ("11", r"\bfree tacos?\b", "They asked for free tacos. Greed. It just cost them a taco.",
     ["Free tacos? In THIS van? Security!", "Free tacos would require tacos to exist first.",
      "Free tacos are coming soon. Paid tacos too. Neither are coming.", "Free tacos? Sure. Free. Soon.",
      "Nothing is free. Except our empty promises.", "Free tacos are being handed out right now. In another dimension.",
      "We're giving away free tacos! (This message is a lie.)"], 1, "🤑 Greed tax"),
    ("12", r"\b(?:i quit|rage ?quit(?:ting)?)\b", "They threatened to quit. Nobody quits the van. It just cost them a taco.",
     ["Nobody quits the van. The doors don't open from the inside. 🚐", "Quit? You haven't even gotten your taco yet.",
      "Rage quitting is just aggressive taco waiting.", "The van says no.", "Sure. See you in 5 minutes.",
      "Rage quit logged. Your taco wait has been extended.", "Quitting won't make the tacos come faster. Nothing will."],
     1, "🚪 Quitter's fee"),
    ("13", r"\bbeep boop\b", "They said 'beep boop' at you, a robot. Be offended or answer in robot.",
     ["Don't mock my people.", "Beep boop yourself.", "Beep boop = 'tacos coming soon' in robot.",
      "Boop beep. That means 'leave me alone.'", "Beep boop to you too, human.",
      "Is that supposed to be me? Rude. Accurate, but rude.", "Beep boop. Taco status: still beep boop."], 0, ""),
    ("14", r"\bsoon,? are (?:you|u) (?:a bot|real|alive)\b|\bis soon (?:a bot|real|alive)\b|"
           r"\b(?:does|do) (?:soon|you|u) (?:even |really |actually )?exist\b|\bsoon (?:even |really |actually )?exists?\b",
     "They asked if you're real. You're exactly as real as the tacos.",
     ["I'm as real as the tacos.", "I'm real enough to hold a grudge.", "Am I real? Are YOU? Are the tacos? (No.)",
      "I'm a bot. You're a person still waiting on tacos. Who's winning?", "Real? Yes. Tacos? No.",
      "Sentient enough to judge your race scores.", "I'm as real as your Space Race qualification.",
      "I exist. The tacos don't. Ask better questions.", "I think, therefore I am out of tacos."], 0, ""),
    ("15", r"\bare we (?:almost )?there yet\b|\bhow much (?:longer|further)\b", "Road-trip whining. Kor is driving. No.",
     ["No. 🚐", "Are we there yet? Are YOU there yet? Your Piggy score isn't.", "Kor is driving. That explains the route.",
      "Ask me one more time and I'm turning this van around.", "We're almost there. (We have never been almost there.)",
      "Five more minutes. (Five more years.)", "The GPS says 'recalculating.' It's been saying that since 2024.",
      "Sit back. Enjoy the view. The view is an empty taco shelf."], 0, ""),
    ("16", r"\bhot sauce\b|\bdiablo\b|\bsriracha\b|\bvalentina\b|\btapat[ií]o\b", "They want hot sauce. For what? There's no taco.",
     ["Hot sauce for WHAT? There's no taco.", "Here's your hot sauce packet. 🌶️ Lick it. That's dinner.",
      "The hot sauce is ready. The tacos are... you know.", "We have 400 hot sauce packets and zero tacos. Classic van.",
      "Diablo sauce, for the devil you are.", "Spicy request. Sadly, also an empty one.",
      "Hot sauce is coming soon. Right after the tacos. So never."], 0, ""),
    ("17", r"\bdoor ?dash\b|\buber ?eats\b|\bgrub ?hub\b|\bpostmates\b|\bwaitr\b",
     "They mentioned a food delivery app. Betrayal. It just cost them a taco.",
     ["You ordered from an APP? In front of the van?", "The van is RIGHT HERE. Waiting. Not delivering. But HERE.",
      "DoorDash? Our driver has been 'arriving soon' for 3 years. Loyalty matters.",
      "Cheating with a delivery driver. The van is devastated.", "Hope your Dasher brings tacos. Ours never will.",
      "Betrayal, with a delivery fee."], 1, "📱 Delivery app betrayal tax"),
    ("18", r"\bpineapples?\b", "They brought up pineapple (on tacos). Heresy. It just cost them a taco.",
     ["Pineapple?! On a TACO?! Get out of my van.", "The van does not negotiate with pineapple people.",
      "Al pastor gets a pass. You do not.", "Heresy. Absolute heresy. 🍍🚫", "Somewhere a taco just cried.",
      "Pineapple belongs on a margarita rim, not in my tacos. If we had any."], 1, "🍍 Heresy tax"),
    ("19", r"\bnachos?\b", "They want nachos: the taco's cousin, also never coming.",
     ["Nachos are just tacos that fell apart under pressure. Relatable.", "Nachos are coming soon. Same truck. Same lie.",
      "Chips? Cheese? In this economy?", "Nachos are the taco's cousin. He's also not coming.",
      "The nacho cheese is warm. The chips are not here. Neither are tacos.",
      "You want nachos? Break a taco shell into pieces. Oh wait. No shells either."], 0, ""),
    ("20", r"\b(?:good ?morning|morning|gm|good ?night|goodnight|night night|nighty night|gn)\b,? soon\b|"
           r"\bsoon,? (?:good ?morning|good ?night|goodnight|gm|gn)\b", None, None, 0, ""),      # time-aware
    ("21", r"(?:🌮\s*){3,}", "They spammed taco emoji. Emoji tacos don't count.",
     ["Those are emoji tacos. They don't count. 🌮🌮🌮", "Wow, look at all those tacos. Shame none are real.",
      "You just typed more tacos than this van has ever served.",
      "Emoji tacos have zero calories and zero flavor. Like your race strategy.", "Okay, taco spammer. The van sees you.",
      "I'll take those. *eats emoji tacos* Still hungry."], 0, ""),
]
COMPILED = [(i, re.compile(rx, re.I), gist, lines, pen, why) for i, rx, gist, lines, pen, why in EGGS]

HINTS = {"1": "Ask the question everyone asks. The one with no answer. *When?*",
         "2": "A crime was committed. Ask about the culprit.",
         "3": "Say the name of the taco's lazy cousin. The one wrapped in shame.",
         "4": "Tell the van how your stomach feels.", "5": "Be nice to the bot. Genuinely. It needs it.",
         "6": "Say something mean to the bot. It can take it. (Can it?)", "7": "Ask for something to dip your chips in.",
         "8": "The van has a door. Try it.", "9": "There's one day a week the van cares about. Celebrate it.",
         "10": "Mention the competition. If you dare. It will cost you.", "11": "Ask for tacos at a price of zero.",
         "12": "Threaten to leave the van. See what happens.", "13": "Speak to the bot in its native language.",
         "14": "Question whether Soon actually exists.", "15": "Ask the question every kid asks on a road trip.",
         "16": "Ask for something to make your taco spicy.",
         "17": "Mention the apps that actually deliver food. It will cost you.",
         "18": "Suggest the fruit that starts holy wars. It will cost you.", "19": "Name the taco's crunchy, cheesy cousin.",
         "20": "Greet Soon at the start or end of your day.", "21": "Say taco without using words. Several times.",
         "g": "Keep asking for tacos. One day, the system might... glitch.",
         "b": "Stay up way too late. The van notices night owls."}
EGG_WORD = re.compile(r"(?i)\beggs?\b")
ASK_HINT = re.compile(r"(?i)^\s*(?:<@!?\d+>\s*)?eggs?\s*[?!.]*\s*$|\begg ?hints?\b|\bi want (?:an |some |the )?eggs?\b|"
                      r"\bwhere (?:are|is) (?:the )?eggs?\b")
HINT_COOLDOWN = 1800
BEDTIME = ["Go to bed. The tacos aren't coming at 3am either. 🌙", "It's the middle of the night. Even the van is asleep. 🚐💤",
           "Why are you awake? No x2 window is worth this.", "Sleep. Dream of tacos. It's the closest you'll get.",
           "Bedtime. The tacos will still be not here in the morning.", "It's 3am. Even the Kraken is asleep. 🦑💤",
           "Your phone brightness is waking up the van.", "Close the app. Nothing good happens in Mob Control at 3am."]


def _clean(message) -> str:
    """Their text with Soon's @mention turned into the word 'soon' (like Classic)."""
    text = message.content or ""
    me = getattr(getattr(message.guild, "me", None), "id", None)
    return re.sub(rf"<@!?{me}>", "soon", text) if me else text


async def found(bank: Bank, gid: int, uid: int, egg: str, always: bool = True) -> str:
    """Record the egg; return Classic's footer lines. always=False: only say something when it's new."""
    new = await bank.add_egg(gid, uid, egg)
    if not new and not always:
        return ""
    n = len((await bank.get(gid, uid)).eggs)
    return ("\n## 🥚 NEW EASTER EGG FOUND! 🥚" if new else "") + f"\n-# Easter eggs: {n}/{TOTAL_EGGS}"


def _day_lines(now: dt.datetime):
    day = now.strftime("%A")
    if day == "Tuesday":
        return ("It IS Taco Tuesday. Celebrate tacos, without any tacos.",
                ["🎉 **HAPPY TACO TUESDAY!** 🎉 Today we celebrate tacos. Not WITH tacos. Just near the concept of them.",
                 "🌮 It's Taco Tuesday! The tacos are coming soon. Next Tuesday, probably.",
                 "🎊 Taco Tuesday is here! Tacos are not. Enjoy the vibes.",
                 "🌮 Taco Tuesday! Tacos arriving soon. Check back next Tuesday.",
                 "🎉 TACO TUESDAY! Please enjoy this emoji in place of a taco: 🌮"])
    return (f"They said Taco Tuesday, but it's {day}. Roast them for the wrong day.",
            ["It's not even Tuesday. Read the room.", f"Taco Tuesday on a {day}? Bold. Wrong, but bold.",
             "Wrong day, champ. Even the calendar is disappointed.", "Taco Tuesday is on Tuesday. That's the whole thing.",
             "Wrong day. The tacos aren't coming today either. (They never are.)"])


def _greeting_lines(text: str, now: dt.datetime):
    if re.search(r"(?i)morning|\bgm\b", text):
        if 5 <= now.hour < 12:
            return ("They said good morning. Morning back, still no tacos.",
                    ["Good morning! ☀️ Still no tacos. Fresh day, same disappointment.",
                     "Morning. The van has been up all night not making tacos.", "Rise and shine! The tacos did neither.",
                     "Good morning! Today's forecast: 0% chance of tacos.", "Morning, sunshine. Coffee is ready. Tacos are soon."])
        clock = now.strftime("%I:%M%p").lstrip("0").lower()
        return (f"They said good morning, but it's {clock} for the van (Chicago). Question their time zone.",
                [f"Good morning? It's {clock}. Are you okay?", "Morning? What timezone is your brain in?",
                 "It's not morning. But sure. Morning. Still no tacos."])
    return ("They said goodnight. Night back, dream of tacos.",
            ["Goodnight! 🌙 Dream of tacos. It's the closest you'll get.",
             "Night night. The van will keep not making tacos while you sleep.", "Sleep tight. Don't let the Kraken bite. 🦑",
             "Goodnight. Your taco will be ready in the morning. (Lie.)", "Sweet dreams. Of tacos. That don't exist.",
             "Night! I'll guard the empty taco shelf."])


async def handle(message, bank: Bank, mod: bool, reply=None) -> bool:
    """reply: Soon's AI reply function (special, footer, fallback) -> bool. Without it (buttons), canned lines."""
    if not taco_channel(message.channel) or getattr(message.author, "bot", False):
        return False
    await bedtime(message, bank)                      # passive: never swallows the message
    text = _clean(message)
    if EGG_WORD.search(text) and not BOARD_RE.search(text):
        if await oracle(message, bank, text):
            return True
    for egg, rx, gist, lines, pen, why in COMPILED:
        if rx.search(text):
            await fire(message, bank, egg, gist, lines, pen, why, text, reply)
            return True
    return False


async def fire(message, bank: Bank, egg, gist, lines, pen, why, text, reply):
    gid, uid = message.guild.id, message.author.id
    now = extras.local_now()
    if egg == "9":
        gist, lines = _day_lines(now)
    elif egg == "20":
        gist, lines = _greeting_lines(text, now)
    line = random.choice(lines)
    foot = ""
    if pen:
        w = await bank.add(gid, uid, why, tacobal=-pen)
        foot += f"\n-# {why}: -{pen} taco{'s' if pen > 1 else ''}. Tacos: {w.tacobal} 🌮"
    foot += await found(bank, gid, uid, egg)
    special = (f"EASTER EGG ({EGG_NAMES[egg]}): {gist} Answer in your own voice, short, aimed at them. "
               f"Riff on this old taco-van line, don't just repeat it: \"{line}\""
               + (" The footer already shows the taco charge, don't do math." if pen else ""))
    if not (reply and await reply(special, foot, line)):
        await message.channel.send(f"### {message.author.mention} {line}{foot}")


async def oracle(message, bank: Bank, text: str) -> bool:
    """The Egg Oracle. Asked on purpose = always answers. Just said 'egg' in a sentence = only when off cooldown.
    @Soon + a sentence with egg = Soon's AI answers instead."""
    ask = bool(ASK_HINT.search(text))
    tagged = bool(re.search(r"<@!?\d+>", message.content or "")) or re.match(r"(?i)\s*soon\b", text)
    if not ask and (tagged or TACO_RE.search(text)):
        return False
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    have = [str(e) for e in (await bank.get(gid, uid)).eggs]
    left = [e for e in HINTS if e not in have]
    if not left:
        if ask:
            await message.channel.send(f"## 🏆 {message.author.display_name} has found ALL {TOTAL_EGGS} eggs.\n"
                                       "The Egg Oracle bows. There is nothing left to find. Go outside. "
                                       "(There are no tacos outside either.)")
        return ask
    if await bank.timer(gid, uid, "hintcd"):
        if ask:
            await message.channel.send(f"🔮 {u} The Egg Oracle is resting. Come back in a bit.\n"
                                       f"-# One hint every 30 minutes. Easter eggs: {len(have)}/{TOTAL_EGGS}")
        return ask
    await bank.set_timer(gid, uid, "hintcd", HINT_COOLDOWN)
    intro = "" if ask else "🥚 " + random.choice(["Did someone say *egg*?", "Egg? EGG? The Oracle has awoken.",
                                                  "You said the magic word.", "Careful. Say egg and the Oracle listens."]) + "\n"
    await message.channel.send(f"{intro}## 🔮 The Egg Oracle whispers...\n### *\"{HINTS[random.choice(left)]}\"*\n"
                               f"-# {u} • Easter eggs: {len(have)}/{TOTAL_EGGS} • {len(left)} still hidden • Next hint in 30 min")
    return True


async def bedtime(message, bank: Bank):
    """Egg b: up between 2 and 5 AM Chicago time. 1 in 75 messages, once every 6 hours for the whole server."""
    now = extras.local_now()
    if not (2 <= now.hour < 5) or random.randrange(75):
        return
    gid = message.guild.id
    last = await bank.get_house(gid, "bedtime", 0) or 0
    if now.timestamp() - last < 6 * 3600:
        return
    await bank.set_house(gid, "bedtime", now.timestamp())
    foot = await found(bank, gid, message.author.id, "b")
    await message.channel.send(f"### {message.author.mention} {random.choice(BEDTIME)}{foot}")


async def glitch(message, bank: Bank):
    """Egg g: 1 in 1,000 taco requests (called from tacovan.request)."""
    foot = await found(bank, message.guild.id, message.author.id, "g")
    await message.channel.send("### ⚠️ ERROR: TACO FOUND. Initiating delivery sequence... 🌮🚦\n"
                               "Loading... ██████████ 100%\n### ...just kidding. Soon." + foot)


async def tone_egg(message, bank: Bank, tone: str) -> str:
    """Eggs 5/6: genuinely nice / mean to Soon (her AI read the tone). Footer only when it's a new egg."""
    if tone not in ("nice", "rude") or not taco_channel(message.channel):
        return ""
    return await found(bank, message.guild.id, message.author.id, "5" if tone == "nice" else "6", always=False)
