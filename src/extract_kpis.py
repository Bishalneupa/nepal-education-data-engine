"""
extract_kpis.py - SESP results framework (KPI) table from the Flash I Report

The Flash I Report 2082 (2025/26) opens with a "KPI AND PRF OF SCHOOL EDUCATION
SECTOR PLAN" table (PDF pages 14-21, printed pages 4-11). For 94 indicator
numbers (95 printed blocks, because 3.3.7 appears twice) it gives the base year
(2021/22), the target for 2025/26 and the achievement for 2025/26. The table has
no "Table X.Y" caption and sits before the chapters that extractor.py reads
(which starts at PDF page 24), so it was not extracted before.

Output: data/processed/sesp_kpi_indicators.csv  (long format, one row per
indicator x disaggregation group, 185 rows).

Why this is not one of the extractor.py patterns
-------------------------------------------------
pdfplumber's cell grid is unreliable for this table: an indicator's ID, name
and unit are vertically centred in a merged block, so a plain cell read puts
them on different rows from the Girls/Boys/Total values. Some values are also
split across rows, and a few "-" cells span several rows.

What this script does instead
-----------------------------
1. Takes each table's column edges (hard-coded below for this specific PDF).
2. Cuts the table into indicator blocks at the horizontal rules that cross the
   ID column (an indicator's ID cell is one merged cell, so only the rules
   between indicators cross it). Each block must contain exactly one indicator
   ID.
3. Inside a block, reads words column by column, so the ID, name, unit,
   group labels and the three value columns cannot be mixed up. Superscript
   footnote markers (7 pt) are read separately: indicator 6.1 prints "2213"
   followed by a superscript "1", which a plain word read glues into "22131".
4. Pairs group labels with values in reading order. If the counts do not match
   (apart from the known "single merged '-' cell" case) it stops with an error
   rather than guessing.
5. Adds a qa_flag column for things the PDF itself gets wrong; these are
   computed from the extracted values, not hand-typed. The values themselves
   are never corrected.

Column notes
------------
group_code is exactly what the PDF prints: G/B/T = girls/boys/total,
F/M/T = female/male/total, or a subject/level label such as "Reading".
Blank means the indicator is not disaggregated.
*_note holds anything that is not a plain number: "-" (printed as a dash),
"NA", a qualifier such as "(2024 AD)", the grade span "ECED - G 5" printed
above the 2.3.5 meal figures, or the text of a footnote. A cell that is empty in
the PDF stays empty in both the value and the note column.
Numbers are stored without thousands separators ("2,494969" is printed in the
PDF and stored as 2494969). Read the CSV with keep_default_na=False, or pandas
turns the note "NA" into a missing value.
pdf_page is the PDF page number (printed page = pdf_page - 10).

qa_flag codes
-------------
DUPLICATE_ID          the same indicator number is printed for two indicators
UNIT_COUNT_FRACTIONAL unit is "No." but a value has decimals
GBT_SUM               girls + boys (or female + male) differ from the total
TOTAL_RANGE           a total rate (%) lies outside the girls and boys rates
GER_RANGE             GER grades 1-8 lies outside GER 1-5 and GER 6-8
HEADER_YEAR           the table header prints a different year from the others

Run from the repository root:  python src/extract_kpis.py
Requires data/raw/sample.pdf (the Flash I Report 2082 PDF; not committed).
"""

import re
import sys
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import pdfplumber

SCRIPT_DIR = Path(__file__).resolve().parent
PDF_PATH = SCRIPT_DIR.parent / "data" / "raw" / "sample.pdf"
OUTPUT_PATH = SCRIPT_DIR.parent / "data" / "processed" / "sesp_kpi_indicators.csv"

# Known size of the table in this report (counted from the PDF). If the
# extraction does not match, something is wrong and the script stops.
EXPECTED_BLOCKS = 95   # 94 distinct indicator numbers; 3.3.7 is printed twice
EXPECTED_ROWS = 185

ROLES_7 = ("id", "name", "group", "unit", "base", "target", "ach")
ROLES_6 = ("id", "name", "unit", "base", "target", "ach")

# (role, value column, note column) for the three year columns
VALUE_COLUMNS = (
    ("base", "base_2021_22", "base_note"),
    ("target", "target_2025_26", "target_note"),
    ("ach", "achievement_2025_26", "achievement_note"),
)
VALUE_KEYS = tuple(column for _, column, _ in VALUE_COLUMNS)
ROLE_NAMES = {"base": "base-year", "target": "target", "ach": "achievement"}


