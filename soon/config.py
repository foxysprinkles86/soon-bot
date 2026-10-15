"""Settings, all read from Railway's Variables tab. Only the first two are required."""
import os


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip().strip("\"'")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# Backup AI brain (any OpenAI-compatible service; default OpenRouter). Used when DeepSeek doesn't answer within
# PRIMARY_TIMEOUT seconds. Off until BACKUP_API_KEY is set in Railway (Shannon pastes it there herself).
BACKUP_API_KEY = os.environ.get("BACKUP_API_KEY", "").strip().strip("\"'")
BACKUP_BASE_URL = os.environ.get("BACKUP_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
# Comma list, tried in order by OpenRouter (if one host is overloaded, "429", the next one answers).
BACKUP_MODELS = [m.strip() for m in os.environ.get(
    "BACKUP_MODEL", "deepseek/deepseek-chat,deepseek/deepseek-chat-v3-0324,openai/gpt-4o-mini").split(",") if m.strip()]
BACKUP_MODEL = BACKUP_MODELS[0]
PRIMARY_TIMEOUT = float(os.environ.get("PRIMARY_TIMEOUT", "8"))
# DeepSeek's own API quietly scales temperature down (1.1 there behaves like ~0.4); other hosts use it raw, which
# turned the backup's replies into word salad. So the backup gets a calm temperature of its own.
BACKUP_TEMPERATURE = float(os.environ.get("BACKUP_TEMPERATURE", "0.7"))

# Where Soon 2.0 is allowed to talk. Comma-separated channel names (or parts of names).
# Starts locked to the lab so the old Soon keeps running everywhere else.
ALLOWED_CHANNELS = [c.strip().lower() for c in os.environ.get("ALLOWED_CHANNELS", "soon-lab").split(",") if c.strip()]

# Where casino words (claim, chips, cash out...) work. Soon must also be allowed to talk there (ALLOWED_CHANNELS).
CASINO_CHANNELS = [c.strip().lower() for c in os.environ.get("CASINO_CHANNELS", "casa,soon-lab").split(",") if c.strip()]

# Where the taco van / bar / eggs answer (Classic still does everywhere else until cutover; then set this to
# the same list as ALLOWED_CHANNELS).
TACO_CHANNELS = [c.strip().lower() for c in os.environ.get("TACO_CHANNELS", "soon-lab").split(",") if c.strip()]


# New-member welcome (Classic's). Off until cutover night so new people don't get welcomed twice: then WELCOME=1.
WELCOME = os.environ.get("WELCOME", "0").strip() in ("1", "true", "on", "yes")

# Classic's scheduled clan posts (weekly race reminders + the 5-week Kraken schedule) and the Kraken mod commands.
# Off until cutover night (Classic still posts them): then SCHEDULES=1. They ping the clan role below.
SCHEDULES = os.environ.get("SCHEDULES", "0").strip() in ("1", "true", "on", "yes")
CLAN_ROLE_ID = int(os.environ.get("CLAN_ROLE_ID", "1534266078941679736") or 0)

# Casino pictures (animated slot machine, roulette wheel, cards...). OFF until Shannon updates the art (she'll pick
# GIFs or still pictures, not both). GRAPHICS=1 in Railway turns them back on.
GRAPHICS = os.environ.get("GRAPHICS", "0").strip() in ("1", "true", "on", "yes")

# Test channels: casino wins there carry a "testing, chips reset later" note (remove the channel after cutover).
TEST_CHANNELS = [c.strip().lower() for c in os.environ.get("TEST_CHANNELS", "soon-lab").split(",") if c.strip()]

# Monthly AI budget in US dollars. When it runs out, Soon falls back to her written lines.
AI_MONTHLY_CAP_USD = _float("AI_MONTHLY_CAP_USD", 10.0)

# Price per million tokens (DeepSeek V4 Flash list prices, Oct 2026).
PRICE_INPUT_MISS = _float("PRICE_INPUT_MISS", 0.14)
PRICE_INPUT_HIT = _float("PRICE_INPUT_HIT", 0.0028)
PRICE_OUTPUT = _float("PRICE_OUTPUT", 0.28)

# Chance Soon butts into a conversation she isn't part of (0.05 = 1 in 20 eligible messages).
BUTT_IN_CHANCE = _float("BUTT_IN_CHANCE", 0.05)
BUTT_IN_COOLDOWN_SEC = int(_float("BUTT_IN_COOLDOWN_SEC", 600))

# Per-player cap on AI replies.
AI_REPLIES_PER_MINUTE = int(_float("AI_REPLIES_PER_MINUTE", 4))

# Role names that count as mods (any role whose name contains one of these words).
MOD_ROLE_WORDS = [w.strip().lower() for w in os.environ.get("MOD_ROLE_WORDS", "mod,admin,leader").split(",") if w.strip()]

# Where she logs warnings/timeouts (first channel whose name contains this word).
MOD_LOG_CHANNEL = os.environ.get("MOD_LOG_CHANNEL", "mod").strip().lower()
# Shannon, Oct 15: diary, Sunday awards and the Van Daily Report go to #soons-diary; daily pester tags and
# regular summons go to #taco-trash-talk. A channel that can't be found falls back to #soon-lab.
DIARY_CHANNEL = os.environ.get("DIARY_CHANNEL", "diary").strip().lower()
PESTER_CHANNEL = os.environ.get("PESTER_CHANNEL", "trash-talk").strip().lower()
REPORT_CHANNEL = os.environ.get("REPORT_CHANNEL", "").strip().lower() or DIARY_CHANNEL
# New-member welcome: info for the newbie in #new-members, the "say hi with a GIF" call in #get-in-the-van.
WELCOME_CHANNEL = os.environ.get("WELCOME_CHANNEL", "new-members").strip().lower()
HELLO_CHANNEL = os.environ.get("HELLO_CHANNEL", "get-in-the-van").strip().lower()
# Where the recruit panel (Tacos / Outlawz / Joined in game buttons for Taco Wranglers) posts.
RECRUIT_CHANNEL = os.environ.get("RECRUIT_CHANNEL", "glovebox-secrets").strip().lower()
# The two clans' Discord roles (exact names; emojis/punctuation ignored when matching).
TACOS_ROLE = os.environ.get("TACOS_ROLE", "We Have Tacos!").strip()
OUTLAWZ_ROLE = os.environ.get("OUTLAWZ_ROLE", "TX Outlawz").strip()
# Where race/event reminders go. Defaults to the pester channel.
# Race reminders, event reminders and Kraken posts all go to #race-and-event-announcements (Shannon, Oct 15).
RACE_CHANNEL = os.environ.get("RACE_CHANNEL", "").strip().lower() or "race-and-event"
KRAKEN_CHANNEL = os.environ.get("KRAKEN_CHANNEL", "").strip().lower() or RACE_CHANNEL
# Roasts on demand per person per day.
ROASTS_PER_DAY = int(_float("ROASTS_PER_DAY", 3))
# Panda gets tagged at least once a day: part of his Discord username or nickname.
PANDA_NAME = os.environ.get("PANDA_NAME", "panda").strip().lower()
TIMEZONE = os.environ.get("TIMEZONE", "America/Chicago")
DIARY_TIME = os.environ.get("DIARY_TIME", "23:30")  # local time, 24h
# Side-eye reactions: chance per message, and extra emoji codes like <:soon_smug:123> (comma-separated).
REACT_CHANCE = _float("REACT_CHANCE", 0.08)
SOON_EMOJIS = [e.strip() for e in os.environ.get("SOON_EMOJIS", "").split(",") if e.strip()]
