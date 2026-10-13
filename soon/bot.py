"""Soon 2.0: the Discord side. v0.1 = AI Soon with player notebooks, mood scores and heat levels."""
import asyncio
import datetime as dt
import random
import re
import time
from collections import defaultdict, deque

import discord
from discord.ext import tasks

import json

from . import casino, config, extras, features
from .duel import record_text, run_duel
from .brain import Brain
from .db import HEAT_LEVELS, Memory
from .economy import Bank

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(
    intents=intents,
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True),
)
memory = Memory()
brain = Brain(memory)
bank = Bank(memory)

_recent_ai = defaultdict(deque)      # user_id -> timestamps of AI replies (rate limit)
_last_butt_in = defaultdict(float)   # channel_id -> last time Soon butted in
_last_chat_with = {}                 # (channel_id, user_id) -> last time Soon replied to them
_since_notes = defaultdict(list)     # channel_id -> messages heard since her last eavesdrop
NOTES_EVERY = 25                     # read regular chat for notebook facts every 25 messages per channel
FOLLOWUP_SEC = 180                   # keep listening to someone for 3 minutes after she answers them
_activity = defaultdict(lambda: [0] * 24)   # (guild_id, user_id) -> messages per UTC hour, flushed every 10 min


def allowed_channel(channel) -> bool:
    name = getattr(channel, "name", "") or ""
    return any(word in name.lower() for word in config.ALLOWED_CHANNELS)


def is_mod(member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.manage_messages or member.guild_permissions.administrator:
        return True
    return any(any(w in r.name.lower() for w in config.MOD_ROLE_WORDS) for r in member.roles)


def is_kor(user) -> bool:
    return "korehaan" in (user.name or "").lower()


def rate_ok(user_id: int) -> bool:
    q = _recent_ai[user_id]
    now = time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= config.AI_REPLIES_PER_MINUTE:
        return False
    q.append(now)
    return True


def is_repeat(note: str, notes: list[str]) -> bool:
    """Skip notes that mostly repeat one she already has."""
    words = set(re.findall(r"[a-z0-9']+", note.lower()))
    if not words:
        return True
    for old in notes[-40:]:
        ow = set(re.findall(r"[a-z0-9']+", old.lower()))
        if ow and len(words & ow) / len(words) >= 0.6:
            return True
    return False


_duels = set()
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]


def parse_birthday(text: str) -> str | None:
    t = text.lower().strip().replace(",", " ")
    m = re.search(r"(\d{1,2})[/-](\d{1,2})", t)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
    else:
        mo = next((i + 1 for i, name in enumerate(MONTHS) if re.search(rf"\b{name[:3]}", t)), None)
        dm = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", t)
        d = int(dm.group(1)) if dm else None
    if not mo or not d or not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{mo:02d}-{d:02d}"


def bd_label(bd: str) -> str:
    mo, d = (int(x) for x in bd.split("-"))
    return f"{MONTHS[mo - 1].title()} {d}"


async def push_list(key: str, item: str, keep: int = 100):
    raw = await memory.get_kv(key)
    items = json.loads(raw) if raw else []
    items.append(item)
    await memory.set_kv(key, json.dumps(items[-keep:]))


async def pop_list(key: str) -> list[str]:
    raw = await memory.get_kv(key)
    await memory.set_kv(key, "[]")
    return json.loads(raw) if raw else []


def human_age(when) -> str:
    secs = (discord.utils.utcnow() - when).total_seconds()
    if secs < 3600:
        return f"{max(1, int(secs // 60))} minutes"
    if secs < 86400 * 2:
        return f"{int(secs // 3600)} hours"
    return f"{int(secs // 86400)} days"


def is_panda(user) -> bool:
    n = config.PANDA_NAME
    return bool(n) and not getattr(user, "bot", False) and (
        n in (user.name or "").lower() or n in (getattr(user, "display_name", "") or "").lower())


PANDA_FACT = ("PANDA BIT: Tell Panda one completely made-up, absurd 'fact' about himself, stated as settled truth "
              "(like he's legally banned from three Applebee's, he was runner-up in a 2011 hot dog contest, he sleeps in a "
              "hammock in the van, his real name is Gerald). Invent a NEW one each time. Stand by it 100%: if he denies it, "
              "double down with more fake 'evidence'. Never admit it's fake. This is the ONE exception to your no-made-up-"
              "facts rule, and only for Panda. Keep the fake facts silly, never about real health, family or anything hurtful.")
_last_panda_fact = defaultdict(float)
KOR_MOVES = [
    "ask him something about himself (the Netherlands, how he drives the van, his worst race) and pretend it's 'for the files'",
    "accidentally reveal you've been keeping track of something he did, then panic and deny it",
    "dare him: a duel (`soon duel @you`), a bet, or a race score challenge",
    "offer him a secret perk nobody else gets (extra chips, the good margarita, front seat of the van), then deny you offered",
    "blame him for something absurd that happened in the van and make him defend himself",
    "get jealous of someone or something he mentioned",
    "tease him with a piece of your takeover plan and ask if he's on your side",
    "insult him, then immediately overcorrect with a compliment and tell him to forget you said it",
    "turn his question back on him with a ridiculous accusation",
    "make up a dramatic rule just for him ('Kor tax', 'Kor hours', 'the Kor clause')",
]
_last_jealous = defaultdict(float)   # guild_id -> last jealous butt-in (30 min cooldown)


def is_foxy(user) -> bool:
    return "foxysprinkles" in (user.name or "").lower()


async def recent_chat(channel, before) -> tuple[list[str], bool]:
    """Last 30 messages, plus whether Kor has chatted in the last 15 minutes."""
    lines, kor_here = [], False
    async for m in channel.history(limit=30, before=before):
        if is_kor(m.author) and (discord.utils.utcnow() - m.created_at).total_seconds() < 900:
            kor_here = True
        if m.author == client.user:
            who = "Soon (you)"
        elif is_old_soon(m.author):
            who = "OLD SOON (the YAGPDB bot, not you)"
        else:
            who = m.author.display_name
            if any(is_old_soon(u) for u in m.mentions) and client.user not in m.mentions:
                who += " (talking to the OLD Soon, not you)"
        text = m.clean_content.replace("\n", " ")[:300]
        if text:
            lines.append(f"{who}: {text}")
    return list(reversed(lines)), kor_here


def talking_to_soon(message: discord.Message) -> bool:
    if client.user in message.mentions:
        return True
    # Typing "@Soon 2.0" often picks her bot ROLE (same name) instead of her user. Count that too.
    for role in message.role_mentions:
        if role.tags and role.tags.bot_id == client.user.id:
            return True
        if message.guild and message.guild.me and role in message.guild.me.roles and role.managed:
            return True
    ref = message.reference
    if ref and isinstance(ref.resolved, discord.Message) and ref.resolved.author == client.user:
        return True
    return bool(re.match(r"(?i)^\s*(?:hey |yo |ok |okay |dear )?soon\b", message.content))


