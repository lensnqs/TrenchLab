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

## Safety and limits

No live orders, wallet keys, transaction signing, FOMO signup, referral dependency, trading advice, paid API, or automated trading. Synthetic paper results are *not* a backtest or evidence of profitability. Partial token-security observations are not a safety certification. Any missing evidence blocks clearance. Never commit credentials or licensed/raw personal data.

**Project separation:** TrenchLab is independent of LENS and PARADIGM.
