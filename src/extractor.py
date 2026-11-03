"""
extractor.py — Multi-table version

Covers 71 tables from the Flash I Report that fit one of eleven verified
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

PATTERN "single_header": a clean one-row header, nothing to fix except
total-row labels. Tables 3.5, 3.6, 4.16, 4.17, 4.20 (by province).

PATTERN "named_columns": the PDF's header is a tangle of merged and
shifted cells, so the column names are written out by hand (checked
against the printed page) and the VALUES are collected row by row:
  - default: the columns are "locked" to the positions of the fullest
    row, and every other row may only have values at those positions
    (this lets a row like "Nepal (%)" legitimately leave cells blank);
  - "compact": values drift between raw columns from row to row, so take
    each row's values in order (every row must have exactly the expected
    number);
  - "compact" + "optional": same, but a short row may skip the listed
    columns (e.g. a "Nepal (%)" row with no school count).
Any row that does not fit stops the run with an error instead of
silently putting a number in the wrong column.

PATTERN "split_rows": one logical row is spread over several raw rows
(a label that wraps onto two lines, values split between two rows).
Key finding 3 (teachers).
"""

import pdfplumber
import pandas as pd
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PDF_PATH = SCRIPT_DIR.parent / "data" / "raw" / "sample.pdf"
OUTPUT_DIR = SCRIPT_DIR.parent / "data" / "processed"

# Total rows are labelled "TOTAL" or "%" in a few tables; make them match
# the "Nepal" / "Nepal (%)" labels used elsewhere so the dashboard can
# recognise them as national figures.
ROW_LABEL_FIXES = {"TOTAL": "Nepal", "%": "Nepal (%)"}


def gbt(*groups, labels=("Girls", "Boys", "Total")):
    """Column names for repeated Girls/Boys/Total blocks."""
    return [f"{g}_{lab}" for g in groups for lab in labels]


def infra_cols(grades):
    return ["Province", f"Schools ({grades})", "Average Buildings", "Electricity",
            "Computers", "Average Computers", "Drinking Water", "Library",
            "Child Club", "Toilet", "Internet"]


def material_cols(grades, pct=False):
    suffix = " (%)" if pct else ""
    return ["Province", f"Schools ({grades})"] + [
        f"{m}{suffix}" for m in ("Teachers' Guide", "Child Material", "Book Corner",
                                  "Curriculum", "Local Curriculum", "Reference Material")]


def sip_cols(pct=False):
    suffix = " (%)" if pct else ""
    return ["Province", "Schools (1-10)", "Schools (1-12)"] + [
        f"Secondary ({g})_{x}{suffix}" for g in ("1-10", "1-12")
        for x in ("SIP", "Social Audit", "Financial Audit")]


SHARE_COLS = ["Community_Share of students", "Institutional_Share of students"]


