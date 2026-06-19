#!/usr/bin/env python3

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

CONFIG_PATH = Path("archive_config.json")

def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

def scalar(conn, sql):
    return conn.execute(sql).fetchone()[0]

def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    db_path = Path(config["database"])
    source_csv = Path(config["source_csv"])
    output_path = Path(config.get("metadata_file", "data/build/archive_metadata.json"))

    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)

    metadata = {
        "archive_name": config.get("archive_name", "Brookline Bird Club eBird Archive"),
        "data_source": "Brookline Bird Club eBird account export",
        "uses_ebird_api": False,
        "refresh_cadence": config.get("refresh_cadence", "monthly"),
        "source_csv": str(source_csv),
        "source_csv_exists": source_csv.exists(),
        "database": str(db_path),
        "last_rebuilt_utc": datetime.now(timezone.utc).isoformat(),
        "row_counts": {
            "observations": count(conn, "observations"),
            "checklists": count(conn, "checklists"),
            "species": count(conn, "species"),
            "locations": count(conn, "locations"),
        },
        "date_range": {
            "first_date": scalar(conn, "SELECT MIN(date_iso) FROM observations WHERE date_iso IS NOT NULL"),
            "last_date": scalar(conn, "SELECT MAX(date_iso) FROM observations WHERE date_iso IS NOT NULL"),
        },
        "public_entry_points": [
            "search_species_records",
            "browse_checklists",
            "browse_locations",
            "browse_species_summary",
            "broad_location_checklists",
            "high_counts",
            "earliest_records_by_species",
            "latest_records_by_species",
            "historical_field_card_checklists",
            "comment_search_helper"
        ],
        "public_downloads_planned": True,
        "notes": [
            "This archive is built from periodic exported data, not the live eBird API.",
            "Public data may lag behind current eBird records.",
            "Location Precision is a derived helper field, not an original eBird field."
        ]
    }

    conn.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")

if __name__ == "__main__":
    main()
