"""Alert roles (Shannon's call): one opt-in role per kind of alert, and Soon @mentions the ROLE instead of listing names.
🎰 Casino Alerts (heists, duels, Kor's honk) • 🏁 Race Alerts (race reminders + race betting) • 🦑 Kraken Alerts
(Kraken schedule + ATTACK) • 👋 New Member Alerts (welcome a new recruit) • 📅 Event Alerts (event reminders).
`alerts` = menu with a button per role (a tap flips it for whoever taps) • `race alerts on/off`, `alerts kraken off`...
Old `heist alerts on` / `duel alerts on` = Casino Alerts. Soon creates a missing role herself (mentionable; needs Manage
Roles, her role above them). Race + Kraken roles start out given to everyone with the clan role (CLAN_ROLE_ID), so
nobody misses what Classic used to ping the whole clan for; they can turn it off. No roles possible = @name list
(kv `alertlist:<cat>`; long lists go out as their own messages, buttons.alert_pings)."""
import asyncio
import re
import time

import discord

from . import buttons, config

CATS = {  # key: (role name, emoji, what it pings for, words people type)
    "casino": ("Casino Alerts", "🎰", "heists and duels starting", r"casino|heists?|duels?|games?"),
    "race": ("Race Alerts", "🏁", "race reminders and race betting", r"races?|racing"),
    "kraken": ("Kraken Alerts", "🦑", "Kraken missions, last calls and ATTACK", r"kraken"),
    "newbie": ("New Member Alerts", "👋", "new clan members to welcome", r"new\s*members?|newbies?|welcomes?|recruits?"),
    "events": ("Event Alerts", "📅", "event reminders, 1 hour before", r"events?"),
}
SEED = {"race", "kraken"}
MENTIONS = discord.AllowedMentions(everyone=False, users=True, roles=True)
_W = "|".join(f"(?:{c[3]})" for c in CATS.values())
ALERT_RE = re.compile(rf"(?i)^\s*(?:soon\s+)?(?:my\s+)?(?:({_W})\s+)?(?:alerts?|notifications?)(?:\s+({_W}))?"
                      r"(?:\s+(on|off|toggle|start|stop|yes|no|sub\w*|unsub\w*))?\s*[.!?]*$")
_failed: dict[tuple, float] = {}        # (guild, cat) -> when creating the role last failed (retry after 10 min)


def btn(cat: str) -> tuple:
    name, emoji, _, _ = CATS[cat]
    return (f"{cat} alerts toggle", f"{name} on/off", "🔔")


def cat_of(word: str) -> str | None:
    return next((k for k, c in CATS.items() if re.fullmatch(rf"(?i){c[3]}", word or "")), None)


async def role(guild, cat: str, create: bool = True):
    if guild is None:
        return None
    name = CATS[cat][0]
    r = next((x for x in getattr(guild, "roles", []) if x.name.lower() == name.lower()), None)
    if r or not create or time.time() - _failed.get((guild.id, cat), 0) < 600:
        return r
    try:
        r = await guild.create_role(name=name, mentionable=True, reason=f"Soon: players who want {name.lower()}")
    except (discord.HTTPException, AttributeError):
        _failed[(guild.id, cat)] = time.time()
        return None
    if cat in SEED and config.CLAN_ROLE_ID:        # opt-out for clan reminders: the whole clan starts with it
        asyncio.create_task(_seed(guild, r))
    return r


async def _seed(guild, r):
    clan = guild.get_role(config.CLAN_ROLE_ID)
    for m in list(getattr(clan, "members", [])):
        if not m.bot and r not in m.roles:
            try:
                await m.add_roles(r, reason="clan reminders (turn off with the alerts menu)")
            except discord.HTTPException:
                return
            await asyncio.sleep(1)


async def _list(bank, gid: int, cat: str) -> list[str]:
    raw = await bank.get_house(gid, f"alertlist:{cat}")
    if raw is None and cat == "casino":           # the old heist + duel lists
        raw = sorted(set(await bank.get_house(gid, "heistsubs", []) or []) | set(await bank.get_house(gid, "duelsubs", []) or []))
    return list(raw or [])


