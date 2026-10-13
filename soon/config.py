"""Settings, all read from Railway's Variables tab. Only the first two are required."""
import os


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# Where Soon 2.0 is allowed to talk. Comma-separated channel names (or parts of names).
# Starts locked to the lab so the old Soon keeps running everywhere else.
ALLOWED_CHANNELS = [c.strip().lower() for c in os.environ.get("ALLOWED_CHANNELS", "soon-lab").split(",") if c.strip()]

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
