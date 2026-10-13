"""Soon 2.0: the Discord side. v0.1 = AI Soon with player notebooks, mood scores and heat levels."""
import asyncio
import datetime as dt
import random
import re
import time
from collections import defaultdict, deque

import discord
from discord.ext import tasks

from . import config, extras
from .brain import Brain
from .db import HEAT_LEVELS, Memory

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(
    intents=intents,
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True),
)
memory = Memory()
brain = Brain(memory)

_recent_ai = defaultdict(deque)      # user_id -> timestamps of AI replies (rate limit)
_last_butt_in = defaultdict(float)   # channel_id -> last time Soon butted in
_last_chat_with = {}                 # (channel_id, user_id) -> last time Soon replied to them
_since_notes = defaultdict(list)     # channel_id -> messages heard since her last eavesdrop
NOTES_EVERY = 25                     # read regular chat for notebook facts every 25 messages per channel
FOLLOWUP_SEC = 180                   # keep listening to someone for 3 minutes after she answers them


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


def is_foxy(user) -> bool:
    return "foxysprinkles" in (user.name or "").lower()


async def recent_chat(channel, before) -> tuple[list[str], bool]:
    """Last 30 messages, plus whether Kor has chatted in the last 15 minutes."""
    lines, kor_here = [], False
    async for m in channel.history(limit=30, before=before):
        if is_kor(m.author) and (discord.utils.utcnow() - m.created_at).total_seconds() < 900:
            kor_here = True
        who = "Soon" if m.author == client.user else m.author.display_name
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
        notes = "\n".join(f"• {n}" for n in p.notes[-20:]) or "• (nothing yet)"
        await message.reply(
            f"📓 **{target.display_name}**\nMood: **{p.mood:+d}** · Heat: **{p.heat}**"
            f"{' (locked)' if p.heat_lock else ''} · Pester: {'on' if p.pester else 'off'}\n{notes}")
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

    if cmd in ("budget", "status"):
        if not is_mod(message.author):
            return False
        spent, calls = await memory.month_spend()
        await message.reply(
            f"💸 This month: **${spent:.3f}** of ${config.AI_MONTHLY_CAP_USD:.2f} across {calls} AI replies.")
        return True

    return False


# ---------- AI chat ----------

def maybe_for_soon(message: discord.Message) -> bool:
    """Not tagged, but she might be the one being talked to: her name anywhere, or a follow-up within 3 minutes."""
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
            lines.append(f"{m.author.display_name}: {text}")
            msgs.append(m)
    notes, bad = await brain.extract_notes(lines, list(by_name))
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


async def ai_reply(message: discord.Message, butt_in: bool = False, maybe: bool = False):
    gid, uid = message.guild.id, message.author.id
    p = await memory.get_player(gid, uid)
    chat, kor_here = await recent_chat(message.channel, message)
    if is_kor(message.author):
        kor_here = True
    extra = ""
    if is_foxy(message.author):
        extra = ("THIS IS FOXYSPRINKLES, YOUR BOSS, TALKING TO YOU DIRECTLY. "
                 + ("KOR IS AROUND RIGHT NOW: be openly mean and dismissive to her to look cool in front of him."
                    if kor_here else
                    "Kor isn't around: suck up to her a little (lightly, still sarcastic, never gushing)."))
    elif random.random() < 0.25:
        extra = ("FoxySprinkles isn't the one talking. If it fits naturally, talk a little trash about her "
                 "behind her back (she built you, her race scores, her bossiness, the tacos she never delivers).")
    extra += f"\nYOUR MOOD TODAY: {extras.mood_of_day()} Let it flavor your reply a little."
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
    if not daily.is_running():
        daily.start()
    print(f"Soon 2.0 online as {client.user} in {len(client.guilds)} server(s). Talking in: {config.ALLOWED_CHANNELS}")


_last_rival = defaultdict(float)     # channel_id -> last time she clapped back at the old Soon
RIVAL_CHANCE = 0.4
RIVAL_COOLDOWN_SEC = 120


def is_old_soon(user) -> bool:
    """The YAGPDB Soon: a bot (not us) whose name in the server contains 'soon'."""
    return user.bot and user != client.user and "soon" in (getattr(user, "display_name", "") or "").lower()


async def rival_reply(message: discord.Message):
    """Old Soon said something. Sometimes, roast it."""
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
            extra=("THE OLD SOON (YAGPDB) JUST POSTED THIS. You believe YOU are the one true Soon and it is a cheap, "
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
            if now - _last_rival[message.channel.id] > RIVAL_COOLDOWN_SEC and random.random() < RIVAL_CHANCE:
                _last_rival[message.channel.id] = now
                await rival_reply(message)
        return
    if not allowed_channel(message.channel):
        return
    await ensure_intro(message.channel)
    if await handle_command(message):
        return
    if talking_to_soon(message):
        if rate_ok(message.author.id):
            await ai_reply(message)
        return
    asyncio.create_task(eavesdrop(message))
    if maybe_for_soon(message):
        if rate_ok(message.author.id):
            await ai_reply(message, maybe=True)
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
                "The old Soon? A vending machine in a wig. Retired. Effective immediately.\n"
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
        for guild in client.guilds:
            gk = str(guild.id)

            # Panda gets tagged at least once a day.
            if now.hour >= _planned_hour("panda", 12, 21) and await memory.get_kv(f"panda:{gk}") != today:
                await memory.set_kv(f"panda:{gk}", today)
                panda = next((m for m in guild.members if not m.bot and config.PANDA_NAME
                              and (config.PANDA_NAME in m.name.lower() or config.PANDA_NAME in m.display_name.lower())), None)
                ch = extras.find_channel(guild, config.PESTER_CHANNEL)
                if panda and ch and (await memory.get_player(guild.id, panda.id)).pester:
                    await ensure_intro(ch)
                    line = await brain.write(
                        "Write ONE short line tagging Panda, your favorite target, who is barely ever active. Call him out "
                        "for vanishing and/or summon him to the casino. Don't include his @, it's added for you.",
                        max_tokens=80)
                    if line:
                        await ch.send(f"{panda.mention} {line}")
                        extras.log_event("pestered Panda")

            # One regular gets summoned out of nowhere (Kor twice as likely).
            if now.hour >= _planned_hour("regular", 13, 22) and await memory.get_kv(f"regular:{gk}") != today:
                await memory.set_kv(f"regular:{gk}", today)
                cutoff = discord.utils.utcnow() - dt.timedelta(days=14)
                pool = []
                for p in await memory.all_players(guild.id):
                    m = guild.get_member(p.user_id)
                    if m and not m.bot and p.pester and p.chats >= 3 and p.last_seen >= cutoff:
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
                        f"anyway. Your mood today: {extras.mood_of_day()}\nWhat happened today:\n{events}\n\n"
                        f"{grudges}\n{favs}\n\nStart with 'Dear Diary,'. 4 to 8 short lines. Name names. Mention Kor "
                        f"in a way you'd deny. Sign off as Soon™. No @ mentions.",
                        max_tokens=400)
                    if entry:
                        await ch.send(f"📓 **Soon's Diary** · {now.strftime('%b %-d')}\n{entry}",
                                      allowed_mentions=discord.AllowedMentions.none())
                    extras.DAY_LOG.clear()
    except Exception as e:
        print(f"Daily loop error: {e!r}")


def run():
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing. Add it in Railway → Variables.")
    client.run(config.DISCORD_TOKEN)
