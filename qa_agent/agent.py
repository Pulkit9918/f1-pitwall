"""A small question-answering agent over the gold tables.

Two model calls, then a repair loop:
  1. route   the model sees one line per table and names the tables the question needs, or none when the data cannot
             answer it. Routing is scored on its own, and it keeps the second prompt small enough for a local model.
  2. write   the model sees the full column descriptions of those tables only (from the dbt manifest) and writes one
             SELECT, or says it cannot answer.
  3. repair  when the query is rejected or fails, the error goes back to the model, up to twice.
The agent can only run read-only SELECTs (see sqlguard and db). It never sees the reference answers.
"""
import datetime as dt
import json
import re
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import db, sqlguard

PROMPT_VERSION = "v2"
ALWAYS = ("dim_session",)  # the entity table that names every session; always shown to the model that writes the SQL

NOTES = """Notes about this database:
- The tables are in DuckDB. Use plain table names; do not add a schema prefix.
- session_code: R race, Q qualifying, S sprint, SQ sprint qualifying, SS sprint shootout, FP1 FP2 FP3 practice.
- Timing detail (laps, stints, pit stops, weather, race control) covers 2018 to 2026. Season results and standings
  (fct_season_result, fct_driver_standing, fct_constructor_standing) cover 1950 to 2026 and use Jolpica ids such as
  'hamilton', 'max_verstappen', 'red_bull'. fct_result and fct_lap use three-letter driver codes such as 'VER'.
- Event names look like 'Italian Grand Prix'. Match them with ILIKE, for example event ILIKE '%Italian%'.
- Results, laps, stints, pit stops, weather and race control identify their session by session_key. Join dim_session
  on session_key to filter by year, event name or session_code, unless the table has its own year column.
- Count one session at a time: filter session_code (for example 'R' for the race) so qualifying and practice are not
  counted as races.
- To find a season's final standings, take the row with the largest round for that season.
- Times are in seconds. Do not invent columns or tables."""


class Backend:
    def chat(self, messages: list[dict]) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class Ollama(Backend):
    def __init__(self, model: str, host: str = "http://localhost:11434", num_ctx: int = 8192, seed: int = 7, timeout: int = 300):
        self.model, self.host, self.num_ctx, self.seed, self.timeout = model, host.rstrip("/"), num_ctx, seed, timeout

    def chat(self, messages):
        body = json.dumps({"model": self.model, "messages": messages, "stream": False, "format": "json",
                           "options": {"temperature": 0, "num_ctx": self.num_ctx, "seed": self.seed}}).encode()
        req = urllib.request.Request(self.host + "/api/chat", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())["message"]["content"]


def parse_json(text: str) -> dict:
    """The first JSON object in a model reply; {} when there is none."""
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        return {}
    try:
        obj = json.loads(text[a:b + 1])
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


@dataclass
class Card:
    name: str
    summary: str
    columns: list[tuple[str, str, str]] = field(default_factory=list)  # name, type, description


def load_cards(con, manifest_path: str | Path | None) -> dict[str, Card]:
    """One card per table the agent may use, with descriptions from the dbt manifest when it is there."""
    docs: dict[str, dict] = {}
    if manifest_path and Path(manifest_path).exists():
        for node in json.loads(Path(manifest_path).read_text()).get("nodes", {}).values():
            if node.get("resource_type") == "model":
                docs[node["name"]] = node
    cols: dict[str, list] = {}
    for t, c, ty in con.execute("select table_name, column_name, data_type from information_schema.columns "
                                "where table_schema = 'gold' order by table_name, ordinal_position").fetchall():
        cols.setdefault(t, []).append((c, ty))
    cards = {}
    for t in db.tables(con):
        node = docs.get(t, {})
        desc = " ".join((node.get("description") or "").split())
        first = re.split(r"(?<=[.!?])\s", desc, maxsplit=1)[0][:220] if desc else ""
        cdocs = node.get("columns", {})
        cards[t] = Card(t, first or "(no description)",
                        [(c, ty, " ".join((cdocs.get(c, {}).get("description") or "").split())[:200]) for c, ty in cols.get(t, [])])
    return cards


def catalogue(cards: dict[str, Card]) -> str:
    return "\n".join(f"- {c.name}: {c.summary}" for c in cards.values())


