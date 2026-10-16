# Implemented baseline

`python -m unittest discover -s tests -v` runs 26 offline regression checks.

`python pipeline.py --sale-date 2026-11-03 --state-dir state` fetches the official listing, validates the source sale date and auction identifiers, and saves raw snapshots, audit records, account records and changes.

For a previously downloaded HTML document, add `--html /path/to/listing.html`. This input is an operational fallback, not an automatic workaround for source access restrictions.

`python enrich.py --inventory state/2026-11-03/latest.json --out state/enrichment` queries the official HCAD parcel GIS in batches of 25, retaining raw responses, provenance and geometries. Multiple matches are flagged and never arbitrarily collapsed. Homestead remains unknown because this GIS schema does not supply exemption evidence.

## Verified October 15 Houston results

GitHub Actions successfully fetched the November 3 official HTML. Development access returned 403, so the source was downloaded through the Actions artifact connector and tested locally. The corrected parser found 182 accounts, 164 complete source addresses and 159 nonempty source legal descriptions. Missing details are retained as explicit exceptions; it never borrows a subsequent card's address or legal text. The live GIS enrichment returned 181 unique matches and one account not found (1163550010076). All 181 matches report tax year 2026; 181 have land square footage and 178 have market value. These are source observations, not title or investment approvals.

Snapshots are content addressed. Each attempted parse has a separate audit file. The last accepted inventory is scoped by sale date and replaced atomically only after quality validation. Missing accounts are review items, never inferred cancellations. A local file lock serializes writers sharing the same state volume. Do not use this local state implementation with multiple Cloud Run instances or ephemeral-only storage.

The source integration workflow runs independently in GitHub Actions when the pipeline changes. It retains evidence as a short-lived Actions artifact; this is an integration check, not a persistent production scheduler. It currently targets November 3, 2026 and must be updated for another sale date.

## Outstanding production work

- Retain more sanitized live structural fixtures and expand source-change regression coverage. The current offline fixtures are small synthetic examples; the full live snapshot was tested separately.
- Monitor source access separately in deployment environments; success in GitHub does not prove access from GCP.
- Add explicit failed-fetch audit records (currently a fetch exception exits nonzero before parse state is written).
- Add verified HCAD bulk schema ingestion for exemptions, flood evidence, Sheets staging publication and source-specific freshness rules. Parcel GIS enrichment is implemented and tested live.
- Verify `cloud_job.py` against a real private versioned Cloud Storage bucket. It persists immutable run evidence before conditional latest-state publication, refusing conflicting generations. Unit tests cover absent-pointer creation and conflict handling. `Dockerfile.cloud` packages this entrypoint; it is not a deployment.
- Configure cloud identity, permissions, billing, monitoring and scheduler, then execute and inspect a real job. No GCP credentials or cloud tooling have been configured in this environment.
- Add a controlled reporting layer that never overwrites manual title warnings or historical research.

There are no bid recommendations, title clearances, market valuations or duplex feasibility conclusions in this baseline. Reporting labels Baytown and fractional interests NO_BID, preserves historical warnings, and keeps cancelled records visible as unavailable.

## Provisional unattended execution

`.github/workflows/refresh.yml` runs the listing, HCAD and FEMA pipeline daily at 8:47 AM Houston. Two UTC cron triggers plus a daylight-saving selector choose one daily run; GitHub schedules can be delayed. The sale date is explicitly November 3, 2026 and execution stops after that local date. Update configuration and validate the next source before using it for another sale.

The prior accepted listing is restored from GitHub Actions cache when available. Cache can be evicted; a missing baseline produces NEW records rather than inferred cancellations. Each run uploads source and enrichment evidence for 90 days. This is provisional retention, not the permanent GCS data store. Workflow artifacts do not include private manual historical notes, and the daily workflow does not refresh Sheets.

The existing Google workbook now contains a separate V2 Inventory report with 182 unique accounts, 179 for-sale records and three cancellations. This initial publication used the connected account and retained 44 account-specific historical warnings. It did not change Master formulas or historical tabs. Native value and formatting readback succeeded; browser rendering was unavailable.

`flood.py` queries FEMA using full parcel rings in EPSG:4326, records the intersecting hazard zones, and never interprets a missing response as safe. It does not calculate coverage percentages or prove that the whole parcel is mapped. Three consecutive source failures open a circuit rather than sending requests for the remaining accounts. Each request has at most one retry for transient errors, with spacing between requests. Successful observations younger than seven days are reused only for an identical parcel geometry, retaining the original timestamp; the next run can work on unresolved accounts. The workflow cache now includes flood observations as well as the listing baseline.

Verified FEMA result: the second full attempt returned 72 parcel observations (57 X, 13 AE, one AO and one mixed AE/X), with 15 SFHA intersections and four floodway intersections. Three requests failed and 106 were skipped after the failure circuit opened; one account had no parcel geometry. These observations were published in V2 Inventory with source links and observation dates. This is partial coverage, not a flood clearance. MAAPnext remains unimplemented.

`sheets_sync.py` reads the live report header before updating its machine-owned tab, retrieves historical warnings, preserves account strings, and verifies the account column after publication. It refuses unfamiliar staging content and never modifies sharing or historical tabs. Cloud Run can enable it with SPREADSHEET_ID after the runtime identity receives editor access. This authenticated runtime path remains unverified; connector-based initial publication and readback succeeded.

## Deployment access blocker

The browser extension was unavailable from this session, and the available cloud browser showed `Site Unavailable` at Google Cloud Console. There is no authenticated gcloud CLI in the development environment. GitHub access does not grant GCP access. Do not call Cloud Run, Scheduler, bucket IAM or Google Sheets integration deployed until verified through those services.

Cloud provisioning must provide a private versioned bucket, a Cloud Run runtime identity with object access scoped to that bucket, an image built from Dockerfile.cloud, a job with STATE_BUCKET and SALE_DATE, and a scheduler identity permitted to execute only that job. Configure one task, parallelism one, bounded retries and America/Chicago scheduling. Run and inspect the job before enabling recurring execution. The selected sale date must be updated for the next auction; mismatches fail closed.
