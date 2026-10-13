"""Soon 2.0: the Discord side. v0.1 = AI Soon with player notebooks, mood scores and heat levels."""
import random
import re
import time
from collections import defaultdict, deque

import discord

from . import config
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


async def recent_chat(channel, before) -> list[str]:
    lines = []
    async for m in channel.history(limit=12, before=before):
        who = "Soon" if m.author == client.user else m.author.display_name
        text = m.clean_content.replace("\n", " ")[:300]
        if text:
            lines.append(f"{who}: {text}")
    return list(reversed(lines))


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
    text = message.content.strip()
    low = text.lower()
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

    if cmd in ("budget", "status"):
        if not is_mod(message.author):
            return False
        spent, calls = await memory.month_spend()
        await message.reply(
            f"💸 This month: **${spent:.3f}** of ${config.AI_MONTHLY_CAP_USD:.2f} across {calls} AI replies.")
        return True

    return False


# ---------- AI chat ----------

async def ai_reply(message: discord.Message, butt_in: bool = False):
    gid, uid = message.guild.id, message.author.id
    p = await memory.get_player(gid, uid)
    chat = await recent_chat(message.channel, message)
    async with message.channel.typing():
        out = await brain.think(
            player_name=message.author.display_name,
            player_notes=p.notes,
            heat=p.heat,
            is_kor=is_kor(message.author),
            message=message.clean_content[:1000],
            recent_chat=chat,
            butt_in=butt_in,
        )
    tone = out["tone"]
    p.drift(rude=(tone == "rude"))
    if tone == "nice":
        p.mood = min(5, p.mood + 1)
    elif tone == "rude":
        p.mood = max(-5, p.mood - 1)
    if out["note"]:
        p.notes.append(out["note"])
        p.notes = p.notes[-200:]
    await memory.save_player(p)
    if out["reply"]:
        if butt_in:
            await message.channel.send(out["reply"])
        else:
            await message.reply(out["reply"])


@client.event
async def on_ready():
    await memory.connect()
    print(f"Soon 2.0 online as {client.user} in {len(client.guilds)} server(s). Talking in: {config.ALLOWED_CHANNELS}")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    if not allowed_channel(message.channel):
        return
    if await handle_command(message):
        return
    if talking_to_soon(message):
        if rate_ok(message.author.id):
            await ai_reply(message)
        return
    # Butting in: rare, only on real sentences, with a cooldown per channel.
    if len(message.content.split()) >= 4 and random.random() < config.BUTT_IN_CHANCE:
        now = time.time()
        if now - _last_butt_in[message.channel.id] > config.BUTT_IN_COOLDOWN_SEC and rate_ok(message.author.id):
            _last_butt_in[message.channel.id] = now
            await ai_reply(message, butt_in=True)


def run():
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing. Add it in Railway → Variables.")
    client.run(config.DISCORD_TOKEN)
