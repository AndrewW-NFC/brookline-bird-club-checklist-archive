#!/usr/bin/env python3
"""
Build a Datasette-ready SQLite database from the Brookline Bird Club eBird export.

Input: the full tabular export from eBird, with columns like:
Submission ID, Common Name, Scientific Name, Taxonomic Order, Count, State/Province,
County, Location ID, Location, Latitude, Longitude, Date, Time, Protocol, Duration (Min),
All Obs Reported, Distance Traveled (km), Area Covered (ha), Number of Observers,
Breeding Code, Observation Details, Checklist Comments

Usage:
    python build_bbc_ebird_db.py /path/to/export.csv bbc-ebird.db
    python build_bbc_ebird_db.py /path/to/export.tsv bbc-ebird.db --replace

Notes:
- Keeps raw date/count fields and adds parsed/derived fields.
- Two-digit years are parsed using a current-year pivot. By default, yy <= current year
  maps to 20yy and yy > current year maps to 19yy. For 2026, 26=>2026, 46=>1946.
- Creates observation/checklist/location/species tables, public views, indexes, and FTS5 tables.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

EXPECTED_COLUMNS = [
    "Submission ID", "Common Name", "Scientific Name", "Taxonomic Order", "Count",
    "State/Province", "County", "Location ID", "Location", "Latitude", "Longitude",
    "Date", "Time", "Protocol", "Duration (Min)", "All Obs Reported",
    "Distance Traveled (km)", "Area Covered (ha)", "Number of Observers",
    "Breeding Code", "Observation Details", "Checklist Comments",
]

COL = {
    "Submission ID": "submission_id",
    "Common Name": "common_name",
    "Scientific Name": "scientific_name",
    "Taxonomic Order": "taxonomic_order",
    "Count": "count_raw",
    "State/Province": "state_province",
    "County": "county",
    "Location ID": "location_id",
    "Location": "location",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Date": "date_raw",
    "Time": "time_raw",
    "Protocol": "protocol",
    "Duration (Min)": "duration_min",
    "All Obs Reported": "all_obs_reported",
    "Distance Traveled (km)": "distance_traveled_km",
    "Area Covered (ha)": "area_covered_ha",
    "Number of Observers": "number_of_observers",
    "Breeding Code": "breeding_code",
    "Observation Details": "observation_details",
    "Checklist Comments": "checklist_comments",
}

GENERIC_LOCATION_RE = re.compile(
    r"^(Barnstable|Berkshire|Bristol|Dukes|Essex|Franklin|Hampden|Hampshire|Middlesex|Nantucket|Norfolk|Plymouth|Suffolk|Worcester)$",
    re.IGNORECASE,
)
BROAD_LOCATION_RE = re.compile(
    r"\b(vicinity|general area|area|please use more refined location|county|various|route)\b",
    re.IGNORECASE,
)


def clean_text(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    # Common mojibake/replacement artifacts seen in old field-card comments.
    text = text.replace("\u00d4\u00f8\u03a9", "\N{DEGREE SIGN}")
    text = text.replace("&#xfffd;", "\N{DEGREE SIGN}")
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def to_int(value: object) -> Optional[int]:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def to_float(value: object) -> Optional[float]:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_count(value: object) -> Tuple[Optional[int], int, Optional[str]]:
    raw = clean_text(value)
    if raw is None:
        return None, 0, "blank"
    if raw.upper() == "X":
        return None, 1, "presence_only"
    try:
        return int(float(raw)), 0, None
    except ValueError:
        # Preserve unusual eBird values such as estimates or notes in count_raw.
        return None, 0, "non_numeric"


def parse_date(raw: object, current_year: int) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[int], Optional[str], Optional[str]]:
    """Return date_iso, year, month, day, decade, parse_note."""
    text = clean_text(raw)
    if text is None:
        return None, None, None, None, None, "blank_date"

    note = None

    # ISO-style eBird export date: yyyy-mm-dd
    m_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if m_iso:
        year, month, day = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
    else:
        # Sample export form: m/d/yy or m/d/yyyy
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$", text)
        if not m:
            return None, None, None, None, None, "unparsed_date"

        month, day, year_token = int(m.group(1)), int(m.group(2)), m.group(3)

        if len(year_token) == 2:
            yy = int(year_token)
            current_yy = current_year % 100
            if yy <= current_yy:
                year = 2000 + yy
                note = "two_digit_year_current_century"
            else:
                year = 1900 + yy
                note = "two_digit_year_previous_century"
        else:
            year = int(year_token)

    try:
        date_obj = dt.date(year, month, day)
    except ValueError:
        return None, None, None, None, None, "invalid_date"

    decade = f"{year // 10 * 10}s"
    return date_obj.isoformat(), year, month, day, decade, note


def month_name(month: Optional[int]) -> Optional[str]:
    if not month:
        return None
    return dt.date(2000, month, 1).strftime("%B")


def classify_location(location: Optional[str], location_id: Optional[str]) -> str:
    if not location and not location_id:
        return "missing_location"
    if location and GENERIC_LOCATION_RE.match(location):
        return "generic_county_location"
    if location and BROAD_LOCATION_RE.search(location):
        return "broad_or_route_location"
    return "specific_or_hotspot_location"


def sniff_dialect(path: Path) -> csv.Dialect:
    sample = path.read_text(errors="replace")[:10000]
    try:
        return csv.Sniffer().sniff(sample, delimiters=["\t", ",", ";"])
    except csv.Error:
        # eBird exports of this form are often tab-delimited.
        class Tsv(csv.excel_tab):
            pass
        return Tsv


def read_rows(path: Path) -> Iterator[Dict[str, str]]:
    dialect = sniff_dialect(path)
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f, dialect=dialect)
        if not reader.fieldnames:
            raise SystemExit("No header row found.")
        missing = [c for c in EXPECTED_COLUMNS if c not in reader.fieldnames]
        if missing:
            print("Warning: missing expected columns:", ", ".join(missing), file=sys.stderr)
            print("Found columns:", ", ".join(reader.fieldnames), file=sys.stderr)
        for row in reader:
            yield row


def connect(db_path: Path, replace: bool) -> sqlite3.Connection:
    if db_path.exists() and replace:
        db_path.unlink()
    if db_path.exists() and not replace:
        raise SystemExit(f"Database already exists: {db_path}. Use --replace to overwrite.")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS observations;
        DROP TABLE IF EXISTS checklists;
        DROP TABLE IF EXISTS species;
        DROP TABLE IF EXISTS locations;
        DROP TABLE IF EXISTS import_warnings;
        DROP VIEW IF EXISTS observations_public;
        DROP VIEW IF EXISTS checklists_public;
        DROP TABLE IF EXISTS observations_fts;
        DROP TABLE IF EXISTS checklists_fts;

        CREATE TABLE observations (
            observation_id INTEGER PRIMARY KEY,
            submission_id TEXT NOT NULL,
            common_name TEXT,
            scientific_name TEXT,
            taxonomic_order INTEGER,
            count_raw TEXT,
            count_numeric INTEGER,
            presence_only INTEGER NOT NULL DEFAULT 0,
            count_parse_note TEXT,
            state_province TEXT,
            county TEXT,
            location_id TEXT,
            location TEXT,
            latitude REAL,
            longitude REAL,
            date_raw TEXT,
            date_iso TEXT,
            year INTEGER,
            decade TEXT,
            month INTEGER,
            month_name TEXT,
            day INTEGER,
            time_raw TEXT,
            protocol TEXT,
            duration_min INTEGER,
            all_obs_reported INTEGER,
            distance_traveled_km REAL,
            area_covered_ha REAL,
            number_of_observers INTEGER,
            breeding_code TEXT,
            observation_details TEXT,
            checklist_comments TEXT,
            date_parse_note TEXT
        );

        CREATE TABLE checklists (
            submission_id TEXT PRIMARY KEY,
            date_raw TEXT,
            date_iso TEXT,
            year INTEGER,
            decade TEXT,
            month INTEGER,
            month_name TEXT,
            day INTEGER,
            time_raw TEXT,
            protocol TEXT,
            all_obs_reported INTEGER,
            duration_min INTEGER,
            distance_traveled_km REAL,
            area_covered_ha REAL,
            number_of_observers INTEGER,
            state_province TEXT,
            county TEXT,
            location_id TEXT,
            location TEXT,
            latitude REAL,
            longitude REAL,
            checklist_comments TEXT,
            location_precision_flag TEXT,
            ebird_url TEXT,
            species_count INTEGER,
            observation_row_count INTEGER,
            date_parse_note TEXT
        );

        CREATE TABLE species (
            common_name TEXT PRIMARY KEY,
            scientific_name TEXT,
            taxonomic_order INTEGER,
            observation_row_count INTEGER,
            checklist_count INTEGER,
            first_date TEXT,
            last_date TEXT,
            max_count_numeric INTEGER
        );

        CREATE TABLE locations (
            location_id TEXT PRIMARY KEY,
            location TEXT,
            state_province TEXT,
            county TEXT,
            latitude REAL,
            longitude REAL,
            location_precision_flag TEXT,
            checklist_count INTEGER,
            observation_row_count INTEGER
        );

        CREATE TABLE import_warnings (
            warning_id INTEGER PRIMARY KEY,
            category TEXT,
            detail TEXT,
            row_count INTEGER
        );
        """
    )


