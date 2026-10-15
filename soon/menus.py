"""Casino menus, moved over from Soon Classic and updated for Soon 2.0: `casino` (main menu), `games` (game list),
`payouts` (what everything costs and pays) and a catch-all for "how do I play / get chips / cash out".
Every menu has buttons that work like typing the command. `crimes` stays secret (crimes.py)."""
import re
import time

import discord

from . import buttons
from .casino import C, DANCE, casino_channel, pic

CASINO_RE = re.compile(r"(?i)^\s*(?:casino(?:\s*(?:help|menu))?|help)\s*[!?.]*\s*$")
GAMES_RE = re.compile(r"(?i)^\s*games?(?:\s*menu)?\s*[!?.]*\s*$")
PAYOUTS_RE = re.compile(r"(?i)^\s*(?:payouts?|odds|casino\s*rules)\s*[!?.]*\s*$")
HOWTO_RE = re.compile(r"(?i)\bhow (?:do|can) (?:i|we|you) (?:play|gamble|get (?:more )?chips|cash out)\b")
_last_gif: dict[int, float] = {}


async def handle(message, bank, mod: bool) -> bool:
    if not casino_channel(message.channel):
        return False
    text = message.content.strip()
    in_casa = "casa" in (getattr(message.channel, "name", "") or "").lower()
    if CASINO_RE.match(text):
        if text.strip().lower().startswith("help") and not in_casa:
            return False                         # plain "help" only means the casino inside the casino channel
        await casino_menu(message, bank)
    elif GAMES_RE.match(text):
        await games_menu(message, bank)
    elif PAYOUTS_RE.match(text):
        await payouts(message)
    elif HOWTO_RE.search(text):
        await casino_menu(message, bank)
    else:
        return False
    return True


MAIN_BTNS = (("games", "Games", "🎲", discord.ButtonStyle.primary), ("cashier", "Cashier", "🏦"),
             ("payouts", "Payouts", "📜"), ("casino board", "Board", "🏆"), ("timers", "Timers", "⏰"))


async def casino_menu(message, bank):
    now = time.time()
    if now - _last_gif.get(message.channel.id, 0) > 600:     # the big casino gif at most every 10 minutes
        _last_gif[message.channel.id] = now
        await message.channel.send(embed=pic("casino.gif"))
    await message.channel.send(
        f"{DANCE} **Casa de Soon™** {DANCE}\n## 🎰 Casino & Lounge\nI'm your dealer, cashier and waitress. The house always wins.\n"
        "**⌨️ This is a menu. Type any gray word below and send it (or press a button).** Start with `games`.\n"
        "🎲 `games`: slots, toss, roulette, blackjack, scratch, heists, duels\n"
        "🏦 `cashier`: claim chips, borrow, cash out for tacos\n"
        "📜 `payouts`: what everything costs and pays\n"
        "🏆 `casino board`: high rollers, hall of shame, jackpots\n"
        "⏰ `timers`: your cooldowns\n"
        f"{C} `chips`: your stack\n"
        "-# New here? Type `claim`",
        view=buttons.view(("claim", "Claim chips", "💵", discord.ButtonStyle.success), *MAIN_BTNS[:4]))


async def games_menu(message, bank):
    jack = 2000 + (await bank.get_house(message.guild.id, "jpot", 0) or 0)
    await message.channel.send(
        "## 🎲 Casa de Soon Games\n**⌨️ Type a gray command to play.** Example: type `spin` and send it.\n"
        "🎟️ `scratch`: FREE every 12 hours\n"
        f"🎟️ `buy scratch`: 5 {C} a card\n"
        f"🎰 `spin`: slots, 5 {C} a spin (🌮🌮🌮 jackpot is at **{jack:,}** and growing!)\n"
        f"{C} `toss 20 heads`: double or nothing\n"
        f"{C} `toss 20 heads side`: same, plus a 20x jackpot shot if it lands on its side\n"
        "🎡 `roulette 20 red`: red, black, odd or even\n"
        "🎡 `roulette 5 17`: one number, pays 35:1\n"
        "🃏 `blackjack 20`, then `hit`, `stand` or `double`\n"
        f"🦹 `heist`: pick a **Vault Heist** or a **Grand Heist** (500 {C} each!)\n"
        "⚔️ `duel @name 20`: quick-draw duel. Fastest tap on **DRAW!** wins • type `duel` for how it works\n"
        "🍿 `bet 10 on @name`: bet on someone else's duel\n"
        "🏁 `race bet @name 20`: bet on who scores the most for TnT in the clan race (`race bets` = the book)\n"
        "💝 `tip @name 10`: share the wealth • `tip soon 10`: tip me. I remember generous people.\n"
        "🌧️ `make it rain 50`: throw chips at random gamblers\n"
        "🚐 `kor menu`: VIP perks for one (1) getaway driver\n"
        "-# The amounts above are just examples. Bet whatever you want, up to each game's max. Say `max` to bet the max. "
        "`payouts` shows what everything pays.",
        view=buttons.view(("spin", "Spin", "🎰", discord.ButtonStyle.primary), ("scratch", "Scratch", "🎟️"),
                          ("blackjack 10", "Blackjack 10", "🃏"), ("heist", "Heists", "🦹"), ("duel", "Duels", "⚔️")))


