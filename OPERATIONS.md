# Implemented baseline

`python -m unittest discover -s tests -v` runs 11 offline regression checks.

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
- Add durable Cloud Storage storage with conditional generation writes and a distributed lease before using Cloud Run. The Dockerfile packages the local implementation only; it is not a production deployment.
- Configure cloud identity, permissions, billing, monitoring and scheduler, then execute and inspect a real job. No GCP credentials or cloud tooling have been configured in this environment.
- Add a controlled reporting layer that never overwrites manual title warnings or historical research.

There are no bid recommendations, title clearances, market valuations or duplex feasibility conclusions in this baseline.