def import_observations(conn: sqlite3.Connection, input_path: Path, current_year: int, batch_size: int = 5000) -> int:
    sql = """
        INSERT INTO observations (
            submission_id, common_name, scientific_name, taxonomic_order, count_raw,
            count_numeric, presence_only, count_parse_note, state_province, county,
            location_id, location, latitude, longitude, date_raw, date_iso, year, decade,
            month, month_name, day, time_raw, protocol, duration_min, all_obs_reported,
            distance_traveled_km, area_covered_ha, number_of_observers, breeding_code,
            observation_details, checklist_comments, date_parse_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    batch: List[Tuple] = []
    n = 0
    for row in read_rows(input_path):
        submission_id = clean_text(row.get("Submission ID"))
        if not submission_id:
            continue
        count_raw = clean_text(row.get("Count"))
        count_numeric, presence_only, count_note = parse_count(count_raw)
        date_raw = clean_text(row.get("Date"))
        date_iso, year, month, day, decade, date_note = parse_date(date_raw, current_year)
        batch.append((
            submission_id,
            clean_text(row.get("Common Name")),
            clean_text(row.get("Scientific Name")),
            to_int(row.get("Taxonomic Order")),
            count_raw,
            count_numeric,
            presence_only,
            count_note,
            clean_text(row.get("State/Province")),
            clean_text(row.get("County")),
            clean_text(row.get("Location ID")),
            clean_text(row.get("Location")),
            to_float(row.get("Latitude")),
            to_float(row.get("Longitude")),
            date_raw,
            date_iso,
            year,
            decade,
            month,
            month_name(month),
            day,
            clean_text(row.get("Time")),
            clean_text(row.get("Protocol")),
            to_int(row.get("Duration (Min)")),
            to_int(row.get("All Obs Reported")),
            to_float(row.get("Distance Traveled (km)")),
            to_float(row.get("Area Covered (ha)")),
            to_int(row.get("Number of Observers")),
            clean_text(row.get("Breeding Code")),
            clean_text(row.get("Observation Details")),
            clean_text(row.get("Checklist Comments")),
            date_note,
        ))
        if len(batch) >= batch_size:
            conn.executemany(sql, batch)
            n += len(batch)
            batch.clear()
    if batch:
        conn.executemany(sql, batch)
        n += len(batch)
    return n


def build_summary_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        INSERT INTO checklists (
            submission_id, date_raw, date_iso, year, decade, month, month_name, day,
            time_raw, protocol, all_obs_reported, duration_min, distance_traveled_km,
            area_covered_ha, number_of_observers, state_province, county, location_id,
            location, latitude, longitude, checklist_comments, location_precision_flag,
            ebird_url, species_count, observation_row_count, date_parse_note
        )
        SELECT
            submission_id,
            MIN(date_raw), MIN(date_iso), MIN(year), MIN(decade), MIN(month), MIN(month_name), MIN(day),
            MIN(time_raw), MIN(protocol), MIN(all_obs_reported), MIN(duration_min), MIN(distance_traveled_km),
            MIN(area_covered_ha), MIN(number_of_observers), MIN(state_province), MIN(county),
            MIN(location_id), MIN(location), MIN(latitude), MIN(longitude), MIN(checklist_comments),
            NULL,
            'https://ebird.org/checklist/' || submission_id,
            COUNT(DISTINCT common_name),
            COUNT(*),
            MIN(date_parse_note)
        FROM observations
        GROUP BY submission_id;

        UPDATE checklists
        SET location_precision_flag = CASE
            WHEN location IS NULL AND location_id IS NULL THEN 'missing_location'
            WHEN lower(location) IN (
                'barnstable','berkshire','bristol','dukes','essex','franklin','hampden','hampshire',
                'middlesex','nantucket','norfolk','plymouth','suffolk','worcester'
            ) THEN 'generic_county_location'
            WHEN lower(location) LIKE '%vicinity%'
              OR lower(location) LIKE '%general area%'
              OR lower(location) LIKE '%please use more refined location%'
              OR lower(location) LIKE '%various%'
              OR lower(location) LIKE '%route%'
            THEN 'broad_or_route_location'
            ELSE 'specific_or_hotspot_location'
        END;

        INSERT INTO species (
            common_name, scientific_name, taxonomic_order, observation_row_count,
            checklist_count, first_date, last_date, max_count_numeric
        )
        SELECT
            common_name,
            MIN(scientific_name),
            MIN(taxonomic_order),
            COUNT(*),
            COUNT(DISTINCT submission_id),
            MIN(date_iso),
            MAX(date_iso),
            MAX(count_numeric)
        FROM observations
        WHERE common_name IS NOT NULL
        GROUP BY common_name;

        INSERT INTO locations (
            location_id, location, state_province, county, latitude, longitude,
            location_precision_flag, checklist_count, observation_row_count
        )
        SELECT
            location_id,
            MIN(location),
            MIN(state_province),
            MIN(county),
            MIN(latitude),
            MIN(longitude),
            MIN(location_precision_flag),
            COUNT(DISTINCT submission_id),
            SUM(observation_row_count)
        FROM checklists
        WHERE location_id IS NOT NULL
        GROUP BY location_id;
        """
    )


