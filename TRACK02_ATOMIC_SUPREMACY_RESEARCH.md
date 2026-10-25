# Track 02 atomic-supremacy research record

Date: 25 October 2026

Branch: `feat/track02-atomic-supremacy`

Protected submission anchor: `main` at `f1b6d992a669cd9f271d510427ac2847515667ed`

## Safety decision

The submitted `main` branch and the HackOS submission remain unchanged. This research branch is not eligible for resubmission yet because the physical two-source federation, replacement video, and replacement deck have not all passed the release gate.

## Zetaris multi-relation experiment

`scripts/capture_live_integrations.py` now expresses the deterministic scenario as two named logical relations:

- `market_ticks`: venue, pair, bid, ask and volume;
- `venue_telemetry`: venue, latency and health status.

The relations are joined on `venue`. The claim boundary explicitly states that these are declared synthetic logical relations and not independently onboarded external sources.

Live read-only execution against the official local Zetaris Docker bundle 2.4.3 succeeded:

- containers: UI, API, driver and PostgreSQL all `healthy`;
- connectivity query: 1 row, approximately 1,679 ms;
- two-relation JOIN: 4 rows, approximately 8,395 ms;
- consensus: three included venues, one rejected outlier, `CALM` post-filter regime;
- no DDL, onboarding, write, drop or instance mutation was performed.

The experiment proves that the local engine can execute this JOIN within the current client timeout. It does **not** yet prove physical federation across two independently registered data sources. The authenticated project SQL endpoint accepts the tested `SELECT`, but rejects `SHOW LIGHTNING DATABASES` as a non-SELECT statement. The reference checkout lacks its own `.env.local` API key, so source discovery through that separate harness was not available.

## Static Audit Viewer

Implemented:

- generator: `scripts/generate_audit_viewer.py`;
- output: `artifacts/index.html`;
- direct inputs: `evidence/zetaris-live-receipt.json` and `evidence/meterless-hmem-runtime/ledger.jsonl`;
- embedded validated snapshot for `file://` use;
- same-origin refresh from the two evidence files when served;
- no CDN, external JavaScript, analytics or secret material.

Browser validation confirmed that the page renders:

- run ID, Zetaris row count, ledger-event count and risk regime;
- four venue latency bars with the anomalous venue visually distinguished;
- the four append-only ledger events.

The GitHub repository is public, but the GitHub API reports `has_pages: false`; GitHub Pages is not currently configured. Publishing Pages is deliberately deferred until the release gate is satisfied.

## Test result

The Python suite now passes **30/30** tests. The six new tests cover:

- both logical relation names;
- the JOIN and join key;
- preservation of the four-row scenario;
- receipt and JSONL input validation;
- dependency-free dashboard generation;
- safe escaping of embedded JSON.

## HackOS edit/resubmission risk

Read-only inspection on 25 October 2026 showed:

- submission header: `#1 The Agent That Can Explain Why Submitted`;
- progress: `Submitted 1 / 1`;
- description and GitHub fields remain editable;
- uploaded video and deck remain present;
- a `Save Changes` control is available;
- official deadline: 27 October 2026, 23:45 UTC;
- rule 3.3 states that the track may be changed before the submission deadline.

This demonstrates that the submitted record is editable before the deadline. It does not prove, without performing a mutation, that pressing `Save Changes` preserves every aspect of the submitted state. No field was changed and `Save Changes` was not pressed.

## Release gate

| Gate | Result | Required before main/HackOS update |
|---|---|---|
| Submitted anchor protected | PASS | Keep `main` at `f1b6d99` until final promotion |
| Multi-relation Zetaris JOIN | PASS | Preserve live receipt and exact timing as an observation |
| Two independently onboarded sources | NOT PROVEN | Execute a read-only query over two registered sources and preserve source metadata |
| Audit Viewer | PASS locally | Decide whether to publish through Pages only after final promotion |
| Python tests >= 28 | PASS, 30/30 | Re-run immediately before promotion |
| Replacement video | NOT CREATED | Produce and validate 1–4 minute demo showing the new flow |
| Replacement deck | NOT CREATED | Update and visually validate sponsor/multi-source claims |
| HackOS save preserves submission | NOT MUTATION-TESTED | Update only after every other gate passes; verify status immediately after save |

## Current verdict

**Do not merge to `main`; do not update HackOS.** The branch is a validated research prototype, while the submitted build at 20:53 EET remains the safer competition entry.
