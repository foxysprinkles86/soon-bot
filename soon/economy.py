"""The casino bank: chips, tacos, taco debt, margaritas, eggs, casino net, timers and the house pots.

Same money as Soon Classic, same names, so the cutover import is one-to-one:
  chips     Tortilla Chips (can go negative from fines = chip debt)
  tacobal   taco balance (negative = taco debt)
  tacos     taco requests (how many times they asked the van)
  margs     margaritas ordered
  eggs      which Easter eggs they found (list of ids) / eggcount = how many
  casnet    all-time casino win/loss
  delivered real tacos delivered (the 1-in-500 miracle)
House pots per server: jpot (slots jackpot growth), jackpots (Hall of Fame lines), heistsubs (heist alert list).
Every change is written to econ_log so we can always see where chips went.
If no database is connected, everything lives in memory (fine for testing, forgotten on restart).
"""
import datetime as dt
import json
from dataclasses import dataclass, field

COUNTERS = ["chips", "tacobal", "tacos", "margs", "eggcount", "casnet", "delivered"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    started   BOOLEAN NOT NULL DEFAULT FALSE,
    chips     BIGINT NOT NULL DEFAULT 0,
    tacobal   BIGINT NOT NULL DEFAULT 0,
    tacos     BIGINT NOT NULL DEFAULT 0,
    margs     BIGINT NOT NULL DEFAULT 0,
    eggcount  BIGINT NOT NULL DEFAULT 0,
    casnet    BIGINT NOT NULL DEFAULT 0,
    delivered BIGINT NOT NULL DEFAULT 0,
    eggs      JSONB  NOT NULL DEFAULT '[]',
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS timers (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    k        TEXT   NOT NULL,
    until    TIMESTAMPTZ NOT NULL,
    n        INT    NOT NULL DEFAULT 1,
    PRIMARY KEY (guild_id, user_id, k)
);
CREATE TABLE IF NOT EXISTS casino_day (
    guild_id BIGINT NOT NULL,
    day      TEXT   NOT NULL,
    user_id  BIGINT NOT NULL,
    net      BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, day, user_id)
);
CREATE TABLE IF NOT EXISTS econ_log (
    id       BIGSERIAL PRIMARY KEY,
    ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    what     TEXT   NOT NULL,
    delta    BIGINT NOT NULL,
    reason   TEXT   NOT NULL
);
"""


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def casino_day(when: dt.datetime | None = None) -> str:
    """Classic's casino day rolls over at 5 AM UTC (midnight Central, roughly)."""
    return ((when or now()) - dt.timedelta(hours=5)).strftime("%Y-%m-%d")


@dataclass
class Wallet:
    guild_id: int
    user_id: int
    started: bool = False
    chips: int = 0
    tacobal: int = 0
    tacos: int = 0
    margs: int = 0
    eggcount: int = 0
    casnet: int = 0
    delivered: int = 0
    eggs: list = field(default_factory=list)


def _wallet(row) -> Wallet:
    eggs = row["eggs"]
    if isinstance(eggs, str):
        eggs = json.loads(eggs)
    return Wallet(row["guild_id"], row["user_id"], row["started"], *(row[c] for c in COUNTERS), list(eggs))