# Each entry: page number (1-indexed), which table on that page (0-indexed,
# for pages with more than one table), which pattern it follows, and a
# short label used for the output filename. Labels are best-effort where
# a page has multiple tables and exact title-to-table matching wasn't
# hand-verified — the DATA is verified correct either way; only the label
# might need a manual rename later.
TABLES = [
    {"page": 12, "idx": 0, "pattern": "named_columns", "label": "kf1_number_of_schools",
     "data_start": 2,
     "columns": ["School Types", "Total", "Community", "Institutional", "Religious"]},
    {"page": 12, "idx": 1, "pattern": "named_columns", "label": "kf2_number_of_students",
     "data_start": 4,
     "columns": ["Level"] + gbt("Total", "Community", "Institutional", "Religious",
                                labels=("Total", "Girls"))},
    {"page": 13, "idx": 0, "pattern": "split_rows", "label": "kf3_number_of_teachers",
     "columns": ["Teacher Types", "Basic (1-5)", "Basic (6-8)", "Basic (1-8)",
                 "Sec (9-10)", "Sec (11-12)", "Sec (9-12)"]},
    {"page": 13, "idx": 1, "pattern": "named_columns", "label": "kf4_student_teacher_ratio",
     "data_start": 2,
     "columns": ["Level"] + gbt("Total", "Community", "Institutional",
                                labels=("Students", "Teacher", "STR"))},
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
    {"page": 32, "idx": 0, "pattern": "named_columns", "label": "3_4_technical_stream_schools",
     "data_start": 3,
     "columns": ["Province", "Schools_CEHRD", "Schools_Province", "Schools_Local", "Schools_Total",
                 "Students", "Average students per school", "Average students per class"]},
    {"page": 33, "idx": 0, "pattern": "single_header", "label": "3_5_model_schools"},
    {"page": 34, "idx": 0, "pattern": "single_header", "label": "3_6_special_school_resource_class"},
    {"page": 34, "idx": 1, "pattern": "named_columns", "label": "3_7_disability_screening",
     "data_start": 2,
     "columns": ["Province", "Students in IEMIS (All)", "ECED-G3", "Screened Students",
                 "Screened %", "Suspected", "Referred", "Confirmed"]},
    {"page": 35, "idx": 0, "pattern": "shift_bug", "label": "3_8_clcs"},
    {"page": 36, "idx": 0, "pattern": "named_columns", "label": "4_1_students_basic",
     "data_start": 2,
     "columns": ["Province"] + gbt("Total", "Community", "Institutional")
                + ["Community_% Girls", "Institutional_% Girls"]},
    {"page": 37, "idx": 0, "pattern": "named_columns", "label": "4_2_students_by_grade_basic",
     "data_start": 2,
     "columns": ["Grade"] + gbt("Total", "Community", "Institutional") + SHARE_COLS},
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
    {"page": 43, "idx": 0, "pattern": "named_columns", "label": "4_12_infrastructure_basic_1_5_community",
     "data_start": 4, "columns": infra_cols("1-5")},
    {"page": 43, "idx": 1, "pattern": "named_columns", "label": "4_13_infrastructure_basic_1_8_community",
     "data_start": 4, "columns": infra_cols("1-8")},
    {"page": 44, "idx": 0, "pattern": "named_columns", "label": "4_14_materials_basic_1_5_community",
     "data_start": 2, "columns": material_cols("1-5")},
    {"page": 44, "idx": 1, "pattern": "named_columns", "label": "4_15_materials_basic_1_8_community",
     "data_start": 2, "mode": "compact", "optional": [1], "columns": material_cols("1-8")},
    {"page": 45, "idx": 0, "pattern": "single_header", "label": "4_16_midday_meal_menu"},
    {"page": 45, "idx": 1, "pattern": "single_header", "label": "4_17_midday_meal_source"},
    {"page": 46, "idx": 0, "pattern": "named_columns", "label": "4_18_midday_meal_management",
     "data_start": 4,
     "columns": ["Province", "Schools", "Catering", "Mother's Group", "Parents", "School canteen",
                 "School's Human resource", "Others agencies", "Not stated"]},
    {"page": 47, "idx": 0, "pattern": "title_then_header", "label": "4_20_scholarship"},
    {"page": 47, "idx": 1, "pattern": "single_header", "label": "4_20_scholarship_by_province"},
    {"page": 48, "idx": 0, "pattern": "named_columns", "label": "4_21_oosc_basic",
     "data_start": 2, "mode": "compact",
     "columns": ["Province", "Number_Girls", "Number_Boys", "Number_Total",
                 "Percent_Girls", "Percent_Boys", "Percent_Total"]},
    {"page": 49, "idx": 0, "pattern": "named_columns", "label": "5_1_students_secondary",
     "data_start": 2,
     "columns": ["Province"] + gbt("Total", "Community", "Institutional")
                + ["Community_% Girls", "Institutional_% Girls"]},
    {"page": 50, "idx": 0, "pattern": "named_columns", "label": "5_2_religious_schools_students",
     "data_start": 2, "mode": "compact",
     "columns": ["Province"] + gbt("G 9-10", "G 11-12", "Total")},
    {"page": 50, "idx": 1, "pattern": "named_columns", "label": "5_3_students_by_grade_secondary",
     "data_start": 4,
     "columns": ["Grade"] + gbt("Total", "Community", "Institutional") + SHARE_COLS},
    {"page": 51, "idx": 0, "pattern": "direct_clean", "label": "5_2_caste_secondary"},
    {"page": 51, "idx": 2, "pattern": "direct_clean", "label": "5_3_disadvantaged_caste_secondary"},
    {"page": 52, "idx": 0, "pattern": "direct_clean", "label": "5_4_disability_secondary"},
    {"page": 53, "idx": 0, "pattern": "direct_clean", "label": "5_5_promotion_dropout_secondary_partial"},
    {"page": 53, "idx": 1, "pattern": "direct_clean", "label": "5_6_ger_ner_secondary"},
    {"page": 53, "idx": 2, "pattern": "stacked_header", "label": "5_4_ger_ner_secondary_additional",
     "top_rows": [0], "sub_rows": [1], "data_start": 2, "tail_from": 7},
    {"page": 54, "idx": 0, "pattern": "direct_clean", "label": "5_5_student_school_ratio_secondary"},
    {"page": 54, "idx": 1, "pattern": "named_columns", "label": "5_6_infrastructure_secondary_1_10_community",
     "data_start": 4, "columns": infra_cols("1-10")},
    {"page": 55, "idx": 0, "pattern": "named_columns", "label": "5_9_infrastructure_secondary_1_12_community",
     "data_start": 4, "columns": infra_cols("1-12")},
    {"page": 55, "idx": 1, "pattern": "named_columns", "label": "5_10_materials_secondary_1_10_community",
     "data_start": 2, "mode": "compact", "optional": [1], "columns": material_cols("1-10")},
    {"page": 56, "idx": 0, "pattern": "named_columns", "label": "5_11_materials_secondary_1_10_percent",
     "data_start": 2, "mode": "compact", "columns": material_cols("1-10", pct=True)},
    {"page": 56, "idx": 1, "pattern": "named_columns", "label": "5_12_materials_secondary_1_12_community",
     "data_start": 2, "mode": "compact", "optional": [1], "columns": material_cols("1-12")},
    {"page": 57, "idx": 0, "pattern": "named_columns", "label": "5_7_materials_secondary_1_12_percent",
     "data_start": 2, "mode": "compact", "columns": material_cols("1-12", pct=True)},
    {"page": 57, "idx": 1, "pattern": "named_columns", "label": "5_8_sip_audit_secondary",
     "data_start": 6, "mode": "compact", "columns": sip_cols()},
    {"page": 58, "idx": 0, "pattern": "named_columns", "label": "5_9_sip_audit_secondary_percent",
     "data_start": 6, "mode": "compact", "columns": sip_cols(pct=True)},
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


def fix_label(row):
    row[0] = ROW_LABEL_FIXES.get(row[0], row[0])
    return row


def extract_named(raw, columns, data_start, mode="locked", optional=()):
    """Hand-named columns; see PATTERN "named_columns" in the docstring."""
    k = len(columns)
    rows = [[clean_cell(c) for c in r] for r in raw[data_start:]]
    rows = [r for r in rows if any(r)]
    out = []

    if mode == "locked":
        ref = max(rows, key=lambda r: sum(1 for v in r if v))
        keep = [j for j, v in enumerate(ref) if v]
        if len(keep) != k:
            raise ValueError(f"expected {k} columns but the fullest row has {len(keep)} values")
        for r in rows:
            stray = [j for j, v in enumerate(r) if v and j not in keep]
            if stray:
                raise ValueError(f"row {r[0]!r} has values outside the expected positions {stray}")
            out.append(fix_label([r[j] for j in keep]))
    elif mode == "compact":
        for r in rows:
            vals = [v for v in r if v]
            if len(vals) == k:
                out.append(fix_label(vals))
            elif optional and len(vals) == k - len(optional):
                it = iter(vals)
                out.append(fix_label(["" if j in optional else next(it) for j in range(k)]))
            else:
                raise ValueError(f"row {r[0]!r} has {len(vals)} values, expected {k}")
    else:
        raise ValueError(f"unknown mode {mode!r}")
    return pd.DataFrame(out, columns=columns)


def extract_split_rows(raw, columns, data_start=1):
    """A record = a row that has both a label and values; values on the
    following label-less rows belong to it, and label-only rows are the
    next line of its (wrapped) label."""
    k = len(columns) - 1
    records = []
    for r in raw[data_start:]:
        cells = [clean_cell(c) for c in r]
        label, vals = cells[0], [v for v in cells[1:] if v]
        if label and vals:
            records.append({"label": [label], "vals": list(vals)})
        elif vals:
            records[-1]["vals"].extend(vals)
        elif label:
            records[-1]["label"].append(label)
    rows = []
    for rec in records:
        if len(rec["vals"]) != k:
            raise ValueError(f"{' '.join(rec['label'])!r} has {len(rec['vals'])} values, expected {k}")
        rows.append([" ".join(rec["label"])] + rec["vals"])
    return pd.DataFrame(rows, columns=columns)


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
    elif pattern == "single_header":
        cols = build_single_header(raw[0])
        rows = [fix_label(clean_direct_row(r)) for r in raw[1:]]
    elif pattern == "split_rows":
        return extract_split_rows(raw, opts["columns"])
    elif pattern == "named_columns":
        return extract_named(raw, opts["columns"], opts["data_start"],
                             opts.get("mode", "locked"), opts.get("optional", ()))
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