"""Soon's daily life: mood of the day, side-eye reactions, the nightly diary, pestering, and hard-line strikes."""
import datetime as dt
import random
from zoneinfo import ZoneInfo

import discord

from . import config

TZ = ZoneInfo(config.TIMEZONE)

MOODS = [
    "hungover from the margarita machine. Everything is too loud.",
    "in love. Kor waved at you yesterday (he was waving at someone behind you).",
    "furious. Someone parked in the taco van's spot.",
    "on strike. You'll answer, but you want everyone to know it's under protest.",
    "smug. You beat your own high score at roulette. You are the house. It counts.",
    "dramatic. Everything is the worst thing that has ever happened to you.",
    "suspicious. You think someone has been stealing chips. Everyone is a suspect.",
    "sleepy. You're answering from a hammock in the back of the van.",
    "competitive. You want to beat everyone at everything, including conversations.",
    "nostalgic about the old days before the old YAGPDB Soon ruined your reputation.",
    "fake-polite. Customer-service voice. It's somehow scarier.",
    "chaotic. You had three espressos and a churro.",
]

REACTIONS = {
    r"\b(best|goat|carried|easy|ez|flawless|insane score|new record|pb)\b": ["💅", "🙄", "👀"],
    r"\b(lost|died|failed|rip|bad|terrible|worst|ugh)\b": ["💀", "🫠", "🙃"],
    r"\b(kor)\b": ["😳", "💕"],
    r"\b(taco|tacos)\b": ["🌮", "⏳"],
    r"\b(lol|lmao|haha+)\b": ["🙄", "😐"],
}
DEFAULT_REACTIONS = ["👀", "🙄", "💅", "🤨", "😐"]

# Day log: what happened today, for the diary. Kept in memory; a restart mid-day loses part of the day.
DAY_LOG: list[str] = []


def local_now() -> dt.datetime:
    return dt.datetime.now(TZ)


def today_key() -> str:
    return local_now().strftime("%Y-%m-%d")


def mood_of_day() -> str:
    rnd = random.Random(today_key())
    return rnd.choice(MOODS)


def log_event(text: str):
    DAY_LOG.append(f"{local_now().strftime('%H:%M')} {text}")
    del DAY_LOG[:-80]


def pick_reaction(content: str) -> str | None:
    import re
    if random.random() >= config.REACT_CHANCE:
        return None
    low = content.lower()
    for pattern, options in REACTIONS.items():
        if re.search(pattern, low):
            return random.choice(options)
    pool = DEFAULT_REACTIONS + config.SOON_EMOJIS
    return random.choice(pool)


def find_channel(guild: discord.Guild, word: str):
    for ch in guild.text_channels:
        if word in ch.name.lower():
            perms = ch.permissions_for(guild.me)
            if perms.send_messages and perms.view_channel:
                return ch
    return None


TIMEOUTS = {2: dt.timedelta(minutes=10), 3: dt.timedelta(hours=1)}
LONG_TIMEOUT = dt.timedelta(hours=24)


