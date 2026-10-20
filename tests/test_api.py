import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
duckdb = pytest.importorskip("duckdb")
from fastapi.testclient import TestClient  # noqa: E402

from api import main  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "gold.duckdb"
    con = duckdb.connect(str(tmp_path / "build.duckdb"))
    con.execute("create schema gold")
    con.execute("""create table gold.dim_session as select * from (values
        ('2025-R01-R', 2025, 1, 'R', 'Race', 'Australian Grand Prix', true, true, true),
        ('2025-R01-Q', 2025, 1, 'Q', 'Qualifying', 'Australian Grand Prix', true, true, true),
        ('2024-R02-R', 2024, 2, 'R', 'Race', 'Saudi Arabian Grand Prix', true, true, true)
      ) t(session_key, year, round, session_code, session_name, event, has_laps, has_results, has_race_control)""")
    con.execute("""create table gold.fct_lap as select * from (values
        ('2025-R01-R', 'VER', 1, true, 90.5), ('2025-R01-R', 'VER', 2, false, 95.0),
        ('2025-R01-R', 'HAM', 1, true, 91.0), ('2025-R01-R', 'HAM', 2, true, 'nan'::double)
      ) t(session_key, driver_code, lap_number, is_clean_lap, lap_time_s)""")
    con.execute("""create table gold.fct_pit_stop as select * from (values
        ('2025-R01-R', 'VER', 20, 22.1), ('2025-R01-R', 'HAM', 18, 23.4)) t(session_key, driver_code, in_lap, pit_lane_time_s)""")
    con.execute("""create table gold.fct_stint as select * from (values
        ('2025-R01-R', 'VER', 1, 'MEDIUM'), ('2025-R01-R', 'VER', 2, 'HARD')) t(session_key, driver_code, stint, compound)""")
    con.execute("""create table gold.fct_stint_degradation as select * from (values
        ('2025-R01-R', 'VER', 1, 0.05)) t(session_key, driver_code, stint, degradation_s_per_lap)""")
    con.execute("""create table gold.fct_race_control_period as select * from (values
        ('2025-R01-R', 2, 'RED'), ('2025-R01-R', 1, 'SC')) t(session_key, period_no, kind)""")
    con.execute("""create table gold.fct_circuit_pit_loss as select * from (values
        ('albert_park', 'Albert Park', 22.5, true), ('imola', 'Imola', 29.5, true), ('tiny', 'Tiny', 40.0, false)
      ) t(circuit_id, circuit_name, median_pit_loss_s, is_reliable)""")
    con.execute("""create table gold.fct_circuit_degradation as select * from (values
        ('albert_park', 'Albert Park', 'SOFT', 0.08, true), ('albert_park', 'Albert Park', 'HARD', 0.03, false),
        ('imola', 'Imola', 'SOFT', 0.06, true)) t(circuit_id, circuit_name, compound, median_degradation_s_per_lap, is_reliable)""")
    con.close()
    (tmp_path / "build.duckdb").rename(path)   # served under a name that would clash with the schema
    monkeypatch.setenv("F1_API_DB", str(path))
    return TestClient(main.app)


def test_health_counts_sessions(client):
    assert client.get("/health").json() == {"status": "ok", "sessions": 3}


def test_sessions_filter_and_order(client):
    r = client.get("/sessions", params={"year": 2025})
    assert [s["session_key"] for s in r.json()] == ["2025-R01-Q", "2025-R01-R"]
    assert client.get("/sessions", params={"round": 2, "session_code": "R"}).json()[0]["event"].startswith("Saudi")


def test_unknown_session_is_404_everywhere(client):
    for path in ("", "/laps", "/stints", "/stint-degradation", "/pit-stops", "/race-control-periods"):
        assert client.get(f"/sessions/nope{path}").status_code == 404


