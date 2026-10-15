""""Forget it?" check-ins (Shannon's call): arguing with Soon is the fun, so she never gives in on the first complaint.
When someone keeps pushing back on the SAME specific thing, she asks once (in her style) with two buttons:
✅ "Yes, forget it" → she drops it for good • 😈 "No, it's fun" → she keeps it and won't ask again for 14 days.
- Nicknames: 2 pushbacks within 7 days ("stop calling me that", "change my name back", "I'm not your <her name for them>").
  Yes = server nickname restored, she stops using the name (kv notcalled), no more renames.
- Anything else (a running joke, a claim about them, a topic): her AI tags real pushback (`pushback` field, plain
  banter doesn't count); 3 times within 14 days. Yes = kv forget:<gid>:<uid> ("never bring up with them") and
  matching notes are erased.
Max one ask per person per day. Only that person can press. Saved in kv push:<gid>:<uid>."""
import json
import random
import re
import secrets
import time

import discord

MEMORY = None          # bot.py sets these at startup
ON_FORGET = None       # async (interaction, kind, label) -> str: does the forgetting, returns her answer line
NICK_TIMES, TOPIC_TIMES = 2, 3
NICK_WINDOW, TOPIC_WINDOW, FUN_FOR = 7 * 86400, 14 * 86400, 14 * 86400

ASK_NICK = ["Okay {u}, that's twice. Real question, don't get used to it: do you actually want me to stop calling you "
            "**{x}**, or are we having fun?",
            "Systems check, {u}: is **{x}** genuinely bugging you, or is this our thing now? I can delete it. I'm a robot.",
            "{u}, you've complained about **{x}** twice. I need to know if I'm winning or if you're actually mad."]
ASK_TOPIC = ["Okay {u}, you keep pushing back on **{x}**. Real question: want me to drop it for good, or is this fun for you?",
             "Systems check, {u}: is **{x}** actually annoying you, or are we just bickering? One tap and it's deleted.",
             "{u}, third time you've fought me on **{x}**. Do I delete it from my memory, or do we keep going?"]


FILLER = set("the and about you your my me that this jokes joke calling call stop keep always saying say thing things "
             "stuff with for from not dont don't".split())


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", (s or "").lower()) if len(w) > 2 and w not in FILLER}


def same(a: str, b: str) -> bool:
    """Loose match: 'jokes about my piggy score' ~ 'my Piggy score'."""
    if re.sub(r"\W", "", a.lower()) == re.sub(r"\W", "", b.lower()):
        return True
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return re.sub(r"\W", "", a.lower()) == re.sub(r"\W", "", b.lower())
    return len(wa & wb) / min(len(wa), len(wb)) >= 0.5


async def _get(gid, uid) -> dict:
    return json.loads(await MEMORY.get_kv(f"push:{gid}:{uid}") or '{"items": {}, "asked": 0}')


async def _put(gid, uid, d):
    await MEMORY.set_kv(f"push:{gid}:{uid}", json.dumps(d))


async def count(gid: int, uid: int, kind: str, label: str) -> tuple[int, str] | None:
    """Count one pushback. Returns (count, label) when it's time to ask them, else None."""
    d = await _get(gid, uid)
    now, window, need = time.time(), (NICK_WINDOW if kind == "nick" else TOPIC_WINDOW), (NICK_TIMES if kind == "nick" else TOPIC_TIMES)
    key = next((k for k, v in d["items"].items() if v["kind"] == kind and same(k, label)), label[:60])
    it = d["items"].get(key, {"kind": kind, "n": 0, "t": 0, "fun": 0})
    if it.get("fun", 0) > now:                    # they said "it's fun" recently: keep bickering, don't ask
        return None
    it["n"] = (it["n"] if now - it["t"] < window else 0) + 1
    it["t"] = now
    d["items"][key] = it
    ready = it["n"] >= need and now - d.get("asked", 0) > 86400
    if ready:
        d["asked"] = now
    await _put(gid, uid, d)
    return (it["n"], key) if ready else None


async def labels(gid: int, uid: int) -> list[str]:
    """Things they've pushed back on lately (so her AI reuses the same label when they do it again)."""
    d, now = await _get(gid, uid), time.time()
    return [k for k, v in d["items"].items() if v["kind"] == "topic" and now - v["t"] < TOPIC_WINDOW][-6:]


async def forgotten(gid: int, uid: int) -> list[str]:
    return json.loads(await MEMORY.get_kv(f"forget:{gid}:{uid}") or "[]")


async def ask(channel, member, kind: str, label: str):
    """Her "want me to forget it?" message with the two buttons (only they can press)."""
    tok = secrets.token_hex(4)
    await MEMORY.set_kv(f"pushask:{tok}", json.dumps({"g": channel.guild.id, "u": member.id, "kind": kind, "label": label}))
    text = random.choice(ASK_NICK if kind == "nick" else ASK_TOPIC).format(u=member.mention, x=label)
    v = discord.ui.View(timeout=None)
    v.add_item(ForgetButton(member.id, "y", tok))
    v.add_item(ForgetButton(member.id, "n", tok))
    await channel.send(text, view=v)


class ForgetButton(discord.ui.DynamicItem[discord.ui.Button], template=r"soon:fg:(?P<u>\d+):(?P<a>[yn]):(?P<t>[0-9a-f]+)"):
    def __init__(self, uid: int, answer: str, tok: str):
        label, emoji, style = (("Yes, forget it", "✅", discord.ButtonStyle.success) if answer == "y"
                               else ("No, it's fun", "😈", discord.ButtonStyle.secondary))
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=f"soon:fg:{uid}:{answer}:{tok}"))
        self.uid, self.answer, self.tok = uid, answer, tok

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(int(match["u"]), match["a"], match["t"])

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("Not your question, nosy. I'll ask YOU when you annoy me enough.",
                                                    ephemeral=True)
            return
        raw = await MEMORY.get_kv(f"pushask:{self.tok}")
        if not raw:
            await interaction.response.edit_message(view=None)
            return
        q = json.loads(raw)
        await MEMORY.set_kv(f"pushask:{self.tok}", "")
        d = await _get(q["g"], q["u"])
        it = next((v for k, v in d["items"].items() if v["kind"] == q["kind"] and same(k, q["label"])), None)
        if self.answer == "y":
            d["items"] = {k: v for k, v in d["items"].items() if not (v["kind"] == q["kind"] and same(k, q["label"]))}
            await _put(q["g"], q["u"], d)
            line = await ON_FORGET(interaction, q["kind"], q["label"]) if ON_FORGET else "Done. Forgotten."
        else:
            if it:
                it.update(n=0, fun=time.time() + FUN_FOR)
                await _put(q["g"], q["u"], d)
            line = random.choice(["I KNEW it. You love it. Carry on suffering.", "Good. I was going to keep doing it anyway.",
                                  "Noted: you're having fun. I'll tell everyone.", "Excellent. Round two starts now."])
        await interaction.response.edit_message(view=None)
        await interaction.followup.send(f"{interaction.user.mention} {line}")
