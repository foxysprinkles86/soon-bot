"""Soon's Guide (Shannon's add): a tap-through how-to. A public start panel ("What do you want to know?") with buttons;
each tap opens a PRIVATE page (only the tapper sees it) with more buttons, ⬅️ Back and 🏠 Start over, so nobody
spams the channel and it works in a read-only channel. `soon help` / `soon guide` shows the start panel in her
channels; mods type `soon guide post` in ANY channel (e.g. the read-only guide channel) to post a permanent one.
Keep pages short. Secrets stay secret: never list the Easter eggs or explain Kor's menu."""
import re

import discord

from . import config, extras

FOOT = f"\n-# 🏠 Start over: tap **Start over**, or type `soon help` in {config.TALK_LINK}."

# key: (button label, emoji, parent, text, children). Keys are lowercase letters only (they go in button ids).
# Layout = Shannon's approved tree (Oct 16): Settings / Soon & Fun / Casa de Soon / Clan & Help, 3 levels max.
# Pages in DYNAMIC_KEYS get live info under their text (bot.py DYNAMIC hook). "show-<key>" buttons put live info
# (boards, lists) on top of the page they're on.
PAGES = {
    "home": ("Start over", "🏠", None,
             "## {SOON} Soon's Guide\nI'm Soon. Dealer, cashier, waitress, and the reason your tacos are always "
             "*coming soon*. What do you want to know? Tap one. Only you see my answers.",
             ["set", "sf", "casa", "ch"]),
    # ⚙️ SETTINGS
    "set": ("Settings", "⚙️", "home", "## ⚙️ Settings\nYour profile, how I treat you, and what I ping you for.",
            ["profile", "mood", "pings"]),
    "profile": ("My profile", "📇", "set",
                "## 📇 My profile\nEverything I know about your settings is below. Change anything:\n"
                "• 📝 name · 🕐 time zone · 🎂 birthday: a little form pops up\n"
                "• 🦝🦁🐼🦆 your world zone · 🎰🏁🦑👋📅 your alerts (tap again to turn off)\n"
                "• 🎲 **New nickname**: I'll invent one next time we talk. 🚫 **No nicknames**: your own name back.",
                []),
    "mood": ("Soon's Mood", "😈", "set",
             "## 😈 Soon's Mood\nPick how I treat you:\n"
             "• 🥰 Sweet · 😇 Mild · 🌶️ Spicy (my normal) · 😈 Savage · 🤬 Unhinged\n"
             "• 🔄 **Auto**: I treat you how you treat me. Be rude = I get meaner. Tip me (`tip soon 10`) = I warm up.\n"
             "• 🙈 **Ignore me** (tap again to undo) · 📣 **Random call-outs** on/off\n"
             "• 🧠 **Erase Soon's memory of me**: I forget what I know about you and start fresh. "
             "It does NOT make me ignore you.\n"
             "-# Gang up on me with friends and find out what happens. 👀",
             []),
    "erase": ("Erase Soon's memory of me", "🧠", "mood",
              "## 🧠 Erase my memory of you?\nI'll forget my notes about you, my grudges (or soft spot), your nickname "
              "and the things you've complained about. My mood toward you goes back to Auto.\n"
              "**I will NOT ignore you.** I'll still chat with you, like we just met.\n"
              "Your in-game name, time zone, birthday, zone, alerts, chips and tacos stay.\n"
              "-# This can't be undone.",
              []),
    "pings": ("Pings & alerts", "🔔", "set",
              "## 🔔 Pings & alerts\nTap a **green** button to turn it on or off, just for you:\n"
              "• 🎰 heists + duels · 🏁 race reminders · 🦑 Kraken · 👋 new members to welcome · 📅 events\n"
              "• 🔔 **My pings**: off = I still talk to you, your phone just won't buzz.\n"
              "**Discord too loud?** Long-press the server icon → **Notifications** → **Only @mentions**. "
              "One noisy channel? Long-press it → **Mute**.",
              []),
    # 🗣️ SOON & FUN
    "sf": ("Soon & Fun", "🗣️", "home", "## 🗣️ Soon & Fun\nTalking to me, my mood, tacos, eggs and gossip.",
           ["talk", "mood", "tacos", "eggs", "fun"]),
    "talk": ("Talking to Soon", "🗣️", "sf",
             "## 🗣️ Talking to me\n"
             "• Start a message with **soon**, @ me, or reply to one of my messages.\n"
             f"• I really chat in {config.TALK_LINK}, {config.CASINO_LINK} and {config.DIARY_LINK}. "
             "Everywhere else I just pop in for a line.\n"
             "• Say just **Soon** and I'll answer your last message. Any language works.\n"
             "• `soon roast @name` or `soon roast me` (3 a day) · `soon who is <name>` · `soon mood` · `soon events`\n"
             "• I keep a diary, hand out awards on Sundays, and side-eye you with emojis. I remember everything.",
             []),
    "tacos": ("Tacos & bar", "🌮", "sf",
              "## 🌮 Tacos & bar\n"
              "• Say **taco** and I take your order. It's coming soon. It's always coming soon. Ask a lot to climb the "
              "taco ranks. Rumor says 1 in 500 orders is real.\n"
              "• `taco status` · In taco debt? `sorry soon` once a day. Maybe I'll forgive you.\n"
              "• Say **marg** for a margarita. Bar ranks too. I cut people off.\n"
              "• Every night the **Van Daily Report** hands out awards in my diary.",
              []),
    "eggs": ("Easter eggs", "🥚", "sf",
             "## 🥚 Easter eggs\nThere are eggs hidden all over. No, I won't tell you where.\n"
             "• `egg hint`: the Egg Oracle gives you a clue (every 30 min)\n"
             "• `egg board` · `basket @name` to snoop on someone",
             []),
    "fun": ("Fun lists", "🎭", "sf", "## 🎭 Fun lists\nTap one. Only you see it.", []),
    # 🎰 CASA DE SOON
    "casa": ("Casa de Soon", "🎰", "home",
             f"## 🎰 Casa de Soon\nThe casino lives in {config.CASINO_LINK}. Type everything there.\n"
             "`casino` = main menu · `games` · `payouts`",
             ["chips", "games", "big", "mycasino"]),
    "chips": ("Chips & cashier", "🪙", "casa",
              "## 🪙 Chips & cashier\n"
              "• `claim`: 100 free chips every 12 hours · `scratch`: a free scratch card every 12 hours\n"
              "• `buy chips 1` (1 taco = 40 chips, debt allowed) · `loan 100` · `cash out 50` · `cashier`\n"
              "• Out of chips? `broke` = every free-chip route + a 💋 **Bribe Soon** button.\n"
              "• `tip @name 10` · `tip soon 10` · `make it rain 50` · `soon make it rain` · `rob the bartender`",
              []),
    "games": ("Games", "🎲", "casa",
              "## 🎲 Games\n"
              "• `spin`: slots, 5 chips. Triple tacos = jackpot.\n"
              "• `toss 20 heads` (add `side` for a long shot) · `roulette 20 red` or `roulette 5 17`\n"
              "• `blackjack 20`, then hit / stand / double · `buy scratch`: 5 chips a card\n"
              "• Sometimes the Wheel of Fortaco spins itself. 🎡",
              []),
    "big": ("Heists, duels & bets", "💰", "casa",
            "## 💰 Heists, duels & bets\n"
            "• `heist`: Vault Heist (every hour) or Grand Heist (every 8 hours). Others type `join`. Kor drives: "
            "`kor menu`. Grand on cooldown? `bribe soon grand 20` feeds the shared bribe pot.\n"
            "• `duel @name 20`: they `accept`, everyone else `bet 10 on @name`, then tap **DRAW!** first. "
            "Early tap = misfire. Winner can go **Double or Nothing**.\n"
            "• `race bet @name 20`: who scores the most for TnT? `race bets` = the book.\n"
            "-# Rumor has it there's a `crimes` menu. I know nothing. 🤫",
            []),
    "mycasino": ("My casino", "📊", "casa", "## 📊 My casino\nCountdowns update by themselves.", []),
    # 🗺️ CLAN & HELP
    "ch": ("Clan & Help", "🗺️", "home", "## 🗺️ Clan & Help\nClan schedule, questions, suggestions and leader tools.",
           ["clanlife", "ask", "faq", "mod"]),
    "clanlife": ("Clan life", "📅", "ch",
                 "## 📅 Clan life\nTimes show in YOUR time zone. Tap your world zone below.\n"
                 "-# Race + Kraken reminders post in #race-and-event-announcements · `soon who is <name>`",
                 []),
    "ask": ("Ask Soon", "❓", "ch",
            "## ❓ Ask me anything\nHow does something work? What do I type? Where do I go? "
            "Tap **Ask** and type your question. I answer privately. Usually helpfully.",
            []),
    "faq": ("FAQ & suggestions", "🤔", "ch",
            "## 🤔 Questions people actually ask me\n"
            "**Where are my tacos?** Coming soon. That's the brand.\n"
            "**Why is she so mean to me?** You earned it. *Settings → Soon's Mood* fixes it.\n"
            "**Why did she rename me?** I gave you a nickname. *Settings → My profile → 🚫 No nicknames.*\n"
            f"**Why won't she answer me here?** I only really chat in {config.TALK_LINK}.\n"
            "**My phone won't stop buzzing!** *Settings → Pings & alerts.*\n"
            "**I'm out of chips.** Type `broke` in the casino. Nobody gets locked out.\n"
            "**📮 Suggestion box:** ideas, complaints, changes. Tap **Suggestion** below. 🔒 Only Master Foxy and "
            "the mods see it. Or DM me `suggest <idea>`.",
            []),
    "mod": ("Leader tools", "🛠️", "ch",
            "## 🛠️ Leader tools\n"
            "• **Clan:** `soon recruit @name` · `soon alumni @name` · `soon event <name> <time>` · "
            "`kraken date` · `kraken go` · `race bets open/close` · `race winner @name`\n"
            "• **Soon:** `soon says #channel text` · `soon answer @name` · `soon summon regulars [why]` · "
            "`soon takeover complete` · `soon welcome test` · `soon guide post`\n"
            "• **Casino:** `give 50 chips @name` · `spin wheel @name` · `van audit @name` · `soon bank`\n"
            "• **Health:** `soon ai` · `soon budget` · `soon notebook @name` · `soon pardon @name` · "
            "`soon suggestions` · `soon suggestion done 3`",
            []),
    # not in the menu
    "new": ("New here? Start here", "👋", "home",
            "## 👋 New here? 3 quick steps\n"
            "**1.** Tap your world zone: 🦝 Americas · 🦁 Europe & Africa · 🐼 Asia · 🦆 Australia & Oceania\n"
            "**2.** Tap 📝 and tell me your Mob Control name.\n"
            "**3.** Pick what I ping you for (tap again to turn off).\n"
            f"Then come say hi in {config.TALK_LINK}. I bite. Lovingly.",
            ["set", "sf"]),
    "dmbox": ("Suggestion box", "📮", "home", "-# Another one? Tap **Write a suggestion** again.", []),
}
EXTRA_PARENTS = {"mood": ["sf"]}     # pages reachable from 2 menus get a button back to the other one too
DYNAMIC_KEYS = {"profile", "mycasino", "clanlife", "mod"}
# Real buttons on some pages (Shannon: "make buttons for these things vs just explaining them"). Each changes the
# TAPPER's own setting and shows the page again with a ✅ line on top. bot.py sets ACT: async (interaction, act) -> str.
ACT = None        # async (interaction, act, value=None) -> str
DYNAMIC = None    # async (interaction, key) -> str: live info for DYNAMIC_KEYS pages (settings, timers, stats...)
MODALS = {  # act: (form title, field label, placeholder, max length)
    "modal-ign": ("Your in-game name", "In-game name (Mob Control)", "e.g. TacoQueen", 40),
    "modal-tz": ("Where are you?", "City or time zone", "e.g. Amsterdam, Sydney, EST, UTC+10", 60),
    "modal-bday": ("Your birthday", "Month and day", "e.g. March 14", 30),
    "modal-suggest": ("📮 Private suggestion", "Idea, complaint or change", "Only Master Foxy and the mods see this.", 500),
    "modal-ask": ("❓ Ask Soon", "Your question", "e.g. How do I get out of taco debt?", 300),
}
_ALERTS = [("al-casino", "Casino alerts", "🎰"), ("al-race", "Race alerts", "🏁"), ("al-kraken", "Kraken alerts", "🦑"),
           ("al-newbie", "New member alerts", "👋"), ("al-events", "Event alerts", "📅")]
