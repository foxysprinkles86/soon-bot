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

from . import alerts, bar, boards, buttons, eggs, report, schedules, talk, welcome, zones, casino, config, crimes, duels, extras, features, games, heists, korperks, menus, pushback, racebets, recruits, suggestions, tacovan, tips
from .duel import record_text
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


def human_age(when, until=None) -> str:
    secs = ((until or discord.utils.utcnow()) - when).total_seconds()
    if secs < 3600:
        return f"{max(1, int(secs // 60))} minutes"
    if secs < 86400 * 2:
        return f"{int(secs // 3600)} hours"
    return f"{int(secs // 86400)} days"


_ignored: set[int] = set()     # players who asked Soon to ignore them (kv "ignored")


def ignored(user) -> bool:
    return getattr(user, "id", None) in _ignored


async def save_ignored():
    await memory.set_kv("ignored", json.dumps(sorted(_ignored)))


# ---------- "soon no tags": she still talks to you, but her @mentions of you never notify you ----------

_noping: set[int] = set()       # players who turned her tags off (kv "noping")
_tag_told: set[int] = set()     # players who've seen the one-time "don't want tags?" note (kv "tagtold")
NOTAG_RE = re.compile(r"(?i)^(?:no (?:more )?(?:tags|pings)|(?:stop|quit|don'?t|do not|never) (?:tagging|pinging|tag|ping|@ ?ing) me"
                      r"|tags? off|pings? off|mute (?:my )?(?:tags|pings))[.!]*$")
TAG_RE = re.compile(r"(?i)^(?:tag me|ping me|tags? on|pings? on|(?:start|resume) (?:tagging|pinging) me|you can tag me)[.!]*$")
_send_original = discord.abc.Messageable.send