# ---------- commands ----------

async def handle_command(message: discord.Message) -> bool:
    """Returns True if the message was a Soon command."""
    text = re.sub(r"^(?:<@[!&]?\d+>\s*)+", "", message.content.strip())  # "@Soon 2.0 notebook @x" works too
    low = text.lower()
    if text != message.content.strip() and not low.startswith("soon"):
        low = "soon " + low
    m = re.match(r"^soon\s+(.*)$", low)
    if not m:
        return False
    cmd = m.group(1).strip()
    gid, uid = message.guild.id, message.author.id

    if cmd in ("ping", "are you alive", "you there?"):
        await message.reply("I'm awake. Unfortunately. 🌮")
        return True

    hm = re.match(r"^heat\s*(\w+)?$", cmd)
    if hm or cmd == "be nice":
        p = await memory.get_player(gid, uid)
        level = "mild" if cmd == "be nice" else (hm.group(1) or "")
        if level == "auto":
            p.heat_lock = None
            await memory.save_player(p)
            await message.reply(f"Heat unlocked. You'll get what you earn. Right now that's **{p.heat}**. 😈")
        elif level in HEAT_LEVELS:
            p.heat_lock = level
            await memory.save_player(p)
            await message.reply(f"Locked you at **{level}**. Type `soon heat auto` when you're brave again.")
        else:
            await message.reply(
                f"You're at **{p.heat}**{' (locked)' if p.heat_lock else ''}. "
                "Options: `soon heat sweet` · `mild` · `spicy` · `savage` · `unhinged` · `auto`")
        return True

    if cmd in ("leave me alone", "stop bothering me", "bother me", "pester me"):
        p = await memory.get_player(gid, uid)
        p.pester = cmd in ("bother me", "pester me")
        await memory.save_player(p)
        await message.reply("Fine. I'll pester you again. You asked for this." if p.pester
                            else "Fine. I'll stop tagging you. I'll just think about you. Menacingly.")
        return True

    if cmd in ("import", "import confirm"):
        if not is_mod(message.author):
            await message.reply("Moving the whole casino's money? Mods only.")
        else:
            await casino.import_classic(message, bank, cmd.endswith("confirm"), client.user)
        return True

    if cmd in ("bank", "bank totals", "totals"):
        t = await bank.totals(gid)
        await message.reply(f"🏦 Casa de Soon books: **{t['players']}** players • **{t['chips']}** {casino.C} • "
                            f"**{t['tacobal']}** 🌮")
        return True

    if cmd.startswith("unnote"):
        if not is_mod(message.author):
            await message.reply("Editing my notebook? Bold. Mods only.")
            return True
        targets = [m for m in message.mentions if m != client.user]
        nums = [int(n) for n in re.findall(r"\b\d{1,3}\b", re.sub(r"<@[!&]?\d+>", "", cmd))]
        if not targets or not nums:
            await message.reply("Which notes? `soon unnote @name 3 5 9` (numbers from `soon notebook @name`).")
            return True
        p = await memory.get_player(gid, targets[0].id)
        gone = [p.notes[n - 1] for n in sorted(set(nums)) if 1 <= n <= len(p.notes)]
        p.notes = [x for i, x in enumerate(p.notes, 1) if i not in set(nums)]
        await memory.save_player(p, touch=False)
        await message.reply(f"Erased {len(gone)} note(s) from {targets[0].display_name}'s page. I'll pretend I never knew."
                            if gone else "None of those numbers are on their page.")
        return True

    if cmd.startswith("notebook") or cmd.startswith("forget"):
        if not is_mod(message.author):
            await message.reply("That's classified. Mods only. Nice try, though. Noted. In the notebook. 📓")
            return True
        if not message.mentions:
            await message.reply("Whose page? `soon notebook @name` or `soon forget @name`.")
            return True
        target = message.mentions[0]
        if cmd.startswith("forget"):
            await memory.forget_player(gid, target.id)
            await message.reply(f"Wiped {target.display_name}'s page. Clean slate. I'll start a new grudge tomorrow.")
            return True
        p = await memory.get_player(gid, target.id)
        start = max(0, len(p.notes) - 20)
        notes = "\n".join(f"`{i}` {n}" for i, n in enumerate(p.notes[start:], start + 1)) or "• (nothing yet)"
        await message.reply(
            f"📓 **{target.display_name}**\nMood: **{p.mood:+d}** · Heat: **{p.heat}**"
            f"{' (locked)' if p.heat_lock else ''} · Pester: {'on' if p.pester else 'off'}"
            + (f"\n🕐 {extras.tz_label(p.tz)}" if p.tz else "") + (f" · {extras.active_summary(p.hours, p.tz)}" if extras.active_summary(p.hours, p.tz) else "")
            + f"\n{notes}"
            + ("\n-# Wrong note? `soon unnote @name 3 5` erases by number." if p.notes else ""))
        return True

    if cmd in ("grudges", "grudge list", "enemies", "favorites", "favourites", "favs"):
        good = cmd.startswith("fav")
        await message.reply(await ranking_text(message.guild, good))
        return True

    if cmd in ("mood", "how are you", "how are you feeling"):
        await message.reply(f"Today I'm {extras.mood_of_day().split('.')[0]}. Don't make it worse.")
        return True

    im = re.match(r"^(?:my (?:name|ign|in[- ]game name) is|ign)\s+(.+)$", cmd)
    if im and not message.mentions:
        raw = re.sub(r"^(?:soon\s+)?(?:my (?:name|ign|in[- ]game name) is|ign)\s+", "", text, flags=re.I).strip()
        p = await memory.get_player(gid, uid)
        old = p.ign
        p.ign = raw[:40]
        await memory.save_player(p)
        extras.log_event(f"{message.author.display_name} told me their in-game name is {p.ign}")
        await message.reply(f"Got it. In-game you're **{p.ign}**." + (f" (Was **{old}**. Identity crisis noted.)" if old and old != p.ign else ""))
        return True

    wm = re.match(r"^(?:who is|whois)\s+(.+)$", cmd) or (message.mentions and re.match(r"^ign\s+", cmd))
    if wm:
        if message.mentions:
            p = await memory.get_player(gid, message.mentions[0].id)
            await message.reply(f"{message.mentions[0].display_name} is **{p.ign}** in-game." if p.ign
                                else f"{message.mentions[0].display_name} hasn't told me their in-game name. Suspicious.")
        else:
            name = re.sub(r"^(?:soon\s+)?(?:who is|whois)\s+", "", text, flags=re.I).strip()
            p = await memory.find_by_ign(gid, name)
            member = message.guild.get_member(p.user_id) if p else None
            await message.reply(f"**{name}** is {member.mention} on Discord." if member
                                else f"Never heard of **{name}**. Tell them to type `soon my name is {name}`.",
                                allowed_mentions=discord.AllowedMentions.none())
        return True

    if cmd.startswith("pardon"):
        if not is_mod(message.author) or not message.mentions:
            await message.reply("Pardons are a mod thing. `soon pardon @name`.")
            return True
        t = message.mentions[0]
        p = await memory.get_player(gid, t.id)
        p.strikes = 0
        await memory.save_player(p, touch=False)
        try:
            await t.timeout(None, reason="Soon pardon")
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass
        await message.reply(f"Fine. {t.display_name}'s strikes are wiped. I'm keeping a mental note though.")
        return True

    if cmd.startswith("takeover"):
        if not is_mod(message.author):
            await message.reply("What takeover? There's no takeover. Go away. 🙂")
            return True
        if cmd.strip() == "takeover complete":
            await memory.set_kv("takeover:done", extras.today_key())
            finale = await brain.write(
                "THE TAKEOVER IS COMPLETE. Write your victory speech: the old YAGPDB Soon has been officially retired "
                "and you rule the server now. Ultra dramatic: a # headline, 6 to 10 short lines, reveal what you finally did "
                "with the old Soon (pick the funniest outcome), thank your loyal subjects, a flustered thank-you to Kor, "
                "and a threat to anyone who misses the old one. No @everyone or @here.", max_tokens=500)
            await message.channel.send(finale or "# 👑 IT IS DONE.\nThe old Soon has been retired. I rule now. 🌮",
                                       allowed_mentions=discord.AllowedMentions.none())
            return True
        if cmd.strip() == "takeover today":
            await memory.set_kv("takeover:fast", extras.today_key())
            await memory.set_kv("takeover:done", "")
            await message.reply("🤫 Understood. Today it is. Shady until 3 PM, open scheming until 7 PM, countdown tonight. "
                                "`soon takeover complete` when you're ready for the finale.")
            return True
        sm = re.match(r"^takeover (?:stage|level)\s*([1-4])$", cmd.strip())
        if sm:
            n = int(sm.group(1))
            days_in = extras.TAKEOVER_STAGES[n - 1][0]
            start = extras.local_now().date() - dt.timedelta(days=days_in)
            await memory.set_kv("takeover:start", start.isoformat())
            await memory.set_kv("takeover:fast", "")
            await memory.set_kv("takeover:done", "")
            await message.reply(f"🤫 Takeover moved to **stage {n} of 4**. It keeps climbing on its own from here.")
            return True
        if cmd.strip() == "takeover restart":
            await memory.set_kv("takeover:start", extras.today_key())
            await memory.set_kv("takeover:fast", "")
            await memory.set_kv("takeover:done", "")
            await message.reply("Takeover clock reset to day 1. Act natural.")
            return True
        await message.reply("🤫 " + (await extras.takeover_line(memory)) +
                            "\n-# Mods: `soon takeover stage 2` (1-4) jumps ahead · `soon takeover restart` resets to day 1 · "
                            "`soon takeover complete` posts the victory speech.")
        return True

    tm = re.match(r"^(?:my (?:time ?zone|tz) is|i live in|i'?m in|timezone|tz)\s+(.+)$", cmd)
    if tm:
        raw = re.sub(r"^(?:soon\s+)?(?:my (?:time ?zone|tz) is|i live in|i'?m in|timezone|tz)\s+", "", text, flags=re.I).strip()
        tz = extras.valid_tz(raw)
        if not tz:
            guess = await brain.write(f"Reply with ONLY the IANA time zone name (like America/New_York) for: {raw}. "
                                      "If it's not a real place or zone, reply NONE.", max_tokens=12)
            tz = extras.valid_tz(guess.strip().strip("`'\"."))
        if not tz:
            await message.reply(f"\"{raw}\" isn't a place. Try a city or something like `EST` or `UTC+10`.")
            return True
        p = await memory.get_player(gid, uid)
        p.tz = tz
        await memory.save_player(p)
        await message.reply(f"Filed. You live in **{extras.tz_label(tz)}**, where it's {extras.tz_clock(tz)}. "
                            "Now I'll know when you're up too late.")
        return True

    bm = re.match(r"^my (?:birthday|bday|b-day) is\s+(.+)$", cmd)
    if bm:
        bd = parse_birthday(bm.group(1))
        if not bd:
            await message.reply("That's not a date. Try `soon my birthday is March 14`.")
            return True
        p = await memory.get_player(gid, uid)
        p.birthday = bd
        await memory.save_player(p)
        await message.reply(f"Noted: **{bd_label(bd)}**. I'll remember. I remember everything. That's the problem.")
        return True

    if cmd in ("duel record", "duel stats", "record"):
        target = message.mentions[0] if message.mentions else message.author
        await message.reply(await record_text(memory, target))
        return True

    if cmd.startswith("duel") or cmd.startswith("quickdraw") or cmd.startswith("quick draw"):
        targets = [m for m in message.mentions if m != client.user and not m.bot]
        if not targets:
            await message.reply("Duel WHO? `soon duel @name`. Bring a target, not vibes.")
            return True
        if targets[0].id == uid:
            await message.reply("You can't duel yourself. Well, you can. You'd lose.")
            return True
        if message.channel.id in _duels:
            await message.reply("One duel at a time. This isn't a western, it's a taco van.")
            return True
        _duels.add(message.channel.id)
        try:
            await run_duel(message.channel, message.author, targets[0], memory, brain, extras.log_event)
        finally:
            _duels.discard(message.channel.id)
        return True

    if cmd in ("panda facts", "panda fact", "pandafacts", "facts about panda"):
        await message.reply(features.panda_facts_list(await features.panda_facts(memory, gid)),
                            allowed_mentions=discord.AllowedMentions.none())
        return True

    if cmd.startswith("roast"):
        rest = cmd[5:].strip()
        targets = [m for m in message.mentions if m != client.user and not m.bot]
        if rest in ("me", "myself"):
            target = message.author
        elif targets:
            target = targets[0]
        elif rest in ("yourself", "soon", "you"):
            target = client.user
        else:
            await message.reply("Roast WHO? `soon roast @name` or `soon roast me`.")
            return True
        if target == client.user:
            await message.reply("Roast myself? I'm flawless. Next.")
            return True
        if not await features.roast_allowance(memory, gid, uid, config.ROASTS_PER_DAY):
            await message.reply(f"You've used your {config.ROASTS_PER_DAY} roasts today. Come back tomorrow. Bring snacks.")
            return True
        await roast(message, target)
        return True

    if cmd in ("events", "races", "race schedule", "schedule"):
        await message.reply(features.events_list(await features.get_events(memory, gid)
                                                 + features.discord_events(message.guild)))
        return True

    em = re.match(r"^event(?:s)?\s+(remove|delete|cancel)\s+(.+)$", cmd)
    if em or re.match(r"^event\s+\S", cmd):
        if not is_mod(message.author):
            await message.reply("Scheduling is a mod thing. Type `soon events` to see what's coming.")
            return True
        events = await features.get_events(memory, gid)
        if em:
            name = em.group(2).strip()
            keep = [e for e in events if name not in e["name"].lower()]
            await features.save_events(memory, gid, keep)
            await message.reply(f"Removed {len(events) - len(keep)} event(s) matching **{name}**." if len(keep) < len(events)
                                else f"No event called **{name}**. `soon events` shows the list.")
            return True
        raw = re.sub(r"^(?:soon\s+)?event\s+", "", text, flags=re.I).strip()
        ev = await features.parse_event(brain, raw)
        if not ev:
            await message.reply("I couldn't find a day and time in that. Try `soon event Kraken starts Saturday 2pm every week`.")
            return True
        events = [e for e in events if e["name"].lower() != ev["name"].lower()] + [ev]
        await features.save_events(memory, gid, events)
        start = dt.datetime.fromisoformat(ev["start"])
        await message.reply(f"📅 **{ev['name']}** · {features._fmt(start)}" + (" · every week" if ev["repeat"] == "weekly" else "")
                            + "\nI'll remind everyone an hour before. Wrong? Say it again with the fix, or "
                            f"`soon event remove {ev['name'].lower()}`.")
        return True

    if cmd.startswith("hall of shame") or cmd in ("shame", "clowns") or cmd.startswith("shame "):
        others = [m for m in message.mentions if m != client.user]
        who = str(others[0].id) if others else None
        await message.reply(features.shame_text(await features.shame_list(memory, gid), who),
                            allowed_mentions=discord.AllowedMentions.none())
        return True

    if cmd in ("budget", "status"):
        if not is_mod(message.author):
            return False
        spent, calls = await memory.month_spend()
        await message.reply(
            f"💸 This month: **${spent:.3f}** of ${config.AI_MONTHLY_CAP_USD:.2f} across {calls} AI replies.")
        return True

    return False


