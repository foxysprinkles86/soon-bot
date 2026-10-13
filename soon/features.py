"""Panda fact archive, roasts on demand, race/event reminders, and the Hall of Shame."""
import datetime as dt
import json
import re

from . import extras

# ---------- Panda Fact Archive ----------

async def panda_facts(memory, gid: int) -> list[str]:
    raw = await memory.get_kv(f"pandafacts:{gid}")
    return json.loads(raw) if raw else []


async def add_panda_fact(memory, gid: int, fact: str) -> bool:
    fact = fact.strip().rstrip(".")
    if not fact:
        return False
    facts = await panda_facts(memory, gid)
    words = set(re.findall(r"[a-z0-9']+", fact.lower()))
    for old in facts:
        ow = set(re.findall(r"[a-z0-9']+", old.lower()))
        if words and ow and len(words & ow) / len(words) >= 0.6:
            return False
    facts.append(fact)
    await memory.set_kv(f"pandafacts:{gid}", json.dumps(facts[-150:]))
    return True


def panda_canon_text(facts: list[str], limit: int = 12) -> str:
    if not facts:
        return ""
    return ("ESTABLISHED PANDA FACTS (canon: you said these before, they are TRUE, never contradict them): "
            + "; ".join(facts[-limit:]) + ".")


def panda_facts_list(facts: list[str]) -> str:
    if not facts:
        return "🐼 **Verified Panda Facts**\nNone yet. Give him time. Give ME time."
    shown = facts[-15:]
    start = len(facts) - len(shown) + 1
    lines = [f"{i}. {f[0].upper() + f[1:]}." for i, f in enumerate(shown, start)]
    return ("🐼 **Verified Panda Facts™**\n" + "\n".join(lines) +
            "\n-# All facts independently verified by Soon. Disputes go in the complaints box. The complaints box is a taco shell.")


# ---------- Roast on demand ----------

async def roast_allowance(memory, gid: int, uid: int, per_day: int) -> bool:
    """True (and counts it) if this person still has roasts left today."""
    key = f"roasts:{gid}:{uid}"
    raw = await memory.get_kv(key) or ""
    day, _, n = raw.partition(",")
    used = int(n) if day == extras.today_key() and n.isdigit() else 0
    if used >= per_day:
        return False
    await memory.set_kv(key, f"{extras.today_key()},{used + 1}")
    return True


# ---------- Race / event reminders ----------

def _fmt(when: dt.datetime) -> str:
    return when.strftime("%a %b %-d, %-I:%M %p").replace(":00 ", " ") + " Central"


async def get_events(memory, gid: int) -> list[dict]:
    raw = await memory.get_kv(f"events:{gid}")
    return json.loads(raw) if raw else []


async def save_events(memory, gid: int, events: list[dict]):
    await memory.set_kv(f"events:{gid}", json.dumps(events))


