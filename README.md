# Harris Tax Deed V2

Independent implementation of Harris County auction ingestion and official parcel GIS enrichment, built from scratch.

## Working and verified

- Official listing download succeeds from GitHub Actions.
- Parser preserves accounts, causes, precincts, sale numbers, types, bids, addresses and legal descriptions.
- Grouped sales, special proceedings, fractional interests and missing details remain explicit review items. No automatic bid recommendations.
- Immutable local source snapshots, audit logs, atomic last-accepted state and sale-specific change history.
- Batch HCAD parcel GIS enrichment retains official responses, geometries, tax year, area, values, situs address and legal text.
- CI tests and a separate live-source integration workflow execute outside the chat.
- Cloud Run entrypoint and image definition use Cloud Storage for durable evidence and conditional state publication. Cloud storage behavior is tested with fake storage objects; real deployment is pending.

## Latest verified source run

For November 3, 2026: 182 listing accounts; 164 complete listing addresses and 159 listing legal descriptions. Missing fields stay unknown. Official parcel GIS matched 181 accounts for tax year 2026, with land area for 181 and market value for 178. Account 1163550010076 needs an alternate official lookup.

## Run

```bash
python -m unittest discover -s tests -v
python pipeline.py --sale-date 2026-11-03 --state-dir state
python enrich.py --inventory state/2026-11-03/latest.json --out state/enrichment
```

The local pipeline uses Python 3.12 standard library. Cloud execution additionally requires `requirements.txt`, application-default credentials, `STATE_BUCKET` and `SALE_DATE`. Build the cloud image with `Dockerfile.cloud`. Do not store production state solely on the Cloud Run temporary filesystem.

## Remaining work

Real GCP deployment, scheduled execution, Google Sheets staging publication, exemption evidence, flood analysis, comparables, title research and duplex underwriting are not complete. Homestead and flood remain unknown. HCAD appraised or market values are not verified resale comparables. Grouped account membership is not a verified auction-lot identity.

Target infrastructure: GitHub → Cloud Run Jobs → Cloud Scheduler (America/Chicago) → Cloud Storage → reporting to Google Sheets. Source data and code are separate. No credentials or private exports belong in this public repository.

Investment scope favors vacant land in northern Houston toward The Woodlands; excludes Baytown and confirmed homestead; has no fixed acquisition price cap. Incomplete legal or physical evidence blocks bid recommendations.

See OPERATIONS.md for verification evidence and deployment limitations.
