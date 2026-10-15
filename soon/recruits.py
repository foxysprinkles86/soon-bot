"""Recruit panel (Shannon's design, Oct 15): when a new recruit arrives, Soon posts a panel in the staff channel
(RECRUIT_CHANNEL, default #glovebox-secrets, the co-leader chat) with buttons only a co-leader (Taco Wrangler role) or mod can press:
🌮 Tacos / 🤠 Outlawz → removes JUST the plain "Recruit" role (the other recruit roles say where they came from,
so they stay) and gives that clan's role • ✅ Joined in game → gives "Clan Member" (full member access) and the
panel is done • ❌ Not joining → closes the panel, roles untouched.
`soon recruit @name` (wranglers/mods) brings up a panel for anyone by hand.
`soon alumni @name`: they left the clan in game but stay in Discord → confirm button → every role Soon can touch is
removed and "Taco Alumni" is given (the confirmation lists what was removed, so it can be undone by hand)."""
import re

import discord

from . import config

MEMBER = None          # bot.py sets: is_mod(member) -> bool
CLANS = {"tacos": ("Tacos", "🌮"), "outlawz": ("Outlawz", "🤠")}
RECRUIT_RE = re.compile(r"(?i)^\s*soon\s+recruit\b")
ALUMNI_RE = re.compile(r"(?i)^\s*soon\s+(?:alumni|alum|left(?:\s+the)?\s+clan|retire)\b")


def _clean(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def role_named(guild, name: str):
    """Exact role name (emojis/punctuation ignored): "Recruit" never matches "Recruit - TikTok"."""
    return next((r for r in guild.roles if _clean(r.name) == _clean(name)), None)


def is_wrangler(member) -> bool:
    if MEMBER and MEMBER(member):
        return True
    return any("wrangler" in r.name.lower() for r in getattr(member, "roles", []))


def staff_channel(guild):
    return next((c for c in guild.text_channels if config.RECRUIT_CHANNEL in c.name.lower()), None)


def view(uid: int, done: bool = False) -> discord.ui.View | None:
    if done:
        return None
    v = discord.ui.View(timeout=None)
    for key in ("tacos", "outlawz", "joined", "no"):
        v.add_item(RecruitButton(uid, key))
    return v


def panel_text(member, status: list[str]) -> str:
    return (f"## 🧾 New recruit: {member.mention} ({member.display_name})\n"
            "1️⃣ Tap the clan they're joining: 🌮 **Tacos** or 🤠 **Outlawz** (swaps out the plain Recruit role)\n"
            "2️⃣ Once they've actually joined in game, tap ✅ **Joined in game** (gives Clan Member = full access)\n"
            + ("\n" + "\n".join(status) if status else "")
            + "\n-# Only Taco Wranglers and mods can press these.")


async def panel(guild, member, channel=None):
    ch = channel or staff_channel(guild)
    if ch:
        await ch.send(panel_text(member, []), view=view(member.id),
                      allowed_mentions=discord.AllowedMentions.none())


class RecruitButton(discord.ui.DynamicItem[discord.ui.Button],
                    template=r"soon:rc:(?P<u>\d+):(?P<a>tacos|outlawz|joined|no)"):
    LOOK = {"tacos": ("Tacos", "🌮", discord.ButtonStyle.primary), "outlawz": ("Outlawz", "🤠", discord.ButtonStyle.primary),
            "joined": ("Joined in game", "✅", discord.ButtonStyle.success), "no": ("Not joining", "❌", discord.ButtonStyle.secondary)}

    def __init__(self, uid: int, action: str):
        label, emoji, style = self.LOOK[action]
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=f"soon:rc:{uid}:{action}"))
        self.uid, self.action = uid, action

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(int(match["u"]), match["a"])

    async def callback(self, interaction: discord.Interaction):
        if not is_wrangler(interaction.user):
            await interaction.response.send_message("Taco Wranglers only. Nice try, though.", ephemeral=True)
            return
        guild = interaction.guild
        member = guild.get_member(self.uid)
        if member is None:
            await interaction.response.edit_message(content=f"🧾 <@{self.uid}> left the server. Panel closed.", view=None)
            return
        who, done, line = interaction.user.display_name, False, ""
        try:
            if self.action in CLANS:
                name, emoji = CLANS[self.action]
                role = role_named(guild, name)
                if not role:
                    await interaction.response.send_message(f"I can't find a role named **{name}**. Create it (exact name) "
                                                            "and drag my role above it.", ephemeral=True)
                    return
                other = role_named(guild, CLANS["outlawz" if self.action == "tacos" else "tacos"][0])
                plain = role_named(guild, "Recruit")
                drop = [r for r in (plain, other) if r and r in member.roles]
                if drop:
                    await member.remove_roles(*drop, reason=f"recruit panel: {name} (by {who})")
                await member.add_roles(role, reason=f"recruit panel: {name} (by {who})")
                line = f"{emoji} **{name}** chosen by {who}" + (" • plain Recruit role removed" if plain in drop else "")
            elif self.action == "joined":
                role = role_named(guild, "Clan Member")
                if not role:
                    await interaction.response.send_message("I can't find a role named **Clan Member**.", ephemeral=True)
                    return
                await member.add_roles(role, reason=f"recruit panel: joined in game (by {who})")
                plain = role_named(guild, "Recruit")
                if plain and plain in member.roles:
                    await member.remove_roles(plain, reason="recruit panel: now a clan member")
                line, done = f"✅ **Joined in game**: Clan Member role given by {who}. Welcome to the van. 🚐", True
            else:
                line, done = f"❌ Marked **not joining** by {who}. Roles left as they were.", True
        except discord.HTTPException:
            await interaction.response.send_message("Discord won't let me change their roles. I need **Manage Roles** and my "
                                                    "role dragged above Recruit, Tacos, Outlawz and Clan Member.", ephemeral=True)
            return
        old = interaction.message.content or ""
        status = [l for l in old.splitlines() if l.startswith(("🌮", "🤠", "✅", "❌"))]
        status = [l for l in status if not (self.action in CLANS and l.startswith(("🌮", "🤠")))] + [line]
        await interaction.response.edit_message(content=panel_text(member, status), view=view(self.uid, done),
                                                allowed_mentions=discord.AllowedMentions.none())


