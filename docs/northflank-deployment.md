# Northflank Deployment

This project can be deployed to Northflank as a Docker-based Datasette web service.

The first deployment path uses the tracked 1,000-row sample export so the service can be built entirely from GitHub without uploading the full local eBird export or generated SQLite database.

## What This Deploys

The Docker image:

1. Installs the Python dependencies in `requirements.txt`.
2. Builds `data/build/bbc-ebird-sample.sqlite` from `data/sample/bbc-ebird-sample-1000.csv`.
3. Starts Datasette using `datasette.yaml`.

This is intended for testing the hosting path and sharing an early demo. The full archive deployment can use the same pattern later, with a decision about how to provide the large SQLite database.

## Northflank Setup

In the `bbc-ebird-archive-demo` Northflank project:

1. Create a new service.
2. Choose a combined service.
3. Select GitHub as the source.
4. Select the repository:

   ```text
   AndrewW-NFC/brookline-bird-club-checklist-archive
   ```

5. Select the `main` branch.
6. Use Dockerfile-based build.
7. Set the Dockerfile path to:

   ```text
   Dockerfile
   ```

8. Expose HTTP traffic to the service port. The container defaults to port `8001`, and the start command also honors Northflank's `PORT` environment variable if one is provided.
9. Deploy the service.

After deployment, Northflank should provide a public service URL for the sample Datasette archive.

## Local Docker Test

From the repository root:

```bash
docker build -t bbc-ebird-archive-demo .
docker run --rm -p 8001:8001 bbc-ebird-archive-demo
```

Then open:

```text
http://127.0.0.1:8001/
```

## Full Archive Deployment Later

The current full generated database is too large to commit to GitHub. For a full-data deployment, choose one of these approaches:

- Build a Docker image locally that includes `data/build/bbc-ebird-archive.sqlite`, then push that image to a registry.
- Store the SQLite database as a release asset or object-storage file and download it during deployment.
- Use a Northflank persistent volume only if a server-side writable database is needed.

For this archive, the preferred long-term shape is still a read-only Datasette service with a regenerated SQLite database.
