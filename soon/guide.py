"""Soon's Guide (Shannon's add): a tap-through how-to. A public start panel ("What do you want to know?") with buttons;
each tap opens a PRIVATE page (only the tapper sees it) with more buttons, ⬅️ Back and 🏠 Start over, so nobody
spams the channel and it works in a read-only channel. `soon help` / `soon guide` shows the start panel in her
channels; mods type `soon guide post` in ANY channel (e.g. the read-only guide channel) to post a permanent one.
Keep pages short. Secrets stay secret: never list the Easter eggs or explain Kor's menu."""
import re

import discord

FOOT = "\n-# 🏠 Start over: tap **Start over**, or type `soon help` (here in DMs: just `help`)."
DM_FOOT = ("\n🔒 **Private suggestion box:** type `suggest <your idea>` right here. Only Master Foxy and the mods see it."
           "\n-# Type `help` here any time to start over.")

# key: (button label, emoji, parent, text, children)
PAGES = {
    "home": ("Start over", "🏠", None,
             "## 👋 Soon's Guide\nI'm Soon. Dealer, cashier, waitress, and the reason your tacos are always "
             "*coming soon*. What do you want to know? Tap one. Only you see my answers.",
             ["talk", "vibe", "casino", "tacos", "pings", "clan", "me"]),
    "talk": ("Talking to me", "🗣️", "home",
             "## 🗣️ Talking to me\n"
             "• Start a message with **soon**, @ me, or reply to one of my messages.\n"
             "• I really chat in **#taco-trash-talk**, the casino and my diary. Everywhere else I just pop in.\n"
             "• Say just **Soon** and I'll answer your last message.\n"
             "• Any language works. I read it all.\n"
             "• I remember things about you. Forever. Choose your words.",
             ["vibe", "me"]),
    "vibe": ("Roast me / be nice / leave me alone", "😈", "home",
             "## 😈 Pick your Soon experience\nWhat's your goal?",
             ["roast", "nice", "ignore", "pings"]),
    "roast": ("Ultimate roasts", "🔥", "vibe",
              "## 🔥 Ultimate roasts\n"
              "• `soon heat savage` or `soon heat unhinged`: no mercy.\n"
              "• `soon roast me` or `soon roast @name` (3 a day).\n"
              "• Be rude to me and I get meaner all by myself.\n"
              "• Gang up on me with friends and find out what happens. 👀",
              ["nice", "ignore"]),
    "nice": ("Make her nicer", "🥰", "vibe",
             "## 🥰 Make me nicer\n"
             "• `soon heat sweet` or `soon heat mild`.\n"
             "• `soon heat` shows your setting with buttons. `soon heat auto` = back to normal.\n"
             "• Be nice to me. Or tip me: `tip soon 10`. I warm up to big tippers.",
             ["roast", "ignore"]),
    "ignore": ("Leave me alone", "🙈", "vibe",
               "## 🙈 Leave me alone\n"
               "• `soon ignore me`: no replies, no tags, no notes. The casino still works. `soon talk to me` undoes it.\n"
               "• `soon stop pestering me`: I stop randomly calling you out. `soon pester me` undoes it.\n"
               "• `soon no tags`: I still talk to you, your phone just won't buzz.",
               ["pings", "nice"]),
    "casino": ("Casino & chips", "🎰", "home",
               "## 🎰 Casa de Soon\nType these in the **casino channel**.\n"
               "• `casino` main menu · `games` · `payouts` · `chips` · `timers` · `casino board`\n"
               "• Out of chips? `broke`. I have a menu for that.\n"
               "-# Rumor has it there's a `crimes` menu. I know nothing. 🤫",
               ["chips", "games", "heists", "duels", "racebet"]),
    "chips": ("Getting chips", "🪙", "casino",
              "## 🪙 Getting chips\n"
              "• `claim`: 100 free chips every 12 hours.\n"
              "• `scratch`: a free scratch card every 12 hours.\n"
              "• `buy chips 1` (1 taco = 40 chips) · `loan 100` · `cashier`\n"
              "• `broke`: every free-chip route, plus a 💋 Bribe Soon button.\n"
              "• Generous? `tip @name 10` · `make it rain 50`",
              ["games", "heists"]),
    "games": ("Games", "🎲", "casino",
              "## 🎲 Games\n"
              "• `spin`: slots, 5 chips. Triple tacos = jackpot.\n"
              "• `toss 20 heads` (add `side` for a long shot)\n"
              "• `roulette 20 red` or `roulette 5 17`\n"
              "• `blackjack 20`, then hit / stand / double\n"
              "• `buy scratch`: 5 chips a card\n"
              "• Sometimes the Wheel of Fortaco spins itself. 🎡",
              ["heists", "duels"]),
    "heists": ("Heists", "💰", "casino",
               "## 💰 Heists\n"
               "• `heist`: start a Vault Heist (every hour) or a Grand Heist (every 8 hours).\n"
               "• Everyone else types `join` before the van leaves.\n"
               "• Kor drives. `kor menu` shows his perks.\n"
               "• Want a ping when one starts? `casino alerts on`",
               ["duels", "pings"]),
    "duels": ("Duels", "🤠", "casino",
              "## 🤠 Duels\n"
              "• `duel @name 20` (1–100). They type `accept` or `decline`.\n"
              "• Everyone else: `bet 10 on @name` (5–25).\n"
              "• Then: wait… wait… tap **DRAW!** first. Tap early = misfire = you lose.\n"
              "• Winner can go **Double or Nothing**. `soon duel record` = your stats.",
              ["heists", "racebet"]),
    "racebet": ("Race betting", "🏁", "casino",
                "## 🏁 Race betting\n"
                "• `race bet @name 20`: who scores the most for TnT this race? (1–100, you can pick yourself)\n"
                "• `race bets`: the betting book.\n"
                "• Opens when race pre-join opens, closes when the race starts. Winners split the pot +20%.",
                ["clan", "games"]),
    "tacos": ("Tacos, bar & eggs", "🌮", "home",
              "## 🌮 Tacos, bar & Easter eggs\n"
              "• Say **taco** and I take your order. It's coming soon. It's always coming soon.\n"
              "• `taco status` · `taco board`\n"
              "• Say **marg** for a margarita · `bar board`\n"
              "• Easter eggs are hidden all over. `egg hint` asks the Egg Oracle · `egg board` · `basket @name`\n"
              "• In taco debt? `sorry soon` once a day. Maybe I'll forgive you.",
              ["clan", "me"]),
    "pings": ("Pings & alerts", "🔔", "home",
              "## 🔔 Pings & alerts\n"
              "• `alerts`: pick what I ping you for: 🎰 casino, 🏁 race, 🦑 Kraken, 👋 new members, 📅 events.\n"
              "• Tap **🔔 My pings on/off** under any of my messages, or type `soon no tags`.\n"
              "• Whole server too loud? Long-press the server icon → **Notifications** → **Only @mentions**.",
              ["ignore", "clan"]),
    "clan": ("Clan stuff", "🗺️", "home",
             "## 🗺️ Clan stuff\n"
             "• `zone raccoon` / `lion` / `panda` / `platypus` (or your country): your world zone.\n"
             "• `soon events`: upcoming race reminders.\n"
             "• Race + Kraken reminders post in **#race-and-event-announcements**. `alerts` to get pinged.\n"
             "• `soon who is <name>`: who someone is in game.",
             ["racebet", "me"]),
    "me": ("Tell Soon about you", "📇", "home",
           "## 📇 Tell me about you\n"
           "• `soon my name is <in-game name>`\n"
           "• `soon my timezone is <city or zone>` · `soon my birthday is March 14`\n"
           "• `soon give me a new nickname` (I pick it. You'll live.)\n"
           "• `soon suggest <idea>`: ideas, complaints, changes. Master Foxy reads every one.\n"
           "• 🔒 Private? DM me `suggest <idea>` instead.\n"
           "• For fun: `soon grudges` · `soon favorites` · `soon panda facts` · `soon hall of shame`",
           ["vibe", "talk"]),
}
CMD_RE = re.compile(r"(?i)^\s*soon\s+(?:help|guide|how ?to|what can you do\??|commands)\s*[!?.]*\s*$")
POST_RE = re.compile(r"(?i)^\s*soon\s+guide\s+post\s*$")


