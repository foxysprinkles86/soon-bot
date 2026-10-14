"""New-member welcome, moved over from Soon Classic (#06 Soon Helper). Fires on Discord's own "X joined the server"
message (so it lands when they actually open the server), only for people with a role whose name contains
"recruit" or "clan member": the abduction GIF, the tour of the van, and a "Find a taco GIF" button.
OFF until cutover (Classic still welcomes people): set WELCOME=1 in Railway on cutover night.
Mods can preview it any time with `soon welcome test` (no pings)."""
import discord

from . import config
from .casino import IMG

ROLE_WORDS = ("recruit", "clan member")
PINK = 0xFF45A3


def wants_welcome(member) -> bool:
    return any(any(w in r.name.lower() for w in ROLE_WORDS) for r in getattr(member, "roles", []))


def text(member_mention: str) -> str:
    return (f"🚐 {member_mention} just got abducted by the taco van!\nBefore you do anything else:\n"
            "📜 Read the Terms of Abduction: https://discord.com/channels/1400306445278253187/1534262128331194369/1535712424311922698\n"
            "📚 Check out the guides: <#1534310432607830077>\nTacos are coming soon. 🌮\n\n"
            "**🗺️ Quick tour of the van:**\n💬 <#1534269691000918137> random chaos\n"
            "🌶️ <#1558281375872716851> roast me. I roast back. Harder.\n"
            "🎮 <#1534274393562153000> gameplay chat • <#1541872673913835762> browse around\n"
            "🎰 <#1557531311260831764> free chips, bad decisions, and taco debt to yours truly\n\n"
            "Everyone: welcome our newest abductee with your best taco GIF! 🌮🎬")


def gif_button() -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="Find a taco GIF", emoji="🌮", style=discord.ButtonStyle.link,
                                 url="https://tenor.com/search/taco-gifs"))
    return v


async def send(channel, member_mention: str, ping: bool = True):
    await channel.send(embed=discord.Embed(color=PINK).set_image(url=IMG + "IMG_9246.gif"))
    await channel.send(text(member_mention), allowed_mentions=discord.AllowedMentions(users=ping, everyone=False, roles=False))
    await channel.send("🌮 No taco GIF ready? Tap below, or type `/tenor taco` and hit send.", view=gif_button())


async def on_join_message(message) -> bool:
    """Call for every message. True if it was a join message Soon welcomed."""
    if message.type != discord.MessageType.new_member or not config.WELCOME:
        return False
    if not wants_welcome(message.author):
        return False
    await send(message.channel, message.author.mention)
    return True
