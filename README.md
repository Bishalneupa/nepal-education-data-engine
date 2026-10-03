# Nepal Open Education Data Engine

An open-source pipeline that turns Nepal's messy, PDF-locked government education
data into clean, machine-readable datasets and a public dashboard.

## The Problem

Nepal's Ministry of Education (CEHRD) publishes its national education census —
the Flash Report — partly as clean spreadsheets and partly as a 60+ page PDF full
of tables with merged header cells and inconsistent formatting. There is no
clean, unified, machine-readable version of this data available to the public.

This project started as an unrelated research effort trying to correlate Google
Trends search data with dengue outbreaks in Nepal. That research hit a wall:
Nepal's public health data was fragmented across conflicting files with no
official source of truth. Digging into why led to direct consultations with
Nepal's Ministry of Science, Technology and Innovation (MOSTI), including
Minister Mahabir Pun, Dr. Sanjay Poudel, Dr. Bikram, and Dr. Sunil Baniya. Their
advice: instead of requesting raw data through formal letters, build a working
prototype that proves the fix is possible. This project is that prototype,
applied to education data.

## Current Status

This is an early proof of concept, not a finished dataset. Right now it
extracts and cleans **33 tables** from the Flash I Report PDF (listed in
`TABLES` in `src/extractor.py`), including correctly handling a genuinely
messy real-world problem: merged header cells whose actual values shift column
position row to row. That specific fix is the hard part of this project, and
it's proven working end to end: PDF to cleaned CSVs to live dashboard.

Not yet done: the remaining tables in the Flash I Report PDF (listed as
comments in `src/extractor.py`), and the separate Annex spreadsheet files CEHRD
also publishes (which have their own different formatting problems). See
Roadmap below.

## Tech Stack

- pdfplumber — extracts raw table data from the PDF, reading its underlying
  layout geometry
- pandas — cleans and restructures the extracted data
- Streamlit — serves the results as an interactive, filterable dashboard

## How It Works

1. `src/extractor.py` opens the source PDF and extracts each table listed in
   `TABLES` as raw data
2. Because of how the PDF's merged cells are structured, in some tables the raw
   values land in the wrong column position depending on the row. The script
   corrects this by grouping columns and picking whichever cell in each group
   actually contains a value. Tables whose cells are already in place only
   have their headers flattened
3. Each cleaned table is saved to `data/processed/table_<number>_<name>.csv`
4. `src/app.py` loads those CSVs into a Streamlit dashboard where you pick a
   table, filter by province (where the table has one), and chart a column

## Setup

    git clone https://github.com/Bishalneupa/nepal-education-data-engine.git
    cd nepal-education-data-engine
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt

Download a Flash Report PDF from the CEHRD website, rename it `sample.pdf`, and
place it in `data/raw/`.

## Usage

Run the extractor to generate the cleaned CSV:

    python src/extractor.py

Launch the dashboard:

    streamlit run src/app.py

## Roadmap

- Extend `extractor.py` to handle the remaining tables in the Flash I Report
- Build a separate cleaner for the Annex spreadsheet files (multi-row merged
  Excel headers)
- Combine all cleaned tables into one unified, queryable dataset
- Deploy the dashboard publicly (Streamlit Community Cloud)