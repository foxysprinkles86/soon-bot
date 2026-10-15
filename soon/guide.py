"""Soon's Guide (Shannon's add): a tap-through how-to. A public start panel ("What do you want to know?") with buttons;
each tap opens a PRIVATE page (only the tapper sees it) with more buttons, ⬅️ Back and 🏠 Start over, so nobody
spams the channel and it works in a read-only channel. `soon help` / `soon guide` shows the start panel in her
channels; mods type `soon guide post` in ANY channel (e.g. the read-only guide channel) to post a permanent one.
Keep pages short. Secrets stay secret: never list the Easter eggs or explain Kor's menu."""
import re

import discord

from . import config

FOOT = f"\n-# 🏠 Start over: tap **Start over**, or type `soon help` in {config.TALK_LINK}."

# key: (button label, emoji, parent, text, children)
PAGES = {
    "home": ("Start over", "🏠", None,
             "## 👋 Soon's Guide\nI'm Soon. Dealer, cashier, waitress, and the reason your tacos are always "
             "*coming soon*. What do you want to know? Tap one. Only you see my answers.",
             ["settings", "talk", "vibe", "casino", "tacos", "pings", "clan", "me"]),
    "dmbox": ("Suggestion box", "📮", "home",
              "-# Another one? Tap **Write a suggestion** again.", []),
    "settings": ("My settings", "⚙️", "home",
                 "## ⚙️ Everything I know about your settings\nChange anything with the buttons below.",
                 ["vibe", "pings", "me", "clan"]),
    "talk": ("Talking to me", "🗣️", "home",
             "## 🗣️ Talking to me\n"
             "• Start a message with **soon**, @ me, or reply to one of my messages.\n"
             f"• I really chat in {config.TALK_LINK}, {config.CASINO_LINK} and {config.DIARY_LINK}. "
             "Everywhere else I just pop in.\n"
             "• Say just **Soon** and I'll answer your last message.\n"
             "• Any language works. I read it all.\n"
             "• I remember things about you. Forever. Choose your words.",
             ["vibe", "me"]),
    "vibe": ("Roast me / be nice / leave me alone", "😈", "home",
             "## 😈 Pick your Soon experience\nWhat's your goal?",
             ["roast", "nice", "ignore", "pings"]),
    "roast": ("Ultimate roasts", "🔥", "vibe",
              "## 🔥 Ultimate roasts\n"
              "• Tap **Savage** or **Unhinged**: no mercy. **Spicy** is my normal.\n"
              "• `soon roast me` or `soon roast @name` (3 a day).\n"
              "• Be rude to me and I get meaner all by myself.\n"
              "• Gang up on me with friends and find out what happens. 👀",
              ["nice", "ignore"]),
    "nice": ("Make her nicer", "🥰", "vibe",
             "## 🥰 Make me nicer\n"
             "• Tap **Sweet** or **Mild**. **Auto** = I treat you how you treat me.\n"
             "• Be nice to me. Or tip me: `tip soon 10`. I warm up to big tippers.",
             ["roast", "ignore"]),
    "ignore": ("Leave me alone", "🙈", "vibe",
               "## 🙈 Leave me alone\nTap to switch, tap again to undo:\n"
               "• 🙈 **Ignore me**: no replies, no tags, no notes. The casino still works.\n"
               "• 📣 **Random call-outs**: me tagging you out of nowhere.\n"
               "• 🔔 **My pings**: I still talk to you, your phone just won't buzz.",
               ["pings", "nice"]),
    "casino": ("Casino & chips", "🎰", "home",
               f"## 🎰 Casa de Soon\nType these in {config.CASINO_LINK}.\n"
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
              "## 🔔 Pings & alerts\nTap a **green** button to turn it on or off, just for you:\n"
              "• 🎰 heists + duels · 🏁 race reminders · 🦑 Kraken · 👋 new members to welcome · 📅 events\n"
              "• 🔔 **My pings**: off = I still talk to you, your phone just won't buzz.\n"
              "• Whole server too loud? Long-press the server icon → **Notifications** → **Only @mentions**.",
              ["ignore", "clan"]),
    "clan": ("Clan stuff", "🗺️", "home",
             "## 🗺️ Clan stuff\n"
             "• Tap your world zone below (or type `zone` + your country).\n"
             "• `soon events`: upcoming race reminders.\n"
             "• Race + Kraken reminders post in **#race-and-event-announcements**. `alerts` to get pinged.\n"
             "• `soon who is <name>`: who someone is in game.",
             ["racebet", "me"]),
    "me": ("About me, nickname & suggestions", "📇", "home",
           "## 📇 Tell me about you\nTap a **green** button: a little form pops up.\n"
           "• 📝 your in-game name · 🕐 your city or time zone · 🎂 your birthday\n"
           "• 🎲 **New nickname**: I'll invent one next time you talk to me. 🚫 **No nicknames**: your own name back.\n"
           "• 📮 **Suggestion**: ideas, complaints, changes. 🔒 Only Master Foxy and the mods see it.\n"
           "-# For fun: `soon grudges` · `soon favorites` · `soon panda facts` · `soon hall of shame`",
           ["settings", "talk"]),
}
# Real buttons on some pages (Shannon: "make buttons for these things vs just explaining them"). Each changes the
# TAPPER's own setting and shows the page again with a ✅ line on top. bot.py sets ACT: async (interaction, act) -> str.
ACT = None        # async (interaction, act, value=None) -> str
STATUS = None     # async (interaction) -> str: the "My settings" overview
MODALS = {  # act: (form title, field label, placeholder, max length)
    "modal-ign": ("Your in-game name", "In-game name (Mob Control)", "e.g. TacoQueen", 40),
    "modal-tz": ("Where are you?", "City or time zone", "e.g. Amsterdam, Sydney, EST, UTC+10", 60),
    "modal-bday": ("Your birthday", "Month and day", "e.g. March 14", 30),
    "modal-suggest": ("📮 Private suggestion", "Idea, complaint or change", "Only Master Foxy and the mods see this.", 500),
}
ACTIONS = {
    "pings": [("al-casino", "Casino alerts", "🎰"), ("al-race", "Race alerts", "🏁"), ("al-kraken", "Kraken alerts", "🦑"),
              ("al-newbie", "New member alerts", "👋"), ("al-events", "Event alerts", "📅"), ("tags", "My pings", "🔔")],
    "roast": [("heat-savage", "Savage", "😈"), ("heat-unhinged", "Unhinged", "🤬"), ("heat-spicy", "Spicy", "🌶️")],
    "nice": [("heat-sweet", "Sweet", "🥰"), ("heat-mild", "Mild", "😇"), ("heat-auto", "Auto: earn it", "🔄")],
    "ignore": [("ignore", "Ignore me / talk to me", "🙈"), ("pester", "Random call-outs", "📣"), ("tags", "My pings", "🔔")],
    "dmbox": [("modal-suggest", "Write a suggestion", "📮")],
    "me": [("modal-ign", "In-game name", "📝"), ("modal-tz", "Time zone", "🕐"), ("modal-bday", "Birthday", "🎂"),
           ("nick-new", "New nickname", "🎲"), ("nick-stop", "No nicknames", "🚫"), ("modal-suggest", "Suggestion", "📮")],
    "clan": [("zone-raccoon", "Raccoons", "🦝"), ("zone-lion", "Lions", "🦁"), ("zone-panda", "Pandas", "🐼"),
             ("zone-platypus", "Platypus", "🦆")],
}
CMD_RE = re.compile(r"(?i)^\s*soon\s+(?:help|guide|how ?to|what can you do\??|commands)\s*[!?.]*\s*$")
POST_RE = re.compile(r"(?i)^\s*soon\s+guide\s+post\s*$")


