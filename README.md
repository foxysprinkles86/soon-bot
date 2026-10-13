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
| `soon budget` | mods | AI spend this month |
| `soon my name is <in-game name>` | anyone | Link your in-game name |
| `soon who is <in-game name>` / `soon ign @name` | anyone | Look up who's who |
| `soon grudges` / `soon favorites` | anyone | Her current grudge and favorites lists |
| `soon mood` | anyone | Her mood of the day |
| `soon pardon @name` | mods | Wipe someone's strikes and lift their timeout |

## Daily life
- **Mood of the day** flavors every reply.
- **Side-eye reactions** on ~8% of messages.
- **Panda** gets tagged once a day (afternoon/evening), plus one random regular gets summoned (Kor twice as likely).
- **Soon's Diary** posts nightly at 11:30 PM Central.
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
| `SOON_EMOJIS` | no | Extra custom emoji codes for reactions, comma-separated |

Her personality lives in `soon/personality.py`.