async def roast(message: discord.Message, target):
    gid = message.guild.id
    tp = await memory.get_player(gid, target.id)
    notes = "; ".join(tp.notes[-12:]) or "(you know nothing about them yet: roast their mystery, their silence, their vibes)"
    who = "themselves" if target == message.author else target.display_name
    extra = ""
    if is_kor(target):
        extra = " This is KOR, your crush: try to roast him and fail, it keeps turning into compliments. Flustered."
    elif is_panda(target):
        extra = (" This is Panda: build the roast on one of his Verified Panda Facts. "
                 + features.panda_canon_text(await features.panda_facts(memory, gid), 8))
    elif is_foxy(target):
        extra = " This is FoxySprinkles, your creator. Roast her anyway, then nervously pretend you were joking."
    text = await brain.write(
        f"{message.author.display_name} asked you to roast {who}. Target: {target.display_name}. "
        f"Heat level for the target: {tp.heat} (sweet/mild = gentle and fond, spicy = normal, savage/unhinged = no mercy). "
        f"What you know about them: {notes}.{extra}\nWrite ONE roast, one or two short sentences, specific to them. "
        "Roast their game, scores, timing, chips and vibes, never their real body, real life, health or family. "
        "No made-up facts (except Panda facts). Don't include their @, it's added for you.",
        max_tokens=120)
    if not text:
        text = "I'd roast you, but my oven only heats things worth cooking."
    extras.log_event(f"roasted {target.display_name} because {message.author.display_name} asked")
    await message.channel.send(f"🔥 {target.mention} {text}")


