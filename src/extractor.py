"""
extractor.py — Multi-table version

Covers 33 tables from the Flash I Report that fit one of two verified
patterns. Each becomes its own CSV in data/processed/.

PATTERN "shift_bug": same issue as our original Table 3.1 — a header
merge causes one real value to land in an unpredictable one of 3 raw
columns depending on the row. Fixed by grabbing whichever of the 3 is
non-empty.

PATTERN "direct_clean": the merged header still needs flattening, but
the data cells are already correctly filled — no shifting. Coalescing
these would silently destroy real data (confirmed by testing: it would
have dropped 2 of 3 true values from Table 6.1 without erroring).
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
    {"page": 26, "idx": 0, "pattern": "direct_clean", "label": "2_3_disability_community_eced"},
    {"page": 26, "idx": 1, "pattern": "direct_clean", "label": "2_4_disability_institutional_eced"},
    {"page": 27, "idx": 0, "pattern": "shift_bug", "label": "2_6_eced_enabling_conditions"},
    {"page": 28, "idx": 0, "pattern": "direct_clean", "label": "2_7_caste_ethnic_eced"},
    {"page": 28, "idx": 1, "pattern": "direct_clean", "label": "2_8_ger_ner_eced"},
    {"page": 31, "idx": 0, "pattern": "direct_clean", "label": "3_2_basic_level_schools"},
    {"page": 35, "idx": 0, "pattern": "shift_bug", "label": "3_8_clcs"},
    {"page": 38, "idx": 1, "pattern": "direct_clean", "label": "4_4_janajati_basic"},
    {"page": 39, "idx": 0, "pattern": "direct_clean", "label": "4_5_disability_basic"},
    {"page": 40, "idx": 0, "pattern": "direct_clean", "label": "4_6_promotion_repetition_dropout_basic"},
    {"page": 40, "idx": 1, "pattern": "direct_clean", "label": "4_7_ger_ner_basic"},
    {"page": 41, "idx": 1, "pattern": "direct_clean", "label": "4_9_gir_nir_grade1"},
    {"page": 42, "idx": 0, "pattern": "direct_clean", "label": "4_10_survival_rates_basic"},
    {"page": 42, "idx": 1, "pattern": "shift_bug", "label": "4_11_student_school_ratio_basic"},
    {"page": 46, "idx": 1, "pattern": "shift_bug", "label": "4_19_governance_basic"},
    {"page": 47, "idx": 0, "pattern": "direct_clean", "label": "4_20_scholarship"},
    {"page": 51, "idx": 0, "pattern": "direct_clean", "label": "5_2_caste_secondary"},
    {"page": 51, "idx": 2, "pattern": "direct_clean", "label": "5_3_disadvantaged_caste_secondary"},
    {"page": 52, "idx": 0, "pattern": "direct_clean", "label": "5_4_disability_secondary"},
    {"page": 53, "idx": 0, "pattern": "direct_clean", "label": "5_5_promotion_dropout_secondary_partial"},
    {"page": 53, "idx": 1, "pattern": "direct_clean", "label": "5_6_ger_ner_secondary"},
    {"page": 54, "idx": 0, "pattern": "direct_clean", "label": "5_5_student_school_ratio_secondary"},
    {"page": 60, "idx": 0, "pattern": "direct_clean", "label": "6_1_teachers_by_gender_basic"},
    {"page": 60, "idx": 1, "pattern": "direct_clean", "label": "6_2_teachers_local_province_basic"},
    {"page": 61, "idx": 0, "pattern": "direct_clean", "label": "6_4_teachers_institutional"},
    {"page": 61, "idx": 1, "pattern": "direct_clean", "label": "6_5_teachers_secondary_govt_approved"},
    {"page": 62, "idx": 0, "pattern": "direct_clean", "label": "6_6_teachers_local_provincial_secondary"},
    {"page": 62, "idx": 1, "pattern": "direct_clean", "label": "6_7_teachers_private_secondary"},
    {"page": 62, "idx": 2, "pattern": "direct_clean", "label": "6_8_teachers_institutional_secondary"},
    {"page": 63, "idx": 1, "pattern": "direct_clean", "label": "6_10_str_secondary"},
]

# Confirmed present but NOT yet handled — different column structure,
# needs individual inspection before adding (same as Table 3.1 did):
# page 32 idx0, page 33 idx0, page 34 idx0/1, page 36 idx0, page 37 idx0,
# page 43 idx0/1, page 44 idx0/1, page 45 idx0/1, page 46 idx0, page 47 idx1,
# page 48 idx0, page 49 idx0, page 50 idx0/1, page 54 idx1, page 55 idx0/1,
# page 56 idx0/1, page 57 idx0/1, page 58 idx0
# Also ambiguous (mixed fill pattern, needs a human look before trusting):
# page 29 idx0/1, page 31 idx1, page 38 idx0, page 41 idx0, page 53 idx2,
# page 60 idx2, page 63 idx0


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


def extract_table(pdf, page_number, table_idx, pattern):
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
                df = extract_table(pdf, entry["page"], entry["idx"], entry["pattern"])
                out_path = OUTPUT_DIR / f"table_{entry['label']}.csv"
                df.to_csv(out_path, index=False)
                succeeded.append(entry["label"])
                print(f"OK  page {entry['page']:>2} idx {entry['idx']} -> {out_path.name}")
            except Exception as e:
                failed.append((entry["label"], str(e)))
                print(f"FAIL page {entry['page']:>2} idx {entry['idx']}: {e}")

    print(f"\n{len(succeeded)} tables extracted successfully, {len(failed)} failed.")