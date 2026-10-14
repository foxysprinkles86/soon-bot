"""Classic's "talking" bits that touch balances or are mod tools (#08 apology, #10 Soon Mouth, #27 Soon Answer,
#32 Soon Says). Soon's AI already does the rest (8-ball answers to questions, "you rang?" when tagged).

- Disrespect tax: rude TO Soon (her AI's read: tone rude + aimed at her) → -1 taco, "Disrespect logged: #n",
  a framed milestone every 10th. Kindness: nice to her → "Kindness logged: #n", 1 in 20 finds a taco (+1).
  Taco channels only until cutover (they move balances). Daily counts feed the Van Daily Report.
- Apology ("sorry soon"): only counts if you're in taco debt, once a day; 1 in 3 forgiven (+1 taco). Soon voices it.
- `soon answer` (mods): reply to someone's message (or @ them) → Soon answers it like a magic 8-ball. Yours gets deleted.
- `soon says [#channel] text` (mods): Soon posts your text (default #get-in-the-van), ✅ on yours."""
import random
import re

import discord

from .economy import Bank, casino_day
from .tacovan import taco_channel

SORRY_RE = re.compile(r"(?i)\b(?:sorry|my bad|apologi[sz]e|forgive me)\b.{0,40}\b(?:soon|bot|bartender)\b|"
                      r"\b(?:soon|bot|bartender)\b.{0,40}\b(?:sorry|my bad|apologi[sz]e|forgive me)\b")
EIGHT_BALL = ["🎱 🟢 It is certain. Unlike your tacos.", "🎱 🟢 Yes. Write it down. Frame it. It'll never happen again.",
              "🎱 🟢 Yes. Don't make it weird.", "🎱 🟡 Reply hazy. Kor is blocking the signal.",
              "🎱 🟡 Better not tell you now. You'd just ask for a taco.",
              "🎱 🟡 Outlook unclear. Someone spilled salsa on the crystal ball.",
              "🎱 🟡 I consulted the Kraken. The Kraken said 'blub.' Take that how you want.",
              "🎱 🔴 My sources say no. My sources are three raccoons in a trench coat.",
              "🎱 🔴 Absolutely not. Next question.", "🎱 🔴 The van has reviewed your question and is choosing violence. No.",
              "🎱 🔴 No, but I admire the confidence of someone with negative tacos asking.",
              "🎱 🔴 That's a no from me, a no from Kor, and a burp from the Kraken.",
              "🎱 🌮 Soon™. Terms and conditions apply.", "🎱 🌮 Yes and no. Mostly no. A little yes. Okay it's no.",
              "🎱 🌮 Ask your mom. She seemed to know a lot last time."]
SAYS_RE = re.compile(r"(?is)^\s*soon\s+says\s+(.+)$")
SAYS_DEFAULT = "get-in-the-van"


async def _count(bank: Bank, gid: int, uid: int, key: str) -> int:
    """Lifetime counter + today's tally (for the Van Daily Report)."""
    n = int(await bank.get_house(gid, f"{key}:{uid}", 0) or 0) + 1
    await bank.set_house(gid, f"{key}:{uid}", n)
    day = await bank.get_house(gid, f"{key}day:{casino_day()}", {}) or {}
    day[str(uid)] = day.get(str(uid), 0) + 1
    await bank.set_house(gid, f"{key}day:{casino_day()}", day)
    return n


async def mouth(message, bank: Bank, tone: str, at_you: bool) -> str:
    """Disrespect tax / kindness log footer for a reply Soon just wrote. "" when it doesn't apply."""
    if not at_you or tone not in ("rude", "nice") or not taco_channel(message.channel):
        return ""
    gid, uid = message.guild.id, message.author.id
    if tone == "rude":
        n = await _count(bank, gid, uid, "disrespect")
        w = await bank.add(gid, uid, "disrespect tax", tacobal=-1)
        foot = f"\n-# 🧾 Disrespect tax: -1 taco. Tacos: {w.tacobal} 🌮 • Disrespect logged: #{n}"
        if n % 10 == 0:
            foot += (f"\n## 🏆 DISRESPECT MILESTONE: #{n}\n"
                     "The van has framed this one and hung it next to the empty taco shelf.")
        return foot
    n = await _count(bank, gid, uid, "kindness")
    if random.randrange(20) == 0:
        w = await bank.add(gid, uid, "kindness couch taco", tacobal=1)
        return f"\n-# 💖 Soon is so touched it found a taco in the couch cushions. +1 taco. Tacos: {w.tacobal} 🌮"
    return f"\n-# 💖 Kindness logged: #{n}"


