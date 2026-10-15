"""World zones, moved over from Soon Classic (#38 World Zone, #39 Zone Nudge).
`zone` = menu • `zone raccoon` / `zone uk` / `my zone australia`... = pick or switch your zone role.
Roles are found by name (a role just has to CONTAIN Raccoon / Lion / Panda / Platypus). Soon needs Manage Roles and
her role above those four. Nudge: ~1 in 25 messages from someone with no zone role, max once per 3 days each.
Same channels as the taco van (TACO_CHANNELS) until cutover, so Classic and Soon don't both answer."""
import random
import re

import discord

from . import buttons
from .economy import Bank
from .extras import ZONES
from .tacovan import taco_channel

ZONE_RE = re.compile(r"(?i)^\s*(?:my\s+)?(?:zone|region)\b(.*)$")
KEYS = {"raccoon": r"raccoon|capybara|america|usa|us\b|canada|mexico|brazil",
        "lion": r"lion|unicorn|europe|africa|uk\b|england|britain",
        "panda": r"panda|peacock|asia|india|middle east|philippines|singapore",
        "platypus": r"platypus|dingo|kangaroo|roo|kiwi|australia|aussie|new zealand|nz\b|japan|korea"}
EMOJI = {"raccoon": "🦝", "lion": "🦁", "panda": "🐼", "platypus": "🦆"}
MENU = ("## 🌍 Which worldly zone are you hiding in?\n"
        "🦝 `zone raccoon`: **Raccoons & Capybaras** • the Americas (UTC−10 to −3)\n"
        "🦁 `zone lion`: **Lions & Unicorns** • UK, Europe & Africa (UTC−1 to +3)\n"
        "🐼 `zone panda`: **Pandas & Peacocks** • Middle East, India & Southeast Asia (UTC+3 to +8)\n"
        "🦆 `zone platypus`: **Platypus & Kiwis** • Australia, New Zealand & East Asia (UTC+8 to +13)\n"
        "-# Typing your country works too: `zone australia`, `zone uk`, `zone usa`. Switch any time.")
LINES = {"raccoon": ["A Raccoon. Of course. Explains the trash-tier Piggy scores.",
                     "Welcome to the Americas, where the tacos are real and still not coming.",
                     "Capybara energy. Calm. Unbothered. Losing."],
         "lion": ["A Lion. Bold claim for someone with your race stats.",
                  "Europe! You'll be asleep for every race. Convenient excuse.",
                  "Unicorn spotted. Rare. Mythical. Like your x2 windows."],
         "panda": ["A Panda. Mostly eats and sleeps. Relatable.", "Peacock vibes. All feathers, no finish line.",
                   "Asia! You're always ahead of us. Except on the leaderboard."],
         "platypus": ["A Platypus. A duck built by a committee that lays eggs and is venomous for no reason. Welcome home.",
                      "Platypus & Kiwis. We had kangaroos. Then Pooty complained. Now we have this. Blame him.",
                      "Kiwi spotted. Small. Fuzzy. Can't fly. Still racing, somehow.",
                      "Down under! Your races start while the rest of us sleep. Suspicious."]}
NUDGES = ["Quick question. Where in the world are you? You don't have a zone yet and it's bothering me.",
          "I've been meaning to ask: are you a Raccoon, Lion, Panda or Platypus? I need to know who to blame.",
          "You're zoneless. Homeless, but for time zones. Let's fix that.",
          "Every zone is accounted for except yours. I'm not mad. I'm just counting."]


def zone_buttons():
    """One tap = typing `zone raccoon` etc. for whoever taps (it changes THEIR zone)."""
    return buttons.view(("zone raccoon", "Raccoons", "🦝"), ("zone lion", "Lions", "🦁"),
                        ("zone panda", "Pandas", "🐼"), ("zone platypus", "Platypus", "🦆"))


def _role(guild, key: str):
    return next((r for r in guild.roles if key in r.name.lower()), None)


async def set_zone(member, pick: str) -> str:
    """Guide button: switch someone's zone role. Returns the line to show them."""
    new = _role(member.guild, pick)
    if not new:
        return "I can't find that zone's role. Tell Master Foxy to create it."
    if new in member.roles:
        return f"{EMOJI[pick]} You're already in **{new.name}**. Nothing changed."
    old = [r for r in member.roles if any(k in r.name.lower() for k in KEYS if k != pick)]
    try:
        if old:
            await member.remove_roles(*old, reason="zone switch")
        await member.add_roles(new, reason="zone pick")
    except discord.HTTPException:
        return "Discord won't let me touch roles. Master Foxy needs to give me **Manage Roles**."
    return f"{EMOJI[pick]} You're now a **{new.name}**! " + random.choice(LINES[pick])


async def handle(message, bank: Bank, mod: bool) -> bool:
    if not taco_channel(message.channel):
        return False
    m = ZONE_RE.match(message.content or "")
    if not m:
        return False
    rest = m.group(1).lower()
    pick = next((k for k, rx in KEYS.items() if re.search(rf"(?i)\b(?:{rx})", rest)), None)
    u = message.author.mention
    if not pick:
        await message.channel.send(MENU + "\n-# Or tap yours below.", view=zone_buttons())
        return True
    new = _role(message.guild, pick)
    if not new:
        await message.channel.send(f"🌍 {u} I can't find that zone's role. Someone tell Foxy to create it. "
                                   "I'd do it myself, but I don't have thumbs.")
        return True
    if new in message.author.roles:
        await message.channel.send(f"🌍 {u} You're already in **{new.name}**. Nothing changed. Like your Piggy score.")
        return True
    old = [r for r in message.author.roles if any(k in r.name.lower() for k in KEYS if k != pick)]
    try:
        if old:
            await message.author.remove_roles(*old, reason="zone switch")
        await message.author.add_roles(new, reason="zone pick")
    except discord.HTTPException:
        await message.channel.send(f"🌍 {u} I tried, but Discord won't let me touch roles. Foxy: give me **Manage Roles** "
                                   "and drag my role above the zone roles.")
        return True
    out = (f"🌍 {u} is now a **{new.name}**!" + (f" (Bye, {old[0].name}. Traitor.)" if old else "")
           + "\n" + random.choice(LINES[pick]))
    if re.search(r"(?i)dingo|kangaroo|\broo\b", rest):
        out += "\n-# Dingos and kangaroos have been deported. Take it up with Pooty, Lord of the Outback."
    await message.channel.send(out)
    return True


async def nudge(message, bank: Bank):
    """~1 in 25 messages: zoneless people get asked to pick one (max once per 3 days each)."""
    if random.randrange(25) or not taco_channel(message.channel) or getattr(message.author, "bot", False):
        return
    if any(any(k in r.name.lower() for k in ZONES) for r in getattr(message.author, "roles", [])):
        return
    gid, uid = message.guild.id, message.author.id
    if await bank.timer(gid, uid, "zonenag"):
        return
    await bank.set_timer(gid, uid, "zonenag", 3 * 86400)
    await message.channel.send(f"🌍 {message.author.mention} {random.choice(NUDGES)}\n"
                               "-# Type `zone` to pick yours: 🦝 Raccoons & Capybaras • 🦁 Lions & Unicorns • "
                               "🐼 Pandas & Peacocks • 🦆 Platypus & Kiwis", view=zone_buttons())
