import streamlit as st

import pitwall as pw

st.set_page_config(page_title="F1 Pitwall", layout="wide")
st.title("F1 Pitwall")
st.write("Lap times, tyre strategy, track maps and telemetry from the sessions ingested so far. "
         "Use the pages in the sidebar.")

df = pw.sessions()
if df.empty:
    st.warning("No data found in data/lake yet.")
    st.stop()

a, b, c, d = st.columns(4)
a.metric("Sessions", len(df))
b.metric("Seasons", df["year"].nunique())
c.metric("With telemetry", int(df["telemetry"].sum()))
d.metric("Data", f"{df['mb'].sum():.0f} MB")

summary = df.groupby("year").agg(
    sessions=("session", "count"), telemetry=("telemetry", "sum"), mb=("mb", "sum"))
st.dataframe(summary.round(1).sort_index(ascending=False))
