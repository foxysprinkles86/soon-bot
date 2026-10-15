"""Classic's scheduled clan posts (#05 Race Reminders, #17 Kraken Schedule, #18 Kraken Commands).

Race reminders (UTC, same as Classic): midweek pre-join opens Tue 07:00, 2h left to pre-join Wed 05:00,
2h left in the race Fri 05:00; weekend pre-join opens Thu 21:00, 2h left to pre-join Fri 19:00, 2h left Sun 19:00;
10-minute warnings before Wed 07:00 and Fri 21:00. Posted in RACE_CHANNEL with the clan role ping.

Kraken (every 5 weeks; the boss ends on a Sunday 18:30 UTC): Day 1-6 missions open (banner + ticket count),
2-hour last calls, Day 7 final missions + "DO NOT ATTACK YET", boss over + rewards. Posted in #kraken-clash.
Mods: `kraken` / `kraken date` (schedule), `kraken date 2026-11-15 [cst]` (new boss-end Sunday),
`kraken go [note]` (ATTACK post), `kraken test` (all images + a sample, no ping).

OFF until cutover (Classic still posts these): set SCHEDULES=1 in Railway on cutover night. Until then the Kraken
commands only answer in the test channel and never ping."""
import datetime as dt
import re

import discord

from . import alerts, config, racebets
from .casino import IMG
from .economy import Bank

DAY, PERIOD = 86400, 35 * 86400
ANCHOR = 1791743400              # Classic's default boss-end time (a Sunday 18:30 UTC); `kraken date` changes it
KRAKEN_CHANNEL = "kraken-clash"
PINK, RED, GOLD = 0xFF45A3, 0xFF0000, 0xFFD700
KRAKEN_RE = re.compile(r"(?i)^\s*kraken\s+(go|date|test)\b(.*)$", re.S)

RACES = [  # (weekday 0=Mon, UTC hour, headline, line)
    (1, 7, "🏁 Midweek race pre-join is OPEN!", "Get in now. Unlike tacos, races actually show up."),
    (2, 5, "⏰ 2 hours left to pre-join the midweek race!", "Miss it and don't come crying to Soon. Soon is busy not making tacos."),
    (4, 5, "🔥 2 hours left in the midweek race!", "Last chance to save your dignity. Your score is watching."),
    (3, 21, "🐷 Weekend race pre-join is OPEN!", "Hop in the van. The race is real. The tacos are not."),
    (4, 19, "⏰ 2 hours left to pre-join the weekend race!", "Move faster than our taco delivery. Low bar. Clear it."),
    (6, 19, "🔥 2 hours left in the weekend race!", "Unlike tacos, this deadline is real. GO."),
]
STARTS = [  # 10-minute warnings: (weekday, UTC hour the race starts, headline, line)
    (2, 7, "🏁 The midweek race starts in 10 MINUTES!", "Warm up those thumbs. Tacos for the winner. (Soon™.)"),
    (4, 21, "🏁 The weekend race starts in 10 MINUTES!", "Get ready to smash it. Foxy is watching. Foxy is always watching."),
]


async def _ping(guild, cat: str) -> tuple[str, discord.AllowedMentions]:
    """The Race Alerts / Kraken Alerts role (alerts.py); the clan role if Soon can't make alert roles."""
    role = await alerts.role(guild, cat)
    if not role and config.CLAN_ROLE_ID:
        role = guild.get_role(config.CLAN_ROLE_ID)
    if not role:
        return "", discord.AllowedMentions.none()
    return role.mention + "\n", discord.AllowedMentions(roles=[role], users=False, everyone=False)


def _channel(guild, word: str):
    return next((c for c in guild.text_channels if word in c.name.lower()), None)


def race_due(t: dt.datetime) -> tuple[str, str] | None:
    if t.minute < 10:
        for wd, h, head, line in RACES:
            if t.weekday() == wd and t.hour == h:
                return head, line
    w = t + dt.timedelta(minutes=10)
    if w.minute < 5:
        for wd, h, head, line in STARTS:
            if w.weekday() == wd and w.hour == h:
                return head, line
    return None


async def races(guild, bank: Bank, t: dt.datetime | None = None):
    t = t or dt.datetime.now(dt.timezone.utc)
    due = race_due(t)
    if not due:
        return
    key = t.strftime("%Y-%m-%d-%H")
    if await bank.get_house(guild.id, "racepost") == key:
        return
    ch = _channel(guild, config.RACE_CHANNEL)
    if not ch:
        return
    await bank.set_house(guild.id, "racepost", key)
    ping, allowed = await _ping(guild, "race")
    extra = ""
    if "pre-join is OPEN" in due[0]:
        extra = "\n🎲 Race betting is open in the casino: `race bet @name 20` on who scores the most for TnT."
    elif "starts in 10" in due[0]:
        extra = "\n🎲 Last call for race bets: betting closes when pre-join closes."
    await ch.send(f"{ping}# {due[0]}\n{due[1]}{extra}", allowed_mentions=allowed)


