"""Talking to DeepSeek. One request per reply: Soon's line, how the player treated her, and an optional note for her notebook."""
import asyncio
import json
import random
import re
import time
from collections import deque

import httpx

from . import config
from .helpdesk import GUIDE
from .personality import FALLBACK_LINES, SHEET

TONES = {"nice", "neutral", "rude", "upset"}

INSTRUCTIONS = """Reply with JSON only:
{"reply": "", "tone": "nice|neutral|rude|upset", "at_you": false, "note": "", "line_crossed": false, "timezone": "", "struggle": "", "panda_fact": "", "nickname": ""}
- reply: what Soon says ("" allowed only in BUTT-IN or MAYBE mode when there's nothing worth saying).
- tone: how their latest message treated Soon or others (upset = genuinely hurt, not joking).
- at_you: true only if that nice/rude tone is aimed at YOU (Soon) yourself, not at someone else or the game.
- note: usually "". One short NEW thing they actually said or did worth remembering for future banter, in your voice. Never health, family or trauma, never a repeat of what you remember.
- line_crossed: true only if they attacked another person with a slur, over race/religion/sexuality/gender/disability, or mocked real trauma. Trash talk, swearing and roasting Soon are fine. If true, call it out in character.
- timezone: IANA zone (like "America/New_York") only if they just said where they live, else "".
- struggle: a few words if they're confused or a command isn't working for them, else "".
- panda_fact: only if your reply states a NEW made-up Panda fact, that fact in a few words, else "".
- nickname: only if your reply calls THIS player by a NEW made-up name you invented for them (a fake name like a person's name or a title), that name (max 32 characters). Not their real name, not your existing nickname for them, not pet words like "sweetie" or "driver". Usually ""."""


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


def pick_notes(notes: list[str], message: str, limit: int = 12) -> list[str]:
    """Only the notes that matter right now: ones sharing a word with their message, topped up with the newest."""
    words = {w for w in re.findall(r"[a-z0-9']{4,}", message.lower())}
    hits = [n for n in notes if words & set(re.findall(r"[a-z0-9']{4,}", n.lower()))][-limit:]
    rest = [n for n in notes if n not in hits][-(limit - len(hits)):] if len(hits) < limit else []
    return rest + hits


class Brain:
    def __init__(self, memory):
        self.memory = memory
        self.client = httpx.AsyncClient(timeout=25)
        # AI health, for `soon ai` and the mod alert: recent call times (s, or None = failed), failure streak, last error
        self.health = {"calls": deque(maxlen=30), "streak": 0, "last_error": "", "last_error_at": 0.0}

    async def _post(self, body: dict) -> dict:
        """One DeepSeek call with one quick retry for blips (not for timeouts: those already took 25s).
        Records timing/failures in self.health. Raises on failure."""
        start = time.time()
        for attempt in (1, 2):
            try:
                r = await self.client.post(f"{config.DEEPSEEK_BASE_URL}/chat/completions",
                                           headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"}, json=body)
                r.raise_for_status()
                data = r.json()
                self.health["calls"].append(round(time.time() - start, 1))
                self.health["streak"] = 0
                return data
            except Exception as e:
                timed_out = isinstance(e, httpx.TimeoutException)
                if attempt == 1 and not timed_out and not (isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 402)):
                    await asyncio.sleep(1.5)
                    continue
                self.health["calls"].append(None)
                self.health["streak"] += 1
                why = ("took longer than 25 seconds (DeepSeek slow or down)" if timed_out else
                       f"DeepSeek said {e.response.status_code}" + (" (out of credit: top up the DeepSeek balance)"
                                                                     if e.response.status_code == 402 else
                                                                     " (API key problem)" if e.response.status_code == 401 else "")
                       if isinstance(e, httpx.HTTPStatusError) else
                       "couldn't reach DeepSeek (their servers or the internet)" if isinstance(e, httpx.TransportError)
                       else f"{type(e).__name__}")
                self.health.update(last_error=why, last_error_at=time.time())
                raise

    async def budget_left(self) -> bool:
        spent, _ = await self.memory.month_spend()
        return spent < config.AI_MONTHLY_CAP_USD

    async def think(self, *, player_name: str, player_notes: list[str], heat: str, is_kor: bool,
                    message: str, recent_chat: list[str], butt_in: bool = False, maybe: bool = False, extra: str = "",
                    length_weights: list[int] | None = None, help_desk: bool = False) -> dict:
        """Returns {"reply", "tone", "note", "ok"}. ok=False means a fallback line was used."""
        if not config.DEEPSEEK_API_KEY or not await self.budget_left():
            return self._fallback(butt_in or maybe)

        if butt_in:
            mode = "BUTT-IN: nobody asked you. Reply only if you have something short, funny and relevant."
        elif maybe:
            mode = "MAYBE: they might be talking to you. Reply only if it's meant for you (not someone else, not just 'coming soon')."
        else:
            mode = "DIRECT: they're talking to you."
        notes = "\n".join(f"- {n}" for n in pick_notes(player_notes, message)) or "- (nothing yet)"
        chat = "\n".join(recent_chat[-30:]) or "(quiet)"
        situation = (
            f"PLAYER: {player_name}{' (this is KOR, your crush)' if is_kor else ''}\n"
            f"HEAT LEVEL FOR THIS PLAYER: {heat}\n"
            f"WHAT YOU REMEMBER ABOUT THEM:\n{notes}\n\n"
            f"RECENT CHAT (oldest first; background, so you know what's going on):\n{chat}\n\n"
            f"MODE: {mode}\n"
            + (f"{extra}\n" if extra else "")
            + f"THEIR LATEST MESSAGE (this is what you're answering): {message}"
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
                {"role": "system", "content": SHEET + ("\n\n" + GUIDE if help_desk else "") + "\n\n" + INSTRUCTIONS},
                {"role": "user", "content": situation},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 1.1,
            "max_tokens": 220,
        }
        try:
            data = await self._post(body)
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
        nickname = str(out.get("nickname") or "").strip()[:32]
        return {"reply": reply[:1900], "tone": tone, "at_you": out.get("at_you") is True, "note": note, "line_crossed": crossed, "timezone": tz,
                "struggle": struggle, "panda_fact": panda_fact, "nickname": nickname, "ok": True}

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
            data = await self._post(body)
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
                    "game milestones, what they're bad at. Skip boring small talk. Write notes in Soon's voice: petty, "
                    "sarcastic commentary is GOOD ('new critic in the house', 'running joke of the chat'). But the fact underneath "
                    "must be real: something they actually said or did. Don't invent secret feelings or motives as fact (not "
                    "'secretly scared of X', not 'the crush is mutual'). "
                    "Lines marked as talking to the OLD YAGPDB Soon are about that bot, not about Soon: don't turn them into "
                    "notes about Soon (ordering tacos, typing 'egg' etc. go to the old bot). Get WHO said what right. Never store health, family, money "
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
            data = await self._post(body)
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
        return {"reply": "" if butt_in else random.choice(FALLBACK_LINES), "tone": "neutral", "at_you": False, "note": "",
                "line_crossed": False, "timezone": "", "struggle": "", "panda_fact": "", "nickname": "", "ok": False}
