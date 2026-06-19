#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

python3 - <<'PY'
import json
import os
import sqlite3
import sys
from pathlib import Path

config = json.loads(Path("archive_config.json").read_text(encoding="utf-8"))
db_path = Path(config["database"])
minimum_observations = int(os.environ.get("MIN_OBSERVATIONS", config.get("minimum_observations", 1)))

if not db_path.exists():
    raise SystemExit(f"Database not found: {db_path}")

conn = sqlite3.connect(db_path)

required_public_entry_points = [
    "search_species_records",
    "browse_checklists",
    "browse_locations",
    "browse_species_summary",
    "broad_location_checklists",
    "high_counts",
    "earliest_records_by_species",
    "latest_records_by_species",
    "historical_field_card_checklists",
    "comment_search_helper",
]

def get_count(sql, params=None):
    return conn.execute(sql, params or []).fetchone()[0]

observations = get_count("SELECT COUNT(*) FROM observations")
checklists = get_count("SELECT COUNT(*) FROM checklists")
species = get_count("SELECT COUNT(*) FROM species")
locations = get_count("SELECT COUNT(*) FROM locations")
public_entry_count = get_count(
    "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table', 'view') AND name IN ({})".format(
        ",".join("?" for _ in required_public_entry_points)
    ),
    required_public_entry_points,
)
old_views_count = get_count(
    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'view' AND name IN ('observations_public', 'checklists_public')"
)
unparsed_dates = get_count(
    "SELECT row_count FROM import_warnings WHERE detail = 'blank_or_unparsed_date'"
)

print("Smoke checks:")
print(f"  observations: {observations}")
print(f"  checklists: {checklists}")
print(f"  species: {species}")
print(f"  locations: {locations}")
print(f"  public_entry_points: {public_entry_count}")
print(f"  old_public_views_should_be_zero: {old_views_count}")
print(f"  blank_or_unparsed_date: {unparsed_dates}")

errors = []

if observations < minimum_observations:
    errors.append(f"observations count is below expected minimum ({minimum_observations})")
if checklists <= 0:
    errors.append("checklists count is zero")
if species <= 0:
    errors.append("species count is zero")
if locations <= 0:
    errors.append("locations count is zero")
if public_entry_count != len(required_public_entry_points):
    errors.append(f"expected {len(required_public_entry_points)} public entry points, found {public_entry_count}")
if old_views_count != 0:
    errors.append("old prototype views still exist")
if unparsed_dates != 0:
    errors.append("unparsed dates found")

conn.close()

if errors:
    print()
    print("Smoke test failed:")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)

print()
print("Smoke test passed.")
PY
