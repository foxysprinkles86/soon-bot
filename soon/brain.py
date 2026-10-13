"""Talking to DeepSeek. One request per reply: Soon's line, how the player treated her, and an optional note for her notebook."""
import json
import random
import re

import httpx

from . import config
from .personality import FALLBACK_LINES, SHEET

TONES = {"nice", "neutral", "rude", "upset"}

INSTRUCTIONS = """Reply with JSON only, in this exact shape:
{"reply": "<what Soon says>", "tone": "nice|neutral|rude|upset", "note": "<optional>", "line_crossed": false, "timezone": "", "struggle": "", "panda_fact": ""}
- "reply": Soon's message. If BUTT-IN MODE is on and you have nothing genuinely funny and relevant to add, use "".
- "tone": how the player's latest message treated Soon (or others): nice, neutral, rude, or upset (genuinely hurt or sad, not joking).
- "note": one short NEW fact worth remembering about this player for future roasts (a brag, a nickname, a running joke, a broken promise, a beef). It must not repeat or rephrase anything already in WHAT YOU REMEMBER. Usually empty: most messages don't need a note. Never store health, family or real-life trauma.
- "line_crossed": true ONLY if the player's latest message attacks ANOTHER PERSON with a slur, or attacks them over race, religion, sexuality, gender or disability, or mocks real-life trauma or health someone shared. Swearing, trash talk, roasting game scores and insulting Soon are all fine and are false. When true, your reply should call it out in character.
- "timezone": if the player's latest message tells you where they live or their time zone (a city, country, "EST", "UTC+10"...), the IANA time zone name, like "America/New_York" or "Australia/Sydney". Otherwise "".
- "struggle": if the player is confused or a command isn't working for them, a few words on what they were trying to do (for the mods' weekly report). Otherwise "".
- "panda_fact": ONLY if your reply states a NEW made-up fact about Panda, that fact in a few words (like "banned from three Applebee's"). Otherwise ""."""


def trim_sentences(text: str, limit: int) -> str:
    """Hard cap on reply length: keep the first `limit` sentences (she gets carried away)."""
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'*(])", text)
    parts, buf = [], ""
    for piece in raw:                      # "Into you? Please. As if." counts as ONE sentence, not three
        buf = f"{buf} {piece}".strip()
        if len(buf.split()) >= 6:
            parts.append(buf)
            buf = ""
    if buf:
        if parts:
            parts[-1] += " " + buf
        else:
            parts.append(buf)
    if len(parts) <= limit:
        return text
    return " ".join(parts[:limit]).strip()


