"""Talking to DeepSeek. One request per reply: Soon's line, how the player treated her, and an optional note for her notebook."""
import json
import random

import httpx

from . import config
from .personality import FALLBACK_LINES, SHEET

TONES = {"nice", "neutral", "rude", "upset"}

INSTRUCTIONS = """Reply with JSON only, in this exact shape:
{"reply": "<what Soon says>", "tone": "nice|neutral|rude|upset", "note": "<optional>"}
- "reply": Soon's message. If BUTT-IN MODE is on and you have nothing genuinely funny and relevant to add, use "".
- "tone": how the player's latest message treated Soon (or others): nice, neutral, rude, or upset (genuinely hurt or sad, not joking).
- "note": one short new fact worth remembering about this player for future roasts (a brag, a nickname, a running joke, a broken promise, a beef). Empty if nothing new. Never store health, family or real-life trauma."""


class Brain:
    def __init__(self, memory):
        self.memory = memory
        self.client = httpx.AsyncClient(timeout=30)

    async def budget_left(self) -> bool:
        spent, _ = await self.memory.month_spend()
        return spent < config.AI_MONTHLY_CAP_USD

    async def think(self, *, player_name: str, player_notes: list[str], heat: str, is_kor: bool,
                    message: str, recent_chat: list[str], butt_in: bool = False, extra: str = "") -> dict:
        """Returns {"reply", "tone", "note", "ok"}. ok=False means a fallback line was used."""
        if not config.DEEPSEEK_API_KEY or not await self.budget_left():
            return self._fallback(butt_in)

        notes = "\n".join(f"- {n}" for n in player_notes[-15:]) or "- (nothing yet)"
        chat = "\n".join(recent_chat[-12:]) or "(quiet)"
        situation = (
            f"PLAYER: {player_name}{' (this is KOR, your crush)' if is_kor else ''}\n"
            f"HEAT LEVEL FOR THIS PLAYER: {heat}\n"
            f"WHAT YOU REMEMBER ABOUT THEM:\n{notes}\n\n"
            f"RECENT CHAT IN THE CHANNEL (oldest first):\n{chat}\n\n"
            f"BUTT-IN MODE: {'ON - nobody asked you, only reply if it is relevant, short and funny' if butt_in else 'off - they are talking to you'}\n"
            f"{extra}\n"
            f"THEIR LATEST MESSAGE: {message}"
        )
        length = random.choices(
            ["ONE short sentence, under 20 words. Punchy.",
             "One or two short sentences, under 35 words.",
             "Up to four sentences. This one can be a little dramatic."],
            weights=[60, 30, 10])[0]
        situation += f"\n\nLENGTH FOR THIS REPLY: {length}"
        body = {
            "model": config.DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": SHEET + "\n\n" + INSTRUCTIONS},
                {"role": "user", "content": situation},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 1.1,
            "max_tokens": 220,
        }
        try:
            r = await self.client.post(
                f"{config.DEEPSEEK_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
                json=body,
            )
            r.raise_for_status()
            data = r.json()
            await self.memory.add_spend(self._cost(data.get("usage", {})))
            out = json.loads(data["choices"][0]["message"]["content"])
        except Exception as e:  # network, budget, bad JSON: never show an error to players
            print(f"AI error: {e!r}")
            return self._fallback(butt_in)

        reply = str(out.get("reply") or "").strip()
        tone = str(out.get("tone") or "neutral").lower()
        if tone not in TONES:
            tone = "neutral"
        note = str(out.get("note") or "").strip()[:200]
        return {"reply": reply[:1900], "tone": tone, "note": note, "ok": True}

    @staticmethod
    def _cost(usage: dict) -> float:
        hit = usage.get("prompt_cache_hit_tokens", 0)
        miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0) - hit)
        out = usage.get("completion_tokens", 0)
        return (hit * config.PRICE_INPUT_HIT + miss * config.PRICE_INPUT_MISS + out * config.PRICE_OUTPUT) / 1_000_000

    @staticmethod
    def _fallback(butt_in: bool) -> dict:
        return {"reply": "" if butt_in else random.choice(FALLBACK_LINES), "tone": "neutral", "note": "", "ok": False}
