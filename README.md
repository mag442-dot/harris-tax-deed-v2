# Harris Tax Deed V2

Independent implementation of a persistent Harris County auction research pipeline. Built from scratch; the separate Claude project is not a code dependency.

## Current status

Repository initialized. No pipeline, cloud deployment, scheduler, source validation, or Google Sheets synchronization has been verified in this repository yet. Earlier ZIP prototypes are not production deployments.

## Target architecture

GitHub source and CI → Google Cloud Run Job → Cloud Scheduler (America/Chicago). Cloud Storage holds immutable source snapshots and HCAD bulk files; a persistent state store holds versioned property records. Google Sheets is a reporting destination, not the primary database. Secret Manager holds credentials.

## Delivery gates

1. Implement and test the official listing parser against retained source fixtures. Verify the auction date from source evidence, preserve 13-character account identifiers, model grouped accounts separately from auction lots, and retain special proceedings for review.
2. Add an idempotent orchestrator with bounded retries, resumable stages, source provenance, immutable snapshots, and change detection. A missing account means missing pending review, not confirmed cancellation.
3. Enrich from official HCAD data and parcel GIS. Preserve unknown exemption status; do not treat missing data as absence of homestead. Track source dates and stale observations.
4. Add parcel-based flood checks with coverage and intersection evidence. Missing flood coverage is unknown, not low risk.
5. Publish into a dedicated staging Sheet tab only after quality gates pass, preserving historical research and manual warnings. Group bids must never be summed as separate purchases.
6. Deploy and execute in Google Cloud, then verify scheduler configuration, job completion, persisted outputs, reporting and failure handling before calling the system automated.
7. Add documented underwriting assumptions, supported comparable evidence, duplex feasibility checks and title research queues. Incomplete evidence must block bid recommendations.

## Investment scope

Favor vacant land in northern Houston toward The Woodlands; exclude Baytown and confirmed homestead under the current strategy. No fixed acquisition price cap. Investigate grouped and fractional interests, special proceedings, flood risk, restrictions and potential duplex construction. Preserve facts separately from inferences and investment decisions.

## Data contract

Each observation records value, status, source URL or snapshot reference, retrieval time and notes. Unknown, blocked, stale and verified are distinct states. Account membership and auction lot identity are separate. Every run records source hash, effective sale date, counts, quality results, changes and stage failures.

## Security and operations

Never commit credentials, tokens, service-account keys, webhook secrets, private exports or bulk datasets. Use workload identity for CI deployment where possible and least-privilege runtime identities. Configuration examples must contain placeholders only. Cloud deployment and billing state remain unverified.