class Region(NamedTuple):
    """One table on one PDF page.

    page: PDF page number; index: position among page.find_tables();
    has_group: the table has a G/B/T style group column; edges: column edges in
    PDF points, read from the PDF's own cell grid.
    """
    page: int
    index: int
    has_group: bool
    edges: list

    @property
    def roles(self):
        """Column roles, left to right."""
        return ROLES_7 if self.has_group else ROLES_6

    @property
    def label(self):
        """Short name used in error messages."""
        return f"p{self.page} t{self.index}"


# p20 t1 has a group column that only exists for indicator 6.3, and p21 t3 has
# stray edges, so those two are set by hand.
REGIONS = [
    Region(14, 0, True, [72.5, 111.1, 291.4, 318.9, 353.4, 409.8, 457.8, 525.4]),
    Region(15, 0, True, [72.0, 115.4, 263.1, 284.7, 312.8, 383.7, 454.7, 525.5]),
    Region(16, 0, True, [72.3, 114.9, 256.1, 305.9, 334.4, 398.1, 454.9, 525.2]),
    Region(17, 0, True, [72.5, 113.6, 256.0, 305.9, 337.2, 400.1, 454.8, 525.1]),
    Region(17, 1, True, [72.5, 113.6, 263.2, 305.9, 337.2, 400.1, 454.8, 525.1]),
    Region(18, 0, True, [72.6, 111.3, 263.0, 305.9, 341.5, 403.0, 454.9, 525.3]),
    Region(19, 0, True, [72.6, 111.5, 263.1, 305.6, 339.5, 403.0, 454.9, 525.1]),
    Region(19, 1, False, [72.6, 99.0, 291.6, 339.5, 391.0, 454.9, 525.1]),
    Region(20, 0, False, [72.7, 102.7, 309.0, 350.1, 403.8, 454.8, 524.9]),
    Region(20, 1, True, [72.7, 102.7, 247.2, 309.0, 350.1, 403.8, 454.8, 524.9]),
    Region(21, 0, False, [73.0, 103.1, 312.7, 347.6, 404.9, 454.4, 524.4]),
    Region(21, 1, False, [73.0, 103.1, 305.9, 347.6, 395.4, 447.7, 524.4]),
    Region(21, 3, False, [73.0, 103.1, 305.9, 347.6, 395.4, 447.7, 524.4]),
]

ID_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?\.?$")
NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
GROUP_CODES = {"G": "Girls", "B": "Boys", "T": "Total", "F": "Female", "M": "Male"}
GROUP_WORDS = {"Reading", "Numeracy", "Nepali", "English", "Math", "Science",
               "Basic", "Advanced"}
GROUP_MULTI = {"Three": "Three core subjects", "Five": "Five core subjects"}

EXPECTED_YEARS = {
    "base": {"2021/22", "2078"},
    "target": {"2025/26", "2082"},
    "ach": {"2025/26", "2082"},
}
YEAR_RE = re.compile(r"^\d{4}(?:/\d{2})?$")

RATE_TOLERANCE = 0.1   # figures are printed to one decimal place

# The three GER indicators that the GER_RANGE check relies on.
GER_NAMES = {"2.1.5": "GER in Grade 1-5", "2.1.7": "GER in Grade 6-8",
             "2.1.9": "GER in Grade 1-8"}

# Superscript footnote markers are printed at 7pt; every other word on these
# pages is 10pt or larger. A marker glued to a number ("2213" + "1") would
# otherwise be read as one number ("22131").
MARKER_MAX_SIZE = 8.0
WORD_ATTRS = ["size"]

COLUMNS = [
    "section_no", "indicator_id", "indicator", "unit", "group_code", "group",
    "base_2021_22", "target_2025_26", "achievement_2025_26",
    "base_note", "target_note", "achievement_note", "pdf_page", "qa_flag",
]


class ExtractionError(Exception):
    """Raised when the PDF layout does not match what this script expects."""


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------

def centre_x(word):
    """Horizontal centre of a pdfplumber word."""
    return (word["x0"] + word["x1"]) / 2.0


