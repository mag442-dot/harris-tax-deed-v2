# Harris Tax Deed V2

Independent implementation of Harris County auction ingestion and official parcel GIS enrichment, built from scratch.

## Working and verified

- Official listing download succeeds from GitHub Actions.
- Parser preserves accounts, causes, precincts, sale numbers, types, bids, addresses and legal descriptions.
- Grouped sales, special proceedings, fractional interests and missing details remain explicit review items. No automatic bid recommendations.
- Immutable local source snapshots, audit logs, atomic last-accepted state and sale-specific change history.
- Batch HCAD parcel GIS enrichment retains official responses, geometries, tax year, area, values, situs address and legal text.
- CI tests and a separate live-source integration workflow execute outside the chat.
- Daily acquisition workflow is configured for 8:47 AM America/Chicago through the November 3 sale, with a best-effort cache baseline and 90-day evidence artifacts. It refreshes listing, HCAD and FEMA observations or explicit source errors. This provisional GitHub workflow does not publish daily updates to Google Sheets and is not permanent cloud storage.
- A verified 182-account report was published through the connected Google Sheets account into the existing workbook's dedicated `V2 Inventory` tab. Existing research tabs were preserved, including historical warnings. The report distinguishes 179 for-sale rows and 3 cancelled rows.
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

Real GCP deployment, continuous Sheets synchronization, exemption evidence, complete flood analysis, comparables, title research and duplex underwriting are not complete. FEMA intersections work from GitHub but can have partial source coverage or connection failures; results distinguish observed zones from unknown coverage and do not provide flood clearance. Homestead remains unknown. HCAD appraised or market values are not verified resale comparables. Grouped account membership is not a verified auction-lot identity.

`sheets_sync.py` implements authenticated staging publication with a schema gate, historical-warning retrieval and account readback. The optional Cloud Run `SPREADSHEET_ID` setting enables it only after the runtime identity has editor access to the target file. This credentialed runtime path has not been executed; the initial Sheet publication used the connected account.

Target infrastructure: GitHub → Cloud Run Jobs → Cloud Scheduler (America/Chicago) → Cloud Storage → reporting to Google Sheets. Source data and code are separate. No credentials or private exports belong in this public repository.

Investment scope favors vacant land in northern Houston toward The Woodlands; excludes Baytown and confirmed homestead; has no fixed acquisition price cap. Incomplete legal or physical evidence blocks bid recommendations.

See OPERATIONS.md for verification evidence and deployment limitations.
