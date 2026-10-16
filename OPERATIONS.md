# Implemented baseline

`python -m unittest discover -s tests -v` runs offline regression checks.

`python pipeline.py --sale-date 2026-11-03 --state-dir state` fetches the official listing, validates the source sale date and auction identifiers, and saves raw snapshots, audit records, account records and changes.

For a previously downloaded HTML document, add `--html /path/to/listing.html`. This input is an operational fallback, not an automatic workaround for source access restrictions.

Snapshots are content addressed. Each attempted parse has a separate audit file. The last accepted inventory is scoped by sale date and replaced atomically only after quality validation. Missing accounts are review items, never inferred cancellations. A local file lock serializes writers sharing the same state volume. Do not use this local state implementation with multiple Cloud Run instances or ephemeral-only storage.

The source integration workflow runs independently in GitHub Actions when the pipeline changes. It retains evidence as a short-lived Actions artifact; this is an integration check, not a persistent production scheduler. It currently targets November 3, 2026 and must be updated for another sale date.

## Outstanding production work

- Validate the parser against the complete live HTML and retain sanitized structural fixtures. Current offline fixtures are small synthetic HTML examples based on visible source fields; they do not certify extraction of all 182 accounts.
- Source access: a direct request from the development environment returned HTTP 403. The integration workflow tests GitHub's environment separately; no successful live download is claimed before its logs confirm it.
- Add explicit failed-fetch audit records (currently a fetch exception exits nonzero before parse state is written).
- Add verified HCAD bulk schema ingestion, parcel enrichment, flood evidence, Sheets staging publication and source-specific freshness rules.
- Add durable Cloud Storage storage with conditional generation writes and a distributed lease before using Cloud Run. The Dockerfile packages the local implementation only; it is not a production deployment.
- Configure cloud identity, permissions, billing, monitoring and scheduler, then execute and inspect a real job. No GCP credentials or cloud tooling have been configured in this environment.
- Add a controlled reporting layer that never overwrites manual title warnings or historical research.

There are no bid recommendations, title clearances, market valuations or duplex feasibility conclusions in this baseline.