def centre_y(word):
    """Vertical centre of a pdfplumber word."""
    return (word["top"] + word["bottom"]) / 2.0


def column_of(word, edges):
    """Index of the column whose edges contain the word's centre, or None."""
    centre = centre_x(word)
    for index, (left, right) in enumerate(zip(edges[:-1], edges[1:])):
        if left <= centre < right:
            return index
    return None


def rule_clusters(page, bbox, id_left, id_right):
    """Horizontal edges that touch the ID column, grouped by height (1.5 pt)."""
    top, bottom = bbox[1], bbox[3]
    edges = [e for e in page.edges
             if e["orientation"] == "h" and top - 2 <= e["top"] <= bottom + 2
             and e["x1"] > id_left and e["x0"] < id_right]
    edges.sort(key=lambda e: e["top"])
    clusters = []
    for edge in edges:
        if clusters and edge["top"] - clusters[-1][-1]["top"] <= 1.5:
            clusters[-1].append(edge)
        else:
            clusters.append([edge])
    return clusters


def covered_width(cluster, id_left, id_right):
    """Width of the ID column that the edges of one cluster cover together."""
    spans = sorted((max(e["x0"], id_left), min(e["x1"], id_right)) for e in cluster)
    covered = 0.0
    cur_start, cur_end = spans[0]
    for start, end in spans[1:]:
        if start <= cur_end + 1.0:
            cur_end = max(cur_end, end)
        else:
            covered += cur_end - cur_start
            cur_start, cur_end = start, end
    return covered + (cur_end - cur_start)


def separator_ys(page, bbox, id_left, id_right, min_cover=0.97):
    """Y positions of the horizontal rules that run across the whole ID column.

    An indicator's ID cell is one merged cell, so a rule that crosses it
    separates two indicators. The rules between the girls/boys/total rows of one
    indicator stop at that merged cell, so they are ignored. So are the edges of
    the small shaded boxes inside it: they cover at most ~90% of the column
    width in this PDF, while real rules cover 100%.
    """
    top, bottom = bbox[1], bbox[3]
    width = id_right - id_left
    cuts = [sum(e["top"] for e in cluster) / len(cluster)
            for cluster in rule_clusters(page, bbox, id_left, id_right)
            if covered_width(cluster, id_left, id_right) >= min_cover * width]
    if not cuts or cuts[0] > top + 3:
        cuts.insert(0, top)
    if cuts[-1] < bottom - 3:
        cuts.append(bottom)
    return cuts


def lines_of(words, tol=2.0):
    """Group words into visual lines (same y within tol); each line left to right."""
    ordered = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines = []
    for word in ordered:
        if lines and abs(word["top"] - lines[-1][0]["top"]) <= tol:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def line_texts(words):
    """One string per visual line."""
    return [" ".join(w["text"] for w in line) for line in lines_of(words)]


def join_name(words):
    """Join name lines; a line ending in a hyphen/en dash joins the next with no space."""
    out = ""
    for text in line_texts(words):
        if out and out[-1] in "-\u2013":
            out += text
        elif out:
            out += " " + text
        else:
            out = text
    return out.strip()


# --------------------------------------------------------------------------
# value handling
# --------------------------------------------------------------------------

def merge_open_brackets(cells):
    """Join cells like '44.9 (2024' + 'AD)' that were split across lines."""
    merged = []
    i = 0
    while i < len(cells):
        cell = cells[i]
        while cell.count("(") > cell.count(")") and i + 1 < len(cells):
            i += 1
            cell = cell + " " + cells[i]
        merged.append(cell)
        i += 1
    return merged


def is_qualifier(cell):
    """True for text such as 'ECED - G 5' that describes the figures below it."""
    if cell in ("NA", "-"):
        return False
    stripped = re.sub(r"\([^)]*\)", "", cell)
    return bool(re.search(r"[A-Za-z]", stripped))


def parse_value(cell):
    """Split a printed cell into (number-as-text, note)."""
    if cell is None:
        return "", ""
    text = cell.strip()
    if text == "":
        return "", ""
    if text in ("-", "NA"):
        return "", text
    match = re.match(r"^(\S+)\s*\((.*)\)$", text)
    note = ""
    if match:
        text, note = match.group(1), match.group(2).strip()
    number = text.replace(",", "")
    if not NUM_RE.match(number):
        raise ExtractionError(f"cannot read value {cell!r}")
    return number, note


