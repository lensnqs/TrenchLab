# ENG-002 — Proposed bounded live validation (Stage B)

**Prepared in Stage A; not executed.** Stage B and any environment permission
changes require a subsequent explicit assignment. Do not run the live command,
save/apply a network draft, publish an environment, or merge PR #2 during Stage A.

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

## Single capture budget

| Resource | Limit |
| --- | --- |
| Connections | One; no automatic reconnect/retry |
| Capture duration | 45 seconds including connection establishment; open timeout 12 seconds; close timeout 1 second |
| Application frames | 500; stop earlier at three unique mint claims or duration |
| Subscription messages | Zero; WebSocket library control ping/pong is separate |
| Individual received message | 1,500,000 bytes (`max_size`); queue high-water setting 16 frames |
| Stored samples | At most 20; at most two per top-level shape; 32 KiB compact serialized sample budget |
| Histogram cardinality | At most 64 buckets per histogram including overflow |
| Downstream HTTP evaluation requests | Zero (`--capture-only`); no `--mint` |
| Process virtual address space / CPU | 512 MiB / 15 CPU seconds, enforced with process resource limits |
| Single output file | 1 MiB hard file-size limit; normal artifacts are bounded sanitized evidence and a summary |
| Outer wall-clock guard | TERM at 55 seconds, KILL after a further 2 seconds |

The queue setting is a high-water mark, not a total process memory guarantee;
the process limit supplies the latter bound. At most 500 accepted application
messages of 1.5 MB means at most 750 MB decoded message payload; this is **not**
a hard wire-traffic cap because protocol/control traffic is additional. The time
and single-connection bounds apply. Any limit/resource termination makes the run
incomplete; do not automatically repeat it or expand the budget. The below
wrapper adds process guards without modifying application code.

The docs recommend reconnection handling for ongoing consumers. This one-attempt
diagnostic run deliberately records a drop and stops, retaining partial evidence;
it does not attempt ongoing service availability. Any further connection requires
a separately authorized experiment/budget, never simultaneous connections or an
unbounded retry loop. No application heartbeat message is invented.

### Pending command — do not execute in Stage A

Use the existing isolated checkout. This Linux command creates a unique local
output directory; every run summary must remain associated with its own capture.

```sh
cd /workspace/TrenchLab
mkdir -p output
capture_dir=$(mktemp -d output/eng002-stage-b.XXXXXX)
timeout --signal=TERM --kill-after=2s 55s /workspace/trenchlab-venv/bin/python - "$capture_dir" <<'PY'
import os
import resource
import sys

for limit, value in (
    (resource.RLIMIT_AS, 512 * 1024 * 1024),
    (resource.RLIMIT_CPU, 15),
    (resource.RLIMIT_FSIZE, 1024 * 1024),
):
    resource.setrlimit(limit, (value, value))
python = "/workspace/trenchlab-venv/bin/python"
os.execv(python, [python, "run_live.py", "--capture-only", "--seconds", "45",
                 "--events", "500", "--limit", "3", "--output", sys.argv[1]])
PY
capture_status=$?
printf 'capture_exit=%s output=%s\n' "$capture_status" "$capture_dir"
```

The wrapper's process limits were checked with an offline Python process;
the live command itself has **not** been run. The application's 45-second budget
is shorter than the outer guard. Exit 2 reports `stream_error`; exit 0 means only
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
The sum of parser outcomes must equal application frames counted. A stream error
can retain partial frames; distinguish that from a completed observation.

No events or no matches is inconclusive in a small all-events window; report the
actual stopping reason and do not infer provider failure or fix the schema from
absence alone. Mint deduplication is per run, not authenticated transaction-level
deduplication. Protocol ping/pong is not an application message; an undocumented
heartbeat payload must not be invented or treated as migration.

Compare the exact `action` value: `createPool` is not `migrate`, even if other
fields resemble the published example. Do not report all migration matches as
Pump.fun graduations. The normalized parser record does not retain launchpad
classification, and the sanitizer currently redacts pool-family/creator values;
any run lacking reviewable origin evidence must report origin UNKNOWN. The
supplied documentation example does not authorize weakening sanitation or adding
a launchpad filter in this diagnostic run. A `burnedLiquidity` provider value is
not a verified LP lock/burn or a token-safety certificate.

Sanitized samples are limited to the first two messages of a top-level shape and
20 overall. A later migration may increment counters without being retained as
a sample, especially if trades share its shape. If this happens, report missing
representative evidence and stop for review; counters alone do not validate the
exact migration payload. No silent rerun or sampler change is authorized by this
procedure. Histograms may overflow; nested payload values and unknown strings are
redacted or hashed. Original frames are not retained, so their hashes alone do
not permit raw reconstruction. Provider time probes are unvalidated and verbatim;
unavailable timestamp semantics stay UNKNOWN, separately from observation time.

Review sanitized outputs before sharing. Keep unreviewed outputs ignored; do not
commit secrets or dump full frames/headers. Stop on proxy denial, provider auth/
rate limiting, resource exhaustion, unexpected subscription/payment requirement,
or malformed/ambiguous contract evidence. All candidates remain
`UNVERIFIED_DO_NOT_TRADE`, and independent migration proof remains UNKNOWN until
a separately scoped read-only transaction verification establishes successful
execution against authoritative program/instruction definitions and exact mint/
pool links. No RPC verification, orders or wallet operations are part of this run.