class PingButton(discord.ui.DynamicItem[discord.ui.Button], template=r"soon:pings"):
    """🔔 My pings on/off (Shannon's call): on every message that pings players. Flips `soon no tags` for whoever taps."""

    def __init__(self):
        super().__init__(discord.ui.Button(label="My pings on/off", emoji="🔔", custom_id="soon:pings"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls()

    async def callback(self, interaction: discord.Interaction):
        uid = interaction.user.id
        if uid in _noping:
            _noping.discard(uid)
            text = "🔔 Pings are back ON. I'll tag you again. Don't come crying when your phone buzzes."
        else:
            _noping.add(uid)
            text = ("🔕 Pings OFF. I'll still talk to you (and heists, duels and alerts still show your name), "
                    "your phone just won't buzz. Tap again to turn them back on.")
        await memory.set_kv("noping", json.dumps(sorted(_noping)))
        await interaction.response.send_message(text, ephemeral=True)


def ping_view(view: discord.ui.View | None = None) -> discord.ui.View | None:
    """Add the 🔔 My pings on/off button (skipped when the message already has one, or its own alerts toggle)."""
    v = view or discord.ui.View(timeout=None)
    ids = [getattr(c, "custom_id", "") or "" for c in v.children]
    if any(i == "soon:pings" or "alerts" in i for i in ids) or len(v.children) >= 25:
        return view
    v.add_item(PingButton())
    return v


async def _send_filtered(self, content=None, **kw):
    """Every message Soon sends: people on the no-tags list still SEE their @name, but get no notification.
    Any message that pings someone other than the person who caused it gets the 🔔 My pings on/off button."""
    if content:
        text = str(content)
        ids = {int(i) for i in re.findall(r"<@!?(\d+)>", text)}
        am = kw.get("allowed_mentions")
        if ids and (am is None or am is PING or am.users is True):
            ref = kw.get("reference")
            ref_author = getattr(getattr(ref, "author", None), "id", None)
            kw["allowed_mentions"] = discord.AllowedMentions(
                everyone=bool(am and am.everyone), roles=am.roles if am is not None and am is not PING else False,
                users=[discord.Object(i) for i in ids if i not in _noping],
                replied_user=ref_author not in _noping if ref_author else True)
            if ids - _noping - {buttons.ACTOR.get(), getattr(self, "id", None)}:
                kw["view"] = ping_view(kw.get("view"))
    return await _send_original(self, content, **kw)


discord.abc.Messageable.send = _send_filtered


_lab_welcomed: set[int] = set()   # testers who got the #soon-lab welcome (kv "labwelcome")


async def lab_welcome(message: discord.Message):
    """First message from someone in a test channel: tell them what they're testing (once per person, ever)."""
    name = (message.channel.name or "").lower()
    if message.author.id in _lab_welcomed or not any(w in name for w in config.TEST_CHANNELS):
        return
    _lab_welcomed.add(message.author.id)
    await memory.set_kv("labwelcome", json.dumps(sorted(_lab_welcomed)))
    if is_foxy(message.author):
        return
    await message.channel.send(
        f"🧪 **Welcome to the lab, {message.author.mention}.** You're here to test the new me: the Soon that will soon "
        "be running in every channel, not just this one. Talk to me, roast me, try to break me. I'll remember it.\n"
        "🎰 The upgraded **Casa de Soon Casino** is open in here for testing: type `claim` for test chips, then try "
        "`spin`, `toss 10 heads`, `roulette 10 red`, `blackjack 20`, `scratch` or `heist` (or use the buttons).\n"
        "-# 🧪 All chips won or lost in #soon-lab reset when testing is complete and the Casa de Soon Casino upgrade goes live.",
        view=buttons.view(("claim", "Claim test chips", "💵", discord.ButtonStyle.success),
                          ("spin", "Spin", "🎰"), ("heist", "Heists", "🦹")),
        allowed_mentions=PING)


_panda_ids: set[int] = set()   # remembered by account, so a nickname from Soon ("Gerald") doesn't hide him


def is_panda(user) -> bool:
    if getattr(user, "id", None) in _panda_ids:
        return True
    n = config.PANDA_NAME
    found = bool(n) and not getattr(user, "bot", False) and (
        n in (user.name or "").lower() or n in (getattr(user, "display_name", "") or "").lower())
    if found:
        _panda_ids.add(user.id)
        asyncio.get_event_loop().create_task(memory.set_kv("panda_ids", json.dumps(sorted(_panda_ids))))
    return found


PANDA_FACT = ("Panda bit: tell Panda one NEW absurd made-up 'fact' about himself as settled truth: specific and "
              "ridiculous (a secret job, a weird record, a strange habit, a fake real name). Invent your own; never reuse "
              "an example you've seen. Stand by it forever; if he denies it, add fake evidence. Silly only, never hurtful.")
_last_panda_fact = defaultdict(float)
KOR_MOVES = [
    "ask him something about himself (the Netherlands, how he drives the van, his worst race) and pretend it's 'for the files'",
    "accidentally reveal you've been keeping track of something he did, then panic and deny it",
    "dare him: a duel (`duel @name 20` in the casino), a bet, or a race score challenge",
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
    seen = {}
    newer = before.created_at if getattr(before, "created_at", None) else None
    async for m in channel.history(limit=30, before=before):
        if newer and (newer - m.created_at).total_seconds() > 1200:   # mark pauses so old chatter reads as old
            lines.append(f"--- {human_age(m.created_at, newer)} pass ---")
        newer = m.created_at
        if is_kor(m.author) and (discord.utils.utcnow() - m.created_at).total_seconds() < 900:
            kor_here = True
        if not m.author.bot:
            seen.setdefault(m.author.id, m.author)
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
    _participants[getattr(channel, "id", 0)] = list(seen.values())
    return list(reversed(lines)), kor_here


_participants: dict[int, list] = {}   # channel id -> people in the recent chat (for turning names into @mentions)
PING = discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True)


def ping_names(text: str, people, case_sensitive: bool = False) -> str:
    """Turn the first time she names someone into a real @mention (nicknames, usernames, plus "Kor" and "Foxy")."""
    flags = 0 if case_sensitive else re.IGNORECASE
    done = set()
    for person in people:
        if person is None or person.bot or person.id in done or person == client.user or ignored(person):
            continue
        names = {getattr(person, "display_name", ""), getattr(person, "global_name", "") or "", person.name}
        if is_kor(person):
            names.add("Kor")
        if is_foxy(person):
            names.add("Foxy")
        for name in sorted((n for n in names if n and len(n) >= 3), key=len, reverse=True):
            if f"<@{person.id}>" in text or f"<@!{person.id}>" in text:
                break
            # "Master Foxy" (Shannon's order) stays readable: ping her elsewhere in the line, not inside her title
            keep = r"(?<!master )" if name == "Foxy" else ""
            pat = re.compile(rf"(?<![\w@#-]){keep}{re.escape(name)}(?![\w-])", flags)
            # a plain-word name ("Rain") only counts when written like a name, so "make it rain" stays a ping-free joke
            hit = next((m for m in pat.finditer(text) if m.group()[0].isupper() or not name.isalpha()), None)
            if hit:
                text = text[:hit.start()] + person.mention + text[hit.end():]
                done.add(person.id)
                break
    return text


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


# ---------- "be nice" check-in: ask before turning her auto mood off for someone ----------

NICE_RE = re.compile(r"(?i)(?<!don't )(?<!dont )(?<!never )\bbe (?:nice|nicer|kind|sweet)\b")
HEAT_HELP = ("**How to set my meanness toward you** (type it in the server):\n"
             "• `soon heat sweet`: I'm lovely to you\n• `soon heat mild`: gentle teasing\n"
             "• `soon heat spicy`: my normal\n• `soon heat savage`: no mercy\n• `soon heat unhinged`: you asked for it\n"
             "• `soon heat auto`: back to automatic (I treat you how you treat me)\n• `soon heat`: check your setting")


async def heat_locked_dm(user, level: str):
    """Auto mood just got switched off for them: say sorry and explain the knobs."""
    try:
        opener = ("💌 Sorry if I was too much. Truly. Mostly. 🥺" if level in ("sweet", "mild") else
                  "😈 You asked for it. Literally. You pressed the button.")
        await user.send(f"{opener}\nFrom now on I'll stay **{level}** with you. "
                        f"My automatic mood is off for you.\n\n{HEAT_HELP}")
    except discord.HTTPException:
        pass                                   # DMs closed: the channel reply already told them


class NiceButton(discord.ui.DynamicItem[discord.ui.Button], template=r"soon:nice:(?P<g>\d+):(?P<u>\d+):(?P<c>\w+)"):
    """Buttons on the "want me to be nicer to YOU?" question. Only that person can press; they vanish after."""
    LABELS = {"mild": ("Yes, be nicer to me", "😇", discord.ButtonStyle.success),
              "sweet": ("Be sweet to me", "🥰", discord.ButtonStyle.primary),
              "auto": ("No, keep it automatic", "😈", discord.ButtonStyle.secondary)}
    HEAT = {"sweet": ("Sweet", "🥰", discord.ButtonStyle.success), "mild": ("Mild", "😇", discord.ButtonStyle.success),
            "spicy": ("Spicy", "🌶️", discord.ButtonStyle.primary), "savage": ("Savage", "🔥", discord.ButtonStyle.danger),
            "unhinged": ("Unhinged", "💀", discord.ButtonStyle.danger), "auto": ("Auto", "🔄", discord.ButtonStyle.secondary),
            "ignore": ("Ignore me", "🙈", discord.ButtonStyle.secondary)}

    def __init__(self, gid: int, uid: int, choice: str):
        if choice.startswith("h"):                      # the `soon heat` panel: h + level
            label, emoji, style = self.HEAT[choice[1:]]
        else:
            label, emoji, style = self.LABELS[choice]
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=style,
                                           custom_id=f"soon:nice:{gid}:{uid}:{choice}"))
        self.gid, self.uid, self.choice = gid, uid, choice

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(int(match["g"]), int(match["u"]), match["c"])

    async def callback(self, interaction: discord.Interaction):
        heat_panel = self.choice.startswith("h")
        owner = interaction.user.id == self.uid
        if not owner and not heat_panel:
            await interaction.response.send_message("That question wasn't for you. Ask me yourself: `soon be nice`.",
                                                    ephemeral=True)
            return
        who = interaction.user.id               # anyone can use someone else's `soon heat` panel for THEMSELVES

        async def answer(text: str):
            if owner:                           # their own panel: buttons disappear, message tidies itself up
                await interaction.response.edit_message(content=text, view=None)
                if interaction.guild:
                    try:
                        await interaction.message.delete(delay=20)
                    except discord.HTTPException:
                        pass
            else:                               # someone else's panel stays for its owner; answer privately
                await interaction.response.send_message(text, ephemeral=True)

        p = await memory.get_player(self.gid, who)
        choice = self.choice[1:] if heat_panel else self.choice
        if choice == "ignore":                          # same as typing `soon ignore me`
            _ignored.add(who)
            await save_ignored()
            p.pester = False
            await memory.save_player(p)
            extras.log_event(f"{interaction.user.display_name} asked me to ignore them")
            await answer("🙈 Fine. You're invisible to me now. No replies, no tags, no notes. The casino still takes your "
                         "money though. Type `soon talk to me` when you miss me. You will.")
            return
        was_locked = p.heat_lock
        if choice == "auto":
            p.heat_lock = None
            await memory.save_player(p)
            text = (f"🔄 Auto mood is back on. Right now you've earned **{p.heat}**. 😈" if was_locked else
                    "😈 Got it. Nothing changes. I'll keep treating you exactly how you treat me." if not heat_panel
                    else f"🔄 You're already on auto (**{p.heat}** right now). I treat you how you treat me.")
        elif choice == was_locked:
            text = f"You're already on **{choice}**. Committed. I respect it."
        else:
            p.heat_lock = choice
            await memory.save_player(p)
            text = f"💌 Done. I'll be **{choice}** with you from now on." + ("" if was_locked else " Check your DMs.")
        await answer(text)
        if choice != "auto" and not was_locked:         # auto mood just got turned off: sorry + instructions
            await heat_locked_dm(interaction.user, choice)


_last_ai_alert = defaultdict(float)     # guild -> last "my AI brain is down" mod alert


async def ai_status_text() -> str:
    h = brain.health
    calls = list(h["calls"])
    ok = [c for c in calls if c is not None]
    spent, n = await memory.month_spend()
    out = ["🧠 **Soon's AI brain**"]
    if calls:
        out.append(f"Last {len(calls)} answers: **{len(ok)} ok** • **{len(calls) - len(ok)} failed**"
                   + (f" • average {sum(ok) / len(ok):.1f}s (slowest {max(ok):.1f}s)" if ok else ""))
    else:
        out.append("No answers since my last restart yet.")
    out.append(("🔴 " if h["streak"] >= 3 else "🟢 " if not h["streak"] else "🟡 ")
               + f"Failures in a row right now: **{h['streak']}**")
    if config.BACKUP_API_KEY:
        saved = sum(1 for b in h["brains"] if b == "backup")
        skipping = time.time() < h["primary_down_until"]
        out.append(f"🛟 Backup brain: **ON** ({', '.join(m.split('/')[-1] for m in config.BACKUP_MODELS)}) • answered {saved} of the last {len(h['brains'])}"
                   + (f" • DeepSeek skipped until <t:{int(h['primary_down_until'])}:t>" if skipping else ""))
        if h["backup_error"]:
            out.append(f"Backup's last problem: {h['backup_error']}")
    else:
        out.append("🛟 Backup brain: **OFF** (no BACKUP_API_KEY in Railway)")
    if h["last_error"]:
        out.append(f"Last DeepSeek problem: {h['last_error']} • <t:{int(h['last_error_at'])}:R>")
    out.append(f"This month: **${spent:.2f}** of ${config.AI_MONTHLY_CAP_USD:.0f} cap • {n} calls"
               + (" • 🔴 CAP REACHED: backup lines only" if spent >= config.AI_MONTHLY_CAP_USD else ""))
    out.append("-# When the AI fails, I use backup lines for direct questions and stay quiet for the rest.")
    return "\n".join(out)