class Bank:
    def __init__(self, memory):
        self.m = memory              # shares the Postgres pool with Soon's memory
        self._w = {}                 # (gid, uid) -> Wallet
        self._t = {}                 # (gid, uid, k) -> (until, n)
        self._day = {}               # (gid, day, uid) -> net
        self._kv = {}

    @property
    def pool(self):
        return self.m.pool

    async def setup(self):
        if self.pool:
            async with self.pool.acquire() as con:
                await con.execute(SCHEMA)

    # ----- wallets -----

    async def get(self, gid: int, uid: int) -> Wallet:
        if not self.pool:
            return self._w.setdefault((gid, uid), Wallet(gid, uid))
        row = await self.pool.fetchrow("SELECT * FROM wallets WHERE guild_id=$1 AND user_id=$2", gid, uid)
        return _wallet(row) if row else Wallet(gid, uid)

    async def add(self, gid: int, uid: int, reason: str, start: bool = False, **deltas) -> Wallet:
        """Add (or subtract, with negatives) to any counters at once. No floor: debt is allowed."""
        deltas = {k: int(v) for k, v in deltas.items() if v}
        bad = set(deltas) - set(COUNTERS)
        if bad:
            raise ValueError(f"unknown wallet fields: {bad}")
        if not self.pool:
            w = await self.get(gid, uid)
            for k, v in deltas.items():
                setattr(w, k, getattr(w, k) + v)
            w.started = w.started or start
            return w
        cols = list(deltas)
        sets = ", ".join(f"{c}=wallets.{c}+EXCLUDED.{c}" for c in cols) or "chips=wallets.chips"
        names = "".join(f", {c}" for c in cols)
        args = "".join(f", ${i + 4}" for i in range(len(cols)))
        async with self.pool.acquire() as con, con.transaction():
            row = await con.fetchrow(
                f"""INSERT INTO wallets (guild_id, user_id, started{names}) VALUES ($1, $2, $3{args})
                    ON CONFLICT (guild_id, user_id) DO UPDATE SET {sets},
                      started = wallets.started OR EXCLUDED.started
                    RETURNING *""",
                gid, uid, start, *deltas.values())
            await self._log(con, gid, uid, deltas, reason)
        return _wallet(row)

    async def pay(self, gid: int, uid: int, amount: int, reason: str) -> Wallet | None:
        """Take chips only if they have enough. Returns the new wallet, or None if they're short."""
        amount = int(amount)
        if not self.pool:
            w = await self.get(gid, uid)
            if w.chips < amount:
                return None
            w.chips -= amount
            return w
        async with self.pool.acquire() as con, con.transaction():
            row = await con.fetchrow(
                "UPDATE wallets SET chips=chips-$3 WHERE guild_id=$1 AND user_id=$2 AND chips >= $3 RETURNING *",
                gid, uid, amount)
            if row:
                await self._log(con, gid, uid, {"chips": -amount}, reason)
        return _wallet(row) if row else None

    async def transfer(self, gid: int, src: int, dst: int, amount: int, reason: str) -> tuple[Wallet, Wallet] | None:
        """Move chips between players (tips, rain). None if the sender is short."""
        a = await self.pay(gid, src, amount, reason)
        if a is None:
            return None
        b = await self.add(gid, dst, reason, chips=amount)
        return a, b

    async def record_play(self, gid: int, uid: int, net: int):
        """A game finished: net win (+) or loss (-). Feeds the casino board and the daily casino report."""
        if net:
            await self.add(gid, uid, "casino result", casnet=net)   # break-even plays still count as "gambled today"
        day = casino_day()
        if not self.pool:
            self._day[(gid, day, uid)] = self._day.get((gid, day, uid), 0) + net
            return
        await self.pool.execute(
            """INSERT INTO casino_day (guild_id, day, user_id, net) VALUES ($1,$2,$3,$4)
               ON CONFLICT (guild_id, day, user_id) DO UPDATE SET net=casino_day.net+EXCLUDED.net""",
            gid, day, uid, net)

    async def day_results(self, gid: int, day: str) -> list[tuple[int, int]]:
        """[(user_id, net)] for one casino day, biggest winner first."""
        if not self.pool:
            rows = [(u, n) for (g, d, u), n in self._day.items() if g == gid and d == day]
        else:
            rows = [(r["user_id"], r["net"]) for r in await self.pool.fetch(
                "SELECT user_id, net FROM casino_day WHERE guild_id=$1 AND day=$2", gid, day)]
        return sorted(rows, key=lambda r: -r[1])

    async def add_egg(self, gid: int, uid: int, egg: str) -> bool:
        """True if it's a new egg for them."""
        w = await self.get(gid, uid)
        if egg in w.eggs:
            return False
        eggs = w.eggs + [egg]
        if not self.pool:
            w.eggs, w.eggcount = eggs, len(eggs)
            return True
        await self.pool.execute(
            """INSERT INTO wallets (guild_id, user_id, eggs, eggcount) VALUES ($1,$2,$3::jsonb,$4)
               ON CONFLICT (guild_id, user_id) DO UPDATE SET eggs=EXCLUDED.eggs, eggcount=EXCLUDED.eggcount""",
            gid, uid, json.dumps(eggs), len(eggs))
        return True

    async def top(self, gid: int, what: str, n: int = 5, lowest: bool = False) -> list[Wallet]:
        if what not in COUNTERS:
            raise ValueError(what)
        if not self.pool:
            ws = [w for (g, _), w in self._w.items() if g == gid]
            return sorted(ws, key=lambda w: getattr(w, what), reverse=not lowest)[:n]
        rows = await self.pool.fetch(
            f"SELECT * FROM wallets WHERE guild_id=$1 ORDER BY {what} {'ASC' if lowest else 'DESC'} LIMIT $2", gid, n)
        return [_wallet(r) for r in rows]

    async def totals(self, gid: int) -> dict:
        """Players with chips, total chips, total tacos: the numbers to compare on cutover night."""
        if not self.pool:
            ws = [w for (g, _), w in self._w.items() if g == gid]
            return {"players": sum(w.started for w in ws), "chips": sum(w.chips for w in ws),
                    "tacobal": sum(w.tacobal for w in ws)}
        row = await self.pool.fetchrow(
            """SELECT count(*) FILTER (WHERE started) AS players, coalesce(sum(chips),0)::bigint AS chips,
                      coalesce(sum(tacobal),0)::bigint AS tacobal FROM wallets WHERE guild_id=$1""", gid)
        return dict(row)

    async def replace_all(self, gid: int, wallets: list[Wallet], house: dict):
        """Cutover import: wipe this server's test balances and load Classic's. One transaction: all or nothing."""
        if not self.pool:
            for store in (self._w, self._t):
                for k in [k for k in store if k[0] == gid]:
                    del store[k]
            self._day = {k: v for k, v in self._day.items() if k[0] != gid}
            for w in wallets:
                self._w[(gid, w.user_id)] = w
            for k, v in house.items():
                await self.set_house(gid, k, v)
            return
        async with self.pool.acquire() as con, con.transaction():
            await con.execute("DELETE FROM wallets WHERE guild_id=$1", gid)
            await con.execute("DELETE FROM timers WHERE guild_id=$1", gid)
            await con.execute("DELETE FROM casino_day WHERE guild_id=$1", gid)
            await con.executemany(
                f"""INSERT INTO wallets (guild_id, user_id, started, {', '.join(COUNTERS)}, eggs)
                    VALUES ($1,$2,$3,{', '.join(f'${i + 4}' for i in range(len(COUNTERS)))},${len(COUNTERS) + 4}::jsonb)""",
                [(gid, w.user_id, w.started, *(getattr(w, c) for c in COUNTERS), json.dumps(w.eggs)) for w in wallets])
            for k, v in house.items():
                await con.execute("INSERT INTO kv (k, v) VALUES ($1,$2) ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v",
                                  f"house:{gid}:{k}", json.dumps(v))
            await con.execute("INSERT INTO econ_log (guild_id, user_id, what, delta, reason) VALUES ($1,0,'import',$2,$3)",
                              gid, len(wallets), "Soon Classic import")

    async def _log(self, con, gid, uid, deltas: dict, reason: str):
        if deltas:
            await con.executemany(
                "INSERT INTO econ_log (guild_id, user_id, what, delta, reason) VALUES ($1,$2,$3,$4,$5)",
                [(gid, uid, k, v, reason[:100]) for k, v in deltas.items()])

    # ----- timers (cooldowns and 12-hour allowance windows) -----

    async def timer(self, gid: int, uid: int, k: str) -> tuple[dt.datetime, int] | None:
        """(ends_at, count) if the timer is still running, else None."""
        if not self.pool:
            t = self._t.get((gid, uid, k))
        else:
            row = await self.pool.fetchrow(
                "SELECT until, n FROM timers WHERE guild_id=$1 AND user_id=$2 AND k=$3", gid, uid, k)
            t = (row["until"], row["n"]) if row else None
        return t if t and t[0] > now() else None

    async def set_timer(self, gid: int, uid: int, k: str, seconds: float, n: int = 1, until: dt.datetime | None = None):
        until = until or now() + dt.timedelta(seconds=seconds)
        if not self.pool:
            self._t[(gid, uid, k)] = (until, n)
            return
        await self.pool.execute(
            """INSERT INTO timers (guild_id, user_id, k, until, n) VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (guild_id, user_id, k) DO UPDATE SET until=EXCLUDED.until, n=EXCLUDED.n""",
            gid, uid, k, until, n)

    async def clear_timer(self, gid: int, uid: int, k: str):
        if not self.pool:
            self._t.pop((gid, uid, k), None)
            return
        await self.pool.execute("DELETE FROM timers WHERE guild_id=$1 AND user_id=$2 AND k=$3", gid, uid, k)

    async def use_allowance(self, gid: int, uid: int, k: str, want: int, limit: int, window: int) -> tuple[int, int, dt.datetime]:
        """Classic's "2 tacos per 12 hours" style limit. The window starts at first use.
        Returns (granted, used_after, resets_at). Granted can be 0."""
        t = await self.timer(gid, uid, k)
        used, until = (t[1], t[0]) if t else (0, now() + dt.timedelta(seconds=window))
        granted = max(0, min(want, limit - used))
        if granted:
            await self.set_timer(gid, uid, k, 0, used + granted, until=until)
        return granted, used + granted, until

    # ----- house pots (per server) -----

    async def get_house(self, gid: int, k: str, default=None):
        raw = await self.m.get_kv(f"house:{gid}:{k}")
        return json.loads(raw) if raw else default

    async def set_house(self, gid: int, k: str, v):
        await self.m.set_kv(f"house:{gid}:{k}", json.dumps(v))
