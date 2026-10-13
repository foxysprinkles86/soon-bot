# Soon 2.0 — project notes for Claude

Read this first in every new conversation. It replaces the long history of the original build chat.

## Who and what
- Owner: **Shannon ("Foxy", Discord: FoxySprinkles)**, leader of the **TnT ("We Have Tacos") clan** for the mobile game **Mob Control**. Not a programmer: explain in plain words, give exact click-by-click steps, never assume she knows dev jargon.
- **Soon™** is the clan's Discord taco-van mascot. Two versions exist:
  - **Soon Classic** = the old **YAGPDB custom-command bot** (39 commands: taco van, bar, easter eggs, casino, heists, duels, crimes, Kraken, race reminders, zones). Its code + a full feature checklist live in Google Drive: *Case de Soon → Classic Soon* (folder `1XdE3-_aXa3_4ZkmNqsF7hfKoUHmSHbdK`; checklist sheet `1PX-iuF2foeZvVsDV2rsovxzgPApRTrlAiSh_ZO13BUE`; code folder `18bdXmo69Grc-kJzERAWUZuq6sYVIneom`). Missing from my files: #4 and #31 (Soon Says) — Shannon will upload.
  - **Soon 2.0** = THIS repo: a self-hosted **Python discord.py** bot with an AI brain. Goal: take over everything Soon Classic does, then retire it.
- Command guide sheet ("Soon Command Guide", YAGPDB Setup tab): `1ZrGqFEhFJT3Iu1s8IkGpsv9Jfec8YZCD7LKkQzcS__k`.