async def boss_end(bank: Bank, gid: int, now: int) -> int:
    """The next boss-end time (keeps the current one for 15 minutes after it passes)."""
    e = int(await bank.get_house(gid, "krakenanchor", ANCHOR) or ANCHOR)
    while e < now - 900:
        e += PERIOD
    return e


def kraken_event(e: int, now: int):
    """(kind, day number, time) if a Kraken post is due in the 10 minutes after `time`, else None."""
    for i in range(1, 8):
        opens = e - (8 - i) * DAY
        call = e - (7 - i) * DAY - 7200
        if opens <= now < opens + 600:
            return "open", i, opens
        if call <= now < call + 600:
            return "call", i, call
    if e <= now < e + 600:
        return "end", 0, e
    return None


def banner(name: str, color=PINK) -> discord.Embed:
    return discord.Embed(color=color).set_image(url=IMG + name)


def kraken_post(kind: str, n: int, t: int, e: int) -> tuple[discord.Embed | None, str]:
    boss = e - DAY
    if kind == "open":
        exp = t + DAY
        if n < 7:
            return (banner(f"Kraken%20Clash%20Missions%20Day%20{n}%20Banner.png"),
                    f"# 🦑 Kraken Day {n} missions are OPEN!\n🎟️ Complete today's clan missions and collect your tickets. "
                    f"Up to date = **{n * 8}** tickets after collecting.\n⏳ Today's tickets expire <t:{exp}:R> (<t:{exp}:t>)\n"
                    f"⚔️ Boss battle opens <t:{boss}:R>")
        return (banner("Kraken%20Day%207%20WAIT%20for%20Battle%20Plan.png"),
                "# 🦑 FINAL missions + Kraken battle are OPEN!\n🎟️ Collect your last 8 tickets. Up to date = **56** tickets.\n"
                "## 🛑 DO NOT ATTACK YET!\nWait for Foxy's battle plan and the go-ahead. It's coming soon. "
                f"(A real soon, not a taco soon.)\n⏳ Final tickets + boss fight end <t:{e}:R> (<t:{e}:f>)")
    if kind == "call":
        exp = t + 7200
        if n < 7:
            return (None, f"# ⏰ LAST CALL: Day {n} Kraken tickets!\nMissions refresh <t:{exp}:R>. "
                          f"**Uncollected tickets are LOST.**\n🎟️ Up to date = **{n * 8}** tickets.")
        return (None, f"# ⏰ LAST CALL: 2 HOURS LEFT!\nFinal tickets AND the Kraken fight end <t:{exp}:R>. "
                      "Collect your tickets and get your hits in!")
    nxt = e + PERIOD - 7 * DAY
    return (banner("kraken-rewards.jpg", GOLD),
            "# 🏆 Kraken Clash is OVER!\nGo claim your rewards before the season closes. **Unclaimed rewards will be lost!**\n"
            f"-# Next Kraken missions start <t:{nxt}:D>")


async def kraken(guild, bank: Bank, now: int | None = None):
    now = now or int(dt.datetime.now(dt.timezone.utc).timestamp())
    e = await boss_end(bank, guild.id, now)
    ev = kraken_event(e, now)
    if not ev:
        return
    kind, n, t = ev
    if int(await bank.get_house(guild.id, "krakenlast", 0) or 0) == t:
        return
    ch = _channel(guild, KRAKEN_CHANNEL)
    if not ch:
        return
    await bank.set_house(guild.id, "krakenlast", t)
    embed, text = kraken_post(kind, n, t, e)
    ping, allowed = await _ping(guild, "kraken")
    if embed:
        await ch.send(embed=embed)
    await ch.send(ping + text, allowed_mentions=allowed)


BOOK_OPENS = [(1, 7, "Midweek"), (3, 21, "Weekend")]      # same time as the pre-join OPEN reminders (UTC)
BOOK_CLOSES = [(2, 7), (4, 21)]                          # pre-join closes = the race starts


def _casino_channel(guild):
    """Where race-bet news goes: the first casino channel Soon is allowed to talk in."""
    return next((c for c in guild.text_channels if any(w in c.name.lower() for w in config.CASINO_CHANNELS)
                 and any(w in c.name.lower() for w in config.ALLOWED_CHANNELS)), None)


