"""TrenchLab v0.2: bounded, read-only Solana migration observer.

No wallets, trades, live positions, or safety certification. All unverified
security layers remain explicitly UNKNOWN; missing provider responses fail closed.
The public stream is third-party, not an on-chain proof of migration.
"""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.stream_evidence import StreamEvidence

DEX = "https://api.dexscreener.com/tokens/v1/solana"
RUG = "https://api.rugcheck.xyz/v1/tokens"
RPC = "https://api.mainnet-beta.solana.com"
STREAM = "wss://stream.pumpapi.io/"  # third-party free stream; not PumpPortal
_BASE58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_mint(mint: Any) -> bool:
    return isinstance(mint, str) and bool(_BASE58.fullmatch(mint))


def json_value(x: Any, *path: str) -> Any:
    for part in path:
        if not isinstance(x, dict):
            return None
        x = x.get(part)
    return x


def numeric(x: Any) -> float | None:
    if isinstance(x, bool) or x is None:
        return None
    try:
        f = float(x)
        if f != f or not -1e308 < f < 1e308:
            return None
        return f
    except (ValueError, TypeError, OverflowError):
        return None


def migration_from_event(raw: Any) -> dict | None:
    """Legacy, UNVALIDATED contract; a match is not independent migration proof.

    Keep this fixture-tested assumption until provider docs and captured frames
    establish the real subscription and schema. Never infer from pool creation.
    """
    if not isinstance(raw, dict) or raw.get("action") != "migrate":
        return None
    mint = raw.get("mint")
    if not is_mint(mint):
        return None
    pool = raw.get("poolId")
    return {"mint": mint, "pool": pool if is_mint(pool) else None,
            "signature": raw.get("signature") if isinstance(raw.get("signature"), str) else None,
            "name": raw.get("name") if isinstance(raw.get("name"), str) else None,
            "symbol": raw.get("symbol") if isinstance(raw.get("symbol"), str) else None,
            "observed_at": utcnow(), "source": "pumpapi_stream",
            "schema_status": "UNVALIDATED", "independent_migration_proof": "UNKNOWN"}


@dataclass
class ObservationConfig:
    duration_s: int = 45
    max_migrations: int = 3
    max_events: int = 15000
    request_timeout_s: int = 12
    rpc_url: str = RPC

    def validate_capture(self):
        for name, maximum in (("duration_s", 180), ("max_events", 15000), ("max_migrations", 10)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be an integer from 1 to {maximum}")


def save_raw(out: Path, source: str, mint: str, payload: Any) -> str:
    folder = out / "raw"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{mint}_{source}.json"
    path.write_text(json.dumps({"source": source, "captured_at": utcnow(),
                                "payload": payload}, indent=2, default=str), encoding="utf-8")
    return str(path)


def init_db(out: Path) -> sqlite3.Connection:
    out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(out / "observations.sqlite3")
    db.execute("""CREATE TABLE IF NOT EXISTS observations
       (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, mint TEXT NOT NULL, source TEXT NOT NULL,
        http_status INTEGER, evidence_file TEXT, error TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS decisions
       (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, mint TEXT NOT NULL, stage TEXT NOT NULL,
        status TEXT NOT NULL, details_json TEXT NOT NULL)""")
    db.commit()
    return db


def record_source(db, mint: str, source: str, file: str | None,
                  status: int | None = None, error: str | None = None):
    db.execute("INSERT INTO observations(ts,mint,source,http_status,evidence_file,error) VALUES(?,?,?,?,?,?)",
               (utcnow(), mint, source, status, file, error))
    db.commit()


def record_decision(db, mint: str, stage: str, status: str, details: Any):
    db.execute("INSERT INTO decisions(ts,mint,stage,status,details_json) VALUES(?,?,?,?,?)",
               (utcnow(), mint, stage, status, json.dumps(details, default=str)))
    db.commit()


def get_json(session, url: str, timeout: float) -> tuple[Any | None, int | None, str | None]:
    try:
        response = session.get(url, timeout=timeout, headers={"Accept":"application/json"})
        status = response.status_code
        if status != 200:
            return None, status, f"HTTP {status}"
        return response.json(), status, None
    except Exception as exc:
        return None, None, f"{type(exc).__name__}: {str(exc)[:160]}"


def rpc_json(session, rpc_url: str, method: str, params: list, timeout: float):
    try:
        response = session.post(rpc_url, json={"jsonrpc": "2.0", "id": 1,
                                                  "method": method, "params": params},
                                timeout=timeout, headers={"Content-Type":"application/json"})
        if response.status_code != 200:
            return {"http_status": response.status_code, "error": f"HTTP {response.status_code}"}
        response_data = response.json()
        if not isinstance(response_data, dict):
            return {"http_status": 200, "error": "non-object response"}
        return response_data
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}


