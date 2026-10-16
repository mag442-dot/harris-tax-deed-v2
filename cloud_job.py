"""Cloud Run entrypoint with immutable evidence and optimistic GCS state writes.

Requires application-default credentials, STATE_BUCKET and SALE_DATE.
No service account keys are accepted as command-line arguments.
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from enrich import enrich
from flood import enrich_flood
from pipeline import SOURCE, fetch, run


def execute(bucket, sale_date, not_found, precondition_failed):
    prefix = 'sales/' + sale_date + '/'
    latest = bucket.blob(prefix + 'latest.json')
    try:
        latest.reload()
        generation = latest.generation
        previous = latest.download_as_text(if_generation_match=generation)
    except not_found:
        generation = 0
        previous = None
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run_prefix = prefix + 'runs/' + run_id + '/'
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        if previous:
            path = root / sale_date / 'latest.json'
            path.parent.mkdir(parents=True)
            path.write_text(previous)
        try:
            html = fetch(SOURCE)
            inventory = run(html, root, sale_date)
            summary = enrich(inventory, root / 'enrichment')
            if summary.get('BLOCKED'):
                raise RuntimeError('GIS batches blocked; refusing latest-state publication')
            enriched = json.loads((root / 'enrichment/enriched.json').read_text())
            if os.environ.get('ENABLE_FEMA', 'true').lower() == 'true':
                enrich_flood(enriched, root / 'flood', previous=json.loads(previous) if previous else None)
                enriched = json.loads((root / 'flood/enriched.json').read_text())
            for path in root.rglob('*'):
                if path.is_file() and path.name != 'run.lock' and path.name != 'latest.json':
                    bucket.blob(run_prefix + str(path.relative_to(root))).upload_from_string(
                        path.read_bytes(), if_generation_match=0)
            # Snapshot and full run are durable before the accepted pointer changes.
            # Concurrent runs cannot overwrite one another's accepted state.
            latest.upload_from_string(json.dumps(enriched), content_type='application/json',
                                      if_generation_match=generation)
            if os.environ.get('SPREADSHEET_ID'):
                import google.auth
                from google.auth.transport.requests import AuthorizedSession
                from sheets_sync import publish
                credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/spreadsheets'])
                receipt = publish(enriched, os.environ['SPREADSHEET_ID'], AuthorizedSession(credentials))
                bucket.blob(run_prefix + 'sheets_receipt.json').upload_from_string(
                    json.dumps(receipt), content_type='application/json', if_generation_match=0)
            print(json.dumps(dict(status='PUBLISHED', run=run_id, records=len(inventory['records']),
                                  hcad=summary)))
        except Exception as exc:
            # Preserve diagnostic parse artifacts even when validation failed.
            for path in root.rglob('*'):
                if not path.is_file() or path.name in ('run.lock', 'latest.json'):
                    continue
                try:
                    bucket.blob(run_prefix + 'failed-evidence/' + str(path.relative_to(root))).upload_from_string(
                        path.read_bytes(), if_generation_match=0)
                except precondition_failed:
                    pass
            bucket.blob(run_prefix + 'failure.json').upload_from_string(
                json.dumps(dict(status='FAILED', error=str(exc), run=run_id, source=SOURCE)),
                content_type='application/json', if_generation_match=0)
            raise


def main():
    from google.cloud import storage
    from google.api_core.exceptions import NotFound, PreconditionFailed
    from datetime import date
    sale_date = date.fromisoformat(os.environ['SALE_DATE']).isoformat()
    execute(storage.Client().bucket(os.environ['STATE_BUCKET']), sale_date, NotFound, PreconditionFailed)


if __name__ == '__main__':
    main()