_ZONES = [("zone-raccoon", "Raccoons", "🦝"), ("zone-lion", "Lions", "🦁"), ("zone-panda", "Pandas", "🐼"),
          ("zone-platypus", "Platypus", "🦆")]
ACTIONS = {
    "profile": [("modal-ign", "In-game name", "📝"), ("modal-tz", "Time zone", "🕐"), ("modal-bday", "Birthday", "🎂"),
                ("nick-new", "New nickname", "🎲"), ("nick-stop", "No nicknames", "🚫")] + _ZONES + _ALERTS,
    "mood": [("heat-sweet", "Sweet", "🥰"), ("heat-mild", "Mild", "😇"), ("heat-spicy", "Spicy", "🌶️"),
             ("heat-savage", "Savage", "😈"), ("heat-unhinged", "Unhinged", "🤬"), ("heat-auto", "Auto", "🔄"),
             ("ignore", "Ignore me / talk to me", "🙈"), ("pester", "Random call-outs", "📣"),
             ("go-erase", "Erase Soon's memory of me", "🧠")],
    "erase": [("erase-yes", "Yes, erase it", "🧠")],
    "pings": _ALERTS + [("tags", "My pings", "🔔")],
    "tacos": [("show-btaco", "Taco board", "🌮"), ("show-bbar", "Bar board", "🍹")],
    "eggs": [("show-begg", "Egg board", "🥚"), ("show-basket", "My basket", "🧺")],
    "fun": [("show-fpanda", "Panda facts", "🐼"), ("show-fshame", "Hall of Shame", "🤡"),
            ("show-fgrudge", "Grudges", "😤"), ("show-ffav", "Favorites", "💖")],
    "mycasino": [("show-bcasino", "Casino board", "🎰"), ("show-duel", "Duel record", "⚔️")],
    "clanlife": _ZONES,
    "ask": [("modal-ask", "Ask", "❓")],
    "faq": [("modal-suggest", "Suggestion", "📮")],
    "mod": [("mod-sugg", "Suggestions → my DMs", "📮"), ("mod-ai", "AI health", "🧠"), ("mod-bank", "Bank totals", "🏦"),
            ("mod-summon", "Summon regulars to the diary", "📣")],
    "new": _ZONES + [("modal-ign", "My Mob Control name", "📝")] + _ALERTS,
    "dmbox": [("modal-suggest", "Write a suggestion", "📮")],
}
CMD_RE = re.compile(r"(?i)^\s*soon\s+(?:help|guide|how ?to|what can you do\??|commands)\s*[!?.]*\s*$")
POST_RE = re.compile(r"(?i)^\s*soon\s+guide\s+post\s*$")