def pair_column(cells, group_count, label):
    """Assign the value cells of one column to the block's groups, in order.

    Returns (values, qualifier). Only three situations are allowed:
    one cell per group, no cells at all (nothing printed), or a single '-'
    that spans every group. Anything else raises.
    """
    cells = merge_open_brackets(cells)
    qualifiers = [c for c in cells if is_qualifier(c)]
    values = [c for c in cells if not is_qualifier(c)]
    if len(qualifiers) > 1:
        raise ExtractionError(f"{label}: more than one qualifier {qualifiers!r}")
    qualifier = qualifiers[0] if qualifiers else ""

    if len(values) == group_count:
        paired = values
    elif not values:
        paired = [""] * group_count
    elif len(values) == 1 and values[0] == "-":
        paired = ["-"] * group_count
    else:
        raise ExtractionError(
            f"{label}: {len(values)} value cells for {group_count} groups: {values!r}")
    return paired, qualifier


def read_groups(words, label):
    """Split the words of the group column into (group codes, name overflow).

    A block either has group labels (G/B/T, Reading, ...) or none. When it has
    none, the column only holds the tail of a long indicator name that runs over
    the column edge. A mix of labels and other words cannot be told apart
    safely, so it raises.
    """
    ordered = sorted(words, key=lambda w: (w["top"], w["x0"]))
    codes = []
    overflow = []
    i = 0
    while i < len(ordered):
        text = ordered[i]["text"]
        following = [w["text"] for w in ordered[i + 1:i + 3]]
        if text in GROUP_MULTI and following == ["core", "subjects"]:
            codes.append(GROUP_MULTI[text])
            i += 3
            continue
        if text in GROUP_CODES or text in GROUP_WORDS or text == "-":
            codes.append(text)
        else:
            overflow.append(ordered[i])
        i += 1
    if codes and overflow:
        raise ExtractionError(
            f"{label}: group column mixes labels {codes!r} with other words "
            f"{[w['text'] for w in overflow]!r}")
    return codes, overflow


# --------------------------------------------------------------------------
# reading one indicator block
# --------------------------------------------------------------------------

def split_by_role(band_words, region):
    """Sort a block's words into table columns. Returns (words by role, markers)."""
    markers = [w for w in band_words if w["size"] <= MARKER_MAX_SIZE]
    by_role = {role: [] for role in region.roles}
    for word in band_words:
        if word["size"] <= MARKER_MAX_SIZE:
            continue
        col = column_of(word, region.edges)
        if col is None:
            raise ExtractionError(
                f"{region.label}: word {word['text']!r} outside table columns")
        by_role[region.roles[col]].append(word)
    return by_role, markers


def read_indicator_id(by_role, region):
    """Return (indicator id, stray words in the ID column); exactly one ID is required."""
    id_words = [w for w in by_role["id"] if ID_RE.match(w["text"])]
    stray = [w["text"] for w in by_role["id"] if not ID_RE.match(w["text"])]
    if len(id_words) != 1:
        raise ExtractionError(
            f"{region.label}: block has {len(id_words)} indicator IDs "
            f"({[w['text'] for w in id_words]!r})")
    return id_words[0]["text"].rstrip("."), stray


def read_name_unit_groups(by_role, label):
    """Return (name, unit, group codes) of a block; '-' group cells are dropped."""
    name_words = list(by_role["name"])
    codes = []
    if "group" in by_role:
        codes, overflow = read_groups(by_role["group"], label)
        name_words.extend(overflow)
    unit_lines = line_texts(by_role["unit"])
    unit = unit_lines[0] if len(set(unit_lines)) == 1 else " ".join(unit_lines)
    codes = [c for c in codes if c != "-"]
    return join_name(name_words), unit, codes or [""]


def read_value_columns(by_role, group_count, label):
    """Pair the cells of the three year columns with the groups.

    Returns (cells by role, qualifier by role).
    """
    columns = {}
    qualifiers = {}
    for role, _, _ in VALUE_COLUMNS:
        columns[role], qualifiers[role] = pair_column(
            line_texts(by_role[role]), group_count, f"{label} {role}")
    return columns, qualifiers