def view(key: str, dm_button: bool = False) -> discord.ui.View:
    _, _, parent, _, kids = PAGES[key]
    v = discord.ui.View(timeout=None)
    for act, label, emoji in ACTIONS.get(key, []):
        v.add_item(ActionButton(key, act, label, emoji))
    for k in kids:
        v.add_item(GuideButton(k))
    if dm_button:                                       # public panel only: the private suggestion box by DM
        v.add_item(GuideButton("dm"))
    if parent and parent != "home":
        v.add_item(GuideButton(parent, back=True))
    if key not in ("home", "dmbox"):
        v.add_item(GuideButton("home"))
    return v


def text(key: str) -> str:
    return PAGES[key][3] + ("" if key == "dmbox" else FOOT)


async def page_text(interaction, key: str) -> str:
    if key == "settings" and STATUS:
        return PAGES[key][3] + "\n" + await STATUS(interaction) + FOOT
    return text(key)


async def show(interaction, key: str, top: str = ""):
    """Flip their private copy / DM to this page, or open a private copy from the public panel."""
    body = (top + "\n\n" if top else "") + await page_text(interaction, key)
    msg = interaction.message
    if interaction.guild is None or (msg is not None and msg.flags.ephemeral):
        await interaction.response.edit_message(content=body[:2000], view=view(key))
    else:
        await interaction.response.send_message(body[:2000], view=view(key), ephemeral=True)


