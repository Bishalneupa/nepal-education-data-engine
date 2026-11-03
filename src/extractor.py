"""
extractor.py — Multi-table version

Covers 41 tables from the Flash I Report that fit one of eight verified
patterns. Each becomes its own CSV in data/processed/.

PATTERN "shift_bug": same issue as our original Table 3.1 — a header
merge causes one real value to land in an unpredictable one of 3 raw
columns depending on the row. Fixed by grabbing whichever of the 3 is
non-empty.

PATTERN "direct_clean": the merged header still needs flattening, but
the data cells are already correctly filled — no shifting. Coalescing
these would silently destroy real data (confirmed by testing: it would
have dropped 2 of 3 true values from Table 6.1 without erroring).

PATTERN "single_header_grouped": the table has ONE header row (not two),
and the Province name is a merged cell spanning a Girls/Boys/Total group
of rows. The name lands on a different row of each group (first row for
Koshi, middle row for Madhesh, ...), so we fill it into every row of its
group. Tables 2.3 and 2.4.

PATTERN "three_header": three stacked header rows, data starts on row 4.
Table 2.7.

PATTERN "title_then_header": a title row sits above the single header
row. Table 4.20.

PATTERN "shift_two_label": like shift_bug, but the first TWO columns
(Province, Total) are real labels and only the columns after them shift.
Table 2.9.

PATTERN "stacked_header": header text is split across several raw rows
(a wrapped label like "Upto" / "G12", or a merged cell several rows
tall). Each entry names which rows are the top header, which are the
sub header, and where the data starts. An optional "tail_from" merges
all columns from that position on into ONE column (Tables 4.8 and 5.4:
the "Gender Parity" header is spread over 3 raw columns but holds a
single value).
"""

import pdfplumber
import pandas as pd
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PDF_PATH = SCRIPT_DIR.parent / "data" / "raw" / "sample.pdf"
OUTPUT_DIR = SCRIPT_DIR.parent / "data" / "processed"

