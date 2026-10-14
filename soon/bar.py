"""The margarita bar, moved over from Soon Classic. The joke: the van bar actually works. The van kitchen does not.
Any message with marg / margarita / rita serves one (20 flavors, or the one you ask for) and adds to your tab.
1 in 25: you're cut off. Bar ranks with BAR LEVEL UP posts. Loyalty card: every 10th margarita pays off 1 taco of
debt (only if you're in taco debt). Robbing the bartender (tips.py) can get you a 10-minute bar ban."""
import random
import re

from .economy import Bank, casino_day
from .tacovan import taco_channel

MARG_RE = re.compile(r"(?i)\b(?:marg(?:arita)?s?|ritas?)\b")
BAR_RANKS = [(0, "🧃 Sober Sipper"), (10, "🍹 Tipsy"), (25, "🥴 Buzzed"), (50, "💡 Lampshade Wearer"),
             (100, "💃 Dancing on the Van"), (200, "🌵 Honorary Tequila")]
LEVELS = {10, 25, 50, 100, 200}
FLAVORS = ["classic lime", "spicy jalapeño", "strawberry", "mango", "watermelon", "blood orange", "frozen",
           "Kraken ink (it's black, don't ask)", "Piggy pink", "rocket fuel", "Space Race blue raspberry",
           "extra salt, extra sass", "pineapple", "prickly pear", "coconut lime", "peach", "cherry", "passion fruit",
           "cucumber", "guava"]
ASK = [("strawberr", "strawberry"), ("jalape", "spicy jalapeño"), ("spic", "spicy jalapeño"), ("mango", "mango"),
       ("watermelon", "watermelon"), ("melon", "watermelon"), ("blood orange", "blood orange"), ("orange", "blood orange"),
       ("frozen", "frozen"), ("kraken", "Kraken ink (it's black, don't ask)"), ("pig", "Piggy pink"), ("pink", "Piggy pink"),
       ("rocket", "rocket fuel"), ("fuel", "rocket fuel"), ("blue", "Space Race blue raspberry"),
       ("raspberr", "Space Race blue raspberry"), ("space", "Space Race blue raspberry"), ("salt", "extra salt, extra sass"),
       ("sass", "extra salt, extra sass"), ("pineapple", "pineapple"), ("prickly", "prickly pear"), ("pear", "prickly pear"),
       ("cactus", "prickly pear"), ("coconut", "coconut lime"), ("peach", "peach"), ("cherr", "cherry"),
       ("passion", "passion fruit"), ("cucumber", "cucumber"), ("guava", "guava"), ("lime", "classic lime"),
       ("classic", "classic lime")]
LINES = [
    "Unlike the tacos, this actually showed up. Don't get used to it.",
    "The bar runs on time. The kitchen runs on 'soon.' Different management.",
    "Drink up. It makes your Piggy score look better.", "Salt on the rim, shade on the side.",
    "Sip slow. The tacos aren't coming any faster.", "Bartender says you look like you need this. Bartender saw your race score.",
    "Served. Tip your bartender in Piggy lines.", "This one's on Foxy. Foxy doesn't know that yet.",
    "Kor already drank half of it. You're welcome.", "Cheers to another week of not getting tacos. 🥂",
    "Margaritas: delivered. Tacos: coming soon. Your dignity: gone.", "Don't drink and race. Actually, go ahead. Can't get worse.",
    "The van has a fully stocked bar. Priorities.", "Shaken, not stirred, and definitely not paired with a taco.",
    "Your excuses for skipping races are still not accepted. Enjoy.",
    "Fresh from the van bar. The van kitchen remains closed. Forever.", "This marg has better aim than your cannon.",
    "Drink responsibly. Race irresponsibly.", "One marg closer to forgetting the tacos never came.",
    "Lime, tequila, and the faint taste of a taco that never arrived."]
CUT_OFF = ["🚫 You've been cut off. Not because you're drunk. Because your race score is embarrassing.",
           "🚫 Bartender says no. Go finish a race and come back.", "🚫 Cut off. Kor drank the rest anyway.",
           "🚫 Last call was 10 minutes ago. Much like your last good race."]


def bar_rank(n: int) -> str:
    return [r for need, r in BAR_RANKS if n >= need][-1]


async def handle(message, bank: Bank, mod: bool, quiet: bool = False) -> bool:
    """quiet=True: a long chat with Soon that just mentions margaritas. Count nothing, let her answer."""
    if not taco_channel(message.channel):
        return False
    text = message.content or ""
    if not MARG_RE.search(text) or re.search(r"(?i)\bbar ?board\b", text):
        return False
    if quiet and len(text.split()) > 12:
        return False
    await serve(message, bank)
    return True


async def serve(message, bank: Bank):
    gid, uid, u = message.guild.id, message.author.id, message.author.mention
    ban = await bank.timer(gid, uid, "barban")
    if ban:
        await message.channel.send(f"🚫 {u} " + random.choice([
            "You're banned from the bar. Nice try.", "No. You robbed my bartender. The bartender is me. I remember.",
            "Banned means banned. Have a water. Room temperature."]) + f" Ban lifts <t:{int(ban[0].timestamp())}:R>.")
        return
    w = await bank.add(gid, uid, "margarita", margs=1)
    c = w.margs
    day = await bank.get_house(gid, f"margday:{casino_day()}", {}) or {}
    day[str(uid)] = day.get(str(uid), 0) + 1                       # for the Van Daily Report
    await bank.set_house(gid, f"margday:{casino_day()}", day)
    rank = bar_rank(c)
    out = []
    if random.randrange(25) == 0:
        out.append(f"{u} {random.choice(CUT_OFF)}")
    else:
        low = (message.content or "").lower()
        asked = next((flavor for key, flavor in ASK if key in low), None)
        pick = asked or random.choice(FLAVORS)
        out.append(f"{u} 🍹 **One {pick} margarita, served!**\n{random.choice(LINES)}\n"
                   f"-# {'Custom order honored. Taco orders remain on hold. • ' if asked else ''}{rank} • "
                   f"Tab: {c} margaritas • Tacos: {w.tacobal}")
    if c in LEVELS:
        out.append(f"🎉 **BAR LEVEL UP!** {u} is now **{rank}**! The bartender is impressed. "
                   "The kitchen still hasn't noticed you exist. 🎉")
    if c % 10 == 0 and w.tacobal < 0:
        w = await bank.add(gid, uid, "margarita loyalty card", tacobal=1)
        out.append(f"🎟️ **LOYALTY CARD FULL!** {u}, every 10th margarita pays off 1 taco of debt. Tacos: {w.tacobal} 🌮")
    await message.channel.send("\n".join(out))
