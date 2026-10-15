"""New-member welcome, moved over from Soon Classic (#06 Soon Helper). Fires on Discord's own "X joined the server"
message (so it lands when they actually open the server), only for people with a role whose name contains
"recruit" or "clan member": the abduction GIF + tour of the van in #new-members (WELCOME_CHANNEL), and the
"welcome them with your best taco GIF" call + "Find a taco GIF" button in #get-in-the-van (HELLO_CHANNEL).
OFF until cutover (Classic still welcomes people): set WELCOME=1 in Railway on cutover night.
Mods can preview it any time with `soon welcome test` (no pings)."""
import discord

from . import alerts, config
from .casino import IMG

ROLE_WORDS = ("recruit", "clan member")
PINK = 0xFF45A3


def wants_welcome(member) -> bool:
    return any(any(w in r.name.lower() for w in ROLE_WORDS) for r in getattr(member, "roles", []))


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
    await info_ch.send(text(member_mention),
                       allowed_mentions=discord.AllowedMentions(users=ping, everyone=False, roles=False))
    await hi_ch.send(hello(member_mention, call) + "\n-# No taco GIF ready? Tap below, or type `/tenor taco` and hit send.",
                     view=gif_button(),
                     allowed_mentions=discord.AllowedMentions(users=ping, everyone=False, roles=[r] if r else False))


async def on_join_message(message) -> bool:
    """Call for every message. True if it was a join message Soon welcomed."""
    if message.type != discord.MessageType.new_member or not config.WELCOME:
        return False
    if not wants_welcome(message.author):
        return False
    await send(message.channel, message.author.mention)
    return True