# Each entry: page number (1-indexed), which table on that page (0-indexed,
# for pages with more than one table), which pattern it follows, and a
# short label used for the output filename. Labels are best-effort where
# a page has multiple tables and exact title-to-table matching wasn't
# hand-verified — the DATA is verified correct either way; only the label
# might need a manual rename later.
TABLES = [
    {"page": 24, "idx": 0, "pattern": "shift_bug", "label": "2_1_eced_centers"},
    {"page": 25, "idx": 0, "pattern": "direct_clean", "label": "2_2_children_in_eced"},
    {"page": 26, "idx": 0, "pattern": "single_header_grouped", "label": "2_3_disability_community_eced"},
    {"page": 26, "idx": 1, "pattern": "single_header_grouped", "label": "2_4_disability_institutional_eced"},
    {"page": 27, "idx": 0, "pattern": "shift_bug", "label": "2_6_eced_enabling_conditions"},
    {"page": 28, "idx": 0, "pattern": "three_header", "label": "2_7_caste_ethnic_eced"},
    {"page": 28, "idx": 1, "pattern": "direct_clean", "label": "2_8_ger_ner_eced"},
    {"page": 29, "idx": 0, "pattern": "shift_two_label", "label": "2_9_eced_materials"},
    {"page": 29, "idx": 1, "pattern": "stacked_header", "label": "2_11_grade1_eced_experience",
     "top_rows": [0, 1, 2, 3], "sub_rows": [4], "data_start": 5},
    {"page": 30, "idx": 0, "pattern": "shift_bug", "label": "3_1_schools_by_province"},
    {"page": 31, "idx": 0, "pattern": "direct_clean", "label": "3_2_basic_level_schools"},
    {"page": 31, "idx": 1, "pattern": "stacked_header", "label": "3_3_secondary_level_schools",
     "top_rows": [0], "sub_rows": [1, 2], "data_start": 3},
    {"page": 35, "idx": 0, "pattern": "shift_bug", "label": "3_8_clcs"},
    {"page": 38, "idx": 0, "pattern": "stacked_header", "label": "4_3_dalit_janajati_basic",
     "top_rows": [0, 1], "sub_rows": [2, 3], "data_start": 4},
    {"page": 38, "idx": 1, "pattern": "direct_clean", "label": "4_4_janajati_basic"},
    {"page": 39, "idx": 0, "pattern": "direct_clean", "label": "4_5_disability_basic"},
    {"page": 40, "idx": 0, "pattern": "direct_clean", "label": "4_6_promotion_repetition_dropout_basic"},
    {"page": 40, "idx": 1, "pattern": "direct_clean", "label": "4_7_ger_ner_basic"},
    {"page": 41, "idx": 0, "pattern": "stacked_header", "label": "4_8_ger_ner_basic_additional",
     "top_rows": [0], "sub_rows": [1], "data_start": 2, "tail_from": 7},
    {"page": 41, "idx": 1, "pattern": "direct_clean", "label": "4_9_gir_nir_grade1"},
    {"page": 42, "idx": 0, "pattern": "direct_clean", "label": "4_10_survival_rates_basic"},
    {"page": 42, "idx": 1, "pattern": "shift_bug", "label": "4_11_student_school_ratio_basic"},
    {"page": 46, "idx": 1, "pattern": "shift_bug", "label": "4_19_governance_basic"},
    {"page": 47, "idx": 0, "pattern": "title_then_header", "label": "4_20_scholarship"},
    {"page": 51, "idx": 0, "pattern": "direct_clean", "label": "5_2_caste_secondary"},
    {"page": 51, "idx": 2, "pattern": "direct_clean", "label": "5_3_disadvantaged_caste_secondary"},
    {"page": 52, "idx": 0, "pattern": "direct_clean", "label": "5_4_disability_secondary"},
    {"page": 53, "idx": 0, "pattern": "direct_clean", "label": "5_5_promotion_dropout_secondary_partial"},
    {"page": 53, "idx": 1, "pattern": "direct_clean", "label": "5_6_ger_ner_secondary"},
    {"page": 53, "idx": 2, "pattern": "stacked_header", "label": "5_4_ger_ner_secondary_additional",
     "top_rows": [0], "sub_rows": [1], "data_start": 2, "tail_from": 7},
    {"page": 54, "idx": 0, "pattern": "direct_clean", "label": "5_5_student_school_ratio_secondary"},
    {"page": 60, "idx": 0, "pattern": "direct_clean", "label": "6_1_teachers_by_gender_basic"},
    {"page": 60, "idx": 1, "pattern": "direct_clean", "label": "6_2_teachers_local_province_basic"},
    {"page": 60, "idx": 2, "pattern": "stacked_header", "label": "6_3_teachers_private_volunteer_community",
     "top_rows": [0, 1], "sub_rows": [2, 3], "data_start": 4},
    {"page": 61, "idx": 0, "pattern": "direct_clean", "label": "6_4_teachers_institutional"},
    {"page": 61, "idx": 1, "pattern": "direct_clean", "label": "6_5_teachers_secondary_govt_approved"},
    {"page": 62, "idx": 0, "pattern": "direct_clean", "label": "6_6_teachers_local_provincial_secondary"},
    {"page": 62, "idx": 1, "pattern": "direct_clean", "label": "6_7_teachers_private_secondary"},
    {"page": 62, "idx": 2, "pattern": "direct_clean", "label": "6_8_teachers_institutional_secondary"},
    {"page": 63, "idx": 0, "pattern": "stacked_header", "label": "6_9_str_basic",
     "top_rows": [0, 1], "sub_rows": [2, 3], "data_start": 4},
    {"page": 63, "idx": 1, "pattern": "direct_clean", "label": "6_10_str_secondary"},
]

