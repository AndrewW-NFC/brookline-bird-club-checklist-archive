FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8001
ENV DATASETTE_DB=data/build/bbc-ebird-sample.sqlite

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts ./scripts
COPY data/sample ./data/sample
COPY archive_config.json datasette.yaml README.md ATTRIBUTION.md ./

RUN mkdir -p data/build \
    && python scripts/build_bbc_ebird_db.py \
      data/sample/bbc-ebird-sample-1000.csv \
      "$DATASETTE_DB" \
      --replace \
      --current-year 2026

EXPOSE 8001

CMD ["sh", "-c", "datasette serve \"$DATASETTE_DB\" --metadata datasette.yaml --host 0.0.0.0 --port \"${PORT:-8001}\""]