def pair_for_migration(pairs: Any, pool: str | None) -> dict | None:
    """Never infer the migrated pool from a different token pair."""
    if not isinstance(pairs, list) or not pool:
        return None
    valid = [p for p in pairs if isinstance(p, dict)
             and p.get("chainId") == "solana"
             and p.get("pairAddress") == pool]
    return max(valid, key=lambda p: numeric(json_value(p, "liquidity", "usd")) or 0, default=None)


def dex_summary(pairs: Any, pool: str | None):
    pair = pair_for_migration(pairs, pool)
    if pair is None:
        return {"status": "UNKNOWN", "reason": "observed migration pool not present in DexScreener response",
                "liquidity_usd": None, "price_usd": None, "age_min": None}
    created = numeric(pair.get("pairCreatedAt"))
    age = max(0, (time.time() * 1000 - created)/60000) if created is not None else None
    return {"status": "OBSERVED", "pair_address": pair.get("pairAddress"),
            "dex_id": pair.get("dexId"), "liquidity_usd": numeric(json_value(pair, "liquidity", "usd")),
            "price_usd": numeric(pair.get("priceUsd")), "age_min": age,
            "h1_change_pct": numeric(json_value(pair, "priceChange", "h1")),
            "volume_h1": numeric(json_value(pair, "volume", "h1"))}


def mint_authorities(rpc_account: Any):
    """Only a validated parsed mint object is evidence of authority revocation."""
    account = json_value(rpc_account, "result", "value")
    parsed = json_value(account, "data", "parsed")
    info = json_value(parsed, "info")
    if not isinstance(info, dict) or json_value(parsed, "type") != "mint":
        return {"mint_revoked": None, "freeze_revoked": None,
                "reason": "mint account missing or not jsonParsed mint"}
    result = {}
    for label, field in (("mint_revoked", "mintAuthority"), ("freeze_revoked", "freezeAuthority")):
        result[label] = (info[field] is None) if field in info else None
    return result


def audit_layers(authorities: dict, summary: dict, rug: Any, rpc_supply: Any,
                 rpc_largest: Any) -> list[dict]:
    """Eight honest research labels; UNKNOWN is never PASS.

    No inference of creator history, concentration exclusions, LP locks, wallet
    clusters, or delegations from incomplete provider evidence.
    """
    layers = []
    def item(n, name, status, evidence):
        layers.append({"n": n, "name": name, "status": status, "evidence": evidence})
    for i, label, key in [(1, "Mint authority", "mint_revoked"), (2, "Freeze authority", "freeze_revoked")]:
        value = authorities.get(key)
        status = "PASS" if value is True else "FAIL" if value is False else "UNKNOWN"
        item(i, label, status, f"RPC parsed mint {key}={value!r}")
    item(3, "Creator ownership / prior selling", "UNKNOWN", "No verified migration-era creator holdings or transfer history")
    item(4, "Top 10 adjusted concentration", "UNKNOWN", "Largest token accounts are not proven wallet owners; pool/curve exclusions unverified")
    item(5, "LP burned / locked", "UNKNOWN", "No validated LP mapping and lock proof for this exact pool")
    age = summary.get("age_min")
    status = "PASS" if isinstance(age, (int, float)) and age >= 10 else "FAIL" if isinstance(age, (int,float)) else "UNKNOWN"
    item(6, "Pool age >= 10 min", status, f"DexScreener pairCreatedAt age (approx.): {age!r} min")
    item(7, "Bundled wallets", "UNKNOWN", "No validated insider graph connected-components method")
    item(8, "Delegated token accounts", "UNKNOWN", "No mint-filtered Token + Token-2022 exhaustive RPC check")
    return layers


def research_verdict(layers: list[dict]):
    # Layer checks cannot establish a migration or certify a token as safe.
    return "UNVERIFIED_DO_NOT_TRADE"


