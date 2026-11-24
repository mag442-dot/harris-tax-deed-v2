# December 1, 2026 due diligence

**Live integration, November 23, 2026 (America/Chicago).** The Harris County Tax
Office HTML parsed to 157 unique accounts, matching the initial reference count:
122 for sale and 35 cancelled. Snapshot SHA-256:
`2fa1ba382b9465844545baf0dbdac7af4e9f44d2cbb18a56f56f9d160aefe73d`.
One address and 13 legal descriptions were incomplete or absent. The source
marked 42 rows with “Sold with Account”. It supplied no identifier on 37 and
repeated the same account on five. Those entries remain unresolved. Equal
counts reconcile the initial count only. The pipeline tracks missing account IDs
across accepted snapshots and suspends ranking when the roster needs review.

HCAD resolved 156 of 157 accounts. Account `1442820050057` had no match.
FEMA returned 156 intersection observations, including 20 SFHA and six
floodway intersections. The account without an HCAD
match had no parcel geometry. Intersections do not establish full coverage.
The run yielded 75 HOLD, 82 NO_BID and zero candidates. The repeat processing
run recovered 157 decisions from checkpoints.

| Module | Verified path | Open evidence |
| --- | --- | --- |
| A1 | Official pull, sale date and account reconciliation, flags and cancellations | Complete legal details and grouped lot identities |
| A2 | HCAD GIS area, class, improvement value, location and geometry, plus recorded exemptions for the review queue | Current physical vacancy and any unresolved homestead evidence |
| A3 | Validates supplied closed duplex sales and computes median sale price per sqft | Authorized closed-sale data |
| A4 | Validates parcel-specific feasibility, access and restrictions evidence | Dwelling entitlement, restrictions, access and constructability records |
| A5 | FEMA observations in a live run | FEMA coverage review and MAAPnext parcel evidence. MAAPnext draft mapping is a risk signal |
| A6 | Evidence schema for title, liens and redemption | Verified case and title records, and redemption disposition |
| A7 | Parses listing judgment date and years and ties supplied tax balances to the judgment and sale date | Official balance evidence |
| A8 | Decimal scenario and strict offer ceiling tests | Actual parcel-level taxes, liens and all other eligibility gates |
| A9 | Separate deterministic checks for data gaps, exclusions and investment risks | Independent property evidence or external review |
| A10 | Tested gated ranking by ZIP preference, base ROI, then account | Real candidates eligible for ranking |

## Supplying private evidence

Provide `--evidence /path/to/evidence.json`, or set
`DILIGENCE_EVIDENCE_OBJECT` to a private GCS object in the configured state
bucket. The JSON root maps a 13-character HCAD account string to named
observations. Every observation includes `account`, `sale_date` (`2026-12-01`),
`observed_on` (ISO date), `source` (HTTPS),
`reference` (record ID or retrieval reference) and `data` (object).
An authorized producer must establish the document's origin and accuracy.
Structural validation does not authenticate an external document.

| Observation | Fields within data |
| --- | --- |
| `hcad` | Boolean `homestead`, `vacant` |
| `comparables` | Array `sales` of at least three reviewed closed duplex transactions, each with unique `reference`, `closed_on`, `price`, `building_sf`, `closed: true`, `property_type: DUPLEX` |
| `construction` | Boolean `buildable`, `legal_access`, `restrictions_clear`, `duplex_allowed` |
| `fema_review` | Boolean `coverage_verified`, `sfha_intersects`, `floodway_intersects` |
| `maapnext` | Boolean `development_clear`, indicating whether the flood-risk review found the project acceptable |
| `title` | Boolean `title_clear`, `redemption_resolved`, and numeric `liens_due` |
| `post_judgment_tax` | `amount_due`, matching `judgment_date` as shown by the listing (MM/DD/YYYY), and `through_sale_date` (`2026-12-01`) |

A nonnegative amount of zero requires evidence. An unfamiliar or absent
observation yields UNKNOWN. Account-local evaluation errors yield HOLD and
processing continues. Failed evaluations are eligible for retry. A checkpoint
is keyed by schema version, roster context, property inputs and evidence.
Resume interrupted local evaluation by repeating the command with the same
inventory, evidence and output path. GitHub Actions restores the latest
inventory and FEMA cache on a best-effort basis.

The underwriting model uses 2,600 sqft, $105/sqft construction, $165/sqft
exit, 5% commission, $17,000 other costs, 12% annual financing, nine months,
$100,000 equity and a strict above-20% return on equity. The model applies
simple interest on peak project borrowing for the whole holding period and
adds verified liens and post-judgment taxes. The downside uses a 10% lower
exit price, 10% higher construction cost and 12 months. The upside uses a
10% higher exit price and base costs. Downside loss triggers review.
The base offer ceiling is rounded down to cents and must still exceed the
return threshold. An open risk suppresses the published ceiling.

## Cloud and Sheets

The existing Cloud Run image packages the new runner, writes immutable run
evidence to the configured GCS bucket and keeps the generation precondition on
the latest pointer. Keep the bucket private. The GitHub live workflow uses
public source data and does not consume private review bundles.

For December, set `SALE_DATE=2026-12-01` and optionally `SPREADSHEET_ID` to the
December workbook ID from `diligence.py` after granting the Cloud Run runtime
identity editor access. That identity uses Application Default Credentials.
The writer checks the target and owns only **V2 Diligence Dec01 2026**.
It refuses a pre-existing tab with a different schema, preserves text account
IDs and compares values after publishing. The November publisher remains
sale-specific. Real Cloud Run, GCS IAM, Scheduler and runtime Sheets identity
have not been verified in this environment.

Sources: [Official tax sales](https://www.hctax.net/Property/TaxSales),
[HCAD downloads](https://hcad.org/pdata/pdata-property-downloads.html),
[MAAPnext draft maps](https://www.maapnext.org/),
[Houston development guidance](https://www.houstontx.gov/planning/livableplacesfaq).

## HCAD exemption follow-up

The December live workflow runs `hcad_exemptions.py` for the HOLD queue and
joins results by account and appraisal year. It reads the HCAD Online Tax
Bills exemptions table. An explicit `None` confirms that the table listed no
exemptions for that account and year. A residential homestead entry excludes
the property. Ambiguous labels, source errors and unverified years yield
UNKNOWN. Conflicting vacancy or homestead evidence requires review. A tax
exemption observation does not establish the property's legal redemption
classification or current physical occupancy. The runner spaces requests,
retries transient failures and stops after three consecutive source errors.
Local checkpoint observations expire after 48 hours. Public workflow artifacts
exclude raw exemption pages and other exemption labels.

For a local run, use the initial December results as input and pass the
resulting directory back to diligence:

```bash
python hcad_exemptions.py --inventory state/diligence/results.json --out state/exemptions --year 2026
python diligence.py --inventory state/flood/enriched.json --hcad-exemptions state/exemptions --out state/diligence
```

The live review checked all 75 initial HOLD accounts. HCAD listed residential
homestead on 20, no exemptions on 54, and gave one inconclusive result. The
revised disposition was 55 HOLD and 102 NO_BID. Seven accounts in priority ZIPs
showed a land classification, zero building and improvement values and at least
5,000 sqft. They still need current physical vacancy evidence.