# Confirmed present but NOT yet handled — different column structure,
# needs individual inspection before adding (same as Table 3.1 did):
# page 32 idx0, page 33 idx0, page 34 idx0/1, page 36 idx0, page 37 idx0,
# page 43 idx0/1, page 44 idx0/1, page 45 idx0/1, page 46 idx0, page 47 idx1,
# page 48 idx0, page 49 idx0, page 50 idx0/1, page 54 idx1, page 55 idx0/1,
# page 56 idx0/1, page 57 idx0/1, page 58 idx0
# (The tables that used to be listed here as "ambiguous" are now handled:
# pages 29, 31, 38, 41, 53, 60 and 63.)


def clean_cell(value):
    if value is None:
        return ""
    value = re.sub(r"\s+", " ", str(value))
    return value.strip()


def coalesce_row(row, n_label_cols=1, group_size=3):
    """Pattern A fix: within each group of 3 raw columns, keep whichever
    single cell actually has a value."""
    cleaned = [clean_cell(c) for c in row]
    label_cols = cleaned[:n_label_cols]
    rest = cleaned[n_label_cols:]
    collapsed = list(label_cols)
    for i in range(0, len(rest), group_size):
        group = rest[i:i + group_size]
        value = next((v for v in group if v != ""), "")
        collapsed.append(value)
    return collapsed


def build_column_names_shift_bug(top_header, sub_header):
    names = []
    last_top = ""
    for top, sub in zip(top_header, sub_header):
        if top:
            last_top = top
        name = f"{last_top}_{sub}" if sub else last_top
        names.append(name)
    return names


def forward_fill_row(row):
    """Pattern B header fix: carries a merged header label forward across
    the columns it visually spans, without collapsing them into one."""
    cleaned = [clean_cell(c) for c in row]
    last = ""
    filled = []
    for v in cleaned:
        if v:
            last = v
        filled.append(last)
    return filled


def build_column_names_direct(top_header, sub_header):
    names = []
    for top, sub in zip(top_header, sub_header):
        names.append(f"{top}_{sub}" if sub else top)
    return names


def clean_direct_row(row):
    """Pattern B data fix: every cell is real, just clean it, no grouping."""
    return [clean_cell(c) for c in row]


def build_single_header(raw_header):
    """One header row: just clean it, no merging or joining needed."""
    return [clean_cell(c) for c in raw_header]


def fill_province_groups(rows, label_col=0, key_col=1, end_value="Total"):
    """For tables where a merged Province cell spans a group of rows
    (Girls / Boys / Total). The province name can sit on ANY row of its
    group, so: collect rows until the row whose key column says "Total",
    then give every row in that group the one non-empty label found."""
    out = []
    group = []

    def flush():
        label = next((r[label_col] for r in group if r[label_col]), "")
        for r in group:
            r[label_col] = label
            out.append(r)

    for row in rows:
        group.append(row)
        if row[key_col] == end_value:
            flush()
            group = []
    if group:  # a trailing group with no Total row; don't lose it
        flush()
    return out


def build_column_names_three_header(r0, r1, r2):
    """Three stacked header rows. The top two are merged cells, so carry
    their labels forward across the columns they span; the bottom row is
    already one label per column."""
    l0 = forward_fill_row(r0)
    l1 = forward_fill_row(r1)
    l2 = [clean_cell(c) for c in r2]
    names = []
    for a, b, c in zip(l0, l1, l2):
        names.append("_".join(p for p in (a, b, c) if p))
    return names


def coalesce_row_strict(row, n_label_cols, group_size=3):
    """Like coalesce_row, but refuses to guess: if a group of raw columns
    holds MORE than one value, something is not a simple shift, so we stop
    instead of silently dropping data."""
    cleaned = [clean_cell(c) for c in row]
    collapsed = list(cleaned[:n_label_cols])
    rest = cleaned[n_label_cols:]
    for i in range(0, len(rest), group_size):
        values = [v for v in rest[i:i + group_size] if v != ""]
        if len(values) > 1:
            raise ValueError(f"more than one value in one group: {values}")
        collapsed.append(values[0] if values else "")
    return collapsed


