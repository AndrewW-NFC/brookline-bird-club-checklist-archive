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
CURRENT_YEAR="$(read_config current_year)"

if [ ! -f "$SOURCE_CSV" ]; then
  echo "Source CSV not found: $SOURCE_CSV"
  echo "Place the latest eBird export there, or update archive_config.json."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Virtual environment not found. Creating .venv..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt

mkdir -p "$(dirname "$DATABASE")"

echo "Rebuilding $DATABASE from:"
echo "$SOURCE_CSV"

python scripts/build_bbc_ebird_db.py "$SOURCE_CSV" "$DATABASE" --replace --current-year "$CURRENT_YEAR"

echo
echo "Writing archive metadata..."
python scripts/write_archive_metadata.py

echo
echo "Running smoke test..."
scripts/smoke_test.sh

echo
echo "Rebuild complete."
echo "Launch Datasette with:"
echo "source .venv/bin/activate && datasette $DATABASE --metadata datasette.yaml"