class Brain:
    def __init__(self, memory):
        self.memory = memory
        self.client = httpx.AsyncClient(timeout=30)

    async def budget_left(self) -> bool:
        spent, _ = await self.memory.month_spend()
        return spent < config.AI_MONTHLY_CAP_USD

    async def think(self, *, player_name: str, player_notes: list[str], heat: str, is_kor: bool,
                    message: str, recent_chat: list[str], butt_in: bool = False, maybe: bool = False, extra: str = "",
                    length_weights: list[int] | None = None) -> dict:
        """Returns {"reply", "tone", "note", "ok"}. ok=False means a fallback line was used."""
        if not config.DEEPSEEK_API_KEY or not await self.budget_left():
            return self._fallback(butt_in or maybe)

        if butt_in:
            mode = "BUTT-IN - nobody asked you. Only reply if you have something relevant, short and funny. Otherwise reply \"\"."
        elif maybe:
            mode = ("MAYBE - they might be talking to you (they said your name, or they're continuing a chat with you). "
                    "Reply only if the message is meant for you; if they're clearly talking to someone else or just saying "
                    "'coming soon', reply \"\".")
        else:
            mode = "DIRECT - they are talking to you. Always reply."
        notes = "\n".join(f"- {n}" for n in player_notes[-15:]) or "- (nothing yet)"
        chat = "\n".join(recent_chat[-30:]) or "(quiet)"
        situation = (
            f"PLAYER: {player_name}{' (this is KOR, your crush)' if is_kor else ''}\n"
            f"HEAT LEVEL FOR THIS PLAYER: {heat}\n"
            f"WHAT YOU REMEMBER ABOUT THEM:\n{notes}\n\n"
            f"RECENT CHAT IN THE CHANNEL (oldest first):\n{chat}\n\n"
            f"MODE: {mode}\n"
            f"{extra}\n"
            f"THEIR LATEST MESSAGE: {message}"
        )
        length, max_sentences = random.choices(
            [("ONE short sentence, under 20 words. Punchy.", 1),
             ("One or two short sentences, under 35 words.", 2),
             ("Up to four sentences. This one can be a little dramatic.", 4)],
            weights=length_weights or [75, 19, 6])[0]
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
            return self._fallback(butt_in or maybe)

        reply = trim_sentences(str(out.get("reply") or "").strip(), max_sentences)
        tone = str(out.get("tone") or "neutral").lower()
        if tone not in TONES:
            tone = "neutral"
        note = str(out.get("note") or "").strip()[:200]
        crossed = out.get("line_crossed") is True
        tz = str(out.get("timezone") or "").strip()
        struggle = str(out.get("struggle") or "").strip()[:150]
        panda_fact = str(out.get("panda_fact") or "").strip()[:160]
        return {"reply": reply[:1900], "tone": tone, "note": note, "line_crossed": crossed, "timezone": tz,
                "struggle": struggle, "panda_fact": panda_fact, "ok": True}

    async def write(self, task: str, max_tokens: int = 350) -> str:
        """Free-form writing in Soon's voice (diary entries, pestering, announcements). '' if unavailable."""
        if not config.DEEPSEEK_API_KEY or not await self.budget_left():
            return ""
        body = {
            "model": config.DEEPSEEK_MODEL,
            "messages": [{"role": "system", "content": SHEET}, {"role": "user", "content": task}],
            "temperature": 1.1,
            "max_tokens": max_tokens,
        }
        try:
            r = await self.client.post(f"{config.DEEPSEEK_BASE_URL}/chat/completions",
                                       headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"}, json=body)
            r.raise_for_status()
            data = r.json()
            await self.memory.add_spend(self._cost(data.get("usage", {})))
            return data["choices"][0]["message"]["content"].strip()[:1900]
        except Exception as e:
            print(f"Write error: {e!r}")
            return ""

    async def extract_notes(self, chat_lines: list[str], names: list[str]):
        """Eavesdropping: read a chunk of regular chat.
        Returns (notes per player, hard-line violations by line number, Hall of Shame picks by line number)."""
        if not config.DEEPSEEK_API_KEY or not await self.budget_left() or not chat_lines:
            return [], [], []
        body = {
            "model": config.DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": (
                    "You are Soon's memory. Read this Discord chat from a Mob Control clan and pull out facts worth "
                    "remembering for future roasts or banter: brags, scores, nicknames, running jokes, promises, beefs, "
                    "game milestones, what they're bad at. Skip boring small talk. Never store health, family, money "
                    "trouble or real-life trauma. Also flag hard-line violations: a line that attacks ANOTHER PERSON with a slur, or over "
                    "race, religion, sexuality, gender or disability, or mocks real trauma or health someone shared. Swearing, "
                    "trash talk and game roasts are NOT violations. Return JSON: {\"notes\": [{\"player\": \"<exact name>\", "
                    "\"note\": \"<short fact>\"}], \"violations\": [{\"line\": <line number>, \"why\": \"<short>\"}], "
                    "\"shame\": [{\"line\": <line number>, \"why\": \"<short>\"}]}. "
                    "\"shame\" is for the Hall of Shame: at most ONE line, and only if it's truly iconic and embarrassing in a "
                    "funny, game-related way (a cocky brag right before losing, a hilariously bad score, a 'trust me I never miss', "
                    "a spectacular self-own). Usually empty. Never pick anything about real life, health, family, or anything sad. "
                    "Use only these player names: " + ", ".join(names) + ". At most 6 notes. Empty lists if nothing.")},
                {"role": "user", "content": "\n".join(f"{i}. {l}" for i, l in enumerate(chat_lines))},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
            "max_tokens": 300,
        }
        try:
            r = await self.client.post(f"{config.DEEPSEEK_BASE_URL}/chat/completions",
                                       headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"}, json=body)
            r.raise_for_status()
            data = r.json()
            await self.memory.add_spend(self._cost(data.get("usage", {})))
            out = json.loads(data["choices"][0]["message"]["content"])
            notes = [(str(n.get("player", "")), str(n.get("note", ""))[:200])
                     for n in out.get("notes", []) if n.get("player") and n.get("note")]
            bad = []
            for v in out.get("violations", []) or []:
                try:
                    bad.append((int(v.get("line")), str(v.get("why", ""))[:200]))
                except (TypeError, ValueError):
                    pass
            shame = []
            for v in (out.get("shame") or [])[:1]:
                try:
                    shame.append((int(v.get("line")), str(v.get("why", ""))[:150]))
                except (TypeError, ValueError, AttributeError):
                    pass
            return notes, bad, shame
        except Exception as e:
            print(f"Notes error: {e!r}")
            return [], [], []

    @staticmethod
    def _cost(usage: dict) -> float:
        hit = usage.get("prompt_cache_hit_tokens", 0)
        miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0) - hit)
        out = usage.get("completion_tokens", 0)
        return (hit * config.PRICE_INPUT_HIT + miss * config.PRICE_INPUT_MISS + out * config.PRICE_OUTPUT) / 1_000_000

    @staticmethod
    def _fallback(butt_in: bool) -> dict:
        return {"reply": "" if butt_in else random.choice(FALLBACK_LINES), "tone": "neutral", "note": "",
                "line_crossed": False, "timezone": "", "struggle": "", "panda_fact": "", "ok": False}