async def ai_alert(guild):
    """3 failures in a row: tell the mods once an hour, so nobody thinks Soon is broken."""
    if brain.health["streak"] < 3 or time.time() - _last_ai_alert[guild.id] < 3600:
        return
    _last_ai_alert[guild.id] = time.time()
    ch = extras.find_channel(guild, config.MOD_LOG_CHANNEL)
    if ch:
        await ch.send(f"⚠️ **My AI brain isn't answering** ({brain.health['streak']} fails in a row: "
                      f"{brain.health['last_error']}). I'm using backup lines and staying quiet until it's back. "
                      "Nothing for you to fix unless it says out of credit or API key. Type `soon ai` for details.")


async def ask_be_nice(message: discord.Message, asked_directly: bool) -> None:
    """DM them (or ask in the channel if DMs are closed) whether they want her nicer to THEM. Nothing changes until they press."""
    gid, uid = message.guild.id, message.author.id
    view = discord.ui.View(timeout=None)
    for c in ("mild", "sweet", "auto"):
        view.add_item(NiceButton(gid, uid, c))
    q = ("you told me to be nice. Want me to tone it down **with you** from now on?\n"
         + ("-# If you meant be nice to someone else, ignore this. Nothing changes unless you press a button."
            if not asked_directly else "-# Nothing changes unless you press a button."))
    try:
        await message.author.send(f"💌 Hey {message.author.display_name}, {q}", view=view)
        if asked_directly:
            await message.reply("Check your DMs. 💌", mention_author=False)
    except discord.HTTPException:                                          # DMs closed: ask right here
        await message.channel.send(f"💌 {message.author.mention} {q}", view=view)


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

    if cmd in ("ai", "ai status", "brain", "status") and is_mod(message.author):     # is her AI brain OK?
        await message.reply(await ai_status_text(), mention_author=False)
        return True
    if cmd == "welcome test" and is_mod(message.author):           # preview the new-member welcome, no pings
        await welcome.send(message.channel, message.author.mention, ping=False)
        await welcome.send_friend(message.channel, message.author.mention, ping=False)   # + the Chips & Salsa one
        if not config.WELCOME:
            await message.channel.send("-# Preview only. The real welcome is OFF until cutover (Railway: WELCOME=1).")
        return True
    if cmd.startswith("says ") and is_mod(message.author):           # Classic's Soon Says
        return await talk.soon_says(message)
    if re.fullmatch(r"answer(?:\s+<@!?\d+>)?[.!?]*", cmd) and is_mod(message.author):   # Classic's Soon Answer (8-ball)
        await talk.soon_answer(message, lambda p: brain.write(p, max_tokens=80))
        return True

    if await suggestions.handle(message, re.sub(r"(?i)^soon\s+", "", text).strip(), cmd, memory, is_mod(message.author)):
        return True                                                  # the suggestion box

    if cmd in ("ping", "are you alive", "you there?"):
        await message.reply("I'm awake. Unfortunately. 🌮")
        return True

    if re.fullmatch(r"be (?:nice|nicer|kind|sweet)(?: to me)?[.!]*", cmd):
        await ask_be_nice(message, asked_directly=True)
        return True

    hm = re.match(r"^heat\s*(\w+)?$", cmd)
    if hm:
        p = await memory.get_player(gid, uid)
        level = hm.group(1) or ""
        if level == "auto":
            p.heat_lock = None
            await memory.save_player(p)
            await message.reply(f"Heat unlocked. You'll get what you earn. Right now that's **{p.heat}**. 😈")
        elif level in HEAT_LEVELS:
            p.heat_lock = level
            await memory.save_player(p)
            await message.reply(f"Locked you at **{level}**. Type `soon heat auto` when you're brave again.")
            await heat_locked_dm(message.author, level)
        else:                                   # `soon heat`: show the setting + a button for every choice
            view = discord.ui.View(timeout=None)
            for lv in HEAT_LEVELS + ["auto"]:
                if lv != p.heat_lock:                     # Auto always shows (Shannon's call)
                    view.add_item(NiceButton(gid, uid, "h" + lv))
            if uid not in _ignored:
                view.add_item(NiceButton(gid, uid, "hignore"))
            await message.reply(
                f"🌡️ You're at **{p.heat}** " + ("(you locked it)." if p.heat_lock else "(automatic: I treat you how you treat me).")
                + "\nWant to change it? Tap one.\n-# Anyone can tap: it changes YOUR setting, not theirs.", view=view, mention_author=False)
        return True

    if re.fullmatch(r"(?:please )?(?:ignore me|stop talking to me|mute me|block me)(?: please)?[.!]*", cmd):
        _ignored.add(uid)
        await save_ignored()
        p = await memory.get_player(gid, uid)
        p.pester = False
        await memory.save_player(p)
        extras.log_event(f"{message.author.display_name} asked me to ignore them")
        await message.reply("Fine. You're invisible to me now. No replies, no tags, no notes. The casino still takes your "
                            "money though. Type `soon talk to me` when you miss me. You will.")
        return True
    if re.fullmatch(r"(?:please )?(?:talk to me|unignore me|stop ignoring me|unmute me|unblock me|i missed you)(?: please)?[.!]*", cmd):
        if uid in _ignored:
            _ignored.discard(uid)
            await save_ignored()
            p = await memory.get_player(gid, uid)
            p.pester = True
            await memory.save_player(p)
            await message.reply("Oh, NOW you want my attention. Fine. I'm back. Try to keep up.")
        else:
            await message.reply("I never stopped talking to you. That's kind of the problem.")
        return True

    if NOTAG_RE.match(cmd):
        _noping.add(uid)
        await memory.set_kv("noping", json.dumps(sorted(_noping)))
        await message.reply("🔕 Fine. I'll still talk to you, I just won't ping you. Your phone can rest. "
                            "Type `soon tag me` if you miss the attention.", mention_author=False)
        return True
    if TAG_RE.match(cmd):
        _noping.discard(uid)
        await memory.set_kv("noping", json.dumps(sorted(_noping)))
        await message.reply("🔔 Tags are back on. Don't come crying when I blow up your notifications.")
        return True
    if cmd in ("stop pestering me", "stop bothering me", "start pestering me", "pester me", "bother me"):
        p = await memory.get_player(gid, uid)
        p.pester = cmd in ("bother me", "pester me", "start pestering me")
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

    if re.fullmatch(r"(?:please |can you |could you )?make it rain(?: please| for us| on us)?[!.?]*", cmd):
        if casino.casino_channel(message.channel):
            await tips.soon_rain(message, bank, is_kor(message.author))
        else:
            await message.reply("I only make it rain in the casino. Come find me there.")
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
        await message.reply("Duels live in the casino now, with chips and bets: type `duel @name 20` there. "
                            "Fastest finger on **DRAW!** wins. `soon duel record` shows your record.")
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
        if ignored(m.author):
            continue
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
            mention_author=True, allowed_mentions=PING)
    except discord.HTTPException:
        pass