def create_indexes_views_fts(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX idx_obs_common_name ON observations(common_name);
        CREATE INDEX idx_obs_scientific_name ON observations(scientific_name);
        CREATE INDEX idx_obs_submission_id ON observations(submission_id);
        CREATE INDEX idx_obs_location_id ON observations(location_id);
        CREATE INDEX idx_obs_county ON observations(county);
        CREATE INDEX idx_obs_date_iso ON observations(date_iso);
        CREATE INDEX idx_obs_year ON observations(year);
        CREATE INDEX idx_obs_decade ON observations(decade);
        CREATE INDEX idx_obs_month ON observations(month);
        CREATE INDEX idx_obs_protocol ON observations(protocol);
        CREATE INDEX idx_obs_count_numeric ON observations(count_numeric);
        CREATE INDEX idx_obs_breeding_code ON observations(breeding_code);
        CREATE INDEX idx_checklists_date_iso ON checklists(date_iso);
        CREATE INDEX idx_checklists_year ON checklists(year);
        CREATE INDEX idx_checklists_decade ON checklists(decade);
        CREATE INDEX idx_checklists_county ON checklists(county);
        CREATE INDEX idx_checklists_location_id ON checklists(location_id);
        CREATE INDEX idx_checklists_location_precision ON checklists(location_precision_flag);
        CREATE INDEX idx_species_tax_order ON species(taxonomic_order);
        CREATE INDEX idx_locations_county ON locations(county);
        CREATE INDEX idx_locations_precision ON locations(location_precision_flag);

        CREATE VIRTUAL TABLE observations_fts USING fts5(
            common_name,
            scientific_name,
            location,
            county,
            observation_details,
            checklist_comments,
            content='observations',
            content_rowid='observation_id'
        );
        INSERT INTO observations_fts(rowid, common_name, scientific_name, location, county, observation_details, checklist_comments)
        SELECT observation_id, common_name, scientific_name, location, county, observation_details, checklist_comments
        FROM observations;

        CREATE VIRTUAL TABLE checklists_fts USING fts5(
            location,
            county,
            checklist_comments,
            content='checklists',
            content_rowid='rowid'
        );
        INSERT INTO checklists_fts(rowid, location, county, checklist_comments)
        SELECT rowid, location, county, checklist_comments
        FROM checklists;
        """
    )


def add_warnings(conn: sqlite3.Connection) -> None:
    queries = [
        ("date", "blank_or_unparsed_date", "SELECT COUNT(*) FROM observations WHERE date_iso IS NULL"),
        ("date", "two_digit_year_current_century", "SELECT COUNT(*) FROM observations WHERE date_parse_note = 'two_digit_year_current_century'"),
        ("date", "two_digit_year_previous_century", "SELECT COUNT(*) FROM observations WHERE date_parse_note = 'two_digit_year_previous_century'"),
        ("count", "presence_only_X", "SELECT COUNT(*) FROM observations WHERE presence_only = 1"),
        ("count", "non_numeric_count", "SELECT COUNT(*) FROM observations WHERE count_parse_note = 'non_numeric'"),
        ("location", "generic_county_location_checklists", "SELECT COUNT(*) FROM checklists WHERE location_precision_flag = 'generic_county_location'"),
        ("location", "broad_or_route_location_checklists", "SELECT COUNT(*) FROM checklists WHERE location_precision_flag = 'broad_or_route_location'"),
        ("location", "missing_coordinates", "SELECT COUNT(*) FROM checklists WHERE latitude IS NULL OR longitude IS NULL"),
    ]
    for category, detail, q in queries:
        count = conn.execute(q).fetchone()[0]
        conn.execute("INSERT INTO import_warnings(category, detail, row_count) VALUES (?, ?, ?)", (category, detail, count))


def create_public_views(conn: sqlite3.Connection) -> None:
    """Create public-facing Datasette views for novice archive browsing."""
    conn.executescript("""
    DROP VIEW IF EXISTS search_species_records;
    DROP VIEW IF EXISTS browse_checklists;
    DROP VIEW IF EXISTS browse_locations;
    DROP VIEW IF EXISTS browse_species_summary;

    CREATE VIEW search_species_records AS
    SELECT
        o.common_name AS "Common Name",
        o.scientific_name AS "Scientific Name",
        o.count_raw AS "Count",
        o.count_numeric AS "Numeric Count",
        o.presence_only AS "Presence Only",
        o.date_iso AS "Date",
        o.year AS "Year",
        o.decade AS "Decade",
        o.month_name AS "Month",
        o.day AS "Day",
        o.time_raw AS "Time",
        o.county AS "County",
        o.location AS "Location",
        c.location_precision_flag AS "Location Precision",
        o.protocol AS "Protocol",
        o.breeding_code AS "Breeding Code",
        o.observation_details AS "Observation Details",
        o.checklist_comments AS "Checklist Comments",
        o.submission_id AS "Submission ID",
        c.ebird_url AS "eBird Checklist"
    FROM observations o
    LEFT JOIN checklists c
        ON o.submission_id = c.submission_id;

    CREATE VIEW browse_checklists AS
    SELECT
        date_iso AS "Date",
        year AS "Year",
        decade AS "Decade",
        month_name AS "Month",
        day AS "Day",
        time_raw AS "Time",
        protocol AS "Protocol",
        county AS "County",
        location AS "Location",
        location_precision_flag AS "Location Precision",
        species_count AS "Species Count",
        observation_row_count AS "Observation Rows",
        number_of_observers AS "Observers",
        duration_min AS "Duration Min",
        distance_traveled_km AS "Distance km",
        area_covered_ha AS "Area ha",
        all_obs_reported AS "All Observations Reported",
        checklist_comments AS "Checklist Comments",
        submission_id AS "Submission ID",
        ebird_url AS "eBird Checklist"
    FROM checklists;

    CREATE VIEW browse_locations AS
    WITH location_dates AS (
        SELECT
            location_id,
            MIN(date_iso) AS first_date,
            MAX(date_iso) AS last_date,
            COUNT(DISTINCT common_name) AS species_count
        FROM observations
        WHERE location_id IS NOT NULL
        GROUP BY location_id
    )
    SELECT
        l.location AS "Location",
        l.location_id AS "Location ID",
        l.county AS "County",
        l.state_province AS "State/Province",
        l.latitude AS "Latitude",
        l.longitude AS "Longitude",
        l.location_precision_flag AS "Location Precision",
        l.checklist_count AS "Checklist Count",
        l.observation_row_count AS "Observation Rows",
        d.species_count AS "Species Count",
        d.first_date AS "First Date",
        d.last_date AS "Last Date"
    FROM locations l
    LEFT JOIN location_dates d
        ON l.location_id = d.location_id;

    CREATE VIEW browse_species_summary AS
    SELECT
        common_name AS "Common Name",
        scientific_name AS "Scientific Name",
        observation_row_count AS "Observation Rows",
        checklist_count AS "Checklist Count",
        first_date AS "First Date",
        last_date AS "Last Date",
        max_count_numeric AS "High Count",
        taxonomic_order AS "Taxonomic Order"
    FROM species;
    """)


def create_supplemental_public_views(conn: sqlite3.Connection) -> None:
    """Create supplemental public archive views for Datasette.

    These views are derived from the normalized source tables and are safe to recreate
    on every monthly data refresh.
    """
    conn.executescript("""
    DROP VIEW IF EXISTS observations_public;
    DROP VIEW IF EXISTS checklists_public;

    DROP VIEW IF EXISTS broad_location_checklists;
    DROP VIEW IF EXISTS high_counts;
    DROP VIEW IF EXISTS earliest_records_by_species;
    DROP VIEW IF EXISTS latest_records_by_species;
    DROP VIEW IF EXISTS historical_field_card_checklists;
    DROP VIEW IF EXISTS comment_search_helper;

    CREATE VIEW broad_location_checklists AS
    SELECT
        date_iso AS "Date",
        year AS "Year",
        decade AS "Decade",
        month_name AS "Month",
        day AS "Day",
        protocol AS "Protocol",
        county AS "County",
        location AS "Location",
        location_precision_flag AS "Location Precision",
        species_count AS "Species Count",
        observation_row_count AS "Observation Rows",
        number_of_observers AS "Observers",
        duration_min AS "Duration Min",
        distance_traveled_km AS "Distance km",
        checklist_comments AS "Checklist Comments",
        submission_id AS "Submission ID",
        ebird_url AS "eBird Checklist"
    FROM checklists
    WHERE location_precision_flag IN ('generic_county_location', 'broad_or_route_location');

    CREATE VIEW high_counts AS
    SELECT
        o.common_name AS "Common Name",
        o.scientific_name AS "Scientific Name",
        o.count_numeric AS "Numeric Count",
        o.count_raw AS "Count",
        o.date_iso AS "Date",
        o.year AS "Year",
        o.decade AS "Decade",
        o.month_name AS "Month",
        o.county AS "County",
        o.location AS "Location",
        c.location_precision_flag AS "Location Precision",
        o.protocol AS "Protocol",
        o.observation_details AS "Observation Details",
        o.checklist_comments AS "Checklist Comments",
        o.submission_id AS "Submission ID",
        c.ebird_url AS "eBird Checklist"
    FROM observations o
    LEFT JOIN checklists c
        ON o.submission_id = c.submission_id
    WHERE o.count_numeric IS NOT NULL
    ORDER BY o.count_numeric DESC;

    CREATE VIEW earliest_records_by_species AS
    WITH ranked AS (
        SELECT
            o.*,
            c.location_precision_flag,
            c.ebird_url,
            ROW_NUMBER() OVER (
                PARTITION BY o.common_name
                ORDER BY o.date_iso ASC, o.submission_id ASC
            ) AS rn
        FROM observations o
        LEFT JOIN checklists c
            ON o.submission_id = c.submission_id
        WHERE o.date_iso IS NOT NULL
    )
    SELECT
        common_name AS "Common Name",
        scientific_name AS "Scientific Name",
        count_raw AS "Count",
        count_numeric AS "Numeric Count",
        date_iso AS "Date",
        year AS "Year",
        decade AS "Decade",
        county AS "County",
        location AS "Location",
        location_precision_flag AS "Location Precision",
        protocol AS "Protocol",
        observation_details AS "Observation Details",
        checklist_comments AS "Checklist Comments",
        submission_id AS "Submission ID",
        ebird_url AS "eBird Checklist"
    FROM ranked
    WHERE rn = 1;

    CREATE VIEW latest_records_by_species AS
    WITH ranked AS (
        SELECT
            o.*,
            c.location_precision_flag,
            c.ebird_url,
            ROW_NUMBER() OVER (
                PARTITION BY o.common_name
                ORDER BY o.date_iso DESC, o.submission_id DESC
            ) AS rn
        FROM observations o
        LEFT JOIN checklists c
            ON o.submission_id = c.submission_id
        WHERE o.date_iso IS NOT NULL
    )
    SELECT
        common_name AS "Common Name",
        scientific_name AS "Scientific Name",
        count_raw AS "Count",
        count_numeric AS "Numeric Count",
        date_iso AS "Date",
        year AS "Year",
        decade AS "Decade",
        county AS "County",
        location AS "Location",
        location_precision_flag AS "Location Precision",
        protocol AS "Protocol",
        observation_details AS "Observation Details",
        checklist_comments AS "Checklist Comments",
        submission_id AS "Submission ID",
        ebird_url AS "eBird Checklist"
    FROM ranked
    WHERE rn = 1;

    CREATE VIEW historical_field_card_checklists AS
    SELECT
        date_iso AS "Date",
        year AS "Year",
        decade AS "Decade",
        month_name AS "Month",
        protocol AS "Protocol",
        county AS "County",
        location AS "Location",
        location_precision_flag AS "Location Precision",
        species_count AS "Species Count",
        observation_row_count AS "Observation Rows",
        checklist_comments AS "Checklist Comments",
        submission_id AS "Submission ID",
        ebird_url AS "eBird Checklist"
    FROM checklists
    WHERE protocol = 'Historical'
       OR checklist_comments LIKE '%field card%'
       OR checklist_comments LIKE '%historic field card%';

    CREATE VIEW comment_search_helper AS
    SELECT
        'Checklist Comment' AS "Source Type",
        submission_id AS "Submission ID",
        date_iso AS "Date",
        year AS "Year",
        decade AS "Decade",
        month_name AS "Month",
        county AS "County",
        location AS "Location",
        location_precision_flag AS "Location Precision",
        checklist_comments AS "Text",
        ebird_url AS "eBird Checklist"
    FROM checklists
    WHERE checklist_comments IS NOT NULL
      AND TRIM(checklist_comments) != ''

    UNION ALL

    SELECT
        'Observation Detail' AS "Source Type",
        o.submission_id AS "Submission ID",
        o.date_iso AS "Date",
        o.year AS "Year",
        o.decade AS "Decade",
        o.month_name AS "Month",
        o.county AS "County",
        o.location AS "Location",
        c.location_precision_flag AS "Location Precision",
        o.observation_details AS "Text",
        c.ebird_url AS "eBird Checklist"
    FROM observations o
    LEFT JOIN checklists c
        ON o.submission_id = c.submission_id
    WHERE o.observation_details IS NOT NULL
      AND TRIM(o.observation_details) != '';
    """)


def drop_legacy_public_views(conn: sqlite3.Connection) -> None:
    """Remove older prototype views that should not appear in the public Datasette interface."""
    conn.executescript("""
    DROP VIEW IF EXISTS observations_public;
    DROP VIEW IF EXISTS checklists_public;
    """)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build BBC eBird archive SQLite database for Datasette.")
    parser.add_argument("input_file", type=Path, help="Full eBird export CSV/TSV file")
    parser.add_argument("output_db", type=Path, help="SQLite database to create")
    parser.add_argument("--replace", action="store_true", help="Overwrite output database if it exists")
    parser.add_argument("--current-year", type=int, default=dt.date.today().year, help="Current year for two-digit year parsing pivot")
    args = parser.parse_args()

    if not args.input_file.exists():
        raise SystemExit(f"Input file not found: {args.input_file}")

    conn = connect(args.output_db, args.replace)
    try:
        create_schema(conn)
        print("Importing observations...")
        n = import_observations(conn, args.input_file, args.current_year)
        print(f"Imported {n:,} observation rows")
        print("Building checklist/species/location summary tables...")
        build_summary_tables(conn)
        create_public_views(conn)
        create_supplemental_public_views(conn)
        drop_legacy_public_views(conn)
        print("Creating indexes and full-text search tables...")
        create_indexes_views_fts(conn)
        add_warnings(conn)
        conn.commit()
        counts = dict(
            observation_rows=conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
            checklists=conn.execute("SELECT COUNT(*) FROM checklists").fetchone()[0],
            species=conn.execute("SELECT COUNT(*) FROM species").fetchone()[0],
            locations=conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0],
        )
        print("Done:", counts)
        print(f"Database written to: {args.output_db}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