async def parse_event(brain, text: str) -> dict | None:
    """Turn 'Kraken starts Saturday 2pm, every week' into {"name","start","repeat"} (Central time)."""
    now = extras.local_now()
    out = await brain.write(
        "You are a date parser. Right now it is " + now.strftime("%A %Y-%m-%d %H:%M") + " US Central time. "
        "Turn this event description into JSON only, no other text: "
        '{"name": "<short event name>", "start": "YYYY-MM-DD HH:MM" (24h, US Central time, the NEXT time it starts), '
        '"repeat": "weekly" or "none"}. If the description gives another time zone, convert it to Central. '
        'If there is no usable day/time, reply {"name": "", "start": "", "repeat": "none"}.\nDescription: ' + text,
        max_tokens=80)
    m = re.search(r"\{.*\}", out or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        start = dt.datetime.strptime(str(data.get("start", "")).strip(), "%Y-%m-%d %H:%M").replace(tzinfo=extras.TZ)
    except (ValueError, json.JSONDecodeError):
        return None
    name = str(data.get("name") or "").strip()[:60]
    if not name:
        return None
    repeat = "weekly" if str(data.get("repeat", "")).lower() == "weekly" else "none"
    return {"name": name, "start": start.isoformat(), "repeat": repeat, "warned": False}


def discord_events(guild) -> list[dict]:
    """Upcoming events from the server's own Discord Events tab (recurring ones show their next date)."""
    out = []
    for e in getattr(guild, "scheduled_events", []) or []:
        status = str(getattr(e, "status", "")).lower()
        if "scheduled" not in status or not e.start_time:
            continue
        out.append({"name": e.name[:60], "start": e.start_time.astimezone(extras.TZ).isoformat(),
                    "repeat": "discord", "id": e.id, "about": (e.description or "")[:200]})
    return out


def events_list(events: list[dict]) -> str:
    if not events:
        return ("🏁 **Upcoming events**\nNothing scheduled. Mods: `soon event Kraken starts Saturday 2pm every week`.")
    rows = sorted(events, key=lambda e: e["start"])
    lines = [f"• **{e['name']}** · {_fmt(dt.datetime.fromisoformat(e['start']))}"
             + (" · weekly" if e.get("repeat") == "weekly" else "") for e in rows[:12]]
    return "🏁 **Upcoming events**\n" + "\n".join(lines) + "\n-# I'll yell about each one an hour before it starts."


def sleepy_zones(start: dt.datetime) -> list[str]:
    """Zones where it'll be the middle of the night (midnight to 7 am) when the event starts."""
    out = []
    utc = start.astimezone(dt.timezone.utc)
    for name, lo, hi in extras.ZONES.values():
        hour = (utc + dt.timedelta(hours=(lo + hi) / 2)).hour
        if hour < 7:
            out.append(name)
    return out


def due_events(events: list[dict], now: dt.datetime) -> tuple[list[dict], bool]:
    """Events that need their 1-hour warning now. Also rolls weekly events forward and drops old one-offs.
    Returns (due, changed)."""
    due, keep, changed = [], [], False
    for e in events:
        start = dt.datetime.fromisoformat(e["start"])
        if not e.get("warned") and start - dt.timedelta(hours=1) <= now < start:
            e["warned"] = True
            due.append(e)
            changed = True
        if now >= start + dt.timedelta(hours=1):
            changed = True
            if e.get("repeat") == "weekly":
                while start + dt.timedelta(hours=1) <= now:
                    start += dt.timedelta(days=7)
                e["start"], e["warned"] = start.isoformat(), False
            else:
                continue
        keep.append(e)
    events[:] = keep
    return due, changed


def event_task(e: dict) -> str:
    start = dt.datetime.fromisoformat(e["start"])
    sleepy = sleepy_zones(start)
    task = (f"Post a race reminder: **{e['name']}** starts in ONE HOUR ({_fmt(start)}). 1 to 3 short lines, hype + "
            "sarcasm, a bold headline with one emoji. Tell them to get ready.")
    if sleepy:
        task += (f" At start time it's the middle of the night for {', '.join(sleepy)}: roast that zone for "
                 "sleeping through it (one jab, not the whole post).")
    if e.get("about"):
        task += f" The event's own description, for context: {e['about']}"
    if "kraken" in e["name"].lower():
        task += (" Kraken tip to include: log in and COLLECT your Kraken tickets before the battle begins. They don't "
                 "vanish when missions refresh anymore, but uncollected ones don't help anybody.")
    return task + " No @ mentions."


# ---------- Hall of Shame (🤡 reactions) ----------

SHAME_EMOJI = "🤡"


async def shame_list(memory, gid: int) -> list[dict]:
    raw = await memory.get_kv(f"shame:{gid}")
    return json.loads(raw) if raw else []


async def add_shame(memory, gid: int, entry: dict) -> bool:
    items = await shame_list(memory, gid)
    if any(i.get("id") == entry["id"] for i in items):
        return False
    items.append(entry)
    await memory.set_kv(f"shame:{gid}", json.dumps(items[-200:]))
    return True


def shame_text(items: list[dict], who: str | None = None) -> str:
    if who:
        items = [i for i in items if i.get("uid") == who]
    if not items:
        return "🤡 **Hall of Shame**\nEmpty. React 🤡 to a message and I'll frame it forever."
    lines = [f"🤡 **{i['who']}**: \"{i['text'][:140]}\" · {i['date']}" for i in items[-10:]]
    return "🏛️ **The Hall of Shame**\n" + "\n".join(lines)
