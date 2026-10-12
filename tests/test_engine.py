import numpy as np
import pytest

import engine as eg


def test_rotate_quarter_turn():
    out = eg.rotate(np.array([[1.0, 0.0]]), 90)
    assert np.allclose(out, [[0.0, 1.0]], atol=1e-9)


def test_project_onto_a_straight_line():
    ref = np.array([[0.0, 0.0], [50.0, 0.0], [100.0, 0.0]])
    s = np.array([0.0, 50.0, 100.0])
    s_out, d_out = eg.project(np.array([[30.0, 5.0], [90.0, -2.0]]), ref, s)
    assert np.allclose(s_out, [30.0, 90.0])
    assert np.allclose(d_out, [5.0, 2.0])


def test_build_and_snapshot_on_a_synthetic_circuit(lake):
    state = eg.build(2099, 1, "R")
    assert state is not None
    assert set(state["drivers"]) == {"AAA", "BBB", "CCC"}
    assert state["drivers"]["AAA"]["approx"] == set()

    snap = eg.snapshot(state, 200.0)
    assert list(snap["driver"]) == ["AAA", "BBB", "CCC"]
    progress = dict(zip(snap["driver"], snap["P"]))
    assert progress["AAA"] == pytest.approx(200 / 90, abs=0.02)
    assert progress["BBB"] == pytest.approx(200 / 91, abs=0.02)
    assert progress["CCC"] == pytest.approx(200 / 95, abs=0.02)
    # B reached A's current spot 2.2 s ago; C reached B's spot 8.4 s ago
    gaps = dict(zip(snap["driver"], snap["int_s"]))
    assert gaps["BBB"] == pytest.approx(2.2, abs=0.5)
    assert gaps["CCC"] == pytest.approx(8.4, abs=0.8)


def test_finished_cars_are_marked(lake):
    state = eg.build(2099, 1, "R")
    snap = eg.snapshot(state, 545.0)
    assert list(snap["driver"]) == ["AAA", "BBB", "CCC"]
    status = dict(zip(snap["driver"], snap["status"]))
    assert status["AAA"] == "FIN"
    assert status["CCC"] == ""
