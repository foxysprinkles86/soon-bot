# Soon 2.0 🌮

The TnT clan's sarcastic taco bot, self-hosted on Railway with an AI brain (DeepSeek).

## What v0.1 does
- Talks back with AI when someone @mentions her, replies to her, or starts a message with "soon".
- Keeps a notebook on every player: notes she writes herself, plus a mood score (-5 enemy to +5 favorite).
- Mood sets each player's heat level: sweet, mild, spicy (default), savage, unhinged.
- Rarely butts into conversations when she has something relevant and funny to say.
- Falls back to written lines if the AI is down or the monthly budget runs out.
- Only talks in channels whose names match `ALLOWED_CHANNELS` (starts as `soon-lab`).

## Commands
| Command | Who | What |
| --- | --- | --- |
| `soon ping` | anyone | Check she's awake |
| `soon heat` | anyone | Show your heat level |
| `soon heat sweet/mild/spicy/savage/unhinged` | anyone | Lock your heat level |
| `soon heat auto` | anyone | Unlock it (earn it again) |
| `soon be nice` | anyone | Lock at mild |
| `soon leave me alone` / `soon bother me` | anyone | Turn pestering off/on |
| `soon notebook @name` | mods | See a player's page |
| `soon forget @name` | mods | Wipe a player's page |
| `soon unnote @name 3 5` | mods | Erase specific notes by number |
| `soon budget` | mods | AI spend this month |
| `soon my name is <in-game name>` | anyone | Link your in-game name |
| `soon who is <in-game name>` / `soon ign @name` | anyone | Look up who's who |
| `soon grudges` / `soon favorites` | anyone | Her current grudge and favorites lists |
| `soon mood` | anyone | Her mood of the day |
| `soon pardon @name` | mods | Wipe someone's strikes and lift their timeout |
| `soon my timezone is <zone/city>` | anyone | Tell her where you live |
| `soon my birthday is <month day>` | anyone | Birthday shout-out every year |
| `soon duel @name` | anyone | Quick-draw duel (bragging rights) |
| `soon duel record` / `soon duel record @name` | anyone | Win-loss record |
| `soon takeover` | mods | Takeover storyline (`stage 1-4` / `restart` / `complete`) |
| `soon roast @name` / `soon roast me` | anyone | Roast on demand (3 a day each) |
| `soon panda facts` | anyone | The Verified Panda Facts™ archive |
| `soon hall of shame` / `soon shame @name` | anyone | What Soon framed (she picks, max 2 a day) |
| `soon events` | anyone | Upcoming race reminders |
| `soon event <name + day + time>` | mods | Add one, e.g. `soon event Kraken starts Saturday 2pm every week` |
| `soon event remove <name>` | mods | Delete one |

## Daily life
- **Mood of the day** flavors every reply.
- **Side-eye reactions** on ~8% of messages.
- **Panda** gets tagged once a day (afternoon/evening), plus one random regular gets summoned (Kor twice as likely).
- **Soon's Diary** posts nightly at 11:30 PM Central.
- **Weekly Soon Awards** post Sundays at 7 PM Central. **Mod report** (what confused people, who talks to her, AI spend) Mondays at 9 AM in the mod channel.
- **Join anniversaries, birthdays, and 1-week recruit check-ins** around noon.
- **Race reminders** an hour before each event (from the server's Discord Events tab, including recurring ones, plus any added with `soon event`) (roasting whichever zone will be asleep). Kraken reminders include the collect-your-tickets tip.
- **Hall of Shame**: Soon alone decides. While skimming chat she picks the truly iconic self-owns (max 2 a day), reacts 🤡 and frames them. Shame quotes feed her diary and the weekly awards.
- **Panda facts** she invents get saved, and she quotes them back as established truth.
- **Help desk**: she knows every casino/clan command and tells confused players exactly what to type.
- **Hard lines**: slurs or attacks on protected traits/real trauma toward another person get called out. Strike 1 = warning, then 10 min, 1 hour, 24 hour timeouts. Logged to the first channel with "mod" in its name. Strikes reset after 7 clean days.

## Railway variables
| Variable | Required | Notes |
| --- | --- | --- |
| `DISCORD_TOKEN` | yes | Bot token from the Discord Developer Portal |
| `DEEPSEEK_API_KEY` | yes | From platform.deepseek.com |
| `DATABASE_URL` | yes | Reference the Postgres service: `${{Postgres.DATABASE_URL}}` |
| `ALLOWED_CHANNELS` | no | Default `soon-lab`. Comma-separated channel names. |
| `AI_MONTHLY_CAP_USD` | no | Default `10` |
| `DEEPSEEK_MODEL` | no | Default `deepseek-chat` |
| `BUTT_IN_CHANCE` | no | Default `0.05` |
| `DIARY_CHANNEL` / `PESTER_CHANNEL` | no | Default `soon-lab` |
| `MOD_LOG_CHANNEL` | no | Default `mod` |
| `PANDA_NAME` | no | Part of Panda's Discord name. Default `panda` |
| `DIARY_TIME` | no | Default `23:30` (Central) |
| `RACE_CHANNEL` | no | Where race reminders go. Default: same as `PESTER_CHANNEL` |
| `ROASTS_PER_DAY` | no | Default `3` |
| `SOON_EMOJIS` | no | Extra custom emoji codes for reactions, comma-separated |

Her personality lives in `soon/personality.py`.