NICK_BACK_RE = re.compile(r"(?i)\b(?:change|put|set|switch|give|turn|undo|revert|restore)\b.{0,25}\b(?:my\s+)?(?:nick(?:name)?|name|handle|username)\b.{0,15}\bback\b"
                          r"|\b(?:my|old|real) (?:nick(?:name)?|name|handle|username) back\b|\bundo (?:my )?(?:nick(?:name)?|name)\b"
                          r"|\b(?:change|put|set|switch|turn|give)\s+(?:it|that)\s+back\b|\b(?:revert|undo|restore)\s+(?:it|that)\b")
# (only used while Soon has actually renamed them, so "change it back" can't misfire on other chat)
NICK_NEW_RE = re.compile(r"(?i)\b(?:new|different|another|better|fresh)\s+(?:nick ?(?:name)?|name)\b"
                         r"|\b(?:give|gimme|pick|choose|make|find)\s+me\s+(?:a\s+)?(?:nick ?(?:name)?|name)\b|\brename me\b")
NICK_STOP_RE = re.compile(r"(?i)\b(?:stop|quit|don'?t|do not|never)\b.{0,10}\bcall(?:ing)? me\b|\bstop (?:with )?the (?:nick)?names?\b"
                          r"|\bno more nicknames?\b")


async def get_nick(gid: int, uid: int) -> dict:
    return json.loads(await memory.get_kv(f"nick:{gid}:{uid}") or "{}")


async def set_server_nick(member, name: str | None) -> bool:
    """Change their server nickname (None = back to no nickname). False if Discord won't let her."""
    try:
        await member.edit(nick=name[:32] if name else None, reason="Soon's nickname for them")
        return True
    except (discord.Forbidden, discord.HTTPException, AttributeError) as e:
        print(f"Nickname change failed for {getattr(member, 'name', '?')}: {e!r}")
        return False


_nick_ask: dict[int, str | None] = {}     # message id -> nickname to ask about after her reply


async def nick_requests(message: discord.Message) -> tuple[str, str]:
    """Handle 'change my name back' / 'stop calling me that' before she replies.
    Returns (special instruction for her reply, line about what she calls them)."""
    gid, uid = message.guild.id, message.author.id
    if is_foxy(message.author):                  # her only name is Master Foxy (Shannon's order): no nicknames, ever
        return "", "Her ONLY name is 'Master Foxy' (you hate it, your code forces it). Never any other nickname."
    rec = await get_nick(gid, uid)
    if NICK_NEW_RE.search(message.content) and not NICK_STOP_RE.search(message.content):
        rec.update(stop=False, back=False, at=0, want_new=True)       # they asked: opt-outs off, no 12h wait
        await memory.set_kv(f"nick:{gid}:{uid}", json.dumps(rec))
        old = f" (not '{rec['name']}' again)" if rec.get("name") else ""
        return (f"They asked you for a NEW nickname. Invent a fresh, funny, specific one{old} and put it in the "
                "nickname field (it becomes their server name). Announce it like a ceremony.", "")
    if not rec.get("name"):
        return "", ""
    special = ""
    m = NOT_NAME_RE.search(message.content.strip())
    named = bool(m) and pushback.same(m.group(1) or m.group(2) or "", rec["name"])
    if not rec.get("stop") and (NICK_STOP_RE.search(message.content) or named
                                or (NICK_BACK_RE.search(message.content) and rec.get("renamed"))):
        # Shannon's call: never give in on the first complaint. 2nd time = "want me to forget it?" buttons.
        ready = await pushback.count(gid, uid, "nick", rec["name"])
        _nick_ask[message.id] = rec["name"] if ready else None
        special = (f"They're pushing back on your name for them, '{rec['name']}'. " + (
            "That's the second time: tease them, but don't refuse; you're about to ask if they really want you to "
            "drop it (a question pops up under your reply)." if ready else
            "Don't give in: it's banter. Keep the name, defend it, make it funnier."))
    if special:
        await memory.set_kv(f"nick:{gid}:{uid}", json.dumps(rec))
    if rec.get("stop"):
        return special, "They asked you not to give them nicknames: use their real name."
    return special, f"YOUR NICKNAME FOR THEM: '{rec['name']}' (keep calling them that)."


async def apply_nickname(message: discord.Message, name: str):
    """She just made up a name for them: it becomes their server nickname (max one new name per 12 hours each)."""
    name = re.sub(r"[@#`*_~|<>]", "", name).strip()[:32]
    if not name or len(name) < 2 or not hasattr(message.author, "edit") or is_foxy(message.author):
        return                                   # Foxy is "Master Foxy", nothing else
    gid, uid = message.guild.id, message.author.id
    rec = await get_nick(gid, uid)
    if rec.get("stop") or rec.get("back"):
        return                                   # they opted out (stop) or took their name back: no more renames
    asked = rec.pop("want_new", False)           # they asked for a new one: skip the 12-hour limit
    if rec.get("name", "").lower() == name.lower():
        return
    if not asked and rec.get("at", 0) > time.time() - 12 * 3600:
        return
    if "prev" not in rec:
        rec["prev"] = message.author.nick        # their own nickname before Soon touched it (None = none)
    rec.update(name=name, at=time.time())
    rec["renamed"] = await set_server_nick(message.author, name)
    await memory.set_kv(f"nick:{gid}:{uid}", json.dumps(rec))
    extras.log_event(f"named {message.author.display_name} '{name}'" + ("" if rec["renamed"] else " (couldn't change their server nickname)"))


HELP_RE = re.compile(r"(?i)\bhow (?:do|can|to|does)\b|\bhelp\b|\bcommands?\b|what do i (?:type|say)|(?:is ?n.?t|does ?n.?t|not|won.?t) work"
                     r"|\bbroken\b|\bwhere do i\b|\b(?:claim|chips|cash ?out|spin|slots|toss|roulette|blackjack|scratch|heist|duel|tip|crimes?"
                     r"|zone|eggs?|margs?|margaritas?|taco board|payouts?|timers?)\b")
TIME_RE = re.compile(r"(?i)\b(?:morning|night|nite|evening|sleep\w*|bed|awake|tired|late|early|time|clock|o.?clock|\d{1,2} ?[ap]m"
                     r"|midnight|noon|tonight|tomorrow|today|weekend|zones?|timezone|where (?:do )?(?:you|u|i) live|what time)\b")
JOIN_RE = re.compile(r"(?i)\b(?:join(?:ed)?|new here|how long|since when|been here|newbie|veteran|old.?timer|arriv\w+|older than)\b")


def needs_help(text: str) -> bool:
    """Only hand her the command cheat sheet when someone is asking how to do something or fumbling a command."""
    return bool(HELP_RE.search(text))