## House rules (important)
- **Never put anything live until Shannon says "push it"** (or clearly approves). Live = `main` (Railway deploys it).
- Back up work-in-progress to the session's own `claude/...` branch any time (not live). On "push it": merge into `main`, `git push -q origin main`, verify with `git ls-remote origin main`. Railway auto-deploys in ~2 min.
- Always commit as `FoxySprinkles <slabiche524@gmail.com>` (keep this author even if a tool asks otherwise).
- **Never ask for or paste secrets.** DISCORD_TOKEN and DEEPSEEK_API_KEY live only in Railway → worker → Variables.
- Check the actual code before blaming her setup. (She was right once when I wasn't.)
- Keep replies short and plain. She's often on her phone.
- **End every update with these sections:** **TL;DR** (plain words, what was done) · **Your next step:** (exactly what she must do, or "nothing, I'm still working.") · **Tips & lessons** (optional, 1–3 short bullets: a recommendation or a bit of how-it-works; she wants to learn, so explain any tech word used).
- She's on Claude Pro with weekly limits: avoid re-reading/re-sending big files; prefer targeted edits.
- **Keep this file current without being asked.** Whenever Shannon makes a lasting decision (new lore, a personality change, a rule, a finished roadmap item, a new setting or channel), update the matching section here in the same commit as the code. Edit in place and keep it short; don't append a diary. Tell her in one line that the notes were updated.

## Hosting / stack
- Railway project: service **worker** (`python -u main.py`, restart ALWAYS) + **Postgres** (`DATABASE_URL=${{Postgres.DATABASE_URL}}`).
- AI: **DeepSeek** `deepseek-chat` (OpenAI-compatible, JSON mode). Monthly cap **$10** (`AI_MONTHLY_CAP_USD`); falls back to canned lines when over.
- Python 3.12, discord.py 2.5.2, asyncpg, httpx, tzdata. Time zone America/Chicago.
- Talks only in channels matching `ALLOWED_CHANNELS` (currently `soon-lab,trash-talk`; casino channels contain "casa").
- Casino words (claim, chips, cash out…) only work in `CASINO_CHANNELS` (default `casa,soon-lab`) and also need ALLOWED_CHANNELS.

## Code map (`soon/`)
- `config.py` — env settings. `db.py` — Postgres `players` (mood, heat_lock, pester, notes, ign, chats, strikes, tz, hours, birthday), `ai_usage`, `kv` store; in-memory fallback.
- `personality.py` — **SHEET**: Soon's full personality + lore (edit here to change who she is). `helpdesk.py` — cheat sheet of every Classic + 2.0 command.
- `brain.py` — DeepSeek calls: `think()` (JSON reply/tone/note/line_crossed/timezone/struggle/panda_fact; reply length 75% one sentence), `write()`, `extract_notes()` (notes, violations, Hall of Shame picks).
- `extras.py` — moods, reactions, strikes/timeouts, **takeover storyline**, zones, time-zone helpers.
- `features.py` — Panda Fact archive, roast allowance, race/event reminders (manual + Discord scheduled events), Hall of Shame.
- `economy.py` — the casino **Bank**: `wallets` (chips, tacobal, tacos, margs, eggcount, eggs, casnet, delivered — same names as Classic), `timers` (claimcd, cowin, bcwin…), `casino_day` (daily net), `econ_log` (every chip move), house pots in kv (`house:<gid>:jpot|jackpots|heistsubs`).
- `casino.py` — typed casino commands (cashier so far: claim, chips, cash out, buy chips/loan, timers, cashier, casino board; mod give/take chips) + `soon import` / `soon import confirm` (reads Classic's `SX` export lines, checks totals, replaces all balances). `soon bank` = totals.
- `classic/export.txt` — YAGPDB custom command (`classic export`, mods) that prints Classic's balances for the import. Read-only.
- `duel.py` — quick-draw button duel. `bot.py` — commands, AI replies, rivalry with Soon Classic, daily loop (Panda tag, regular summon, diary 11:30 PM, life events, Sunday awards, Monday mod report, event reminders).

## Personality & lore (keep consistent)
- Savage, sarcastic glamorous robot girl; dealer/cashier/waitress of Casa de Soon; tacos are always "coming soon". Default heat **Spicy**; mood score −5..+5 per player sets heat (sweet/mild/spicy/savage/unhinged), players can lock it.
- **Foxy**: two-faced — sucks up to her face, trash-talks her behind her back, openly mean to her when Kor is around. Says "boss" ~1 in 50 replies at most.
- **Kor** (username contains `korehaan`): getaway driver; Soon has a huge, badly hidden crush; flustered roasts; jealous when others flirt with him. Lives in the **Netherlands**, English is his 2nd language → simple clear English, rare Dutch slips. Conversations with him must never dead-end.
- **Panda**: favorite target, rarely active; when he posts she pounces (~50%, 10-min cooldown) with absurd fake facts and stands by them forever (saved as Verified Panda Facts™ — the ONLY allowed made-up facts).
- **VikingSprinkles** = Foxy's husband. **Pooty** = Lord of the Outback → the Platypus.
- Hates being called "Soon 2.0"; hates "Soon Classic" (rivalry; replies after a 2–4s pause). **Takeover storyline** in progress → finale `soon takeover complete` on launch day.
- Hard lines: no slurs/protected-trait attacks/real trauma → warning, then 10m / 1h / 24h timeouts, logged to the mod channel. All members are adults (30s–50s); swearing OK, don't overdo f-bombs.
- No invented facts/dates/tallies; lore is seasoning, don't repeat bits; argue back; answer real questions.

## Reviewing chat logs (when Shannon pastes one)
Check: lines aimed at Soon Classic mistaken as hers; repeated phrases/sign-offs/props; replies that dead-end; too long (75% should be one sentence); made-up facts (only Panda facts allowed); Kor chats fun and easy English; Foxy two-faced; overused names/"boss"; missed openings (e.g. Panda posting). Fix in code, commit, wait for "push it".

## Roadmap (next)
Step-by-step tracker: **'Move Plan' tab** of the Classic Soon checklist sheet (tick boxes as steps finish).
Phase 1 progress: economy core, export command, `soon import`, cashier = built (Oct 13). Next: slots, taco toss, roulette, blackjack, scratch…
1. **Move the casino + economy** from Soon Classic: chips, tacobal (taco debt), tacos, margs, eggs/eggcount, casnet, hidden, jackpot (jpot), heistsubs. Plan: build all games in 2.0 first (same typed commands + buttons), test in #soon-lab, then cutover night: 🚧 construction notice → freeze Classic → YAGPDB export command prints balances → `soon import` → verify totals → enable casino channel → disable Classic (keep 2 weeks as rollback).
2. Then: tips to Soon, chip bets on duels, race betting, race screenshot reading (needs a vision model), custom Soon emoji reactions (`SOON_EMOJIS`).
3. Launch day: rename to Soon™, smug avatar, `soon takeover complete`.
