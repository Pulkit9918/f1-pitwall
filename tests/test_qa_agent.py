"""Tests for the question-answering agent: the SQL gate, the scoring, the question set and the agent loop, with a
scripted model and a tiny database. No model, network or real data is needed."""
import json
import re
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qa_agent import agent as ag  # noqa: E402
from qa_agent import compare, db, evaluate, report, run_eval, sqlguard  # noqa: E402
from qa_agent.questions import BY_ID, QUESTIONS  # noqa: E402


# ---------------------------------------------------------------- the SQL gate
@pytest.mark.parametrize("sql", [
    "select 1", "SELECT * FROM fct_lap LIMIT 5;", "with a as (select 1) select * from a", "select 'drop table x'",
    "select event from dim_session where event ilike '%set%'", "select sessions_loaded from fct_ingest_summary",
    "-- comment\nselect 1", "select \"year\" from dim_session",
])
def test_gate_accepts(sql):
    assert sqlguard.check(sql)


@pytest.mark.parametrize("sql", [
    "", "drop table dim_session", "select 1; select 2", "delete from fct_lap", "attach 'x.db' as y",
    "copy fct_lap to 'x.csv'", "select * from read_csv('x.csv')", "install httpfs", "pragma database_list",
    "create table t as select 1", "set schema = 'main'", "insert into t values (1)", "update t set a = 1",
    "select 1 /* hidden */; drop table t", "call dbgen(sf=1)", "export database 'x'",
])
def test_gate_rejects(sql):
    with pytest.raises(sqlguard.Rejected):
        sqlguard.check(sql)


# ---------------------------------------------------------------- scoring
def test_compare_basics():
    assert compare.matches([("VER",)], [("ver ",)])
    assert compare.matches([("VER",)], [("VER", "Max Verstappen")])  # extra columns are fine
    assert not compare.matches([("VER",)], [("HAM",)])
    assert not compare.matches([("VER",)], [("VER",), ("HAM",)])
    assert compare.matches([(18,)], [(18,), (18,), (18,)])  # the same row repeated is still the answer
    assert not compare.matches([(18,)], [(18,), (19,)])
    assert not compare.matches([("VER", 1)], [("VER",)])  # a missing column is not
    assert compare.matches([(5,)], [(5.0,)])
    assert not compare.matches([(5,)], [(6,)])
    assert compare.matches([(19.234,)], [(19.2349,)], tol=0.01)
    assert not compare.matches([(0.7935,)], [(0.7966,)], tol=0.0005)


def test_compare_order_and_columns():
    assert compare.matches([("a",), ("b",)], [("b",), ("a",)])
    assert not compare.matches([("a",), ("b",)], [("b",), ("a",)], ordered=True)
    assert compare.matches([("HAM", 72.5)], [("Lewis", 72.5, "HAM")])
    assert compare.matches([(2022, 10), (2023, 20)], [(2023, 20), (2022, 10)])
    # the same values paired differently are a different answer
    assert not compare.matches([(2022, 10), (2023, 20)], [(2022, 20), (2023, 10)])
    assert compare.matches([(None,)], [(None,)])
    assert compare.matches([], [])
    assert not compare.matches([], [("x",)])


def test_parse_json():
    assert ag.parse_json('{"sql": "select 1"}') == {"sql": "select 1"}
    assert ag.parse_json('Sure! {"tables": ["a"]} done') == {"tables": ["a"]}
    assert ag.parse_json("no json") == {}
    assert ag.parse_json("[1, 2]") == {}
    assert ag.parse_json("{broken") == {}


# ---------------------------------------------------------------- the question set
def test_question_set_is_sound():
    assert len(QUESTIONS) >= 40
    assert sum(not q.answerable for q in QUESTIONS) >= 8
    for q in QUESTIONS:
        assert q.question.endswith(("?", ".")), q.id
        if q.answerable:
            assert q.tables, q.id
            sqlguard.check(q.sql)
            for t in q.tables:
                assert re.search(rf"\b{t}\b", q.sql), f"{q.id}: lists {t} but the SQL does not use it"
            used = set(re.findall(r"\b(?:from|join)\s+(\w+)", q.sql, flags=re.I))
            assert used <= set(q.tables), f"{q.id}: SQL uses {used - set(q.tables)}"
        else:
            assert not q.tables, q.id
    assert len(BY_ID) == len(QUESTIONS)