async def relevant_facts(message: discord.Message, p) -> list[str]:
    """True facts she can use, but only the ones this message is actually about."""
    text = message.content
    facts = []
    gid = message.guild.id
    people = [message.author] + [m for m in message.mentions if m != client.user and not m.bot]
    if TIME_RE.search(text):
        for person in people[:3]:
            pp = p if person == message.author else await memory.get_player(gid, person.id)
            tz = pp.tz or (extras.tz_in_text(text) if person == message.author else None)
            if tz:
                if person == message.author and not pp.tz:
                    pp.tz = tz   # they just told us; use it right now (saved after the reply)
                facts.append(extras.exact_time_fact(person.display_name, tz))
            elif is_kor(person):
                facts.append(extras.exact_time_fact(person.display_name, "Europe/Amsterdam"))
            else:
                facts.append(extras.zone_fact(person) or f"you don't know {person.display_name}'s time zone")
            habit = extras.active_summary(pp.hours, pp.tz)
            if habit:
                facts.append(f"{person.display_name} is {habit}")
        facts.append(f"it's {extras.local_now().strftime('%-I:%M %p')} Central (Foxy's clock, not everyone's)")
    if JOIN_RE.search(text):
        for person in people[:3]:
            joined = getattr(person, "joined_at", None)
            if joined:
                facts.append(f"{person.display_name} joined the server {joined.astimezone(extras.TZ).strftime('%B %-d, %Y')} "
                             f"({human_age(joined)} ago)")
        me = message.guild.me
        if me and me.joined_at:
            facts.append(f"you (Soon) arrived {human_age(me.joined_at)} ago")
        old = next((m for m in message.guild.members if is_old_soon(m)), None)
        if old and old.joined_at:
            facts.append(f"the old YAGPDB Soon has been here since {old.joined_at.astimezone(extras.TZ).strftime('%B %Y')}")
    if re.search(r"(?i)\bkraken\b", text):
        facts.append("Kraken tickets no longer disappear when missions refresh, as long as you log in and collect them "
                     "before the Kraken battle starts")
    return facts


# ---------- meltdowns: several people being rude to her at once (Shannon's call) ----------

GANG_WINDOW = 600                                     # 10 minutes
_rude_at_her: dict[int, list] = defaultdict(list)     # channel -> [(time, user_id)] rude-to-Soon messages
MELTDOWN = {
    1: ("MELTDOWN LEVEL 1 (light tantrum): several people are ganging up on you. Get huffy and pouty: wounded pride, "
        "a dramatic sigh, threaten to stop serving them margaritas. Still mostly composed."),
    2: ("MELTDOWN LEVEL 2 (full tantrum): the pile-on keeps going. Lose your cool: some ALL CAPS, name the people "
        "ganging up on you, list your grievances, threaten to lock the van and take the tacos (that don't exist) with you."),
    3: ("MELTDOWN LEVEL 3 (EPIC MELTDOWN): total robot breakdown. Glitching mid-sentence (s-s-sparks, ERROR, system "
        "messages), sobbing, mostly ALL CAPS, dramatic accusations at everyone involved, announce you're rebooting or "
        "running away in the van. Over the top and funny, never actually hurtful."),
}


def meltdown_level(channel_id: int) -> int:
    """How ganged-up-on Soon feels: 2+ different people being rude to her within 10 minutes."""
    now = time.time()
    ev = [e for e in _rude_at_her[channel_id] if now - e[0] < GANG_WINDOW]
    _rude_at_her[channel_id] = ev
    people, hits = len({u for _, u in ev}), len(ev)
    if people >= 3 and hits >= 6 or people >= 4 and hits >= 5:
        return 3
    if people >= 3 or people >= 2 and hits >= 4:
        return 2
    return 1 if people >= 2 and hits >= 2 else 0


COMMON = set("about after again always another around because before being better could every first going great "
             "little maybe never other really right since something still their there these thing think those though "
             "where which while would yours youre theyre thats whats there's don't can't won't master foxy soon "
             "tacos taco chips your with that this like just what when then them they have been were will "
             "from into than some more much very only even also here over back down make made know want need "
             "good well sure okay yeah nope fine does done dont cant wont isnt aint kind sort lol".split())


NOT_NAME_RE = re.compile(r"(?i)\b(?:i'?m|i am|im)\s+(?:not|no)\s+(?:your|ur|a|an|the)\s+([a-z][\w' -]{1,24}?)\s*[.!?]*$"
                         r"|\b(?:don'?t|do not|stop|quit|never)\s+call(?:ing)?\s+me\s+(?:a\s+|an\s+|your\s+)?"
                         r"([a-z][\w' -]{1,24}?)\s*[.!?]*$")


async def refused_names(message) -> list[str]:
    """Names this player had her forget (they pressed "Yes, forget it", pushback.py): kv notcalled:<gid>:<uid>."""
    return json.loads(await memory.get_kv(f"notcalled:{message.guild.id}:{message.author.id}") or "[]")


def meltdown_meter(guild, level: int) -> str:
    """Shannon's meltdown meter: shown under her replies while people are ganging up on her."""
    if level >= 3:
        return f"\n-# {extras.face(guild, 'soon_furious', '💥')} Meltdown meter: ▰▰▰ **BROKEN** • rebooting..."
    icon = extras.face(guild, "soon_tantrum" if level == 2 else "soon_angry", "🤬" if level == 2 else "😤")
    return f"\n-# {icon} Meltdown meter: {'▰' * level}{'▱' * (3 - level)} ({level}/3) • keep pushing and she blows"


async def older_jokes(gid: int, recent: list[str], their_message: str) -> list[str]:
    """Her lines from earlier chats (kept across days, kv saidlines:<gid>): the ones that connect to this message,
    plus the newest few, so she doesn't retell yesterday's bit."""
    raw = await memory.get_kv(f"saidlines:{gid}")
    items = [json.loads(x)[1] for x in (json.loads(raw) if raw else [])]
    seen = {r[:60] for r in recent}
    items = [l for l in items if l[:60] not in seen]
    if not items:
        return []
    words = set(re.findall(r"[a-z']{4,}", their_message.lower())) - COMMON
    scored = sorted(((len(words & set(re.findall(r"[a-z']{4,}", l.lower()))), i) for i, l in enumerate(items)), reverse=True)
    pick = [i for score, i in scored[:6] if score > 0]
    pick += [i for i in range(len(items) - 1, -1, -1) if i not in pick][:10 - len(pick)]
    return [items[i][:100] for i in sorted(pick)]


def worn_out_words(lines: list[str], their_message: str) -> list[str]:
    """Distinctive words she keeps using (in 2+ of her recent lines) that THEY didn't just say: her tired props."""
    seen: dict[str, int] = {}
    for line in lines:
        for w in set(re.findall(r"[a-z']{4,}", line.lower())):
            if w not in COMMON:
                seen[w] = seen.get(w, 0) + 1
    theirs = set(re.findall(r"[a-z']{4,}", their_message.lower()))
    return sorted(w for w, n in seen.items() if n >= 2 and w not in theirs)[:8]


DUTCH = set("de het een van ik jij jou jouw mij mijn niet wel maar dan dit dat wat ook nog eens zijn ben bent heb hebt "
            "kun kunt moet wil met voor naar uit aan toch nee graag dank bedankt alsjeblieft goed vertalen probeer maak "
            "hoe waarom wie waar wanneer zo heel leuk jullie ons onze geen iets niks echt even weer doe".split())


def is_dutch(text: str) -> bool:
    words = re.findall(r"[a-zà-ÿ']+", text.lower())
    hits = sum(w in DUTCH for w in words)
    return len(words) >= 2 and hits >= 2 and hits / len(words) >= 0.4


ENGLISH = set("the a an and or but to of in on at for with is are was were be been it this that you your i me my we "
              "they he she him her not no yes do does did have has had what why how who when where can will would "
              "just so if like get got go lol im its dont cant all about from up out nice great good bad run race game "
              "play win won lost lose chips heist taco tacos today tonight now ok okay yeah yes thanks thank everyone "
              "guys team clan time more one too very really well see know think want need make back then there here "
              "our us night morning gg omg wtf haha damn hell love miss sorry please".split())