class GuideModal(discord.ui.Modal):
    def __init__(self, page: str, act: str):
        title, label, hint, size = MODALS[act]
        super().__init__(title=title, timeout=600)
        self.page, self.act = page, act
        self.box = discord.ui.TextInput(label=label, placeholder=hint, max_length=size,
                                        style=discord.TextStyle.paragraph if size > 100 else discord.TextStyle.short)
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        done = await ACT(interaction, self.act, str(self.box.value).strip()) if ACT else "Not now."
        try:
            await show(interaction, self.page, f"✅ {done}")
        except discord.HTTPException:
            await interaction.response.send_message(f"✅ {done}", ephemeral=True)


class GuideButton(discord.ui.DynamicItem[discord.ui.Button], template=r"soon:g:(?P<k>[a-z]+)(?P<b>:b)?"):
    def __init__(self, key: str, back: bool = False):
        label, emoji, *_ = PAGES.get(key) or ("Private suggestion box (DM)", "📬")
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
        if self.key == "dm":                             # 📬 the private suggestion box, in their DMs (Shannon)
            box = discord.ui.View(timeout=None)
            box.add_item(ActionButton("dmbox", "modal-suggest", "Write a suggestion", "📮"))
            try:
                await interaction.user.send(SUGGEST_DM, view=box)
                await interaction.response.send_message("📬 Check your DMs. The suggestion box is waiting.", ephemeral=True)
            except discord.HTTPException:
                await interaction.response.send_message("Your DMs are closed, so use this instead. "
                                                        "🔒 Still private: only Master Foxy and the mods see it.",
                                                        view=box, ephemeral=True)
            return
        await show(interaction, self.key)


class ActionButton(discord.ui.DynamicItem[discord.ui.Button], template=r"soon:ga:(?P<p>[a-z]+):(?P<a>[a-z-]+)"):
    """A guide button that DOES something for whoever taps it (alerts, heat, ignore, zone...)."""

    def __init__(self, page: str, act: str, label: str = "", emoji: str | None = None):
        if not label:
            label, emoji = next(((lb, em) for a, lb, em in ACTIONS.get(page, []) if a == act), (act, None))
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.success,
                                           custom_id=f"soon:ga:{page}:{act}"))
        self.page, self.act = page, act

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(match["p"] if match["p"] in PAGES else "home", match["a"])

    async def callback(self, interaction: discord.Interaction):
        if self.act in MODALS:                           # a little form pops up (name, time zone, birthday, suggestion)
            await interaction.response.send_modal(GuideModal(self.page, self.act))
            return
        done = await ACT(interaction, self.act) if ACT else "Not now. Try again in a minute."
        await show(interaction, self.page, f"✅ {done}")


async def post(channel, reply_to=None):
    kw = dict(view=view("home", dm_button=True), allowed_mentions=discord.AllowedMentions.none())
    body = PAGES["home"][3] + f"\n-# Tap a button. Lost later? Type `soon help` in {config.TALK_LINK}."
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


SUGGEST_DM = ("## 📮 Soon's private suggestion box\nIdeas, complaints, changes, things I should stop doing. "
              "Tap **Write a suggestion**, or just type `suggest <your idea>` here.\n"
              "🔒 Only Master Foxy and the mods see it. Not the server. Not even the testers.")
DM_HELP_RE = re.compile(r"(?i)^\s*(?:soon\s+)?(?:help|guide|how ?to|menu|start|start over|commands|hi|hello|hey)\s*[!?.]*\s*$")


async def dm(message, guild) -> bool:
    """DMs are for the private suggestion box only (Shannon: keep the guide in the channel). `help` / `settings` /
    `suggest` with nothing after it = the suggestion box with its 📮 form button, plus a link to #soon-guide."""
    if not (DM_HELP_RE.match(message.content or "") or re.match(r"(?i)^\s*(?:soon\s+)?(?:my\s+)?(?:settings|suggest(?:ion)?"
                                                             r"(?: box)?)\s*[!?.]*\s*$", message.content or "")):
        return False
    await send_box(message.channel, guild)
    return True


def guide_link(guild) -> str:
    ch = next((c for c in getattr(guild, "text_channels", []) if "soon-guide" in c.name.lower()), None)
    return ch.mention if ch else "#soon-guide"


async def send_box(channel, guild):
    box = discord.ui.View(timeout=None)
    box.add_item(ActionButton("dmbox", "modal-suggest", "Write a suggestion", "📮"))
    await channel.send(SUGGEST_DM + f"\n-# Help and all your settings live in {guide_link(guild)}.", view=box)