def place_footnotes(markers, region, group_count, footnotes, label):
    """Footnote text per value column, from the superscript markers in a block."""
    notes = {}
    for mark in markers:
        col = column_of(mark, region.edges)
        role = region.roles[col] if col is not None else None
        if (role not in ("base", "target", "ach") or group_count != 1
                or mark["text"] not in footnotes or role in notes):
            raise ExtractionError(f"{label}: cannot place footnote marker {mark['text']!r}")
        notes[role] = f"footnote {mark['text']}: {footnotes[mark['text']]}"
    return notes


def read_cell(cell, qualifier, footnote, label):
    """Number and combined note text of one printed cell."""
    try:
        number, note = parse_value(cell)
    except ExtractionError as err:
        raise ExtractionError(f"{label}: {err}") from err
    return number, "; ".join(t for t in (qualifier, note, footnote) if t)


def make_rows(common, codes, columns, qualifiers, footnote_notes):
    """One row dict per group, from the paired value cells of a block."""
    rows = []
    for i, code in enumerate(codes):
        row = common.copy()
        row["group_code"] = code
        row["group"] = GROUP_CODES.get(code, code)
        for role, value_key, note_key in VALUE_COLUMNS:
            row[value_key], row[note_key] = read_cell(
                columns[role][i], qualifiers[role], footnote_notes.get(role, ""),
                f"{common['indicator_id']} {role}")
        rows.append(row)
    return rows


def read_block(band_words, region, footnotes):
    """Turn the words of one indicator block into (indicator id, name, row dicts).

    A sub-heading row such as "1.1 Access and Participation" has an ID but no
    values or groups; it returns name None and no rows.
    """
    by_role, markers = split_by_role(band_words, region)
    indicator_id, stray = read_indicator_id(by_role, region)
    if not (any(by_role[role] for role in ("base", "target", "ach"))
            or by_role.get("group")):
        return indicator_id, None, []
    label = f"{region.label} {indicator_id}"
    if stray:
        raise ExtractionError(f"{label}: unexpected words in ID column {stray!r}")

    name, unit, codes = read_name_unit_groups(by_role, label)
    columns, qualifiers = read_value_columns(by_role, len(codes), label)
    footnote_notes = place_footnotes(markers, region, len(codes), footnotes, label)
    common = {
        "section_no": int(indicator_id.split(".")[0]),
        "indicator_id": indicator_id,
        "indicator": name,
        "unit": unit,
        "pdf_page": region.page,
    }
    return indicator_id, name, make_rows(common, codes, columns, qualifiers,
                                         footnote_notes)


# --------------------------------------------------------------------------
# reading the pages
# --------------------------------------------------------------------------

def page_words(page):
    """All words of a page, with their font size."""
    return page.extract_words(x_tolerance=1.5, y_tolerance=2, extra_attrs=WORD_ATTRS)


def inside(word, bbox):
    """True if the centre of the word lies inside the box (1 pt margin)."""
    return (bbox[0] - 1 <= centre_x(word) <= bbox[2] + 1
            and bbox[1] - 1 <= centre_y(word) <= bbox[3] + 1)


def read_footnotes(page, boxes):
    """Footnote texts printed outside the tables, as {marker: text}."""
    outside = [w for w in page_words(page) if not any(inside(w, b) for b in boxes)]
    notes = {}
    for mark in outside:
        if mark["size"] > MARKER_MAX_SIZE:
            continue
        line = [w for w in outside if w["size"] > MARKER_MAX_SIZE
                and abs(w["top"] - mark["top"]) <= 3 and w["x0"] > mark["x1"]]
        if not re.match(r"^\d$", mark["text"]) or not line:
            raise ExtractionError(f"page footnote {mark['text']!r} has no readable text")
        notes[mark["text"]] = " ".join(w["text"] for w in sorted(line, key=lambda w: w["x0"]))
    return notes


def header_year_problems(header_words, region):
    """Years printed in a table header that differ from the rest of the report."""
    problems = []
    for word in header_words:
        if not YEAR_RE.match(word["text"]):
            continue
        col = column_of(word, region.edges)
        role = region.roles[col] if col is not None else None
        if role in EXPECTED_YEARS and word["text"] not in EXPECTED_YEARS[role]:
            problems.append((role, word["text"]))
    return problems


