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

Her personality lives in `soon/personality.py`.