async def apology(message, bank: Bank, reply=None) -> bool:
    """'sorry soon': forgiveness only matters if you owe tacos. Once a day, 1 in 3 forgiven (+1 taco)."""
    if not taco_channel(message.channel) or not SORRY_RE.search(message.content or ""):
        return False
    gid, uid = message.guild.id, message.author.id
    w = await bank.get(gid, uid)
    if w.tacobal >= 0:
        line, gist, foot = ("Apology for what? You're not even in debt. Suspicious.",
                            "They apologized to you, but they don't owe the van any tacos. Be suspicious of it.", "")
    elif await bank.timer(gid, uid, "sorrycd"):
        line, gist, foot = ("The van already heard one apology from you today. Come back tomorrow.",
                            "They already apologized today. One apology a day. Brush it off.", "")
    else:
        await bank.set_timer(gid, uid, "sorrycd", 86400)
        if random.randrange(3) == 0:
            w = await bank.add(gid, uid, "apology accepted", tacobal=1)
            line = random.choice(["...fine. The van accepts your apology.", "Apology accepted. Don't make it weird.",
                                  "The van is moved. Slightly.", "Okay. But I'm writing this down."])
            gist, foot = "They apologized and you ACCEPT it, grudgingly.", f"\n-# 🙏 Forgiven: +1 taco. Tacos: {w.tacobal} 🌮"
        else:
            line = random.choice(["Apology rejected. Try again tomorrow.", "The van has read your apology and is not convinced.",
                                  "Nice try. The van remembers everything.", "Sounds rehearsed. Denied."])
            gist, foot = "They apologized and you REJECT it.", "\n-# 🙏 Forgiveness denied. Next apology accepted in 24 hours."
    special = f"APOLOGY: {gist} Short, your voice. Riff on this old line, don't just repeat it: \"{line}\""
    if not (reply and await reply(special, foot, line)):
        await message.channel.send(f"### {message.author.mention} {line}{foot}")
    return True


async def soon_answer(message, write) -> None:
    """Mods: `soon answer` as a reply to someone (or `soon answer @name`). write(prompt) -> text or ''."""
    ref = message.reference.resolved if message.reference and isinstance(message.reference.resolved, discord.Message) else None
    target = ref.author if ref else (message.mentions[0] if message.mentions else None)
    try:
        await message.delete()
    except discord.HTTPException:
        pass
    if not target:
        await message.channel.send("🎱 Reply to someone's message with `soon answer`, or type `soon answer @name`.",
                                   delete_after=15)
        return
    text = await write(f"You are a sassy taco-van magic 8-ball. Answer this message from {target.display_name} in ONE "
                       "short line. Start with 🎱 then 🟢 (yes), 🟡 (maybe), 🔴 (no) or 🌮 (taco nonsense). "
                       f"Their message: \"{(ref.content if ref else '')[:300]}\"") if ref and ref.content else ""
    line = text.strip() if text and text.strip().startswith("🎱") else random.choice(EIGHT_BALL)
    out = f"{target.mention} **{line}**"
    if ref:
        await ref.reply(out, mention_author=True)
    else:
        await message.channel.send(out)


async def soon_says(message) -> bool:
    """Mods: `soon says [#channel] text` → Soon posts it (default #get-in-the-van)."""
    m = SAYS_RE.match(message.content or "")
    if not m:
        return False
    text = m.group(1).strip()
    ch = None
    if message.channel_mentions and text.startswith(message.channel_mentions[0].mention):
        ch = message.channel_mentions[0]
        text = text[len(ch.mention):].strip()
    else:
        ch = discord.utils.find(lambda c: SAYS_DEFAULT in c.name, message.guild.text_channels)
    if not text or not ch:
        await message.reply("Tell me what to say: `soon says #channel your message` (no channel = #get-in-the-van).")
        return True
    await ch.send(text, allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True))
    try:
        await message.add_reaction("✅")
    except discord.HTTPException:
        pass
    return True
