# Nepal Open Education Data Engine

Nepal's national school census, taken out of a PDF and put back into a shape you can actually use efficiently.

**Live dashboard:** https://nepal-education-data-engine.streamlit.app/

Every year the Centre for Education and Human Resource Development (CEHRD) publishes the Flash Report, the headline numbers on schools, students and teachers across all seven provinces. The data is real and useful. It is also trapped in a PDF of more than 60 pages, with tables have merged header cells, wrapped labels and values that sit one column away from the label they belong to. There is no clean, machine-readable version of it anywhere.

This repo is my attempt at one. It reads the Flash I Report 2082 (2025/26), rebuilds its tables as CSV files, checks every number it extracts against the PDF, and serves the result in a small dashboard.

| | |
|---|---|
| Source | CEHRD Flash I Report 2082 (2025/26) |
| Tables extracted from the PDF | 71, across pages 12 to 63 |
| Rows / values | 616 rows, about 5,000 values |
| Values confirmed present on their source page | 4,909 of 4,909 numeric cells |
| SESP KPI indicator table | 185 rows, 94 indicators, 513 numbers, each confirmed on its page |
| Mistakes found in the original report | listed [below](#mistakes-in-the-original-report) |

## Why this exists

I started with a different question: could Google search trends predict dengue outbreaks in Nepal? That went nowhere, and not because of the statistics. The health data I needed was spread across files that contradicted each other, with no official source of truth to settle it.

I took the problem to officials at Nepal's Ministry of Science, Technology and Innovation (MOSTI). Their advice was practical. Don't write formal letters asking for raw data. Build a working prototype that shows the fix is possible, and let that make the argument.

Education was the place to build it, because CEHRD already publishes its data and the PDF is a hard, honest test. This project is that prototype.

## What the problem actually looks like

Take Table 2.4, children with disabilities in institutional ECED. The PDF has one header row, and the province name is a merged cell that spans three rows (Girls, Boys, Total). A standard extraction gives you this:

```
Province_Koshi | Gender_Girls | 1_116 | 2_13 | 3_2 | ... | Total_199
None           | Boys         | 170   | 16   | 10  | ... | 306
None           | Total        | 286   | 29   | 12  | ... | 505
```

The Koshi/Girls row has been read as the header, so those numbers became column names and disappeared from the data. The province is missing from two rows out of three. Nothing errors. The file looks fine and is wrong.

What the extractor produces:

```
Province | Gender | 1   | 2  | 3  | ... | Total
Koshi    | Girls  | 116 | 13 | 2  | ... | 199
Koshi    | Boys   | 170 | 16 | 10 | ... | 306
Koshi    | Total  | 286 | 29 | 12 | ... | 505
```

Most of the work in this repo is getting that kind of table right, one layout at a time, without ever letting a number land in the wrong column unnoticed.

## How the extractor works

`src/extractor.py` keeps a registry, the `TABLES` list. Each entry says which page a table is on, which table on that page, which layout pattern it follows, and what to call the output file. pdfplumber reads the raw cells, the matching pattern repairs them, and pandas writes `data/processed/table_<number>_<name>.csv`.

There are ten patterns, because the PDF has more than one way to break a table:

| Pattern | What it fixes | Example |
|---|---|---|
| `shift_bug` | A merged header pushes each value into one of three raw columns, depending on the row. Take the one that is filled. | 3.1, 2.1 |
| `direct_clean` | Header is merged but the data is fine. Collapsing it would silently delete real values, so it doesn't. | 6.1, 4.7 |
| `single_header_grouped` | One header row, and the province name floats over a Girls/Boys/Total group. | 2.3, 2.4 |
| `three_header` | Three stacked header rows. | 2.7 |
| `title_then_header` | A title row sits above the header. | 4.20 |
| `shift_two_label` | Like `shift_bug`, but two label columns before the shifting starts. | 2.9 |
| `stacked_header` | Header text wrapped across several rows, or one value spread over three columns. | 2.11, 3.3, 4.8 |
| `single_header` | Clean header. Only the total-row labels need normalising. | 3.5, 4.16 |
| `named_columns` | Header too tangled to trust. Column names are written by hand and checked against the printed page. Values are collected under strict rules. | 4.12 to 4.15, 5.6 to 5.12 |
| `split_rows` | One logical row spread over several raw rows. | Key finding 3 |

The rule behind all of it: **fail loudly**. In the strict modes, a row that doesn't have the expected number of values, or has a value in a position the table never uses, stops the run with an error. A crash is annoying. A wrong number in a public dataset is worse.

## How I know the numbers are right

Extraction code can be wrong in ways that look fine. So every table goes through four checks:

1. **Strict shape.** Described above. A row that doesn't fit never makes it into a CSV.
2. **Cross-check against the text layer.** Every numeric cell in every CSV is looked up on its source page. For the largest batch of tables I also compared row by row, in order, against the text lines printed in the PDF.
3. **Arithmetic.** Girls plus Boys equals Total. Community plus Institutional equals Total. A "Nepal (%)" row equals the Nepal count divided by the number of schools. Several hundred of these checks catch what the text lookup can't: a value that exists on the page but sits in the wrong column.
4. **No regressions.** After each change to the extractor, every CSV that wasn't supposed to change is compared byte for byte with the previous run.

What this proves is that the CSVs match the PDF. It does not prove the PDF is right. See the next section.

## Mistakes in the original report

The arithmetic checks turned up places where the report disagrees with itself. These are in the published PDF, not introduced by the extraction. I've kept the printed numbers and listed the disagreements here.

- **Tables 2.3 and 2.4:** five province groups where Girls plus Boys does not equal Total (Bagmati, Lumbini and Nepal in 2.3; Karnali and Nepal in 2.4).
- **Table 3.4:** Nepal's average students per school is printed as 73.8. The table's own totals (40,438 students, 569 schools) give 71.1.
- **Table 4.16:** Lumbini's menu columns add up to 4,338 but the school count is 4,438. The gap carries into the Nepal row (26,910 against 27,010).
- **Table 5.10:** the provinces' Local Curriculum counts add up to 3,403. The Nepal row says 3,645.
- **Table 5.9 (SIP and audits, percentage):** the "(1-10) SIP" column repeats the Social Audit percentages. Recomputed from the counts in 5.8, Koshi is 85.7%. The report prints 87.1%.
- **Key finding 3:** in the "Other" row, the Sec (9-12) figure (15,552) is larger than its two parts combined (11,365).
- **Table numbering:** there are two tables called 5.9, and one heading reads "Table 4.2116".
- **KPI table:**
  - 1.2.3, the base-year Total (0.6) falls outside the Girls (0.2) and Boys (0.1) values.
  - 2.1.9, the combined GER for grades 1-8 is higher than both GER 1-5 and GER 6-8, which can't happen.
  - 2.3.5, in the target column, Girls plus Boys exceed the printed Total by 11,578.
  - 3.2.6, the achievement Total is 1,800 above Girls plus Boys.
  - Indicator 3.3.7 is printed twice for two different indicators.
  - The table header says 2081 on page 19 and "2025/25" on page 21.

The KPI CSV carries a `qa_flag` column that marks each of these rows.

## What's in the repo

```
.devcontainer/            Dev container config
.github/workflows/        keep-alive.yml, see below
.streamlit/config.toml    Dashboard colours and theme
data/processed/           The CSVs: table_*.csv, plus sesp_kpi_indicators.csv
src/extractor.py          PDF to CSV
src/app.py                Streamlit dashboard
CITATION.cff              How to cite this repository
requirements.txt
```

**The dashboard** groups every CSV in `data/processed` by chapter of the report and gives each table three views: a chart of any column, the full data with search and a CSV download, and the PDF page it came from. National rows (`Nepal`, `Nepal (No.)`, `Nepal (%)`) stay out of the charts unless you ask for them. The KPI table has its own view, showing base year, target and achievement side by side for each indicator. A separate tab lists the places where the original report disagrees with itself, and tables affected by one carry a warning. Every table has its own link: add `?table=table_4_12_infrastructure_basic_1_5_community` to the dashboard address to open it directly.

**The keep-alive workflow.** Streamlit Community Cloud puts free apps to sleep after a stretch of inactivity. A GitHub Actions job visits the app every six hours in a headless browser and presses the wake-up button if it finds one, so the link in this README works when you click it.

## Run it yourself

You need Python 3.12 and the Flash I Report PDF from the CEHRD website. Rename it `sample.pdf` and put it in `data/raw/`.

```
git clone https://github.com/Bishalneupa/nepal-education-data-engine.git
cd nepal-education-data-engine
python -m venv venv
```

Activate the environment. On Windows:

```
venv\Scripts\activate
```

On macOS or Linux:

```
source venv/bin/activate
```

Then:

```
pip install -r requirements.txt
python src/extractor.py
streamlit run src/app.py
```

The extractor should finish with `71 tables extracted successfully, 0 failed.`

## Limits

- **One report.** This covers the Flash I Report 2082 only. The Annex spreadsheets CEHRD publishes alongside it, which have their own merged-header problems, aren't handled yet.
- **Page numbers are hard-coded.** The registry points at specific pages. A different edition of the report will need its tables registered again.
- **Province names aren't consistent.** The report itself uses `Sudurpashchim`, `Su.Pa` and `SuPa`, and `Bagamati` next to `Bagmati`. I kept the names as printed so each CSV can be compared against the PDF. The tables can't be joined until they're normalised.
- **Values are stored as text.** Some carry thousands separators (`8,265`) and some don't (`8265`), exactly as printed. The dashboard converts them when it charts.
- **File names are best effort.** They carry the table number from the report, and the report's numbering isn't reliable (see above). A few older files were named by best guess. The data in them is verified, but the name may need adjusting.
- **Blank means blank.** In Table 3.4 the Province-run schools column is empty for most provinces in the PDF. I left it empty.

## Next

- A cleaner for the Annex spreadsheets.
- Province-name normalisation, then one combined, queryable dataset.
- Find tables by their printed title instead of page number, so next year's report doesn't need to be registered by hand.
- Move the verification checks into the repo as automated tests. They exist today as scripts I ran by hand, and they should live next to the code.
- Earlier Flash Reports, to turn single-year snapshots into a time series.

## Credits and licence

Dashboard crash fix and the restored Table 3.1 came from [@rcgiri-physics](https://github.com/rcgiri-physics) in pull request #1.

The data belongs to CEHRD, Government of Nepal. The CSVs here are derived from their published report. If you reuse them, cite the original report, and check CEHRD's terms.

The code is released under the MIT licence. See `LICENSE`.

Found a number that doesn't match the PDF? Open an issue with the table number and the value. That's the most useful bug report this project can get.
