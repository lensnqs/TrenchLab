"""Offline resource/coverage tests. All traffic and clocks are synthetic.

The sole published payload is a DOCS_EXAMPLE_NOT_LIVE_EVIDENCE excerpt supplied
by ORBIT; mutations and replays below do not authenticate a provider or chain.
"""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from src.observe import ObservationConfig, capture_migrations
from src.stream_evidence import (MAX_EVIDENCE_BYTES, MAX_MIGRATION_SAMPLES,
                                 MAX_MIGRATION_SAMPLE_BYTES, StreamEvidence)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads((ROOT / 'fixtures/pumpapi_docs_example.json').read_text())['migration']
NOW = '2026-11-02T20:00:00+00:00'


def wire(value):
    return json.dumps(value)


class ClockSocket:
    def __init__(self, events, clock):
        self.events = iter(events)
        self.clock = clock
        self.send = AsyncMock()
        self.recv_count = 0

    async def recv(self):
        self.recv_count += 1
        offset, item = next(self.events)
        self.clock.now = offset
        if isinstance(item, Exception):
            raise item
        return item


class ClockConnection:
    def __init__(self, socket, connect_at):
        self.socket = socket
        self.connect_at = connect_at
        self.closed = False

    async def __aenter__(self):
        self.socket.clock.now = self.connect_at
        return self.socket

    async def __aexit__(self, *args):
        self.closed = True


