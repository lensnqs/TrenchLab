# ENG-002 — Proposed bounded live validation (Stage B)

**Revised after Stage A acceptance; not executed.** Stage B and any environment
permission changes require a subsequent explicit assignment. Do not run the live
command, save/apply a network draft, publish an environment, or merge PR #2/#4
during this readiness correction. No provider endpoint is contacted by its tests.

## Purpose and network requirements

The experiment would test transport access, actual all-events message structures,
and whether any provider migration claim matches the documented basic schema.
It cannot independently prove an on-chain migration or explain the historical
Colab result from a short sample. There is no paid or wallet-dependent fallback.

The Stage A reference is the published excerpt supplied by ORBIT, retained in
`fixtures/pumpapi_docs_example.json` as `DOCS_EXAMPLE_NOT_LIVE_EVIDENCE`. It was not
captured from a live stream. Its `pool: "pump-amm"` / `poolCreatedBy: "pump"` describe
that particular provider Pump.fun example; other launchpads also emit migration
events. No generic `migrate` match establishes a Pump.fun graduation.

| Required destination | Protocol / port | Scope |
| --- | --- | --- |
| `pumpapi.io` | HTTPS, TCP 443, `GET /stream` | Retrieve/reconfirm official documentation; at most one request, 20-second timeout, no automatic retries or redirects |
| `stream.pumpapi.io` | WSS, TCP 443, path `/` | One capture connection using the existing HTTPS proxy's CONNECT and TLS trust, including WebSocket upgrade |

These are exact destination hostnames, not wildcards or URLs to place in a
hostname allowlist. Both current policy authorization and proxy support for WSS
must be established; an HTTPS allowlist entry alone does not prove WebSocket
access. Use inherited `HTTPS_PROXY`/`HTTP_PROXY` and CA configuration (the selected
executor snapshot names `http://proxy:8080`). Do not change routes, unset proxies,
use an alternate tunnel, disable TLS verification, or assume separate TCP grants.
`InvalidProxyStatus` means the proxy rejected CONNECT before provider upgrade.

`api.github.com:443` is needed only for issue/PR API access, not this live capture;
`github.com:443` is used for Git. Capture-only does **not** need DexScreener,
RugCheck, Solana RPC, PumpPortal, a wallet, credentials or a funded account to be
added. Existing URI carries no key. If the provider demands authentication, payment,
an additional host or a changed contract, stop and report it; do not invent access.
Use the installed Python 3.12 venv, requests 2.34.2 and websockets 16.1.1. No
dependency download or new cloud resource is part of this procedure.

## Authorized-stage preflight

After separate authorization, first inspect current `environment_status`, actual
policy and Git status. Apply only specifically authorized host changes, preserving
all existing requirements. A saved draft or stale/UNKNOWN observation does not
establish readiness. Recheck the actual permitted operation after a meaningful
configuration change; do not loop denied requests.

Read `https://pumpapi.io/stream` with a 20-second limit and no automatic redirects
or retries; stop on a denied request or unexpected host. Preserve the retrieval
time and content hash of any successfully obtained page locally. Compare it with
ORBIT's findings: all-events, no application subscription, top-level migrate/mint/
poolId/signature. If the page disagrees or the contract is unclear, stop before
connecting. Do not substitute PumpPortal documentation. Provider timestamp and
heartbeat semantics must be quoted only if actually documented. The supplied
example's original `timestamp: 1793204432648` and `block: 462541749` do not establish
timestamp units, transaction success or authenticated chain inclusion. ORBIT
reports that the accessible documentation leaves application heartbeat schema,
ping interval, pong payload and timeout unspecified; keep those UNKNOWN.

Run the offline regression suite first. Confirm the output directory is ignored
and has adequate space. Do not print environment values or credential files.
Record commit SHA, dependency versions and the actual selected limits.

## Duration takes priority over message count

The proposed experiment targets **180 connected seconds**, starting after the
WebSocket handshake, rather than a frame count or number of migration claims.
`--capture-only --time-priority` makes no downstream evaluation calls and retains
no raw candidate payloads. It continues after the legacy `--limit` goal or either
sample allocation fills. The frame and cumulative-byte bounds below are emergency
resource stops, not statements about adequate market coverage. Reaching either
early is **TRUNCATED** coverage and requires review, never an automatic increase
or retry. Neither 500 nor 15,000 frames is a coverage target. Three minutes is a
bounded experiment, not evidence that a rare event should have occurred.

