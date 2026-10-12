import history

RACE = {
    "season": "2025", "round": "1", "raceName": "Australian Grand Prix", "date": "2025-03-16",
    "Circuit": {"circuitId": "albert_park"},
    "Results": [
        {"number": "4", "position": "1", "positionText": "1", "points": "25",
         "Driver": {"driverId": "norris", "permanentNumber": "1", "code": "NOR",
                    "givenName": "Lando", "familyName": "Norris"},
         "Constructor": {"constructorId": "mclaren", "name": "McLaren"},
         "grid": "1", "laps": "57", "status": "Finished",
         "Time": {"millis": "6126304", "time": "1:42:06.304"},
         "FastestLap": {"rank": "1", "lap": "43", "Time": {"time": "1:22.167"}}},
        {"number": "1", "position": "2", "positionText": "2", "points": "18",
         "Driver": {"driverId": "max_verstappen", "permanentNumber": "3", "code": "VER",
                    "givenName": "Max", "familyName": "Verstappen"},
         "Constructor": {"constructorId": "red_bull", "name": "Red Bull"},
         "grid": "3", "laps": "57", "status": "Finished",
         "Time": {"millis": "6127199", "time": "+0.895"},
         "FastestLap": {"rank": "3", "lap": "43", "Time": {"time": "1:23.081"}}},
    ],
}


def test_num():
    assert history.num("5") == 5.0
    assert history.num(None) is None
    assert history.num("x") is None


def test_collect_results(monkeypatch):
    def fake_pages(path, pause):
        yield {"limit": "100", "offset": "0", "total": "2",
               "RaceTable": {"season": "2025", "Races": [RACE]}}

    monkeypatch.setattr(history, "pages", fake_pages)
    rows = history.collect_results("2025", 0)
    assert len(rows) == 2
    first = rows[0]
    assert first["driver"] == "Lando Norris"
    assert first["constructor"] == "McLaren"
    assert first["points"] == 25.0
    assert first["grid"] == 1.0
    assert first["position"] == 1.0
    assert first["time_ms"] == 6126304.0
    assert first["fastest_time"] == "1:22.167"
    assert first["season"] == 2025 and first["round"] == 1


def test_collect_driver_standings(monkeypatch):
    page = {"StandingsTable": {"StandingsLists": [{
        "season": "1950", "round": "7", "DriverStandings": [{
            "position": "1", "positionText": "1", "points": "30", "wins": "3",
            "Driver": {"driverId": "farina", "givenName": "Nino", "familyName": "Farina"},
            "Constructors": [{"constructorId": "alfa", "name": "Alfa Romeo"}]}]}]}}
    monkeypatch.setattr(history, "pages", lambda path, pause: iter([page]))
    rows = history.collect_driver_standings("1950", 0)
    assert rows[0]["driver"] == "Nino Farina"
    assert rows[0]["points"] == 30.0 and rows[0]["wins"] == 3.0
    assert rows[0]["constructor"] == "Alfa Romeo"
    assert rows[0]["round"] == 7


def test_collect_constructor_standings(monkeypatch):
    page = {"StandingsTable": {"StandingsLists": [{
        "season": "2025", "round": "24", "ConstructorStandings": [{
            "position": "1", "positionText": "1", "points": "833", "wins": "14",
            "Constructor": {"constructorId": "mclaren", "name": "McLaren",
                            "nationality": "British"}}]}]}}
    monkeypatch.setattr(history, "pages", lambda path, pause: iter([page]))
    rows = history.collect_constructor_standings("2025", 0)
    assert rows[0]["constructor"] == "McLaren"
    assert rows[0]["points"] == 833.0 and rows[0]["wins"] == 14.0


class FakeResponse:
    def __init__(self, status, data=None, headers=None):
        self.status_code = status
        self._data = data or {}
        self.headers = headers or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_get_retries_after_a_429_and_then_serves_from_the_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "RAW", tmp_path)
    monkeypatch.setattr(history.time, "sleep", lambda s: None)
    answers = [FakeResponse(429, headers={"Retry-After": "0"}), FakeResponse(200, {"ok": 1})]
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return answers.pop(0)

    monkeypatch.setattr(history.requests, "get", fake_get)
    assert history.get("seasons.json?limit=1", 0) == {"ok": 1}
    assert len(calls) == 2
    assert history.get("seasons.json?limit=1", 0) == {"ok": 1}      # raw cache: no new request
    assert len(calls) == 2


def test_pages_follows_the_offsets(monkeypatch):
    paths = []

    def fake_get(path, pause):
        paths.append(path)
        return {"MRData": {"limit": "100", "offset": "0", "total": "250"}}

    monkeypatch.setattr(history, "get", fake_get)
    pages = list(history.pages("2025/results.json", 0))
    assert len(pages) == 3
    assert paths[-1].endswith("limit=100&offset=200")
