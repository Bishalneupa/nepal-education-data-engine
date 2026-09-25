import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Nepal Education Data Engine", layout="wide")

# Same relative-path trick as extractor.py, so this runs correctly
# no matter what folder you launch it from.
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_PATH = SCRIPT_DIR.parent / "data" / "processed" / "output.csv"

st.title("Nepal Open Education Data Engine")
st.caption("Schools by Province — Flash Report 2082 (2025/26), CEHRD")

df = pd.read_csv(DATA_PATH)

# Lets the viewer pick which provinces to look at. Defaults to all of them.
provinces = df["Province"].tolist()
selected = st.multiselect("Filter by Province", provinces, default=provinces)
filtered = df[df["Province"].isin(selected)]

st.subheader("Data table")
st.dataframe(filtered, use_container_width=True)

# "Nepal" is the national total row, not a real province — it's roughly
# 5x bigger than any single province, so leaving it in the bar chart
# makes every actual province look tiny by comparison. Excluded from
# the chart by default; the checkbox brings it back if you want it.
show_total = st.checkbox("Include national total (Nepal) in chart", value=False)
chart_data = filtered if show_total else filtered[filtered["Province"] != "Nepal"]

st.subheader("Total schools by province")
st.bar_chart(chart_data.set_index("Province")["Total"])