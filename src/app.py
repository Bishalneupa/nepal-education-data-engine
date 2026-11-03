"""
Nepal Open Education Data Engine: dashboard.

Reads every CSV in data/processed and lets you browse it by chapter, chart
any column, download the table, and see where the original CEHRD report
disagrees with itself. Charts are plain HTML/CSS bars on purpose: no chart
library to break between versions, and every bar has a hover label.
"""

import html
import re
from pathlib import Path

import pandas as pd
import streamlit as st

# The extractor's registry tells us which PDF page each table came from.
# If it can't be imported (for example pdfplumber is missing), the dashboard
# still works and simply leaves the page number out.
try:
    from extractor import TABLES as REGISTRY
except Exception:
    REGISTRY = []

REPO_URL = "https://github.com/Bishalneupa/nepal-education-data-engine"
NAVY, BLUE, CRIMSON, GREY = "#14284B", "#2F5D8C", "#B3123C", "#A9B4C2"

st.set_page_config(
    page_title="Nepal Open Education Data Engine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data" / "processed"

STYLE = f"""
<style>
.block-container {{ padding-top: 4.2rem; max-width: 1250px; }}
footer {{ visibility: hidden; }}
.hero {{ background: linear-gradient(135deg, {NAVY} 0%, #1D3F6E 62%, {CRIMSON} 150%);
         color: #fff; padding: 26px 30px; border-radius: 14px; margin-bottom: 20px; }}
.hero-title {{ font-size: 1.95rem; font-weight: 700; line-height: 1.15; margin: 0; }}
.hero-sub {{ margin: 8px 0 0 0; opacity: .88; font-size: 1.0rem; }}
.stat-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 18px; }}
.stat {{ background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.20);
         border-radius: 10px; padding: 9px 14px; min-width: 104px; }}
.stat b {{ display: block; font-size: 1.35rem; }}
.stat span {{ font-size: .72rem; opacity: .85; text-transform: uppercase; letter-spacing: .06em; }}
.bars {{ margin: 6px 0 14px 0; }}
.bar-row {{ display: flex; align-items: center; gap: 12px; margin: 5px 0; }}
.bar-label {{ flex: 0 0 210px; font-size: .88rem; text-align: right; overflow: hidden;
              text-overflow: ellipsis; white-space: nowrap; }}
.bar-track {{ flex: 1; background: rgba(128,128,128,.14); border-radius: 5px; height: 22px; }}
.bar-fill {{ height: 100%; border-radius: 5px; min-width: 2px; }}
.bar-value {{ flex: 0 0 96px; font-size: .88rem; font-variant-numeric: tabular-nums; }}
.group-title {{ font-weight: 600; margin: 14px 0 2px 0; }}
.legend {{ font-size: .8rem; opacity: .85; margin-bottom: 4px; }}
.legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px;
             margin: 0 5px 0 12px; }}
.legend i:first-child {{ margin-left: 0; }}
.foot {{ opacity: .7; font-size: .82rem; margin-top: 28px; }}
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)

# ----------------------------------------------------------------- catalog

CHAPTERS = {
    2: "Early childhood education (ECED)",
    3: "Schools",
    4: "Basic level (Grades 1-8)",
    5: "Secondary level (Grades 9-12)",
    6: "Teachers",
}
CHAPTER_ORDER = ["Key findings"] + list(CHAPTERS.values()) + ["KPI framework", "Other tables"]
ACRONYMS = {"eced", "ger", "ner", "gir", "nir", "str", "clcs", "sip", "oosc", "kpi", "sesp", "iemis"}


def humanize(slug):
    """'infrastructure_basic_1_5_community' -> 'Infrastructure basic 1-5 community'."""
    slug = re.sub(r"(?:(?<=_)|^)(\d+)_(\d+)(?=_|$)", r"\1-\2", slug)
    words = [w.upper() if w in ACRONYMS else w for w in slug.split("_") if w]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def describe(stem):
    """Work out chapter, sort order and a readable title from a file name."""
    name = stem[len("table_"):] if stem.startswith("table_") else stem
    m = re.match(r"^kf(\d+)_(.*)$", name)
    if m:
        n = int(m.group(1))
        return {"chapter": "Key findings", "order": (1, n),
                "title": f"Key finding {n}: {humanize(m.group(2))}"}
    m = re.match(r"^(\d+)_(\d+)_(.*)$", name)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return {"chapter": CHAPTERS.get(a, "Other tables"), "order": (10 + a, b),
                "title": f"Table {a}.{b}: {humanize(m.group(3))}"}
    if "kpi" in name:
        return {"chapter": "KPI framework", "order": (99, 0), "title": humanize(name)}
    return {"chapter": "Other tables", "order": (98, 0), "title": humanize(name)}


@st.cache_data(show_spinner=False)
def build_catalog(data_dir):
    items = []
    for f in sorted(Path(data_dir).glob("*.csv")):
        info = describe(f.stem)
        info.update(path=str(f), stem=f.stem)
        items.append(info)
    return items


@st.cache_data(show_spinner=False)
def load_table(path):
    # Only an empty cell counts as missing. The text "NA" printed in the
    # report must stay "NA" instead of silently becoming a blank.
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


META = {f"table_{e['label']}": e for e in REGISTRY}

# Places where the published report disagrees with itself (see README).
SOURCE_NOTES = {
    "2_3_disability_community_eced": "In the printed report, Girls + Boys does not equal Total in at least one column for Bagmati, Lumbini and Nepal.",
    "2_4_disability_institutional_eced": "In the printed report, Girls + Boys does not equal Total in at least one column for Karnali and Nepal.",
    "3_4_technical_stream_schools": "The report prints Nepal's average students per school as 73.8. Its own totals (40,438 students, 569 schools) give 71.1.",
    "4_16_midday_meal_menu": "Lumbini's menu columns add up to 4,338, but the report prints 4,438 schools. The gap carries into the Nepal row.",
    "5_10_materials_secondary_1_10_community": "The provinces' Local Curriculum counts add up to 3,403, but the Nepal row prints 3,645.",
    "5_9_sip_audit_secondary_percent": "The (1-10) SIP column repeats the Social Audit percentages. Recomputed from the counts in Table 5.8, Koshi is 85.7%, not the printed 87.1%.",
    "kf3_number_of_teachers": "In the Other row, the Sec (9-12) figure (15,552) is larger than its parts combined (11,365).",
    "sesp_kpi_indicators": "Rows flagged in the qa_flag column are places where the report's own numbers disagree. Open the Explorer tab to see them by indicator.",
}

REPORT_ISSUES = [
    ("Tables 2.3 and 2.4", "Five province groups: Girls + Boys is not Total", "Bagmati, Lumbini, Nepal (2.3); Karnali, Nepal (2.4)"),
    ("Table 3.4", "Nepal average students per school printed as 73.8", "40,438 / 569 = 71.1"),
    ("Table 4.16", "Lumbini: 4,438 schools printed", "Menu columns add up to 4,338 (Nepal: 27,010 vs 26,910)"),
    ("Table 5.10", "Nepal Local Curriculum printed as 3,645", "Provinces add up to 3,403"),
    ("Table 5.9 (SIP, %)", "(1-10) SIP column repeats the Social Audit column", "Koshi from counts: 85.7%, printed 87.1%"),
    ("Key finding 3", "Other row, Sec (9-12): 15,552", "Parts (9,873 + 1,492) give 11,365"),
    ("Table numbering", "Two tables are called 5.9; one heading reads 'Table 4.2116'", "Labelling only"),
    ("KPI 1.2.3", "Base-year Total printed as 0.6", "Outside Girls (0.2) and Boys (0.1)"),
    ("KPI 1.3.2", "Achievement Total printed as 13,355", "Female + Male = 13,356"),
    ("KPI 2.1.9", "GER 1-8: Boys 147.2, Total 136.1", "Must lie between GER 1-5 and GER 6-8"),
    ("KPI 2.3.5", "Target Total printed as 4,885,165", "Girls + Boys = 4,896,743"),
    ("KPI 3.2.6", "Achievement Total printed as 66,681", "Girls + Boys = 64,881"),
    ("KPI 3.3.7", "ID printed twice for two different indicators", "Labelling only"),
    ("KPI headers", "Year printed as 2081 (page 19) and 2025/25 (page 21)", "Other pages use 2025/26"),
]

# ------------------------------------------------------------------ helpers


def to_number(series):
    """Text like '8,265' or '62.5%' -> numbers; anything else -> NaN."""
    s = series.fillna("").astype(str).str.replace(",", "", regex=False)
    s = s.str.replace("%", "", regex=False).str.strip()
    return pd.to_numeric(s, errors="coerce")


def fmt_number(v):
    if v is None or pd.isna(v):
        return ""
    v = float(v)
    if v.is_integer():
        return f"{v:,.0f}"
    return f"{v:,.2f}" if abs(v) < 10 else f"{v:,.1f}"


def bars_html(items, color=BLUE, highlight_top=True, scale=None):
    """items: list of (label, value, color or None). Plain HTML bars.
    Pass `scale` to draw several charts against the same maximum."""
    items = [(l, v, c) for l, v, c in items if v is not None and not pd.isna(v)]
    if not items:
        return ""
    top = max(v for _, v, _ in items)
    scale = scale if scale else (top if top > 0 else 1)
    rows = []
    for label, value, col in items:
        if col is None:
            col = CRIMSON if (highlight_top and value == top) else color
        text = fmt_number(value)
        width = max(0.0, float(value)) / scale * 100
        rows.append(
            f'<div class="bar-row" title="{html.escape(str(label))}: {text}">'
            f'<div class="bar-label">{html.escape(str(label))}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.2f}%;background:{col}"></div></div>'
            f'<div class="bar-value">{text}</div></div>'
        )
    return '<div class="bars">' + "".join(rows) + "</div>"


def is_national(labels):
    return labels.fillna("").astype(str).str.startswith("Nepal")


def numeric_columns(df, label_col):
    return [c for c in df.columns if c != label_col and to_number(df[c]).notna().sum() >= 2]


def show_table(df):
    """Full-width table. Newer Streamlit wants width="stretch"; older versions
    only know the older spelling. Try the new one, fall back to the old one."""
    try:
        st.dataframe(df, width="stretch", hide_index=True)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True)


def shown(value):
    return "n/a" if pd.isna(value) or str(value).strip() == "" else str(value)


def lookup_number(value):
    out = to_number(pd.Series([value]))
    return None if pd.isna(out.iloc[0]) else float(out.iloc[0])


# ------------------------------------------------------------------ views


def explore_table(df, name):
    has_province = "Province" in df.columns
    label_col = "Province" if has_province else df.columns[0]
    cols = numeric_columns(df, label_col)
    if not cols:
        st.info("This table has no numeric columns to chart. The Data tab shows it in full.")
        return

    left, right = st.columns([3, 1])
    column = left.selectbox("Column to chart", cols, key=f"col_{name}")
    labels = df[label_col].fillna("").astype(str)
    national = is_national(labels)
    show_national = False
    if national.any():
        show_national = right.toggle("Include national rows", value=False, key=f"nat_{name}")

    values = to_number(df[column])
    frame = pd.DataFrame({"label": labels, "value": values, "national": national}).dropna(subset=["value"])
    parts = frame[~frame["national"]]
    if parts.empty:
        st.info("Nothing to chart for this column.")
        return

    cards = st.columns(3)
    top = parts.loc[parts["value"].idxmax()]
    low = parts.loc[parts["value"].idxmin()]
    cards[0].metric(f"Highest: {top['label']}", fmt_number(top["value"]))
    cards[1].metric(f"Lowest: {low['label']}", fmt_number(low["value"]))
    nat = frame[frame["national"]]
    if not nat.empty:
        cards[2].metric(f"National: {nat.iloc[0]['label']}", fmt_number(nat.iloc[0]["value"]))

    shown = frame if show_national else parts
    if has_province:
        shown = shown.sort_values("value", ascending=False)
    items = [(r.label, r.value, GREY if r.national else None) for r in shown.itertuples()]
    st.markdown(f"**{column}** by {label_col.lower()}")
    st.markdown(bars_html(items), unsafe_allow_html=True)
    st.caption("Highlighted bar is the highest value. Numbers are exactly as printed in the report.")


def explore_kpi(df):
    sections = sorted(df["section_no"].dropna().unique(), key=lambda s: int(s) if str(s).isdigit() else 99)
    left, right = st.columns([1, 3])
    section = left.selectbox("Section", sections, format_func=lambda s: f"Section {s}", key="kpi_section")
    sub = df[df["section_no"] == section]
    options = list(dict.fromkeys(zip(sub["indicator_id"], sub["indicator"].fillna(""))))
    pick = right.selectbox("Indicator", options, key=f"kpi_ind_{section}",
                           format_func=lambda p: f"{p[0]}  {p[1][:95]}")
    rows = sub[(sub["indicator_id"] == pick[0]) & (sub["indicator"].fillna("") == pick[1])].copy()
    rows["group"] = rows["group"].fillna("").replace("", "All")
    unit = next((u for u in rows["unit"].fillna("") if u), "")

    head = rows[rows["group_code"] == "T"]
    head = head.iloc[0] if not head.empty else rows.iloc[0]
    base, target, ach = (lookup_number(head[c]) for c in ("base_2021_22", "target_2025_26", "achievement_2025_26"))
    cards = st.columns(3)
    cards[0].metric("Base 2021/22", fmt_number(base) or shown(head["base_2021_22"]))
    cards[1].metric("Target 2025/26", fmt_number(target) or shown(head["target_2025_26"]))
    delta = None if ach is None or target is None else f"{ach - target:+,.2f} vs target"
    cards[2].metric("Achievement 2025/26", fmt_number(ach) or shown(head["achievement_2025_26"]),
                    delta=delta, delta_color="off")
    st.caption(f"Headline row: {head['group']}. Unit: {unit or 'not stated'}.")

    periods = [("Base 2021/22", "base_2021_22", GREY), ("Target 2025/26", "target_2025_26", BLUE),
               ("Achievement 2025/26", "achievement_2025_26", CRIMSON)]
    st.markdown("".join(f'<span class="legend"><i style="background:{c}"></i>{t}</span>' for t, _, c in periods),
                unsafe_allow_html=True)
    numbers = [lookup_number(v) for c in ("base_2021_22", "target_2025_26", "achievement_2025_26") for v in rows[c]]
    scale_top = max([n for n in numbers if n is not None], default=None)
    for _, r in rows.iterrows():
        items = [(t, lookup_number(r[c]), color) for t, c, color in periods]
        html_bars = bars_html(items, scale=scale_top)
        st.markdown(f'<div class="group-title">{html.escape(str(r["group"]))}</div>' + html_bars,
                    unsafe_allow_html=True)

    for col, label in (("base_note", "Base"), ("target_note", "Target"), ("achievement_note", "Achievement")):
        notes = [n for n in rows[col].fillna("") if n]
        if notes:
            st.caption(f"{label} note: " + "; ".join(dict.fromkeys(notes)))
    flags = [f for f in rows["qa_flag"].fillna("") if f]
    if flags:
        st.warning("Inconsistency in the original report: " + " | ".join(dict.fromkeys(flags)))


def data_tab(df, item):
    has_province = "Province" in df.columns
    filtered = df
    left, right = st.columns([2, 3])
    query = left.text_input("Filter rows", placeholder="Type to search any column", key=f"q_{item['stem']}")
    if has_province:
        provinces = [p for p in df["Province"].dropna().unique()]
        chosen = right.multiselect("Rows to show", provinces, default=provinces, key=f"p_{item['stem']}")
        filtered = filtered[filtered["Province"].isin(chosen)]
    if query:
        text = filtered.fillna("").astype(str)
        mask = text.apply(lambda col: col.str.contains(query, case=False, regex=False)).any(axis=1)
        filtered = filtered[mask]
    show_table(filtered)
    st.download_button("Download this table (CSV)", data=filtered.to_csv(index=False).encode("utf-8"),
                       file_name=f"{item['stem']}.csv", mime="text/csv")


def about_table(df, item):
    meta = META.get(item["stem"])
    if meta:
        st.markdown(f"**Source:** CEHRD Flash I Report 2082 (2025/26), PDF page {meta['page']}")
        st.markdown(f"**Extraction pattern:** `{meta['pattern']}`")
    elif "kpi" in item["stem"]:
        st.markdown("**Source:** CEHRD Flash I Report 2082 (2025/26), PDF pages 14 to 21")
    st.markdown(f"**Size:** {len(df)} rows, {len(df.columns)} columns")
    st.markdown("**Columns:** " + ", ".join(f"`{c}`" for c in df.columns))
    st.caption("Values are stored as text, exactly as the report prints them (some with thousands "
               "commas, some without). The dashboard converts them to numbers only for charting.")


# --------------------------------------------------------------------- page

catalog = build_catalog(str(DATA_DIR))
if not catalog:
    st.error("No data files found in data/processed. Run src/extractor.py first.")
    st.stop()

total_rows = sum(len(load_table(i["path"])) for i in catalog)
pages = len({e["page"] for e in REGISTRY})
stats = [(len(catalog), "datasets"), (f"{total_rows:,}", "rows")]
if pages:
    stats.append((pages, "PDF pages"))
stats.append(("2082", "Flash I Report"))
stat_html = "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for v, k in stats)
st.markdown(
    '<div class="hero"><div class="hero-title">Nepal Open Education Data Engine</div>'
    '<p class="hero-sub">The CEHRD Flash Report, taken out of the PDF: cleaned, checked '
    'against the source, and open to everyone.</p>'
    f'<div class="stat-row">{stat_html}</div></div>',
    unsafe_allow_html=True,
)

chapters = [c for c in CHAPTER_ORDER if any(i["chapter"] == c for i in catalog)]
wanted = st.query_params.get("table")
wanted_item = next((i for i in catalog if i["stem"] == wanted), None)

with st.sidebar:
    st.markdown("### Browse tables")
    chapter = st.selectbox("Chapter", chapters, key="chapter",
                           index=chapters.index(wanted_item["chapter"]) if wanted_item else 0)
    items = sorted((i for i in catalog if i["chapter"] == chapter), key=lambda i: (i["order"], i["title"]))
    start = next((n for n, i in enumerate(items) if wanted_item and i["stem"] == wanted_item["stem"]), 0)
    choice = st.selectbox("Table", list(range(len(items))), index=start, key=f"table_{chapter}",
                          format_func=lambda n: items[n]["title"])
    item = items[choice]
    st.divider()
    st.link_button("View code on GitHub", REPO_URL)
    st.caption("Data: CEHRD, Government of Nepal. Code: MIT licence.")

if st.query_params.get("table") != item["stem"]:
    st.query_params["table"] = item["stem"]

tab_explore, tab_errors, tab_about = st.tabs(["Explorer", "Errors in the report", "About"])

with tab_explore:
    df = load_table(item["path"])
    st.markdown(f"## {item['title']}")
    note = SOURCE_NOTES.get(item["stem"].replace("table_", "", 1))
    if note:
        st.warning(note)
    inner = st.tabs(["Chart", "Data", "Table details"])
    with inner[0]:
        if {"indicator_id", "base_2021_22", "target_2025_26", "achievement_2025_26"} <= set(df.columns):
            explore_kpi(df)
        else:
            explore_table(df, item["stem"])
    with inner[1]:
        data_tab(df, item)
    with inner[2]:
        about_table(df, item)

with tab_errors:
    st.markdown("### Where the original report disagrees with itself")
    st.write("The arithmetic checks behind this project turned up the places below. They are in the "
             "published PDF, not introduced by the extraction. The CSVs keep the printed numbers.")
    show_table(pd.DataFrame(REPORT_ISSUES, columns=["Where", "What the report prints", "What the numbers give"]))

with tab_about:
    st.markdown("### About this project")
    st.write("Nepal's Ministry of Education publishes its national school census as a PDF whose tables "
             "have merged headers and shifted values. This project rebuilds those tables as clean CSV "
             "files, checks every number against the PDF, and serves them here.")
    st.write("Found a number that doesn't match the PDF? Open an issue with the table number and the value.")
    st.link_button("Read the README and the code", REPO_URL)
    st.caption("If you use this data, cite the original report (CEHRD, Flash I Report 2082) "
               "and this repository.")
