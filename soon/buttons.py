"""Clickable buttons for the casino. Every button just "types" a casino command for whoever presses it,
so buttons and typed commands always behave the same (same chips, cooldowns, limits and jokes).
Buttons keep working after Soon restarts (the command lives in the button's id)."""
import re

import discord

ROUTERS = []      # filled by bot.py at startup: async handlers (message, bank, mod) -> bool
BANK = None


class ButtonMessage:
    """Looks enough like a typed Discord message for the casino code to handle a button press."""

    def __init__(self, interaction: discord.Interaction, content: str):
        self.author = interaction.user
        self.channel = interaction.channel
        self.guild = interaction.guild
        self.content = content
        self.clean_content = content
        self.mentions = []
        self.reference = None

    async def reply(self, text: str = "", **kw):
        kw.pop("mention_author", None)
        return await self.channel.send(f"{self.author.mention} {text}", **kw)


class PlayButton(discord.ui.DynamicItem[discord.ui.Button], template=r"soon:p:(?P<cmd>.+)"):
    def __init__(self, cmd: str, label: str = "", emoji: str | None = None,
                 style: discord.ButtonStyle = discord.ButtonStyle.secondary):
        super().__init__(discord.ui.Button(label=label or None, emoji=emoji, style=style,
                                           custom_id=f"soon:p:{cmd}"[:100]))
        self.cmd = cmd

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(match["cmd"])

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()          # tells Discord "got it"; results post in the channel
        msg = ButtonMessage(interaction, self.cmd)
        for route in ROUTERS:
            if await route(msg, BANK, False):
                return
        if self.cmd in ("hit", "stand", "double"):
            text = "That's not your hand, sweetie. Deal your own: type `blackjack 20`."
        else:
            text = "Nothing to do there right now. Type the command instead."
        await interaction.followup.send(text, ephemeral=True)


def view(*buttons: tuple) -> discord.ui.View:
    """view(("spin", "Spin again", "🎰"), ("hit", "Hit", None, discord.ButtonStyle.primary), ...)"""
    v = discord.ui.View(timeout=None)
    for b in buttons:
        cmd, label, emoji = b[0], b[1], b[2] if len(b) > 2 else None
        style = b[3] if len(b) > 3 else discord.ButtonStyle.secondary
        v.add_item(PlayButton(cmd, label, emoji, style))
    return v