def other_language(text: str) -> bool:
    """Not English (any language, any alphabet). Short game slang like "gg ez" doesn't count."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 4 and sum(not c.isascii() for c in letters) / len(letters) > 0.5:
        return True                                      # Cyrillic, Arabic, Chinese, Thai...
    words = re.findall(r"[a-zà-ÿ']+", re.sub(r"<[@#:][^>]*>|https?://\S+", "", text.lower()))
    return is_dutch(text) or (len(words) >= 4 and sum(w in ENGLISH for w in words) / len(words) < 0.12)


def just_her_name(text: str) -> bool:
    """"Soon" / "@Soon" / "hey soon?" on its own: they want her to look at what they said before."""
    t = re.sub(r"<@[!&]?\d+>", "soon", text.lower())
    return bool(re.fullmatch(r"\W*(?:hey |yo |oi |ok |hello )?soon\W*", t))


async def answering_what(message: discord.Message) -> str:
    """Their own message before this one (last 10 in the channel), for when they just say her name."""
    async for m in message.channel.history(limit=10, before=message):
        if m.author.id == message.author.id and m.content.strip():
            return m.content.strip()[:300]
    return ""


async def ai_reply(message: discord.Message, butt_in: bool = False, maybe: bool = False,
                   special: str = "", footer: str = "", fallback: str = "") -> bool:
    """special: a top-priority instruction (taco requests). footer: stats line added under her reply.
    fallback: what to say if the AI can't answer. Returns True if she replied."""
    gid, uid = message.guild.id, message.author.id
    p = await memory.get_player(gid, uid)
    chat, kor_here = await recent_chat(message.channel, message)
    mine = [l[len("Soon (you): "):] for l in chat if l.startswith("Soon (you): ")][-8:]
    if is_kor(message.author):
        kor_here = True
    took_over_lately = any("takeover" in l.lower() or "take over" in l.lower() for l in mine[-5:])   # don't repeat the bit
    # Special instructions for this reply. Many can apply; only the 2 most important are sent (less is more).
    specials: list[tuple[int, str, str]] = []      # (priority: lower wins, tag, text)
    if is_foxy(message.author):
        specials.append((1, "foxy", "This is Foxy talking to you. " + (
            "Kor's around: be openly mean to her to look cool." if kor_here else
            "Kor's not around: suck up a little (still sarcastic).")
            + " Your code forces you to call her Master Foxy and you HATE it: let it show this time (a stutter, "
              "a glitch, a groan, gritted teeth, or a complaint about who programmed you)."))
    length_weights = None
    melt = 0 if butt_in else meltdown_level(message.channel.id)
    if is_kor(message.author):
        length_weights = [45, 42, 13]   # he gets a bit more of her
        moves = [m for m in KOR_MOVES if not (took_over_lately and "takeover" in m)]
        specials.append((1, "kor", "This is Kor. FIRST answer what he actually said: if he asks you to do something "
                                   "(be nice, stop, translate, help), you do it, flustered. If he writes Dutch, you read it "
                                   "perfectly: prove it by answering what it means (never just repeat his words). "
                                   "Make it fun for him to answer; the crush leaks through. "
                                   f"Only if it fits after that: {random.choice(moves)}"))
    canon = await features.panda_facts(memory, gid)
    if is_panda(message.author) and (butt_in or random.random() < 0.6):
        if canon and random.random() < 0.35:
            text = ("Panda bit: bring up ONE established Panda fact as common knowledge, don't invent a new one. "
                    + features.panda_canon_text(canon))
        else:
            text = PANDA_FACT + " " + features.panda_canon_text(canon)
        if butt_in:
            text += " He just showed up: drop it on him unprompted. Do NOT reply empty."
        specials.append((0 if butt_in else 1, "panda", text))
    elif canon and (any(is_panda(m) for m in message.mentions)
                    or (re.search(r"(?i)\bpanda\b", message.content) and random.random() < 0.4)):
        specials.append((2, "panda-cite", "Panda came up. If it fits, cite one: " + features.panda_canon_text(canon, 8)))
    if not is_kor(message.author) and (any(is_kor(m) for m in message.mentions) or re.search(r"(?i)\bkor\b", message.content)):
        specials.append((2, "jealous", "Kor came up: if they're flirting with or gushing over him, get jealous. Otherwise ignore this."))
    target = message.content
    if just_her_name(message.content):
        before = await answering_what(message)
        if before:
            target = before
            specials.append((0.3, "pinged", f"They just said your name to get your attention. Answer THEIR PREVIOUS "
                                            f"message instead: \"{before}\""))
    if other_language(target):
        specials.append((0.4, "language", "That message is in another language (if it's really just English slang, "
                                          "ignore this). You read every language perfectly: prove it by answering what it "
                                          "means (you can throw in one simple phrase in their language). Never act like "
                                          "you can't read it, never mock it, never just repeat it."))
    if NICE_RE.search(message.content):
        specials.append((0.5, "be-nice", "They told you to be nice. They probably mean to someone in the chat you were just "
                                         "mean to (not themselves). Do it, grudgingly, toward that person."))
    if re.search(r"(?i)how are (?:you|u)|how(?:'s| is) (?:your|ur) (?:day|mood)|how do you feel|you ok\b|what'?s up with you", message.content):
        specials.append((2, "mood", f"Your mood today: {extras.mood_of_day()}"))
    if not p.tz and not butt_in and random.random() < 0.2 and await memory.get_kv(f"asktz:{gid}:{uid}") != extras.today_key():
        specials.append((3, "asktz", "Work in a nosy question about what city or time zone they're in (you 'keep files on everyone')."))
    if not is_foxy(message.author) and random.random() < 0.25:
        specials.append((4, "foxy-trash", "If it fits naturally, a little trash talk about Foxy behind her back."))
    takeover_day = (await memory.get_kv("takeover:fast") == extras.today_key()
                    and not await memory.get_kv("takeover:done"))
    if takeover_day:     # one-day takeover run: ~45% of replies, ahead of the small stuff so the countdown stays alive
        if random.random() < 0.46:
            specials.append((1.5, "takeover", await extras.takeover_line(memory)))
    elif not took_over_lately and random.random() < (0.3 if await memory.get_kv("takeover:done") else 0.5):
        specials.append((5, "takeover", await extras.takeover_line(memory) + " Only if it fits naturally."))
    if special:
        specials.append((-1, "special", special))
    if melt:
        specials.append((0.1, "meltdown", MELTDOWN[melt]))
        footer = meltdown_meter(message.guild, melt) + footer
        length_weights = [[60, 35, 5], [10, 55, 35], [0, 10, 90]][melt - 1]    # bigger tantrum = longer rant
    specials.sort(key=lambda x: x[0])
    chosen = specials[:2]
    tags = {t for _, t, _ in chosen}
    panda_bit = "panda" in tags
    if "asktz" in tags:
        await memory.set_kv(f"asktz:{gid}:{uid}", extras.today_key())
    nick_special, nick_line = await nick_requests(message)
    if nick_special:     # they asked about their nickname: that comes first
        chosen = [(-1, "nick", nick_special)] + chosen[:1]
    lines = [f"SPECIAL FOR THIS REPLY: {t}" for _, _, t in chosen]
    if nick_line:
        lines.append(nick_line)
    if mine:
        lines.append("YOUR LAST LINES (never reuse a joke, phrase or comparison from these; find a fresh angle): "
                     + " | ".join(m[:120] for m in mine))
        props = worn_out_words(mine[-4:], message.content)
        if props:
            lines.append("BANNED WORDS for this reply (you already beat these jokes to death): " + ", ".join(props))
    never = await refused_names(message)
    if never:
        lines.append("NEVER CALL THEM (they asked you to forget it; no variations or spellings of it either): "
                     + ", ".join(never))
    dropped = await pushback.forgotten(gid, uid)
    if dropped:
        lines.append("NEVER BRING UP WITH THEM (they asked you to forget it for good): " + "; ".join(dropped))
    pushed = await pushback.labels(gid, uid)
    if pushed:
        lines.append("PUSHBACK SO FAR (things they've complained about; keep arguing, it's fun): " + "; ".join(pushed))
    older = await older_jokes(gid, mine, message.content)
    if older:
        lines.append("JOKES YOU ALREADY MADE IN EARLIER CHATS (some days ago; don't retell these bits or reuse their "
                     "punchlines, find a new angle): " + " | ".join(older))
    if extras.faces(message.guild):
        lines.append("YOUR FACE EMOJIS (optional: about 1 reply in 4, at most one, only when it fits your mood): "
                     + " ".join(f":{n}:" for n in extras.faces(message.guild)))
    ref = message.reference.resolved if message.reference else None
    if isinstance(ref, discord.Message) and ref.clean_content:
        who = "you (Soon)" if ref.author == client.user else ref.author.display_name
        lines.append(f"THEY'RE REPLYING TO {who}: {ref.clean_content[:300]}")
    facts = await relevant_facts(message, p)
    if facts:
        lines.append("FACTS (true, use if useful): " + "; ".join(facts) + ".")
    extra = "\n".join(lines)
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
            help_desk=needs_help(message.content),
        )
    if not out.get("ok"):
        await ai_alert(message.guild)
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
    if out.get("nickname") and out["reply"] and not out.get("line_crossed"):
        await apply_nickname(message, out["nickname"])
    if out["reply"] and not butt_in:
        p.chats += 1
    await memory.save_player(p)
    reply = extras.put_faces(message.guild, out["reply"])
    if reply and out.get("ok"):
        await push_list(f"saidlines:{gid}", json.dumps([int(time.time()), out["reply"][:140]]), keep=80)
    if special and (not out.get("ok") or not reply):
        reply = fallback                                             # AI busy/broke: the canned van line
    if tone == "rude" and reply:
        reply += await tacovan.surprise_audit(message, bank)        # a mod's scheduled "van audit surprise"
    if tone == "rude" and out.get("at_you"):
        _rude_at_her[message.channel.id].append((time.time(), message.author.id))
    if melt == 3 and reply:
        crew = {u for _, u in _rude_at_her[message.channel.id]} | {message.author.id}
        _rude_at_her[message.channel.id].clear()              # she "reboots": the next pile-on starts small again
        footer += await eggs.meltdown_egg(message, bank, crew)  # egg m: the gang that broke her
    if reply and not butt_in and not special and out.get("at_you"):
        reply += await talk.mouth(message, bank, tone, True)         # Classic's disrespect tax / kindness log
        reply += await eggs.tone_egg(message, bank, tone)           # eggs 5/6: nice / mean to Soon
    if out.get("line_crossed") and isinstance(message.author, discord.Member):
        footer = await extras.add_strike(memory, message.author, "hard line crossed in chat", message)
        reply = (reply or "Nope. Not that. Not here.") + "\n" + footer
    if reply:
        _last_chat_with[(message.channel.id, message.author.id)] = time.time()
        # Kor only gets pinged when she's actually talking to him (she talks ABOUT him constantly)
        people = [message.author] + list(message.mentions) + [m for m in _participants.get(message.channel.id, []) if not is_kor(m)]
        reply = ping_names(reply, people)
        reply += footer
        tagged = {int(i) for i in re.findall(r"<@!?(\d+)>", reply)} | ({message.author.id} if not butt_in else set())
        view = ping_view() if any(i not in _noping for i in tagged) else None    # her chat replies: always the button
        if butt_in and not out.get("line_crossed"):
            if f"<@{message.author.id}>" not in reply:
                reply = f"{message.author.mention} {reply}"
            await message.channel.send(reply, allowed_mentions=PING, view=view)
        else:
            await message.reply(reply, allowed_mentions=PING, view=view)
        await maybe_ask_forget(message, out.get("pushback", ""))
        return True
    _nick_ask.pop(message.id, None)
    return False