# ---------------------------------------------------------------- the agent loop
@pytest.fixture()
def dbfile(tmp_path):
    p = tmp_path / "t.duckdb"
    c = duckdb.connect(str(p))
    c.execute("create schema gold")
    c.execute("create table gold.dim_session (session_key varchar, year integer, event varchar, session_code varchar)")
    c.execute("insert into gold.dim_session values ('2025-R14-R', 2025, 'Italian Grand Prix', 'R'), ('2024-R14-R', 2024, 'Italian Grand Prix', 'R')")
    c.execute("create table gold.fct_result (session_key varchar, driver_code varchar, position integer)")
    c.execute("insert into gold.fct_result values ('2025-R14-R', 'VER', 1), ('2025-R14-R', 'NOR', 2), ('2024-R14-R', 'LEC', 1)")
    c.execute("create table gold.fct_lap_sample (lap_key varchar)")  # excluded from the agent's tables
    c.close()
    return p


class Scripted(ag.Backend):
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def chat(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0)


def make(dbfile, replies, **kw):
    con = db.connect(dbfile)
    return ag.Agent(con, Scripted(replies), ag.load_cards(con, None), **kw)


def test_agent_tables_exclude_heavy_views(dbfile):
    assert db.tables(db.connect(dbfile)) == ["dim_session", "fct_result"]


def test_writer_always_sees_dim_session_and_the_date(dbfile):
    import datetime as dt
    con = db.connect(dbfile)
    a = ag.Agent(con, Scripted(['{"tables": ["fct_result"]}', '{"sql": "select 1"}']), ag.load_cards(con, None), today=dt.date(2026, 10, 29))
    a.answer("q")
    writer_prompt = a.backend.calls[1][0]["content"]
    assert "Table dim_session" in writer_prompt and "Today is 2026-10-29" in writer_prompt
    assert "Timing data" in a.backend.calls[0][0]["content"]  # the router is told what years exist


def test_agent_answers(dbfile):
    a = make(dbfile, ['{"tables": ["fct_result", "dim_session"]}',
                      '{"sql": "select r.driver_code from fct_result r join dim_session s using (session_key) '
                      "where s.year = 2025 and r.position = 1\"}"])
    o = a.answer("Who won the 2025 Italian Grand Prix?")
    assert not o.refused and o.attempts == 1 and o.rows == [("VER",)] and o.tables == ["fct_result", "dim_session"]


def test_agent_repairs_after_an_error(dbfile):
    a = make(dbfile, ['{"tables": ["fct_result"]}', '{"sql": "select driver from fct_result"}',
                      '{"sql": "select driver_code from fct_result where position = 1 and session_key like \'2025%\'"}'])
    o = a.answer("q")
    assert o.attempts == 2 and o.rows == [("VER",)] and len(o.errors) == 1
    assert "failed" in a.backend.calls[-1][-1]["content"]


def test_agent_gives_up_after_the_repairs(dbfile):
    a = make(dbfile, ['{"tables": ["fct_result"]}'] + ['{"sql": "select nope from fct_result"}'] * 3)
    o = a.answer("q")
    assert o.attempts == 3 and not o.rows and not o.refused and len(o.errors) == 3


def test_agent_refuses_at_routing(dbfile):
    o = make(dbfile, ['{"tables": [], "reason": "future event"}']).answer("Who will win next year?")
    assert o.refused and "future" in o.reason and not o.sql


def test_agent_refuses_at_writing(dbfile):
    o = make(dbfile, ['{"tables": ["fct_result"]}', '{"cannot_answer": "no salary column"}']).answer("q")
    assert o.refused and "salary" in o.reason