def vertical_join(raw, rows, ncols):
    """Header text that wraps over several raw rows ("Upto" above "G12"):
    for each column, glue that column's non-empty cells together."""
    joined = []
    for j in range(ncols):
        parts = [clean_cell(raw[r][j]) for r in rows]
        joined.append(" ".join(p for p in parts if p))
    return joined


def extract_stacked(raw, top_rows, sub_rows, data_start, tail_from=None):
    ncols = len(raw[0])
    main_n = tail_from if tail_from is not None else ncols

    top = vertical_join(raw, top_rows, ncols)[:main_n]
    last = ""
    for i, v in enumerate(top):          # merged cells: carry label rightwards
        if v:
            last = v
        top[i] = last
    sub = vertical_join(raw, sub_rows, ncols)[:main_n]
    cols = [f"{t}_{s}" if t and s else (t or s) for t, s in zip(top, sub)]

    rows = []
    for r in raw[data_start:]:
        cleaned = [clean_cell(c) for c in r]
        row = cleaned[:main_n]
        if tail_from is not None:
            values = [v for v in cleaned[tail_from:] if v]
            if len(values) > 1:
                raise ValueError(f"more than one value in the merged tail: {values}")
            row.append(values[0] if values else "")
        rows.append(row)

    if tail_from is not None:
        header_rows = list(top_rows) + list(sub_rows)
        tail_text = [clean_cell(raw[r][j]) for r in header_rows for j in range(tail_from, ncols)]
        cols.append(" ".join(t for t in tail_text if t))
    return pd.DataFrame(rows, columns=cols)


def extract_table(pdf, page_number, table_idx, pattern, opts=None):
    page = pdf.pages[page_number - 1]
    tables = page.extract_tables()
    if table_idx >= len(tables):
        raise ValueError(f"No table at index {table_idx} on page {page_number}")
    raw = tables[table_idx]

    if pattern == "shift_bug":
        top = coalesce_row(raw[0])
        sub = coalesce_row(raw[1])
        cols = build_column_names_shift_bug(top, sub)
        rows = [coalesce_row(r) for r in raw[2:]]
    elif pattern == "direct_clean":
        top = forward_fill_row(raw[0])
        sub = [clean_cell(c) for c in raw[1]]
        cols = build_column_names_direct(top, sub)
        rows = [clean_direct_row(r) for r in raw[2:]]
    elif pattern == "single_header_grouped":
        cols = build_single_header(raw[0])
        rows = fill_province_groups([clean_direct_row(r) for r in raw[1:]])
    elif pattern == "three_header":
        cols = build_column_names_three_header(raw[0], raw[1], raw[2])
        rows = [clean_direct_row(r) for r in raw[3:]]
    elif pattern == "title_then_header":
        cols = build_single_header(raw[1])
        rows = [clean_direct_row(r) for r in raw[2:]]
    elif pattern == "shift_two_label":
        cols = coalesce_row_strict(raw[0], n_label_cols=2)
        rows = [coalesce_row_strict(r, n_label_cols=2) for r in raw[1:]]
    elif pattern == "stacked_header":
        return extract_stacked(raw, opts["top_rows"], opts["sub_rows"],
                               opts["data_start"], opts.get("tail_from"))
    else:
        raise ValueError(f"Unknown pattern: {pattern}")

    return pd.DataFrame(rows, columns=cols)


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    succeeded = []
    failed = []

    with pdfplumber.open(PDF_PATH) as pdf:
        for entry in TABLES:
            try:
                df = extract_table(pdf, entry["page"], entry["idx"], entry["pattern"], entry)
                out_path = OUTPUT_DIR / f"table_{entry['label']}.csv"
                df.to_csv(out_path, index=False)
                succeeded.append(entry["label"])
                print(f"OK  page {entry['page']:>2} idx {entry['idx']} -> {out_path.name}")
            except Exception as e:
                failed.append((entry["label"], str(e)))
                print(f"FAIL page {entry['page']:>2} idx {entry['idx']}: {e}")

    print(f"\n{len(succeeded)} tables extracted successfully, {len(failed)} failed.")