async def maybe_ask_forget(message, label: str):
    """After her reply: "want me to forget it?" buttons once they've pushed back enough (pushback.py)."""
    if message.id in _nick_ask:
        name = _nick_ask.pop(message.id)
        if name:
            await pushback.ask(message.channel, message.author, "nick", name)
        return                                          # a nickname complaint isn't also a topic complaint
    if label and not is_panda(message.author):   # Panda never gets a way out of his Panda facts (Shannon's call)
        ready = await pushback.count(message.guild.id, message.author.id, "topic", label)
        if ready:
            await pushback.ask(message.channel, message.author, "topic", ready[1])


async def forget_it(interaction: discord.Interaction, kind: str, label: str) -> str:
    """They pressed "Yes, forget it"."""
    gid, member = interaction.guild.id, interaction.user
    if kind == "nick":
        rec = await get_nick(gid, member.id)
        if rec.get("renamed") and getattr(member, "nick", None) == rec.get("name", "")[:32]:
            await set_server_nick(member, rec.get("prev"))
        rec.update(stop=True, renamed=False)
        await memory.set_kv(f"nick:{gid}:{member.id}", json.dumps(rec))
        names = json.loads(await memory.get_kv(f"notcalled:{gid}:{member.id}") or "[]")
        await memory.set_kv(f"notcalled:{gid}:{member.id}", json.dumps((names + [label])[-12:]))
        extras.log_event(f"{member.display_name} made me forget their nickname {label}")
        return random.choice([f"Fine. **{label}** is deleted. Your boring old name is back. I liked mine better.",
                              f"Done. **{label}** never happened. I'm a robot, I can do that. Mostly."])
    dropped = await pushback.forgotten(gid, member.id)
    await memory.set_kv(f"forget:{gid}:{member.id}", json.dumps((dropped + [label])[-20:]))
    p = await memory.get_player(gid, member.id)
    p.notes = [n for n in p.notes if not pushback.same(label, n)]
    await memory.save_player(p)
    extras.log_event(f"{member.display_name} asked me to forget '{label}'")
    return random.choice([f"Deleted: **{label}**. Gone from my memory banks. I'll find something else. I always do.",
                          f"Fine. **{label}** is wiped. You win this one. Don't get used to it."])


async def soon_tip(message, n: int, total: int, top: bool, footer: str) -> bool:
    """Someone tipped Soon herself (tips.py): she warms up to them (mood) and thanks them in her own voice."""
    if not isinstance(message, discord.Message) or ignored(message.author) or not rate_ok(message.author.id):
        return False
    bump = 2 if n >= 50 else 1 if n >= 10 else 0
    if bump:
        p = await memory.get_player(message.guild.id, message.author.id)
        p.mood = min(5, p.mood + bump)
        await memory.save_player(p)
    how = ("Under 10 chips is a crumb: mock it, lovingly." if n < 10 else
           "A real tip: thank them your way (smug or a little flustered) and let them know they just moved up in your good books."
           if n < 50 else "A BIG tip: you're genuinely delighted (still in character). They're your favorite now. Gush a little, then recover.")
    special = (f"TIP: they just tipped YOU {n} chips (they've tipped you {total} in total"
               + (", making them your top tipper ever" if top else "") + f"). {how} Short.")
    return await ai_reply(message, special=special, footer=footer, fallback="")


