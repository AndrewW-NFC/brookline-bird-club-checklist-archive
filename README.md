# Brookline Bird Club Checklist Archive

This repository builds a searchable Datasette archive from periodic Brookline Bird Club eBird account exports. It does not use the eBird API; the source of truth is the full export file downloaded from the club account.

The archive is intended to make BBC checklist and observation history easier to browse by species, checklist, location, date, count, protocol, breeding code, observation details, and checklist comments.

## What is tracked here

- Importer and maintenance scripts in `scripts/`
- Datasette metadata in `datasette.yaml`
- Shared build settings in `archive_config.json`
- Maintainer notes in `docs/`
- Provisional attribution and caveat language in `ATTRIBUTION.md`

Large generated files are intentionally not tracked by Git:

- Raw eBird exports in `data/source/`
- Built SQLite databases and metadata in `data/build/`
- Public-download staging files in `public_downloads/`

The current full export and SQLite database are each larger than GitHub's normal per-file limit, so they should be regenerated locally, uploaded as release assets, or handled through a large-file strategy rather than committed directly.

## Quick Start

1. Create the local environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Put the latest eBird export at the path configured in `archive_config.json`:

   ```text
   data/source/BBC data download 2026-06-18.csv
   ```

   You can use a different filename if you update `source_csv` in `archive_config.json`.

3. Rebuild the archive:

   ```bash
   scripts/rebuild.sh
   ```

4. Run Datasette locally:

   ```bash
   source .venv/bin/activate
   datasette data/build/bbc-ebird-archive.sqlite --metadata datasette.yaml
   ```

5. Open the local URL printed by Datasette, usually:

   ```text
   http://127.0.0.1:8001/
   ```

## Sample Data

The repository includes a tracked representative sample export:

```text
data/sample/bbc-ebird-sample-1000.csv
```

This file contains 1,000 rows from the full Brookline Bird Club eBird export, selected to cover all species in the current archive plus a mix of historical records, recent records, broad locations, presence-only counts, checklist comments, observation details, protocols, counties, and high counts. It is intended for quick testing, GitHub-based development, and vendor review without requiring the full local export.

Build a sample SQLite database with:

```bash
python scripts/build_bbc_ebird_db.py \
  data/sample/bbc-ebird-sample-1000.csv \
  data/build/bbc-ebird-sample.sqlite \
  --replace \
  --current-year 2026
```

Then launch it with:

```bash
datasette data/build/bbc-ebird-sample.sqlite --metadata datasette.yaml
```

## Public Entry Points

The importer creates these public-facing Datasette entry points:

- `search_species_records`
- `browse_checklists`
- `browse_locations`
- `browse_species_summary`
- `broad_location_checklists`
- `high_counts`
- `earliest_records_by_species`
- `latest_records_by_species`
- `historical_field_card_checklists`
- `comment_search_helper`

The raw source tables are still present for diagnostics and deeper archive work:

- `observations`
- `checklists`
- `locations`
- `species`
- `import_warnings`

## Monthly Refresh

For routine updates, download the latest same-structure export, update `source_csv` in `archive_config.json` if needed, then run:

```bash
scripts/rebuild.sh
scripts/prepare_public_downloads.sh
```

See [docs/monthly-update.md](docs/monthly-update.md) for the full checklist.

## Temporary Hosting

The repository includes a Dockerfile for deploying a sample-data Datasette prototype to Northflank or another container host. See [docs/northflank-deployment.md](docs/northflank-deployment.md).

For local testing with the full generated SQLite database, use `Dockerfile.full`. This packages `data/build/bbc-ebird-archive.sqlite` into a local Docker image without committing the large database to GitHub.

The current full archive image is also available in GitHub Container Registry as `ghcr.io/andreww-nfc/bbc-ebird-archive-full:2026-06-18-guided`.

## Caveats

Some historical checklists use broad eBird locations, such as county-level or route-style locations. The importer preserves the original eBird location and adds a derived `Location Precision` helper field. In many cases, checklist comments give better detail about actual places visited.

Attribution and public-use language in [ATTRIBUTION.md](ATTRIBUTION.md) is provisional and should be reviewed before public launch.
