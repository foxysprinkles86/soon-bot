"""Quick-draw duel: challenge, accept, wait for it... DRAW. First tap wins. Tapping early is a misfire.
Bragging rights only for now; chips get wired in after the casino moves over."""
import asyncio
import random

import discord


class ChallengeView(discord.ui.View):
    def __init__(self, challenger: discord.Member, target: discord.Member):
        super().__init__(timeout=120)
        self.challenger, self.target = challenger, target
        self.accepted: bool | None = None
        self.done = asyncio.Event()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("This duel isn't yours. Get your own enemies.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept", emoji="⚔️", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, _):
        self.accepted = True
        await interaction.response.edit_message(view=None)
        self.done.set()

    @discord.ui.button(label="Decline", emoji="🐔", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, _):
        self.accepted = False
        await interaction.response.edit_message(view=None)
        self.done.set()

    async def on_timeout(self):
        self.done.set()


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


async def run_duel(channel: discord.abc.Messageable, challenger: discord.Member, target: discord.Member, memory, brain, log_event):
    view = ChallengeView(challenger, target)
    msg = await channel.send(
        f"⚔️ {challenger.mention} challenges {target.mention} to a **quick-draw duel**!\n"
        f"{target.mention}, accept? You have 2 minutes.\n-# When the button turns red and says DRAW, tap it first. Tap early and you misfire.",
        view=view)
    await view.done.wait()
    if not view.accepted:
        text = ("🐔 Declined. Bawk." if view.accepted is False else "⏰ No answer. Cowardice by default.")
        await msg.edit(content=msg.content.split("\n")[0] + f"\n{text}", view=None)
        return

    draw = DrawView(challenger, target)
    duel_msg = await channel.send(f"🤠 {challenger.display_name} vs {target.display_name}\n# Ready...", view=draw)
    wait = random.uniform(3, 10)
    if random.random() < 0.35:  # fake-out
        try:
            await asyncio.wait_for(draw.done.wait(), timeout=wait * 0.5)
        except asyncio.TimeoutError:
            await duel_msg.edit(content=f"🤠 {challenger.display_name} vs {target.display_name}\n# DR... no. Not yet. 🙂")
        wait *= 0.6
    try:
        await asyncio.wait_for(draw.done.wait(), timeout=wait)
    except asyncio.TimeoutError:
        await draw.go_live(duel_msg)
        try:
            await asyncio.wait_for(draw.done.wait(), timeout=20)
        except asyncio.TimeoutError:
            await duel_msg.edit(content="# 💤 Nobody drew. You're both cowards. I'm keeping the dust.", view=None)
            return

    winner = draw.winner
    loser = target if winner == challenger else challenger
    w = await memory.get_kv(f"duel:{winner.guild.id}:{winner.id}") or "0,0"
    l = await memory.get_kv(f"duel:{loser.guild.id}:{loser.id}") or "0,0"
    ww, wl = (int(x) for x in w.split(","))
    lw, ll = (int(x) for x in l.split(","))
    await memory.set_kv(f"duel:{winner.guild.id}:{winner.id}", f"{ww + 1},{wl}")
    await memory.set_kv(f"duel:{loser.guild.id}:{loser.id}", f"{lw},{ll + 1}")
    how = f"{loser.display_name} MISFIRED" if draw.misfire else f"{winner.display_name} was faster"
    log_event(f"quick-draw duel: {winner.display_name} beat {loser.display_name} ({how})")
    line = await brain.write(
        f"A quick-draw duel just ended: {winner.display_name} beat {loser.display_name} because {how}. "
        f"Write ONE short, savage commentary line. "
        f"{'Kor won: be flustered and proud. ' if 'korehaan' in winner.name.lower() else ''}"
        f"{'Kor lost: blame the other person somehow. ' if 'korehaan' in loser.name.lower() else ''}No @ mentions.",
        max_tokens=80)
    await duel_msg.edit(
        content=(f"# 🏆 {winner.display_name} wins!\n"
                 f"{'💥 ' + loser.display_name + ' drew too early. Misfire. Humiliating.' if draw.misfire else '⚡ Fastest hand in the van.'}\n"
                 f"{line}\n-# Record: {winner.display_name} {ww + 1}-{wl} · {loser.display_name} {lw}-{ll + 1}"),
        view=None)


async def record_text(memory, member: discord.Member) -> str:
    rec = await memory.get_kv(f"duel:{member.guild.id}:{member.id}") or "0,0"
    w, l = (int(x) for x in rec.split(","))
    return f"⚔️ **{member.display_name}**: {w} wins, {l} losses." + (" Undefeated. Suspicious." if w and not l else "")
