"""Tests for scripts/export_predictor.py on a small mock gold schema with the real column names."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
SPEC = importlib.util.spec_from_file_location("export_predictor", Path(__file__).resolve().parents[1] / "scripts" / "export_predictor.py")
mod = importlib.util.module_from_spec(SPEC)
sys.modules["export_predictor"] = mod
SPEC.loader.exec_module(mod)


@pytest.fixture()
def db(tmp_path):
    c = duckdb.connect(str(tmp_path / "g.duckdb"))
    c.execute("create schema gold")
    c.execute("""create table gold.fct_pit_prediction_check(pit_stop_key varchar, session_key varchar, year int, round int, driver_code varchar, in_lap int,
                 regime varchar, position_now int, predicted_position int, predicted_position_fast int, predicted_position_slow int, actual_position int,
                 margin_s double, other_stops_nearby int)""")
    c.execute("""create table gold.fct_pit_prediction_score(scope varchar, regime varchar, margin_bucket varchar, stops int, hit_rate double, within_one_rate double,
                 mae double, bias double, in_range_rate double, no_loss_hit_rate double, no_loss_mae double, global_hit_rate double, global_mae double, is_reliable boolean)""")
    c.execute("""create table gold.fct_pit_prediction_heldout_score(scope varchar, stops int, in_sample_hit_rate double, held_out_hit_rate double, in_sample_mae double,
                 held_out_mae double, loss_shift_s double, held_out_circuit_share double)""")
    c.execute("insert into gold.fct_pit_prediction_heldout_score values ('all',100,0.8,0.7,0.3,0.45,0.25,0.9),('undisturbed',40,0.85,0.8,0.2,0.3,0.2,0.9)")
    c.execute("create table gold.dim_session_circuit(session_key varchar, event varchar)")
    c.execute("insert into gold.dim_session_circuit values ('2025-R01-R','Synth GP'),('2019-R01-R','Old GP')")
    c.execute("insert into gold.fct_pit_prediction_check values ('a','2025-R01-R',2025,1,'AAA',20,'green',3,5,4,6,6,0.7,0),('b','2025-R01-R',2025,1,'BBB',10,'sc',2,3,3,4,3,NULL,1),('z','2019-R01-R',2019,1,'ZZZ',5,'green',1,2,2,2,2,1.0,0)")
    c.execute("insert into gold.fct_pit_prediction_score values ('all','all','all',3,0.5,0.9,0.6,-0.2,1.0,0.1,2.0,0.4,0.7,false)")
    c.close()
    return tmp_path / "g.duckdb"


def test_stops_are_columns_in_lap_order_and_score_rows_are_named(db, tmp_path):
    out = tmp_path / "out"
    assert mod.export(db, out, from_year=2022, log=lambda *_: None) == {"stops": 2, "sessions": 1, "rows": 1}
    stops = json.loads((out / "stops.json").read_text())
    assert stops["sessions"] == [{"key": "2025-R01-R", "year": 2025, "round": 1, "event": "Synth GP"}]
    assert stops["d"] == ["BBB", "AAA"] and stops["l"] == [10, 20] and stops["r"] == ["s", "g"]
    assert stops["p"] == [3, 5] and stops["f"] == [3, 4] and stops["w"] == [4, 6] and stops["a"] == [3, 6] and stops["m"] == [None, 0.7] and stops["o"] == [1, 0]
    score = json.loads((out / "score.json").read_text())["rows"][0]
    assert score["scope"] == "all" and score["hit"] == 0.5 and score["no_loss_mae"] == 2.0 and score["reliable"] is False
    held = json.loads((out / "score.json").read_text())["heldout"]
    assert [h["scope"] for h in held] == ["all", "undisturbed"] and held[0]["held_out_hit"] == 0.7 and held[0]["in_sample_mae"] == 0.3 and held[1]["circuit_share"] == 0.9
    assert json.loads((out / "index.json").read_text())["generator"] == "export_predictor"


def test_refuses_a_folder_it_did_not_write(db, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "mine.txt").write_text("keep")
    with pytest.raises(SystemExit):
        mod.export(db, out, log=lambda *_: None)
    assert (out / "mine.txt").read_text() == "keep" and not (out / "index.json").exists()


def test_can_write_again_over_its_own_output(db, tmp_path):
    out = tmp_path / "out"
    mod.export(db, out, from_year=2022, log=lambda *_: None)
    assert mod.export(db, out, from_year=2022, log=lambda *_: None)["stops"] == 2


def test_exports_every_year_by_default(db, tmp_path):
    assert mod.export(db, tmp_path / "out", log=lambda *_: None)["stops"] == 3