def find_table(page, region):
    """The pdfplumber table for a region, checked against the hard-coded edges."""
    tables = page.find_tables()
    if region.index >= len(tables):
        raise ExtractionError(f"page {region.page} has no table {region.index}")
    table = tables[region.index]
    if len(region.edges) != len(region.roles) + 1:
        raise ExtractionError(f"{region.label}: wrong number of column edges")
    if not (abs(table.bbox[0] - region.edges[0]) < 3
            and abs(table.bbox[2] - region.edges[-1]) < 3):
        raise ExtractionError(f"{region.label}: table is not where expected {table.bbox!r}")
    return table


def read_region(page, region, footnotes):
    """Read one table. Returns ([(indicator id, rows), ...], header year problems).

    Sub-heading rows are left out of the list.
    """
    table = find_table(page, region)
    words = [w for w in page_words(page) if inside(w, table.bbox)]
    if not any(w["text"] in ("S.N.", "S.N") for w in words):
        raise ExtractionError(f"{region.label}: header 'S.N.' not found")

    cuts = separator_ys(page, table.bbox, region.edges[0], region.edges[1])
    header_words = []
    blocks = []
    for y_lo, y_hi in zip(cuts[:-1], cuts[1:]):
        band = [w for w in words if y_lo < centre_y(w) <= y_hi]
        if not band:
            continue
        has_id = any(column_of(w, region.edges) == 0 and ID_RE.match(w["text"])
                     for w in band)
        if not has_id and not blocks:
            header_words.extend(band)
            continue
        if not has_id:
            raise ExtractionError(
                f"{region.label}: band at y={y_lo:.1f} has text but no indicator ID: "
                f"{[w['text'] for w in band]!r}")
        blocks.append(read_block(band, region, footnotes))
    problems = header_year_problems(header_words, region)
    return [(ind, rows) for ind, name, rows in blocks if name is not None], problems


def extract_all(pdf):
    """Extract every indicator row from the KPI pages."""
    footnotes_by_page = {}
    for page_no in sorted({r.page for r in REGIONS}):
        page = pdf.pages[page_no - 1]
        boxes = [find_table(page, r).bbox for r in REGIONS if r.page == page_no]
        footnotes_by_page[page_no] = read_footnotes(page, boxes)

    all_rows = []
    seen_ids = []
    for region in REGIONS:
        blocks, problems = read_region(pdf.pages[region.page - 1], region,
                                       footnotes_by_page[region.page])
        for indicator_id, rows in blocks:
            seen_ids.append(indicator_id)
            for row in rows:
                row["_block"] = len(seen_ids)
                row["_header_problems"] = problems
                all_rows.append(row)
    return all_rows, seen_ids


# --------------------------------------------------------------------------
# data-quality flags (computed from the extracted values)
# --------------------------------------------------------------------------

def to_number(text):
    """Number from an extracted value, or None."""
    return float(text) if text not in ("", None) else None


def flag_duplicate_ids(table, seen_ids, flags):
    """DUPLICATE_ID: an indicator number used more than once."""
    duplicated = {i for i in seen_ids if seen_ids.count(i) > 1}
    for idx, indicator_id in enumerate(table["indicator_id"]):
        if indicator_id in duplicated:
            flags[idx].append(
                f"DUPLICATE_ID: indicator number {indicator_id} is printed twice "
                "in the source for two different indicators")


def flag_fractional_counts(table, flags):
    """UNIT_COUNT_FRACTIONAL: unit "No." but a value has decimals."""
    for idx, row in table.iterrows():
        if row["unit"] == "No." and any("." in row[c] for c in VALUE_KEYS):
            flags[idx].append(
                "UNIT_COUNT_FRACTIONAL: unit is printed as 'No.' but a value is "
                "fractional, so it cannot be a head-count")


def sum_problem(column, codes, vals):
    """GBT_SUM message if the first two groups do not add up to the total."""
    if vals[0] + vals[1] == vals[2]:
        return None
    diff = int(vals[2] - vals[0] - vals[1])
    return (f"GBT_SUM: {column}: {codes[0]} + {codes[1]} = {int(vals[0] + vals[1])} "
            f"but Total is printed as {int(vals[2])} (diff {diff:+d})")


