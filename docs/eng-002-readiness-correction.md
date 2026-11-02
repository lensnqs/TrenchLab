# ENG-002 — Stage B readiness correction, PR #4

**Offline engineering only; Stage B remains unexecuted and unauthorized.** No
provider request, network-policy/draft change, proxy bypass, spending, wallet
access, order, deployment or merge was performed for this correction.

## Review and baseline

PR #4's Git head was verified as
`1fbee2c66a503e69e2d2b8601e875e74499b6d12`, matching the clean local branch
`eng-002/stage-a-doc-contract`. The GitHub PR metadata API returned `Forbidden`;
the code review used the exact Git head and local diff. PR #2 remained at
`d11d83df72ab19d9393724cfc041ae2895478460`; main remained at
`e42e531cf3dba77127fde61fa0cdec6da4f4c323`. Baseline: **58/58 tests passed**.

Both reported defects were present: capture stopped at 500 messages or three
claims, and general sampling could discard a later migration after two messages
with the same shape. This update keeps the migration acceptance predicate and
all trading/audit behavior unchanged while correcting diagnostic coverage and
evidence retention.

## Coverage correction

`--capture-only --time-priority` targets **180 connected seconds after setup**.
Claim goals and full sample allocations do not stop this mode. Raw candidate
payloads are not accumulated or returned. Client-observed duration, total elapsed
time, stop reason, decoded bytes, effective capture limits and 18 ten-second bins
are saved. `DURATION_REACHED` requires measured connected duration to reach the
target. Early frame/byte stops, receive errors or disconnects mean `TRUNCATED`.

| Resource | Revised bound |
| --- | --- |
| Connection | One; no subscription JSON, reconnect, retry or downstream HTTP calls |
| Time | 180 connected seconds; setup <=12 seconds; close timeout 1 second; outer TERM at 205 seconds and KILL after 2 more |
| Frame/byte emergency guards | 1,000,000 messages; 256 MiB decoded bytes, with at most one 64 KiB crossing message counted but unparsed |
| Message / queue | 64 KiB, compression disabled, queue high-water setting 4 |
| Process | 512 MiB virtual address space, 60 CPU seconds; supplied wrapper required for OS guards |
| Output | General samples 20 / 32 KiB plus claim samples 8 / 16 KiB; 512 KiB serialized evidence ceiling and 1 MiB process limit per file |
| Other retained state | 64 buckets per histogram; 1,024 mint identities; at most eight retained claim hashes |

Frame/byte guards are conservative abort thresholds, not evidence that a number
of messages provides sufficient coverage. Three minutes also does not guarantee
a rare migration. The procedure explicitly disallows automatic retries, longer
runs or raised limits without review. Decoded-byte accounting is not a wire-traffic
cap; queued/control/framing/close traffic is additional. Process-level kills may
leave no finalized artifact, which is an incomplete outcome, not an empty success.

After 1,024 tracked mints, `migrations` / `legacy_parser_matches` are lower bounds
and `distinct_mint_count_complete` becomes false. Novel untracked mints versus
their repeats cannot be distinguished; `dedup_overflow_frames` counts that
uncertainty. `migration_claim_frames` still counts all successfully parsed valid
claim messages including repeats. No unbounded set or raw-event list is used.

## Evidence preservation correction

The separate claim allocation takes the **first eight distinct message hashes**
eligible under the existing top-level migrate + valid-shaped-mint parser contract,
within 16 KiB. It is independent of general sample count, bytes and per-shape
quota. Invalid mints and `createPool` do not consume it. Relevant keys beyond the
general first-24-key projection are still captured by the fixed claim projection.

Each sample contains message hash, byte count, sequence, source, observation time,
outcome, and explicit UNKNOWN source verification, migration proof, origin
verification and timestamp semantics. Selected provider fields include public
identifiers, original timestamp/block and only documented literal metadata labels.
Missing, invalid or unrecognized fields are UNKNOWN. Names, arbitrary metadata,
balances, wallet/trader fields, credentials, URLs and free text are excluded.
Only the eight retained hashes are kept; repeated retained messages are suppressed
while capacity remains. Explicit retained/repeat/capacity/byte-budget counters
account for every eligible message. Capacity omissions include repeats after
saturation and must not be interpreted as a count of omitted unique migrations.

Residual sampling risks: the first eight distinct messages favor early traffic
and can share a mint; later claims are not exhaustively represented. Unknown
origin labels are redacted rather than guessed. Identifier/hash disclosure is
not anonymity. Hashes cover decoded application-message bytes, not encrypted
wire frames, and do not reconstruct the discarded original. Provider assertions
such as `burnedLiquidity: "100%"` and `poolCreatedBy: "pump"` do not verify safety,
LP burn, launchpad origin or chain inclusion. All candidates remain
`UNVERIFIED_DO_NOT_TRADE`; independent migration proof remains UNKNOWN.

## Offline validation and resource evidence

`tests/test_capture_readiness.py` adds 21 focused tests. They reproduce a late
claim after 15,001 same-shape trades, full general and claim allocations,
byte/event stops, disconnect/early timeout classification, connected-time setup
separation, bounded mint overflow, duplicate hash handling, missing/invalid/secret
field projection, key-order independence, artifact size/hash integrity, and
capture-only entry-point isolation. All clocks/traffic are synthetic or mocked.
The published example retains `DOCS_EXAMPLE_NOT_LIVE_EVIDENCE` provenance; no
replay is called an actual provider session or verified transaction.

```sh
cd /workspace/TrenchLab
/workspace/trenchlab-venv/bin/python -m unittest discover -s tests -p test_capture_readiness.py -v
/workspace/trenchlab-venv/bin/python -m unittest discover -s tests -v
git diff --check
```

Results: **21/21 focused tests and 79/79 total tests passed, 0 skipped**.
The exact pending wrapper's arguments and inherited OS limits were checked with
an offline child process rather than launching the live runner.

An additional synthetic replay processed **100,000 mock messages / 44,900,000
decoded bytes**, with a simulated 180-second clock, under the proposed 512 MiB /
60 CPU-second / 1 MiB-file process limits. Observed on this worker: **5.309 CPU
seconds, 5.350 real seconds, peak RSS 45,200 KiB, 5,094-byte evidence file**.
Provider connections: **zero**. This supports the current bounded implementation
on ordinary mock traffic; it is not provider throughput, live-duration evidence,
a worst-case memory proof or a guarantee that adversarial traffic avoids aborts.

## Delivery and stopping point

The revised [live procedure](eng-002-live-validation-procedure.md) is proposed
only. Implementation commit `d76f085f8cdab78fc4f1b0149f48bf187e7d0f10` was pushed
to PR #4's existing branch, preserving PR #2 and main. The title/body PATCH request
to `https://api.github.com/repos/lensnqs/TrenchLab/pulls/4` returned `Forbidden`;
**the PR's code is updated, but no title/body edit is claimed**. The prepared
description is retained at `/workspace/trenchlab-pr4-body.md`; the committed report
carries the revised scope, limits and evidence. No network settings were changed
to bypass that restriction. Review remaining authorization/connectivity,
resource-termination and sampling limitations before any separately authorized
Stage B. Stop for ORBIT review.
