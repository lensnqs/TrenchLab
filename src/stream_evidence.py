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
MAX_MIGRATION_SAMPLES = 8
MAX_MIGRATION_SAMPLE_BYTES = 16 * 1024
MAX_EVIDENCE_BYTES = 512 * 1024


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


def migration_fields(value):
    """Fixed projection of provider claims; no arbitrary keys or free text.

    Known pool labels are provider assertions, never origin or LP verification.
    Missing, malformed and unrecognized fields stay explicitly UNKNOWN.
    """
    result = {key: "UNKNOWN" for key in (
        "action", "mint", "poolId", "signature", "quoteMint", "pool", "poolCreatedBy",
        "tokenProgram", "burnedLiquidity", "timestamp", "block")}
    result["action"] = "migrate"
    for key in ("mint", "poolId", "quoteMint"):
        item = value.get(key)
        if isinstance(item, str) and _ADDRESS.fullmatch(item):
            result[key] = item
    signature = value.get("signature")
    if isinstance(signature, str) and _SIGNATURE.fullmatch(signature):
        result["signature"] = signature
    for key, allowed in (("pool", ("pump-amm",)), ("poolCreatedBy", ("pump",)),
                         ("tokenProgram", ("spl-token-2022",)), ("burnedLiquidity", ("100%",))):
        if isinstance(value.get(key), str) and value[key] in allowed:
            result[key] = value[key]
    if safe_time(value.get("timestamp")):
        result["timestamp"] = value["timestamp"]
    block = value.get("block")
    if type(block) is int and 0 <= block < 2**64:
        result["block"] = block
    return result


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
        self.migration_samples = []
        self.migration_sample_bytes = 0
        self.migration_hashes = set()  # At most eight retained message hashes.
        self.migration_sampling = Counter()

    def sample_migration(self, frame, data, outcome, observed_at):
        if not (isinstance(data, dict) and data.get("action") == "migrate"
                and isinstance(data.get("mint"), str) and _ADDRESS.fullmatch(data["mint"])):
            return
        self.migration_sampling["eligible_frames"] += 1
        if len(self.migration_samples) >= MAX_MIGRATION_SAMPLES:
            self.migration_sampling["omitted_capacity"] += 1
            return
        digest = sha256(frame).hexdigest()
        if digest in self.migration_hashes:
            self.migration_sampling["duplicate_retained_hash"] += 1
            return
        sample = {"sequence": self.events, "source": self.stream, "observed_at": observed_at,
                  "wire_sha256": digest, "message_bytes": len(frame), "outcome": outcome,
                  "evidence_classification": "UNVERIFIED_PROVIDER_MIGRATION_CLAIM",
                  "source_verification": "UNKNOWN",
                  "independent_migration_proof": "UNKNOWN", "origin_verification": "UNKNOWN",
                  "provider_timestamp_semantics": "UNKNOWN", "provider_fields": migration_fields(data)}
        size = len(json.dumps(sample, separators=(",", ":")).encode("utf-8")) + 1
        if self.migration_sample_bytes + size > MAX_MIGRATION_SAMPLE_BYTES:
            self.migration_sampling["omitted_byte_budget"] += 1
            return
        self.migration_samples.append(sample)
        self.migration_sample_bytes += size
        self.migration_hashes.add(digest)
        self.migration_sampling["retained"] += 1

    def observe(self, message, data, outcome, observed_at):
        self.events += 1
        bounded_increment(self.outcomes, outcome)
        frame = message.encode("utf-8") if isinstance(message, str) else message
        # Independent of general sample count, byte budget, key order and shape quota.
        self.sample_migration(frame, data, outcome, observed_at)
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
                              "counter_keys": MAX_COUNTER_KEYS, "samples_per_shape": 2,
                              "migration_samples": MAX_MIGRATION_SAMPLES,
                              "migration_sample_bytes": MAX_MIGRATION_SAMPLE_BYTES,
                              "evidence_file_bytes": MAX_EVIDENCE_BYTES},
                   "samples": self.samples, "capture_status": status.copy(),
                   "migration_samples": self.migration_samples,
                   "migration_sampling": {key: self.migration_sampling[key] for key in
                       ("eligible_frames", "retained", "duplicate_retained_hash", "omitted_capacity",
                        "omitted_byte_budget")},
                   "hash_note": "wire_sha256 hashes decoded application-message bytes, not network framing; file hash covers sanitized JSON"}
        encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) > MAX_EVIDENCE_BYTES:
            raise ValueError("sanitized evidence exceeded the file budget")
        path = out / f"stream_evidence_{uuid4().hex}.json"
        with path.open("xb") as handle:
            handle.write(encoded)
        return {"file": str(path), "sha256": sha256(encoded).hexdigest(),
                "samples": len(self.samples)}
