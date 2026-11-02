# ORBIT engineering report — Assignment 001

**Outcome B: provider contract verification blocked.** The cause of the original
15,000-message / zero-migration Colab result remains UNKNOWN. No genuine migration
was independently established. This change adds diagnostics without changing the
unverified migration predicate or inventing a subscription or alternative schema.

## Baseline and scope

- Repository: `lensnqs/TrenchLab`, baseline
  `e42e531cf3dba77127fde61fa0cdec6da4f4c323` (exact match to ORBIT's brief).
- Initially clean checkout on `work`; dedicated branch:
  `fix/issue-1-migration-evidence`. No worktree, reset, merge, deployment, paid
  service, wallet access, order or signing operation.
- Before modifications: `python -m unittest discover -s tests -v` executed
  **25 tests, all passed**, Python 3.12.14. No baseline failures.
- The full issue text was supplied by the founder in chat after issue retrieval
  failed. Source files were already present; native Git read access succeeded.

## Evidence and source contract

The only original-session evidence available is ORBIT's aggregate report:
connected=true, events_seen=15000, migrations=0, reason=event_limit. No original
frames or type histogram were supplied. The legacy implementation discarded
rejected frames. Therefore absence of migration events, a wrong subscription,
schema mismatch, malformed data and premature exhaustion by unrelated traffic
cannot be distinguished for that session.

| Contract item | Verified in baseline source | Provider evidence in this task |
| --- | --- | --- |
| Endpoint | `wss://stream.pumpapi.io/`; identified as a third party, not PumpPortal | Connection rejected by configured proxy before provider handshake |
| Subscription | No application messages sent | Required subscription is UNKNOWN; none guessed |
| Migration discriminator | Exact top-level `action == "migrate"` | UNVALIDATED; existing fixtures are fictional |
| Mint | Top-level base58-shaped `mint`, length 32–44 | Actual location and semantics UNKNOWN; format alone is not authentication |
| Pool/signature | Optional top-level `poolId` / `signature` | Meaning and necessity UNKNOWN |
| Timestamps | Local observation time only | Provider units, timezone and meaning UNKNOWN |
| Heartbeats | Library handles protocol ping/pong; application frames use JSON parser | Application heartbeat format UNKNOWN |
| Migration proof | No on-chain transaction authentication | UNKNOWN; no independently verified migrations |

Actual external operations on 2026-11-02:

| Destination / operation | Actual result |
| --- | --- |
| `https://github.com/lensnqs/TrenchLab.git`, `git ls-remote origin HEAD` | Succeeded; baseline SHA matched |
| `https://api.github.com/graphql`, issue query | `Forbidden` |
| `https://api.github.com/repos/lensnqs/TrenchLab/issues/1`, GET | `Forbidden` |
| `https://github.com/lensnqs/TrenchLab/issues/1`, GET | HTTP 404; no authenticated issue content obtained |
| `https://pumpapi.io/`, GET to discover provider documentation | Proxy CONNECT HTTP 403; no documentation retrieved |
| `wss://stream.pumpapi.io/`, single diagnostic connection | `InvalidProxyStatus`, HTTP 403; connected=false; 0 application frames |
| PyPI / Python package download hosts, dependency installation | Succeeded with inherited proxy and TLS verification |

The provider documentation was **not read successfully**. The 403 is local
access evidence, not evidence that PumpApi is down or lacks migration support.
At the time of the attempts, the reported enforced restricted policy omitted
`api.github.com`, `pumpapi.io` and `stream.pumpapi.io`. Those domains were added
to the saved environment draft, not applied to the running instance. A later
status observation reported policy state UNKNOWN and the same empty custom host
list; it did not establish that access had changed. No denial was bypassed.

### Retained real evidence

[`evidence/stream-access-denied.json`](evidence/stream-access-denied.json) is the
unaltered sanitized artifact from the single real connection attempt:

- Observation: **2026-11-02 19:15:08 WAT** (artifact stores UTC start/end).
- Configured limits: 10 seconds, 100 frames, one unique parser match.
- Connected: false; frames: **0**; classifications: **none**; samples: **0**;
  legacy parser matches: **0**; independent migration proof: **UNKNOWN**.
- SHA-256:
  `dd18915879d8a1ece1d6f37d803e40fdc75d207ce60587478ea4be335e0d1e2e`.
- This artifact was captured during implementation, before the final CLI exit
  status and compact JSON serialization changes. It is retained unchanged; its
  hash was checked after copying. The final CLI's error exit is tested offline.

No raw provider event fixtures are included because no frames were received.
`fixtures/stream_diagnostic_mocks.json` and existing `provider_mocks.json` are
explicitly synthetic and must never be cited as provider schema evidence.

## Implementation

- `src/stream_evidence.py`: count every received application frame, bounded
  top-level shape and discriminator probes, parser outcomes, sanitized samples,
  original-frame hashes, observation timestamps and unique evidence files.
  Plausible top-level time-probe values are preserved verbatim without assuming
  units or meanings; absent/unrecognized provider times remain UNKNOWN.
- `src/observe.py`: keep the exact migration acceptance predicate. Explicitly
  mark matches UNVALIDATED / proof UNKNOWN; classify invalid JSON, non-objects,
  nonmatching action, invalid mint and duplicate mint separately. Bound runtime,
  frames and memory, report connection errors without exception text, and retain
  partial diagnostics on disconnect. No automatic reconnect or retry; another
  run starts a new connection and independent counters/dedup state.
- `run_live.py`: `--capture-only`, `--events`, `--output`; capture-only makes no
  DexScreener, RugCheck or RPC evaluation calls. Stream error exits with code 2.
- Scanner persistence now says `UNVERIFIED_MIGRATION_CLAIM`; research verdicts
  remain `UNVERIFIED_DO_NOT_TRADE` even if every audit layer is marked PASS.
- README documents limits, probes, output semantics and reproducible commands.

Changed tracked files: `README.md`, `run_live.py`, `src/observe.py`,
`src/stream_evidence.py`, `tests/test_stream_evidence.py`,
`fixtures/stream_diagnostic_mocks.json`, `docs/assignment-001-report.md`, and
`docs/evidence/stream-access-denied.json`.

Samples are limited to 20, two per shape, with a 32 KiB compact serialized sample
budget. Each histogram has at most 64 buckets including overflow. Values are
redacted except for selected public identifiers, plausible time probes and a
small diagnostic type vocabulary. Other type strings are hashed. Nested values,
free text and exception messages are not logged. Complete files additionally
contain bounded histograms and metadata. Hashes are not reversible raw evidence;
the sanitizer deliberately loses information. Automatic retries are excluded to
avoid traffic/reconnect storms. Operator-created repeated runs can accumulate
files; use distinct output directories and remove local outputs when no longer
needed. Do not commit unreviewed live outputs.

## Validation

Python 3.12.14; isolated venv `/workspace/trenchlab-venv`; requests 2.34.2,
websockets 16.1.1. Repository dependency declarations and fixtures were not
replaced. TLS and package verification were not disabled.

```sh
cd /workspace/TrenchLab
/workspace/trenchlab-venv/bin/python -m unittest discover -s tests -v
/workspace/trenchlab-venv/bin/python -m pip check
/workspace/trenchlab-venv/bin/python run_demo.py
git diff --check
```

- Final suite: **44 tests executed, 44 passed, 0 skipped** (25 baseline + 19 new).
- Mock coverage: malformed and non-object frames, missing fields, unrelated
  events, duplicate mint handling, sample goals, event and duration limits,
  disconnect preservation/no automatic reconnect, fresh connection isolation,
  HTTP 429/no retry, connect timeout, sanitation/hashes, timestamp separation,
  bounded histogram/sample growth, capture-only isolation, and nonzero CLI error.
- A deterministic replay supplies 15,000 synthetic `action=buy` frames: exactly
  15,000 counted, zero matches, event_limit, two stored samples. This demonstrates
  diagnostics and one possible failure mode; it does **not** identify the actual
  Colab messages or prove the historical cause.
- `pip check`: passed; synthetic demo: passed and clearly fictional; whitespace
  diff check: passed. No paid/live downstream APIs were tested.

## Remaining blockers and recommended experiment

1. Apply the saved network additions through environment settings. The onboarding
   draft save is not runtime activation or publication. The platform says the
   environment draft requires review/save and publication; no publication was
   performed, and founder authorization is required before doing so.
2. Read the actual PumpApi documentation after access works. Establish free/read-
   only availability, subscription payload, message categories and documented
   migration semantics. Record documentation URLs, retrieval time and content
   hashes. Do not borrow PumpPortal's contract for this third-party host.
3. Make one fresh bounded capture using the documented subscription only after
   it has been established. Compare samples with docs; preserve source times and
   observation times separately. Extend the parser only with evidence-backed
   fixtures and an exact field/semantics mapping. No guessed alternatives.
4. If PumpApi cannot establish migration semantics, prefer a read-only chain-
   evidence experiment: obtain a public known migration transaction signature,
   verify the successful transaction against the authoritative Pump program ID
   and versioned instruction definition, and establish exact mint/pool links.
   Then consider a bounded public Solana RPC log/transaction observation for that
   verified program. Neither a log name nor pool creation alone proves migration.
   This is a recommendation, not an implemented or validated alternative. Public
   RPC availability/rate limits and authoritative ABI evidence remain prerequisites;
   use no paid fallback or funded account.

## Acceptance and delivery

AC-01 baseline, AC-03 diagnostics and AC-05 independent mock testing are completed.
AC-04 keeps the unvalidated predicate unchanged and adds fail-closed labels.
AC-06 preserves available provenance with explicit time/schema limitations.
AC-02 contains the source-code comparison and honest absence of provider evidence;
provider schema verification remains blocked. AC-07 is Outcome B, not Outcome A.
AC-08 uses the expressly authorized local-patch fallback: Git push succeeded but
`POST https://api.github.com/repos/lensnqs/TrenchLab/pulls` returned `Forbidden`.
**No draft PR exists.** The request explicitly specified `draft: true`, head
`fix/issue-1-migration-evidence`, base `main`; no merge was attempted.

Implementation commit `0547a037a58baff89adc216f0b0aa92fd63bbe0f` was published to
the dedicated branch. The subsequent report-only commit records this delivery
result; its full SHA is included in the final delivery. A complete baseline-to-
delivery patch and ready-to-submit draft PR body are retained outside the checkout
at `/workspace/trenchlab-issue-1.patch` and `/workspace/trenchlab-pr-body.md`.
After GitHub API access is restored, the prepared JSON payload at
`/workspace/trenchlab-pr.json` can be submitted with:

```sh
gh api --method POST repos/lensnqs/TrenchLab/pulls --input /workspace/trenchlab-pr.json
```

Reusable `install_script` and `start_skill` contents were saved in the environment
draft after the full install/test/demo script was executed successfully and
repeatably. The draft also retains the three network additions. No background
service is required. Offline/mock development is validated; live source access,
publication, and restoration in a fresh task are not validated.

Stop for ORBIT review. No merge, deployment, spending or claim of authenticated
migration behavior is authorized by these offline tests.
