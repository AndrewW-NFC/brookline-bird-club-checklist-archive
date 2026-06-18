#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

read_config() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path("archive_config.json").read_text(encoding="utf-8"))
print(config[sys.argv[1]])
PY
}

SOURCE_CSV="$(read_config source_csv)"
DATABASE="$(read_config database)"
METADATA_FILE="$(read_config metadata_file)"
DOWNLOAD_DIR="$(read_config public_download_dir)"
PUBLIC_SQLITE="$(read_config public_sqlite_filename)"
PUBLIC_CSV="$(read_config public_raw_csv_filename)"

mkdir -p "$DOWNLOAD_DIR"

if [ ! -f "$DATABASE" ]; then
  echo "Database not found: $DATABASE"
  echo "Run scripts/rebuild.sh first."
  exit 1
fi

if [ ! -f "$SOURCE_CSV" ]; then
  echo "Source CSV not found: $SOURCE_CSV"
  exit 1
fi

if [ ! -f "$METADATA_FILE" ]; then
  echo "Metadata not found: $METADATA_FILE"
  echo "Run scripts/rebuild.sh first."
  exit 1
fi

cp "$DATABASE" "$DOWNLOAD_DIR/$PUBLIC_SQLITE"
cp "$SOURCE_CSV" "$DOWNLOAD_DIR/$PUBLIC_CSV"
cp "$METADATA_FILE" "$DOWNLOAD_DIR/archive_metadata.json"

cat > "$DOWNLOAD_DIR/README.txt" <<'TXT'
Brookline Bird Club eBird Archive - Public Downloads

This folder contains files prepared for eventual public download.

Files may include:

- bbc-ebird-archive-current.sqlite
  SQLite database used by the Datasette archive.

- bbc-ebird-raw-export-current.csv
  Raw exported Brookline Bird Club eBird account data used to build the archive.

- archive_metadata.json
  Machine-readable metadata about the current archive build.

About and attribution:

The Brookline Bird Club eBird Archive is a searchable copy of checklist and observation data exported from the Brookline Bird Club eBird account. It is intended to make the club's historical bird records easier to browse by species, checklist, location, date, and comments.

This archive is built from periodic eBird account exports, not from the live eBird API. It may lag behind current eBird records. Original checklist records remain on eBird, and checklist links in this archive point back to eBird where available.

Some historical checklists use broad eBird locations, such as county-level locations or route-style locations. In those cases, checklist comments may provide better detail about the actual places visited. The "Location Precision" field is a derived helper field added for this archive; it is not an original eBird field.

Raw data and SQLite database downloads are planned for users who want to inspect or reuse the archive data. Public use should preserve attribution to the Brookline Bird Club and eBird as appropriate.

This attribution and caveat language is provisional and should be reviewed before public launch.
TXT

echo "Prepared public download files:"
ls -lh "$DOWNLOAD_DIR"
