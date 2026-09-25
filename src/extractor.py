import pdfplumber
import pandas as pd
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PDF_PATH = SCRIPT_DIR.parent / "data" / "raw" / "sample.pdf"
OUTPUT_PATH = SCRIPT_DIR.parent / "data" / "processed" / "output.csv"
TARGET_PAGE_NUMBER = 30


def clean_cell(value):
    if value is None:
        return ""
    value = re.sub(r"\s+", " ", str(value))
    return value.strip()


def coalesce_row(row, n_label_cols=1, group_size=3):
    cleaned = [clean_cell(c) for c in row]
    label_cols = cleaned[:n_label_cols]
    rest = cleaned[n_label_cols:]
    collapsed = list(label_cols)
    for i in range(0, len(rest), group_size):
        group = rest[i:i + group_size]
        value = next((v for v in group if v != ""), "")
        collapsed.append(value)
    return collapsed


def build_column_names(top_header, sub_header):
    names = []
    last_top = ""
    for top, sub in zip(top_header, sub_header):
        if top:
            last_top = top
        name = f"{last_top}_{sub}" if sub else last_top
        names.append(name)
    return names


def extract_and_clean_table(pdf_path, page_number):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_number - 1]
        tables = page.extract_tables()
        if not tables:
            raise ValueError(f"No tables found on page {page_number}")
        raw_table = tables[0]

    top_header = coalesce_row(raw_table[0])
    sub_header = coalesce_row(raw_table[1])
    column_names = build_column_names(top_header, sub_header)

    data_rows = [coalesce_row(row) for row in raw_table[2:]]
    df = pd.DataFrame(data_rows, columns=column_names)
    return df


if __name__ == "__main__":
    df = extract_and_clean_table(PDF_PATH, TARGET_PAGE_NUMBER)
    print(df.to_string())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved to {OUTPUT_PATH}")