async def race_book(guild, bank: Bank, t: dt.datetime | None = None):
    """Race betting opens and closes by itself with pre-join (runs even before cutover, unlike the reminders)."""
    t = t or dt.datetime.now(dt.timezone.utc)
    if t.minute >= 10:
        return
    key = t.strftime("%Y-%m-%d-%H")
    opening = next((lab for wd, h, lab in BOOK_OPENS if t.weekday() == wd and t.hour == h), None)
    closing = any(t.weekday() == wd and t.hour == h for wd, h in BOOK_CLOSES)
    if not (opening or closing) or await bank.get_house(guild.id, "racebookpost") == key:
        return
    await bank.set_house(guild.id, "racebookpost", key)
    ch = _casino_channel(guild)
    ping, allowed = (await _ping(guild, "race")) if config.SCHEDULES else ("", discord.AllowedMentions.none())
    if opening and await racebets.open_book(bank, guild.id, opening):
        if ch:
            await ch.send(f"{ping}# 🏁 {opening} race betting is OPEN!\nPre-join just opened. Who's going to score the most for "
                          "TnT? `race bet @name 20` (up to 100 chips).\n-# Betting closes when pre-join closes. "
                          "Betting on yourself is allowed.", view=racebets._view(), allowed_mentions=allowed)
    elif closing and await racebets.close_book(bank, guild.id) and ch:
        await ch.send(f"{ping}# 🔒 Race betting is CLOSED!\nPre-join is over and the race is on. A mod will call the winner "
                      "after the race with `race winner @name`.", view=racebets._view(), allowed_mentions=allowed)


async def tick(guild, bank: Bank):
    """Called every minute from bot.py's daily loop."""
    await race_book(guild, bank)
    if not config.SCHEDULES:
        return
    await races(guild, bank)
    await kraken(guild, bank)


async def command(message, bank: Bank, mod: bool) -> bool:
    """Mods: kraken / kraken date [YYYY-MM-DD [cst]] / kraken go [note] / kraken test."""
    m = KRAKEN_RE.match(message.content or "")
    if not m or not mod:
        return False
    test_ch = any(w in (message.channel.name or "").lower() for w in config.TEST_CHANNELS)
    if not config.SCHEDULES and not test_ch:
        return False                    # Classic still handles Kraken commands until cutover
    live = config.SCHEDULES             # never ping the clan from a test run
    word, rest = m.group(1).lower(), m.group(2).strip()
    gid, now = message.guild.id, int(dt.datetime.now(dt.timezone.utc).timestamp())
    if word == "date" and re.match(r"\d{4}-\d{1,2}-\d{1,2}", rest):
        y, mo, d = (int(x) for x in re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", rest).groups())
        hour = 19 if re.search(r"(?i)\bcst\b", rest) else 18
        a = int(dt.datetime(y, mo, d, hour, 30, tzinfo=dt.timezone.utc).timestamp())
        await bank.set_house(gid, "krakenanchor", a)
        await message.channel.send(f"✅ Kraken schedule updated. Boss ends <t:{a}:F>, then every 5 weeks after.\n"
                                   f"-# Missions start <t:{a - 7 * DAY}:F> • Boss opens <t:{a - DAY}:F>")
        return True
    e = await boss_end(bank, gid, now)
    if word == "test":
        embeds = [discord.Embed(title=f"Day {i}").set_image(url=IMG + f"Kraken%20Clash%20Missions%20Day%20{i}%20Banner.png")
                  for i in range(1, 7)]
        embeds += [discord.Embed(title="Day 7: WAIT").set_image(url=IMG + "Kraken%20Day%207%20WAIT%20for%20Battle%20Plan.png"),
                   discord.Embed(title="kraken go: ATTACK").set_image(url=IMG + "Kraken%20Day%207%20ATTACK%20KRAKEN.png"),
                   discord.Embed(title="Boss over: REWARDS").set_image(url=IMG + "kraken-rewards.jpg")]
        await message.channel.send("🧪 **Kraken image test.** You should see 9 pictures below. Any blank one = broken link.",
                                   embeds=embeds)
        _, sample = kraken_post("open", 5, e - 2 * DAY - DAY, e)
        await message.channel.send("🧪 **Sample post (no ping):**\n@Kraken Alerts\n" + sample)
        return True
    if word == "go":
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        ping, allowed = await _ping(message.guild, "kraken") if live else ("", discord.AllowedMentions.none())
        await message.channel.send(embed=banner("Kraken%20Day%207%20ATTACK%20KRAKEN.png", RED))
        await message.channel.send(ping + "# ⚔️ ATTACK THE KRAKEN!\nThe battle plan is GO. Hit Krill McKraken with "
                                   "everything you've got! 🦑💥\n" + (f"📋 {rest}\n" if rest else "")
                                   + f"⏳ Boss fight ends <t:{e}:R> (<t:{e}:f>)", allowed_mentions=allowed)
        return True
    await message.channel.send(f"### 🦑 Kraken schedule\nMissions start: <t:{e - 7 * DAY}:F>\nBoss opens: <t:{e - DAY}:F>\n"
                               f"Boss ends: <t:{e}:F> (<t:{e}:R>)\n-# Repeats every 5 weeks. Change with: kraken date YYYY-MM-DD")
    return True