class TimePriorityTests(unittest.IsolatedAsyncioTestCase):
    async def capture(self, events, *, connect_at=0, **kwargs):
        clock = SimpleNamespace(now=0)
        socket = ClockSocket(events, clock)
        connection = ClockConnection(socket, connect_at)
        cfg = ObservationConfig(time_priority=True, max_events=1_000_000, **kwargs)
        with tempfile.TemporaryDirectory() as temp, \
             patch('src.observe.time', SimpleNamespace(monotonic=lambda: clock.now)), \
             patch('websockets.connect', return_value=connection) as connect:
            matches, status = await capture_migrations(cfg, Path(temp))
            evidence = json.loads(Path(status['evidence']['file']).read_text())
            self.assertEqual(sha256(Path(status['evidence']['file']).read_bytes()).hexdigest(),
                             status['evidence']['sha256'])
        connect.assert_called_once()
        self.assertTrue(connection.closed)
        socket.send.assert_not_called()
        self.assertEqual(matches, [], 'time-priority must not retain raw candidate payloads')
        self.assertEqual(sum(status['parser_outcomes'].values()), status['events_seen'])
        self.assertEqual(status['independent_migration_proof'], 'UNKNOWN')
        return status, evidence, socket, connect.call_args.kwargs

    async def test_late_claim_after_15000_same_shape_trades_survives_to_duration(self):
        trade = wire({**EXAMPLE, 'action': 'buy'})
        def events():
            for i in range(15001):
                yield (i / 10000, trade)
            yield (179, wire(EXAMPLE))
            yield (180, trade)
        status, evidence, socket, options = await self.capture(events(), duration_s=180, max_migrations=1)
        self.assertEqual(status['events_seen'], 15003)
        self.assertEqual(status['reason'], 'time_limit')
        self.assertEqual(status['coverage'], 'DURATION_REACHED')
        self.assertEqual(status['connected_observation_s'], 180)
        self.assertEqual(socket.recv_count, 15003)
        self.assertEqual(status['legacy_parser_matches'], 1)
        self.assertEqual(sum(b['events'] for b in status['time_bins']), 15003)
        self.assertEqual(sum(b['migration_claim_frames'] for b in status['time_bins']), 1)
        self.assertEqual(len(evidence['samples']), 2)  # Both are earlier trades.
        self.assertTrue(all(s['sanitized_message']['action'] == 'buy' for s in evidence['samples']))
        claim = evidence['migration_samples'][0]
        self.assertEqual(claim['sequence'], 15002)
        self.assertEqual(claim['provider_fields']['signature'], EXAMPLE['signature'])
        self.assertEqual(claim['wire_sha256'], sha256(wire(EXAMPLE).encode()).hexdigest())
        self.assertEqual(options['max_size'], 64 * 1024)
        self.assertEqual(options['max_queue'], 4)
        self.assertIsNone(options['compression'])

    async def test_full_claim_allocation_and_legacy_goal_do_not_end_observation(self):
        payloads = [{**EXAMPLE, 'mint': char * 32} for char in 'ABCDEFGHJKLMNPQRSTUV']
        events = [(i + 1, wire(p)) for i, p in enumerate(payloads)] + [(180, '{}')]
        status, evidence, _, _ = await self.capture(events, duration_s=180, max_migrations=1)
        self.assertEqual(status['migration_claim_frames'], 20)
        self.assertEqual(status['legacy_parser_matches'], 20)
        self.assertEqual(status['coverage'], 'DURATION_REACHED')
        self.assertEqual(len(evidence['migration_samples']), 8)
        self.assertEqual(evidence['migration_sampling']['omitted_capacity'], 12)

    async def test_connected_duration_excludes_connection_setup(self):
        status, _, _, _ = await self.capture([(185, '{}')], connect_at=5, duration_s=180)
        self.assertEqual(status['connected_observation_s'], 180)
        self.assertEqual(status['elapsed_s'], 185)
        self.assertEqual(status['coverage'], 'DURATION_REACHED')

    async def test_frame_guard_is_reported_as_truncated_coverage(self):
        clock = SimpleNamespace(now=0)
        socket = ClockSocket([(1, '{}'), (2, '{}')], clock)
        with tempfile.TemporaryDirectory() as temp, \
             patch('src.observe.time', SimpleNamespace(monotonic=lambda: clock.now)), \
             patch('websockets.connect', return_value=ClockConnection(socket, 0)):
            _, status = await capture_migrations(
                ObservationConfig(time_priority=True, max_events=2, duration_s=180), Path(temp))
        self.assertEqual(status['reason'], 'event_limit')
        self.assertEqual(status['coverage'], 'TRUNCATED')
        self.assertEqual(status['connected_observation_s'], 2)

    async def test_cumulative_byte_guard_counts_unparsed_crossing_message(self):
        with patch('src.observe.TIME_PRIORITY_TOTAL_BYTES', 5):
            status, evidence, _, _ = await self.capture([(1, '{}'), (2, '{}'), (3, '{}')], duration_s=180)
        self.assertEqual(status['reason'], 'byte_limit')
        self.assertEqual(status['received_message_bytes'], 6)
        self.assertEqual(status['parser_outcomes']['byte_budget_exceeded'], 1)
        self.assertEqual(status['coverage'], 'TRUNCATED')
        self.assertEqual(evidence['events_seen'], 3)

    async def test_dedup_saturation_is_an_explicit_unique_count_lower_bound(self):
        payloads = [{**EXAMPLE, 'mint': char * 32} for char in 'ABCCA']
        with patch('src.observe.MAX_TRACKED_MINTS', 2):
            status, evidence, _, _ = await self.capture(
                [(i + 1, wire(p)) for i, p in enumerate(payloads)] + [(180, '{}')], duration_s=180)
        self.assertEqual(status['legacy_parser_matches'], 2)
        self.assertFalse(status['distinct_mint_count_complete'])
        self.assertEqual(status['dedup_overflow_frames'], 2)
        self.assertEqual(status['migration_claim_frames'], 5)
        self.assertEqual(status['parser_outcomes']['duplicate_mint'], 1)
        self.assertEqual(len(evidence['migration_samples']), 3)

    async def test_disconnect_retains_reserved_claim_and_marks_partial_duration(self):
        from websockets.exceptions import ConnectionClosedError
        status, evidence, _, _ = await self.capture(
            [(1, wire(EXAMPLE)), (2, ConnectionClosedError(None, None))], duration_s=180)
        self.assertEqual(status['reason'], 'stream_error')
        self.assertEqual(status['coverage'], 'TRUNCATED')
        self.assertEqual(status['connected_observation_s'], 2)
        self.assertEqual(len(evidence['migration_samples']), 1)

    async def test_early_receive_timeout_cannot_claim_full_duration(self):
        status, _, _, _ = await self.capture([(1, TimeoutError())], duration_s=180)
        self.assertEqual(status['reason'], 'stream_error')
        self.assertEqual(status['error']['category'], 'receive_timeout')
        self.assertEqual(status['coverage'], 'TRUNCATED')
        self.assertLess(status['connected_observation_s'], status['duration_target_s'])

    async def test_time_priority_requires_capture_only_before_any_network(self):
        from run_live import run
        with patch('websockets.connect') as connect:
            with self.assertRaises(ValueError):
                await run(time_priority=True)
            connect.assert_not_called()

    async def test_time_priority_entry_point_defaults_and_no_downstream_calls(self):
        from run_live import run
        with tempfile.TemporaryDirectory() as temp, patch('builtins.print'), \
             patch('run_live.capture_migrations', new=AsyncMock(return_value=([], {'reason': 'time_limit'}))) as capture, \
             patch('requests.Session.get') as get, patch('requests.Session.post') as post:
            await run(time_priority=True, capture_only=True, output=temp)
        cfg = capture.call_args.args[0]
        self.assertTrue(cfg.time_priority)
        self.assertEqual(cfg.duration_s, 180)
        self.assertEqual(cfg.max_events, 1_000_000)
        get.assert_not_called()
        post.assert_not_called()

    async def test_invalid_time_priority_configuration_fails_before_connect(self):
        for kwargs in ({'time_priority': 'yes'}, {'time_priority': True, 'max_events': 1_000_001}):
            with tempfile.TemporaryDirectory() as temp, patch('websockets.connect') as connect:
                with self.assertRaises(ValueError):
                    await capture_migrations(ObservationConfig(**kwargs), Path(temp))
                connect.assert_not_called()