def range_problem(column, codes, cells, vals):
    """TOTAL_RANGE message if the total lies outside the two group rates."""
    low, high = min(vals[0], vals[1]), max(vals[0], vals[1])
    if (round(low - vals[2], 6) <= RATE_TOLERANCE
            and round(vals[2] - high, 6) <= RATE_TOLERANCE):
        return None
    return (f"TOTAL_RANGE: {column}: Total {cells[2]} is outside the range of "
            f"{codes[0]} ({cells[0]}) and {codes[1]} ({cells[1]}); a total rate must "
            "lie between the two group rates (0.1 allowed for rounding)")


def flag_totals(table, flags):
    """GBT_SUM and TOTAL_RANGE for blocks with three groups ending in a total.

    Blocks are used instead of indicator numbers because 3.3.7 is printed twice.
    """
    for _, grp in table.groupby("_block", sort=False):
        codes = list(grp["group_code"])
        if len(grp) != 3 or codes not in (["G", "B", "T"], ["F", "M", "T"]):
            continue
        units = set(grp["unit"])
        for column in VALUE_KEYS:
            cells = list(grp[column])
            vals = [to_number(v) for v in cells]
            if None in vals:
                continue
            problem = None
            if units == {"No."} and all(v == int(v) for v in vals):
                problem = sum_problem(column, codes, vals)
            elif units == {"%"}:
                problem = range_problem(column, codes, cells, vals)
            if problem:
                flags[grp.index[2]].append(problem)


def flag_ger_range(table, flags):
    """GER_RANGE: GER 1-8 (2.1.9) must lie between GER 1-5 (2.1.5) and GER 6-8 (2.1.7)."""
    lookup = {(r["indicator_id"], r["group_code"]): r for _, r in table.iterrows()}
    for indicator_id, expected in GER_NAMES.items():
        names = set(table.loc[table["indicator_id"] == indicator_id, "indicator"])
        if names != {expected}:
            raise ExtractionError(f"{indicator_id} is {names!r}, expected {expected!r}")
    for idx, row in table.iterrows():
        if row["indicator_id"] != "2.1.9":
            continue
        low = lookup[("2.1.5", row["group_code"])]
        high = lookup[("2.1.7", row["group_code"])]
        for column in VALUE_KEYS:
            vals = [to_number(low[column]), to_number(high[column]), to_number(row[column])]
            if None in vals:
                continue
            if not min(vals[0], vals[1]) <= vals[2] <= max(vals[0], vals[1]):
                flags[idx].append(
                    f"GER_RANGE: {column}: GER 1-8 = {row[column]} is outside the range of "
                    f"GER 1-5 ({low[column]}) and GER 6-8 ({high[column]}); a combined "
                    "GER must lie between them")


def flag_header_years(table, flags):
    """HEADER_YEAR: years in a table header that differ from the other tables."""
    for idx, problems in enumerate(table["_header_problems"]):
        if problems:
            text = ", ".join(f"{ROLE_NAMES[role]} column prints {year}"
                             for role, year in problems)
            flags[idx].append(
                f"HEADER_YEAR: table header: {text} (other tables print "
                "2021/22 / 2078 BS and 2025/26 / 2082 BS)")


def build_flags(table, seen_ids):
    """Return a list of qa_flag strings, one per row of the table."""
    flags = [[] for _ in range(len(table))]
    flag_duplicate_ids(table, seen_ids, flags)
    flag_fractional_counts(table, flags)
    flag_totals(table, flags)
    flag_ger_range(table, flags)
    flag_header_years(table, flags)
    return ["; ".join(f) for f in flags]


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    """Extract the KPI table and write the CSV."""
    if not PDF_PATH.exists():
        print(f"Missing {PDF_PATH} - download the Flash I Report PDF and save it there.")
        return 1
    with pdfplumber.open(PDF_PATH) as pdf:
        rows, seen_ids = extract_all(pdf)

    if len(seen_ids) != EXPECTED_BLOCKS or len(rows) != EXPECTED_ROWS:
        raise ExtractionError(
            f"expected {EXPECTED_BLOCKS} indicators / {EXPECTED_ROWS} rows, "
            f"got {len(seen_ids)} / {len(rows)}")

    table = pd.DataFrame(rows)
    table["qa_flag"] = build_flags(table, seen_ids)
    table = table[COLUMNS]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT_PATH, index=False)
    flagged = int((table["qa_flag"] != "").sum())
    print(f"OK  {len(seen_ids)} indicators, {len(table)} rows -> {OUTPUT_PATH.name} "
          f"({flagged} rows carry a qa_flag)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
