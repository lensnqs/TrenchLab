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

ORBIT supplied an abbreviated published JSON example with original field values,
classified `PROVIDER_DOCUMENTATION_EXAMPLE_NOT_LIVE_EVIDENCE`, and reported a
retrieval date of November 2, 2026. The source is `https://pumpapi.io/stream`;
Codex reviewed the supplied excerpt, not a directly retrieved copy of the page.
No exact retrieval time or original page content hash was supplied or invented.

The excerpt describes an all-events feed with client-side filtering, one reused
connection and no application subscription message in the connection example.
Ongoing clients should handle dropped connections. The accessible documentation
does not specify an application heartbeat JSON schema, ping interval, pong payload
or heartbeat timeout; these remain UNKNOWN. Library protocol ping/pong does not
establish a provider-specific heartbeat contract. The original Colab session is
not reconstructed by this documentation example.

## Contract comparison

| Item | ORBIT's documentation findings | Existing diagnostic implementation | Conclusion |
| --- | --- | --- | --- |
| Feed | All-events | Receives application frames without a filter | Consistent; unrelated traffic may consume the event budget |
| Application subscription | None required | No `ws.send()` call | Consistent; do not add a subscription as a guessed fix |
| Migration discriminator | `action: "migrate"` | Exact top-level match | Basic schema supported by attributed docs |
| Mint | Top-level `mint` | Requires a base58-shaped string, length 32–44 | Location consistent; account validity is not proven by format |
| Pool | Top-level `poolId` | Retains a base58-shaped pool, otherwise None | Location consistent; parser permits partial claims, docs optionality is not established |
| Pool family / creator | This Pump.fun example has `pool: "pump-amm"`, `poolCreatedBy: "pump"` | Generic migration parser does not classify launchpad origin; normalized `pool` contains the `poolId` address | Do not call every `migrate` event a Pump.fun graduation; metadata is still a provider claim |
| Signature | Top-level `signature` | Retains any string, without authentication | Location consistent; parser is not a transaction verifier |
| Timestamp / block | Example contains `timestamp: 1793204432648`, `block: 462541749` | Sanitized time probe retains timestamp verbatim separately from observation time; normalized record does not expose a provider timestamp | Preserve original values; units and chain inclusion are not authenticated |
| Application heartbeat | Not specified in the accessible docs, as reported by ORBIT | Library protocol ping/pong; bounded connection timeouts and error classification | No provider-specific heartbeat schema or timing is inferred |
| Live connection / delivery | Not established by documentation | Last ENG-001 connection was proxy-blocked | No current live availability claim |
| Independent migration proof | Not established by an example | Explicit UNKNOWN; verdict `UNVERIFIED_DO_NOT_TRADE` | Preserve this distinction |

The docs support the parser's basic schema and the no-subscription choice. They
do not establish the historical reason for 15,000 frames and zero matches, event
frequency, complete validation requirements, or a successful migration transaction.
No parser correction is justified by the supplied findings. Runtime code and its
conservative `schema_status: UNVALIDATED` labels are unchanged in Stage A; this
report records the narrower documentation support separately.

## Fixtures and tests

[`fixtures/pumpapi_docs_example.json`](../fixtures/pumpapi_docs_example.json)
is labeled **`DOCS_EXAMPLE_NOT_LIVE_EVIDENCE`**, with ORBIT's evidence classification
also retained. All eleven included fields and their published values are preserved
exactly from the supplied abbreviated excerpt, including the signature, mint,
pool address, quote mint, pool family/creator, liquidity claim, token program,
block and timestamp. No omitted balances or metadata were reconstructed. Its
provenance distinguishes ORBIT's retrieval from Codex direct page access and
records live capture false / independent on-chain verification UNKNOWN. A published
`burnedLiquidity: "100%"` value is a claim, not independently verified LP evidence.

[`fixtures/pumpapi_documentation_derived.json`](../fixtures/pumpapi_documentation_derived.json)
remains labeled `DOCUMENTATION_DERIVED_SCHEMA_REPORTED_BY_ORBIT`. Only its field names,
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

[`tests/test_pumpapi_documentation_excerpt.py`](../tests/test_pumpapi_documentation_excerpt.py)
adds six tests for the preserved example, address-versus-pool-family mapping,
explicit `createPool` rejection, generic handling of a synthetic other-origin
migration, separation of original timestamp and local observation time, and mocked
capture of migration/createPool/duplicate frames. The only published payload is
the supplied migration example; mutated `createPool` and other-origin inputs are
clearly synthetic, not invented provider evidence. Parsing a documentation example
does not establish delivery, transaction success, Pump.fun origin or token safety.

```sh
cd /workspace/TrenchLab
/workspace/trenchlab-venv/bin/python -m unittest discover -s tests -p 'test_pumpapi_documentation*.py' -v
/workspace/trenchlab-venv/bin/python -m unittest discover -s tests -v
git diff --check
```

Validation: **14/14 focused tests passed; 58/58 total tests passed; 0 skipped**.
Runtime code remains identical to the reviewed diagnostic baseline. Documentation
support and independently verified source behavior are recorded separately.

## Proposed next stage and stopping point

[`eng-002-live-validation-procedure.md`](eng-002-live-validation-procedure.md)
specifies exact hosts, proxy/TLS requirements, one connection, time/frame/sample
budgets, process safeguards, outputs and outcome interpretation. It is a proposal
for a later authorized Stage B, **not an instruction to run during Stage A**.
No WebSocket attempt was made in ENG-002. No current live event counts exist;
zero new stream attempts is different from a live observation of zero events.

Stage A establishes offline consistency with the documentation excerpt supplied
by ORBIT. The remaining access limitation is direct Issue #3/page retrieval; the remaining
research limitation is actual provider delivery and independent transaction proof.
No permission change is requested or applied here. Stop for ORBIT review before
any environment settings change or Stage B execution.