PAYOUTS = f"""**🎰 SLOTS** • 5 {C} a spin
🌮🌮🌮 **Progressive jackpot!** Starts at 2,000, grows +5 every spin until someone hits it (1 in 1,000) • 🦑🦑🦑 **100** • 🍹🍹🍹 **50**
🐷🐷🐷 or 🚀🚀🚀 **40** • 🥑🥑🥑 **25**
Two 🌮 **12** • Any pair **9** • One 🌮 **5** (your chips back)
🌯🌯 Burrito bust: lose 10 • 🌯🌯🌯 lose 30 • one spin every 5 seconds

Say **max** instead of a number to bet the max (toss max heads • blackjack max • roulette max red)

**{C} TACO TOSS** • bet 1–50
Call it right: double your bet • 4% of tosses land on the side (house wins)
Add side (toss 20 heads side): costs half your bet extra • lands on its side = **20x your bet** • max bet 20 with side

**🎡 ROULETTE** • "all on black" works too
Red, black, odd, even: pays 1:1 (max 50)
One number 0–36: pays **35:1** (max 10) • 🟢 0 is the house number

**🃏 BLACKJACK** • bet 1–50
Win pays 1:1 • Blackjack pays **3:2** • Tie gets your bet back
Say double on your first two cards: doubles your bet, one more card, then you stand
Soon stands on 17

**🎟️ SCRATCH-OFF** • FREE every 12 hours • buy scratch: 5 {C} a card
🥑🥑🥑 5 (1 in 4) • 🍹🍹🍹 15 (1 in 10) • 🦑🦑🦑 25 (1 in 25) • 🌮🌮🌮 **100** (1 in 100)

**🦹 HEISTS** • type heist for the heist board • max crew 7 • one heist at a time
Vault Heist: 15 {C} buy-in • pays **35 each** • 40% solo, +10% per crew (max 80%) • 10 min to join • 1 per hour
Grand Heist: 50 {C} buy-in • pays **500 each** • 20% solo, +10% per crew (80% with 7) • 15 min to join • 1 per 8 hours
casino alerts on: get pinged whenever a heist or duel starts (`alerts` = all your alerts)

**⚔️ DUELS** • duel @name 20 (1–100 each) • quick-draw: first tap on **DRAW!** wins, tapping early = misfire • winner takes both
Spectators: bet 5–25 on @name • betting stays open 2 minutes after they accept • 10-second warning, then the channel pauses for the fight • back the winner = double your bet
🎲 Double or Nothing: both fighters press it after the duel → rematch at double stakes, bets reopen at a flat 20
casino alerts on: get pinged whenever a duel starts

**🏁 RACE BETTING** • race bet @name 20 (1–100 per race, one pick each, betting on yourself allowed)
Opens when race pre-join opens, closes when pre-join closes • a mod calls the winner
Winners split the whole pot **+20% house bonus**, by how much they bet • nobody picked the winner = refunds

**🎡 WHEEL OF FORTACO** • surprise!
Any slots, toss, roulette, or blackjack play can randomly trigger a free spin
+5 • +10 • +20 • +40 • **+100** • free scratch card • or I keep it

**💵 CASHIER**
claim: **100 {C} every 12 hours**
cash out: **50 {C} = 1 taco** (max 2 tacos per 12 hours)
buy chips: **1 taco = 40 {C}** (max 3 per 12 hours, taco debt allowed)
timers: see all your cooldowns"""


async def payouts(message):
    await message.channel.send(
        embed=discord.Embed(title="📜 Casa de Soon™ House Rules", description=PAYOUTS, color=16729507),
        view=buttons.view(("games", "Games", "🎲", discord.ButtonStyle.primary), ("cashier", "Cashier", "🏦")))