def evaluate_mint(migration: dict, raw_migration: Any, out: Path, db,
                  session, cfg: ObservationConfig) -> dict:
    """Fetch a bounded number of read-only observations. No execution logic."""
    mint = migration["mint"]
    path = save_raw(out, "migration", mint, raw_migration)
    record_source(db, mint, "migration", path)
    record_decision(db, mint, "Scanner", "UNVERIFIED_MIGRATION_CLAIM", migration)

    pairs, status, err = get_json(session, f"{DEX}/{mint}", cfg.request_timeout_s)
    path = save_raw(out, "dex", mint, pairs if err is None else {"error":err,"http_status":status})
    record_source(db, mint, "dex", path, status, err)
    summ = dex_summary(pairs, migration.get("pool"))
    record_decision(db, mint, "Scanner", summ["status"], summ)

    rug, status, err = get_json(session, f"{RUG}/{mint}/report", cfg.request_timeout_s)
    path = save_raw(out, "rugcheck", mint, rug if err is None else {"error":err,"http_status":status})
    record_source(db, mint, "rugcheck", path, status, err)

    rpc_inputs = [("getAccountInfo", [mint, {"encoding":"jsonParsed"}]),
                  ("getTokenSupply", [mint]), ("getTokenLargestAccounts", [mint])]
    rpc_results = {}
    for method, params in rpc_inputs:
        data = rpc_json(session, cfg.rpc_url, method, params, cfg.request_timeout_s)
        rpc_results[method] = data
        path = save_raw(out, method, mint, data)
        err = str(data.get("error"))[:180] if isinstance(data, dict) and data.get("error") else None
        record_source(db, mint, method, path, data.get("http_status") if isinstance(data,dict) else None, err)
    authorities = mint_authorities(rpc_results["getAccountInfo"])
    layers = audit_layers(authorities, summ, rug, rpc_results["getTokenSupply"], rpc_results["getTokenLargestAccounts"])
    verdict = research_verdict(layers)
    record_decision(db, mint, "Auditor", verdict, {"layers": layers, "source_status": "INCOMPLETE_BY_DESIGN"})
    return {"mint":mint, "symbol":migration.get("symbol"), "pool":migration.get("pool"),
            "scanner":summ, "auditor":verdict, "layers":layers,
            "note":"Data research only. No signal, no position, no live or paper fill."}


async def capture_migrations(cfg: ObservationConfig, out: Path) -> tuple[list[tuple[dict,dict]], dict]:
    """One bounded connection, no subscription guesses, no retries or trading.

    `migrations` counts legacy parser matches, never independently proven events.
    Every frame contributes to diagnostics, even when the parser rejects it.
    """
    import websockets
    cfg.validate_capture()
    out.mkdir(parents=True, exist_ok=True)
    migrations: list[tuple[dict,dict]] = []
    seen: set[str] = set()
    count = 0
    status = {"connected":False, "events_seen":0, "migrations":0, "reason":None, "stream":STREAM,
              "schema_status": "UNVALIDATED", "independent_migration_proof": "UNKNOWN",
              "error": None}
    evidence = StreamEvidence(STREAM, utcnow())
    deadline = time.monotonic() + cfg.duration_s
    try:
        async with asyncio.timeout(cfg.duration_s):
            async with websockets.connect(STREAM, open_timeout=min(12, cfg.duration_s), close_timeout=1,
                                          max_size=1_500_000, max_queue=16, ping_interval=20) as ws:
                status["connected"] = True
                while count < cfg.max_events and len(migrations) < cfg.max_migrations:
                    msg = await asyncio.wait_for(ws.recv(), timeout=max(0.001, deadline - time.monotonic()))
                    count += 1
                    data = None
                    migration = None
                    try:
                        data = json.loads(msg)
                    except (ValueError, TypeError, RecursionError):
                        outcome = "invalid_json"
                    else:
                        migration = migration_from_event(data)
                        if not isinstance(data, dict):
                            outcome = "non_object"
                        elif data.get("action") != "migrate":
                            outcome = "not_legacy_migrate_action"
                        elif migration is None:
                            outcome = "invalid_mint"
                        elif migration["mint"] in seen:
                            outcome = "duplicate_mint"
                        else:
                            outcome = "legacy_parser_match_unvalidated"
                            seen.add(migration["mint"])
                            migrations.append((migration, data))
                    evidence.observe(msg, data, outcome, utcnow())
                status["reason"] = ("sample_goal" if len(migrations) == cfg.max_migrations else "event_limit")
    except TimeoutError:
        status["reason"] = "time_limit" if status["connected"] else "stream_error"
        if not status["connected"]:
            status["error"] = {"category": "connection_timeout", "exception_type": "TimeoutError"}
    except Exception as exc:
        # Never persist exception text: it may contain URLs, headers or credentials.
        response = getattr(exc, "response", None)
        code = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
        category = ("http_rejected" if isinstance(code, int) else
                    "connection_closed" if isinstance(exc, websockets.exceptions.ConnectionClosed) else
                    "transport_error")
        status["reason"] = "stream_error"
        status["error"] = {"category": category, "exception_type": type(exc).__name__,
                           "http_status": code if isinstance(code, int) else None}
    status["events_seen"] = count
    status["migrations"] = len(migrations)
    status["legacy_parser_matches"] = len(migrations)
    status["parser_outcomes"] = dict(evidence.outcomes)
    status["evidence"] = evidence.write(out, utcnow(), status)
    return migrations, status


def write_summary(out: Path, results: list[dict], status: dict):
    payload = {"captured_at": utcnow(), "mode":"READ_ONLY_NO_TRADING",
               "stream":status, "results":results}
    (out / "run_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
