# TrenchLab v0.2 | Read-only Solana research observer

**Status:** experimental prototype. 25 automated *mock/fixture* tests passed locally on 2026-11-02. A real Colab session connected to the third-party PumpApi WebSocket and received **15,000 events, 0 recognized migrations**, then stopped at the configured event limit. The migration event schema is **not validated**. No real candidate has been authenticated or audited end-to-end.

## Scope

- `src/desk.py`: isolated, offline-only five-stage paper decision pipeline using fictional fixtures.
- `src/observe.py`: bounded, read-only stream listener and partial public-source adapters.
- `run_demo.py`: synthetic demonstration.
- `run_live.py`: limited real-source observation only; does **not** trigger trading signals.
- `tests/`: deterministic tests using mocked data.
- `fixtures/`: test examples, not evidence of real trading performance.

Available sources attempted by the observer: `wss://stream.pumpapi.io/` (a third party, **not PumpPortal**), DexScreener, RugCheck and Solana public RPC. Live provider schemas, availability and limits must be verified. Missing information remains `UNKNOWN`.

## Local / Codex commands

Python 3.12 recommended; virtual environment preferred.

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python run_demo.py
python run_live.py --seconds 45 --limit 3
```

The final command accesses public network endpoints and should only be run with the appropriate environment/network approval. Output is written under `output/` and is deliberately gitignored. No always-on hosting is supplied.

## Priority 001: investigate 15,000 events / zero migrations

1. Capture a *small, bounded, sanitized* sample of raw event shapes and event-type counts.
2. Verify the documented WebSocket subscription and actual migration event schema before changing `migration_from_event()`.
3. Test the parser with evidence-backed fixtures, including missing/invalid fields and unrelated events.
4. Preserve exact source and observation timestamps, hashes and error classifications.
5. Report whether any migration was independently established. Do not promote pool creation or token creation to migration without source proof.

See the Codex engineering brief supplied by ORBIT. Implement via a reviewable branch/PR; do not merge or spend without founder authorization.

### Assignment 001 diagnostics

```sh
python run_live.py --capture-only --seconds 10 --events 100 --limit 1 --output output/investigation-001
```

This mode contacts only the original WebSocket, sends no subscription guesses,
and performs no DexScreener, RugCheck or RPC evaluation. It makes one connection
attempt with no automatic retry. A stream error exits with code 2; a completed
bounded observation exits with code 0, which does **not** establish a migration.

Each run writes a unique `stream_evidence_*.json` plus `run_summary.json` in the
chosen output directory. Use a new output directory to retain each run summary.
Diagnostics cap samples at 20, two per top-level shape, with a 32 KiB compact
serialized sample budget and 64 buckets per histogram (including overflow).
Whole evidence files also contain bounded histograms and metadata. Legacy capture
remains capped at 1.5 MB per message, 180 seconds / 15,000 messages / 10 unique
legacy parser matches. The time-priority diagnostic mode below uses different
resource guards. Limits must be positive integers within their mode's bounds.

Samples retain top-level key/type shapes, public address/signature fields, and
plausible timestamp probe values verbatim. Other values are redacted; unknown
event-type strings are hashed. These probes do not define provider schemas or
timestamp units. Original frame hashes and sanitized file hashes are separate;
the original frames are not retained and cannot be reconstructed from hashes.
Wire ping/pong control frames handled by the WebSocket library are not counted
as received application messages. Nested values are redacted, not unpacked.

The existing `action == "migrate"` predicate is unchanged and explicitly
**UNVALIDATED**. `migrations` is retained for compatibility and means unique
legacy parser matches, also exposed as `legacy_parser_matches`; it never means
independently verified migrations. All evaluated candidates remain
`UNVERIFIED_DO_NOT_TRADE`. See [the engineering report](docs/assignment-001-report.md)
for actual access evidence, mock-test results and remaining blockers.

### ENG-002 Stage A

ORBIT's findings from the [official PumpApi stream documentation](https://pumpapi.io/stream)
support the existing top-level `action: "migrate"` schema and no-subscription
connection. [The Stage A report](docs/eng-002-stage-a.md) distinguishes those
attributed findings, the preserved `DOCS_EXAMPLE_NOT_LIVE_EVIDENCE` excerpt, and
separate tests with synthetic identifiers from live delivery and on-chain proof.
`createPool` is not migration, and `migrate` alone does not establish Pump.fun
origin. The [proposed live procedure](docs/eng-002-live-validation-procedure.md)
is for a separately authorized Stage B and has not been executed. Stage A changes
no parser behavior or environment permissions; PR #2 remains unmerged.

### ENG-002 readiness correction (PR #4)

The [readiness report](docs/eng-002-readiness-correction.md) supersedes the initial
500-message capture plan. `--capture-only --time-priority` targets 180 connected
seconds and continues after sample/claim goals fill. Its one-million-message and
256 MiB decoded-byte guards are emergency stops, not adequate-coverage claims.
It retains no raw candidate payloads, bounds mint tracking at 1,024, records
duration/stop reason and ten-second counts, and reports incomplete uniqueness
after tracking overflow. Use the process guards in the proposed procedure too.

Separate `migration_samples` retain at most eight distinct eligible message
hashes within 16 KiB, independent of the 20-sample / 32 KiB general sampler. They
include observation time, hash and a fixed provider-field projection with UNKNOWN
states. Omission/repeat counters disclose saturation; no sampling completeness or
on-chain proof is claimed. No Stage B capture is authorized by this change.

## Safety and limits

No live orders, wallet keys, transaction signing, FOMO signup, referral dependency, trading advice, paid API, or automated trading. Synthetic paper results are *not* a backtest or evidence of profitability. Partial token-security observations are not a safety certification. Any missing evidence blocks clearance. Never commit credentials or licensed/raw personal data.

**Project separation:** TrenchLab is independent of LENS and PARADIGM.
