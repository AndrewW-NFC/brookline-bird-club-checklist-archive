# Deployment Notes

This project builds a searchable Datasette archive from the Brookline Bird Club eBird account export.

## Local Build

From the repository root:

```bash
scripts/rebuild.sh
```

This reads `archive_config.json` and creates:

```text
data/build/bbc-ebird-archive.sqlite
data/build/archive_metadata.json
```

## Local Datasette

```bash
source .venv/bin/activate
datasette data/build/bbc-ebird-archive.sqlite --metadata datasette.yaml
```

Then open the local URL printed by Datasette, usually:

```text
http://127.0.0.1:8001/
```

## Public Entry Points

The main public-facing Datasette entry points are:

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

The raw source tables are:

- `observations`
- `checklists`
- `locations`
- `species`
- `import_warnings`

## Public Download Staging

Prepare public-download files with:

```bash
scripts/prepare_public_downloads.sh
```

This creates:

- `public_downloads/bbc-ebird-archive-current.sqlite`
- `public_downloads/bbc-ebird-raw-export-current.csv`
- `public_downloads/archive_metadata.json`
- `public_downloads/README.txt`

These outputs are ignored by Git because the database and raw export are large. For public hosting, use release assets, object storage, GitHub Pages with an external large-file strategy, or another deployment channel suited to large files.

## Hosting Considerations

A hosting-ready deployment should include:

- The generated SQLite database
- `datasette.yaml`
- Python requirements
- Attribution and caveat text
- A clear monthly refresh procedure
- A decision about whether raw source-table access and raw CSV downloads are appropriate for public users

Do not rely on the eBird API for this archive. The public archive is built from periodic full account exports.
