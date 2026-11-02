"""Research-only, offline, deterministic five-agent mock desk.

NOT a live trading bot. All supplied fixtures are fictional. All fills are
hypothetical, quotes are not executable, and contract audits are simulated.
"""
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


def require_number(obj, key):
    value = obj.get(key)
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"missing/invalid {key}: fail closed")
    return float(value)


def clamp(x):
    return max(0.0, min(1.0, x))


@dataclass(frozen=True)
class Config:
    min_liquidity_usd: float = 40_000
    max_top10_pct: float = 25
    max_h1_change_pct: float = 80
    min_age_min: float = 10
    max_dev_pct: float = 5
    min_lp_locked_pct: float = 99
    max_bundled: int = 5
    max_delegate_holders: int = 10
    allocation_pct: float = 2.0    # DELIBERATELY lowered vs promoted 8%; no forced min-ticket bump
    max_pool_pct: float = 2.0
    stop_pct: float = 6.0
    trail_start_pct: float = 20.0
    trail_pct: float = 12.0
    timeout_hours: float = 3.0
    timeout_min_gain_pct: float = 5.0
    assumed_slippage_pct: float = 1.0  # illustration ONLY, not empirically calibrated
    assumed_fee_pct_each_side: float = 1.0  # illustration ONLY, not FOMO's documented fees


def scan(c, cfg):
    for key in ("liquidity_usd", "top10_pct", "h1_change_pct", "age_min"):
        require_number(c, key)
    if c.get("is_copycat") is not False:
        return {"passed": False, "reason": "copycat status unknown or true"}
    checks = [
        (c["liquidity_usd"] >= cfg.min_liquidity_usd, "liquidity below minimum"),
        (c["top10_pct"] <= cfg.max_top10_pct, "top-10 concentration too high"),
        (c["h1_change_pct"] <= cfg.max_h1_change_pct, "already ran above cap"),
        (c["age_min"] >= cfg.min_age_min, "pool too young"),
    ]
    for good, why in checks:
        if not good:
            return {"passed": False, "reason": why}
    return {"passed": True, "reason": "synthetic scanner requirements passed"}


def audit(c, cfg):
    specs = [
        ("mint authority", "mint_revoked", lambda x: x is True),
        ("freeze authority", "freeze_revoked", lambda x: x is True),
        ("developer balance", "dev_pct", lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x < cfg.max_dev_pct and c.get("dev_sold") is False),
        ("top holders", "top10_pct", lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x < cfg.max_top10_pct),
        ("liquidity lock", "lp_locked_pct", lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= cfg.min_lp_locked_pct and c.get("liquidity_declined_over_50pct") is False),
        ("pool age", "age_min", lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= cfg.min_age_min),
        ("bundled wallet cluster", "bundled_largest", lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x < cfg.max_bundled),
        ("delegate concentration", "max_delegate_holders", lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x <= cfg.max_delegate_holders),
    ]
    layers = []
    for name, field, predicate in specs:
        value = c.get(field)
        passed = bool(predicate(value))
        layers.append({"name": name, "observed": value, "passed": passed})
        if not passed:
            return {"passed": False, "layers": layers, "reason": f"{name}: {field}={value!r}"}
    return {"passed": True, "layers": layers, "reason": "all eight synthetic fixture checks passed (NOT a real safety certification)"}


def analyze(c):
    """Explicitly uncalibrated proxies, NOT probability forecasts or wallet verification."""
    try:
        volume = require_number(c, "volume_h1")
        buys = require_number(c, "buys_h1")
        price_m5 = require_number(c, "price_change_m5_pct")
        price_h1 = require_number(c, "h1_change_pct")
        buys_m5 = require_number(c, "buys_m5")
        sells_m5 = require_number(c, "sells_m5")
    except ValueError as e:
        return {"passed": False, "reason": str(e), "score": None}
    activity_proxy = clamp(volume / 25_000)
    buying_proxy = clamp(buys / 150) * (0.5 if c["bundled_largest"] >= 3 else 1)
    dip_proxy = 1.0 if price_m5 <= -5 and buys_m5 >= sells_m5 else (0.5 if price_m5 < 0 else 0.0)
    chase_proxy = clamp(max(0, price_h1) / 80)
    score = round(100 * (activity_proxy + buying_proxy + dip_proxy + 1-chase_proxy) / 4)
    passed = activity_proxy >= .70 and buying_proxy >= .65 and chase_proxy <= .30 and score >= 70
    return {"passed": passed, "score": score, "reason": "uncalibrated heuristic score; not a forecast", "proxies": {"volume_activity": activity_proxy, "buys_activity": buying_proxy, "recent_dip": dip_proxy, "chase": chase_proxy}}


def propose(c, stack, cfg):
    """No minimum ticket bump, no wallet, no order link, no capital transfer."""
    liq = require_number(c, "liquidity_usd")
    price = require_number(c, "price_usd")
    if price <= 0 or liq <= 0:
        return {"passed": False, "reason": "unpriced/no liquidity"}
    ticket = round(min(stack * cfg.allocation_pct/100, liq * cfg.max_pool_pct/100), 2)
    if ticket <= 0 or ticket > stack:
        return {"passed": False, "reason": "no affordable allocation"}
    return {"passed": True, "size_usd": ticket, "signal_price": price, "status": "HYPOTHETICAL_SIGNAL_ONLY"}