def test_laps_filters_and_nan_becomes_null(client):
    laps = client.get("/sessions/2025-R01-R/laps").json()
    assert len(laps) == 4
    assert [(x["driver_code"], x["lap_number"]) for x in laps] == [("HAM", 1), ("HAM", 2), ("VER", 1), ("VER", 2)]
    assert laps[1]["lap_time_s"] is None
    clean = client.get("/sessions/2025-R01-R/laps", params={"clean_only": True}).json()
    assert len(clean) == 3
    only = client.get("/sessions/2025-R01-R/laps", params={"driver_code": "VER", "clean_only": True}).json()
    assert [x["lap_number"] for x in only] == [1]


def test_values_are_parameters_not_sql(client):
    r = client.get("/sessions/2025-R01-R/laps", params={"driver_code": "x' or '1'='1"})
    assert r.status_code == 200 and r.json() == []
    assert client.get("/sessions/2025-R01-R'; drop table gold.fct_lap; --/laps").status_code == 404
    assert client.get("/sessions/2025-R01-R/laps").status_code == 200


@pytest.mark.parametrize("limit", [0, -1, main.MAX_LIMIT + 1])
def test_limit_is_validated(client, limit):
    assert client.get("/sessions", params={"limit": limit}).status_code == 422


def test_limit_applies(client):
    assert len(client.get("/sessions/2025-R01-R/laps", params={"limit": 2}).json()) == 2


def test_session_tables(client):
    assert [p["kind"] for p in client.get("/sessions/2025-R01-R/race-control-periods").json()] == ["SC", "RED"]
    assert client.get("/sessions/2025-R01-R/pit-stops").json()[0]["driver_code"] == "HAM"
    assert len(client.get("/sessions/2025-R01-R/stints").json()) == 2
    assert client.get("/sessions/2025-R01-R/stint-degradation", params={"driver_code": "VER"}).json()[0]["degradation_s_per_lap"] == 0.05


def test_circuit_endpoints(client):
    reliable = client.get("/circuits/pit-loss").json()
    assert [c["circuit_id"] for c in reliable] == ["imola", "albert_park"]
    assert len(client.get("/circuits/pit-loss", params={"reliable_only": False}).json()) == 3
    deg = client.get("/circuits/degradation").json()
    assert [(d["circuit_id"], d["compound"]) for d in deg] == [("albert_park", "SOFT"), ("imola", "SOFT")]
    assert [d["compound"] for d in client.get("/circuits/degradation", params={"compound": "HARD", "reliable_only": False}).json()] == ["HARD"]


def test_missing_database_is_503(tmp_path, monkeypatch):
    monkeypatch.setenv("F1_API_DB", str(tmp_path / "absent.duckdb"))
    r = TestClient(main.app).get("/health")
    assert r.status_code == 503 and "build" in r.json()["detail"]


def test_locked_database_is_503(client, tmp_path, monkeypatch):
    import os
    path = os.environ["F1_API_DB"]
    writer = duckdb.connect(path)          # holds the write lock, as a dbt build would
    try:
        assert client.get("/health").status_code == 503
    finally:
        writer.close()
    assert client.get("/health").status_code == 200


def test_every_endpoint_works_on_the_real_gold_database_if_present(monkeypatch):
    from pathlib import Path
    real = Path(main.__file__).resolve().parents[1] / "data" / "f1_dbt.duckdb"
    if not real.exists():
        pytest.skip("no real gold database here")
    monkeypatch.delenv("F1_API_DB", raising=False)
    c = TestClient(main.app)
    first = c.get("/sessions", params={"session_code": "R", "year": 2025, "limit": 1})
    if first.status_code != 200:
        pytest.skip(f"real database not readable: {first.status_code}")
    key = first.json()[0]["session_key"]
    for path in ("", "/laps", "/stints", "/stint-degradation", "/pit-stops", "/race-control-periods"):
        assert c.get(f"/sessions/{key}{path}", params={"limit": 5} if path else None).status_code == 200, path
    assert c.get("/circuits/pit-loss", params={"limit": 5}).status_code == 200
    assert c.get("/circuits/degradation", params={"limit": 5}).status_code == 200
