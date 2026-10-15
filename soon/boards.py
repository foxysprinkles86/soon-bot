"""Leader boards, moved over from Soon Classic (#02 Leader Boards): `taco board`, `bar board`, `egg board`.
Top 8 by taco requests / margaritas / eggs found, each with their taco balance. The egg board also shows the
asker's own basket. Same channels as the taco van (TACO_CHANNELS) until cutover. Buttons switch between boards."""
import re

import discord

from . import buttons
from .economy import Bank
from .tacovan import taco_channel

BOARD_RE = re.compile(r"(?i)\b(taco|bar|egg) ?board\b|\begg ?(basket)\b|^\s*(?:my\s+)?(basket)\b")
TOTAL_EGGS = 24                  # Classic's 23 + Soon 2.0's "Epic meltdown" (egg m)
EGG_NAMES = {"1": "When are the tacos coming?", "2": "Who ate them?", "3": "Burrito", "4": "Hungry", "5": "Being nice",
             "6": "Being mean", "7": "Dips", "8": "Open the van", "9": "Taco Tuesday", "10": "The competition",
             "11": "Free tacos", "12": "Quitting", "13": "Beep boop", "14": "Is Soon real?", "15": "Are we there yet?",
             "16": "Hot sauce", "17": "Delivery apps", "18": "Pineapple", "19": "Nachos", "20": "Good morning/night",
             "21": "Taco emoji spam", "g": "The glitch", "b": "Bedtime", "m": "Epic meltdown"}
KEEP_EGGS = {"m"}               # Soon 2.0-only eggs: the cutover import keeps these (Classic never had them)
FOOTER = "-# Boards: taco board • bar board • egg board"


def _name(guild: discord.Guild, uid: int) -> str:
    m = guild.get_member(uid)
    return m.display_name if m else f"<@{uid}>"


def _view():
    return buttons.view(("taco board", "Taco board", "🌮"), ("bar board", "Bar board", "🍹"),
                        ("egg board", "Egg board", "🥚"))


async def basket(gid: int, who, bank: Bank) -> str:
    """Anyone's egg basket: `egg board @name` or `basket @name` (no @ = your own)."""
    mine = [EGG_NAMES[str(e)] for e in (await bank.get(gid, who.id)).eggs if str(e) in EGG_NAMES]
    return (f"### 🧺 {who.display_name}'s basket: {len(mine)}/{TOTAL_EGGS}\n"
            + (" • ".join(mine) if mine else "Empty. Not a single egg. Try `egg hint`.")
            + f"\n-# {TOTAL_EGGS - len(mine)} still hidden • `egg board @name` or `basket @name` to snoop on someone else")


async def handle(message, bank: Bank, mod: bool) -> bool:
    if not taco_channel(message.channel):
        return False
    m = BOARD_RE.search(message.content or "")
    if not m:
        return False
    kind = (m.group(1) or m.group(2) or m.group(3)).lower()
    g, gid = message.guild, message.guild.id
    me = getattr(getattr(g, "me", None), "id", None)
    who = next((x for x in getattr(message, "mentions", []) if x.id != me and not x.bot), message.author)
    if kind == "basket":                          # `basket` / `egg basket @name`: just someone's basket
        await message.channel.send(await basket(gid, who, bank), allowed_mentions=discord.AllowedMentions.none())
        return True
    if kind == "taco":
        top = [w for w in await bank.top(gid, "tacos", 8) if w.tacos > 0]
        out = "## 🌮 The Taco Waitlist 🌮\n" + ("" if top else "Nobody's in line yet. Say taco. Tacos coming soon! 🌮\n")
        out += "".join(f"{i}. **{_name(g, w.user_id)}** — {w.tacos} requests, {w.tacobal} tacos\n"
                       for i, w in enumerate(top, 1))
    elif kind == "bar":
        top = [w for w in await bank.top(gid, "margs", 8) if w.margs > 0]
        out = "## 🍹 Bar Tabs 🍹\n" + ("" if top else "Nobody's ordered yet. The bar is open. The kitchen is not.\n")
        out += "".join(f"{i}. **{_name(g, w.user_id)}** — {w.margs} margaritas, {w.tacobal} tacos\n"
                       for i, w in enumerate(top, 1))
    else:
        top = [w for w in await bank.top(gid, "eggcount", 8) if w.eggcount > 0]
        out = "## 🥚 Egg Hunters 🥚\n" + ("" if top else "No eggs found yet. They're out there...\n")
        out += "".join(f"{i}. **{_name(g, w.user_id)}** — {w.eggcount}/{TOTAL_EGGS} found, {w.tacobal} tacos\n"
                       for i, w in enumerate(top, 1))
        out += "\n" + await basket(gid, who, bank) + "\n"
    msg = await message.channel.send(out + FOOTER, view=_view(), allowed_mentions=discord.AllowedMentions.none())
    await buttons.replace(f"boards:{message.channel.id}", msg)      # only the newest board keeps its buttons
    return True