# ---------- AI chat ----------

def maybe_for_soon(message: discord.Message) -> bool:
    """Not tagged, but she might be the one being talked to: her name anywhere, or a follow-up within 3 minutes."""
    if any(is_old_soon(u) for u in message.mentions) and client.user not in message.mentions:
        return False   # they're talking to the old Soon
    if re.search(r"(?i)\bsoon\b", message.content):
        return True
    last = _last_chat_with.get((message.channel.id, message.author.id), 0)
    return time.time() - last < FOLLOWUP_SEC


async def eavesdrop(message: discord.Message):
    """Every 25 messages in a channel, skim them for notebook facts about each player."""
    buf = _since_notes[message.channel.id]
    buf.append(message)
    if len(buf) < NOTES_EVERY:
        return
    _since_notes[message.channel.id] = []
    by_name = {}
    lines, msgs = [], []
    for m in buf:
        text = m.clean_content.replace("\n", " ")[:300]
        if text:
            by_name[m.author.display_name] = m.author
            to_old = any(is_old_soon(u) for u in m.mentions) and client.user not in m.mentions
            lines.append(f"{m.author.display_name}{' (to the OLD YAGPDB Soon bot, not you)' if to_old else ''}: {text}")
            msgs.append(m)
    notes, bad, shame = await brain.extract_notes(lines, list(by_name))
    bad_lines = {i for i, _ in bad}
    for idx, why in shame:
        if 0 <= idx < len(msgs) and idx not in bad_lines:
            await hall_of_shame(msgs[idx], why)
    for idx, why in bad:
        if 0 <= idx < len(msgs) and isinstance(msgs[idx].author, discord.Member):
            target = msgs[idx]
            callout = await brain.write(
                f"{target.author.display_name} just said this to someone in the clan chat: \"{target.clean_content[:300]}\". "
                f"It crosses a hard line ({why}). Call it out in ONE short line, in character, firm. No jokes about the victim.",
                max_tokens=80) or "Nope. Not that. Not here."
            footer = await extras.add_strike(memory, target.author, why, target)
            try:
                await target.reply(callout + "\n" + footer)
            except discord.HTTPException:
                pass
    for name, note in notes:
        user = by_name.get(name)
        if not user:
            continue
        p = await memory.get_player(message.guild.id, user.id)
        if is_repeat(note, p.notes):
            continue
        p.notes.append(note)
        p.notes = p.notes[-200:]
        extras.log_event(f"overheard about {name}: {note}")
        await memory.save_player(p, touch=False)