def card_text(c: Card) -> str:
    lines = [f"Table {c.name}: {c.summary}"]
    lines += [f"  {n} {ty}" + (f" - {d}" if d else "") for n, ty, d in c.columns]
    return "\n".join(lines)


@dataclass
class Outcome:
    question: str
    tables: list[str] = field(default_factory=list)
    refused: bool = False
    reason: str = ""
    sql: str = ""
    attempts: int = 0
    errors: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    truncated: bool = False
    seconds: float = 0.0
    raw: list[str] = field(default_factory=list)


class Agent:
    def __init__(self, con, backend: Backend, cards: dict[str, Card], max_repairs: int = 2, timeout_s: float = 20.0,
                 today: dt.date | None = None):
        self.con, self.backend, self.cards = con, backend, cards
        self.max_repairs, self.timeout_s = max_repairs, timeout_s
        self.table_names = set(cards)
        self.context = self._context(today or dt.date.today())

    def _context(self, today: dt.date) -> str:
        """Today's date and what years the data covers, so the model does not take a past season for the future."""
        text = f"Today is {today.isoformat()}."
        try:
            a, b = self.con.execute("select min(year), max(year) from dim_session").fetchone()
            text += f" Timing data (laps, stints, pit stops, weather, race control) covers {a} to {b}, which is in the past."
            c, d = self.con.execute("select min(season), max(season) from fct_season_result").fetchone()
            text += f" Season results and standings cover {c} to {d}."
        except Exception:  # a database without these tables simply gets the date
            pass
        return text

    def _ask(self, out: Outcome, messages):
        reply = self.backend.chat(messages)
        out.raw.append(reply)
        return parse_json(reply), reply

    def route(self, out: Outcome) -> list[str] | None:
        system = ("You route questions about Formula 1 data to database tables. Reply with JSON only.\n"
                  + self.context + "\nTables:\n" + catalogue(self.cards))
        user = (f"Question: {out.question}\n\nReturn {{\"tables\": [up to 4 exact table names needed to answer it]}}. "
                "Return an empty list only when the question is about something that has not happened yet, is an "
                "opinion, or asks for something none of these tables records. A season or race that is within the years "
                "above has already happened and is in the data. When the list is empty, add a \"reason\" field "
                "with one sentence.")
        data, _ = self._ask(out, [{"role": "system", "content": system}, {"role": "user", "content": user}])
        names = [t for t in data.get("tables", []) if isinstance(t, str) and t in self.table_names] if isinstance(data.get("tables"), list) else []
        if not names:
            out.reason = str(data.get("reason", "") or "no table chosen")
            return None
        return names[:4]

    def answer(self, question: str) -> Outcome:
        out = Outcome(question)
        t0 = time.time()
        try:
            tables = self.route(out)
            if tables is None:
                out.refused = True
                return out
            out.tables = tables
            shown = tables + [t for t in ALWAYS if t in self.cards and t not in tables]
            system = ("You write one DuckDB SELECT query that answers a question about Formula 1 data. Reply with JSON only.\n"
                      + self.context + "\n" + NOTES + "\n\n" + "\n\n".join(card_text(self.cards[t]) for t in shown))
            user = (f"Question: {question}\n\nReturn {{\"sql\": \"SELECT ...\"}} with a complete query. Return "
                    "{\"cannot_answer\": \"<one sentence>\"} instead only if these tables really cannot answer it.")
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            for attempt in range(self.max_repairs + 1):
                out.attempts = attempt + 1
                data, reply = self._ask(out, messages)
                if "cannot_answer" in data and not data.get("sql"):
                    out.refused, out.reason = True, str(data["cannot_answer"])
                    return out
                sql = data.get("sql")
                if not isinstance(sql, str) or not sql.strip():
                    err = "the reply was not JSON with an \"sql\" field"
                else:
                    out.sql = sql
                    try:
                        out.columns, out.rows, out.truncated = db.run(self.con, sql, self.timeout_s)
                        return out
                    except (sqlguard.Rejected, db.QueryFailed) as e:
                        err = str(e)
                out.errors.append(err)
                messages += [{"role": "assistant", "content": reply},
                             {"role": "user", "content": f"That failed: {err}\nReturn corrected JSON with an \"sql\" field."}]
            return out
        finally:
            out.seconds = round(time.time() - t0, 2)
