"""The quick-draw button used by Duels (duels.py): WAIT... then DRAW! First tap wins. Tapping early is a misfire.
Plus the duel win-loss record (`soon duel record`)."""
import asyncio
import random

import discord


class DrawView(discord.ui.View):
    """One button. While it says WAIT, tapping it is a misfire. When it flips to DRAW, first tap wins."""

    def __init__(self, a: discord.Member, b: discord.Member):
        super().__init__(timeout=60)
        self.a, self.b = a, b
        self.live = False
        self.winner: discord.Member | None = None
        self.misfire: discord.Member | None = None
        self.done = asyncio.Event()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in (self.a.id, self.b.id):
            await interaction.response.send_message("Spectators don't get a gun. Sit down.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="WAIT...", emoji="✋", style=discord.ButtonStyle.secondary)
    async def draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.done.is_set():
            await interaction.response.defer()
            return
        shooter = self.a if interaction.user.id == self.a.id else self.b
        if self.live:
            self.winner = shooter
        else:
            self.misfire = shooter
            self.winner = self.b if shooter == self.a else self.a
        button.disabled = True
        self.done.set()
        await interaction.response.edit_message(view=self)

    async def go_live(self, message: discord.Message):
        self.live = True
        btn = self.children[0]
        btn.label, btn.emoji, btn.style = "DRAW!", "⚔️", discord.ButtonStyle.danger
        await message.edit(content="# ⚔️ DRAW! ⚔️", view=self)


async def record_text(memory, member: discord.Member) -> str:
    rec = await memory.get_kv(f"duel:{member.guild.id}:{member.id}") or "0,0"
    w, l = (int(x) for x in rec.split(","))
    return f"⚔️ **{member.display_name}**: {w} wins, {l} losses." + (" Undefeated. Suspicious." if w and not l else "")
