"""Bounded diagnostics, not a provider schema or proof of migration.

Wire hashes identify received frames. Persisted samples are sanitized projections,
not byte-for-byte raw frames. All other values (including free text) are removed.
"""
from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
import re
from uuid import uuid4


_LABEL = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,47}$")
_ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_SIGNATURE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{64,88}$")
# Probes only: preserve plausible original values without inferring units/meaning.
TIME_PROBES = ("timestamp", "time", "blockTime", "createdAt")
# These are diagnostic probes, NOT accepted event names or alternative parsers.
DISCRIMINATORS = ("action", "type", "event", "txType")
# Readable diagnostic labels only; this list confers no migration semantics.
# Unknown values are hashed so event-type counts cannot expose arbitrary secrets.
_PUBLIC_LABELS = frozenset(("buy", "sell", "create", "trade", "migrate", "migration",
                            "heartbeat", "ping", "pong", "error", "subscribed"))
MAX_SAMPLES = 20
MAX_SAMPLE_BYTES = 32768
MAX_COUNTER_KEYS = 64


def label(value):
    return value if isinstance(value, str) and _LABEL.fullmatch(value) else "<other>"


def type_label(value):
    if isinstance(value, str):
        if value in _PUBLIC_LABELS:
            return value
        return "sha256:" + sha256(value.encode("utf-8", errors="replace")).hexdigest()
    return "<" + kind(value) + ">"


def kind(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    return "number"


def shape(value):
    if not isinstance(value, dict):
        return kind(value)
    # Bounded top-level shape only; no nested data or arbitrary text values.
    return json.dumps(sorted((label(k), kind(v)) for k, v in list(value.items())[:24]),
                      separators=(",", ":"))


def sanitize(value):
    if not isinstance(value, dict):
        return {"json_kind": kind(value)}
    result = {}
    for key, item in list(value.items())[:24]:
        safe_key = label(key)
        if key in DISCRIMINATORS:
            result[safe_key] = type_label(item)
        elif key in TIME_PROBES and safe_time(item):
            result[safe_key] = item
        elif key in ("mint", "poolId") and isinstance(item, str) and _ADDRESS.fullmatch(item):
            result[safe_key] = item
        elif key == "signature" and isinstance(item, str) and _SIGNATURE.fullmatch(item):
            result[safe_key] = item
        else:
            result[safe_key] = {"redacted": True, "json_kind": kind(item)}
    return result


def safe_time(value):
    if type(value) in (int, float):
        return 0 <= value < 1e16
    if isinstance(value, str) and 10 <= len(value) <= 40:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            pass
    return False


def bounded_increment(counter, key):
    # Reserve one bucket so adversarial cardinality cannot grow memory/disk.
    if key not in counter and len(counter) >= MAX_COUNTER_KEYS - 1:
        key = "<overflow>"
    counter[key] += 1


class StreamEvidence:
    def __init__(self, stream, started_at):
        self.stream = stream
        self.started_at = started_at
        self.events = 0
        self.shapes = Counter()
        self.event_types = Counter()
        self.outcomes = Counter()
        self.samples = []
        self.sample_bytes = 0
        self.sample_counts = Counter()

    def observe(self, message, data, outcome, observed_at):
        self.events += 1
        bounded_increment(self.outcomes, outcome)
        frame = message.encode("utf-8") if isinstance(message, str) else message
        frame_shape = "invalid_json" if outcome == "invalid_json" else shape(data)
        bounded_increment(self.shapes, frame_shape)
        if isinstance(data, dict):
            for key in DISCRIMINATORS:
                if key in data:
                    bounded_increment(self.event_types, f"{key}={type_label(data[key])}")
        if (len(self.samples) >= MAX_SAMPLES or self.sample_counts[frame_shape] >= 2):
            return
        sample = {"sequence": self.events, "observed_at": observed_at,
                  "wire_sha256": sha256(frame).hexdigest(), "wire_bytes": len(frame),
                  "frame_kind": "text" if isinstance(message, str) else "binary",
                  "outcome": outcome, "shape": frame_shape,
                  "sanitized_message": None if outcome == "invalid_json" else sanitize(data)}
        encoded = json.dumps(sample, separators=(",", ":")).encode("utf-8")
        if self.sample_bytes + len(encoded) + 1 > MAX_SAMPLE_BYTES:
            return
        self.sample_counts[frame_shape] += 1
        self.samples.append(sample)
        self.sample_bytes += len(encoded) + 1

    def write(self, out, ended_at, status):
        payload = {"evidence_kind": "SANITIZED_STREAM_DIAGNOSTICS", "stream": self.stream,
                   "started_at": self.started_at, "ended_at": ended_at,
                   "subscription": {"messages_sent": 0, "schema_status": "UNVALIDATED"},
                   "schema_status": "UNVALIDATED", "independent_migration_proof": "UNKNOWN",
                   "provider_timestamp_semantics": "UNKNOWN; time probes retained verbatim when present",
                   "events_seen": self.events, "parser_outcomes": dict(self.outcomes),
                   "event_type_probes": dict(self.event_types), "top_level_shapes": dict(self.shapes),
                   "limits": {"samples": MAX_SAMPLES, "sample_bytes": MAX_SAMPLE_BYTES,
                              "counter_keys": MAX_COUNTER_KEYS, "samples_per_shape": 2},
                   "samples": self.samples, "capture_status": status.copy(),
                   "hash_note": "wire_sha256 hashes original frames; file hash covers sanitized JSON"}
        encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        path = out / f"stream_evidence_{uuid4().hex}.json"
        with path.open("xb") as handle:
            handle.write(encoded)
        return {"file": str(path), "sha256": sha256(encoded).hexdigest(),
                "samples": len(self.samples)}