def view(key: str, dm_button: bool = False) -> discord.ui.View:
    _, _, parent, _, kids = PAGES[key]
    v = discord.ui.View(timeout=None)
    for k in kids:
        v.add_item(GuideButton(k))
    if dm_button:                                       # public panel only: take the whole guide to their DMs
        v.add_item(GuideButton("dm"))
    if parent and parent != "home":
        v.add_item(GuideButton(parent, back=True))
    if key != "home":
        v.add_item(GuideButton("home"))
    return v


def text(key: str) -> str:
    return PAGES[key][3] + FOOT


class GuideButton(discord.ui.DynamicItem[discord.ui.Button], template=r"soon:g:(?P<k>[a-z]+)(?P<b>:b)?"):
    def __init__(self, key: str, back: bool = False):
        label, emoji, *_ = PAGES.get(key) or ("Open in my DMs", "📬")
        if back:
            label, emoji = "Back", "⬅️"
        style = discord.ButtonStyle.primary if key == "home" and not back else discord.ButtonStyle.secondary
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=style,
                                           custom_id=f"soon:g:{key}" + (":b" if back else "")))
        self.key = key

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(match["k"] if match["k"] in PAGES or match["k"] == "dm" else "home", bool(match["b"]))

    async def callback(self, interaction: discord.Interaction):
        if self.key == "dm":                             # 📬 the whole guide, privately, in their DMs
            try:
                await interaction.user.send(PAGES["home"][3] + DM_FOOT, view=view("home"))
                await interaction.response.send_message("📬 Check your DMs. I slid in. Classy.", ephemeral=True)
            except discord.HTTPException:
                await interaction.response.send_message("Your DMs are closed. Here's your private copy instead:\n\n"
                                                        + text("home"), view=view("home"), ephemeral=True)
            return
        msg = interaction.message
        if interaction.guild is None or (msg is not None and msg.flags.ephemeral):   # their DM / private copy: flip the page
            await interaction.response.edit_message(content=text(self.key), view=view(self.key))
        else:                                            # the public panel: open a private copy for the tapper
            await interaction.response.send_message(text(self.key), view=view(self.key), ephemeral=True)


async def post(channel, reply_to=None):
    kw = dict(view=view("home", dm_button=True), allowed_mentions=discord.AllowedMentions.none())
    body = PAGES["home"][3] + "\n-# Tap a button. Lost later? Type `soon help` in one of my channels."
    if reply_to is not None:
        await reply_to.reply(body, mention_author=False, **kw)
    else:
        await channel.send(body, **kw)


async def command(message, is_mod: bool, in_her_channel: bool) -> bool:
    """`soon guide post` (mods, any channel: a permanent panel) • `soon help` / `soon guide` (her channels)."""
    content = message.content or ""
    if POST_RE.match(content) and is_mod:
        await post(message.channel)
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        return True
    if in_her_channel and CMD_RE.match(content):
        await post(message.channel, reply_to=message)
        return True
    return False


DM_HELP_RE = re.compile(r"(?i)^\s*(?:soon\s+)?(?:help|guide|how ?to|menu|start|start over|commands|hi|hello|hey)\s*[!?.]*\s*$")


async def dm(message) -> bool:
    """`help` in DMs: the whole guide right there."""
    if not DM_HELP_RE.match(message.content or ""):
        return False
    await message.channel.send(PAGES["home"][3] + DM_FOOT, view=view("home"))
    return True
