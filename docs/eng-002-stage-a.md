# ENG-002 — Stage A findings

Stage A covers documentation review, offline regression fixtures and a proposed
bounded live procedure. **Stage B has not run.** No environment configuration or
permission changes, paid resources, wallet access, orders, deployment or merge
were performed. PR #2 remains unmerged and unmodified.

## Reviewed baseline and source access

- Diagnostic baseline: `d11d83df72ab19d9393724cfc041ae2895478460`.
  Read-only `git ls-remote` confirmed this is both PR #2's head and the diagnostic
  branch head. `main` was `e42e531cf3dba77127fde61fa0cdec6da4f4c323`.
- New branch: `eng-002/stage-a-doc-contract`, based on the diagnostic baseline.
- Baseline suite: **44 tests executed, all passed**, before changes.
- Issue #3: GET `https://api.github.com/repos/lensnqs/TrenchLab/issues/3`
  returned `Forbidden`. The founder's ENG-002 message is the controlling brief.
- Official documentation GET `https://pumpapi.io/stream`: existing proxy rejected
  CONNECT with HTTP 403; curl exited 56 with origin HTTP status `000`. No provider
  page body was obtained. This does not mean the provider returned HTTP 403.
- Current environment status reported restricted networking, no custom allowed
  hosts, and policy state UNKNOWN. This is not evidence of active permission.
  No environment draft read/write, allowlist change, proxy bypass or credential
  change was used in Stage A.

ORBIT reports independently reviewing the official `/stream` page. The founder
supplied these findings in the controlling message: the feed is all-events,
requires no subscription message, and migration examples have `action: "migrate"`
with top-level `mint`, `poolId` and `signature`.

Those findings are attributed documentation evidence, not a page Codex retrieved.
No verbatim JSON example, provider timestamp definition, heartbeat example, page
retrieval time or documentation content hash was supplied. None is invented here.
An exact excerpt was requested asynchronously; the supplied findings permit the
schema-only work to proceed without it. Full direct page review remains limited
by access. The original Colab session is not reconstructed by these fixtures.

## Contract comparison

| Item | ORBIT's documentation findings | Existing diagnostic implementation | Conclusion |
| --- | --- | --- | --- |
| Feed | All-events | Receives application frames without a filter | Consistent; unrelated traffic may consume the event budget |
| Application subscription | None required | No `ws.send()` call | Consistent; do not add a subscription as a guessed fix |
| Migration discriminator | `action: "migrate"` | Exact top-level match | Basic schema supported by attributed docs |
| Mint | Top-level `mint` | Requires a base58-shaped string, length 32–44 | Location consistent; account validity is not proven by format |
| Pool | Top-level `poolId` | Retains a base58-shaped pool, otherwise None | Location consistent; parser permits partial claims, docs optionality is not established |
| Signature | Top-level `signature` | Retains any string, without authentication | Location consistent; parser is not a transaction verifier |
| Timestamp / heartbeat details | Not supplied | UTC observation time; limited unvalidated time probes; library ping/pong | Provider time units and application heartbeat schema remain UNKNOWN |
| Live connection / delivery | Not established by documentation | Last ENG-001 connection was proxy-blocked | No current live availability claim |
| Independent migration proof | Not established by an example | Explicit UNKNOWN; verdict `UNVERIFIED_DO_NOT_TRADE` | Preserve this distinction |

The docs support the parser's basic schema and the no-subscription choice. They
do not establish the historical reason for 15,000 frames and zero matches, event
frequency, complete validation requirements, or a successful migration transaction.
No parser correction is justified by the supplied findings. Runtime code and its
conservative `schema_status: UNVALIDATED` labels are unchanged in Stage A; this
report records the narrower documentation support separately.

## Fixtures and tests

[`fixtures/pumpapi_documentation_derived.json`](../fixtures/pumpapi_documentation_derived.json)
is labeled `DOCUMENTATION_DERIVED_SCHEMA_REPORTED_BY_ORBIT`. Only its field names,
top-level layout and discriminator come from the reported documentation. The two
sets of base58-shaped identifiers are synthetic substitutions, not literal copied
examples, real observed events or evidence of existing on-chain accounts. The
fixture records source URL, attribution, blocked direct retrieval, no live capture
and independent proof UNKNOWN. No unreported metadata or time fields are added.

[`tests/test_pumpapi_documentation.py`](../tests/test_pumpapi_documentation.py)
adds eight offline tests covering minimal documented field mapping, explicit
fixture provenance, invalid/missing mint, absent/unrelated action, partial claims
and unauthenticated signatures, refusal to guess nested/alternate layouts, no
fabricated provider timestamp, and mock all-events capture with no subscription,
deduplication and no downstream API calls. Negative variants are synthetic test
mutations; they are not additional claimed provider examples. The replay verifies
the real capture-only entry point against mocked WebSocket data.

```sh
cd /workspace/TrenchLab
/workspace/trenchlab-venv/bin/python -m unittest discover -s tests -p test_pumpapi_documentation.py -v
/workspace/trenchlab-venv/bin/python -m unittest discover -s tests -v
git diff --check
```

Validation: **8/8 focused tests passed; 52/52 total tests passed; 0 skipped**.
An initial fixture typo made a synthetic signature longer than the sanitizer's
88-character bound; the focused replay caught its redaction. Synthetic signatures
were corrected to 64 characters and the focused suite passed. No runtime behavior
was changed to accommodate a test.

## Proposed next stage and stopping point

[`eng-002-live-validation-procedure.md`](eng-002-live-validation-procedure.md)
specifies exact hosts, proxy/TLS requirements, one connection, time/frame/sample
budgets, process safeguards, outputs and outcome interpretation. It is a proposal
for a later authorized Stage B, **not an instruction to run during Stage A**.
No WebSocket attempt was made in ENG-002. No current live event counts exist;
zero new stream attempts is different from a live observation of zero events.

Stage A establishes offline consistency with ORBIT's documentation findings. The
remaining access limitation is direct Issue #3/page retrieval; the remaining
research limitation is actual provider delivery and independent transaction proof.
No permission change is requested or applied here. Stop for ORBIT review before
any environment settings change or Stage B execution.