def paper_open(signal, ts, cfg):
    """Hypothetical price with assumed positive slippage. Never an actual fill."""
    px = signal["signal_price"] * (1 + cfg.assumed_slippage_pct/100)
    return {"opened_at": ts, "entry": px, "peak": px, "stop": px*(1-cfg.stop_pct/100), "trail_active": False, "size_usd": signal["size_usd"], "status": "HYPOTHETICAL_PAPER", "exit": None}


def observe_risk(pos, observed_price, observed_liquidity, ts, cfg):
    """Never assume sellable last-price fills during a liquidity collapse."""
    if observed_price is None or observed_liquidity is None or observed_liquidity <= 0:
        pos["status"] = "UNPRICED_EXIT_UNCERTAIN"
        return {"action": "UNKNOWN_EXIT", "reason": "price/liquidity unavailable; no paper PnL fabricated"}
    price = float(observed_price)
    if not math.isfinite(price) or price <= 0:
        pos["status"] = "UNPRICED_EXIT_UNCERTAIN"
        return {"action": "UNKNOWN_EXIT", "reason": "price unavailable"}
    pos["peak"] = max(pos["peak"], price)
    if price >= pos["entry"]*(1 + cfg.trail_start_pct/100):
        pos["trail_active"] = True
    if pos["trail_active"]:
        pos["stop"] = max(pos["stop"], pos["peak"]*(1-cfg.trail_pct/100))
    age_hours = (ts - pos["opened_at"]).total_seconds()/3600
    triggered = price <= pos["stop"]
    expired = age_hours >= cfg.timeout_hours and price < pos["entry"]*(1+cfg.timeout_min_gain_pct/100)
    if not triggered and not expired:
        return {"action": "HOLD", "stop": pos["stop"], "trail_active": pos["trail_active"]}
    why = "TRAIL_OR_STOP" if triggered else "TIMEOUT"
    # Deliberately label this as an assumed, NOT executable, counterfactual.
    hypothetical_exit = price*(1-cfg.assumed_slippage_pct/100)
    qty = pos["size_usd"]/pos["entry"]
    gross = qty*(hypothetical_exit-pos["entry"])
    fees = pos["size_usd"]*cfg.assumed_fee_pct_each_side/100 + qty*hypothetical_exit*cfg.assumed_fee_pct_each_side/100
    pnl = round(gross-fees, 4)
    pos["status"] = "PAPER_CLOSED_ASSUMED_FILLS"
    pos["exit"] = hypothetical_exit
    return {"action": "PAPER_EXIT", "reason": why, "hypothetical_exit": hypothetical_exit, "hypothetical_pnl_usd": pnl, "fee_assumption_usd": round(fees, 4)}


def run_fixture(fixture_path, output_dir):
    source = json.loads(Path(fixture_path).read_text())
    if source.get("data_kind") != "SYNTHETIC_FIXTURE":
        raise ValueError("this v0.1 runner requires synthetic fixture data")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    timestamp = datetime.fromisoformat(source["timestamp"].replace("Z", "+00:00"))
    db = sqlite3.connect(str(out / "journal.sqlite3"))
    db.execute("CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, ts TEXT, mint TEXT, stage TEXT, passed TEXT, details_json TEXT)")
    db.execute("DELETE FROM decisions")
    events = []
    def record(mint, stage, result):
        row = {"ts": timestamp.isoformat(), "mint": mint, "stage": stage, **result}
        events.append(row)
        db.execute("INSERT INTO decisions(ts,mint,stage,passed,details_json) VALUES(?,?,?,?,?)", (row["ts"], mint, stage, str(result.get("passed")), json.dumps(result)))
    stack = float(source["paper_start_stack"])
    for coin in source["coins"]:
        mint = coin["mint"]
        s = scan(coin, cfg); record(mint,"Scanner",s)
        if not s["passed"]: continue
        a = audit(coin,cfg); record(mint,"Auditor",a)
        if not a["passed"]: continue
        n = analyze(coin); record(mint,"Analyst",n)
        if not n["passed"]: continue
        ex = propose(coin,stack,cfg); record(mint,"Executor",ex)
        if not ex["passed"]: continue
        position = paper_open(ex,timestamp,cfg)
        for step in coin["fictional_future_observations"]:
            seen = timestamp + timedelta(minutes=step["minutes_later"])
            result = observe_risk(position,step.get("price_usd"),step.get("liquidity_usd"),seen,cfg)
            record(mint,"Risk",result)
            if result["action"] != "HOLD": break
    db.commit()
    db.close()
    (out / "decisions.json").write_text(json.dumps(events,indent=2)+"\n")
    (out / "README_RESULTS.txt").write_text("SYNTHETIC TEST DATA ONLY. No live API calls, wallets, real orders or verified fills.\n" + f"{len(events)} stage events; inspect decisions.json and journal.sqlite3.\n")
    return events