async def is_on(member, bank, cat: str) -> bool:
    r = await role(member.guild, cat, create=False)
    if r:
        return r in member.roles
    return str(member.id) in await _list(bank, member.guild.id, cat)


async def set_on(member, bank, cat: str, on: bool) -> bool:
    """Flip someone's alert. True = done with the role, False = only the name list (no role possible)."""
    gid, me = member.guild.id, str(member.id)
    lst = [s for s in await _list(bank, gid, cat) if s != me] + ([me] if on else [])
    await bank.set_house(gid, f"alertlist:{cat}", lst)
    r = await role(member.guild, cat)
    if not r or not hasattr(member, "add_roles"):
        return False
    try:
        if on and r not in member.roles:
            await member.add_roles(r, reason=f"{CATS[cat][0]} on")
        elif not on and r in member.roles:
            await member.remove_roles(r, reason=f"{CATS[cat][0]} off")
        return True
    except discord.HTTPException:
        return False


async def prefix(channel, cat: str, bank=None) -> str:
    """The ping line on top of an alert: the role, or (no role possible) the @names."""
    guild = getattr(channel, "guild", None)
    r = await role(guild, cat)
    if r:
        return f"🔔 {r.mention}\n"
    if bank is None or guild is None:
        return ""
    subs = " ".join(f"<@{s}>" for s in await _list(bank, guild.id, cat))
    return await buttons.alert_pings(channel, subs, btn(cat))


async def menu(message, bank):
    lines = ["## 🔔 Soon's alerts\nPick what I should ping you for. **Anyone** can tap these: a tap turns that alert on or off for YOU."]
    for cat, (name, emoji, what, _) in CATS.items():
        on = await is_on(message.author, bank, cat)
        lines.append(f"{emoji} **{name}**: {what} • you: **{'ON' if on else 'off'}**")
    lines.append("-# Or type it: `race alerts on`, `casino alerts off`, `kraken alerts off`...")
    await message.channel.send("\n".join(lines), allowed_mentions=discord.AllowedMentions.none(),
                               view=buttons.view(*[(f"{c} alerts toggle", CATS[c][0], CATS[c][1]) for c in CATS]))


async def handle(message, bank, mod: bool) -> bool:
    m = ALERT_RE.match(message.content or "")
    if not m:
        return False
    cat = cat_of(m.group(1)) or cat_of(m.group(2))
    if not cat:
        await menu(message, bank)
        return True
    word = (m.group(3) or "on").lower()
    name, emoji, what, _ = CATS[cat]
    on = (not await is_on(message.author, bank, cat)) if word == "toggle" else not re.match(r"off|stop|no|unsub", word)
    by_role = await set_on(message.author, bank, cat, on)
    press = getattr(message, "interaction", None)          # a button tap: answer just the tapper, privately
    u = "" if press else message.author.mention + " "
    if on:
        how = f"You've got the **{name}** role: I ping it for {what}." if by_role else f"I'll tag you for {what}."
        text = f"{emoji} {u}{name} **on**. {how}\n-# `alerts` shows all your alerts."
    else:
        text = f"{emoji} {u}{name} **off**. Enjoy the silence. You'll miss everything.\n-# `alerts` shows all your alerts."
    if press:
        await press.followup.send(text, ephemeral=True)
    else:
        await message.channel.send(text)
    return True


async def sync(guild, bank):
    """At startup: everyone on an old name list gets the matching role (slowly, so Discord doesn't rate-limit her)."""
    for cat in CATS:
        subs = await _list(bank, guild.id, cat)
        r = await role(guild, cat, create=bool(subs))
        if not r:
            continue
        for s in subs:
            m = guild.get_member(int(s))
            if m and r not in m.roles:
                try:
                    await m.add_roles(r, reason="alerts on (moved to the alert role)")
                except discord.HTTPException:
                    return
                await asyncio.sleep(1)
