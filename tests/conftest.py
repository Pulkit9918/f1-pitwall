import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "app", ROOT):
    sys.path.insert(0, str(_p))


@pytest.fixture
def lake(tmp_path, monkeypatch):
    """A tiny synthetic lake: three cars on a circular track, six laps."""
    import streamlit as st

    import pitwall as pw
    from synth import make_session

    monkeypatch.setattr(pw, "LAKE", tmp_path)
    monkeypatch.setattr(pw, "MANIFEST", tmp_path / "_manifest" / "sessions.jsonl")
    st.cache_data.clear()
    st.cache_resource.clear()
    make_session(tmp_path)
    yield tmp_path
    st.cache_data.clear()
    st.cache_resource.clear()
