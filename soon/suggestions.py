"""Suggestion box (Shannon's add): ideas, complaints, changes, things to stop; Foxy/mods pull the list, and each new
one is copied to #soon-lab (SUGGEST_CHANNEL) so Master Foxy sees it right away.
Anyone: `soon suggest <idea>` (also `soon suggestion/idea/feedback/complaint/complain/request ...`), max 5 a day each.
`soon suggestion box` = how it works. Mods: `soon suggestions` (the open list, sent by DM), `soon suggestion done 3 5`
(takes those off the list). Saved in kv `suggestions:<gid>` (open ones) and `suggestid:<gid>` (the number counter)."""
import datetime as dt
import json
import random
import re

import discord

from . import config

ADD_RE = re.compile(r"(?is)^(?:suggest(?:ion)?|idea|feedback|complain(?:t)?|request)\s*[:\-]?\s+(.+)$")
LIST_RE = re.compile(r"(?i)^(?:suggestions|suggestion list|suggestions list|show suggestions|read suggestions)[.!?]*$")
BOX_RE = re.compile(r"(?i)^(?:suggestion box|suggest|suggestion|idea|feedback|complain|complaint|request|suggestions? help|"
                    r"how do i (?:suggest|complain)\b.*)[.!?]*$")
DONE_RE = re.compile(r"(?i)^suggestions?\s+(?:done|delete|remove|clear)\s+([\d ,#and]+)$")
PER_DAY, MAX_LEN = 5, 500
THANKS = ["Filed. In a drawer. A nice drawer. Master Foxy reads the drawer.",
          "Noted. I'll pretend I didn't read it until Master Foxy makes me.",
          "Into the box it goes. The box is judging you. Lovingly.",
          "Received. Your opinion has been laminated.",
          "Suggestion accepted. Feelings not included.",
          "Got it. If this was about me being nicer: no. If it wasn't: we'll see."]


async def handle(message, text: str, cmd: str, memory, mod: bool, guild=None) -> bool:
    """text = the command with its original capitals (after "soon"), cmd = lowercased. True if it was ours.
    guild = the server, for suggestions sent by DM (private: the copy goes to the mod log, not #soon-lab)."""
    guild = guild or message.guild
    gid, uid, private = guild.id, message.author.id, message.guild is None
    if BOX_RE.match(cmd) or (LIST_RE.match(cmd) and not mod):
        await message.reply("📮 **Soon's suggestion box.** Ideas, complaints, changes, things I should stop doing. Say it:\n"
                            "`soon suggest stop roasting my Piggy score` • `soon complaint the heist pings are too loud`\n"
                            "🔒 Want it private? DM me: `suggest <your idea>`. Only Master Foxy and the mods see those.\n"
                            "-# Master Foxy reads every one. I read them too. I just pretend not to.", mention_author=False)
        return True
    if LIST_RE.match(cmd):
        await send_list(message, memory, guild)
        return True
    m = DONE_RE.match(cmd)
    if m and mod:
        nums = {int(n) for n in re.findall(r"\d+", m.group(1))}
        items = json.loads(await memory.get_kv(f"suggestions:{gid}") or "[]")
        left = [s for s in items if s["n"] not in nums]
        await memory.set_kv(f"suggestions:{gid}", json.dumps(left))
        gone = len(items) - len(left)
        await message.reply(f"📮 Took {gone} suggestion{'s' if gone != 1 else ''} off the list. {len(left)} still open.",
                            mention_author=False)
        return True
    m = ADD_RE.match(text)
    if not m:
        return False
    idea = m.group(1).strip()
    if len(idea) < 4:
        await message.reply("📮 Suggest WHAT? `soon suggest <your idea>`. Use your words.", mention_author=False)
        return True
    n = await file(guild, message.author, idea, memory, mod, private, message.channel,
                   "" if private else getattr(message, "jump_url", ""))
    if n is None:
        await message.reply(f"📮 That's {PER_DAY} suggestions today. The box is full of you. Try again tomorrow.",
                            mention_author=False)
        return True
    try:
        await message.add_reaction("📮")
    except discord.HTTPException:
        pass
    await message.reply(f"📮 **Suggestion #{n} filed.**{' 🔒 Private: only Master Foxy and the mods see it.' if private else ''} "
                        f"{random.choice(THANKS)}"
                        + ("\n-# (I kept the first 500 characters. Brevity, darling.)" if len(idea) > MAX_LEN else ""),
                        mention_author=False)
    return True


