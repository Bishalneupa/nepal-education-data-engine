import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Nepal Education Data Engine", layout="wide")

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data" / "processed"

st.title("Nepal Open Education Data Engine")
st.caption("Flash Report 2082 (2025/26), CEHRD — cleaned tables")


def pretty_label(filename: str) -> str:
    """Turns a filename like table_6_1_teachers_by_gender_basic.csv into
    a readable label like '6 1 teachers by gender basic'."""
    stem = filename.replace(".csv", "")
    if stem.startswith("table_"):
        stem = stem[len("table_"):]
    return stem.replace("_", " ")


# Find every CSV that's actually been extracted so far, regardless of
# whether it came from the original single-table script or the new
# multi-table one.
csv_files = sorted(DATA_DIR.glob("*.csv"))

if not csv_files:
    st.error("No data files found in data/processed. Run extractor.py first.")
    st.stop()

labels = {pretty_label(f.name): f for f in csv_files}
selected_label = st.selectbox("Choose a table", sorted(labels.keys()))
selected_file = labels[selected_label]

df = pd.read_csv(selected_file, dtype=str)

# Every one of these tables is organized by Province, so this filter
# works the same way regardless of which table is selected.
if "Province" in df.columns:
    provinces = df["Province"].tolist()
    selected = st.multiselect("Filter by Province", provinces, default=provinces)
    filtered = df[df["Province"].isin(selected)]
else:
    filtered = df

st.subheader("Data table")
st.dataframe(filtered, use_container_width=True)

# Let the viewer pick which column to chart. Values are stored as text
# (e.g. "8,265") because different tables have different formats, so we
# strip commas and convert to numbers here, just for charting.
numeric_candidates = [c for c in filtered.columns if c != "Province"]

if numeric_candidates:
    chart_column = st.selectbox("Chart which column?", numeric_candidates)
    show_total = st.checkbox("Include national total (Nepal) in chart", value=False)

    chart_df = filtered if show_total else filtered[filtered.get("Province") != "Nepal"]
    chart_values = pd.to_numeric(
        chart_df[chart_column].str.replace(",", "", regex=False),
        errors="coerce"
    )

    st.subheader(f"{chart_column} by Province")
    st.bar_chart(chart_values.set_axis(chart_df["Province"]))