def test_agent_ignores_unknown_tables(dbfile):
    o = make(dbfile, ['{"tables": ["made_up_table"]}']).answer("q")
    assert o.refused


def test_agent_blocks_writes(dbfile):
    a = make(dbfile, ['{"tables": ["fct_result"]}', '{"sql": "drop table fct_result"}', '{"cannot_answer": "x"}'])
    o = a.answer("q")
    assert o.refused and any("not allowed" in e or "SELECT" in e for e in o.errors)
    assert db.connect(dbfile).execute("select count(*) from gold.fct_result").fetchone()[0] == 3


def test_read_only_connection_cannot_write(dbfile):
    with pytest.raises(duckdb.Error):
        db.connect(dbfile).execute("create table gold.x (a int)")


# ---------------------------------------------------------------- scoring and the whole run
def test_score_and_summary():
    q = BY_ID["winner_2025_italy"]
    good = ag.Outcome(q.question, tables=list(q.tables), sql="select 1", columns=["c"], rows=[("VER",)], attempts=1)
    bad = ag.Outcome(q.question, tables=["fct_lap"], sql="select 1", columns=["c"], rows=[("HAM",)], attempts=2)
    s1, s2 = evaluate.score(q, good, [("VER",)]), evaluate.score(q, bad, [("VER",)])
    assert s1["correct"] and s1["route_recall"] and s1["first_try"]
    assert not s2["correct"] and not s2["route_recall"] and not s2["first_try"]
    u = BY_ID["next_race_winner"]
    assert evaluate.score(u, ag.Outcome(u.question, refused=True), None)["correct"]
    empty = evaluate.score(u, ag.Outcome(u.question, sql="select max(x) from t", columns=["c"], rows=[(None,)], attempts=1), None)
    assert empty["correct"] and empty["no_data"]  # a query that finds nothing is not a made-up answer
    assert not evaluate.score(u, ag.Outcome(u.question, sql="select 1", columns=["c"], rows=[("VER",)], attempts=1), None)["correct"]
    sm = evaluate.summarise([s1, s2, evaluate.score(u, ag.Outcome(u.question, refused=True), None)])
    assert sm["answerable"] == 2 and sm["correct_answerable"] == 1 and sm["correct_refusals"] == 1 and sm["accuracy"] == 0.5


def test_whole_run_and_report(dbfile, tmp_path, monkeypatch):
    class Fake(ag.Backend):
        def __init__(self, *a, **k):
            pass

        def chat(self, messages):
            user = messages[-1]["content"]
            if "route" in messages[0]["content"]:
                return '{"tables": [], "reason": "no"}' if "next Formula 1 race" in user else '{"tables": ["fct_result", "dim_session"]}'
            return '{"sql": "select driver_code from fct_result r join dim_session s using (session_key) where s.year = 2025 and position = 1"}'

    monkeypatch.setattr(ag, "Ollama", Fake)
    # the reference queries need the full schema, so point the run at two questions that fit the tiny database
    monkeypatch.setattr(run_eval, "QUESTIONS", [BY_ID["winner_2025_italy"], BY_ID["next_race_winner"]])
    # the reference SQL uses the same two tables; give the tiny database the columns it needs
    c = duckdb.connect(str(dbfile))
    c.execute("alter table gold.dim_session add column round integer")
    c.execute("alter table gold.fct_result add column grid_position integer")
    c.close()
    out = tmp_path / "res.json"
    run_eval.main(["--model", "fake:1", "--db", str(dbfile), "--manifest", str(tmp_path / "none.json"), "--out", str(out)])
    data = json.loads(out.read_text())
    assert data["summary"]["correct_answerable"] == 1 and data["summary"]["correct_refusals"] == 1
    monkeypatch.setattr(report, "RES", tmp_path)
    report.main()
    md = (tmp_path / "RESULTS.md").read_text()
    assert "fake:1" in md and "1 of 1" in md
