"""Soon's memory: player notebooks, mood scores, heat levels and the AI budget.

Every row carries the server (guild) id, so other clans can be added later without a rebuild.
If no database is connected, everything is kept in memory instead (fine for testing, forgotten on restart).
"""
import datetime as dt
import json

import asyncpg

from . import config

HEAT_LEVELS = ["sweet", "mild", "spicy", "savage", "unhinged"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    guild_id    BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    mood        INT    NOT NULL DEFAULT 0,
    heat_lock   TEXT,
    pester      BOOLEAN NOT NULL DEFAULT TRUE,
    notes       JSONB  NOT NULL DEFAULT '[]',
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS ai_usage (
    month   TEXT PRIMARY KEY,
    cost    DOUBLE PRECISION NOT NULL DEFAULT 0,
    calls   INT NOT NULL DEFAULT 0
);
"""


def mood_to_heat(mood: int) -> str:
    if mood >= 4:
        return "sweet"
    if mood >= 2:
        return "mild"
    if mood >= -1:
        return "spicy"
    if mood >= -3:
        return "savage"
    return "unhinged"


class Player:
    def __init__(self, guild_id, user_id, mood=0, heat_lock=None, pester=True, notes=None, last_seen=None):
        self.guild_id = guild_id
        self.user_id = user_id
        self.mood = mood
        self.heat_lock = heat_lock
        self.pester = pester
        self.notes = list(notes or [])
        self.last_seen = last_seen or dt.datetime.now(dt.timezone.utc)

    @property
    def heat(self) -> str:
        return self.heat_lock or mood_to_heat(self.mood)

    def drift(self, rude: bool):
        """Quiet players drift back toward 0 (one step per 2 days away). Rude ones don't get the drift."""
        if rude:
            return
        days = (dt.datetime.now(dt.timezone.utc) - self.last_seen).days
        steps = days // 2
        if steps and self.mood:
            if self.mood > 0:
                self.mood = max(0, self.mood - steps)
            else:
                self.mood = min(0, self.mood + steps)


class Memory:
    def __init__(self):
        self.pool = None
        self._players = {}
        self._usage = {}

    async def connect(self):
        if not config.DATABASE_URL:
            print("No DATABASE_URL set: using temporary memory (forgotten on restart).")
            return
        self.pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=4)
        async with self.pool.acquire() as con:
            await con.execute(SCHEMA)
        print("Database connected.")

    async def get_player(self, guild_id: int, user_id: int) -> Player:
        if not self.pool:
            return self._players.setdefault((guild_id, user_id), Player(guild_id, user_id))
        row = await self.pool.fetchrow(
            "SELECT * FROM players WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)
        if not row:
            return Player(guild_id, user_id)
        notes = row["notes"]
        if isinstance(notes, str):
            notes = json.loads(notes)
        return Player(guild_id, user_id, row["mood"], row["heat_lock"], row["pester"], notes, row["last_seen"])

    async def save_player(self, p: Player):
        p.last_seen = dt.datetime.now(dt.timezone.utc)
        if not self.pool:
            self._players[(p.guild_id, p.user_id)] = p
            return
        await self.pool.execute(
            """INSERT INTO players (guild_id, user_id, mood, heat_lock, pester, notes, last_seen)
               VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7)
               ON CONFLICT (guild_id, user_id) DO UPDATE SET
                 mood=EXCLUDED.mood, heat_lock=EXCLUDED.heat_lock, pester=EXCLUDED.pester,
                 notes=EXCLUDED.notes, last_seen=EXCLUDED.last_seen""",
            p.guild_id, p.user_id, p.mood, p.heat_lock, p.pester, json.dumps(p.notes), p.last_seen)

    async def forget_player(self, guild_id: int, user_id: int):
        if not self.pool:
            self._players.pop((guild_id, user_id), None)
            return
        await self.pool.execute("DELETE FROM players WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)

    @staticmethod
    def _month() -> str:
        return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")

    async def month_spend(self) -> tuple[float, int]:
        m = self._month()
        if not self.pool:
            return self._usage.get(m, (0.0, 0))
        row = await self.pool.fetchrow("SELECT cost, calls FROM ai_usage WHERE month=$1", m)
        return (row["cost"], row["calls"]) if row else (0.0, 0)

    async def add_spend(self, cost: float):
        m = self._month()
        if not self.pool:
            c, n = self._usage.get(m, (0.0, 0))
            self._usage[m] = (c + cost, n + 1)
            return
        await self.pool.execute(
            """INSERT INTO ai_usage (month, cost, calls) VALUES ($1,$2,1)
               ON CONFLICT (month) DO UPDATE SET cost=ai_usage.cost+$2, calls=ai_usage.calls+1""",
            m, cost)
