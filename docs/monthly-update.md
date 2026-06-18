# Monthly Update Notes

This project is designed for monthly refreshes from a same-structure Brookline Bird Club eBird account export.

## Checklist

1. Download the latest eBird/Cornell export for the Brookline Bird Club account.
2. Save the CSV in `data/source/`, or another stable local path.
3. Open `archive_config.json`.
4. Update `source_csv` if the filename changed.
5. Update `current_year` if the two-digit-year pivot year has changed.
6. Run the rebuild workflow:

   ```bash
   scripts/rebuild.sh
   ```

7. Confirm the rebuild ends with:

   ```text
   Smoke test passed.
   ```

8. Prepare public-download files if needed:

   ```bash
   scripts/prepare_public_downloads.sh
   ```

9. Launch Datasette locally:

   ```bash
   source .venv/bin/activate
   datasette data/build/bbc-ebird-archive.sqlite --metadata datasette.yaml
   ```

10. Review these areas in Datasette:

- `import_warnings`
- `browse_species_summary`
- `search_species_records`
- `browse_checklists`
- `browse_locations`
- `broad_location_checklists`
- `comment_search_helper`

11. Spot-check the public-download folder:

   ```bash
   ls -lh public_downloads
   ```

## Expected Smoke-Test Conditions

These values may change as the dataset grows, but these conditions should remain true for the current full archive:

- Observations should be above 600,000.
- Checklists should be nonzero.
- Species should be nonzero.
- Locations should be nonzero.
- Public views should equal 10.
- Old prototype views should equal 0.
- Blank or unparsed dates should equal 0, unless the export format changes.

The expected observation minimum is configured in `archive_config.json` as `minimum_observations`.

## Files Usually Changed Monthly

Usually only `archive_config.json` needs manual editing:

```json
"source_csv": "data/source/new-export-file.csv"
```

## Generated Or Refreshed

Running `scripts/rebuild.sh` updates:

- `data/build/bbc-ebird-archive.sqlite`
- `data/build/archive_metadata.json`

Running `scripts/prepare_public_downloads.sh` updates:

- `public_downloads/bbc-ebird-archive-current.sqlite`
- `public_downloads/bbc-ebird-raw-export-current.csv`
- `public_downloads/archive_metadata.json`
- `public_downloads/README.txt`

## Before Public Release

Before anything goes online, review:

- `ATTRIBUTION.md`
- `public_downloads/README.txt`
- Raw CSV fields
- eBird checklist links
- Broad-location caveats
- Whether raw/source tables should be visible in Datasette

The current attribution and caveat language is provisional.