def welcome_view() -> discord.ui.View:
    """The 👋 quick start under the #new-members welcome (Shannon): zone, name, alerts + the full guide, all private."""
    v = discord.ui.View(timeout=None)
    for act, label, emoji in ACTIONS["new"]:
        v.add_item(ActionButton("new", act, label, emoji))
    v.add_item(GuideButton("home", label="Soon's full guide"))
    return v


WELCOME_STEPS = ("**👋 Quick start** (tap below, only you see it):\n"
                 "**1.** Your world zone 🦝🦁🐼🦆 · **2.** 📝 your Mob Control name · **3.** what I ping you for\n"
                 "-# 🏠 opens my full guide: settings, timers, casino, everything.")


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
    for other in EXTRA_PARENTS.get(key, []):            # reachable from 2 menus: a way back to the other one too
        v.add_item(GuideButton(other))
    if key not in ("home", "dmbox"):
        v.add_item(GuideButton("home"))
    return v


def text(key: str, guild=None) -> str:
    """{SOON} = her own :soon_smug: emoji (Shannon), 👋 if the server doesn't have it."""
    body = PAGES[key][3].replace("{SOON}", extras.face(guild, "soon_smug", "👋"))
    return body + ("" if key == "dmbox" else FOOT)


async def page_text(interaction, key: str) -> str:
    if key in DYNAMIC_KEYS and DYNAMIC:
        return PAGES[key][3] + "\n" + await DYNAMIC(interaction, key) + FOOT
    return text(key, interaction.guild)


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
    def __init__(self, key: str, back: bool = False, label: str = ""):
        default, emoji, *_ = PAGES.get(key) or ("Private suggestion box (DM)", "📬")
        label = label or default
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
        if self.act == "go-erase":                       # Erase my memory: confirm first
            await show(interaction, "erase")
            return
        if self.act.startswith("show-"):                 # a live board / list on top of this page
            top = await DYNAMIC(interaction, self.act[5:]) if DYNAMIC else ""
            await show(interaction, self.page, top)
            return
        done = await ACT(interaction, self.act) if ACT else "Not now. Try again in a minute."
        await show(interaction, "mood" if self.act == "erase-yes" else self.page, f"✅ {done}")


async def post(channel, reply_to=None):
    kw = dict(view=view("home", dm_button=True), allowed_mentions=discord.AllowedMentions.none())
    body = PAGES["home"][3].replace("{SOON}", extras.face(channel.guild, "soon_smug", "👋")) + f"\n-# Tap a button. Lost later? Type `soon help` in {config.TALK_LINK}."
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
