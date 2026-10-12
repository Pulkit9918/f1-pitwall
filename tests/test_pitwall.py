import pitwall as pw


def test_fmt_lap():
    assert pw.fmt_lap(95.123) == "1:35.123"
    assert pw.fmt_lap(5.2) == "0:05.200"
    assert pw.fmt_lap(None) == ""
    assert pw.fmt_lap(float("nan")) == ""


def test_unit_conversions():
    assert pw.spd(100, False) == 100
    assert abs(pw.spd(100, True) - 62.1371) < 1e-3
    assert pw.tmp(0, True) == 32
    assert pw.tmp(100, True) == 212
    assert pw.spd_unit(True) == "mph"
    assert pw.spd_unit(False) == "km/h"


def test_partition_path(tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "LAKE", tmp_path)
    p = pw.part("laps", 2025, 3, "FP1")
    assert p == tmp_path / "laps" / "year=2025" / "round=03" / "session=FP1" / "part.parquet"