async def command(message) -> bool:
    """`soon recruit @name`: a panel for anyone, right here. `soon alumni @name`: left the clan in game
    (wranglers/mods)."""
    if ALUMNI_RE.match(message.content or "") and is_wrangler(message.author):
        target = next((m for m in message.mentions if not m.bot), None)
        if not target:
            await message.reply("Who left? `soon alumni @name`", mention_author=False)
            return True
        v = discord.ui.View(timeout=None)
        v.add_item(AlumniButton(target.id, "y"))
        v.add_item(AlumniButton(target.id, "n"))
        await message.channel.send(f"🎓 **{target.display_name}** left the clan in game?\nThis removes **all** their roles and "
                                   "gives them **Taco Alumni**. They stay in the Discord.", view=v,
                                   allowed_mentions=discord.AllowedMentions.none())
        return True
    if not RECRUIT_RE.match(message.content or "") or not is_wrangler(message.author):
        return False
    target = next((m for m in message.mentions if not m.bot), None)
    if not target:
        await message.reply("Who? `soon recruit @name`", mention_author=False)
        return True
    await panel(message.guild, target, message.channel)
    return True


class AlumniButton(discord.ui.DynamicItem[discord.ui.Button], template=r"soon:al:(?P<u>\d+):(?P<a>[yn])"):
    """Confirm for `soon alumni @name`: every role off (the ones Soon is allowed to touch), Taco Alumni on."""

    def __init__(self, uid: int, answer: str):
        label, emoji, style = (("Yes, make them alumni", "🎓", discord.ButtonStyle.danger) if answer == "y"
                               else ("Cancel", "✖️", discord.ButtonStyle.secondary))
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=f"soon:al:{uid}:{answer}"))
        self.uid, self.answer = uid, answer

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(int(match["u"]), match["a"])

    async def callback(self, interaction: discord.Interaction):
        if not is_wrangler(interaction.user):
            await interaction.response.send_message("Taco Wranglers only.", ephemeral=True)
            return
        if self.answer == "n":
            await interaction.response.edit_message(content="✖️ Cancelled. Nobody graduated.", view=None)
            return
        guild = interaction.guild
        member = guild.get_member(self.uid)
        alumni = role_named(guild, "Taco Alumni")
        if member is None:
            await interaction.response.edit_message(content=f"🎓 <@{self.uid}> isn't in the server anymore.", view=None)
            return
        if not alumni:
            await interaction.response.send_message("I can't find a role named **Taco Alumni**. Create it (exact name) "
                                                    "and drag my role above it.", ephemeral=True)
            return
        top = guild.me.top_role
        drop = [r for r in member.roles if not r.is_default() and not r.managed and r < top and r != alumni]
        kept = [r for r in member.roles if not r.is_default() and r not in drop and r != alumni]
        try:
            if drop:
                await member.remove_roles(*drop, reason=f"left the clan in game (by {interaction.user.display_name})")
            await member.add_roles(alumni, reason="Taco Alumni")
        except discord.HTTPException:
            await interaction.response.send_message("Discord won't let me change their roles. I need **Manage Roles** and "
                                                    "my role above theirs.", ephemeral=True)
            return
        text = (f"🎓 **{member.display_name}** is now **Taco Alumni** (by {interaction.user.display_name}). "
                "Gone from the van, never from our hearts. Their taco debt stays on the books.\n"
                f"-# Removed: {', '.join(r.name for r in drop) or 'nothing'}"
                + (f" • Couldn't remove (above me or managed by Discord): {', '.join(r.name for r in kept)}" if kept else ""))
        await interaction.response.edit_message(content=text, view=None, allowed_mentions=discord.AllowedMentions.none())