The report records requested duration, actual connected observation time, total
elapsed time, stop reason, decoded message bytes and 18 ten-second bins of event
and accepted-claim-frame counts. Connection setup and close time are excluded from
connected observation time. `DURATION_REACHED` requires reaching the measured
connected target. Slow consumers, unobserved server drops and backpressure can
still make client counts incomplete.

## Single capture budget

| Resource | Limit |
| --- | --- |
| Connections | One; no automatic reconnect/retry |
| Capture duration | 180 connected seconds; separate open timeout 12 seconds; close timeout 1 second |
| Application frames | 1,000,000 emergency stop; no claim/sample-goal early stop |
| Subscription messages | Zero; WebSocket library control ping/pong is separate |
| Individual received message | 64 KiB (`max_size`), compression disabled; queue high-water setting 4 frames |
| Cumulative decoded bytes | 256 MiB stop; crossing message is counted but not parsed, with at most one 64 KiB message of overshoot; queued/unread transport bytes are additional |
| General sample allocation | At most 20; at most two per shape; 32 KiB compact serialized budget |
| Reserved migration-claim allocation | First 8 distinct message hashes eligible under the parser; separate 16 KiB serialized budget; no per-shape quota |
| Histogram cardinality | At most 64 buckets per histogram including overflow |
| Mint deduplication | At most 1,024 tracked mints; explicit overflow and unique-count incompleteness |
| Downstream HTTP evaluation requests | Zero (`--capture-only`); no `--mint` |
| Process virtual address space / CPU | 512 MiB / 60 CPU seconds, enforced with process resource limits |
| Evidence / process file size | Evidence serializer checks 512 KiB before writing; process hard limit 1 MiB per file; capture-only writes evidence and summary, no raw directory or database |
| Outer wall-clock guard | TERM at 205 seconds, KILL after a further 2 seconds |

The queue setting is a high-water mark, not a total process memory guarantee;
the process limit supplies an address-space bound. Decoded message bytes are not
a hard wire-traffic cap: framing, control, buffered transport and close traffic
are additional. A legitimate oversized event can terminate this run rather than
being silently skipped. These limits are resource tradeoffs, not evidence that
all events were observed. CPU/memory/file/wall-limit termination may prevent final
artifact writing; missing artifacts mean incomplete evidence. Do not repeat or
expand limits automatically. Running only the application omits the OS guards.

The docs recommend reconnection handling for ongoing consumers. This one-attempt
diagnostic run deliberately records a drop and stops, retaining partial evidence;
it does not attempt ongoing service availability. Any further connection requires
a separately authorized experiment/budget, never simultaneous connections or an
unbounded retry loop. No application heartbeat message is invented.

### Pending command — do not execute without Stage B authorization

Use the existing isolated checkout. This Linux command creates a unique local
output directory; every run summary must remain associated with its own capture.

```sh
cd /workspace/TrenchLab
mkdir -p output
capture_dir=$(mktemp -d output/eng002-stage-b.XXXXXX)
timeout --signal=TERM --kill-after=2s 205s /workspace/trenchlab-venv/bin/python - "$capture_dir" <<'PY'
import os
import resource
import sys

for limit, value in (
    (resource.RLIMIT_AS, 512 * 1024 * 1024),
    (resource.RLIMIT_CPU, 60),
    (resource.RLIMIT_FSIZE, 1024 * 1024),
):
    resource.setrlimit(limit, (value, value))
python = "/workspace/trenchlab-venv/bin/python"
os.execv(python, [python, "run_live.py", "--capture-only", "--time-priority",
                 "--seconds", "180", "--events", "1000000", "--output", sys.argv[1]])
PY
capture_status=$?
printf 'capture_exit=%s output=%s\n' "$capture_status" "$capture_dir"
```

