"""Pure parsers for race control messages: flag periods, events, stewards' status, lap deletions
and restart times. No Streamlit and no file access, so they can be tested directly.

Expects a DataFrame with the columns Time (UTC timestamp), t (session seconds), Category, Message,
Flag, Scope, Sector and Lap."""

import re
from collections import Counter

import numpy as np
import pandas as pd


def steward_status(rc, names):
    """Latest investigation / penalty state per driver from the message text."""
    out = {n: "" for n in names}
    for msg in rc["Message"].astype(str):
        up = msg.upper()
        for c in re.findall(r"\(([A-Z]{3})\)", up):
            if c not in out:
                continue
            if "NO FURTHER" in up or "NO INVESTIGATION" in up:
                out[c] = ""
            elif "PENALTY SERVED" in up:
                out[c] = "served"
            elif "PENALTY" in up:
                m = re.search(r"(\d+) SECOND", up)
                out[c] = f"PEN {m.group(1)}s" if m else "PEN"
            elif "UNDER INVESTIGATION" in up or "NOTED" in up:
                out[c] = "INV"
    return out


def build_periods(d, grid, lead, end):
    """Safety car, VSC and red flag periods (session seconds) from the message wording.

    grid / lead: the leader's progress over time, used to place each period on the lap axis."""
    periods, cur = [], None

    def close(t1):
        nonlocal cur
        if cur is not None:
            cur["t1"] = t1
            periods.append(cur)
            cur = None

    for r in d.itertuples():
        msg = str(r.Message).upper()
        flag = str(r.Flag).upper() if pd.notna(r.Flag) else ""
        t = float(r.t)
        if "BEHIND SAFETY CAR" in msg or "FORMATION" in msg:
            continue
        is_red = (flag == "RED" or msg.startswith("RED FLAG")) and "INFRINGEMENT" not in msg
        is_sc = "SAFETY CAR DEPLOYED" in msg and "VIRTUAL" not in msg
        is_vsc = "VSC DEPLOYED" in msg or "VIRTUAL SAFETY CAR DEPLOYED" in msg
        is_vsc_end = "VSC ENDING" in msg or "VIRTUAL SAFETY CAR ENDING" in msg
        if is_red:
            if not (cur and cur["kind"] == "RED"):
                close(t)
                cur = {"kind": "RED", "t0": t}
            continue
        if cur and cur["kind"] == "RED":
            if is_sc or "PIT EXIT OPEN" in msg or "TRACK CLEAR" in msg or "RACE START" in msg:
                close(t)
            else:
                continue                      # still red-flagged
        if is_sc:
            close(t)
            cur = {"kind": "SC", "t0": t}
        elif is_vsc:
            close(t)
            cur = {"kind": "VSC", "t0": t}
        elif cur and cur["kind"] == "SC":
            if "LIGHTS OFF" in msg:
                cur.setdefault("t_off", t)
            elif "IN THIS LAP" in msg:
                cur.setdefault("t_in", t)
            elif "TRACK CLEAR" in msg:
                close(t)
        elif cur and cur["kind"] == "VSC" and is_vsc_end:
            close(t)
    close(end)
    periods = [q for q in periods if q["t1"] > q["t0"]]
    for q in periods:
        q["p0"] = float(np.interp(q["t0"], grid, lead))
        q["p1"] = float(np.interp(q["t1"], grid, lead))
    return periods


def build_events(d, start, duration):
    """Race events for a jump-to-event box: safety cars, red flags, yellows, stewards' decisions."""
    out, seen = [], set()
    for r in d.itertuples():
        msg = str(r.Message).upper()
        flag = str(r.Flag).upper() if pd.notna(r.Flag) else ""
        scope = str(r.Scope) if pd.notna(r.Scope) else ""
        keep = (str(r.Category) == "SafetyCar" or flag in ("RED", "CHEQUERED")
                or msg.startswith("RED FLAG")
                or (scope == "Sector" and flag in ("YELLOW", "DOUBLE YELLOW"))
                or ("FIA STEWARDS" in msg and ("PENALTY" in msg or "INVESTIGAT" in msg)))
        t_race = float(r.t) - start
        if not keep or t_race < -5 or t_race > duration + 5:
            continue
        sig = (round(t_race), msg)
        if sig in seen:
            continue
        seen.add(sig)
        lap = int(r.Lap) if pd.notna(r.Lap) else None
        mm, ss = divmod(int(max(0, t_race)), 60)
        out.append({"t": max(0.0, t_race),
                    "label": f"L{lap if lap is not None else '-'} | {mm}:{ss:02d} | {msg[:80]}"})
    return out[:200]


def deleted_laps(d):
    """Lap-time deletions (track limits and similar) from messages such as
    'CAR 63 (RUS) TIME 1:20.011 DELETED - TRACK LIMITS AT TURN 12 LAP 5 11:30:13'."""
    rows = []
    for r in d.itertuples():
        up = str(r.Message).upper()
        if "DELETED" not in up:
            continue
        m = re.search(r"\(([A-Z]{3})\)", up)
        if not m:
            continue
        lap = re.search(r"\bLAP (\d+)\b", up)
        reason = up.split(" - ", 1)[1] if " - " in up else ""
        reason = re.sub(r"\s*\bLAP \d+.*$", "", reason).strip()
        rows.append({"t": float(r.t), "driver": m.group(1),
                     "lap": int(lap.group(1)) if lap else None, "reason": reason})
    return pd.DataFrame(rows, columns=["t", "driver", "lap", "reason"])


def estimate_tz_offset(d):
    """Local-time offset from UTC in seconds, from messages that quote a local clock time
    (for example 'TIMED AT 20:38:16' next to a UTC timestamp of 12:38:16). None if unknown."""
    votes = Counter()
    for r in d.itertuples():
        text = str(r.Message).upper()
        if "RESUME" in text or "ESTIMATED" in text:
            continue
        for hh, mm, ss in re.findall(r"\b(\d{1,2}):(\d{2}):(\d{2})\b", text):
            local = int(hh) * 3600 + int(mm) * 60 + int(ss)
            ts = pd.Timestamp(r.Time)
            utc = ts.hour * 3600 + ts.minute * 60 + ts.second
            diff = (local - utc + 12 * 3600) % 86400 - 12 * 3600
            off = int(round(diff / 900.0)) * 900
            if -12 * 3600 <= off <= 14 * 3600:
                votes[off] += 1
    return votes.most_common(1)[0][0] if votes else None


def resume_targets(d, tz_offset):
    """(session second of the announcement, session second of the announced restart)."""
    out = []
    if tz_offset is None:
        return out
    for r in d.itertuples():
        up = str(r.Message).upper()
        m = re.search(r"(?:RESUME AT|RESUMPTION -) (\d{1,2}):(\d{2})", up)
        if not m:
            continue
        local = int(m.group(1)) * 3600 + int(m.group(2)) * 60
        ts = pd.Timestamp(r.Time)
        msg_utc = ts.hour * 3600 + ts.minute * 60 + ts.second
        delta = (local - tz_offset - msg_utc) % 86400
        if delta > 43200:
            delta -= 86400
        out.append((float(r.t), float(r.t) + delta))
    return out