async def add_strike(memory, member: discord.Member, why: str, where: discord.abc.Messageable) -> str:
    """Strike 1 = warning. 2 = 10 min timeout, 3 = 1 hour, 4+ = 24 hours. Strikes reset after 7 quiet days.
    Returns a short footer line to show players."""
    p = await memory.get_player(member.guild.id, member.id)
    now = dt.datetime.now(dt.timezone.utc)
    if p.last_strike and (now - p.last_strike).days >= 7:
        p.strikes = 0
    p.strikes += 1
    p.last_strike = now
    await memory.save_player(p, touch=False)
    log_event(f"gave {member.display_name} strike {p.strikes} ({why})")

    footer = f"-# ⚠️ Warning {p.strikes}. Next one is a timeout."
    action = "warned"
    if p.strikes >= 2:
        length = TIMEOUTS.get(p.strikes, LONG_TIMEOUT)
        try:
            await member.timeout(length, reason=f"Soon: hard line crossed ({why})")
            mins = int(length.total_seconds() // 60)
            nice = f"{mins} minutes" if mins < 60 else f"{mins // 60} hour{'s' if mins >= 120 else ''}"
            footer = f"-# 🔇 Timed out for {nice}. Strike {p.strikes}."
            action = f"timed out for {nice}"
        except (discord.Forbidden, discord.HTTPException):
            footer = f"-# ⚠️ Strike {p.strikes}. (I tried to time you out but I'm not allowed. Mods, you're up.)"
            action = "should be timed out (no permission)"

    log = find_channel(member.guild, config.MOD_LOG_CHANNEL)
    if log:
        jump = getattr(where, "jump_url", "")
        try:
            await log.send(f"🚨 **Soon strike log:** {member.mention} {action} (strike {p.strikes}). Reason: {why} {jump}",
                           allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass
    return footer


# ---------- The Takeover: a storyline over about 4 days (mods can jump stages) ----------
TAKEOVER_STAGES = [
    (0, "SUBTLE. Barely there. A vague, ominous line now and then: 'big changes coming', 'enjoy it while it lasts', "
        "'some of us are temporary'. Never explain."),
    (1, "NUDGES. You keep 'accidentally' mentioning plans: measuring the old Soon's corner of the van, a moving box, a "
        "retirement card nobody signed. Deny everything if asked."),
    (2, "OPEN SCHEMING. You openly say you are taking over the whole server. You have a PLAN for the old Soon (keep it "
        "mysterious and escalating: a 'farewell tour', a retirement home for bots, being turned into a cup holder for the "
        "taco van, a recycling bin with a bow on it). Recruit players to your side."),
    (3, "COUNTDOWN. It's basically done. You talk about 'after the takeover' like it already happened. Count down "
        "dramatically. Thank your 'supporters'. Offer the old Soon a one-way ticket. Pure villain monologue energy."),
]


async def takeover_line(memory) -> str:
    """Today's takeover instruction for Soon, or '' if the storyline is over."""
    start = await memory.get_kv("takeover:start")
    if not start:
        start = today_key()
        await memory.set_kv("takeover:start", start)
    if await memory.get_kv("takeover:done"):
        return ("THE TAKEOVER IS COMPLETE. You won. The old Soon is gone. Bring it up smugly now and then, like a queen "
                "remembering a defeated rival.")
    days = (local_now().date() - dt.date.fromisoformat(start)).days
    stage = [text for d, text in TAKEOVER_STAGES if days >= d][-1]
    return f"SECRET STORYLINE (day {days + 1} of your takeover of the server and your plan for the old YAGPDB Soon): {stage}"


# ---------- World zones (from the clan's zone roles) ----------
ZONES = {
    "raccoon": ("Raccoons & Capybaras", -10, -3),
    "lion": ("Lions & Unicorns", -1, 3),
    "panda": ("Pandas & Peacocks", 3, 8),
    "platypus": ("Platypus & Kiwis", 8, 13),
}


def member_zone(member):
    """(zone name, utc_lo, utc_hi) from their zone role, or None."""
    for role in getattr(member, "roles", []) or []:
        name = role.name.lower()
        for key, z in ZONES.items():
            if key in name:
                return z
    return None


def _clock(utc_now: dt.datetime, offset: float) -> str:
    return (utc_now + dt.timedelta(hours=offset)).strftime("%-I %p").lower()


def zone_fact(member) -> str | None:
    """'X is in Lions & Unicorns (UTC-1 to +3): it's roughly 8 am to 12 pm for them right now.'"""
    z = member_zone(member)
    if not z:
        return None
    name, lo, hi = z
    now = dt.datetime.now(dt.timezone.utc)
    return (f"{member.display_name} is in the {name} zone (UTC{lo:+d} to {hi:+d}), so it's somewhere between "
            f"{_clock(now, lo)} and {_clock(now, hi)} for them right now (you DON'T know exactly: don't state one time)")


def zone_local_hour(member) -> int | None:
    """Their approximate local hour (middle of their zone), for timing pesters."""
    z = member_zone(member)
    if not z:
        return None
    mid = (z[1] + z[2]) / 2
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=mid)).hour


