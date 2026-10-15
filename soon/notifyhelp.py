"""Notification help (Shannon's add): in ANY channel Soon can see, when someone complains about notifications
("too many pings", "my phone keeps buzzing", "how do I mute this"), she answers with short how-to steps.
Canned lines (no AI), max once a day per person and once per 10 min per channel."""
import random
import re
import time

import discord

_N = r"(?:notifications?|notifs?|pings?|pinged|alerts?|buzz\w*|dings?)"
COMPLAINT_RE = re.compile(
    rf"(?i)\b(?:too many|so many|stop(?:\s+the)?|turn(?:ing)? off|mute|silence|disable|hate|sick of|tired of|"
    rf"spam\w*|nonstop|non-stop|constant|all these|endless)\s+(?:\w+\s+){{0,2}}{_N}"
    rf"|\b{_N}\s+(?:\w+\s+){{0,3}}(?:too much|annoying|driving me|crazy|nonstop|non-stop|blowing up|out of control|"
    rf"won'?t stop|keep(?:s)? (?:going|coming))"
    rf"|\bhow (?:do|can|would) (?:i|you|we) (?:\w+\s+){{0,2}}(?:turn off|stop|mute|change|disable|silence)\s+(?:\w+\s+){{0,3}}"
    rf"(?:{_N}|this channel|the server|discord)"
    rf"|\b(?:phone|discord)\s+(?:keeps|won'?t stop|is|has been)\s+(?:\w+\s+){{0,2}}(?:buzzing|blowing up|going off|dinging)"
    rf"|\bstop (?:pinging|tagging|@'?ing) (?:me|us|everyone)\b")
OPENERS = ["Sorry, I can't change that for you. I'm powerful, not THAT powerful. But here's how:",
           "I can't touch your settings (believe me, I've tried). Here's how you do it:",
           "Can't do it for you, darling. Discord won't let me. Here's the trick:",
           "Not my buttons to press, sadly. Here's how:"]
HOW = ("• **Whole server quieter:** long-press the server icon (right-click on a computer) → **Notifications** → "
       "**Only @mentions**\n"
       "• **One noisy channel:** long-press the channel → **Mute** (or its notification settings)\n"
       "• **My pings:** in my channels, type `alerts` to pick which ones you get, or `soon no tags`")
_last_user: dict[tuple, float] = {}
_last_channel: dict[int, float] = {}


async def check(message) -> bool:
    """True if she answered a notification complaint."""
    text = message.content or ""
    if len(text) > 400 or not COMPLAINT_RE.search(text):
        return False
    now = time.time()
    ukey = (message.guild.id, message.author.id)
    if now - _last_user.get(ukey, 0) < 86400 or now - _last_channel.get(message.channel.id, 0) < 600:
        return False
    try:
        await message.reply(f"🔔 {random.choice(OPENERS)}\n{HOW}", mention_author=False,
                            allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        return False                         # can't post in this channel: say nothing
    _last_user[ukey] = _last_channel[message.channel.id] = now
    return True
