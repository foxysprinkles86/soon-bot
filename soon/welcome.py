"""New-member welcome, moved over from Soon Classic (#06 Soon Helper). Fires on Discord's own "X joined the server"
message (so it lands when they actually open the server), only for people with a role whose name contains
"recruit" or "clan member": the abduction GIF + tour of the van in #new-members (WELCOME_CHANNEL), and the
"welcome them with your best taco GIF" call + "Find a taco GIF" button in #get-in-the-van (HELLO_CHANNEL).
OFF until cutover (Classic still welcomes people): set WELCOME=1 in Railway on cutover night.
Mods can preview it any time with `soon welcome test` (no pings)."""
import discord

from . import guide, alerts, config, recruits
from .casino import IMG

ROLE_WORDS = ("recruit", "clan member")
PINK = 0xFF45A3


FRIEND_WORDS = ("salsa",)     # the "Chips & Salsa" role: friends of the clan, not TnT members


def wants_welcome(member) -> str | None:
    """"member" (recruit / clan member), "friend" (Chips & Salsa) or None. Clan member wins if they have both."""
    names = [r.name.lower() for r in getattr(member, "roles", [])]
    if any(w in n for n in names for w in ROLE_WORDS):
        return "member"
    if any(w in n for n in names for w in FRIEND_WORDS):
        return "friend"
    return None


def friend_text(member_mention: str, call: str = "Everyone:") -> str:
    """Chips & Salsa: a friend of the clan, NOT a TnT member (Shannon's call). Short, public channels only."""
    return (f"🌶️ {member_mention} pulled up to the taco van for some **Chips & Salsa**!\n"
            "They're a **friend of the clan**, not a TnT member, so no recruiting them by force. Probably.\n\n"
            "**🗺️ While you're here:**\n"
            "📜 Terms of Abduction (still applies to guests): https://discord.com/channels/1400306445278253187/1534262128331194369/1535712424311922698\n"
            "💬 <#1534269691000918137> say hi • 🌶️ <#1558281375872716851> roast me, I roast back • "
            "🎰 <#1557531311260831764> free chips, bad decisions\n"
            "Tacos are coming soon. Even for guests. 🌮\n\n"
            f"{call} say hi to our newest guest! 🌮🎬")


def text(member_mention: str) -> str:
    """The info part, for the new member (in #new-members)."""
    return (f"🚐 {member_mention} just got abducted by the taco van!\nBefore you do anything else:\n"
            "📜 Read the Terms of Abduction: https://discord.com/channels/1400306445278253187/1534262128331194369/1535712424311922698\n"
            "📚 Check out the guides: <#1534310432607830077>\nTacos are coming soon. 🌮\n\n"
            "**🗺️ Quick tour of the van:**\n💬 <#1534269691000918137> random chaos\n"
            "🌶️ <#1558281375872716851> roast me. I roast back. Harder.\n"
            "🎮 <#1534274393562153000> gameplay chat • <#1541872673913835762> browse around\n"
            "🎰 <#1557531311260831764> free chips, bad decisions, and taco debt to yours truly\n\n"
            "-# Everyone's saying hi in the van chat. Go see. 🌮")


def hello(member_mention: str, call: str = "Everyone:") -> str:
    """The "say hi" part, for the current members (in #get-in-the-van)."""
    return (f"🚐 Fresh abductee! {member_mention} just got thrown in the taco van.\n"
            f"{call} welcome them with your best taco GIF! 🌮🎬")


def _find(guild, word: str, fallback):
    return next((c for c in getattr(guild, "text_channels", []) if word in c.name.lower()), None) or fallback


def gif_button() -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="Find a taco GIF", emoji="🌮", style=discord.ButtonStyle.link,
                                 url="https://tenor.com/search/taco-gifs"))
    return v


async def send(channel, member_mention: str, ping: bool = True):
    """Shannon's split (Oct 15): the info goes to #new-members for the newbie; the "welcome them with a GIF" call
    goes to #get-in-the-van for everyone else (pings the New Member Alerts role). ping=False = preview: both parts
    in this channel, no pings."""
    guild = channel.guild
    info_ch = _find(guild, config.WELCOME_CHANNEL, channel) if ping else channel
    hi_ch = _find(guild, config.HELLO_CHANNEL, channel) if ping else channel
    r = await alerts.role(guild, "newbie") if ping else None
    call = f"🔔 {r.mention}" if r else "Everyone:"
    await info_ch.send(embed=discord.Embed(color=PINK).set_image(url=IMG + "IMG_9246.gif"))
    await info_ch.send(text(member_mention) + "\n\n" + guide.WELCOME_STEPS, view=guide.welcome_view(),
                       allowed_mentions=discord.AllowedMentions(users=ping, everyone=False, roles=False))
    await hi_ch.send(hello(member_mention, call) + "\n-# No taco GIF ready? Tap below, or type `/tenor taco` and hit send.",
                     view=gif_button(),
                     allowed_mentions=discord.AllowedMentions(users=ping, everyone=False, roles=[r] if r else False))


async def on_join_message(message) -> bool:
    """Call for every message. True if it was a join message Soon welcomed."""
    if message.type != discord.MessageType.new_member or not config.WELCOME:
        return False
    kind = wants_welcome(message.author)
    if not kind:
        return False                     # no role yet (e.g. still in Discord onboarding): on_roles catches it later
    await welcome(message.author, kind, message.channel)
    return True


MEMORY = None   # bot.py sets this (kv store): remembers who was already welcomed, so nobody gets it twice


async def welcome(member, kind: str, channel=None):
    key = f"welcomed:{member.guild.id}:{member.id}"
    if MEMORY and await MEMORY.get_kv(key):
        return
    if MEMORY:
        await MEMORY.set_kv(key, "1")
    channel = channel or next((c for c in member.guild.text_channels if config.HELLO_CHANNEL in c.name.lower()), None)
    if channel is None:
        return
    if kind == "friend":
        await send_friend(channel, member.mention)
    else:
        await send(channel, member.mention)
        if any("recruit" in r.name.lower() for r in member.roles):
            await recruits.panel(member.guild, member)       # co-leaders' Tacos / Outlawz / Joined buttons


async def on_roles(before, after):
    """Roles given AFTER joining (Discord onboarding questions, or a mod adding them by hand): welcome them then.
    Only the Recruit and Chips & Salsa roles trigger it (getting Clan Member from the panel doesn't)."""
    if not config.WELCOME:
        return
    gained = [r.name.lower() for r in after.roles if r not in before.roles]
    if any(w in n for n in gained for w in FRIEND_WORDS) and wants_welcome(after) == "friend":
        await welcome(after, "friend")
    elif any("recruit" in n for n in gained):
        await welcome(after, "member")


async def send_friend(channel, member_mention: str, ping: bool = True):
    """Chips & Salsa welcome: one message in #get-in-the-van (public), pings the New Member Alerts role."""
    ch = _find(channel.guild, config.HELLO_CHANNEL, channel) if ping else channel
    r = await alerts.role(channel.guild, "newbie") if ping else None
    call = f"🔔 {r.mention}" if r else "Everyone:"
    await ch.send(friend_text(member_mention, call), view=gif_button(),
                  allowed_mentions=discord.AllowedMentions(users=ping, everyone=False, roles=[r] if r else False))
