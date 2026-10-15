"""Alert roles (Shannon's call): turning on heist/duel alerts gives the player a role ("Heist Alerts" / "Duel Alerts"),
and alerts @mention that ONE role instead of listing every name. Soon creates the role if it's missing (needs Manage
Roles; her role must sit above it). No role possible = the old list of @names (buttons.alert_pings)."""
import asyncio
import time

import discord

from . import buttons

ROLES = {"heistsubs": "Heist Alerts", "duelsubs": "Duel Alerts"}
MENTIONS = discord.AllowedMentions(everyone=False, users=True, roles=True)
_failed: dict[tuple, float] = {}        # (guild, key) -> when creating the role last failed (retry after 10 min)


async def role(guild, key: str, create: bool = True):
    name = ROLES[key]
    if guild is None:
        return None
    r = next((x for x in getattr(guild, "roles", []) if x.name.lower() == name.lower()), None)
    if r or not create or time.time() - _failed.get((guild.id, key), 0) < 600:
        return r
    try:
        return await guild.create_role(name=name, mentionable=True,
                                       reason=f"Soon: players who turned on {name.lower()}")
    except (discord.HTTPException, AttributeError):
        _failed[(guild.id, key)] = time.time()
        return None


async def set_member(member, key: str, on: bool) -> bool:
    """Give or take the alert role. True if it worked."""
    r = await role(getattr(member, "guild", None), key)
    if not r or not hasattr(member, "add_roles"):
        return False
    try:
        if on and r not in member.roles:
            await member.add_roles(r, reason="alerts on")
        elif not on and r in member.roles:
            await member.remove_roles(r, reason="alerts off")
        return True
    except discord.HTTPException:
        return False


async def prefix(channel, key: str, subs: str, btn: tuple) -> str:
    """The ping line for an alert: the role if it exists, otherwise the @names."""
    r = await role(getattr(channel, "guild", None), key)
    if r:
        return f"🔔 {r.mention}\n"
    return await buttons.alert_pings(channel, subs, btn)


async def sync(guild, bank):
    """At startup: everyone already on an alerts list gets the role (slowly, so Discord doesn't rate-limit her)."""
    for key in ROLES:
        subs = await bank.get_house(guild.id, key, []) or []
        r = await role(guild, key, create=bool(subs))
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