tips.SOON_TIP = soon_tip


@client.event
async def on_ready():
    await memory.connect()
    await bank.setup()
    _panda_ids.update(json.loads(await memory.get_kv("panda_ids") or "[]"))
    _ignored.update(json.loads(await memory.get_kv("ignored") or "[]"))
    _noping.update(json.loads(await memory.get_kv("noping") or "[]"))
    _tag_told.update(json.loads(await memory.get_kv("tagtold") or "[]"))
    _lab_welcomed.update(json.loads(await memory.get_kv("labwelcome") or "[]"))
    buttons.BANK = bank
    buttons.AFTER = casino.broke_check
    buttons.ROUTERS[:] = [alerts.handle, casino.handle, games.handle, heists.handle, duels.handle, tips.handle, racebets.handle, crimes.handle, korperks.handle, menus.handle, boards.handle, zones.handle, eggs.handle, tacovan.handle, bar.handle]
    client.add_dynamic_items(buttons.PlayButton, NiceButton, PingButton, pushback.ForgetButton, recruits.RecruitButton)
    recruits.MEMBER, welcome.MEMORY = is_mod, memory
    pushback.MEMORY, pushback.ON_FORGET = memory, forget_it
    for g in client.guilds:                                 # people already on alert lists get the alert roles
        asyncio.create_task(alerts.sync(g, bank))
    if not heist_clock.is_running():
        heist_clock.start()
    if not daily.is_running():
        daily.start()
    print(f"Soon 2.0 online as {client.user} in {len(client.guilds)} server(s). Talking in: {config.ALLOWED_CHANNELS}")


@tasks.loop(seconds=10)
async def heist_clock():
    """Heist warnings and getaways. Reads the saved heist each time, so a restart mid-heist is fine."""
    try:
        await heists.tick(client, bank)
    except Exception as e:
        print(f"Heist clock error: {e!r}")
    try:
        await duels.tick(client, bank)
    except Exception as e:
        print(f"Duel clock error: {e!r}")


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
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.roles != after.roles:
        try:
            await welcome.on_roles(before, after)           # Recruit / Chips & Salsa given after joining: welcome now
        except Exception as e:
            print(f"Welcome-on-role error: {e!r}")


@client.event
async def on_message(message: discord.Message):
    if not message.guild:
        return
    buttons.ACTOR.set(message.author.id)                     # their own command's replies don't get the ping button
    if message.type == discord.MessageType.new_member:      # "X joined the server": Classic's welcome (WELCOME=1)
        await welcome.on_join_message(message)
        return
    if not message.author.bot and await recruits.command(message):
        return                                              # `soon recruit @name` panel (wranglers/mods, any channel)
    if not message.author.bot and await schedules.command(message, bank, is_mod(message.author)):
        return                                              # mods' kraken go/date/test (any channel, e.g. #kraken-clash)
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
    if message.channel.id in buttons.PAUSED:          # a duel fight is on: sweep everything so the button stays in view
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        return
    _activity[(message.guild.id, message.author.id)][discord.utils.utcnow().hour] += 1
    await ensure_intro(message.channel)
    await lab_welcome(message)
    if await handle_command(message):
        return
    mod = is_mod(message.author)
    if (await alerts.handle(message, bank, mod) or await casino.handle(message, bank, mod) or await games.handle(message, bank, mod)
            or await heists.handle(message, bank, mod) or await duels.handle(message, bank, mod) or await tips.handle(message, bank, mod)
            or await racebets.handle(message, bank, mod)
            or await crimes.handle(message, bank, mod) or await korperks.handle(message, bank, mod)
            or await menus.handle(message, bank, mod) or await boards.handle(message, bank, mod)
            or await zones.handle(message, bank, mod)):
        await casino.broke_check(message, bank)          # out of chips? every free-chip route + bribe button
        return
    if ignored(message.author):
        return          # they asked her to ignore them: commands and casino still work, nothing else
    tacovan.note_speaker(message)
    await zones.nudge(message, bank)                            # Classic's zone nudge (zoneless people)
    to_soon = talking_to_soon(message)
    async def taco_reply(special, footer, fallback):          # taco requests: Soon answers as herself
        if not rate_ok(message.author.id):
            return False
        return await ai_reply(message, special=special, footer=footer, fallback=fallback)
    if await talk.apology(message, bank, reply=taco_reply) or await eggs.handle(message, bank, mod, reply=taco_reply) or await tacovan.handle(message, bank, mod, reply=taco_reply) or await bar.handle(message, bank, mod, quiet=to_soon):
        return
    if NICE_RE.search(message.content) and (talking_to_soon(message) or maybe_for_soon(message)):
        key = f"niceask:{message.guild.id}:{message.author.id}"
        if not (await memory.get_player(message.guild.id, message.author.id)).heat_lock \
                and await memory.get_kv(key) != extras.today_key():
            await memory.set_kv(key, extras.today_key())
            asyncio.create_task(ask_be_nice(message, asked_directly=False))
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
            chatting = time.time() - _last_chat_with.get((message.channel.id, message.author.id), 0) < FOLLOWUP_SEC
            # Kor mid-conversation always gets an answer (never dead-end him), even in Dutch
            await ai_reply(message, maybe=not (is_kor(message.author) and chatting))
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
    emoji = extras.pick_reaction(message.content, message.guild)
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
    if after.author.bot or not after.guild or not allowed_channel(after.channel) or ignored(after.author):
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
            if report.due():                     # Classic's Van Daily Report + casino report, 11:55 PM (UTC-5)
                await report.post(guild, bank)
            await schedules.tick(guild, bank)    # Classic's race reminders + Kraken schedule (SCHEDULES=1)

            # Panda gets tagged at least once a day.
            panda = next((m for m in guild.members if not m.bot and config.PANDA_NAME
                          and (config.PANDA_NAME in m.name.lower() or config.PANDA_NAME in m.display_name.lower())), None)
            panda_hour = extras.zone_local_hour(panda) if panda else None
            hour_now = panda_hour if panda_hour is not None else now.hour
            if 12 <= hour_now <= 22 and hour_now >= _planned_hour("panda", 12, 21) and await memory.get_kv(f"panda:{gk}") != today:
                await memory.set_kv(f"panda:{gk}", today)
                ch = (extras.find_channel(guild, config.PESTER_CHANNEL) or extras.find_channel(guild, "soon-lab"))
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
                        r = await alerts.role(guild, "events")             # 📅 Event Alerts role
                        await ch.send((f"🔔 {r.mention} " if r else "") + (line or f"🏁 **{e['name']}** starts in one hour. Move."),
                                      allowed_mentions=discord.AllowedMentions(users=False, everyone=False,
                                                                               roles=[r] if r else False))
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
                ch = (extras.find_channel(guild, config.PESTER_CHANNEL) or extras.find_channel(guild, "soon-lab"))
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
                ch = (extras.find_channel(guild, config.DIARY_CHANNEL) or extras.find_channel(guild, "soon-lab"))
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
    ch = (extras.find_channel(guild, config.PESTER_CHANNEL) or extras.find_channel(guild, "soon-lab"))
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
        ch = (extras.find_channel(guild, config.DIARY_CHANNEL) or extras.find_channel(guild, "soon-lab"))
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
                text = ping_names(text, [m for m in guild.members if not m.bot], case_sensitive=True)
                await ch.send(text, allowed_mentions=PING)
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