async def file(guild, author, idea: str, memory, mod: bool = False, private: bool = True, channel=None,
               link: str = "") -> int | None:
    """Saves a suggestion and sends Master Foxy her copy. Returns its number, or None when they hit 5 today.
    Also used by the guide's 📮 form (always private)."""
    gid, uid = guild.id, author.id
    day = dt.date.today().isoformat()
    key = f"suggestday:{gid}:{uid}"
    used = json.loads(await memory.get_kv(key) or "{}")
    if used.get("d") == day and used.get("n", 0) >= PER_DAY and not mod:
        return None
    await memory.set_kv(key, json.dumps({"d": day, "n": (used.get("n", 0) if used.get("d") == day else 0) + 1}))
    n = int(await memory.get_kv(f"suggestid:{gid}") or 0) + 1
    await memory.set_kv(f"suggestid:{gid}", str(n))
    items = json.loads(await memory.get_kv(f"suggestions:{gid}") or "[]")
    items.append({"n": n, "uid": uid, "name": f"{author.display_name} (@{author.name})", "text": idea[:MAX_LEN],
                  "ts": int(dt.datetime.now(dt.timezone.utc).timestamp()), "ch": getattr(channel, "id", 0),
                  "link": link, "private": private})
    await memory.set_kv(f"suggestions:{gid}", json.dumps(items[-300:]))
    await forward(author, channel, guild, n, idea[:MAX_LEN], private, link)
    return n


async def forward(author, channel, guild, n: int, idea: str, private: bool = False, link: str = ""):
    """A copy for Master Foxy: #soon-lab (SUGGEST_CHANNEL) unless filed right there. Private (DM) ones go to the
    mod-only log instead (#soon-roast-mod, else #moderator-only), because testers can see #soon-lab."""
    want = [config.MOD_LOG_CHANNEL, "moderator"] if private else [config.SUGGEST_CHANNEL]
    ch = next((c for w in want for c in guild.text_channels if w in c.name.lower()), None)
    if not ch or ch.id == getattr(channel, "id", None):
        return
    where = "🔒 **privately**" if private else f"in {channel.mention}"
    link = f"[Jump to it]({link}) • " if link and not private else ""
    try:
        await ch.send(f"📮 **New suggestion #{n}** from **{author.display_name}** (<@{author.id}> · @{author.name}) {where}:\n"
                      f"> {idea.replace(chr(10), chr(10) + '> ')}\n"
                      f"-# {link}done with it? `soon suggestion done {n}`",
                      allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True)
    except discord.HTTPException:
        pass


async def send_list(message, memory, guild=None):
    """The open suggestions, oldest first, sent to the mod's DMs (never to a channel: some are private)."""
    gid = (guild or message.guild).id
    items = json.loads(await memory.get_kv(f"suggestions:{gid}") or "[]")
    if not items:
        await message.reply("📮 The suggestion box is empty. Either everyone loves me, or nobody can type.",
                            mention_author=False)
        return
    lines = [f"**#{s['n']}** {'🔒 ' if s.get('private') else ''}{s['name']} <@{s['uid']}> (<t:{s['ts']}:d>): {s['text']}" + (f" [→]({s['link']})" if s.get("link") else "")
             for s in items]
    pages, page = [], f"## 📮 Suggestion box: {len(items)} open\n"
    for line in lines:
        if len(page) + len(line) > 1900:
            pages.append(page)
            page = ""
        page += line + "\n"
    pages.append(page + "-# Done with some? `soon suggestion done 3 5` takes them off the list.")
    try:
        for p in pages:
            await message.author.send(p, allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True)
        if message.guild is not None:
            await message.reply(f"📮 Sent you the list in DMs ({len(items)} open).", mention_author=False)
    except discord.HTTPException:                       # some are private: never read them out in a channel
        await message.reply("📮 Your DMs are closed, and I don't read suggestions out loud (some are private). "
                            "Allow DMs from this server, then try again.", mention_author=False)