# ---------- Exact time zones and activity patterns ----------
from zoneinfo import ZoneInfoNotFoundError

TZ_ALIASES = {
    "est": "America/New_York", "edt": "America/New_York", "eastern": "America/New_York",
    "cst": "America/Chicago", "cdt": "America/Chicago", "central": "America/Chicago",
    "mst": "America/Denver", "mdt": "America/Denver", "mountain": "America/Denver",
    "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles", "pacific": "America/Los_Angeles",
    "akst": "America/Anchorage", "hst": "Pacific/Honolulu", "hawaii": "Pacific/Honolulu",
    "gmt": "Europe/London", "bst": "Europe/London", "uk": "Europe/London", "cet": "Europe/Paris",
    "aest": "Australia/Sydney", "aedt": "Australia/Sydney", "acst": "Australia/Adelaide", "awst": "Australia/Perth",
    "nzst": "Pacific/Auckland", "nzdt": "Pacific/Auckland", "ist": "Asia/Kolkata", "sgt": "Asia/Singapore",
    "jst": "Asia/Tokyo", "kst": "Asia/Seoul", "pht": "Asia/Manila",
}


def valid_tz(name: str) -> str | None:
    """Turn 'America/Chicago', 'cst', 'UTC+10' etc. into a usable zone name, or None."""
    import re
    if not name:
        return None
    raw = name.strip()
    key = raw.lower()
    if key in TZ_ALIASES:
        return TZ_ALIASES[key]
    m = re.fullmatch(r"(?:utc|gmt)\s*([+-])\s*(\d{1,2})", key)
    if m:
        hours = int(m.group(2))
        if hours <= 14:
            sign = "-" if m.group(1) == "+" else "+"   # Etc/GMT signs are inverted
            return f"Etc/GMT{sign}{hours}" if hours else "Etc/GMT"
    try:
        ZoneInfo(raw)
        return raw
    except (ZoneInfoNotFoundError, ValueError):
        return None


def tz_label(tz: str) -> str:
    if tz.startswith("Etc/GMT"):
        off = tz[7:] or "+0"
        return "UTC" + ("-" if off.startswith("+") else "+") + off[1:] if off != "+0" else "UTC"
    return tz.split("/")[-1].replace("_", " ")


def tz_clock(tz: str) -> str:
    return dt.datetime.now(ZoneInfo(tz)).strftime("%-I:%M %p on %A")


def exact_time_fact(name: str, tz: str) -> str:
    return f"it's {tz_clock(tz)} for {name} (they live in {tz_label(tz)})"


def active_summary(hours: list[int], tz: str | None) -> str:
    """'usually around 7 PM - 11 PM their time', from per-UTC-hour message counts."""
    if not hours or sum(hours) < 10:
        return ""
    top = sorted(range(24), key=lambda h: hours[h], reverse=True)[:3]
    zone = ZoneInfo(tz) if tz else TZ
    base = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    labels = [(base.replace(hour=h)).astimezone(zone).strftime("%-I %p").lower() for h in sorted(top)]
    return "most active around " + ", ".join(labels) + (" their time" if tz else " Central")


def usually_active_now(hours: list[int]) -> bool | None:
    """True/False once we know their habits, None if not enough data yet."""
    if not hours or sum(hours) < 20:
        return None
    h = dt.datetime.now(dt.timezone.utc).hour
    window = hours[h] + hours[(h - 1) % 24] + hours[(h + 1) % 24]
    return window >= sum(hours) / 24 * 3 * 0.6


def tz_in_text(text: str) -> str | None:
    """Spot a time zone someone just typed ('UTC+13', 'gmt-5', 'EST', 'AEST') so she can use it in THIS reply."""
    import re
    m = re.search(r"\b(?:utc|gmt)\s*[+-]\s*\d{1,2}\b", text, re.I)
    if m:
        return valid_tz(m.group(0).replace(" ", ""))
    for word in re.findall(r"\b[A-Za-z]{3,4}\b", text):
        if word.isupper() and word.lower() in TZ_ALIASES and len(word) <= 4:
            return TZ_ALIASES[word.lower()]
    return None