The wrapper's process limits were checked with an offline Python process;
the live command itself has **not** been run. The application budget is at most
12 + 180 + 1 seconds before outer cleanup safeguards. Exit 2 reports `stream_error`;
exit 0 means only
a completed bounded observation. Timeout/resource exits or missing artifacts
mean incomplete capture, not a successful empty observation. If a parent shell
uses `set -e`, capture the nonzero status explicitly rather than letting the shell
skip evidence inspection.

## Readout and evidence handling

Inspect `run_summary.json` and the unique `stream_evidence_*.json`; check the
returned file hash, source URI, start/end and observation times, connection status,
error class/status, events_seen, parser_outcomes, discriminator/shape histograms
and sample counts. Report `migrations` / `legacy_parser_matches` as **unique
provider-claim mint matches**, never independently verified migration counts.
These distinct-mint counts are a lower bound when `distinct_mint_count_complete`
is false; `dedup_overflow_frames` reports events whose novel-versus-repeat status
could not be tracked. `migration_claim_frames` includes valid-parser claim repeats.
Byte-budget rejection messages are unparsed, not evidence of absence. Parser
outcomes and time-bin events must each sum to messages counted. A stream error
can retain partial messages; distinguish that from a full-duration result.

No events or no matches is inconclusive in a small all-events window; report the
actual stopping reason and do not infer provider failure or fix the schema from
absence alone. Mint deduplication is per run, not authenticated transaction-level
deduplication. Protocol ping/pong is not an application message; an undocumented
heartbeat payload must not be invented or treated as migration.

Compare the exact `action` value: `createPool` is not `migrate`, even if other
fields resemble the published example. Do not report all migration matches as
Pump.fun graduations. The normalized parser record does not classify launchpad
origin. The reserved projection retains documented `pool: "pump-amm"` /
`poolCreatedBy: "pump"` strings as provider assertions only; unknown labels stay
UNKNOWN and origin verification is always UNKNOWN. No launchpad filter is added.
A `burnedLiquidity` value is not a verified LP lock/burn or safety certificate.

## Separate migration evidence allocation

General samples remain limited to 20 / two per shape / 32 KiB. Independently,
`migration_samples` reserves eight samples and 16 KiB for parser-eligible
`action == "migrate"` messages with a valid-shaped top-level mint. Invalid mints
and `createPool` cannot consume this allocation. Eligibility is a parser claim,
not authentication. General saturation, identical trade shapes, and the general
first-24-key projection cannot suppress these claim slots.

Each record contains source, sequence, observation time, SHA-256 of original
decoded application-message bytes, message length, parser outcome, and explicit
UNKNOWN source/origin/transaction/time-semantics verification. Its fixed
`provider_fields` projection retains well-shaped mint/poolId/signature/quoteMint,
plausible original timestamp and block, and only documented literal pool/creator/
token-program/liquidity labels. Missing, invalid or unrecognized values are
UNKNOWN. Names, symbols, balances, wallet/trader metadata, arbitrary keys, URLs,
headers and free text are excluded. No time units, LP proof or chain inclusion
are inferred from provider assertions.

While slots remain, exact retained message hashes suppress repeats; this is not
transaction-level deduplication. After saturation, every further eligible message
increments `omitted_capacity`, including repeats; byte-budget omissions and
earlier repeat suppression are separate counters. The first eight distinct
messages may share a mint and favor early arrivals. Later claims can be counted
without examples after the explicit cap. Report omissions and missing evidence
rather than claiming exhaustive sampling. No raw payload collection, silent
expansion or automatic rerun is authorized. Public identifiers and hashes are
not anonymity guarantees. Histograms can overflow; originals cannot be
reconstructed from sanitized samples/hashes. Documentation fixtures, mocked test
traffic, actual received messages and independently verified transactions remain
separate evidence classes.

Review sanitized outputs before sharing. Keep unreviewed outputs ignored; do not
commit secrets or dump full frames/headers. Stop on proxy denial, provider auth/
rate limiting, resource exhaustion, unexpected subscription/payment requirement,
or malformed/ambiguous contract evidence. All candidates remain
`UNVERIFIED_DO_NOT_TRADE`, and independent migration proof remains UNKNOWN until
a separately scoped read-only transaction verification establishes successful
execution against authoritative program/instruction definitions and exact mint/
pool links. No RPC verification, orders or wallet operations are part of this run.