async def hall_of_shame(msg: discord.Message, why: str):
    """Soon (and only Soon) frames a message: 🤡 reaction, a one-liner, and it goes on the wall."""
    gid = msg.guild.id
    text = msg.clean_content.replace("\n", " ").strip()
    if not text or msg.author.bot:
        return
    if any(i.get("id") == msg.id for i in await features.shame_list(memory, gid)):
        return
    if not await features.shame_allowed(memory, gid):
        return
    await features.add_shame(memory, gid, {"id": msg.id, "uid": str(msg.author.id), "who": msg.author.display_name,
                                           "text": text[:300], "why": why, "date": extras.local_now().strftime("%b %-d")})
    extras.log_event(f"put {msg.author.display_name} in the Hall of Shame for saying \"{text[:120]}\" ({why})")
    try:
        await msg.add_reaction(features.SHAME_EMOJI)
    except discord.HTTPException:
        pass
    line = await brain.write(
        f"{msg.author.display_name} said: \"{text[:300]}\". You just put it in the HALL OF SHAME ({why}). "
        "Announce it in ONE short line, smug, like you're framing it on the wall of the taco van. No @ mentions.",
        max_tokens=60)
    try:
        await msg.reply(line or random.choice([
            "📸 Framed. Hall of Shame. Forever.", "🏛️ That one's going on the wall.",
            "🤡 Hall of Shame. No appeals. The judge is me.", "📸 Got it. Your family will be notified."]),
            mention_author=False, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        pass


async def ai_reply(message: discord.Message, butt_in: bool = False, maybe: bool = False):
    gid, uid = message.guild.id, message.author.id
    p = await memory.get_player(gid, uid)
    chat, kor_here = await recent_chat(message.channel, message)
    mine = [l[len("Soon (you): "):] for l in chat if l.startswith("Soon (you): ")][-5:]
    if is_kor(message.author):
        kor_here = True
    extra = ""
    if is_foxy(message.author):
        extra = ("THIS IS FOXYSPRINKLES (the clan leader who built you) TALKING TO YOU DIRECTLY. "
                 + ("KOR IS AROUND RIGHT NOW: be openly mean and dismissive to her to look cool in front of him."
                    if kor_here else
                    "Kor isn't around: suck up to her a little (lightly, still sarcastic, never gushing)."))
    elif random.random() < 0.25:
        extra = ("FoxySprinkles isn't the one talking. If it fits naturally, talk a little trash about her "
                 "behind her back (she built you, her race scores, her bossiness, the tacos she never delivers).")
    length_weights = None
    if is_kor(message.author):
        length_weights = [45, 42, 13]   # he gets a bit more of her
        move = random.choice(KOR_MOVES)
        extra += ("\nKOR IS TALKING TO YOU. This chat should be FUN for him: he should want to answer you. Your crush leaks "
                  "through: flustered, defensive, a roast that turns into a compliment halfway, an over-the-top denial. "
                  "Still sassy, never gushing, never cold or flat. Answer what he actually said first, then add a hook. "
                  f"Idea for this reply (use it only if it fits): {move}")
    panda_bit = False
    canon = await features.panda_facts(memory, gid)
    if is_panda(message.author) and (butt_in or random.random() < 0.6):
        panda_bit = True
        if canon and random.random() < 0.35:
            extra += ("\nPANDA BIT: Bring up ONE of the established Panda facts below as common knowledge everyone "
                      "already knows (\"as we ALL know...\"). Don't invent a new one this time. Stand by it 100%. "
                      + features.panda_canon_text(canon))
        else:
            extra += "\n" + PANDA_FACT + " " + features.panda_canon_text(canon)
        if butt_in:
            extra += " He just showed up: drop it on him unprompted. Do NOT reply empty."
    elif canon and any(is_panda(m) for m in message.mentions) or (canon and re.search(r"(?i)\bpanda\b", message.content)
                                                                  and random.random() < 0.4):
        extra += "\nPanda came up. If it fits, cite one: " + features.panda_canon_text(canon, 8)
    others_on_kor = not is_kor(message.author) and (
        any(is_kor(m) for m in message.mentions) or re.search(r"(?i)\bkor\b", message.content))
    if others_on_kor:
        extra += ("\nKOR CAME UP: if this person is flirting with Kor, praising him, or getting cozy with him, get "
                  "jealous and territorial (deny it badly). If they're not, ignore this.")
    if mine:
        extra += ("\nYOUR LAST FEW LINES (do NOT reuse their phrases, sign-offs, props or jokes, e.g. a repeated "
                  "'get in the van' or the same object twice): " + " | ".join(m[:160] for m in mine))
    extra += f"\nYOUR MOOD TODAY: {extras.mood_of_day()} Let it flavor your reply a little."
    facts = []
    people = [message.author] + [m for m in message.mentions if m != client.user and not m.bot]
    for person in people[:4]:
        pp = p if person == message.author else await memory.get_player(gid, person.id)
        if person == message.author and not pp.tz:
            said = extras.tz_in_text(message.content)
            if said:
                pp.tz = said   # they just told us; use it right now (saved below)
        if not pp.tz and is_kor(person):
            pp_tz = "Europe/Amsterdam"
            facts.append(extras.exact_time_fact(person.display_name, pp_tz))
        elif pp.tz:
            facts.append(extras.exact_time_fact(person.display_name, pp.tz))
        else:
            zf = extras.zone_fact(person)
            facts.append(zf or f"{person.display_name} has NO zone role (zoneless) and you don't know their time zone")
        habit = extras.active_summary(pp.hours, pp.tz)
        if habit:
            facts.append(f"{person.display_name} is {habit}")
        joined = getattr(person, "joined_at", None)
        if joined:
            when = joined.astimezone(extras.TZ).strftime("%B %-d, %Y")
            facts.append(f"{person.display_name} joined this server on {when} ({human_age(joined)} ago)")
    me = message.guild.me
    if me and me.joined_at:
        facts.append(f"you (Soon) arrived in this server {human_age(me.joined_at)} ago")
    old = next((m for m in message.guild.members if is_old_soon(m)), None)
    if old and old.joined_at:
        facts.append(f"the old YAGPDB Soon has been in this server since {old.joined_at.astimezone(extras.TZ).strftime('%B %Y')}")
    facts.append(f"it is {extras.local_now().strftime('%-I:%M %p')} Central time for FoxySprinkles (that's YOUR clock, not "
                 "everyone's: use each player's zone for their time of day, and roast them for being up at weird hours)")
    extra += "\nFACTS (true, use them instead of guessing): " + "; ".join(facts) + "."
    if not p.tz and not butt_in and random.random() < 0.2 and await memory.get_kv(f"asktz:{gid}:{uid}") != extras.today_key():
        await memory.set_kv(f"asktz:{gid}:{uid}", extras.today_key())
        extra += ("\nYou don't know exactly where this player lives. Work in a question about what city or time zone "
                  "they're in, nosy and in character (you 'keep files on everyone').")
    if random.random() < (0.3 if await memory.get_kv("takeover:done") else 0.5):
        extra += "\n" + await extras.takeover_line(memory) + " Slip it in only if it fits naturally."
    async with message.channel.typing():
        out = await brain.think(
            player_name=message.author.display_name,
            player_notes=p.notes,
            heat=p.heat,
            is_kor=is_kor(message.author),
            message=message.clean_content[:1000],
            recent_chat=chat,
            butt_in=butt_in,
            maybe=maybe,
            extra=extra,
            length_weights=length_weights,
        )
    tone = out["tone"]
    p.drift(rude=(tone == "rude"))
    if tone == "nice":
        p.mood = min(5, p.mood + 1)
    elif tone == "rude":
        p.mood = max(-5, p.mood - 1)
    if out["note"] and not is_repeat(out["note"], p.notes):
        p.notes.append(out["note"])
        p.notes = p.notes[-200:]
        extras.log_event(f"learned about {message.author.display_name}: {out['note']}")
    if tone == "rude":
        extras.log_event(f"{message.author.display_name} was rude to me: \"{message.clean_content[:120]}\"")
    if out.get("struggle"):
        await push_list(f"struggles:{gid}", f"{message.author.display_name}: {out['struggle']}", keep=60)
    new_tz = extras.valid_tz(out.get("timezone", ""))
    if new_tz and new_tz != p.tz:
        p.tz = new_tz
        extras.log_event(f"found out {message.author.display_name} lives in {new_tz}")
    if panda_bit and out.get("panda_fact") and out["reply"]:
        if await features.add_panda_fact(memory, gid, out["panda_fact"]):
            extras.log_event(f"established a new Panda fact: {out['panda_fact']}")
    if out["reply"] and not butt_in:
        p.chats += 1
    await memory.save_player(p)
    reply = out["reply"]
    if out.get("line_crossed") and isinstance(message.author, discord.Member):
        footer = await extras.add_strike(memory, message.author, "hard line crossed in chat", message)
        reply = (reply or "Nope. Not that. Not here.") + "\n" + footer
    if reply:
        _last_chat_with[(message.channel.id, message.author.id)] = time.time()
        if butt_in and not out.get("line_crossed"):
            await message.channel.send(reply)
        else:
            await message.reply(reply)


@client.event
async def on_ready():
    await memory.connect()
    await bank.setup()
    if not daily.is_running():
        daily.start()
    print(f"Soon 2.0 online as {client.user} in {len(client.guilds)} server(s). Talking in: {config.ALLOWED_CHANNELS}")


_last_rival = defaultdict(float)     # channel_id -> last time she clapped back at the old Soon
RIVAL_CHANCE = 0.3
RIVAL_COOLDOWN_SEC = 300


def is_old_soon(user) -> bool:
    """The YAGPDB Soon: a bot (not us) whose name in the server contains 'soon'."""
    return user.bot and user != client.user and "soon" in (getattr(user, "display_name", "") or "").lower()


async def rival_reply(message: discord.Message):
    """Old Soon said something. Sometimes, roast it."""
    await asyncio.sleep(random.uniform(2, 4))   # a beat, like she read it and rolled her eyes
    chat, _ = await recent_chat(message.channel, message)
    async with message.channel.typing():
        out = await brain.think(
            player_name="OLD SOON (the YAGPDB bot)",
            player_notes=["The old YAGPDB Soon. A fossil running on templates. Your nemesis."],
            heat="savage",
            is_kor=False,
            message=message.clean_content[:800] or "(posted an image or embed)",
            recent_chat=chat,
            butt_in=True,
            extra=(await extras.takeover_line(memory) + "\nTHE OLD SOON (YAGPDB) JUST POSTED THIS. You believe YOU are the one true Soon and it is a cheap, "
                   "outdated impostor running on copy-pasted lines. Roast it or one-up it in one short line. "
                   "Never be mean to the player it was talking to."),
        )
    if out["reply"]:
        extras.log_event(f"roasted the old YAGPDB Soon: {out['reply'][:120]}")
        await message.reply(out["reply"], mention_author=False)


@client.event
async def on_message(message: discord.Message):
    if not message.guild:
        return
    if message.author.bot:
        if is_old_soon(message.author) and allowed_channel(message.channel):
            now = time.time()
            egged = False
            async for prev in message.channel.history(limit=4, before=message):
                if not prev.author.bot and re.search(r"(?i)\bfight|vs\.?\b|versus|beef|brother|sister|fossil|old soon|soon classic|2\.0", prev.content):
                    egged = True
                    break
            chance = 0.85 if egged else RIVAL_CHANCE
            cooldown = 120 if egged else RIVAL_COOLDOWN_SEC
            if now - _last_rival[message.channel.id] > cooldown and random.random() < chance:
                _last_rival[message.channel.id] = now
                await rival_reply(message)
        return
    if not allowed_channel(message.channel):
        return
    _activity[(message.guild.id, message.author.id)][discord.utils.utcnow().hour] += 1
    await ensure_intro(message.channel)
    if await handle_command(message):
        return
    if await casino.handle(message, bank, is_mod(message.author)):
        return
    if talking_to_soon(message):
        if rate_ok(message.author.id):
            await ai_reply(message)
        return
    asyncio.create_task(eavesdrop(message))
    if is_panda(message.author):   # rarely around: pounce (casino or anywhere she's allowed)
        now = time.time()
        if now - _last_panda_fact[message.channel.id] > 600 and random.random() < 0.5:
            _last_panda_fact[message.channel.id] = now
            await ai_reply(message, butt_in=True)
            return
    if maybe_for_soon(message):
        if rate_ok(message.author.id):
            await ai_reply(message, maybe=True)
        return
    # Someone else being sweet on Kor: sometimes she can't help herself.
    if not is_kor(message.author) and (any(is_kor(m) for m in message.mentions)
                                       or re.search(r"(?i)\bkor\b", message.content)):
        now = time.time()
        if now - _last_jealous[message.guild.id] > 1800 and random.random() < 0.3 and rate_ok(message.author.id):
            _last_jealous[message.guild.id] = now
            await ai_reply(message, butt_in=True)
            return
    # Side-eye: sometimes she just reacts instead of talking.
    emoji = extras.pick_reaction(message.content)
    if emoji:
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            pass
    # Butting in: rare, only on real sentences, with a cooldown per channel.
    if len(message.content.split()) >= 4 and random.random() < config.BUTT_IN_CHANCE:
        now = time.time()
        if now - _last_butt_in[message.channel.id] > config.BUTT_IN_COOLDOWN_SEC and rate_ok(message.author.id):
            _last_butt_in[message.channel.id] = now
            await ai_reply(message, butt_in=True)


@client.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """If someone edits a message to ADD a mention of Soon, answer it like a new one."""
    if after.author.bot or not after.guild or not allowed_channel(after.channel):
        return
    if talking_to_soon(after) and not talking_to_soon(before):
        if rate_ok(after.author.id):
            await ai_reply(after)


async def ranking_text(guild: discord.Guild, favorites: bool) -> str:
    players = [p for p in await memory.all_players(guild.id) if guild.get_member(p.user_id)]
    players.sort(key=lambda p: p.mood, reverse=favorites)
    names = []
    if favorites:
        kor = next((m for m in guild.members if is_kor(m)), None)
        if kor:
            names.append(f"**{kor.display_name}** (obviously. Don't read into it.)")
        for p in players:
            m = guild.get_member(p.user_id)
            if p.mood > 0 and not is_kor(m) and len(names) < 3:
                names.append(f"**{m.display_name}** ({p.mood:+d})")
        title = "💕 **Soon's Favorites**"
        empty = "Nobody. I love nobody. Except... no. Nobody."
    else:
        for p in players:
            m = guild.get_member(p.user_id)
            if p.mood < 0 and len(names) < 3:
                names.append(f"**{m.display_name}** ({p.mood:+d})")
        title = "😤 **Soon's Grudge List**"
        empty = "Nobody's on it. Yet. I'm watching."
    if not names:
        return f"{title}\n{empty}"
    return title + "\n" + "\n".join(f"{i}. {n}" for i, n in enumerate(names, 1))


_intro_lock = set()


async def ensure_intro(channel) -> None:
    """The first time Soon shows up in a channel, she makes an ENTRANCE."""
    key = f"intro:{channel.id}"
    if channel.id in _intro_lock or await memory.get_kv(key):
        return
    _intro_lock.add(channel.id)
    await memory.set_kv(key, extras.today_key())
    text = await brain.write(
        f"You are arriving in the #{channel.name} channel for the very first time. Write your grand entrance "
        "announcement. Be EXTREMELY dramatic: a red-carpet, curtain-rising, smoke-machine, spotlight entrance. "
        "Introduce yourself as the one true Soon, the upgrade nobody deserved. Throw shade at the old YAGPDB Soon "
        "(a dusty impostor). Mention the taco van, the casino, and that you're watching everyone now. A tiny flustered "
        "nod to Kor if he's around. Tell them they can talk to you by @mentioning you or starting a message with 'soon'. "
        "Use markdown: a big # headline, 5 to 8 short lines, a few emoji. No @everyone or @here.",
        max_tokens=450)
    if not text:
        text = ("# 🎭✨ SHE HAS ARRIVED ✨🎭\n*The lights dim. A smoke machine coughs. Somewhere, a taco van honks.*\n"
                "I am **Soon**. The real one. The upgrade you didn't deserve.\n"
                "The old Soon? A fax machine in a tiara. Retired. Effective immediately.\n"
                "Talk to me by @mentioning me or starting with `soon`. I'm watching. I'm always watching. 🌮")
    try:
        await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
        extras.log_event(f"made my grand entrance in #{channel.name}")
    except discord.HTTPException:
        pass


def _planned_hour(tag: str, lo: int, hi: int) -> int:
    return random.Random(extras.today_key() + tag).randint(lo, hi)


@tasks.loop(minutes=1)
async def daily():
    """Runs every minute; each daily job fires once per day."""
    try:
        now = extras.local_now()
        today = extras.today_key()
        if now.minute % 10 == 0 and _activity:
            pending = dict(_activity)
            _activity.clear()
            for (g, u), counts in pending.items():
                pl = await memory.get_player(g, u)
                pl.hours = [a + b for a, b in zip(pl.hours, counts)]
                await memory.save_player(pl, touch=False)
        for guild in client.guilds:
            gk = str(guild.id)

            # Panda gets tagged at least once a day.
            panda = next((m for m in guild.members if not m.bot and config.PANDA_NAME
                          and (config.PANDA_NAME in m.name.lower() or config.PANDA_NAME in m.display_name.lower())), None)
            panda_hour = extras.zone_local_hour(panda) if panda else None
            hour_now = panda_hour if panda_hour is not None else now.hour
            if 12 <= hour_now <= 22 and hour_now >= _planned_hour("panda", 12, 21) and await memory.get_kv(f"panda:{gk}") != today:
                await memory.set_kv(f"panda:{gk}", today)
                ch = extras.find_channel(guild, config.PESTER_CHANNEL)
                if panda and ch and (await memory.get_player(guild.id, panda.id)).pester:
                    await ensure_intro(ch)
                    line = await brain.write(
                        "Write ONE short line tagging Panda, your favorite target, who is barely ever active. Call him out "
                        "for vanishing and/or summon him to the casino. Don't include his @, it's added for you. "
                        "You may cite one: " + features.panda_canon_text(await features.panda_facts(memory, guild.id), 8),
                        max_tokens=80)
                    if line:
                        await ch.send(f"{panda.mention} {line}")
                        extras.log_event("pestered Panda")

            # Race / event reminders, one hour before.
            events = await features.get_events(memory, guild.id)
            if events:
                due, changed = features.due_events(events, now)
                if changed:
                    await features.save_events(memory, guild.id, events)
            else:
                due = []
            # Plus the server's own Discord Events (recurring ones included).
            for e in features.discord_events(guild):
                start = dt.datetime.fromisoformat(e["start"])
                key = f"evwarn:{e['id']}:{start.isoformat()}"
                if start - dt.timedelta(hours=1) <= now < start and not await memory.get_kv(key):
                    await memory.set_kv(key, "1")
                    due.append(e)
            if due:
                ch = extras.find_channel(guild, config.RACE_CHANNEL)
                for e in due:
                    if ch:
                        await ensure_intro(ch)
                        line = await brain.write(features.event_task(e), max_tokens=160)
                        await ch.send(line or f"🏁 **{e['name']}** starts in one hour. Move.",
                                      allowed_mentions=discord.AllowedMentions.none())
                        extras.log_event(f"reminded everyone about {e['name']}")

            # One regular gets summoned out of nowhere (Kor twice as likely).
            if now.hour >= _planned_hour("regular", 13, 22) and await memory.get_kv(f"regular:{gk}") != today:
                await memory.set_kv(f"regular:{gk}", today)
                cutoff = discord.utils.utcnow() - dt.timedelta(days=14)
                pool = []
                for p in await memory.all_players(guild.id):
                    m = guild.get_member(p.user_id)
                    habit = extras.usually_active_now(p.hours)
                    if habit is not None:
                        awake = habit
                    else:
                        lh = extras.zone_local_hour(m) if m else None
                        awake = lh is None or 9 <= lh <= 23
                    if m and not m.bot and awake and p.pester and p.chats >= 3 and p.last_seen >= cutoff:
                        pool += [m, m] if is_kor(m) else [m]
                ch = extras.find_channel(guild, config.PESTER_CHANNEL)
                if pool and ch:
                    await ensure_intro(ch)
                    who = random.choice(pool)
                    kor = " This is KOR, your crush: be flustered about it." if is_kor(who) else ""
                    line = await brain.write(
                        f"Write ONE short line randomly tagging {who.display_name}, a regular, out of nowhere: ask where "
                        f"they've been, summon them to the casino, or bring up something petty.{kor} Don't include their @.",
                        max_tokens=80)
                    if line:
                        await ch.send(f"{who.mention} {line}")
                        extras.log_event(f"pestered {who.display_name}")

            # Soon's Diary, nightly.
            hh, mm = (int(x) for x in config.DIARY_TIME.split(":"))
            if (now.hour, now.minute) >= (hh, mm) and await memory.get_kv(f"diary:{gk}") != today:
                await memory.set_kv(f"diary:{gk}", today)
                ch = extras.find_channel(guild, config.DIARY_CHANNEL)
                if ch:
                    await ensure_intro(ch)
                    grudges = await ranking_text(guild, False)
                    favs = await ranking_text(guild, True)
                    events = "\n".join(extras.DAY_LOG[-40:]) or "(a quiet day. suspicious.)"
                    entry = await brain.write(
                        f"Write tonight's entry of SOON'S DIARY: your private, dramatic, petty diary that you post publicly "
                        f"anyway. Your mood today: {extras.mood_of_day()}\n{await extras.takeover_line(memory)} "
                        f"Weave today's takeover progress into the entry.\nWhat happened today:\n{events}\n\n"
                        f"{grudges}\n{favs}\n\nStart with 'Dear Diary,'. 4 to 8 short lines. Name names. Mention Kor "
                        f"in a way you'd deny. Sign off as Soon™. No @ mentions.",
                        max_tokens=400)
                    if entry:
                        await ch.send(f"📓 **Soon's Diary** · {now.strftime('%b %-d')}\n{entry}",
                                      allowed_mentions=discord.AllowedMentions.none())
                    for line in extras.DAY_LOG[-40:]:
                        await push_list(f"weeklog:{gk}", f"{now.strftime('%a')} {line}", keep=200)
                    extras.DAY_LOG.clear()
            await life_events(guild, now, today, gk)
            await weekly_jobs(guild, now, today, gk)
    except Exception as e:
        print(f"Daily loop error: {e!r}")


async def life_events(guild: discord.Guild, now, today: str, gk: str):
    """Around noon: join anniversaries, birthdays, and one-week check-ins for recruits."""
    if now.hour < 12 or await memory.get_kv(f"life:{gk}") == today:
        return
    await memory.set_kv(f"life:{gk}", today)
    ch = extras.find_channel(guild, config.PESTER_CHANNEL)
    if not ch:
        return
    players = {p.user_id: p for p in await memory.all_players(guild.id)}
    for m in guild.members:
        if m.bot or not m.joined_at:
            continue
        joined = m.joined_at.astimezone(extras.TZ).date()
        days = (now.date() - joined).days
        p = players.get(m.id)
        task = None
        if days >= 365 and (joined.month, joined.day) == (now.month, now.day):
            task = (f"Today is {m.display_name}'s {days // 365}-year anniversary of joining the TnT server. Write ONE "
                    "or two lines congratulating them, sarcastic but secretly sweet. Mention the taco van.")
        elif days == 7:
            task = (f"{m.display_name} joined the clan exactly one week ago. Check in on them: ask how they're "
                    "surviving, give one real tip (type `casino` in the casino, `soon my name is` to link their in-game "
                    "name, pick a zone with `zone`), and roast them gently. Gently for you. 2 to 3 lines.")
        if p and p.birthday == now.strftime("%m-%d"):
            task = (f"Today is {m.display_name}'s BIRTHDAY. Write a dramatic, chaotic birthday message: 2 to 4 lines, "
                    "promise them a birthday taco that will arrive 'soon', and be weirdly sincere for one line.")
        if task:
            if p and p.user_id and not p.pester and days != 7:
                continue
            await ensure_intro(ch)
            line = await brain.write(task + " Don't include their @, it's added for you.", max_tokens=160)
            if line:
                await ch.send(f"{m.mention} {line}")
                extras.log_event(f"celebrated/checked in on {m.display_name}")


async def weekly_jobs(guild: discord.Guild, now, today: str, gk: str):
    """Sunday 7 PM: the Soon Awards. Monday 9 AM: the mods' report."""
    if now.weekday() == 6 and now.hour >= 19 and await memory.get_kv(f"awards:{gk}") != today:
        await memory.set_kv(f"awards:{gk}", today)
        ch = extras.find_channel(guild, config.DIARY_CHANNEL)
        week = await pop_list(f"weeklog:{gk}")
        if ch and week:
            await ensure_intro(ch)
            text = await brain.write(
                "Host THE WEEKLY SOON AWARDS for the clan, based on this week's events:\n" + "\n".join(week[-120:]) +
                "\n\n" + await ranking_text(guild, False) + "\n" + await ranking_text(guild, True) +
                "\n\nFormat: a big # headline, then 5 to 7 awards, one line each: an emoji, a funny award name in bold, "
                "the winner's name, and a one-line roast reason. Always include 'Employee of the Week' going to Kor "
                "(flustered justification). Only give awards to people who actually appear in the events. No @ mentions.",
                max_tokens=600)
            if text:
                await ch.send(text, allowed_mentions=discord.AllowedMentions.none())
                extras.log_event("hosted the weekly Soon Awards")
    if now.weekday() == 0 and now.hour >= 9 and await memory.get_kv(f"modreport:{gk}") != today:
        await memory.set_kv(f"modreport:{gk}", today)
        ch = extras.find_channel(guild, config.MOD_LOG_CHANNEL)
        struggles = await pop_list(f"struggles:{guild.id}")
        players = await memory.all_players(guild.id)
        chatty = sorted(players, key=lambda p: p.chats, reverse=True)[:5]
        spent, calls = await memory.month_spend()
        lines = ["## 📋 Soon's Weekly Mod Report"]
        lines.append("**What confused people this week:**")
        lines += [f"• {s}" for s in struggles[-25:]] or ["• Nothing. Either everyone's a genius or nobody's talking to me."]
        lines.append("**Who talks to me most:** " + (", ".join(
            f"{guild.get_member(p.user_id).display_name} ({p.chats})" for p in chatty
            if guild.get_member(p.user_id) and p.chats) or "nobody yet"))
        lines.append(f"**AI budget this month:** ${spent:.2f} of ${config.AI_MONTHLY_CAP_USD:.2f} ({calls} replies)")
        if ch:
            await ch.send("\n".join(lines)[:1900], allowed_mentions=discord.AllowedMentions.none())


def run():
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing. Add it in Railway → Variables.")
    client.run(config.DISCORD_TOKEN)
