# Project Manifest

This repository is a Datasette build pipeline for the Brookline Bird Club eBird archive.

## Core Files

| Path | Purpose |
|---|---|
| `README.md` | Main project overview and quick start. |
| `archive_config.json` | Central build configuration: source CSV, output database, current-year date pivot, and public-download filenames. |
| `datasette.yaml` | Datasette title, descriptions, table/view labels, and facets. |
| `requirements.txt` | Python package requirements for building and running the archive. |
| `ATTRIBUTION.md` | Provisional attribution and caveat language for public launch. |

## Scripts

| Path | Purpose |
|---|---|
| `scripts/build_bbc_ebird_db.py` | Main importer. Converts an eBird export CSV/TSV into a normalized SQLite database with summary tables, public views, indexes, and full-text search tables. |
| `scripts/rebuild.sh` | Monthly rebuild wrapper. Creates `.venv` if needed, installs requirements, rebuilds the database, writes metadata, and runs smoke tests. |
| `scripts/smoke_test.sh` | Standalone database verification script. Checks row counts, public views, old-view cleanup, and date parsing. |
| `scripts/write_archive_metadata.py` | Writes machine-readable metadata for the current local build. |
| `scripts/prepare_public_downloads.sh` | Copies the current SQLite database, raw CSV, metadata, and README into `public_downloads/`. |

## Local Data Folders

| Path | Purpose |
|---|---|
| `data/source/` | Local-only source eBird exports. Ignored by Git. |
| `data/build/` | Local-only generated SQLite databases and build metadata. Ignored by Git. |
| `public_downloads/` | Local-only staging folder for public download artifacts. Ignored by Git except for README/placeholders. |

## Generated Files

These are created by the scripts and intentionally ignored by Git:

- `data/source/*.csv`
- `data/build/*.sqlite`
- `data/build/archive_metadata.json`
- `public_downloads/bbc-ebird-archive-current.sqlite`
- `public_downloads/bbc-ebird-raw-export-current.csv`
- `public_downloads/archive_metadata.json`

## Removed From the ChatGPT Bundle

The original bundle included several files that are not appropriate for the repository:

- A complete Python virtual environment
- macOS `._*` sidecar files
- Duplicate nested starter-project files
- Patch backups such as `*.backup*` and `*.old`
- Zero-byte placeholder files named `source`, `datasette`, and `sample-check.txt`
- Large generated SQLite and CSV artifacts