class ReservedSamplingTests(unittest.TestCase):
    def observe(self, evidence, payload, outcome='legacy_parser_match_unvalidated'):
        evidence.observe(wire(payload), payload, outcome, NOW)

    def test_reserved_sample_is_independent_of_filled_general_count_and_shape_slots(self):
        evidence = StreamEvidence('mock', NOW)
        for i in range(20):
            self.observe(evidence, {f'field{i}': 'SECRET_SENTINEL'}, 'not_legacy_migrate_action')
        self.assertEqual(len(evidence.samples), 20)
        self.observe(evidence, EXAMPLE)
        self.assertEqual(len(evidence.samples), 20)
        self.assertEqual(len(evidence.migration_samples), 1)

    def test_reserved_sample_is_independent_of_general_byte_budget(self):
        evidence = StreamEvidence('mock', NOW)
        with patch('src.stream_evidence.MAX_SAMPLE_BYTES', 0):
            self.observe(evidence, EXAMPLE)
        self.assertEqual(evidence.samples, [])
        self.assertEqual(len(evidence.migration_samples), 1)

    def test_projection_preserves_published_fields_hash_and_separate_observation_time(self):
        evidence = StreamEvidence('wss://stream.pumpapi.io/', NOW)
        self.observe(evidence, EXAMPLE)
        sample = evidence.migration_samples[0]
        self.assertEqual(sample['provider_fields'], EXAMPLE)
        self.assertEqual(sample['wire_sha256'], sha256(wire(EXAMPLE).encode()).hexdigest())
        self.assertEqual(sample['observed_at'], NOW)
        self.assertEqual(sample['provider_fields']['timestamp'], 1793204432648)
        self.assertEqual(sample['independent_migration_proof'], 'UNKNOWN')
        self.assertEqual(sample['origin_verification'], 'UNKNOWN')
        self.assertEqual(sample['provider_timestamp_semantics'], 'UNKNOWN')

    def test_relevant_fields_after_general_key_limit_are_still_retained(self):
        evidence = StreamEvidence('mock', NOW)
        payload = {**{f'field{i}': 'SECRET_SENTINEL' for i in range(30)}, **EXAMPLE}
        self.observe(evidence, payload)
        self.assertEqual(evidence.migration_samples[0]['provider_fields'], EXAMPLE)
        self.assertNotIn('SECRET_SENTINEL', json.dumps(evidence.migration_samples))

    def test_unknown_missing_and_malformed_fields_never_expose_free_text(self):
        evidence = StreamEvidence('mock', NOW)
        payload = {'action': 'migrate', 'mint': EXAMPLE['mint'], 'poolId': 'SECRET_SENTINEL',
                   'signature': 'SECRET_SENTINEL', 'pool': 'SECRET_SENTINEL',
                   'poolCreatedBy': {'private': 'SECRET_SENTINEL'}, 'block': -1,
                   'name': 'SECRET_SENTINEL', 'apiKey': 'SECRET_SENTINEL'}
        self.observe(evidence, payload)
        fields = evidence.migration_samples[0]['provider_fields']
        for key in ('poolId', 'signature', 'pool', 'poolCreatedBy', 'timestamp', 'block', 'quoteMint'):
            self.assertEqual(fields[key], 'UNKNOWN')
        self.assertNotIn('name', fields)
        self.assertNotIn('SECRET_SENTINEL', json.dumps(evidence.migration_samples))

    def test_invalid_mint_and_create_pool_cannot_consume_reserved_slots(self):
        evidence = StreamEvidence('mock', NOW)
        for i in range(100):
            self.observe(evidence, {**EXAMPLE, 'mint': 'invalid'}, 'invalid_mint')
            self.observe(evidence, {**EXAMPLE, 'action': 'createPool'}, 'not_legacy_migrate_action')
        self.assertEqual(evidence.migration_samples, [])
        self.observe(evidence, EXAMPLE)
        self.assertEqual(len(evidence.migration_samples), 1)

    def test_repeats_and_overflow_do_not_grow_memory_or_budgets(self):
        evidence = StreamEvidence('mock', NOW)
        self.observe(evidence, EXAMPLE)
        self.observe(evidence, EXAMPLE)
        self.assertEqual(evidence.migration_sampling['duplicate_retained_hash'], 1)
        for i in range(1000):
            self.observe(evidence, {**EXAMPLE, 'block': i})
        self.assertEqual(len(evidence.migration_samples), MAX_MIGRATION_SAMPLES)
        self.assertEqual(len(evidence.migration_hashes), MAX_MIGRATION_SAMPLES)
        self.assertLessEqual(evidence.migration_sample_bytes, MAX_MIGRATION_SAMPLE_BYTES)
        self.assertGreater(evidence.migration_sampling['omitted_capacity'], 0)
        self.assertEqual(evidence.migration_sampling['eligible_frames'], sum(
            evidence.migration_sampling[k] for k in ('retained', 'duplicate_retained_hash',
                                                    'omitted_capacity', 'omitted_byte_budget')))

    def test_reserved_byte_budget_failure_is_explicit(self):
        evidence = StreamEvidence('mock', NOW)
        with patch('src.stream_evidence.MAX_MIGRATION_SAMPLE_BYTES', 1):
            self.observe(evidence, EXAMPLE)
        self.assertEqual(evidence.migration_samples, [])
        self.assertEqual(evidence.migration_sampling['omitted_byte_budget'], 1)

    def test_adversarial_general_cardinality_and_full_claim_projection_fit_file_limit(self):
        evidence = StreamEvidence('mock', NOW)
        for i in range(100):
            payload = {('k' * 42 + str(i) + str(j)): 'SECRET_SENTINEL' for j in range(24)}
            self.observe(evidence, payload, 'not_legacy_migrate_action')
        for i in range(8):
            self.observe(evidence, {**EXAMPLE, 'block': 2**64 - 1 - i})
        with tempfile.TemporaryDirectory() as temp:
            result = evidence.write(Path(temp), NOW, {})
            encoded = Path(result['file']).read_bytes()
        self.assertLessEqual(len(encoded), MAX_EVIDENCE_BYTES)
        self.assertNotIn(b'SECRET_SENTINEL', encoded)
        self.assertEqual(sha256(encoded).hexdigest(), result['sha256'])

    def test_file_budget_rejects_before_creating_a_partial_artifact(self):
        evidence = StreamEvidence('mock', NOW)
        self.observe(evidence, EXAMPLE)
        with tempfile.TemporaryDirectory() as temp, patch('src.stream_evidence.MAX_EVIDENCE_BYTES', 1):
            with self.assertRaises(ValueError):
                evidence.write(Path(temp), NOW, {})
            self.assertEqual(list(Path(temp).iterdir()), [])
